---
name: tool-calling
description: Use when changing Solar conversation tools or designing future LangChain tools and their tests.
---

# tool-calling

LLM이 선택해 호출할 런타임 툴을 작성한다.
질문 유형별 처리 경로는 별도 라우터 없이 툴 docstring(description)으로 정한다.

## 현재 Solar 대화 도구

[`conversation.py`](../../../solar_handoff/src/conversation.py)는 같은 설정의 GPT에 읽기 전용 Responses 함수 도구 네 개를 등록한다. 별도 질문 라우터나 LangChain 바인딩은 없다. [`cli.py`](../../../solar_handoff/src/cli.py)는 도구 선택 없는 기존 단일 질문 검색 경로다. A/B/C 후보와 대화 호출 흐름은 [langchain-rag](../langchain-rag/SKILL.md)를 따른다.

| 도구 | 함수 인수 | 사용 범위 |
| --- | --- | --- |
| `search_pokedex` | `{}` (인수 없음) | 기본 정보·스탯·습득·획득 등 일반 도감 검색. 여러 포켓몬의 개별 정보를 묻는 질문도 포함한다. 모델은 `query`, `k`, 필터를 넘기지 않고 서버가 원질문과 대화 이력으로 검색어를 만든다. |
| `analyze_team_defense` | `intent`, `members`, `replace_member`, `candidate` | 확인된 현재 팀의 방어 상성 진단(`analyze`), 빈자리 추가(`add`), 교체(`replace`). `members`는 현재 팀원 이름만 받는다. `replace_member`와 `candidate` 키는 필수지만 지정되지 않은 값은 `null`이다. |
| `find_move_weaknesses` | `move` | 특정 기술 이름으로 Red·Blue 피해 분류와 기본 방어 상성을 확인한다. 포켓몬의 기술 습득 여부나 실제 HP 피해량은 다루지 않는다. |
| `clarify_pokedex_question` | `reason` | 명단·교체 대상·후보·기술·지칭 대상이 모호하면 확인한다. 허용된 사유만 받고 자유 문장 대신 서버의 정해진 문구를 반환한다. |

- 함수 정의와 Pydantic 입력 모델은 [`src/pokedex/tools/__init__.py`](../../../src/pokedex/tools/__init__.py)가 원본이다. `strict: true`, `additionalProperties: false`, `tool_choice: required`, `parallel_tool_calls: false`를 사용한다. 서버는 완료된 GPT 응답의 등록된 단일 호출, 중복 키 없는 JSON, 인수 스키마를 검사한다. 잘못된 호출 형식이나 결과가 불명인 실패를 다른 경로로 우회하거나 자동 재시도하지 않는다.
- 정형 도구의 데이터 읽기는 [`src/pokedex/store.py`](../../../src/pokedex/store.py) 한 곳에 둔다. `BattleRules`를 통해 루트의 해시 고정 5개 파일을 검증하고 이름·별명과 Red·Blue 상성표를 사용한다. 이 검증은 별도 진화·획득·머신 데이터까지 포함하지 않는다.
- 이름의 정규화된 정확 일치로 ID를 확인한다. 다른 ID의 더 긴 정상 이름에 포함된 부분은 독립 언급이 아니다(예: `피죤투` 속 `피죤`, `몸통박치기` 속 `박치기`). 조사가 붙은 정확한 이름, 두 이름이 각각 언급된 경우, 이전 대화의 명시적인 참조는 유지한다. 모델은 현재 팀원과 상대·후보를 구분하고, 서버는 이름의 언급 여부를 검사한다. 팀원 이름은 사용자 발화에서 확인하되, 사용자나 모델의 진술을 사실 근거로 쓰지 않는다. 없는 이름·중복 팀원·불명확한 대상은 추측하지 않고 묻는다.

### 정형 조회·계산과 근거

- **팀:** 공격 타입별로 약점(1배 초과)과 저항·무효(1배 미만)를 집계한다. 약점은 있지만 저항·무효 팀원이 없는 타입을 보완 대상으로 보고 반복 약점을 우선한다. 추천은 기존 팀원을 제외하고 새 방어 공백·늘어나는 약점을 고려한 최대 세 대안이다. 여섯 마리 팀에 추가를 요청하면 일곱 번째를 권하지 않고 교체 대상을 확인한다. 팀원마다 `pokemon:{id}#profile`, `pokemon:{id}#defense_matchup`을, 후보는 `pokemon:{id}#defense_matchup`을 정확한 ID로 찾는다.
- **기술:** `moves.json`의 Red·Blue 타입과 피해 분류 레코드를 기술 ID로 연결한다. 일반 피해(`regular_damage`)만 151마리에서 해당 타입의 방어 배율이 1배를 넘는 대상을 찾아 배율별로 묶고 각 대상의 `defense_matchup`을 연결한다. 변화기(`status`)는 직접 피해가 없으며 확인된 효과만 말한다(망각술: 사용자 특수 2단계 상승). 별도 피해(`special_damage`, 예: 지구던지기의 `user_level`) 및 분류 미확정(`unknown`)도 일반 배율을 만들지 않는다. 이때 집계의 `null`은 대상이 0마리라는 뜻이 아니다. 타입 배율은 실제 HP 피해·기술 습득·승패를 증명하지 않는다.
- **근거 전달:** 정형 경로에서 질의 임베딩, BM25, 벡터 검색, 재작성, 재순위화를 호출하지 않는다. 필요한 경우에만 기존 DB 청크를 읽어 ID와 등록 문서를 확인한다. 필수 청크 누락이나 컨텍스트 한도 초과를 조용히 잘라 답하지 않는다. 기술 분류는 검증된 `move:{id}`와 정제 파일의 레코드 위치를 답변 본문에 표시한다. 습득표는 분류 근거가 아니며 기술 ID를 HTTP 포켓몬 번호 출처에 넣지 않는다.

