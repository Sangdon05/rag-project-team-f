# documents 설계안

상태: 검토 중

입력 원본: [API 엔드포인트 계획](../../plans/2026-11-26-api-endpoints.md) 2절 결정, 3절 `GET /api/v1/documents/{source_ref_id}`. 포트 계약 원본: [API–RAG 연결 가이드](../../references/api-rag-integration.md) 2절 "문서 저장소 포트". 응답 형식·공통 에러·기반 예외·설정은 [health 설계안 0절(공통)](health.md#0-공통)을 따른다.

## 1. 목적과 범위

[chat](chat.md) 응답의 `sources[].source_ref_id`로 출처 원문 Markdown을 돌려준다.

- 문서 원본은 RAG 데이터다. API는 파일을 **읽기만** 하고 고치지 않는다. 내용을 가공(HTML 변환, 공백 정리, 줄바꿈 변환)하지 않는다.
- 문서 파일 위치·이름 규칙은 RAG 쪽(chunking 스킬)이 원본이다. 바뀌면 `API_DOCUMENTS_DIR`만 바꾼다.
- 파일 목록 조회, 검색, 부분 조회는 범위 밖이다.

## 2. 용어

| 코드 이름 | 뜻 |
| --- | --- |
| `SourceRefId` | 문서 ID 값 객체. 도감번호 3자리(예: `001`). 형식 `[0-9]{3}` |
| `Document` | 조회 결과. `source_ref_id`, `markdown` |
| `DocumentStore` | 문서 저장소 포트. `get(source_ref_id) -> str` |
| `FileDocumentStore` | 파일 시스템 구현체 |
| `DocumentService` | 유스케이스 서비스 |

## 3. 도메인

### 3.1 엔티티·값 객체

`api/documents/domain/document.py`:

| 타입 | 필드 | 규칙 (불변식) | 위반 시 |
| --- | --- | --- | --- |
| `SourceRefId` (frozen) | `value: str` | `create(raw)`: 문자열이고 `re.fullmatch(r"[0-9]{3}", raw)`. 2자리·4자리, 숫자 밖 문자(`.`, `/`, `\`, 공백, `%`, 한글 등)가 있으면 거부. 변환(0 채우기, strip)하지 않는다 | `InvalidSourceRefIdError` |
| `Document` (frozen) | `source_ref_id: SourceRefId`, `markdown: str` | `markdown`은 받은 그대로(빈 문자열도 허용, 가공 없음) | — |

- `\d` 대신 `[0-9]`를 써서 유니코드 숫자(아랍 숫자 등)를 받지 않는다. `re.match(...$)` 대신 `fullmatch`를 써서 끝의 줄바꿈도 거부한다.
- 이 검증이 경로 탈출(`..`, 절대 경로)을 막는 유일한 방어선이다. 구현체는 검증된 `SourceRefId.value`만 받는다.

### 3.2 규칙 위반과 예외

`api/documents/domain/exceptions.py`:

| 예외 | 기반 | 상태 | `error_code` | 발생 조건 |
| --- | --- | --- | --- | --- |
| `InvalidSourceRefIdError` | `InvalidInputError` | 400 | `VALIDATION_ERROR` | `source_ref_id`에 허용 문자 밖 문자가 있음 |
| `DocumentNotFoundError` | `NotFoundError` | 404 | `DOCUMENT_NOT_FOUND` | 형식은 맞지만 `<API_DOCUMENTS_DIR>/<source_ref_id>_*.md`에 맞는 파일이 없음 |
| `DocumentSourceError` | `UpstreamError` | 502 | `DOCUMENT_SOURCE_FAILED` | 저장소 읽기 실패: 같은 번호 파일이 둘 이상(모호), 문서 폴더가 없거나 폴더가 아님, 권한 오류 등 `OSError`, UTF-8 디코딩 실패, 대상이 파일이 아님 |

메시지(고정 문구, 경로·원문 오류 비노출):

| 예외 | `message` |
| --- | --- |
| `InvalidSourceRefIdError` | `source_ref_id는 도감번호 3자리(예: 001)여야 합니다.` |
| `DocumentNotFoundError` | `문서를 찾을 수 없습니다.` |
| `DocumentSourceError` | `문서를 읽지 못했습니다. 잠시 후 다시 시도하세요.` |

## 4. 포트와 구현체

```python
# api/documents/domain/store.py — 계약 원본은 연결 가이드 2절
class DocumentStore(ABC):
    @abstractmethod
    async def get(self, source_ref_id: str) -> str: ...   # 원문 Markdown
```

- 포트 인자는 연결 가이드대로 `str`이다. 서비스가 `SourceRefId.value`(검증된 값)를 넘긴다.

| 구현체 | 위치 | 동작 |
| --- | --- | --- |
| `FileDocumentStore` | `api/documents/infrastructure/file_store.py` | 생성자 `base_dir: Path`. `get`: 아래 순서 |

`FileDocumentStore.get(source_ref_id)`:

1. `base_dir`가 폴더가 아니면(없음 포함) `DocumentSourceError`. 문서 폴더 설정 오류를 404로 숨기지 않기 위해서다.
2. `matches = sorted(base_dir.glob(f"{source_ref_id}_*.md"))`. 0개면 `DocumentNotFoundError`, 2개 이상이면 `DocumentSourceError`(같은 번호 파일이 여럿, 모호). 1개면 `path = matches[0]`.
3. `path.read_bytes()`를 `asyncio.to_thread`로 읽고 `bytes.decode("utf-8")`로 바꾼다. `read_text`의 줄바꿈 변환을 피해 원문 그대로 돌려준다.
4. 예외 변환:

   | 원래 예외 | 바꾼 예외 |
   | --- | --- |
   | `FileNotFoundError` | `DocumentNotFoundError` |
   | 그 밖의 `OSError` (`IsADirectoryError`, `PermissionError` 등) | `DocumentSourceError` |
   | `UnicodeDecodeError` | `DocumentSourceError` |

   원문 오류는 `logger.warning`에 예외 타입명과 `source_ref_id`만 남긴다(절대 경로·내용 비노출). `from exc`로 연결한다.

- 상대 경로 `base_dir`는 프로세스 작업 디렉터리(저장소 루트에서 서버 실행) 기준이다. container가 `Path(settings.documents_dir)`로 만든다.
- 파일을 쓰거나 지우는 메서드를 두지 않는다.

## 5. 유스케이스

`api/documents/application/service.py`:

```python
class DocumentService:
    def __init__(self, store: DocumentStore) -> None: ...

    async def get(self, raw_id: str) -> Document:
        source_ref_id = SourceRefId.create(raw_id)              # 형식 검증은 도메인 (R3)
        markdown = await self.store.get(source_ref_id.value)
        return Document(source_ref_id=source_ref_id, markdown=markdown)
```

- 형식이 틀리면 저장소를 부르지 않는다.

## 6. 엔드포인트 명세

### `GET /api/v1/documents/{source_ref_id}`

요청 path:

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `source_ref_id` | string | 예 | chat `sources[].source_ref_id` 값. 도감번호 3자리 `[0-9]{3}` (도메인 판정) |

- path 파라미터는 presentation에서 `str`로만 받는다(정규식 `Path(pattern=...)`을 쓰지 않는다). 형식 검증은 도메인 `SourceRefId.create`가 하며 위반은 `InvalidSourceRefIdError` → 400 `VALIDATION_ERROR`.
- **`/`가 들어간 id는 라우트에 매칭되지 않는다.** Starlette 기본 path 변환기는 `[^/]+`라서 `/api/v1/documents/a/b`는 이 라우트가 아니고, 맞는 경로가 없어 404 `NOT_FOUND`(공통)가 된다. `%2F`로 인코딩해도 Starlette가 디코딩된 경로로 매칭하므로 같은 404 `NOT_FOUND`다. `DOCUMENT_NOT_FOUND`·`VALIDATION_ERROR`가 아니다.
- 빈 id(`/api/v1/documents/`)도 매칭되지 않아 404 `NOT_FOUND`다.
- `.`, 공백, `%2E` 같은 다른 허용 밖 문자는 라우트에 매칭된 뒤 도메인에서 400 `VALIDATION_ERROR`다(예: `bulbasaur.md`, `..`).

응답 `data` (`DocumentData`, `SuccessResponse[DocumentData]`):

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `source_ref_id` | string | 예 | 요청한 id 그대로 |
| `markdown` | string | 예 | 원문 Markdown 그대로(HTML 변환 없음) |

에러 판정 순서: 라우트 매칭(`/` 포함·빈 id → 404 `NOT_FOUND`) → 도메인 형식 검증(400) → 저장소 폴더 확인(502) → 파일 읽기(404 `DOCUMENT_NOT_FOUND` / 502).

상태 코드:

| HTTP | `error_code` | 조건 |
| --- | --- | --- |
| 200 | — | 파일을 읽음 |
| 400 | `VALIDATION_ERROR` | id가 도감번호 3자리가 아님 (라우트에 매칭된 경우) |
| 404 | `DOCUMENT_NOT_FOUND` | 형식은 맞지만 파일 없음 |
| 404 | `NOT_FOUND` | id에 `/`가 들어가거나 비어 있어 라우트에 매칭되지 않음 (공통) |
| 405 | `METHOD_NOT_ALLOWED` | GET 외 메서드 |
| 502 | `DOCUMENT_SOURCE_FAILED` | 문서 폴더 없음, 읽기 권한·디코딩 실패 등 저장소 읽기 실패 |
| 500 | `INTERNAL_ERROR` | 처리 못 한 예외. 원문 비노출 |

예시 (`API_DOCUMENTS_DIR=solar_handoff/documents`):

```http
GET /api/v1/documents/001
```

```json
{"success": true, "data": {"source_ref_id": "001", "markdown": "# 이상해씨\n..."}}
```

```json
{"success": false, "error_code": "DOCUMENT_NOT_FOUND", "message": "문서를 찾을 수 없습니다."}
```

파일 배치:

```text
api/documents/
  __init__.py
  domain/          document.py (SourceRefId, Document), store.py (DocumentStore), exceptions.py
  application/     service.py (DocumentService)
  infrastructure/  file_store.py (FileDocumentStore)
  presentation/    schemas.py (DocumentData.from_domain), dependencies.py (provide_document_service), router.py
```

- router: `APIRouter(prefix="/api/v1", tags=["documents"])`, `GET /documents/{source_ref_id}`, `response_model=SuccessResponse[DocumentData]`.
- container: `DocumentService(FileDocumentStore(Path(settings.documents_dir)))`를 앱당 하나 만들어 `provide_document_service`에 연결. 시작 시 폴더를 검사하지 않는다(4절 1단계가 요청 시 502로 알린다).

## 7. 설정

| 변수 | 기본값 | 쓰임 |
| --- | --- | --- |
| `API_DOCUMENTS_DIR` | `solar_handoff/documents` | 원문 Markdown 폴더. 파일은 `<API_DOCUMENTS_DIR>/<source_ref_id>_*.md`(예: `001_이상해씨.md`). 상대 경로는 서버 작업 디렉터리 기준 |

## 8. 테스트 시나리오 (`api/tests/documents/`)

임시 폴더(`tempfile.TemporaryDirectory`)에 문서를 만들어 쓴다. 성공 1건은 저장소의 `solar_handoff/documents/001_이상해씨.md`도 확인한다(읽기만).

| # | 종류 | 시나리오 | 기대 |
| --- | --- | --- | --- |
| D1 | 도메인 | `001`, `151` | 성공 |
| D2 | 도메인 | `""`, `1`, `01`, `0001`, `00a`, `..`, `001.md`, `001_이상해씨`, ` 001`, `001\n`, `١٢٣`(아랍 숫자) | `InvalidSourceRefIdError` |
| D3 | 구현체 | 임시 폴더 `001_x.md`(CRLF·끝 공백 포함) | 바이트 그대로 디코딩한 문자열 |
| D4 | 구현체 | 없는 `002`, 접두어만 비슷한 `0010_x.md`만 있는 `001` | `DocumentNotFoundError` |
| D5 | 구현체 | `base_dir` 없음 / `003_z.md`가 폴더 / 잘못된 UTF-8 바이트 / `004_a.md`·`004_b.md` 둘 다 있음 | 각각 `DocumentSourceError`, `message`에 경로 없음 |
| D6 | 서비스 | 형식 오류 id, fake 저장소 | `InvalidSourceRefIdError`, 저장소 호출 0회 |
| D7 | API 성공 | `API_DOCUMENTS_DIR=solar_handoff/documents` 설정, `GET /api/v1/documents/001` | 200, `data.source_ref_id` 일치, `data.markdown`이 파일 내용과 같음 |
| D8 | API 400 | `/api/v1/documents/1`, `/api/v1/documents/001.md`, `/api/v1/documents/%2E%2E`(디코딩 후 `..`) | 400 `VALIDATION_ERROR` |
| D9 | API 404 | `/api/v1/documents/999` | 404 `DOCUMENT_NOT_FOUND` |
| D10 | API 404 | `/api/v1/documents/a/b`, `/api/v1/documents/a%2Fb` | 404 `NOT_FOUND` (라우트 미매칭) |
| D11 | API 502 | 저장소가 `DocumentSourceError` (fake 또는 없는 폴더) | 502 `DOCUMENT_SOURCE_FAILED` |
| D12 | API 500 | fake 저장소가 `RuntimeError("/abs/secret")` (`raise_app_exceptions=False`) | 500 `INTERNAL_ERROR`, 본문에 `/abs/secret` 없음 |

## 9. 변경 제안 (설계안 밖 파일)

| 파일 | 제안 |
| --- | --- |
| `.env.example`, `docs/references/environment.md`, `README.md` | `API_DOCUMENTS_DIR=solar_handoff/documents` (R12) |

## 10. 질문

| 질문 | 임시 기본값 |
| --- | --- |
| 대소문자만 다른 id (`Bulbasaur_red_blue`) | API는 변환하지 않는다. macOS 기본 파일 시스템(대소문자 무시)에서는 200, Linux에서는 404가 될 수 있다. 파일명 규칙(소문자)은 RAG 쪽이 정하고 API는 그대로 둔다 |
| `API_DOCUMENTS_DIR`가 없을 때 시작 실패로 할지 | 시작은 성공, 요청 시 502 `DOCUMENT_SOURCE_FAILED` (mock 모드 서버가 문서 없이도 떠야 함) |
| 응답 `Content-Type`을 `text/markdown`으로 줄지 | 아니오. 공통 JSON 형식의 `data.markdown` 문자열 |
| symlink를 따라갈지 | 따라간다(기본 동작). 문서 폴더는 저장소 안 커밋된 파일이므로 별도 제한 없음 |
