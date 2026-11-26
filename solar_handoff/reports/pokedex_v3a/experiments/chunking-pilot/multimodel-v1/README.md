# 3문서 멀티모델 검색 파일럿

사용자 승인 후 118·129·151의 동일 A/B 청크와 질문을 Gemma·KURE·OpenAI로 실제 검색하고 독립 채점했다. A/B는 검색 방법이 아닌 청킹 변형이다. 15문항 중 범위 밖 CP15를 제외한 14문항의 결과와 판정은 [상위 README](../README.md), 문항별 근거는 [score.md](eval/comparison-v1/score.md)를 따른다. A를 파일럿 기본으로 유지하며 KURE 결과는 이 3문서·14문항·동일 입력·무접두사 조건에서만 유망하다. 일반 모델 순위나 별도 held-out 평가는 아니다. 현재 실행 범위·제한은 [RUN.md](RUN.md)를 따른다.

`results/kure/`, `results/openai/`는 보존 중인 모의 자료이고 실제 결과는 `results/real-v1/<model>/`이다. 성공해도 `pending` 파일은 남는다. 파일·DB 스키마·기록은 별도 승인 없이 삭제하지 않는다. 기존 151개 문서 등록부는 pending이며, 이후 전체 승인 의사의 서명 없는 별도 파일 기록과 운영 준비의 한계는 [승인 overlay](../../../chunks/approval-overlay.md)를 따른다. 답변 생성·범위 밖 거절은 평가하지 않았다.

두 모의 디렉터리의 산출물 6개는 로컬에만 보존하고 Git에 커밋하거나 공유하지 않는다. 재현에 필요한 청크와 실제 파일럿 결과에만 사용자 지정 생성물 예외가 적용된다. 상세는 [모의 결과 안내](MOCK_RESULTS_NOTICE.md)를 따른다.

## 역사적 준비 기록 — 현재 상태가 아님

아래는 최초 오프라인 stub 당시의 계획과 미구현 상태를 보존한 것으로 현재 실행 코드·결과를 설명하지 않는다. 구 `results/kure/`, `results/openai/` 출력 제안은 폐기됐다. 현재 결과·절차는 위 링크를 따른다.

## 범위 및 고정 입력

상위 `chunking-pilot` 기준 `chunks/A-v2.jsonl`, `chunks/B-v2.jsonl`, `chunks/manifest-v2.json`, `queries/pilot_queries.json`, `results/raw_search_v1.json`의 사용자 지정 SHA-256을 `pilot.py`에 고정했다. 마지막 파일은 Gemma 결과 보존 여부만 검사하며 내용을 정답이나 생성 입력으로 쓰지 않는다. 질문은 qid와 question만 취하고 태그는 전달하지 않는다. A 29, B 48, 질문 15개이며 양쪽 모두 118·129·151에 한정한다. 기존 `scripts/vector_store.py`의 오프라인 전체 재생성 검증을 호출한다. 사람이 확인한 승인 또는 독립 평가를 대체하지 않는다.

평가 정답 파일과 평가 스크립트는 접근하지 않는다. 향후 원본 결과는 각 모델별 `results/kure/raw_search_v1.json`, `results/openai/raw_search_v1.json`으로만 신규 생성하는 것을 제안한다. 이 결과는 독립 평가자에게 넘긴다. 결과와 설정은 검색 전용, k=5, exact cosine, 필터 없음, chunk_id 바이트순 tie-break가 목표다. 아직 SQL 검색 구현이 없으므로 실측 사실이 아니다.

## 모델과 제안된 격리 대상

| 키 | 요청 모델 | 제안 스키마 | 제안 소유 역할 | 카드상의 차원 (실측 아님) |
|---|---|---|---|---:|
| kure | `kure-v1:f32` | `chunking_pilot_kure_v1` | `chunking_pilot_kure_writer_v1` | 1024 |
| openai | `text-embedding-3-small` | `chunking_pilot_openai_v1` | `chunking_pilot_openai_writer_v1` | 1536 |

