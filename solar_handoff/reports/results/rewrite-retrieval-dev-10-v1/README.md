# 리라이트 후 B 검색

**실환경 어댑터와 CLI는 합성 입력·모의 DB/전송으로만 검증했다. 실제 DB·모델·API 실행은 아직 하지 않았다.** 평가·재정렬·답변 생성은 없다. `config.json`은 검토용 설정 요약이고 실행값의 기준은 `run.py`의 `settings()`와 기존 하이브리드 설정이다. 설정 해시는 `settings()`의 정렬된 compact UTF-8 JSON에 대한 SHA-256이다.

## 오프라인 검사

저장소 루트에서 Git Bash로 실행:

```bash
export TMPDIR='C:/Users/lexus/AppData/Local/hermes/profiles/blank/cache/scratch'
export TEMP="$TMPDIR" TMP="$TMPDIR" PYTHONDONTWRITEBYTECODE=1
python results/rewrite-retrieval-dev-10-v1/test_run.py -v
python results/rewrite-retrieval-dev-10-v1/test_live.py -v
```

실제 질문·청크·정답·환경 파일은 열지 않는다. 합성 10문항/30청크 코어 검사와 합성 1,504청크·모의 DB/HTTP 통합 검사다. 실제 DB·제공자 호환성 검사는 아니다.

## 인터페이스와 기록

`run(original_bytes, rewrite_bytes, corpus, db, kure, solar, directory, secrets)`는 정확한 원본 질문과 리라이트 JSON 바이트를 받아 스키마·qid 순서·원문 UTF-8·fallback 및 입력 크기를 검증하고 두 바이트의 해시를 기록한다. Solar의 기존 어댑터 제약상 같은 배치 내 중복 검색어는 사전에 거부한다. 질문 데이터는 `{qid, question}`, 리라이트는 정확히 `{qid, original_question, search_query, status}`여야 한다. 정답/근거 키가 들어오면 거부한다. 원문은 기록에 보존하고 검색에는 `search_query`만 보낸다.

- `corpus`: 각 항목은 `chunk_id`, `document_id`, `content`, `content_sha256`, `metadata`를 포함. BM25와 결과 첨부에 같은 객체를 사용한다.
- `db.preflight(bindings, corpus)`는 오류 발생 시 예외; `db.search(table, vector, 20)`은 거리·ID 오름차순 `{chunk_id, distance, rank}` 20개를 반환. 테이블 키는 `kure` 또는 `solar`다.
- `kure.preflight(binding)`와 `solar.preflight(binding)`는 신원 검증 후 반환. 각각 `embed(texts, options)`가 순서대로 1024차원 벡터 목록을 메모리로만 반환한다. KURE는 10개 한 번, Solar는 4/4/2번이다.
- `directory`는 비어 있는 전용 결과 디렉터리여야 하며, 기존 execution/call 마커 또는 raw 결과가 있으면 재실행을 거부한다. 호출 직전에 fsync한 독점 start 마커를 남기고 결과·실패 마커와 부분 `raw.json`을 보존한다. 실패나 결과 미확인 때 자동 재시도하지 않는다. 디렉터리 fsync나 전원 장애에 대한 완전한 내구성 보장은 확인하지 않았다. 마커를 지우고 무심코 재실행하지 않는다.
- `secrets`에는 실제 키·비밀번호 등 민감값을 전달해야 하며 기록 전 충돌을 검사한다. 어댑터는 예외·벡터·키·질문키를 출력/기록하지 않아야 한다. 코어는 벡터와 예외 문자열을 저장하지 않는다. 이 가드는 호출자·어댑터의 별도 로깅까지 통제하지 않는다.
- B 결과 20행에는 질의별 양쪽 후보, 결합 전체 union, 원문과 검색어 및 top5 본문·출처가 남는다. 미래 C/답변 단계는 **원문 질문**과 해당 모델의 B top5만 사용해야 한다. C는 이 코드 범위 밖이다.

## 실제 실행 전 조건

부모가 `rewritten_queries.json` 원본을 보존하고 `search_queries_reviewed.json`을 별도로 검토·고정한다. 두 파일은 `results/rewrite-dev-10-v1/`에 있어야 한다. 원본 질문 파일의 기존 고정 해시와 두 리라이트 파일의 별도 SHA를 검증한다. 형식이나 해시 일치는 의미 보존을 증명하지 않는다. `fallback_original` 검색어는 원문과 같아야 한다.

