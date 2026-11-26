---
name: rag-eval
description: Use when running RAG evaluations, scoring setup, failure analysis, comparison reports, or reviewing the user-owned eval set.
---

# rag-eval

eval 에이전트가 쓰는 스킬. 사용자가 만든 평가셋으로 RAG 체인을 같은 조건에서 실행하고, 원본 기록을 남기고, 실패를 분석하고, 비교 보고서를 쓴다.

## 전제

- **평가셋은 사용자 소유다.** `eval/dev.json`, `eval/test.json`, `eval/LOCK.json`을 만들거나 고치지 않는다. `lock` 명령도 실행하지 않는다. 문제를 발견하면 의견서를 쓴다. 스키마는 [eval/README.md](../../../eval/README.md)가 원본이다.
- **사람이 채점한다.** 정답 충족, 근거 적합(뒷받침 여부), 근거 없음 대응은 사람이 처음부터 채점한다. 에이전트는 자동 지표만 계산하고, 채점표를 준비하고, 사람이 채운 결과를 집계한다. LLM 판정을 쓰지 않는다.
- **평가 대상은 langchain-rag 스킬이 정의한 체인이다.** eval은 체인 구조를 정하지 않는다. 체인이 남기는 트레이스(검색 방식, 검색 호출 여부, 재정렬 전후 후보, 툴 호출, 답변, 인용)를 원본으로 채점한다. 검색을 호출하지 않고 답한 문항은 Hit@5 = 0으로 집계하고 따로 표시한다.
- **최적화는 쿼리 리라이트만 쓴다.** 캐싱 실험은 하지 않는다.

## 구성 (A/B/C + 리라이트)

| 구성 | 내용 | 기록할 설정 |
| --- | --- | --- |
| A | Vector 검색만 | 임베딩 모델, k |
| B | BM25 + Vector, RRF 결합 | 후보 수(각 검색기), RRF k·가중치, 중복 제거 규칙 |
| C | B + re-ranking | reranker, 입력 후보 수, 출력 k |
| C+RW | C + 쿼리 리라이트 | 리라이트 모델·프롬프트 버전, fallback 여부 |

A/B/C/C+RW는 생성 모델·프롬프트·출력 한도·툴 설정·최종 k가 같아야 한다 (langchain-rag 재현성 규칙). 다르면 실행하지 않고 보고한다.
langchain-rag가 구분하는 "검색 결과만 비교하는 실험"과 "툴을 포함한 전체 답변 실험"은 run을 나눠 기록한다 (`run.json`의 실험 종류).

## 단계별 절차

### 1. 평가셋 검토 (평가셋이 바뀔 때마다)

1. `scripts/eval/evalset_lock.py verify --split dev`(최종 평가 발주와 설정 고정 후에는 `test`)를 실행한다. 실패하면 멈추고 사용자에게 잠금을 요청한다.
2. [eval/README.md](../../../eval/README.md) 스키마로 검증한다: 필수 필드, qid 중복, 문항 수·유형 분포(dev 8/2, test 10/7/3).
3. `allowed_evidence`의 chunk_id가 현재 승인 청크에 있는지 확인한다. 없으면 근거 매핑이 낡은 것이다.
4. `key_facts`를 승인된 문서·`data/processed/`와 대조한다. 다르면 "정답 오류 의심"으로 적는다. 고치지 않는다. 답변 기준은 영문 Red·Blue다.
5. 발견 사항을 [의견서](references/feedback-template.md)로 `eval/feedback/{YYYYMMDD}-{split}.md`에 쓴다.
6. 의견서에 **차단** 의견(잠금 불일치, 스키마 위반, 근거 매핑 낡음)이 하나라도 있으면 평가를 실행하지 않고 `blocked`로 보고한다. 권고만 있으면 실행할 수 있다.

test 문항 검토는 오케스트레이터의 최종 평가 발주와 설정 고정 후에만 한다 (검토는 발주에 포함된 것으로 본다). 그 전에는 test 내용을 열거나 해시를 계산하지 않고 `verify --split test`와 `verify --split all`도 실행하지 않는다. dev 검증은 가능하다.

### 2. 개발 평가 (dev 10)

- rag-developer의 변경을 검증할 때 오케스트레이터가 발주한다. 근거 부족 판정 기준(임계값 등)은 dev 결과로만 정한다.
- 실행 → [기록](references/records.md) → 자동 지표 → 채점표 준비 → (사람 채점) → 집계 → [실패 분석](references/failure-taxonomy.md).
- 불안정한 실패는 해당 qid만 3회 반복해 구분한다 (dev에서만).

### 3. 최종 평가 (test 20)

- 오케스트레이터의 최종 평가 발주와 "설정 고정"이 모두 있은 뒤에만 한다. 고정 이후에는 체인·설정·프롬프트를 바꾸지 않는다.
- 실행 수: A/B/C × 20 = **기본 60건**, C+RW × 20 = **분기 20건**. 각 1회.
- 호출 오류가 나도 그 결과를 그대로 기록한다. 재시도는 `retry` 종류로 따로 기록하고, 최종 지표는 첫 실행 기준으로 낸다.
- 최종 결과를 본 뒤 하는 실험은 `extra`로 분리한다.

### 4. 지표 집계

- 정의는 [metrics.md](references/metrics.md). 모든 지표에 분모를 같이 쓴다.
- 사람 채점이 비어 있는 문항이 있으면 집계를 미완료(`scoring_pending`)로 보고한다. 빈칸을 추정하지 않는다. 확정된 문항만의 잠정값은 `잠정`을 붙여 따로 쓴다.
- 채점자 이름이 없는 채점값, 두 채점자가 다른데 최종값이 없는 문항은 미완료로 본다.

### 5. 실패 분석

- 처음 실패한 단계 하나로 분류한다 ([failure-taxonomy.md](references/failure-taxonomy.md)).
- 유형마다 대표 사례를 원본 기록(검색 후보, 재정렬 전후 순위, 답변, 인용)과 함께 남긴다.

### 6. 비교 보고서

- [report-template.md](references/report-template.md)로 `results/reports/`에 쓴다.
- 나빠진 결과도 원인과 함께 쓴다. 채택 판정은 하지 않는다 (오케스트레이터 몫).

## 금지

- 평가셋·잠금 파일 수정, `lock` 실행, 최종 평가 발주와 설정 고정 전 test 열람·해시 계산 및 `verify --split test`·`verify --split all` 실행
- 사람 채점 칸 채우기, LLM 판정 사용
- `src/`, 프롬프트, 체인 설정 수정
- 실패한 run 삭제, 좋은 재실행만 골라 보고
- 검색 점수를 답변의 사실성 확률처럼 표현
