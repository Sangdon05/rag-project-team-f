# 관동도감 NEO-RETRO 프론트엔드

HTML, CSS, Vanilla JavaScript와 ES Modules로 만든 Red/Blue 관동도감 대화 화면입니다. [관동도감 열기](neo.html)에서 가상 유저를 고르면 메이트가 배정되고, 같은 화면에서 질문·답변·출처·원문 문서를 확인합니다.

| 질문자 | 가상 유저 | 메이트 | 추천 질문 level |
| --- | --- | --- | --- |
| A | 에이스 · P1 | 지우 | beginner |
| B | 루키 · P2 | 이슬이 | novice |
| C | 마스터 · P3 | 웅이 | expert |

각 유저의 추천 질문은 API가 반환하는 고정 후보 4개입니다. 실시간 에이전트가 생성하는 개인화 추천을 뜻하지 않습니다. HOME의 피카츄 인사창과 픽셀 하늘·구름·초원, 스프라이트를 유지하고 메이트 선택 후 투명한 채팅 레이어를 표시합니다. 사용자 질문은 오른쪽, 메이트 답변은 왼쪽에 쌓이고 메시지만 스크롤합니다.

## 실행

저장소 루트에서 두 터미널을 사용합니다. 프론트엔드는 별도 빌드 없이 HTTP로 제공합니다.

첫 터미널에서 비용 없는 API 연결 확인용 mock 서버를 실행합니다. PowerShell 예시입니다.

```powershell
$env:ANSWER_BACKEND = "mock"
$env:API_CORS_ORIGINS = "http://127.0.0.1:8772"
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
```

다른 터미널에서 정적 서버를 실행합니다.

```sh
uv run python -m http.server 8772 --bind 127.0.0.1
```

브라우저 주소는 `http://127.0.0.1:8772/frontend/neo.html#home`입니다. 파일을 직접 여는 방식 대신 위 HTTP 주소를 사용합니다.

`mock` 응답은 연결 확인용 예시이며 검색 결과가 아닙니다. 서버의 `llm` 모드는 검색 없이 답변을 생성합니다. 화면은 서버가 반환한 `mock`, `llm`, `rag`를 구분하고 출처가 없으면 그대로 표시합니다. 서버가 지원하는 백엔드와 실행 설정에 맞춰 사용합니다.

## API 연결

[neo-config.mjs](neo-config.mjs)의 `TEAM_API.baseUrl` 기본값은 `http://127.0.0.1:8000`입니다. 팀 서버 주소가 다르면 이 공개 URL을 변경하고, API 서버의 `API_CORS_ORIGINS`에 실제 프론트 origin을 설정합니다. 호스트 이름과 포트까지 같아야 합니다.

| 기능 | 메서드·경로 | 요청 |
| --- | --- | --- |
| 추천 질문 | `GET /api/v1/suggestion` | level Query, 기본 beginner |
| 질문·답변 | `POST /api/v1/chat` | messages 배열의 role/content만 전송 |
| 원문 문서 | `GET /api/v1/documents/{source_ref_id}` | 답변이 제공한 원문 ID |

API 성공 응답은 `success: true`와 `data`를 사용합니다. `source_ref_id`는 문자열로 보존하므로 `001`의 앞자리0도 유지됩니다. 원문은 사용자가 출처를 열 때 조회하고, 답변의 `[n]`을 해당 답변의 `sources[].ref`와 연결합니다. 전체 원문 문서는 검색된 청크 본문과 구분합니다.

기본 메시지 수 상한은20이며, 메시지 문자 수는 서버가 검증합니다. 서버 운영 한도가 달라지면 설정을 맞춥니다. 요청 실패는 화면에 표시하고 예시 답변으로 대체하지 않습니다. 인증정보는 브라우저 코드에 넣지 않습니다.

## 대화와 원문 표시

IndexedDB에 P1·P2·P3 대화 전체를 각각 저장합니다. 새로고침하거나 유저를 바꾼 뒤에도 해당 유저의 대화를 불러옵니다. 실패한 질문을 재시도할 때 같은 메시지 ID를 사용합니다.

API 전송용 기록에는 완료된 질문·답변 쌍과 새 질문만 포함합니다. 기본 상한20에서 최근9쌍과 새 질문인 최대19개를 전송하며, 인사말과 실패·미완료 응답은 제외합니다. assistant의 숫자 출처 표기는 전송용 복사본에서만 제거하고 저장된 원문과 출처는 유지합니다.

이전 메시지나 원문을 읽는 동안에는 자동 스크롤을 멈춥니다. 원문 Markdown은 허용된 DOM 요소로 구성하고 임의 HTML 실행·위험한 URL·외부 이미지 자동 로딩을 차단합니다. 출처의 순차 등장은 화면 연출이며 서버 검색 순서를 뜻하지 않습니다.

## 검증

Node.js로 API 계약, 대화 직렬화, 안전한 원문 표시와 배경 보존을 검사합니다. 아래 API 검사는 테스트 응답을 사용하며 실제 모델·DB를 호출하지 않습니다.

```sh
node --test tests/test_neo_team_client.mjs tests/test_neo_conversation.mjs tests/test_neo_chat_render.mjs tests/test_neo_background_lock.mjs tests/test_dialogue.mjs
```

정적 서버 실행 후 `http://127.0.0.1:8772/tests/neo-browser-qa.html`을 열면 별도 테스트 저장소와 테스트 응답으로 화면 흐름을 확인합니다. 페이지에 테스트용 응답이라는 표시가 있으며 실제 API 연결 검증과 구분합니다.

화면 표현은 관동 리메이크 스프라이트를 사용하고 도감 데이터 기준은 영문 Red/Blue입니다. 에셋 출처와 폰트 라이선스는 [에셋 출처](assets/neo/SOURCES.md)를 확인합니다.
