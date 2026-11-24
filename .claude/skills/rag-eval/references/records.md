# 실행 기록 (results/)

원본 기록은 추가만 한다. 실패한 run도 지우지 않는다. `results/`는 제출물이므로 커밋한다.

문항별 원본은 **langchain-rag 스킬의 트레이스**다. eval은 트레이스 형식을 정하지 않고, 받은 트레이스를 바꾸지 않고 저장한 뒤 채점표를 만든다. 트레이스 형식이 바뀌면 이 문서의 "트레이스에서 읽는 필드"를 맞춘다.

## 디렉터리

```
results/
  {run_id}/
    run.json        실행 조건
    traces.jsonl    문항별 트레이스 원본 (langchain-rag 형식 그대로)
    scores.csv      채점표 (자동 칸 + 사람 칸)
    summary.md      집계 결과 (사람 채점 완료 후)
  reports/          비교 보고서
```

## run_id와 종류

`{YYYYMMDD-HHMM}_{kind}_{config}` 예: `20261127-1030_final_C`

| kind | 뜻 | 최종 지표 포함 |
| --- | --- | --- |
| `dev` | 개발 평가 (dev 10) | X |
| `final` | 최종 평가 기본 60건 (A/B/C 각 1 run) | O |
| `rewrite` | 최종 평가 분기 20건 (C+RW) | O (분기로 따로 보고) |
| `warmup` | 연결 확인 | X |
| `retry` | 호출 오류 재시도 | X (따로 보고) |
| `extra` | 최종 결과를 본 뒤 한 추가 실험 | X (본 평가와 분리) |

## run.json

실행 조건 전체. 트레이스의 `config_hash`가 가리키는 config 스냅샷을 함께 둔다.

```json
{
  "run_id": "20261127-1030_final_C",
  "kind": "final",
  "config": "C",
  "rewrite": false,
  "split": "test",
  "evalset": {"label": "test-v1", "sha256": "..."},
  "chunks_sha256": "...",
  "index_version": "...",
  "config_hash": "...",
  "config_snapshot": {},
  "models": {"chat": "gpt-6-luna", "embedding": "text-embedding-3-small", "reranker": null, "rewriter": null},
  "git_commit": "...",
  "started_at": "...", "finished_at": "..."
}
```

해당하지 않는 모델은 `null`로 명시한다 (langchain-rag 재현성 규칙과 같다).

## 트레이스에서 읽는 필드

| 트레이스 필드 | eval 용도 |
| --- | --- |
| `qid`, `question` | 문항 매칭 |
| `index_version`, `config_hash` | run.json과 일치 확인 (다르면 해당 문항 무효로 보고) |
| `retrieval.method` | 구성(A/B/C) 확인 |
| `retrieval.called` | `false`면 검색 미호출. Hit@5 = 0, `retrieval_not_called` 표시 |
| `retrieval.final` | Hit@5 계산 (상위 5개의 chunk_id) |
| `retrieval.pre_rerank` | 검색 누락과 순위 실패 구분, 재정렬 전후 순위 |
| `retrieval.latency_ms`, `latency_ms` | 검색 시간, 전체 응답 시간 |
| `tool_calls` | 툴 경로 사용 여부 (실패 분석 참고) |
| `answer`, `citations` | 사람 채점 자료, 인용 존재 확인 |
| `tokens` | 비용 보조 지표 |

### 트레이스에 아직 없는 필드 (요청 사항)

발제 지표에 필요하지만 현재 langchain-rag 트레이스 예시에 없는 것. 없으면 해당 칸은 `unknown`으로 두고 추정하지 않는다.

| 필요 | 이유 |
| --- | --- |
| 상태 (`ok` / `no_evidence` / `error` / `timeout`)와 오류 내용 | 호출 오류를 올바른 거절로 세지 않기 위해 (근거 없음 대응, 호출 성공률) |
| 리라이트 원문·결과·fallback 여부, 리라이트 시간 | C+RW 검증 (원질문·변환 질의 저장 의무) |
| `final` 항목의 `document_id`, 원문 위치 | 인용 근거 확인, 사람 채점 자료 |

## scores.csv

| 열 | 채우는 쪽 |
| --- | --- |
| `run_id, qid, type, subtype` | 에이전트 |
| `status, retrieval_called, hit5, citation_in_results, n_final_results, total_ms` | 에이전트 (트레이스에서 자동) |
| `answer_ok_r1, answer_ok_r2, answer_ok` | 사람 |
| `support_ok_r1, support_ok_r2, support_ok` | 사람 (근거가 주장을 뒷받침하는가) |
| `refusal_ok_r1, refusal_ok_r2, refusal_ok` | 사람 (근거 없음 문항만) |
| `reviewer1, reviewer2, note` | 사람 |

- `citation_in_results`: `citations`가 모두 `retrieval.final`에 있으면 1. 검색 미호출이면 0.
- 근거 적합 = `citation_in_results` AND `support_ok`. 집계는 에이전트가 한다.