각 역할은 제안상 NOLOGIN, 최소 권한, 해당 스키마와 테이블만 소유한다. 역할은 DB가 아니라 클러스터 전역 객체다. 두 이름은 제안일 뿐 객체를 만들지 않았다. 기존 `chunking_pilot_3doc_v1` 및 `chunking_pilot_writer_v1`은 절대 변경하지 않는다. 두 스키마는 새 DB의 별도 파일럿 전용으로만 쓰며, 다른 이름/역할을 사용자 입력 SQL로 허용하지 않는다. 나중에 DB 외부 객체의 유지·삭제는 사용자 별도 결정이 필요하다.

문서와 질문에 공통으로 추가 접두사 없이 원문 그대로 보낸다는 계획이다. 순수 요청 빌더는 KURE `truncate:false`와 OpenAI 차원 변경 없는 float 요청을 만든다. 전송, 토크나이저, 숨은 접두사, 서버 측 잘림 여부는 검증하지 않았다. KURE 카드상 8192, OpenAI 문서상 입력 8192 토큰과 100만 입력 토큰당 $0.02는 발주자가 제공한 참고치이고 이 작업에서 외부 확인하지 않았다. 실제 한도·가격과 각 입력의 토큰 수는 실행 전 별도 확인해야 하며, 글자 수를 토큰 수로 대신하지 않는다. OpenAI 요청의 명시적 자르기/분할은 없지만 그 자체가 서버 동작 증명은 아니다. 실제 첫 probe 벡터와 전체 문서·질문의 차원 및 길이 검증 결과가 기준이다.

## 오프라인 명령

저장소 루트에서 Python 3.13 이상, 기존 프로젝트 환경을 사용한다. `TMPDIR`은 절대경로인 허용 scratch로 미리 설정해야 한다. 새 패키지는 추가하지 않았다.

```sh
export PYTHONDONTWRITEBYTECODE=1 TEMP="$TMPDIR" TMP="$TMPDIR"
python pokedex_v3a/experiments/chunking-pilot/multimodel-v1/pilot.py --preflight
python -m unittest discover -s pokedex_v3a/experiments/chunking-pilot/multimodel-v1 -p 'test_*.py' -v
```

`--preflight`는 비밀 파일, DB, Docker, 모델이나 네트워크에 접근하지 않는다. 단위 테스트는 동결 원본, 임시 파일과 가짜 응답을 사용한다. 소스 해시 변경·재생성 불일치, 대상 중복·누락, 모델/스키마/역할 불일치, 차원·응답 개수·인덱스·float32 유효성·0 벡터, 요청 형식, 오류 메시지의 비밀 억제, 결과 파일 독점 생성에 대한 오프라인 검사다. 이 테스트는 실제 서버와 DB의 안전성이나 의미 검색 품질을 검증하지 않는다.

## 명시적 모델 probe (승인 후에만)

다음 명령은 각각 실제 로컬 모델 요청 또는 과금될 수 있는 OpenAI 요청을 수행한다. 이 작업에서는 실행하지 않았다. `PILOT_KURE_DIGEST`는 별도 확인한 로컬 모델의 전체 SHA-256이며 `OPENAI_API_KEY`는 승인된 외부 런처가 환경에 넣는다. `.env`는 읽지 않는다.

```sh
python pokedex_v3a/experiments/chunking-pilot/multimodel-v1/probe.py --model kure
python pokedex_v3a/experiments/chunking-pilot/multimodel-v1/probe.py --model openai
```

77개 청크와 15개 질문 중 **문자 수**가 가장 긴 입력 하나를 원문 그대로 보낸다. 토큰 수 기준 최장은 아니다. KURE는 고정 loopback 및 `truncate:false`, 전후 모델 digest를 확인하고 OpenAI는 고정 공식 HTTPS 엔드포인트에만 Authorization 헤더를 사용한다. 프록시·리다이렉트·자동 재시도·클라이언트 분할은 없다. 관측 차원이 각각 1024·1536이 아니면 실패한다. 서버 내부 처리와 토큰 기준 최대 길이는 검증되지 않는다. `logs/<model>_probe.pending`은 요청 전에 독점 생성하고 성공해도 보존한다. `logs/<model>_probe.json`도 독점 생성한다. 실패·응답 불명·부분 파일이 있으면 자동 재시도하지 말고 운영자가 상태를 확인해야 한다. 출력된 probe 해시는 독립적으로 보관해야 하지만, 이 파일은 아직 DB 가드의 입력이 아니다.

