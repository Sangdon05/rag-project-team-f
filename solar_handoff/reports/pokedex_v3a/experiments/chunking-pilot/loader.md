# 3문서 A/B 로더 — 실행 기록과 제한

**실행 완료:** 별도 허가된 테스트에서 118·129·151의 A-v2 29개, B-v2 48개를 로컬 전용 스키마에 적재하고 검증했다. `logs/loader_execution.json`은 모델 `embeddinggemma-2:bf16`, 768차원, 77개 벡터와 검증 결과를 기록한다. `logs/vector_manifest_v1.json`, `logs/schema_init_attestation.json`, `results/`에 당시 증거가 있다. 문서는 모두 `pending`, 운영 인덱싱 불가다. 로더는 질문과 평가 정답 파일을 읽지 않는다. 이 문서 수정에서는 DB나 모델에 접속하지 않았다.

## 오프라인 검사

저장소 루트에서 기존 Python 환경을 이용한다. `--preflight`는 전체 입력 재생성·근거 검증만 수행하며 DB, Docker, Ollama에 접근하지 않고 환경 설정이나 `.env`를 읽지 않는다.

```sh
export PYTHONDONTWRITEBYTECODE=1 TEMP="$TMPDIR" TMP="$TMPDIR"
.venv/Scripts/python.exe -m unittest discover -s pokedex_v3a/experiments/chunking-pilot/tests -p test_load_data.py -v
.venv/Scripts/python.exe pokedex_v3a/experiments/chunking-pilot/scripts/load_data.py --preflight
```

## 추가 실행 전 게이트

스키마 초기화는 별도 코드다. 추가 적재·재실행은 기존 실행 승인을 재사용하지 않고 대상·가드·모델·입력 및 권한의 재검토와 **별도 실행 승인**을 받은 뒤에만 한다. 역할과 스키마의 기존 계약은 `storage.md`와 `scripts/pilot_db.py`를 확인한다.

향후 실행 환경으로만 `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `PILOT_EXPECTED_DB_NAME`(DB와 동일), `PILOT_CONTAINER_ID`(정확한 64자리 소문자 16진 컨테이너 ID), `PILOT_OLLAMA_MODEL`, `PILOT_OLLAMA_DIGEST`(실제 64자리 소문자 SHA-256), `PILOT_MODEL_DIMENSION`(실측 차원), `PILOT_SCHEMA_ATTESTATION_SHA256`(독립적으로 고정한 attestation 파일 SHA-256)을 전달한다. 기존 DB 재검증에는 `PILOT_VECTOR_MANIFEST_SHA256`도 독립 고정값으로 필요하다. 비밀을 파일·명령 인자·로그에 넣지 않는다. 아래 명령은 승인 전 실행하지 않는다.

```sh
.venv/Scripts/python.exe pokedex_v3a/experiments/chunking-pilot/scripts/load_data.py --execute
```

기존 모델 요청 코드는 로컬 tags/ps/embed만 사용하고 배치는 최대 4개, `truncate:false`, 접두사·차원 재지정 없이 전송한다. `PILOT_MODEL_DIMENSION`은 양의 정수로 검증되며 벡터 응답과 DB typmod 비교에 사용된다. 실제 최장 입력 probe는 `logs/longest_input_probe.json`에 있다. 서버가 몰래 입력을 자르지 않았다는 사실까지 증명하지는 못한다.

모든 배치를 성공적으로 계산·검증한 후 쓰기 트랜잭션 전에 `logs/vector_manifest_v1.json`을 독점 생성한다. 기존 파일은 새 계산 결과와 바이트가 같을 때만 사용하며 절대 덮어쓰거나 삭제하지 않는다. 매니페스트에는 모델·차원·입력 파일 해시와 정렬된 청크 ID·본문 해시·float32 big-endian 벡터 해시만 기록하고 본문·벡터·비밀은 기록하지 않는다. 기존 DB를 재임베딩 없이 검증하려면 독립 고정 SHA를 `PILOT_VECTOR_MANIFEST_SHA256`으로 넘겨야 한다. 해시는 그 자체로 원본 진정성을 보장하지 않는다. 실패·불확실 시에도 파일을 보존하고 대상과 파일의 상태를 먼저 확인한다. 실제 매니페스트는 실행 기록과 함께 보존되어 있다.

오류나 커밋 응답 유실 시 자동 재시도하지 않는다. 쓰기 오류 뒤 새 검증 연결을 통한 읽기 전용 상태 검사를 시도하되 성공으로 간주하지 않는다. 출력은 비밀을 숨기기 위해 원인을 상세 표시하지 않으므로, 승인된 운영자가 정확한 대상의 실제 상태를 안전하게 확인한 후 다음 조치를 결정해야 한다.

## 제한 및 통합 주의

- 단위 테스트는 가짜 DB/HTTP를 사용하며 실제 서버 통합의 증거가 아니다. 별도 실제 적재·검증 기록이 존재하지만 모든 격리·실패 시나리오를 실증하지는 않는다. **추가 실행은 별도 승인 전 금지.**
- 쓰기 트랜잭션에서는 검증 전에 세 테이블에 `ACCESS EXCLUSIVE` 잠금을 잡고 커밋까지 유지한다. 테이블 접근을 막을 수 있으므로 격리된 테스트 DB에서만 사용한다. 스키마 전체 또는 권한·routine 변경까지 막는 전역 DDL 잠금은 아니며 관리자나 다른 변경 주체를 별도로 통제해야 한다.
- 테이블 소유 역할과 슈퍼유저 세션은 적대적 관리자나 동시 권한 변경을 차단하는 보안 경계가 아니다. `RESET ROLE`은 매 삽입 전 검사에만 사용하고 실제 INSERT는 제한 역할에서만 실행한다.
- 검색은 로더와 별도 연결 계약으로 실제 실행됐고 결과 및 독립 채점은 `results/`에 있다. 이 결과는 문서 승인이나 운영 검색 연결을 뜻하지 않는다.
- 유지·삭제 결정은 사용자에게 있다. DB의 테스트 스키마와 역할은 폴더 바깥에 있으며 자동 정리하지 않는다.
