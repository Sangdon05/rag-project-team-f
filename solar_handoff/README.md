# Solar 데이터·검색 팀 전달본

영문 Red·Blue 도감의 문서·청크와 **Solar 임베딩** 기반 검색을 팀에 전달한다. 루트의 `pyproject.toml`, `uv.lock`, `docker-compose.yml`을 재사용하며 별도 프로젝트 설정은 만들지 않는다. 과거 보고서의 다른 임베딩 모델은 이력이다. 답변 생성 및 선택적 재작성·재순위화는 별도 모델을 사용한다.

## 포함 범위와 검증 상태

- `data/processed/`, `data/source_manifest.json`, `data/document_register.json`: 정제 데이터, 출처 및 문서 등록부.
- `documents/`, `document_evidence/`: 문서와 근거 각 151개. `chunks/draft-a-v1/`: 1,504개 청크와 당시 매니페스트. 초안은 사람의 사실 검토나 운영 승인이 아니다.
- [문서·청크 생성 및 검증](scripts/README.md): 오프라인 생성 절차, 새 출력 경로 조건, 원본 보존 및 한계.
- `src/`: Solar 임베딩 적재·검색, 번들 내보내기·복원 및 질문 CLI. `db/schema.sql`: 팀 DB 스키마. `config/retrieval.json`: 검색 설정.
- `reports/`: 원본 경로를 유지한 과거 보고서 26개. 당시 원본 실험 raw 및 과거 실행 도구는 포함하지 않는다. 최종 평가셋과 잠금 파일은 전달 범위가 아니다.

### 확인된 실 실행 범위

- 기존 Solar 벡터 1,504개를 별도로 격리한 임시 PostgreSQL에 실제 복원했다. 독립된 새 연결에서 전체 메타데이터와 벡터 float32 바이트를 대조했다. 사용자가 승인한 동일 입력의 증분 실행은 새 임베딩 0개였고 1,504개 readback을 확인했다.
- 2026-11-26 사용자가 명시적으로 승인한 질문 1개에 대해 Solar 질문 임베딩 + C 검색 + 재작성 + GPT 답변이 실제 성공했다. 인용 ID `pokemon:133#profile`과 이브이가 노말 타입이라는 내용은 전달 문서 `documents/133_이브이.md`의 6행·10행에서 확인했다.
- 위 범위 밖의 다른 조합이나 API는 실 실행 성공을 주장하지 않는다. 인용 ID 유효성은 각 주장의 사실성 검증과 다르다. 자료의 출처·재배포 권리와 승인 상태는 사용 전에 별도 확인한다.

## 환경과 안전 경계