`results/rewrite-dev-10-v1/semantic-review.md`의 원문과 SHA를 `raw.json`의 `preflight.rewrite_review`에 두 리라이트 파일 SHA와 함께 기록한다. 보고서는 UTF-8이어야 하고 fallback qid를 모두 언급해야 한다. qid 출현 검사는 사유의 타당성을 보장하지 않으므로 부모가 이미 검토한 실제 사유를 확인한다. 알려진 비밀과 충돌하면 기록 전 중단하며, 부모가 보고서에 정답이나 기타 민감정보가 없는지도 별도로 확인해야 한다.

`--manifest`는 독립 검토·승인된 기존 preflight JSON 경로이며 파일 SHA가 기존 `base.PREFLIGHT_HASH`와 같아야 한다. `--approval-name`은 `pokedex_v3a/approvals/`에 있는 결정 파일명이다. 결정은 기존 `base.DECISION`에 묶고 `solar_ingest.snapshot`으로 승인 범위를 검증한다. 과거 manifest 부재, 변경된 대상, 승인 철회 여부가 있으면 실행하면 안 된다. 부모가 현재 승인과 대상 정체성을 별도 확인한다. 해시만으로 승인·철회 여부를 증명할 수 없다.

실제 실행 Python에는 `psycopg`가 필요하다. 연결 시에만 `pokedex_v3a/.env`의 DB 자격 증명 및 루트 `.env`의 `UPSTAGE_API_KEY`, `UPSTAGE_QUERY_MODEL`, `UPSTAGE_EMBEDDING_MODEL`을 프로세스 메모리에서 읽는다. 환경 파일을 만들거나 변경하지 않는다. `PG*` 환경 변수는 거부한다. 공급자 모델 설정은 기존 passage/query ID와 일치해야 한다.

부모가 코드를 독립 검토하고 비용·외부 전송을 설명하여 **명시적 실행 승인**을 받은 뒤에만 실행한다. 원문은 로컬 결과에, 검색어 10개는 Solar에도 전송된다. Solar 유료 요청 3회(4/4/2), KURE 로컬 임베딩 1회(10개)와 태그 조회를 계획한다. 비용은 공급자 사용량에 따르며 실패 시에도 발생할 수 있다.

## 승인 이후 실행 형식

아래 변수는 부모가 확정한 경로·이름·해시이며 비밀을 넣지 않는다. 예시는 실행 승인 자체가 아니다.

```bash
python results/rewrite-retrieval-dev-10-v1/live.py --execute \
  --manifest "$APPROVED_PREFLIGHT_FILE" \
  --approval-name "$APPROVED_DECISION_BASENAME" \
  --original-rewrite-sha256 "$ORIGINAL_REWRITE_SHA256" \
  --rewrite-sha256 "$REVIEWED_REWRITE_SHA256" \
  --review-report-sha256 "$REVIEW_REPORT_SHA256"
```

읽기 전용 repeatable-read 트랜잭션에서 승인된 1,504 청크와 DB의 ID·본문·메타데이터·해시, 기존 config와 KURE/Solar 벡터 전체 digest를 검사한다. 양쪽 별도 테이블의 exact sequential scan 계획을 확인한다. KURE 모델 태그·digest와 `truncate=false`, `num_ctx=8192`를 사용하며 Solar는 4/4/2 query 호출이다. Solar `conservative_unverified`의 UTF-8 바이트 제한은 토큰 수가 아니며 토크나이저 일치와 서버 잘림은 미검증이다.

결과 디렉터리는 이 폴더로 고정한다. `raw.json`은 B 20행과 전체 결합 후보, top5, 원문·검색어, 주요 코드 해시 및 검토 보고를 보존한다. 호출별 마커에 qid와 사용 가능한 usage를 기록하며 벡터·키·DB 신원은 기록하지 않는다. 기존 `execution-*`, `call-*` 또는 `raw.json`이 있으면 재실행을 거부한다. 실패·타임아웃 시 자동 재시도하지 않으며 기존 마커를 지우지 않는다. 마커는 파일 fsync 후 독점 생성하지만 디렉터리 fsync나 전원 장애 내구성은 검증하지 않았다. 예외 내용은 비밀 누출을 막기 위해 출력하지 않는다.
