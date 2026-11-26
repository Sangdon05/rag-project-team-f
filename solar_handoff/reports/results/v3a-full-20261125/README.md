# 151문서 3모델 임베딩 실행 기록

## 범위와 근거

- 실행 기록 기준 날짜: **2026-11-25**. 전체 index_version은 `v3a_full_151_20261125_v1`, 스키마는 `pokedex_v3a_full_v1`이다. 입력은 `draft-a-v1` 151문서, 1,504청크다. 별도의 1문서 시험은 `v3a_smoke_pokemon1_20261125_v1`, `pokedex_v3a_smoke_v1`이다.
- 사용자의 전체 운영 인덱싱 승인 의사를 전달받은 기록과 정확한 스냅샷 범위는 [승인 overlay](../../pokedex_v3a/chunks/approval-overlay.md), [승인 기록](../../pokedex_v3a/approvals/approved-draft-a-v1.json)을 따른다. 승인 기록 SHA-256은 `87b420f80c75f27ac94320c378d2094d54309c8b9c2d2ae3b95b0ee0db599983`이다. 서명·발화 인증이나 최신성·철회 관리가 없으며, 해시는 이를 대체하지 않는다. 기존 등록부와 초안은 여전히 `pending` / `index_eligible=false`; overlay는 원본 상태 변경이나 개별 문서의 사실 검증이 아니다.
- [전체 결과 JSON](full.json), [1문서 시험 JSON](smoke.json), [적재 경로 및 제약](../../pokedex_v3a/src/README.md)이 근거다. 기존 결과의 `source_files`에서 개인 scratch 절대경로만 `historical_source_name`(원래 파일명)과 `availability: original_local_scratch_not_shared`로 바꾸었고 각 원본 출처의 `sha256` 및 나머지 결과 값은 보존했다. 파일명은 이 저장소에 해당 출처 파일이 존재한다는 뜻이 아니며, 해당 원본 scratch 파일의 현재 존재 여부는 확인하지 않았다. 공유 결과는 원래 저널 전체를 대체하지 않는다. 정리 과정에서 DB·모델·API에 재접속하지 않았다.
- 수정 전 결과 JSON의 바이트 원본은 로컬 Git 제외 `runs/v3a-full-20261125/full.original.json`, `smoke.original.json`에 별도 보존하고 읽기 전용으로 표시했다. 해당 백업에는 개인 경로가 남아 있어 공유·커밋하지 않는다. 읽기 전용 표시는 변경 방지 보장이 아니며 ACL은 별도 검증하지 않았다. 원본 SHA-256: 전체 `3e3456bf1fee340d214e3f36a93dfea77aae5688f38e63ad5619caa756ec5db1`, 시험 `49d74c50bf20dae14fe6012ef96996ebd058fa604f86fa189515cf2374bc143a`. 공유 JSON SHA-256: 전체 `3434e562fc47d604cdb74f2de25e4a5b1c9a8bf72b13b4547f2691eda96394bc`, 시험 `b93769c2253faa5f20dc9412338de074b3eebba519726a6071e9ce33284753a1`. 해시는 바이트 동일성 확인용이지 원본의 진위 증명이 아니다.

## 전체 적재 및 사용량

세 모델 모두 문서와 질문에 `raw` 입력을 사용했다. 전체 문서 배치 크기 4, 모델별 성공 376/376 배치다. 로컬 요청은 `truncate=false`, `num_ctx=8192`로 기록되어 있으나 서버 실제 전처리·토큰화·잘림과 감사 토크나이저의 동등성은 미검증이다. 아래 토큰 수는 모델별 보고 사용량이지 서로 동등한 토크나이저의 비교치가 아니다. 비용은 미상이다.

| 키 | 실제 모델 ID / runtime | 기록된 revision | 차원 | 문서 토큰 사용량 | 질문 토큰 사용량 |
| --- | --- | --- | ---: | ---: | ---: |
| gemma | `embeddinggemma-2:bf16` / ollama | `6c69a2d1816d07887f4fb7fa50f40f4ba076334438680ae13ba3f7c8763c130f` | 768 | prompt_eval_count 302,428 | 9 |
| kure | `kure-v1:f32` / ollama | `7ee043f328640021d761e48b673634035e252880c6805a5c61696d10b2ca1d6c` | 1024 | prompt_eval_count 313,790 | 10 |
| openai | `text-embedding-3-small` / openai | `provider-model-alias-unpinned` | 1536 | prompt_tokens / total_tokens 각각 427,267 | 각각 12 |

로컬 revision은 기록된 모델 digest다. OpenAI의 revision은 고정된 불변 버전이 아닌 제공자 별칭이므로 나중에 동일 동작을 보장하지 않는다. 해당 실행의 벡터 SHA-256은 다음과 같으며, 원본 결과의 검증 결과·receipt와 별도 DB 읽기 검사에서 각각 일치한다고 기록됐다. 이는 모델 파일 digest가 아닌 **벡터 집합 digest**다.

| 모델 | 벡터 SHA-256 |
| --- | --- |
| gemma | `7d22b9af1b5aececbe669b9f87b6a54c1a30dbec5cfee9a7581eb9c0369416b9` |
| kure | `99f233595405f56e6d947286dcb2303bddcb026d16652319bc1dbd4744fbd826` |
| openai | `836634eac2bbade76c6e446182d09ebdd374cd47e375611d025629461e55804e` |

