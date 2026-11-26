# 멀티모델 독립 검색 채점

3개 문서 검색 전용 파일럿. A/B는 청킹 방식이며 정식 검색 방식 A/B가 아니다. 완전 적중은 모든 앵커를 발견한 경우다. MRR@5는 앵커별 최초 순위의 최댓값의 역수 평균(미스 0), 분모 14. 모델 간 유사도 점수는 직접 비교하지 않는다. 답변 품질·거절·사람 승인 평가가 아니다.

| 모델 | 청크 | Hit@1 | Hit@3 | Hit@5 | MRR@5 | 부분만 @5 |
|---|---|---:|---:|---:|---:|---:|
| gemma | A | 8/14 | 12/14 | 14/14 | 0.734524 | 0/14 |
| gemma | B | 8/14 | 11/14 | 13/14 | 0.702381 | 0/14 |
| kure | A | 12/14 | 14/14 | 14/14 | 0.928571 | 0/14 |
| kure | B | 8/14 | 13/14 | 14/14 | 0.755952 | 0/14 |
| openai | A | 7/14 | 10/14 | 13/14 | 0.645238 | 0/14 |
| openai | B | 6/14 | 10/14 | 10/14 | 0.535714 | 1/14 |

## 문항별 완전 순위 및 변화

— = 미스; 변화는 1–5, 미스=6 기준. B/A Hit@5는 각 모델별로 별도 표시.

| qid | Gemma A/B | KURE A/B | OpenAI A/B | KURE vs Gemma A/B | OpenAI vs Gemma A/B | B vs A (Gemma/KURE/OpenAI) | Hit@5 A/B (Gemma/KURE/OpenAI) |
|---|---|---|---|---|---|---|---|
| CP01 | 1/2 | 1/2 | —/3 | unchanged/unchanged | regressed/regressed | regressed/regressed/improved | ✓✓ / ✓✓ / ×✓ |
| CP02 | 1/1 | 1/2 | 4/1 | unchanged/regressed | regressed/unchanged | unchanged/regressed/improved | ✓✓ / ✓✓ / ✓✓ |
| CP03 | 2/4 | 2/2 | 5/— | unchanged/improved | regressed/regressed | regressed/unchanged/regressed | ✓✓ / ✓✓ / ✓× |
| CP04 | 1/1 | 1/1 | 1/1 | unchanged/unchanged | unchanged/unchanged | unchanged/unchanged/unchanged | ✓✓ / ✓✓ / ✓✓ |
| CP05 | 2/2 | 1/1 | 4/3 | improved/improved | regressed/regressed | unchanged/unchanged/improved | ✓✓ / ✓✓ / ✓✓ |
| CP06 | 2/1 | 1/4 | 1/1 | improved/regressed | improved/unchanged | improved/regressed/unchanged | ✓✓ / ✓✓ / ✓✓ |
| CP07 | 1/1 | 1/1 | 1/1 | unchanged/unchanged | unchanged/unchanged | unchanged/unchanged/unchanged | ✓✓ / ✓✓ / ✓✓ |
| CP08 | 1/1 | 1/1 | 1/1 | unchanged/unchanged | unchanged/unchanged | unchanged/unchanged/unchanged | ✓✓ / ✓✓ / ✓✓ |
| CP09 | 4/— | 1/2 | 1/— | improved/improved | improved/unchanged | regressed/regressed/regressed | ✓× / ✓✓ / ✓× |
| CP10 | 1/4 | 1/1 | 1/2 | unchanged/improved | unchanged/improved | regressed/unchanged/regressed | ✓✓ / ✓✓ / ✓✓ |
| CP11 | 5/1 | 1/1 | 1/1 | improved/unchanged | improved/unchanged | improved/unchanged/unchanged | ✓✓ / ✓✓ / ✓✓ |
| CP12 | 1/1 | 1/1 | 3/— | unchanged/unchanged | regressed/regressed | unchanged/unchanged/regressed | ✓✓ / ✓✓ / ✓× |
| CP13 | 3/3 | 2/3 | 2/3 | improved/unchanged | improved/unchanged | unchanged/regressed/regressed | ✓✓ / ✓✓ / ✓✓ |
| CP14 | 1/1 | 1/1 | 2/— | unchanged/unchanged | regressed/regressed | unchanged/unchanged/regressed | ✓✓ / ✓✓ / ✓× |

## 범위 밖 CP15

완전 적중 분모에서 제외. 검색 결과는 JSON에 별도 보존하며 거절 성공을 평가하지 않는다.

입력 해시, 실제 설정, 앵커와 후보 및 순위별 연결은 같은 디렉터리의 score.json에 기록한다. 실행 진위·모델 서버 내부 변환 또는 잘림은 해시만으로 입증할 수 없다.
