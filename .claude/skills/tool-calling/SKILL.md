---
name: tool-calling
description: Use when writing or changing runtime tools the RAG agent calls (signatures, pydantic schemas, docstrings, LangChain binding, tool tests).
---

# tool-calling

LLM이 선택해 호출할 런타임 툴을 작성한다.
질문 유형별 처리 경로는 별도 라우터 없이 툴 docstring(description)으로 정한다.

## 현재 Solar handoff와의 경계

- `solar_handoff/src/cli.py`는 Solar 검색·답변 CLI이며 LangChain tool-calling 에이전트나 아래 8개 툴의 구현이 아니다. 집계·정렬·정확 조회를 벡터 검색으로 대체하지 않는다.
- 현재 검색·출처 경로는 `solar_handoff/src/{retrieval,providers,citations}.py`, 설정은 `solar_handoff/config/retrieval.json`이다. A/B/C, rewrite, GPT 전용 답변 및 출처 검증의 실제 계약과 실 실행 한계는 `langchain-rag` 스킬의 Solar handoff 섹션을 따른다.
- 아래의 데이터 로더·툴 목록과 검증은 향후 설계다. Solar CLI에 `search_pokedex`, `src/pokedex/store.py` 또는 정형 툴이 존재한다고 가정하지 않는다.

## 툴 목록 (1차 설계, 구현 예정)

| 툴 | 데이터 소스 | 용도 |
| --- | --- | --- |
| `resolve_name(name, kind)` | pokemon/moves/types.json + aliases | 한글/영문/별칭/오타 → id. kind = pokemon / move / type. 못 찾으면 후보 반환 |
| `get_pokemon(id)` | pokemon.json; 필요 시 evolutions_red_blue.json, encounters_red_blue.json | Red·Blue 기본 정보와 확인된 진화·획득 기록 |
| `get_move(id)` | moves.json | 기술 정보 (red-blue 값) |
| `get_learnset(pokemon_id, move_id?, method?)` | pokemon.json learnset + moves.json + machines_red_blue.json | Red·Blue 습득 방법·레벨, 기술 타입, 해당 시 TM/HM 번호 |
| `type_effectiveness(user, target, move)` | `BattleRules.calculate` | 상성 배율, 자속. 기존 코드 래핑 |
| `filter_pokemon(types, stat, op, value, sort_by, limit)` | pokemon.json | 집계, 필터, 순위 |
| `compare_pokemon(ids, fields)` | pokemon.json | 비교 |
| `search_pokedex(query, k, entity, pokemon_id, section, types)` | 설정된 검색 인덱스 | 서술형·설명형 질문에서 관련 청크 검색 |

- 향후 `search_pokedex`는 선택한 A(벡터), B(BM25+벡터), C(B+재정렬) 설정을 따른다. 해당 툴과 에이전트 연결은 예정이며, 별도 Solar CLI 구현과 혼동하지 않는다.
- 정렬·집계·정확 조회는 정규화 데이터로 푼다. 검색 방식 설정을 질문별 별도 라우터로 만들지 않는다.
- `get_pokemon`은 `pokemon.json`의 Red·Blue 기준 타입·종족치와, 필요한 경우 포켓몬 ID로 연결한 진화·획득 기록을 쓴다. 획득 기록은 Red와 Blue를 구분한다. 별도 보강 파일 `pokedex_extra.json`의 존재를 전제하지 않는다.
- `get_learnset`은 `version_group`이 `red-blue`인 습득 기록을 기준으로 한다. 기술 타입은 `moves.json`의 Red·Blue 값, 머신 번호는 같은 버전의 `machines_red_blue.json` 매핑에서 확인한다. 하나의 기술에 레벨업과 머신 기록이 있으면 두 방법을 유지한다.
- 버전 그룹이 `red-blue`라도 `method`를 확인한다. `level-up`·`machine` 외의 특수 경로는 별도로 표시하고, 검증 없이 Red·Blue 게임 내 일반 습득 경로라고 단정하지 않는다.
- 머신의 확인된 획득처는 `machine_acquisition_red_blue.json`을 머신 번호(`code`)로 연결한다. 정형 조회 인터페이스는 구현 전 확정한다. 확인된 경로만 반환하며 기록이 없거나 불완전하다고 해서 획득할 수 없다고 단정하지 않는다.
- 정제 데이터의 Red·Blue 필드라고 해서 모든 원본 검증이 끝난 것으로 보지 않는다. `data/source_manifest.json`의 현재 값 대체·원본 미확인 등 제한을 확인하고 검증 상태와 불확실성을 함께 전달한다.
- 진화·획득·머신 정제 파일의 레코드와 출처는 `data/source_manifest.json` 및 `data-normalize` 스킬에 따라 확인한다. 결합한 파일마다 `source_id`와 레코드 ID를 연결하고, JSON 포인터를 사용하면 실제 ID와 일치하는지 확인한다. 누락된 파일·연결·값은 미확인 또는 오류로 구분해 반환한다. 파일 존재와 전체 경로 완전성은 별개다.
- 상성 계산은 `scripts/gen1_battle/gen1_battle_rules.py`를 재사용한다. 이름 해석(`_resolve`)과 `resolve_name`의 규칙을 통일한다.
- 향후 런타임 데이터는 로더 모듈 `src/pokedex/store.py`(예정) 하나로만 읽는다. 로더는 `verify_bundle()`을 호출하되, 이 검사가 해시 고정 다섯 파일 외의 진화·획득·머신 파일을 검증한다고 가정하지 않는다.
- 검색의 `section`과 청크 출처는 `chunking` 스킬 및 확정된 청크 계약을 따른다. 포켓몬 Markdown의 주제별 청크와 근거 연결이 유지되게 한다.
- 검색 결과는 청크 본문·ID, 순위, 사용 가능한 점수와 선택된 검색 방식, 문서 및 상세 원본 근거로 연결되는 정보를 반환한다. 원본 근거를 찾지 못하면 확인 불가로 표시한다.