현재 검증은 [`test_pokedex_structured_tools.py`](../../../tests/test_pokedex_structured_tools.py)의 결정적 계산·근거 검사와 [`test_solar_tool_provider.py`](../../../tests/test_solar_tool_provider.py)의 가짜 Responses·인메모리 청크 회귀다. 실 GPT 선택의 정확성이나 공식 평가를 증명하지 않는다.

## 향후 LangChain 툴 목록 (1차 설계, 구현 예정)

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

- 향후 `search_pokedex(query, k, entity, pokemon_id, section, types)`는 선택한 A(벡터), B(BM25+벡터), C(B+재정렬) 설정을 따르는 계획이다. 표의 시그니처와 LangChain 연결은 미구현이다. 현재 Solar 대화의 무인수 `search_pokedex`와 같지 않으며 Solar CLI에도 붙지 않는다.
- 정렬·집계·정확 조회는 정규화 데이터로 푼다. 검색 방식 설정을 질문별 별도 라우터로 만들지 않는다.
- `get_pokemon`은 `pokemon.json`의 Red·Blue 기준 타입·종족치와, 필요한 경우 포켓몬 ID로 연결한 진화·획득 기록을 쓴다. 획득 기록은 Red와 Blue를 구분한다. 별도 보강 파일 `pokedex_extra.json`의 존재를 전제하지 않는다.
- `get_learnset`은 `version_group`이 `red-blue`인 습득 기록을 기준으로 한다. 기술 타입은 `moves.json`의 Red·Blue 값, 머신 번호는 같은 버전의 `machines_red_blue.json` 매핑에서 확인한다. 하나의 기술에 레벨업과 머신 기록이 있으면 두 방법을 유지한다.
- 버전 그룹이 `red-blue`라도 `method`를 확인한다. `level-up`·`machine` 외의 특수 경로는 별도로 표시하고, 검증 없이 Red·Blue 게임 내 일반 습득 경로라고 단정하지 않는다.
- 머신의 확인된 획득처는 `machine_acquisition_red_blue.json`을 머신 번호(`code`)로 연결한다. 정형 조회 인터페이스는 구현 전 확정한다. 확인된 경로만 반환하며 기록이 없거나 불완전하다고 해서 획득할 수 없다고 단정하지 않는다.
- 정제 데이터의 Red·Blue 필드라고 해서 모든 원본 검증이 끝난 것으로 보지 않는다. `data/source_manifest.json`의 현재 값 대체·원본 미확인 등 제한을 확인하고 검증 상태와 불확실성을 함께 전달한다.
- 진화·획득·머신 정제 파일의 레코드와 출처는 `data/source_manifest.json` 및 `data-normalize` 스킬에 따라 확인한다. 결합한 파일마다 `source_id`와 레코드 ID를 연결하고, JSON 포인터를 사용하면 실제 ID와 일치하는지 확인한다. 누락된 파일·연결·값은 미확인 또는 오류로 구분해 반환한다. 파일 존재와 전체 경로 완전성은 별개다.
- 상성 계산은 `scripts/gen1_battle/gen1_battle_rules.py`를 재사용한다. 이름 해석(`_resolve`)과 `resolve_name`의 규칙을 통일한다.
- 향후 툴도 현재 정형 조회에 쓰는 단일 로더 `src/pokedex/store.py`를 확장해 사용하고, 추가 데이터는 해당 파일의 출처·검증 규칙을 따로 확인한다.
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
4. 사용자 확인으로 풀 수 있는 입력 문제는 값으로 반환한다. 현재 정형 도구의 `clarification_required`와 잘못된 함수 호출·데이터 무결성 실패를 구분한다.
5. 같은 입력·같은 데이터 버전이면 같은 출력.
6. 현재 Solar 대화는 Responses 함수 등록을 사용한다. `@tool` / `StructuredTool` + `bind_tools`는 향후 LangChain 계획이다.

## 향후 LangChain 검증 (LLM 없이)

- 툴별 단위 테스트: 정상 입력, 없는 대상, 오타, 빈 결과
- Red·Blue 타입·종족치와 진화·포켓몬 획득 기록을 원본 정제 레코드와 대조한다. 미기록과 획득 불가를 구분한다.
- 레벨업과 TM/HM 습득 방법·기술 타입·머신 번호, 같은 기술의 복수 습득 방법을 정제 데이터와 대조한다. 특수 습득 경로와 머신 획득처의 부분 기록·누락도 검증한다.
- 고정 예시: `resolve_name("피카츄", "pokemon") == 25`, `filter_pokemon(types=["fire"], sort_by="attack", limit=1)`이 정규화 데이터에서 직접 계산한 값과 일치
- `type_effectiveness` 구현 후 일반 피해·무효 배율 0, 적용 대상 아님·미지원의 `null`, 잘못된 입력, `red-blue` 버전과 출처를 계산기 및 `tests/test_gen1_battle_rules.py`와 대조한다. 기술 습득 여부는 계산과 별도 검증한다.
- 툴 JSON Schema 스냅샷 테스트로 시그니처 변경 감지
- A/B/C 설정에 따른 결과 형식·청크 ID·출처, 빈 결과·중복과 재정렬 결과를 LLM 없이 검증한다. 동일 청크 집합과 B·C 후보 풀 확인은 `langchain-rag` 스킬을 따른다.
