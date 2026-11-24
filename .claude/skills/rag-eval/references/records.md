# 실행 기록 (results/)

원본 기록은 추가만 한다. 실패한 run도 지우지 않는다. `results/`는 제출물이므로 커밋한다.

## 디렉터리

```
results/
  {run_id}/
    run.json        실행 조건
    records.jsonl   문항별 원본 기록
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
| `warmup` | 연결 확인, 캐시 예열 | X |
| `retry` | 호출 오류 재시도 | X (따로 보고) |
| `extra` | 최종 결과를 본 뒤 한 추가 실험 | X (본 평가와 분리) |

## run.json

```json
{
  "run_id": "20261127-1030_final_C",
  "kind": "final",
  "config": "C",
  "split": "test",
  "evalset": {"label": "test-v1", "sha256": "..."},
  "chunks_sha256": "...",
  "index_version": "v1-te3s-tpl1",
  "models": {"chat": "gpt-6-luna", "embedding": "text-embedding-3-small", "reranker": "...", "rewriter": null},
  "prompt_version": "...",
  "retrieval": {"k": 5, "vector_candidates": 20, "bm25_candidates": 20, "fusion": "rrf", "rrf_k": 60, "dedupe": "chunk_id", "rerank_in": 20, "rerank_out": 5},
  "generation": {"max_output_tokens": 0, "max_context_chunks": 5, "max_context_chars": 0, "params": {}},
  "config_hash": "...",
  "git_commit": "...",
  "started_at": "...", "finished_at": "..."
}
```

## records.jsonl (문항당 한 줄)

```json
{
  "run_id": "...", "qid": "T01", "attempt": 1,
  "question": "...", "rewritten_query": null, "rewrite_fallback": false,
  "candidates": {
    "vector": [{"chunk_id": "...", "score": 0.0, "rank": 1}],
    "bm25":   [{"chunk_id": "...", "score": 0.0, "rank": 1}],
    "fused":  [{"chunk_id": "...", "score": 0.0, "rank": 1}],
    "reranked": [{"chunk_id": "...", "score": 0.0, "rank": 1, "rank_before": 3}]
  },
  "final_results": ["chunk_id", "..."],
  "evidence": [{"chunk_id": "...", "doc_id": "...", "source_loc": "..."}],
  "answer": "...",
  "citations": ["chunk_id"],
  "status": "ok | no_evidence | error | timeout",
  "error": null,
  "timing_ms": {"rewrite": 0, "retrieval": 0, "rerank": 0, "generation": 0, "total": 0}
}
```

- `status=no_evidence`는 체인이 정상적으로 "정보 부족"을 판단한 경우다. 호출 실패는 `error` / `timeout`이다.
- 해당 구성에 없는 단계는 빈 목록이나 `null`로 둔다.

## scores.csv

| 열 | 채우는 쪽 |
| --- | --- |
| `run_id, qid, type, subtype, status` | 에이전트 |
| `hit5, citation_in_results, n_final_results, total_ms` | 에이전트 (자동) |
| `answer_ok_r1, answer_ok_r2, answer_ok` | 사람 |
| `support_ok_r1, support_ok_r2, support_ok` | 사람 (근거가 주장을 뒷받침하는가) |
| `refusal_ok_r1, refusal_ok_r2, refusal_ok` | 사람 (근거 없음 문항만) |
| `reviewer1, reviewer2, note` | 사람 |

근거 적합 = `citation_in_results` AND `support_ok`. 집계는 에이전트가 한다.