저장소 루트에서 기존 환경을 준비한다. 패키지·Python 준비는 [루트 안내](../README.md#개발-환경)를 참조한다. 루트 Compose의 5432 포트는 이미 사용 중일 수 있으므로 기존 서비스·데이터를 먼저 확인한다. 기존 DB나 볼륨을 중지·삭제·초기화하지 말고, 충돌 시 팀과 별도 대상 및 접근 방법을 합의한다. 실제 작업 전 DB 대상·스키마·권한과 백업을 확인하고 별도 승인을 받는다. `solar_handoff` 스키마는 지정된 팀 DB에만 생성한다.

환경 변수는 각자의 안전한 환경에 설정한다. 아래는 **이름만**이며 값·API 키·접속 문자열을 문서, Git, 번들 또는 채팅에 넣지 않는다. 코드는 `.env`를 자동으로 읽지 않는다. 필요한 변수를 각자의 셸 환경에 안전하게 전달하거나, 저장소 루트에서 `uv run --env-file .env` 뒤에 실행할 Python 명령을 명시한다. 예를 들어 `uv run --env-file .env python -B -m solar_handoff.src.cli --help`를 사용할 수 있다. 아래의 `python` 예시는 필요한 환경 변수가 이미 전달됐다는 전제다.

| 이름 | 역할 |
| --- | --- |
| `DATABASE_URL` | 기존 환경에서 사용하는 PostgreSQL 연결. Solar 실행에서도 사용하며 작업 전 대상과 권한을 확인 |
| `UPSTAGE_API_KEY` | Solar 임베딩 API 인증 |
| `UPSTAGE_EMBEDDING_MODEL` | 문서 임베딩 모델 ID |
| `UPSTAGE_QUERY_MODEL` | 질문 임베딩 모델 ID; 문서 모델 ID와 달라야 하며 인덱스에 기록된 모델과 일치해야 함 |
| `OPENAI_CHAT_MODEL`, `OPENAI_API_KEY` | GPT 답변, 재작성 또는 C 방식 재순위화에 필요. 모델 ID는 환경에서 읽으며 `gpt-` 접두사만 허용하고 그 외 ID는 거부한다. 응답의 실제 모델 ID도 `gpt-`여야 하나 설정 ID와의 정확한 일치는 요구하지 않는다 (alias가 날짜가 붙은 revision으로 응답할 수 있음) |

Solar 임베딩은 Upstage로 질문 또는 청크 본문을 전송한다. GPT 사용 시 질문과 검색 문맥이 OpenAI로 전송될 수 있다. 민감정보·전송 범위·라이선스·비용을 사전에 검토하고 각 실행을 승인한다. 모델별 실제 비용은 미상이며 새 유료 호출마다 사용자에게 별도 승인을 받아야 한다. 코드의 민감정보 검사로 알려지지 않은 민감정보나 모든 변형을 자동 탐지한다고 보장할 수 없다. 실패한 요청도 과금됐을 수 있으므로 자동 재시도하지 말고 먼저 확인한다. 이번 README 수정에서는 실제 DB나 API에 접근하지 않았다.

## 기존 Solar 벡터를 팀 DB로 전달

1. **`legacy-export`는 현재 모든 플랫폼에서 비활성화되어 있다.** 비공개 파일 생성과 저장소 밖 경로의 안전성을 검증하기 전에는 원본에 접근하거나 출력 파일을 만들지 않고 실패한다. Windows의 소유자 전용 DACL과 경로 교체 방어, POSIX의 0600 생성·검증 및 경로 보호가 아직 구현·검증되지 않았다. Windows에서 `chmod`는 DACL 보호를 보장하지 않는다. 자동 재시도하거나 다른 경로로 우회하지 말고 보안 구현과 독립 검증을 기다린다.
2. 기존 검증된 번들에는 청크 본문·메타데이터·벡터 및 모델 설정이 포함된다. 저장소 밖의 비공개 위치에 보관 중이며 사용자가 비공개 공유를 선택했지만 아직 전달하지 않았다. 구체적인 전달 방법과 라이선스·재배포 권리는 별도 확인이 필요하다. 공유 전에 데이터와 권리, 비밀 포함 여부, 수신자 권한 및 전송·보관 정책과 ACL을 확인한다. Git이나 공개 장소에 포함하지 않는다. 이전 실행에서 남은 부분 파일은 완전한 번들로 간주하거나 자동 재시도·덮어쓰지 말고, 접근을 제한한 상태에서 사람이 안전하게 조사·처리한다.
3. 운영 DB를 복원 대상으로 사용하면 기존 서비스·데이터에 위험이 있다. 승인된 **팀 DB**의 실제 호스트·포트·DB명·권한과 기존 스키마를 독립 확인한다. 소스 DB에 `init`하지 않는다. `public.vector` 및 대상 스키마·세 테이블을 확인하고 아래 분기에 따른다. 복원은 세 테이블이 모두 빈 대상만 허용하며 자체 readback도 수행한다. 임시 DB의 tmpfs 데이터는 환경 종료 등에 따라 삭제될 수 있으므로 공유용 영구 저장소로 취급하지 않는다.

### 자동 초기화와 기존 DB 분기

루트 Compose는 **빈 PGDATA의 최초 기동에만** 기본 DB(`POSTGRES_DB`, 기본값 `pokedex`)에서 `init.sql`로 `public.vector` 확장을 먼저 만든다. 이어서 동일한 기존 `db/schema.sql`을 `psql`의 `\i`로 단일 트랜잭션 안에 포함해 `solar_handoff`와 빈 `chunks`, `vectors`, `index_info`를 생성한다. SQL 파일은 읽기 전용으로 연결되며 데이터·벡터는 자동으로 로드되지 않는다. `DATABASE_URL`이 이 기본 DB와 같은 대상인지 별도로 확인한다.

스키마 생성 중 SQL 오류가 나면 스키마 생성 트랜잭션은 롤백된다. 그 앞에 별도로 생성된 vector 확장은 남을 수 있다. 실패했더라도 PGDATA는 이미 초기화됐을 수 있어 `docker restart`로 초기화가 자동 재시도되지 않으며, `pg_isready`가 `healthy`여도 스키마 준비를 증명하지 않는다. 기존 볼륨에는 새 초기화 파일도 자동 적용되지 않는다. 기존 DB나 볼륨을 절대 삭제하지 말고 중단해 대상 상태를 조사한다. 연결 장애나 커밋 결과 불명 등 다른 실패에서는 롤백을 가정하지 않는다.

작업 전 해당 사용자의 기존 포트·서비스·DB·스키마를 읽기 전용으로 확인하고, DB 접근 자체도 승인받는다. 예를 들어 승인된 연결에서 `SELECT current_database(), inet_server_addr(), inet_server_port(), to_regnamespace('solar_handoff'), to_regclass('solar_handoff.chunks'), to_regclass('solar_handoff.vectors'), to_regclass('solar_handoff.index_info'), (SELECT extnamespace::regnamespace::text FROM pg_extension WHERE extname = 'vector');`를 실행해 실제 대상과 객체를 확인한다. 스키마 1개와 테이블 3개 중 존재하는 객체 수가 0인지 4인지 확인하고, 1~3개이거나 판독 불가라면 중단해 조사한다. 연결 주소와 포트를 독립 확인하고 결과를 승인된 대상과 대조한다. 존재 확인만으로 테이블 구조나 내용의 호환성을 보장하지 않는다.

- **스키마가 이미 존재:** `init`을 실행하지 않는다. `public.vector`, 세 테이블 구조·권한 및 데이터 상태를 확인한다. 부분 생성·구조 불일치·판독 불가라면 중단하고 조사한다. 세 테이블 중 하나라도 행이 있으면 `restore`는 빈 대상 가드로 거부한다. 기존 데이터 삭제나 덮어쓰기로 우회하지 않는다.
- **스키마가 없음:** 대상·권한과 백업을 확인하고 사용자 승인을 받은 후에만 `public.vector`를 준비하고 아래 `init`을 한 번 실행한다. 이는 기존 볼륨에 대한 수동 작업이며 소스 DB에는 적용하지 않는다.
- **복원:** 번들을 별도 안전 공유로 받은 뒤 출처·권한과 내용을 확인하고, 승인된 대상의 세 테이블이 모두 비었음을 확인한 다음 `restore`와 `verify`를 수행한다. `restore`도 트랜잭션에서 빈 테이블을 확인하며 커밋 후 새 연결로 대조한다. 이미 복원된 경우 `init`이나 `restore`를 반복하지 말고 승인된 대상과 번들을 확인한 뒤 `verify`만 사용한다.

`init`은 커밋 후 새 연결로 같은 대상과 스키마·테이블 존재를 확인한다. `init`·`restore`의 `commit_unknown` 또는 `committed_readback_unknown`이면 자동 재시도하지 말고 대상의 실제 상태를 사람이 확인한다. 이는 임베딩 실행이 아니다.

팀 Solar 연결에도 기존 `DATABASE_URL`을 사용한다. Solar 직접 연결 코드는 SQLAlchemy용 드라이버 접두부만 psycopg용으로 변환하고 일반 PostgreSQL URL도 지원한다. 사용자의 기존 설정을 사용하되 실제 대상이 의도한 DB인지 독립 확인하고, 원본 DB는 보존한다. 저장소 루트에서 도움말과 세부 옵션을 먼저 확인한다. 아래 따옴표 안 경로와 컨테이너 이름은 각 팀이 승인한 실제 대상으로 바꾼다. `--confirm-target`에는 연결하려는 대상의 정확한 DB 이름을 입력한다. `init`, `restore`, `verify`는 지정한 `DATABASE_URL`을 사용한다. 아래 예시는 실행 전 대상·권한과 사용자 승인을 확인한다.

`init`·`restore`는 실제 연결이 loopback이 아니면 거부하며, 원격 대상은 별도 승인과 `--allow-remote-target`이 필요하다. `verify`에는 `--confirm-target` 가드가 없으므로 실행 전 대상 연결을 독립 확인한다. 두 쓰기 명령은 원본 보호 스키마가 있는 DB도 거부한다.

```sh
python -B -m solar_handoff.src.export --help
python -B -m solar_handoff.src.export legacy-export --help
python -B -m solar_handoff.src.export restore --help
python -B -m solar_handoff.src.export verify --help

# legacy-export는 보안 구현·검증 전 비활성화되어 실행해도 실패한다.
# 승인된 팀 DB에 스키마가 없을 때만 실행 (이미 있으면 생략)
python -B -m solar_handoff.src.export init --confirm-target "승인된_대상_DB_이름"
# 세 테이블이 모두 비었고 번들 전달과 복원을 승인한 경우에만 실행
python -B -m solar_handoff.src.export restore --bundle "저장소_밖_비공개_폴더/새_번들.json" --confirm-target "승인된_대상_DB_이름"
python -B -m solar_handoff.src.export verify --bundle "저장소_밖_비공개_폴더/새_번들.json"
```

## 질문 실행

대화 API용 진입점은 [`src/conversation.py`](src/conversation.py)의 `create_service()`입니다. 전체 대화 이력을 답변 생성에 전달합니다. 기본 B 검색의 상위5개 청크를 보존하고 같은 문서의 형제 청크를 최대50개·직렬화된 UTF-8 96,000바이트까지 통째로 추가합니다. CLI A/B/C의 후보 생성·상위5개 비교는 변경하지 않는 별도 대화 컨텍스트 확장입니다. 실제 전달 근거에서 인용한 청크만 번호 출처로 반환하며, 검증한 질의 임베딩 모델과 인덱스의 문서 모델을 답변 메타데이터로 제공합니다. `SOLAR_RETRIEVAL_METHOD`로 A/B/C를 선택하고 `SOLAR_REWRITE`는 기본 `false`입니다. HTTP 원문 조회는 기존 documents 슬라이스를 사용합니다. 요청·응답과 오류 경계는 [API–RAG 연결 가이드](../docs/references/api-rag-integration.md)를 따릅니다.

저장소 루트에서 CLI 옵션을 확인한다.

```sh
python -B -m solar_handoff.src.cli --help
```

CLI는 `--question` 또는 표준입력으로 한 질문을 받는다. `--method A`는 Solar 벡터 검색, `B`는 벡터와 BM25의 RRF 결합, 기본 `C`는 B의 상위 5개를 GPT로 재순위화한다. `--rewrite`는 GPT 질문 재작성에 사용하며 답변은 GPT 전용이다 (`--answer gpt`). 실제 질문 실행에는 별도로 승인된 DB 접근과 비용을 확인하는 `--allow-cost`가 필요하다. `--qid`는 선택적 식별자다. CLI가 JSON 트레이스를 출력하므로 질문·청크·응답 등 포함 내용을 확인하고 외부 공유를 제한한다. 인용 ID 검사는 근거의 사실 지원 여부에 대한 사람 검토나 평가를 대신하지 않는다.

승인 후 질문 예시 (`--allow-cost`는 실제 DB 접근과 API 호출을 허용함):

```sh
python -B -m solar_handoff.src.cli --question "피카츄의 타입은 무엇인가요?" --method B --answer gpt --allow-cost
```

## 문서·청크 재생성 및 증분 적재

[생성 안내](scripts/README.md)의 `--check`와 새 출력 경로 절차를 따른다. 기존 문서·근거·청크를 덮어쓰지 않는다. 생성 자료는 `pending` 초안이며 새 적재 전에 사용자가 정확한 입력과 실제 사용·승인 범위를 확인하고 승인 여부를 결정한다. 이 과정에서 과거 승인 스냅샷 검증 시스템을 재구축하지 않는다. 코드의 `src/ingest.py`는 제공된 청크 중 본문이 새롭거나 바뀐 항목만 Solar로 임베딩하고, 빠진 항목은 삭제하지 않는 증분 적재 경로다. 기본 dry-run도 팀 DB에 연결하므로 사전 승인이 필요하다. 실제 쓰기에는 정확한 입력 승인 확인 `--confirm-input-approved`, 대상 DB명 확인 `--confirm-target`, 실행별 비용 승인 `--approve-cost`가 모두 필요하다. 플래그는 실제 사용자의 승인 결정을 대체하지 않는다. 모델별 비용은 미상이며, 새 유료 호출은 실행마다 별도 승인을 받는다. 모델 설정이 기존 인덱스와 다르면 별도 인덱스가 필요하다. 생성·적재 후 출처와 결과를 재검토하고 별도 평가한다.

```sh
python -B -m solar_handoff.src.ingest --help
# DB 접근 승인 후 예상 API 호출 건수 확인 (임베딩 호출·DB 쓰기 없음)
python -B -m solar_handoff.src.ingest --chunks "승인된_청크.jsonl"
# 사용자 입력 승인·대상 DB 및 실행별 비용 승인 후에만 실행
python -B -m solar_handoff.src.ingest --chunks "승인된_청크.jsonl" --approve-cost --confirm-input-approved --confirm-target "승인된_대상_DB_이름"
```

## 과거 보고서의 링크와 재현성

보고서 26개는 원본 바이트 그대로 보존한 역사 기록이다. 복사된 위치에서는 문서·청크·승인 자료를 포함한 보고서 내부의 일부 근거 인용 링크가 끊어진다. 원본 실험 raw와 일부 도구도 포함하지 않으므로 재현을 보장하지 않는다. 같은 이름의 다른 파일을 원본 근거로 임의 대체하지 말고 필요한 자료와 출처를 별도로 확인한다.
