---
name: chunking
description: Use when creating or changing chunks, chunk text templates, chunk IDs, or chunk metadata for the Pokédex vector index.
---

# chunking

정규화 데이터를 검색 단위 청크로 나누고 메타데이터를 붙인다.
메타데이터 스키마는 계약 파일 `contracts/chunk_schema.json`(예정)이 기준이다. 아래 표는 그 초안이다.

## 입력 / 출력

- 입력: `data/processed/pokemon.json`, `moves.json`, `types.json`, `pokedex_extra.json`
- 출력: `data/chunks/chunks.jsonl`

## 청크 단위

| 대상 | section | 내용 | 개수 |
| --- | --- | --- | --- |
| 포켓몬 | profile | 이름, 분류, 타입(1세대 / 현재), 키, 몸무게 | 151 |
| 포켓몬 | stats | 1세대 종족값 (HP, 공격, 방어, 스피드, 특수) | 151 |
| 포켓몬 | learnset | 레벨업 기술 요약 (기술머신은 개수만) | 151 |
| 포켓몬 | flavor | 도감 설명 | 151 |
| 포켓몬 | evolution | 진화 전후 | 151 |
| 기술 | move | 이름, 타입, 위력, 명중, PP, 물리/특수 | 165 |

약 920개. 1세대에는 특성이 없으므로 abilities 섹션은 만들지 않는다.
습득 여부·레벨 같은 정확한 조회는 청크가 아니라 툴(`get_learnset`)이 담당한다.

## 텍스트 규칙

1. JSON이 아닌 한국어 문장 템플릿. 예:
   `피카츄(Pikachu, 25번)의 1세대 종족값: HP 35, 공격 55, 방어 30, 스피드 90, 특수 50.`
2. 모든 청크 앞에 `이름(영문명, 번호)`를 넣는다. 섹션 청크도 이름으로 검색되게 하기 위해서다.
3. 템플릿에 버전(`tpl1`)을 붙인다. 템플릿 변경 = 전체 재임베딩 = 새 index_version.
4. 결정적 출력: 숫자 포맷·순서 고정, 가변 값 금지.

## 청크 ID

- 포켓몬: `pokemon:{id}#{section}` (예: `pokemon:25#stats`)
- 기술: `move:{id}` (예: `move:85`)

데이터가 바뀌어도 ID는 유지된다. 증분 sync가 ID에 의존한다.

## 메타데이터 (계약 초안)

| 키 | 타입 | 비고 |
| --- | --- | --- |
| entity | enum | pokemon / move |
| pokemon_id | int | 포켓몬 청크만 |
| move_id | int | 기술 청크만 |
| name_en | str | |
| section | enum | profile / stats / learnset / flavor / evolution / move |
| type_{normal, fire, …} | bool | 1세대 15종. 포켓몬은 types_gen1, 기술은 기술 타입 |
| stat_hp, stat_attack, stat_defense, stat_speed, stat_special | int | stats 섹션만 |
| power, accuracy, pp | int | move 청크만, red-blue 값 |
| damage_class | enum | move 청크만, physical / special |
| content_hash | str | sha256(embed_model + "\|" + text) |
| meta_hash | str | sha256(정렬된 메타데이터) |
| schema_version | str | |

- 메타데이터 값은 스칼라만 쓴다 (pgvector JSONB 필터 기준). `"fire,flying"` 같은 문자열은 정확히 필터하기 어려우므로 타입별 불리언 플래그를 쓴다.
- 타입 enum은 `types.json`의 15개, 소문자 영문으로 고정한다. 표기가 섞이면 필터가 조용히 0건을 반환한다.
- 한글명·별칭은 필터가 아니라 텍스트와 `resolve_name` 툴에서 처리한다.

## 검증

- 청크 수 = 151 × 5 + 165 (도감 설명 없는 경우 예외 목록 기록)
- 섹션별 분포, 텍스트 길이 범위
- 모든 청크가 계약 스키마 검증 통과
- 같은 입력으로 두 번 실행 시 chunks.jsonl 해시 동일
