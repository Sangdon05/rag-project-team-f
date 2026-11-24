# 평가셋 (eval/)

평가셋은 **사용자(팀원)만 작성·수정한다.** 에이전트는 읽고 검증해서 의견서를 낼 수 있지만, 파일을 만들거나 고치지 않는다.

| 파일 | 작성 | 내용 |
| --- | --- | --- |
| `dev.json` | 사용자 | 개발용 10문항 (답변 가능 8, 근거 없음 2) |
| `test.json` | 사용자 | 최종 평가용 20문항 (직접 검색 10, 표현 변형·유사 조건 구분 7, 근거 없음 3) |
| `LOCK.json` | 사용자 (`lock` 명령) | 평가셋·청크 파일 해시 |
| `feedback/` | eval 에이전트 | 평가셋 의견서 |

## 규칙

- `test.json`은 최종 평가 전까지 개발·튜닝에 쓰지 않는다. rag-developer는 `eval/`을 읽지 않는다.
- 정답·허용 근거를 프롬프트, few-shot, 쿼리 리라이터 입력, 검색 문서에 넣지 않는다. `eval/`은 색인 대상이 아니다.
- 평가셋을 확정하면 잠근다. 평가 실행기는 잠금과 해시가 다르면 실행하지 않는다.

  ```bash
  uv run python scripts/eval/evalset_lock.py lock --split dev --chunks data/chunks/chunks.jsonl   # label = 파일의 version
  uv run python scripts/eval/evalset_lock.py verify --split dev --chunks data/chunks/chunks.jsonl
  ```

- 청킹이 바뀌어 청크 ID가 달라지면 `verify --chunks`가 실패한다. 근거 매핑(`allowed_evidence`)을 갱신하고 다시 잠근다.
- 최종 평가 결과를 본 뒤 질문을 바꾸거나 빼지 않는다.

## 문항 스키마

파일 형식: `{"version": "dev-v1", "items": [ ... ]}`. `version`이 평가셋 버전의 유일한 값이며, 잠금 label도 이 값을 쓴다. 내용을 바꾸면 version도 올린다.

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `qid` | O | 고유 ID. dev `D01`~`D10`, test `T01`~`T20` |
| `split` | O | `dev` / `test` |
| `type` | O | dev: `answerable` / `no_evidence`. test: `direct` / `variation` / `no_evidence` |
| `subtype` | | `variation`일 때 `paraphrase`(표현 변형) / `confusable`(유사 조건 구분) |
| `question` | O | 질문 원문 |
| `key_facts` | 답변 가능 | 정답 충족 채점 단위. 모두 맞고 모순이 없어야 정답 |
| `allowed_evidence` | 답변 가능 | 허용 근거 목록: `{"document_id", "chunk_id", "source_loc"}` (청크 메타데이터와 같은 이름, chunking 스킬). 하나라도 상위 5개에 있으면 Hit |
| `confusable_with` | | 혼동되기 쉬운 근거 (chunk_id 목록). `confusable` 문항에는 권장 |
| `no_evidence_reason` | 근거 없음 | 근거가 없다고 판단한 이유. 이 문항은 `allowed_evidence`를 비운다 |
| `note` | | 작성자 메모 |

근거 없음 문항의 기대 답변은 "정보 부족 안내"다.

예시 (형식 설명용, 실제 문항 아님):

```json
{
  "qid": "D01",
  "split": "dev",
  "type": "answerable",
  "question": "이상해씨의 스피드 종족치는?",
  "key_facts": ["스피드 45"],
  "allowed_evidence": [
    {"document_id": "pokemon:1", "chunk_id": "pokemon:1#stats", "source_loc": "data/synthetic/pilot/bulbasaur_red_blue_plain.md#종족치"}
  ],
  "confusable_with": []
}
```

평가 절차·지표·기록 형식은 [rag-eval 스킬](../.claude/skills/rag-eval/SKILL.md)을 따른다.

eval 도입에 따라 다른 에이전트·스킬에 필요한 수정은 [후속 수정 요청](../docs/proposals/eval-agent-followups.md)에 정리했다 (미반영).
