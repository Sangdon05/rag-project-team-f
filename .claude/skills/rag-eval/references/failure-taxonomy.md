# 실패 분석

문항마다 **처음 실패한 단계 하나**로 분류한다. 아래 순서대로 확인하고, 처음 해당하는 유형을 쓴다.

| 순서 | 유형 | 판정 기준 (records.jsonl) | 넘길 곳 |
| --- | --- | --- | --- |
| 1 | 호출 오류 | `status`가 `error` / `timeout` | rag-developer (재시도·timeout·예외 처리) |
| 2 | 검색 누락 | 허용 근거가 어떤 후보 목록(vector, bm25, fused)에도 없음 | data-engineer (청킹·텍스트 템플릿·임베딩) 또는 rag-developer (후보 수, 리라이트) |
| 3 | 순위 실패 | 후보에는 있으나 최종 상위 5개 밖 (결합·재정렬에서 밀림) | rag-developer (RRF 설정, reranker, 출력 k) |
| 4 | 근거 선택 실패 | 상위 5개에는 있으나 답변 근거로 쓰이지 않음 | rag-developer (근거 선택·컨텍스트 구성) |
| 5 | 생성 오류 | 근거는 맞는데 `answer_ok = 0` (누락, 모순, 세대 혼동) | rag-developer (프롬프트) |
| 6 | 잘못된 인용 | 답은 맞으나 `support_ok = 0` 또는 `citation_in_results = 0` | rag-developer (인용 규칙·검증) |
| 7 | 근거 없음 대응 실패 | 근거 없음 문항에 단정해서 답함, 또는 답변 가능 문항에서 근거가 있는데 정보 부족으로 답함(과잉 거절) | rag-developer (근거 부족 판정 기준, dev로만 조정) |
| - | 정답표 의심 | 원본 기록과 `data/processed/`로 볼 때 `key_facts`나 `allowed_evidence`가 틀려 보임 | 사용자 (의견서) — 에이전트는 고치지 않는다 |

- confusable 문항은 혼동 근거(`confusable_with`)를 고른 것인지 함께 적는다.
- 리라이트 구성은 리라이트로 의도가 바뀌어 실패한 경우를 "검색 누락"이 아니라 별도 메모(`rewrite_drift`)로 표시한다.

## 재현

- 재현 명령: run_id와 qid 목록을 받아 같은 조건(run.json)으로 다시 실행할 수 있어야 한다.
- dev에서만 3회 반복으로 불안정 실패를 구분한다. 3회 중 결과가 갈리면 `unstable`로 표시한다.
- 최종 평가는 1회 실행이 기준이다. 반복 결과로 최종 수치를 대체하지 않는다.
- 생성 파라미터(temperature 또는 reasoning effort, seed)는 run.json에 기록한다. 모델이 temperature를 받지 않으면 지원하는 파라미터로 고정한다.

## 보고 단위

```
qid | config | 유형 | 근거 (후보 순위, 인용, 답변 발췌) | 넘길 곳 | unstable 여부
```

유형별 건수표와 대표 사례(유형마다 1~2건)를 비교 보고서에 넣는다.
