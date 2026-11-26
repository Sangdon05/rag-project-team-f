---
name: layered-architecture
description: Use when designing or reviewing a layered Python service. Generic 4-layer roles, dependency direction, ports/adapters, DI wiring.
---

# layered-architecture

서비스 하나를 4계층(presentation · application · domain · infrastructure)으로 나누는 **공통 원칙**이다. 특정 서비스·도메인에 묶이지 않는다.
서비스마다 다른 것(폴더 위치, 금지 패키지, 에러 코드, 외부 의존, R번호 규칙)은 이 스킬에 쓰지 않고 **서비스 규칙 스킬이 주입한다**(5절).

- 슬라이스(기능 단위) 폴더 구성과 슬라이스 간 규칙: [fsd-architecture](../fsd-architecture/SKILL.md)
- 자동 검사: [layer-check](../layer-check/SKILL.md)

## 1. 계층 책임

| 계층 | 책임 | 두지 않는 것 |
| --- | --- | --- |
| presentation | 요청·응답 형식 검증, 라우팅, 주입 지점 선언, 형식 ↔ 도메인 객체 변환 | 비즈니스 규칙, 구현체 생성, 예외를 HTTP 응답으로 직접 만들기 |
| application | 유스케이스 흐름: 도메인 객체 생성·조회 → 도메인 메서드 → 포트 호출 → 결과 반환. 트랜잭션이 있으면 그 경계 | 비즈니스 if-else, 쿼리·SDK 직접 사용 |
| domain | 엔티티·값 객체, 규칙 메서드·생성 팩토리, 도메인 예외, **포트(추상 인터페이스)** | 프레임워크·SDK·설정 읽기, 다른 계층 import |
| infrastructure | 포트 구현체(어댑터): DB, 외부 API, LLM, 파일. 외부 예외를 도메인 예외로 변환 | 유스케이스 흐름, 요청 형식 |

조립 지점(보통 `main.py`, `container.py`)은 계층 밖에 있으며 모든 계층을 알 수 있는 유일한 곳이다.

## 2. 의존 방향

```text
presentation ──▶ application ──▶ domain ◀── infrastructure
      ▲                                          ▲
      └────────────── 조립 지점 (container) ─────┘
```

- domain은 아무 계층도 import하지 않는다.
- application은 domain만 import한다. 구현체가 필요하면 포트를 생성자로 받는다.
- infrastructure는 domain만 import한다(포트를 구현하기 위해).
- presentation은 application과 domain을 import할 수 있고 infrastructure는 import하지 않는다.
- 공용 코드(shared)는 슬라이스의 infrastructure·application·presentation을 import하지 않는다.

이 방향은 4계층의 정의이므로 서비스가 바꾸지 않는다. layer-check가 고정 규칙으로 검사한다.

## 3. 도메인 모델

- 규칙은 엔티티의 메서드와 생성 팩토리(`create`)에 둔다. 서비스에 같은 규칙을 if-else로 두지 않는다. 속성만 있는 빈 엔티티를 만들지 않는다.
- 규칙 위반은 도메인 예외로 낸다. HTTP 상태 코드 변환은 presentation 밖의 전역 예외 핸들러가 한다.
- 설정값(한도 등)은 domain이 직접 읽지 않고 값 객체로 받는다. 읽는 일은 shared의 설정 모듈, 넘기는 일은 조립 지점이 한다.
- 용어는 코드·설계안·API 필드에서 같게 쓴다(유비쿼터스 언어). 용어 정의는 서비스 설계안이 원본이다.

## 4. 포트와 조립

### 4.1 포트 — domain

```python
from abc import ABC, abstractmethod


class Notifier(ABC):            # 예시 이름. 서비스가 자기 포트를 정한다
    @abstractmethod
    async def send(self, message: Message) -> Receipt: ...
```

- 외부 기능(저장소, 외부 API, LLM, 시계, 해싱)은 포트로 추상화한다.
- 구현체 이름은 `<기술·방식><포트명>`이다(예: `SmtpNotifier`, `FakeNotifier`).
- 구현체는 외부 예외를 그대로 올리지 않고 도메인 예외로 바꾼다. 원문 오류는 로그에만 남긴다.

### 4.2 응용 서비스 — 추상만 받는다

```python
class SendService:
    def __init__(self, notifier: Notifier) -> None:   # 필수 인자, 기본 구현체 생성 금지
        self.notifier = notifier
```

- 테스트는 fake 구현체를 넘겨 외부 의존 없이 검증한다.
- 서비스 생성자 안에서 다른 서비스나 구현체를 만들지 않는다.

### 4.3 주입 지점 — presentation (FastAPI 예)

```python
def provide_send_service() -> SendService:
    """Depends 플레이스홀더. 조립 지점에서 연결한다."""
    raise NotImplementedError("SendService 의존성이 연결되지 않았습니다.")
```

### 4.4 조립 지점 — container

- 구현체 선택(환경 변수 등)과 생성은 여기서만 한다. 알 수 없는 설정값이면 앱 시작 시점에 실패시킨다.
- `wire_dependencies(app, ...)`가 `app.dependency_overrides`에 모든 `provide_*`를 연결한다. 연결되지 않은 `provide_*`가 없어야 한다.
- 상태 없는 객체는 앱당 하나, 요청 상태(DB 세션 등)를 가진 객체는 요청마다 만든다.
- 앱은 `create_app(settings)` 함수로 만들어 테스트가 설정을 바꿔 다시 만들 수 있게 한다.
- 테스트는 `dependency_overrides`로 fake를 넣는다.

## 5. 서비스가 주입하는 것

이 스킬을 쓰는 서비스는 아래를 자기 규칙 스킬(예: `<service>-invariants`)에 둔다. 공통 스킬에는 쓰지 않는다.

| 주입 항목 | 형식 | 예 |
| --- | --- | --- |
| 서비스 위치·import 패키지 | layer-check 프로파일의 `root`, `package` | `svc/`, `svc` |
| 계층별 금지 패키지 | 프로파일 `forbidden_packages` | domain에서 프레임워크·SDK 금지 |
| 도메인 경계 규칙 | 서비스 규칙 문서(R번호) | 외부 SDK는 infrastructure에서만 |
| 에러 응답 형식·코드 | 서비스 규칙 문서 + 설계안 | 공통 에러 본문, 상태 코드 표 |
| 포트 목록과 계약 | 서비스 아키텍처 문서·연결 가이드 | 답변 생성기 계약 |
| 완료 게이트 명령 | 서비스 규칙 문서 | layer-check, import, 테스트 명령 |
| 설계안 위치 | 서비스 규칙 문서 | `docs/design/<service>/` |

서비스 규칙이 이 스킬과 충돌하면 서비스 규칙을 고치거나 이 스킬의 원칙을 바꾸는 제안을 한다. 서비스 문서에서 공통 원칙을 조용히 뒤집지 않는다.

## 6. 새 슬라이스 순서

domain(엔티티·예외·포트) → infrastructure(구현체) → application(서비스) → presentation(스키마·주입 지점·라우터) → 조립 지점 연결 → 테스트 → layer-check
