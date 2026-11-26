---
name: fsd-architecture
description: Use when organizing a service or monorepo into feature slices. Generic FSD layout, slice public API, cross-slice rules.
---

# fsd-architecture

Feature-Sliced Design(FSD)의 폴더 구성 원칙을 백엔드 서비스에 맞춰 정리한 **공통 스킬**이다. 특정 서비스·도메인에 묶이지 않는다.
어떤 슬라이스를 둘지, 규칙을 얼마나 강하게 적용할지는 서비스가 주입한다(4절).
슬라이스 안의 계층 구조는 [layered-architecture](../layered-architecture/SKILL.md)를 따른다.

## 1. 대응 관계

FSD는 프론트엔드에서 나온 구조라 백엔드에는 아래처럼 대응시킨다.

| FSD | 백엔드 서비스 | 내용 |
| --- | --- | --- |
| app | 서비스 루트의 조립 파일 (`main.py`, `container.py`, 전역 예외 핸들러) | 앱 생성, 미들웨어, 의존성 연결, 라우터 등록 |
| shared | `shared/` | 설정, 기반 예외, 도메인이 없는 유틸. 어떤 슬라이스도 모른다 |
| slice | 서비스 바로 아래 기능 폴더 (`<service>/<slice>/`) | 하나의 기능·바운디드 컨텍스트 |
| segment | 슬라이스 안의 계층 폴더 (domain, application, infrastructure, presentation) | 4계층 |

모노레포에서는 서비스 하나가 FSD 단위 하나다. 서비스끼리는 코드를 import하지 않고 HTTP·메시지 같은 공개 계약으로만 연결한다.

## 2. 규칙

1. 의존은 위에서 아래로만: app → slice → shared. shared는 슬라이스를 import하지 않는다.
2. 슬라이스는 다른 슬라이스의 내부(segment)를 import하지 않는다. 필요하면 상대 슬라이스의 **공개 API**(`<slice>/__init__.py`에서 내보낸 이름)만 쓴다.
3. 두 슬라이스가 서로를 필요로 하면 쓰는 쪽 domain에 포트를 두고, 상대 슬라이스 기반 어댑터를 조립 지점에서 연결한다. 순환 import를 만들지 않는다.
4. 여러 슬라이스가 쓰는 코드는 shared로 내린다. 슬라이스 안에 다른 슬라이스용 공용 코드를 두지 않는다.
5. 슬라이스는 필요한 segment만 만든다(예: 규칙이 없는 헬스 체크는 presentation만).

## 3. 공개 API

```python
# <service>/<slice>/__init__.py
from <service>.<slice>.application.service import SomeService
from <service>.<slice>.domain.entity import SomeEntity

__all__ = ["SomeService", "SomeEntity"]
```

다른 슬라이스는 `from <service>.<slice> import SomeService`로만 참조한다.

## 4. 서비스가 주입하는 것

| 항목 | 위치 | 값 |
| --- | --- | --- |
| 슬라이스 목록과 책임 | 서비스 아키텍처 문서·설계안 | 예: `orders`, `payments` |
| 슬라이스 간 규칙 강도 | layer-check 프로파일 `fsd.cross_slice` | `off`(검사 안 함) / `warn`(경고) / `error`(위반) |
| shared 폴더 이름 | 프로파일 `shared_dirs` | 기본 `shared` |
| 조립 파일 | 프로파일 `assembly_files` | 기본 `main.py`, `container.py` |

규칙 강도는 서비스가 정한다. 도입 초기에는 `off`나 `warn`으로 두고 팀이 구조를 확정하면 `error`로 올린다.

## 5. 검사

`fsd.cross_slice`가 `warn`·`error`이면 layer-check가 `[슬라이스]` 태그로 2절의 1·2번 규칙을 검사한다. 3~5번은 리뷰어가 코드를 읽어 판정한다.
