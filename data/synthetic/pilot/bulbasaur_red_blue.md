---
document_id: "pokemon:1:red-blue"
pokemon_id: 1
version_group: "red-blue"
review_status: "pending"
index_eligible: false
generation_method: "AI-assisted draft based on the reviewed-data template"
metadata_source: "data/synthetic/pilot/bulbasaur_red_blue.json"
metadata_scope: "source references only; Markdown text is independently edited"
source_manifest: "data/source_manifest.json"
---

# 이상해씨

- **도감번호:** 001
- **타입:** 풀 · 독
- **기준 게임:** 영문 Pokémon Red·Blue

> 검토 전 초안입니다. 설명과 수치는 정제 데이터와 파일럿 청크를 바탕으로 작성했으며, 게임의 모든 예외를 재현하지 않습니다.

<!-- chunk_id: pokemon:1:red-blue:basic_stats -->
## 어떤 포켓몬인가요?

이상해씨는 풀과 독, 두 가지 타입을 가진 복합 타입 포켓몬입니다. 레벨업으로 기술을 배우며, 레벨 16에 이상해풀로 진화합니다.

## 종족치

| HP | 공격 | 방어 | 스피드 | 특수 |
|---:|---:|---:|---:|---:|
| 45 | 49 | 49 | 45 | 65 |

<!-- chunk_id: pokemon:1:red-blue:evolution -->
## 진화

이상해씨는 **레벨 16**에 이상해풀로 진화합니다.

```text
이상해씨 ── 레벨 16 ──▶ 이상해풀
```

<!-- chunk_id: pokemon:1:red-blue:level_moves -->
## 기술

### 레벨업으로 배우는 기술

영문 Red·Blue 습득 데이터에 기록된 레벨업 기술 전체입니다.

| 습득 레벨 | 기술 | 타입 |
|---:|---|---|
| 1 | 몸통박치기 | 노말 |
| 1 | 울음소리 | 노말 |
| 7 | 씨뿌리기 | 풀 |
| 13 | 덩굴채찍 | 풀 |
| 20 | 독가루 | 독 |
| 27 | 잎날가르기 | 풀 |
| 34 | 성장 | 노말 |
| 41 | 수면가루 | 풀 |
| 48 | 솔라빔 | 풀 |

<!-- chunk_id: pokemon:1:red-blue:machine_moves -->
### 기술머신·비전머신으로 배우는 기술

영문 Red·Blue 습득 데이터에 기록된 머신 기술 전체입니다.

| 머신 | 기술 | 타입 |
|---|---|---|
| HM01 | 풀베기 | 노말 |
| TM03 | 칼춤 | 노말 |
| TM06 | 맹독 | 독 |
| TM08 | 누르기 | 노말 |
| TM09 | 돌진 | 노말 |
| TM10 | 이판사판태클 | 노말 |
| TM20 | 분노 | 노말 |
| TM21 | 메가드레인 | 풀 |
| TM22 | 솔라빔 | 풀 |
| TM31 | 흉내내기 | 노말 |
| TM32 | 그림자분신 | 노말 |
| TM33 | 리플렉터 | 에스퍼 |
| TM34 | 참기 | 노말 |
| TM44 | 잠자기 | 에스퍼 |
| TM50 | 대타출동 | 노말 |

솔라빔은 레벨업과 TM22 두 방법으로 기록돼 있습니다. 레벨업 9건과 머신 15건을 합치면 습득 기록은 24건이고, 중복을 제외하면 기술은 23개입니다. 목록은 **배울 수 있는 기술**을 뜻하며, 지금 보유한 기술을 뜻하지는 않습니다.

<!-- chunk_id: pokemon:1:red-blue:machine_acquisition -->
### 머신은 어디서 얻나요?

아래는 현재 데이터에서 확인한 머신 획득 경로입니다. 같은 머신에 기록된 경로가 여러 개면 함께 표시했습니다. 장소 이름은 검증된 한국어 명칭이 없어 원본 지도 식별자를 사용합니다. 모든 경로나 도달 조건을 완전히 검증한 목록은 아닙니다.