## 후속 구현 및 승인 게이트 — DB 및 검색 미완료

1. 모델 probe 전송만 구현됐다. 전체 적재·검색 요청은 별도 구현 및 검토가 필요하다. 로컬 모델 digest와 배포 식별자, 원격 모델 식별자/버전 한계와 비용·토큰 사용을 기록한다. API 키·DB 인증정보는 인자, 로그, 결과에 기록하지 않는다. Ollama의 설치 확인과 embed 요청 사이에 모델이 제거되는 경쟁 상황까지 코드만으로 다운로드 불가를 보장하지 못한다. 별도 네트워크 차단과 운영자 통제가 필요하다.
2. 입력 원문 및 실제 서버 전달, 최장 입력과 전체 입력 토큰 한도, 무접두사, 무잘림 및 비분할을 검증한다. 실제 probe를 문서와 질문에 수행해 벡터 수, 유한 float32, nonzero 및 일관된 차원을 확인하고 각 모델의 probe 기록을 독점 생성·외부 해시 고정한다. 검증할 수 없는 서버 내부 변환은 명시한다. 차원을 환경변수나 카드만으로 확정하지 않는다.
3. 검토된 DB 어댑터 구현: 기존 대상 DB의 로컬 Docker endpoint, 컨테이너 ID, 이미지, 포트, 볼륨, 네트워크 IP와 DB/세션 identity를 각각 독립적으로 검증하고 연결 문자열, `PG*`, Docker context 등 우회·위조 설정을 금지한다. 독립된 외부 attestation과 해시를 사용하되 값 자체가 진정성을 보장하지 않음을 기록한다. 모델별 새 스키마/역할이 이미 존재하면 비어 있어도 재사용하지 않고 중단한다.
4. 검증된 실측 차원 후에만 고정 SQL로 스키마·역할·테이블을 생성한다. DB 및 역할 권한, 검색 경로, 공개 vector 타입, 소유권과 다른 스키마의 write·routine 권한을 확인한다. 외부 입력에서 SQL 식별자나 SQL 문을 받지 않는다. 별도 관리자가 동시 DDL·권한 변경을 하지 못하도록 통제한다. 스키마 카탈로그·ACL 전체와 입력·벡터 매니페스트를 독립 검토·고정하고, 알 수 없는 객체·상태는 거절한다.
5. 완전한 A/B 데이터만 모델별로 정확히 한번 삽입한다. 하나의 트랜잭션과 실패 시 rollback, 커밋 응답 유실 시 자동 재시도 금지, readback과 벡터·청크·모델별 SHA 및 77개 정합성을 확인한다. 로컬 결과와 DB 트랜잭션은 원자적이지 않으므로 부분 파일·불확실한 커밋은 보존하고 운영자가 상태 확인한다. 기존 스키마·다른 모델 대상으로 어떠한 write도 금지한다.
6. 각 모델의 해당 벡터 테이블에만 같은 모델의 질문 벡터를 사용한다. SQL exact cosine(근사 인덱스 미사용), k=5, A/B별 15개 결과와 근거, 순서, 거리, 모델·입력·설정·벡터 매니페스트 해시를 검증하고 독점 출력한다. 독립 평가자는 고정된 Gemma 원본과 A/B 질문을 비교한다. 평가 정답을 구현자나 임베딩 요청에 노출하지 않는다.
7. 가짜 DB·HTTP로 존재 스키마/역할 거절, 부분 재고 거절, 모든 실패 지점 rollback 및 불확실 커밋, 권한·attestation·연결 변조, endpoint 변경, 비밀 유출, 병렬성 및 파일 충돌 테스트를 추가한다. 임시 DB에서의 통합 테스트는 별도 승인 후 수행한다. 현재 그런 DB 관련 구현이나 테스트는 **없다**.
8. 보안 리뷰와 부모 독립 검증, 실제 모델/API 및 DB write 승인 전에는 라이브 기능을 연결·실행하지 않는다. 기존 파일과 Gemma 스키마·역할·매니페스트의 보존을 전후 검증한다.
