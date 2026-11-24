---
name: tool-calling
description: Use when writing or changing runtime tools the RAG agent calls (signatures, pydantic schemas, docstrings, LangChain binding, tool tests).
---

# tool-calling

LLM이 선택해 호출할 런타임 툴을 작성한다.
질문 유형별 처리 경로는 별도 라우터 없이 툴 docstring(description)으로 정한다.

## 툴 목록 (1차)

| 툴 | 데이터 소스 | 용도 |
| --- | --- | --- |
| `resolve_name(name, kind)` | pokemon/moves/types.json + aliases | 한글/영문/별칭/오타 → id. kind = pokemon / move / type. 못 찾으면 후보 반환 |
| `get_pokemon(id)` | pokemon.json + pokedex_extra.json | 1세대 정보 (현재 값은 참고 필드) |
| `get_move(id)` | moves.json | 기술 정보 (red-blue 값) |
| `get_learnset(pokemon_id, move_id?, method?)` | pokemon.json learnset | 배우는 기술, 레벨 |
| `type_effectiveness(user, target, move)` | `BattleRules.calculate` | 상성 배율, 자속. 기존 코드 래핑 |
| `filter_pokemon(types, stat, op, value, sort_by, limit)` | pokemon.json | 집계, 필터, 순위 |
| `compare_pokemon(ids, fields)` | pokemon.json | 비교 |
| `search_pokedex(query, k, entity, pokemon_id, section, types)` | 벡터 DB | 서술형·설명형 질문 |

- 벡터 DB는 `search_pokedex`만 쓴다. 정렬·집계·정확 조회는 정규화 데이터로 푼다.
- 상성 계산은 `scripts/gen1_battle/gen1_battle_rules.py`를 재사용한다. 이름 해석(`_resolve`)과 `resolve_name`의 규칙을 통일한다.
- 데이터는 로더 모듈 `src/pokedex/store.py` 하나로만 읽는다. 로더는 `verify_bundle()`을 호출한다.

## 작성 규칙

1. 인자는 pydantic 모델. enum(타입, 섹션, 스탯)은 계약 파일의 허용값을 쓴다.
2. docstring = LLM이 읽는 툴 설명. "언제 쓰는가"와 "언제 쓰지 않는가"를 쓴다.
   예: `filter_pokemon` — "조건에 맞는 포켓몬 목록이나 순위가 필요할 때. 한 마리의 정보는 get_pokemon을 쓴다."
3. 반환은 JSON 직렬화 가능한 dict. 출처(`pokemon_id`, `move_id`, `chunk_id`)를 포함한다.
4. 에러는 예외 대신 값으로 반환: `{"error": "not_found", "candidates": [...]}`.
5. 같은 입력·같은 데이터 버전이면 같은 출력.
6. LangChain 연결은 `@tool` / `StructuredTool` + `bind_tools`.

## 검증 (LLM 없이)

- 툴별 단위 테스트: 정상 입력, 없는 대상, 오타, 빈 결과
- 고정 예시: `resolve_name("피카츄", "pokemon") == 25`, `filter_pokemon(types=["fire"], sort_by="attack", limit=1)`이 정규화 데이터에서 직접 계산한 값과 일치
- `type_effectiveness`가 `tests/test_gen1_battle_rules.py`와 결과 일치
- 툴 JSON Schema 스냅샷 테스트로 시그니처 변경 감지
