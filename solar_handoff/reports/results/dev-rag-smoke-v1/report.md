# 개발 질문용 통합 CLI 실환경 동작 확인

2026-11-26 UTC. 이것은 질문 하나에 대한 제한된 동작 시험이지 독립 품질 평가, 최종 평가 또는 운영 채택이 아니다. 실행은 이미 별도 승인되어 수행됐고 이 보고서 작성에서는 API나 DB를 호출하지 않았다. 원본 트레이스는 로컬 `runs/`에 보존되며 질문·문서·답변을 포함하므로 공유 시 접근에 주의한다.

## 질문과 실제 답변

- 원 질문: `이브이의 타입은 무엇인가요?`
- KURE + C + 리라이트 + GPT-6 Luna: 검색어 `이브이의 타입`, 답변 `이브이는 노말 타입입니다. [[pokemon:133#profile]]`.
- KURE + B + 리라이트 끔 + 로컬 EXAONE: 검색어는 원 질문 그대로, 답변 `이브이의 타입은 **노말**입니다 [pokemon:133#profile].`
- 두 실행 모두 선택된 청크의 ID `pokemon:133#profile`을 인용했고 유효하지 않은 ID는 없었다. 해당 청크의 본문에 `타입: 노말`이 실제로 있다. 출처는 `pokedex_v3a/` 기준 `documents/133_이브이.md`, 제목 `기본 정보`, 제목 줄 1·8, 본문 줄 2–7·9–11이며 근거 파일은 `document_evidence/133.json`이다. 이는 이 답변에 대한 본문 확인이지 자동 의미 검증이나 독립적인 정식 채점은 아니다. 트레이스 자체는 `ids_valid_claim_support_unreviewed`와 사람 검토 필요를 기록한다.

## 후보와 순서

GPT 실행의 BM25 20개와 벡터 20개를 RRF로 결합한 중복 제거 합집합은 27개, 그중 B top5는 아래 다섯 개다. C는 바로 이 다섯 개만 재정렬했다. 숫자는 순위이고, C의 원래 B 순위 순열은 `[2, 4, 5, 1, 3]`이다.

| B 순위 | 청크 ID | C 순위 |
| --- | --- | --- |
| 1 | `pokemon:133#defense_matchup` | 4 |
| 2 | `pokemon:133#profile` | 1 |
| 3 | `pokemon:133#evolution` | 5 |
| 4 | `pokemon:133#stab` | 2 |
| 5 | `pokemon:133#attack_matchup` | 3 |

EXAONE 실행은 리라이트를 끄고 별도 검색했으며 BM25 20개와 벡터 20개의 중복 제거 합집합은 28개다. B top5 순서는 `pokemon:133#defense_matchup`, `pokemon:133#attack_matchup`, `pokemon:133#profile`, `pokemon:133#evolution`, `pokemon:136#evolution`이다. 두 실행은 검색어와 방법이 달라 답변 모델만 바꾼 공정 비교가 아니다. 이 숫자는 후보 수이지 검색 품질 점수가 아니다.

## 모델 사용량과 비용

GPT 리라이트, 재정렬, 답변은 각각 `gpt-6-luna`, reasoning `low`, temperature 미지정, truncation disabled다. 제공된 실제 토큰 사용량은 다음과 같다.

| 단계 | 입력 | 출력 | 총 토큰 |
| --- | ---: | ---: | ---: |
| 리라이트 | 93 | 46 | 139 |
| 재정렬 | 923 | 196 | 1,119 |
| 답변 | 1,614 | 19 | 1,633 |

로컬 EXAONE `exaone3.5:7.8b-instruct-q4_K_M` 답변의 기록은 prompt 1,852, 생성 22 토큰이다. KURE 질의 임베딩 기록은 GPT 실행 prompt 8, EXAONE 실행 prompt 12다. 비용은 측정되지 않아 **알 수 없음**이며 숫자를 추정하지 않았다. 로컬 답변 입력 잘림 여부 및 서버 토크나이저 동등성은 확인되지 않았다. Solar의 바이트 제한은 토큰 수나 잘림 없음의 증명이 아니다.

## 이전 실패와 재시험

- `runs/dev-rag-13614d4874634f30bba1ad16ba94db1c/trace.json`: EXAONE이 잘못된 플레이스홀더 형식 `[[[chunk_id]]]`를 출력했고 인용 ID 검증 실패로 중단됐다. SHA-256 `e3e4585421853039a4ad1037d785b4629af7735f6710419c288351af4775a5cd`.
- `runs/dev-rag-02ad135a91d04f75b08a96eba078281d/trace.json`: 단일 대괄호 ID가 답변에는 있었지만 당시 파서가 이를 인식하지 못해 `unverified/missing` 경고를 남겼다. SHA-256 `a94c814875cc9eca48a488fce55b9d6098db84ee7a638a2a6fe4a587e6c2d892`.
- 파서 확장 이후의 최종 EXAONE 실행에서 해당 단일 대괄호 ID가 인식됐다. 이전 두 결과를 성공으로 덮어쓰지 않았다.

## 현재 원본 증거

- GPT: `runs/dev-rag-4fe5d7a022f241e9ba967d31951774c4/trace.json` — SHA-256 `5aa6997567137985086ed6165e562aef4f50ec90d74e6202413a8f7ba262c79a`.
- EXAONE: `runs/dev-rag-ae6e67a868a6419ca9873f015ad46f34/trace.json` — SHA-256 `bcb316fdd2702286f61fa83a104a307b10279a775d92f23329a7fbf6a6f9a6eb`.
- 별도로 생성한 시험 대상 읽기 역할의 새 연결 확인: `runs/dev-rag-read-role-ad14f813de0a4a25a84ed509613b4c3f/result.json` — SHA-256 `fc8dfad7676f9244368a197c9dd5ebebb48713907e203c7c793cc5b53e8c54cd`. 테이블 변경 권한 없음과 네 대상의 행 수 1 / 1,504 / 1,504 / 1,504를 확인한 기록이다. 로그인 역할은 superuser이므로 SET ROLE과 읽기 전용 트랜잭션은 보안 샌드박스가 아니다.
- 오프라인 CLI 단위 테스트: 부모 실행에서 18개 통과. 모의 단위 테스트는 실환경 호출의 대체 증거가 아니다.

## 남은 범위

Solar 검색 및 EXAONE과 C/리라이트의 조합은 통합 CLI에서 실환경 시험하지 않았다. 리라이트 형식 성공만으로 의미 보존을 보장하지 않으며, 한 질문의 내용 확인만으로 다양한 질문의 정확성·거절 처리·출처 적합성을 일반화할 수 없다. 사람의 독립 평가와 최종 평가, 전체 LangChain tool-calling 에이전트 및 UI는 이 시험 범위 밖이다. 설정은 실행 전 프로세스 환경에 수동 주입하며 `.env`를 자동으로 읽지 않는다. 팀 공유에 필요한 의존 파일과 현재 승인 확인은 별도 선행 조건이다.