| 머신 | 확인된 장소와 방법 |
|---|---|
| HM01 | `SSAnneCaptainsRoom` — NPC 보상 |
| TM03 | `SilphCo7F` — 바닥 아이템 |
| TM06 | `FuchsiaGym` — NPC 보상 |
| TM08 | `SSAnne1FRooms` — 바닥 아이템 |
| TM09 | `SilphCo5F` — 바닥 아이템; `CeladonMart2F` — 상점 |
| TM10 | `RocketHideoutB3F` — 바닥 아이템 |
| TM20 | `Route15` — 바닥 아이템 |
| TM21 | `CeladonGym` — NPC 보상 |
| TM22 | `PokemonMansionB1F` — 바닥 아이템 |
| TM31 | `CopycatsHouse2F` — NPC 보상 |
| TM32 | `SafariZoneWest` — 바닥 아이템; `CeladonMart2F` — 상점 |
| TM33 | `PowerPlant` — 바닥 아이템; `CeladonMart2F` — 상점 |
| TM34 | `PewterGym` — NPC 보상 |
| TM44 | `SSAnneB1FRooms` — 바닥 아이템 |
| TM50 | `GameCornerPrizeRoom` — 게임코너 경품 교환 |

<!-- chunk_id: pokemon:1:red-blue:type_matchups; 추가 근거: data/processed/type_chart.json의 grass, poison 공격 행과 grass, poison 방어 열; data/processed/moves.json의 /39; data/processed/red_blue_move_damage_classification.json의 /moves/39 -->
## 타입 · 상성

### 자속 보정

이상해씨가 자신의 타입과 같은 **풀 또는 독 타입 공격 기술**을 사용하면 자속 보정으로 피해가 1.5배가 됩니다.

- **풀 타입 예시:** 덩굴채찍을 사용하면 자속 보정을 받습니다.
- **독 타입 예시:** 독 타입 공격 기술인 독침을 사용할 수 있다면 같은 자속 보정을 받습니다.

현재 습득 데이터에는 이상해씨가 독침을 배운다는 기록이 없어, 독 타입 예시는 가정입니다.

### 공격할 때

사용하는 **기술의 타입**에 따라 상대에게 주는 효과가 달라집니다.

| 기술 타입 | 효과가 좋은 상대 타입 | 효과가 약한 상대 타입 |
|---|---|---|
| 풀 | 물, 땅, 바위 | 불꽃, 풀, 독, 비행, 벌레, 드래곤 |
| 독 | 풀, 벌레 | 독, 땅, 바위, 고스트 |

독 타입 공격 행은 상성을 이해하기 위한 가정입니다.

### 공격받을 때

상대가 어떤 타입의 기술을 쓰는지에 따라 이상해씨가 받는 피해가 달라집니다.

| 상대 기술의 타입 | 받는 피해 |
|---|---:|
| 벌레 | 4배 |
| 비행, 불꽃, 에스퍼, 얼음 | 2배 |
| 격투, 물, 전기 | 0.5배 |
| 풀 | 0.25배 |

위에 없는 타입의 기본 배율은 1배입니다. 실제 피해량은 레벨과 능력치 등 전투 상황에 따라 달라집니다.

<!-- chunk_id: pokemon:1:red-blue:pokemon_acquisition -->
## 획득처

PokéAPI의 영문 Red와 Blue 기록에서 이상해씨는 각각 `pallet-town-area`에서 **선물** 방식으로 얻는 것으로 기록돼 있습니다. 한국어 장소명은 현재 검증된 값이 없어 원본 식별자를 사용했습니다. 이 기록이 모든 획득 경로를 보장하지는 않습니다.

---

## 출처와 검토 상태

- 원천 데이터: `data/processed/pokemon.json`, `moves.json`, `evolutions_red_blue.json`, `machines_red_blue.json`, `machine_acquisition_red_blue.json`, `types.json`, `type_chart.json`, `encounters_red_blue.json` 및 `red_blue_move_damage_classification.json`.
- 청크별 기존 근거와 JSON 위치: `data/synthetic/pilot/bulbasaur_red_blue.json`의 각 청크 `source_records`. 상성 문장의 독 타입 공격 행은 위 주석에 기재된 타입 상성표를 추가 근거로 사용합니다. JSON의 문장 내용은 이 Markdown 수정과 자동 동기화되지 않습니다.
- 원천 데이터의 출처·버전·해시 목록: `data/source_manifest.json`.
- 작성 방식: 정제 데이터와 템플릿 파일럿을 근거로 읽기 쉽게 다듬은 AI 보조 초안.
- 검토 상태: 사람의 검토가 필요하며, 아직 검색 색인 대상으로 승인하지 않았습니다.
