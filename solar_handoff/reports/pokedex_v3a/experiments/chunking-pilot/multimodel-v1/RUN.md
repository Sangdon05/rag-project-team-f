# 3문서 멀티모델 검색 파일럿

**상태: 사용자 승인 후 KURE·OpenAI 실제 적재·검색 및 기존 Gemma와의 독립 채점 완료.** 결과는 [score.md](eval/comparison-v1/score.md)를 따른다. 이 기록은 추가 실행 승인이나 pending 문서의 운영 승인이 아니다.

**주의:** `results/kure/`와 `results/openai/`는 보존 중인 모의 테스트 파일이며 실제 결과가 아니다. [MOCK_RESULTS_NOTICE.md](MOCK_RESULTS_NOTICE.md)를 확인한다. 실제 결과는 별도의 `results/real-v1/<model>/`에만 생성하며, 기존 모의 파일을 삭제하거나 변경하지 않는다.

두 디렉터리의 모의 산출물 6개는 로컬에만 보존하며 Git에 커밋하거나 공유하지 않는다. 사용자 지정 생성물 예외는 재현에 필요한 청크와 실제 파일럿 결과에 한정된다.

## 범위와 보존

A 29개, B 48개, 질문 15개는 상위 실험의 SHA-256 고정 입력을 그대로 사용한다. `pilot.py`는 문서·근거를 재생성 대조하고 기존 Gemma raw 파일의 해시도 확인한다. 정답 파일은 읽지 않는다. Gemma 스키마·기존 파일은 쓰지 않는다. 새 스키마는 `chunking_pilot_kure_v1`, `chunking_pilot_openai_v1`로 고정되어 있으며 이미 있으면 빈 스키마여도 중단한다. 새 역할 생성, DROP, 덮어쓰기, 자동 재시도는 없다.

각 실행은 단일 소유자 트랜잭션에서 스키마를 만들고 PUBLIC 권한을 회수한 뒤 해당 스키마의 `chunks` 테이블에만 77개 레코드를 삽입한다. ANN 인덱스 없이 exact cosine, 각 질문당 모델 임베딩 1회, A/B 각각 k=5, C 정렬 tie-break로 검색한다. 30개 행의 원본 결과와 벡터 manifest는 `results/real-v1/<model>/`에 독점 생성한다. 검색에는 정답이 들어가지 않으며 채점하지 않는다. 벡터 manifest SHA-256은 JSON canonical bytes(마지막 개행 제외)의 해시다. 입력, 청크, 메타데이터 및 float32 벡터를 트랜잭션 안과 커밋 후 읽어 확인한다.

기존 Gemma 초기화 attestation SHA `300145897c76f7673c9e943c122aa3f16bfcf3c6a1575fa135db706ea2acc746`을 독립 검증한다. 실행 시 DB 이름과 고정 container ID로 fingerprint를 재계산하고 기존 `pilot_db.connect_verified(container_id)`로 로컬 Docker/DB identity를 확인한다. 기존 Gemma 청크 77개 및 모델·벡터 수를 읽기 전용 트랜잭션에서 대조한다. 이 검사는 baseline 벡터 전체 해시를 재검증하지 않는다. DB 소유자/슈퍼유저와 악의적인 동시 로컬 관리자는 샌드박스 대상이 아니다. 실행 중 관리자 변경을 막을 운영자 통제가 필요하다. 모델별 스키마는 실험 폴더 밖 DB 객체이므로 나중의 삭제도 별도 승인이 필요하다.

읽기 검사는 생성 전, 생성 트랜잭션 및 커밋 후 반복한다. 로그인/현재 사용자는 승인된 동일 슈퍼유저여야 하고, enabled event trigger와 생성자에 적용되는 schema/table custom default ACL은 하나라도 거절한다 (owner-only custom default도 보수적으로 거절). 다른 비관리자의 owner 역할 멤버십도 거절한다. 생성 후 schema·table·index 소유자, relation/column 목록, routine 및 추가 type, schema/table/column의 ACL을 검사한다. NULL ACL은 PostgreSQL 내장 기본 ACL로 확장하고 PUBLIC을 포함해 owner 이외의 명시 권한은 모두 거절한다. `public` 확장 자체의 정상 읽기 권한은 회수하지 않는다. PostgreSQL 슈퍼유저의 내재적 우회 권한은 제거되지 않는다. 벡터 텍스트는 `-0` 부호를 유지해 float32 비트 SHA를 각 manifest 레코드와 트랜잭션 내부 및 커밋 후 비교한다.

