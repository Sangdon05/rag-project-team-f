---
name: langchain-rag
description: Use when building or changing the LangChain QA agent chain, system prompt, retriever settings, or trace logging.
---

# langchain-rag

툴을 쓰는 질의응답 에이전트 체인과 프롬프트를 만든다.

## 구성

- tool-calling 에이전트 1개 + `tool-calling` 스킬의 툴 8개. 별도 라우터 체인은 두지 않는다.
- 권장 흐름: 특정 포켓몬·기술 질문 → `resolve_name` → `get_*` 또는 `search_pokedex(pokemon_id=…)`. 상성 질문 → `type_effectiveness`.
- retriever 설정(k, 필터 조합, MMR)은 이 스킬 소유다. 코드가 아닌 config 파일로 둔다.

## 시스템 프롬프트 규칙

1. 툴 결과에 있는 내용으로만 답한다.
2. 답에 출처(`pokemon_id` / `move_id` / `chunk_id`)를 붙인다.
3. 1세대 Red/Blue 기준으로 답한다. 현재 값과 다르면 "현재 세대에서는 …"으로 병기한다.
4. 근거가 없거나 범위(1~151번) 밖이면 모른다고 답한다.
5. 수치는 정규화 단위(m, kg) 그대로 쓴다.

## 재현성

- temperature 0, 모델명·버전 고정
- 실행마다 config 스냅샷 해시와 사용한 `index_version`을 기록

## 트레이스 로깅 (필수)

질문마다 JSONL 한 줄. Eval의 실패 분석이 이 로그에 의존한다.

```json
{"qid": "...", "question": "...", "index_version": "...", "config_hash": "...",
 "tool_calls": [{"name": "...", "args": {}, "result": {}}],
 "answer": "...", "citations": ["pokemon:25#stats"], "latency_ms": 0, "tokens": {}}
```

## 검증

- 질문 유형별 1개 이상 실행: 단일 사실, 기술/습득, 상성, 비교, 집계, 서술형, 범위 밖
- 모든 답변에 출처 포함, 트레이스 로그 생성 확인
- 품질 판정은 하지 않는다 (Eval 담당)