## 검증 범위와 검색

[전체 결과](full.json)의 실행 결과는 `verified`, 1,504청크 및 모델별 1,504벡터다. 별도 DB readback 기록은 버전 행 1개, 고유 문서 151개, 고유 청크 ID 1,504개 및 모델별 고유 ID 1,504개, 차원 유효, 벡터 digest와 receipt 일치를 보고한다. [src 설명](../../pokedex_v3a/src/README.md)은 별도 연결 readback과 SQL count·차원 확인을 기술한다. 이들은 당시 도구/에이전트가 남긴 결과이지 이 문서 작성 시 새 DB 실측이나 독립 인증은 아니다.

1문서 시험은 `pokemon:1`의 청크 10개와 각 모델 벡터 10개, 별도 읽기 전용 연결 readback과 각 모델 검색을 기록한다. 전체 검색 질문은 `이상해씨의 타입은?` (`type`), k=5이며 각 모델의 전용 테이블을 검색했다. 상위 다섯 ID는 다음과 같다. 거리와 1문서 검색은 각 JSON에 보존한다.

| 모델 / 대상 테이블 | 순서대로 검색된 청크 ID |
| --- | --- |
| gemma / `vectors_gemma` | `pokemon:1#profile`, `pokemon:1#stats`, `pokemon:3#stats`, `pokemon:2#profile`, `pokemon:3#profile` |
| kure / `vectors_kure` | `pokemon:1#profile`, `pokemon:1#stats`, `pokemon:2#profile`, `pokemon:1#attack_matchup`, `pokemon:1#defense_matchup` |
| openai / `vectors_openai` | `pokemon:1#profile`, `pokemon:2#profile`, `pokemon:1#stab`, `pokemon:1#attack_matchup`, `pokemon:3#profile` |

모두 첫 결과가 `pokemon:1#profile`이지만, 1질문 검증은 정식 평가나 모델 순위·품질 채택이 아니다. 검색 방식 A/B/C, 전체 RAG·생성 및 정식 평가 연동, 증분 sync와 활성화는 미구현이며 모델 최종 선택도 아니다. 최종 평가 발주·설정 고정과 평가 입력 및 실행 준비는 별도로 필요하다.

## DB와 보존 한계

전체 스키마는 `index_versions`, 공통 `chunks`, 모델별 `vectors_gemma`, `vectors_kure`, `vectors_openai` 다섯 테이블이다. 세 벡터 공간을 섞지 않는다. 전용 실행 역할 `pokedex_v3a_index_writer_v1`은 비관리자 NOLOGIN이지만 관리자 로그인에서 트랜잭션 로컬 SET ROLE을 쓰는 방식은 보안 샌드박스가 아니다. 관리자 또는 임의 SQL은 역할을 되돌리거나 권한을 바꿀 수 있다. 전체·시험 스키마와 전용 역할 등 DB 객체는 남는 대상으로 취급하며 별도 승인 없이 삭제하지 않는다. 기존 DB·볼륨·파일럿 및 기준선은 보존 대상이고, SQL 제약이 관리자의 변경을 방지한다는 뜻은 아니다. 상세는 [적재 경로](../../pokedex_v3a/src/README.md)와 [vectordb 규칙](../../.claude/skills/vectordb/SKILL.md)을 따른다.

로컬 `runs/manifest.jsonl`에는 전체·시험 결과를 가리키는 `embedding_run_record`와 후속 부분 보존 기록 `v3a-full-partial-journal-evidence-cff0ccf6e0fa441298cbc804adb8f6ea`가 있다. 전자에는 run_id가 없다. 후자와 로컬 `runs/v3a-full-20261125/SUMMARY.txt`는 성공 1,128배치, 원본 17파일 제외를 기록한다. 2,256개 배치 JSON은 **부분 증거일 뿐 재개 가능한 완전 저널이 아니다**. 원본 scratch는 24시간 유휴 정리 제한이 있고, `runs/`와 manifest는 Git ignore되어 팀에 공유되지 않는다. 로컬 보존분의 ACL은 검증되지 않았다. 벡터가 든 대용량 저널은 제출 결과에 넣지 않는다.

`full.json`의 `archive_status`는 당시 비밀값 충돌로 원본 전체의 바이트 보존 복사가 중단된 시점의 기록이다. 이후 위 부분 증거가 보존되었지만 원본 전체 복구·보존이 완료된 것은 아니다. 기록 실패 원인은 민감 값과 식별값의 충돌로만 다루며 값 자체는 기록하지 않는다.

## 남은 확인

- 보안 검사 경고 38건은 작업 요청에서 전달된 이전 검사 시점의 수치다. 이번 문서 작업에서는 사용자 제한 때문에 보안 검사 전체를 다시 실행하지 않았으며 현재 수치·분류·해소 여부는 미확인이다. PR 또는 push 전 별도 보안 검토가 필요하다.
- 공유 결과 JSON은 원본 scratch 절대경로 대신 원래 파일명과 출처 해시만 담는다. 전체 저널은 공유·재현에 충분하지 않다. 승인 원본 바이트의 공유 및 새 checkout 검증, 원본 근거의 적법한 보존과 로컬 접근 통제는 별도 확인이 필요하다.