## 상성 계산 툴 계약 (구현 예정)

`type_effectiveness`는 `BattleRules.calculate()`를 래핑한다. 내부에서 `version='red-blue'`를 명시하고 입력 포켓몬·상대·기술을 전달한다. 계산기 결과의 버전, 대상 ID·타입, 기술 ID·타입·분류, `calculation` 상태와 아래 배율을 빠뜨리지 않는다.

| 계산기 `calculation` | 의미 | 툴의 처리 |
| --- | --- | --- |
| `basic_type_and_stab` | 일반 피해 기술의 기본 상성과 자속 계산 | `type_effectiveness`, `stab`, `combined_factor`, `per_type_effectiveness`, `type_immunity`를 계산기 결과 그대로 전달 |
| `not_applicable` | 해당 기술에 이 배율 계산을 적용하지 않음 | 상태와 배율 필드의 `null`을 유지 |
| `unsupported` | 해당 계산을 현재 지원하지 않음 | 상태와 배율 필드의 `null`을 유지하고 계산 결과를 만들어 내지 않음 |

- `null`은 미적용·미지원이지 배율 0이나 1이 아니다. 반대로 일반 피해 계산 결과의 실제 `0`은 `null`로 바꾸지 않는다.
- 계산 결과는 기본 타입 상성과 자속의 명목 배율이며 실제 피해량, 승패, 명중 여부나 모든 전투 효과가 아니다. `combined_factor`도 실제 피해량으로 표시하지 않는다.
- 계산기는 기술의 습득·현재 보유 여부를 검사하지 않는다. 해당 포켓몬이 기술을 사용할 수 있는지가 질문에 필요하면 `get_learnset`의 Red·Blue 기록을 별도로 확인하고, 미확인을 불가능으로 단정하지 않는다.
- 계산기 예외는 툴 계약의 오류 값으로 구분해 반환한다. 잘못된 이름·ID·타입·버전을 미지원 기술의 계산 결과로 바꾸지 않는다.
- 래퍼 구현 전에 입력 오류와 데이터 로딩·무결성 실패의 오류 코드·필드를 계약으로 확정하고, 계산기 예외와 래퍼의 오류 값을 각각 테스트한다.
- 답변에는 질문과 관련된 한계만 간결하게 설명한다. 이 내부 계약의 예외를 모든 포켓몬 문서나 일반 답변에 반복하지 않는다.

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
- Red·Blue 타입·종족치와 진화·포켓몬 획득 기록을 원본 정제 레코드와 대조한다. 미기록과 획득 불가를 구분한다.
- 레벨업과 TM/HM 습득 방법·기술 타입·머신 번호, 같은 기술의 복수 습득 방법을 정제 데이터와 대조한다. 특수 습득 경로와 머신 획득처의 부분 기록·누락도 검증한다.
- 고정 예시: `resolve_name("피카츄", "pokemon") == 25`, `filter_pokemon(types=["fire"], sort_by="attack", limit=1)`이 정규화 데이터에서 직접 계산한 값과 일치
- `type_effectiveness` 구현 후 일반 피해·무효 배율 0, 적용 대상 아님·미지원의 `null`, 잘못된 입력, `red-blue` 버전과 출처를 계산기 및 `tests/test_gen1_battle_rules.py`와 대조한다. 기술 습득 여부는 계산과 별도 검증한다.
- 툴 JSON Schema 스냅샷 테스트로 시그니처 변경 감지
- A/B/C 설정에 따른 결과 형식·청크 ID·출처, 빈 결과·중복과 재정렬 결과를 LLM 없이 검증한다. 동일 청크 집합과 B·C 후보 풀 확인은 `langchain-rag` 스킬을 따른다.
