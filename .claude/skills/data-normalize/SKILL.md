---
name: data-normalize
description: Use when adding or changing normalized Pokémon data (fields, species info, units, gen1 values). Extends data/processed without touching hash-pinned files.
---

# data-normalize

RAG에 필요한 정규화 데이터를 갖추고 검증한다.

## 기준 데이터 (수정 금지)

`data/processed/` — 1세대 Red/Blue 기준. `scripts/gen1_battle/data_integrity.py`가 SHA-256으로 고정한다.

| 파일 | 내용 |
| --- | --- |
| pokemon.json | 151마리. name_ko, types_gen1/current, stats_gen1/current, learnset |
| moves.json | 165개 기술. name_ko, 버전별 위력/명중/PP/타입 |
| types.json | 1세대 15개 타입, name_ko |
| type_chart.json | 1세대 상성표 |
| red_blue_move_damage_classification.json | 기술 물리/특수 분류 |

이 파일을 수정하면 `BattleRules` 로딩이 실패한다. 값을 바꿔야 하면 파일과 `HASHES`를 함께 갱신하는 별도 PR로 처리하고 오케스트레이터에 보고한다.

## 보강 대상

| 필드 | 출처 | 용도 |
| --- | --- | --- |
| height_m, weight_kg | PokeAPI `/pokemon/{id}` (dm/10, hg/10) | 프로필 질문 |
| genus_ko | PokeAPI `/pokemon-species/{id}` genera (ko) | 분류 ("쥐포켓몬") |
| flavor_text_ko | PokeAPI `/pokemon-species/{id}` flavor_text_entries (ko) | 서술형 질문 |
| evolution | PokeAPI `/pokemon-species/{id}` + evolution_chain | 진화 질문 |
| aliases | 수동 테이블 | 이름 해석 (별칭, 오타) |

보강 데이터는 `scripts/helper/build_pokedex_extra.py`(예정)가 PokeAPI를 직접 호출해 만든다. 중간 원본 파일은 저장소에 두지 않고, 결과 파일만 커밋한다. 팀원 누구나 같은 명령으로 같은 결과를 재생성할 수 있어야 한다.

## 출력

`data/processed/pokedex_extra.json` — id를 키로 보강 필드만 담는다. 기존 파일과는 `id`로 조인한다.

## 절차

1. `verify_bundle()`로 기준 데이터 무결성을 확인한다.
2. PokeAPI에서 보강 필드를 받아 단위를 변환한다. 호출 간격 0.5초 이상, 429/5xx는 지수 백오프로 재시도한다.
3. `pokedex_extra.json`을 결정적으로 쓴다 (id 오름차순, 키 순서 고정).
4. 아래 검증을 모두 통과하면 manifest에 `stage: normalize`로 기록한다.

## 규칙

- 단위 변환은 여기서 끝낸다. 하위 단계와 LLM은 변환하지 않는다.
- 답변 기준은 1세대 Red/Blue(`*_gen1`). `*_current`는 참고용으로만 노출한다.
- 실행 시각 등 가변 값을 출력에 넣지 않는다.
- 저장소에 커밋되지 않은 로컬 파일을 입력으로 쓰지 않는다. 입력은 `data/processed/`와 PokeAPI뿐이다.

## 검증

- `verify_bundle()` 통과
- pokedex_extra 151건, 필수 필드 null 없음, pokemon.json과 id 집합 일치
- 샘플 대조: 25(피카츄), 35(삐삐: 1세대 normal), 6(리자몽: 복합 타입)
- 같은 입력으로 두 번 실행 시 출력 파일 해시 동일