**추가 실행 전 독립 DB 읽기 검토가 필요하다.** 이 구현은 모든 PostgreSQL 네임스페이스 객체 종류(예: operator, collation)나 constraint/index 정의 전체를 열거하지 않는다. 부모는 승인된 DB에 읽기 전용으로 접속해 enabled event trigger가 0개인지, 동일 승인 superuser/session인지, 생성자 global 및 대상 schema의 default ACL이 없는지, owner 멤버십 및 PUBLIC 포함 유효 schema/table/column 권한이 owner 외 없는지 확인해야 한다. 대상 schema가 이미 있으면 실행하지 않는다. 생성 이후에는 `run.py`의 CREATE TABLE 정의와 모든 네임스페이스 객체·constraint/index 정의·ACL을 직접 대조한다. 어느 하나라도 확인 불가거나 차이가 있으면 결과를 채택하지 않고 보존·중단한다. 관리자 동시 변경은 통제되어야 하며 이 읽기 검토는 race를 방지하지 않는다.

## 오프라인 확인

저장소 루트에서, 프로젝트 Python 환경과 허용 scratch의 `TMPDIR`을 사용한다. DB, Docker, 모델, 네트워크, `.env`에 접근하지 않는다.

```sh
export PYTHONDONTWRITEBYTECODE=1 TMP="$TMPDIR" TEMP="$TMPDIR"
python pokedex_v3a/experiments/chunking-pilot/multimodel-v1/run.py --preflight
python -m unittest discover -s pokedex_v3a/experiments/chunking-pilot/multimodel-v1 -p 'test_*.py' -v
```

테스트는 모의 DB·HTTP 응답으로 트랜잭션 실패, 이미 존재하는 스키마, 파일 충돌, 입력 변경, DB fingerprint, 모델·차원·범위, 검색 건수와 근거 ID를 확인한다. 실제 PostgreSQL/pgvector의 SQL 호환성이나 실제 모델의 입력 한도·검색 품질을 증명하지 않는다.

실제 raw 결과에는 `run_type: real`과 `provider: ollama` 또는 `openai`를 기록한다. 오프라인 테스트의 가짜 provider/DB 결과는 임시 디렉터리 전용이며 실제 결과가 아니다.

## 별도 승인 후 실행 명령

부모가 코드·실행 범위·비용을 검토하고 명시적으로 승인한 뒤 각각 별도 실행한다. 런처는 환경 변수 `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `PILOT_EXPECTED_DB_NAME`을 설정해야 하며 뒤 두 값은 같아야 한다. `pilot_db`가 `PG*`, 원격 Docker context 및 허용 외 대상 연결을 거절한다. KURE는 별도 확인한 설치 모델의 전체 64자리 digest를 `PILOT_KURE_DIGEST`에, OpenAI는 `OPENAI_API_KEY`를 환경에 설정한다. 코드 자체는 `.env`를 읽지 않으며 DSN이나 키를 출력하지 않는다. 필요한 라이브러리 `psycopg`와 실행 중인 기존 승인 DB, KURE Ollama 또는 OpenAI 접근은 별도 전제다.

```sh
python pokedex_v3a/experiments/chunking-pilot/multimodel-v1/run.py --execute --model kure
python pokedex_v3a/experiments/chunking-pilot/multimodel-v1/run.py --execute --model openai
```

한 모델 실행은 먼저 문자 수로 가장 긴 청크 또는 질문 하나를 probe해 기본 차원 KURE 1024/OpenAI 1536을 실측 검증하고, 77개 청크 원문을 한 요청으로, 15개 질문은 각각 한 번씩 그대로 보낸다. 문자 수는 토큰 수가 아니다. KURE `/api/embed`는 `truncate:false`, 전후 digest 확인을 사용한다. OpenAI는 원문을 외부 공식 HTTPS embeddings API에 native dimension, 차원 override 없이 전송한다. 프록시·리다이렉트·클라이언트 분할·접두사·자동 재시도는 없다. 모든 벡터의 개수·차원·유한값·nonzero 및 float32를 검사한다. API 사용량이 기록되지 않아 비용은 알 수 없고, 서버 내부의 숨은 변환·잘림은 검증할 수 없다. 모델 revision은 불변으로 보장되지 않는다. 전체 입력이 서비스 한도를 초과하면 분할하지 않고 실패한다. 로컬 Ollama 모델 제거 경쟁 시 서버 측 자동 다운로드 방지는 보장하지 않는다.

`results/real-v1/<model>/`은 실행 시 새로 독점 생성하며, 빈 디렉터리를 포함해 이미 존재하면 중단한다. 그 안의 `pending`은 외부 작업 전에 독점 생성되고 성공 후에도 남는다. 성공 시 같은 디렉터리에 `vector_manifest_v1.json`과 `raw_search_v1.json`을 독점 생성한다. DB 커밋과 결과 파일은 원자적으로 묶이지 않는다. 실패, 커밋 응답 유실 또는 부분 결과가 있으면 자동 재시도하거나 삭제하지 말고 DB 스키마·파일을 직접 확인하고 복구 방법을 별도 결정한다. API 요청은 과금될 수 있다. 각 모델 결과는 독립 평가자에게 넘긴다.
