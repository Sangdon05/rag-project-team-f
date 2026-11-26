# 3문서 격리 저장 계약 — 실행 기록과 제한

**상태: 3문서 테스트 초기화·적재·검색 완료.** `logs/schema_init_attestation.json`, `logs/loader_execution.json`, `logs/vector_manifest_v1.json`과 `results/`가 당시 기록이다. `chunking_pilot_3doc_v1`에 A 29·B 48 청크와 768차원 벡터 77개, 모델 1개를 적재해 검증했다. `scripts/vector_store.py`의 `writer_transaction`은 별도 차단된 경로이며 실제 로더가 없다는 뜻이 아니다. 운영 인덱스나 151개 문서의 승인이 아니다. 이 문서 갱신에서는 DB에 재접속하지 않았다.

## 구현과 검증

- 명시된 `chunks/A-v2.jsonl`, `chunks/B-v2.jsonl`, `chunks/manifest-v2.json`은 `prepare_chunks.render()`의 전체 오프라인 재생성 결과와 바이트 비교한다. 대상 118·129·151, A/B, pending, `index_eligible=false`, Red·Blue, 설정·본문 해시·근거 경로를 별도로 검사한다. 재생성기는 각 원문과 근거·입력 해시를 검증한다. 재생성 일치는 독립적인 사실 검수나 사람 승인, 생성기 자체의 진정성을 보장하지 않는다.
- 파일 경로는 실험 폴더 안의 일반 파일만 허용하고 링크와 `pilot_expected` 경로를 거부한다. A/B와 매니페스트는 명시적으로 지정하고 모두 다르게 지정한다. 결과 청크는 메모리에 반환하며 파일이나 DB에 쓰지 않는다. 테스트의 재생성 주입은 단위 테스트용 모의 경로이므로 실제 검증에는 사용하지 않는다.
- `validate_vectors()` 자체는 전달된 응답만 검사한다. 별도 실제 모델 probe·로더 기록은 `logs/longest_input_probe.json`, `logs/loader_execution.json`에 있다. 모델 이름·digest·차원 등 기록을 참고하되 응답만으로 서버의 숨은 잘림 부재를 증명하지는 않는다.
- 루트 프로젝트의 `uv` 환경에서 `PYTHONDONTWRITEBYTECODE=1 uv run python -m unittest discover -s pokedex_v3a/experiments/chunking-pilot/tests -p test_vector_store.py -v`로 실행한다. 현재 이 코드 자체는 표준 라이브러리만 사용하나 원문 재생성기에는 루트/이식 폴더의 기존 코드와 데이터가 필요하다. 실제 DB 코드에는 루트 uv 환경의 psycopg 및 pgvector 또는 동일 패키지를 별도 설치한 환경이 필요하다. `pokedex_v3a` 자체에 이 의존성이 정의되어 있다는 뜻이 아니다.

## 대상과 연결

- 사용자가 승인한 새 컨테이너는 `pokedex-v3a-pg`, 그 안의 DB는 `post`다. **두 번째 DB를 만들지 않는다.** 코드는 DB 이름을 하드코딩하지 않는다. 오케스트레이터가 `PILOT_EXPECTED_DB_NAME`과 `POSTGRES_DB`를 명시적으로 전달하고, 두 값과 `current_database()`가 모두 일치해야 한다. `POSTGRES_USER`, `POSTGRES_PASSWORD`도 호출 환경으로만 전달하며 코드는 `.env`를 읽거나 값을 출력하지 않는다. `PG*` libpq 환경 우회는 거부한다.
- `connect_verified(container_id, *, host=HOST, port=PORT)`는 정확한 64자리 container ID, 로컬 Docker context, 컨테이너 이름·이미지·상태·네트워크·named volume·읽기 전용 초기화 마운트 및 `127.0.0.1:5432` 바인딩을 확인한다. Docker 출력은 지정된 format 필드만 읽고 환경은 조회하지 않는다. 연결 후 DB명·현재/세션 사용자·슈퍼유저 여부·서버 주소와 Docker IP를 대조하고 Docker 대상을 다시 확인한다. 다른 호스트·포트는 허용하지 않는다.
- 주소 비교는 DB 식별 쿼리에서 `pg_catalog.host(inet_server_addr())`의 접두사 없는 서버 주소를 Docker 네트워크 IP와 정확히 비교한다. 부모가 전달한 기존 호스트→컨테이너 읽기 전용 검증 결과에서는 Docker IP와 DB `host()`가 일치했다. 이번 작업에서 직접 접속해 재검증하지는 않았다. 오프라인 CIDR 테스트는 모의 결과다.
- 검사는 호스트 관리자나 Docker 소켓을 적대적으로 제어하는 상대에 대한 암호학적 증명이 아니며, 검사와 사용 사이 변경(TOCTOU)을 없애지 않는다. 이후 권한 변경이나 다른 DB 접근도 별도 통제해야 한다.

## 초기화 범위와 조건

- 초기화된 `chunking_pilot_3doc_v1` 스키마와 `chunking_pilot_writer_v1` 역할을 보존한다. `--init`은 둘이 모두 없을 때만 진행한다. 역할은 NOLOGIN·NOSUPERUSER·NOCREATEDB·NOCREATEROLE·NOINHERIT·NOREPLICATION·NOBYPASSRLS다. **역할은 새 컨테이너의 클러스터 전역 객체**이며 스키마와 별도의 정리 대상이다. 자동 삭제는 없고 각각 별도 사용자 승인이 필요하다.
- role 생성, 스키마와 세 테이블 생성은 한 최상위 트랜잭션에서 수행한다. 이미 활성 트랜잭션·savepoint·pipeline이 있거나 상태를 확인할 수 없으면 시작하지 않는다. 권한 회수, 다른 스키마에 대한 GRANT, 확장 생성 및 기존 객체 변경은 하지 않는다.
- 새 role의 속성과 역할 멤버십, DB `CREATE`, 다른 비시스템 영구 스키마의 `CREATE`, 테이블 및 시퀀스 쓰기, 열 단위 `INSERT`·`UPDATE`·`REFERENCES`, 실행 가능한 비시스템 `SECURITY DEFINER` routine을 실효 권한 API로 검사한다. PUBLIC·역할 소유·상속 등으로 위험 권한이 있거나 검사에 실패하면 중단한다. 그 후 `SET LOCAL ROLE`과 `current_user`/`session_user`를 확인하고 고정 테이블만 생성한다.
- 설치된 **기존 `public.vector`** 타입의 스키마와 타입 USAGE를 확인해 사용한다. 확장을 새로 만들거나 전역 권한을 수정하지 않는다. 세 테이블은 `models`, `chunks`, `vectors`이며 벡터 차원은 호출자가 명시한다. A/B의 `(variant, chunk_id)`는 독립적이다. `chunks`에는 A/B, 118·129·151과 재생성된 정확한 `(variant, chunk_id, pokemon_id)` 목록의 CHECK, `vectors`에는 A/B CHECK와 chunks/models 외래키를 둔다. 모델 행과 벡터는 초기화에서 넣지 않는다.
- `--model-id`, `--model-digest`, `--dimension`, `--confirm-live-model-probe`는 **실행 전 운영자의 모델 확인 진술**이다. 프로그램은 실제 모델이나 차원을 조회하지 않으므로 이 플래그가 probe의 증거는 아니다. 오케스트레이터는 별도로 실측·검증하고 기록해야 한다.
- DB 작업 오류 시 트랜잭션 롤백을 시도하지만 연결 끊김이나 커밋 응답 유실 시 결과는 **불명**이다. 재시도 전에 정확한 대상 DB의 스키마·역할·테이블을 실제로 읽어 상태를 확인하고 기존 객체가 있으면 덮어쓰지 않는다.

## 보안 한계와 후속 구현

이 역할은 **프로덕션 보안 경계가 아니다**. TEMP 권한은 차단하지 않으며 슈퍼유저 세션은 역할 전환을 해제할 수 있다. routine·권한 검사는 특정 시점의 검사이고 동시 권한 변경, 악의적 관리자와 모든 우회 경로에 대한 보장은 아니다. 범용 슈퍼유저 연결을 넘겨주는 writer 경로는 금지한다. 실제 로더의 제한 역할·가드 계약은 `loader.md`를 따르며 새로운 writer는 별도 코드·독립 검토를 거쳐야 한다. 기존 `run_search.py`가 이 검증된 연결을 사용하도록 통합됐다고 가정하지 않는다.

실제 로더 및 별도 검색 경로를 사용한 결과와 검증 기록은 `loader.md`, `results/`를 따른다. 로더는 트랜잭션 안에 외부 고정 SHA의 스키마 가드를 호출하고 최초 벡터 해시 매니페스트를 독점 생성한다. 기존 데이터는 독립 고정 매니페스트 SHA로 대조한다. 별도 검색 연결이 로더 연결과 동일하다고 가정하지 않는다. 이후 재실행은 새 승인과 대상 검증이 필요하며 출력·오류에 비밀·연결 문자열·`.env` 내용을 남기지 않는다.

## 오프라인 검사

저장소 루트의 기존 가상환경에서 `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m unittest discover -s pokedex_v3a/experiments/chunking-pilot/tests -v`를 실행한다. 이 오프라인 테스트는 모의 DB·Docker와 scratch fixture를 사용하며 PostgreSQL 서버 검증 자체는 아니다. 별도의 실제 실행 기록이 이 폴더에 있지만 모든 실패·동시성·커밋 불확실성 시나리오를 실증한 것은 아니다.
