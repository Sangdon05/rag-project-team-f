---
name: data-normalize
description: Use when preparing or verifying normalized Red/Blue data and source provenance without modifying hash-pinned files.
---

# data-normalize

영문 Red·Blue 포켓몬별 Markdown과 정확한 조회·계산에 필요한 정제 데이터의 범위, 출처와 완전성을 확인한다. 파일 존재만으로 내용의 완전성이나 재생성 가능성을 보장하지 않는다.

## 기준 데이터 (수정 금지)

`scripts/gen1_battle/data_integrity.py`의 `HASHES`에 명시된 `data/processed/`의 다섯 파일만 이 검사로 SHA-256 고정된다.

| 파일 | 내용 |
| --- | --- |
| pokemon.json | 151마리. name_ko, types_gen1/current, stats_gen1/current, learnset |
| moves.json | 165개 기술. name_ko, 버전별 위력/명중/PP/타입 |
| types.json | 1세대 15개 타입, name_ko |
| type_chart.json | 1세대 상성표 |
| red_blue_move_damage_classification.json | Red·Blue 기술 피해 처리 분류 |

이 파일을 수정하면 `BattleRules` 로딩이 실패한다. 값을 바꿔야 하면 파일과 `HASHES`를 함께 갱신하는 별도 PR로 처리하고 오케스트레이터에 보고한다.

## 별도 정제 데이터와 출처

아래 파일은 위 `HASHES` 검사의 대상이 아니다. 현재 작업 트리에서 확인된 파일이며, 공유·커밋 여부와 실제 내용·출처는 작업마다 확인한다.

| 파일 | 내용과 검증 시 주의 |
| --- | --- |
| `evolutions_red_blue.json` | 포켓몬별 진화 관계·조건 |
| `encounters_red_blue.json` | 포켓몬별 Red/Blue 등장·획득 기록. 빈 기록은 획득 불가의 증거가 아니다 |
| `machines_red_blue.json` | TM/HM 번호와 기술 매핑 |
| `machine_acquisition_red_blue.json` | 머신의 확인된 획득 경로. 전체 경로·조건의 완전성은 별도 검증한다 |

`data/source_manifest.json`은 공유 정제 데이터의 파일 해시·출처·레코드 식별을 기록한다. 파일을 변경하면 실제 크기·해시와 레코드 연결을 대조하고 매니페스트의 적용 여부를 확인한다. 매니페스트나 라이브 API 링크만으로 과거 원본 보존이나 동일 재생성이 보장되지는 않는다. 원본 스냅샷이 없는 부분과 수집 시각을 모르는 부분은 명시한다.

외형·생태·도감 설명, 키·몸무게는 현재 포켓몬 문서의 필수 보강 범위가 아니다. `pokedex_extra.json`이나 별도 수집 스크립트의 존재·151건 생성을 전제하지 않는다. 추가 데이터가 필요하면 먼저 질문·출처·사용 범위를 확인하고 별도 산출물로 보강한다.

## 절차

1. 대상 질문과 필요한 필드를 확인하고 `verify_bundle()`로 해시 고정 파일의 무결성을 검사한다.
2. 기존 정제 데이터와 출처 매니페스트를 먼저 확인한다. ID·버전별 기록, 빠진 필드와 원본 대조 가능 여부를 구분한다.
3. 필요한 경우 저장소에 공유되는 입력 또는 PokeAPI로 별도 보강한다. API 수집 시 호출 간격 0.5초 이상, 429/5xx는 지수 백오프로 재시도한다. 버전 차이와 원본·정제 결과를 구분하고 결정적으로 출력한다.
4. 대상 범위의 검증 결과와 출처를 기록한다. 파이프라인 실행은 `runs/manifest.jsonl`(예정)에 남기며, 기록 수단이 없으면 완료로 가정하지 않고 보고한다.
5. 정제 데이터는 포켓몬별 Markdown의 사실 근거다. Markdown 작성·승인·청킹과 별도 근거 연결은 `chunking` 스킬을 따른다.

## 규칙

- 단위 변환은 여기서 끝낸다. 하위 단계와 LLM은 변환하지 않는다.
- 답변 기준은 영문 Red·Blue다. 버전별 값과 현재 값을 구분하고 현재 값을 Red·Blue 값으로 대체하지 않는다.
- 실행 시각 등 가변 값을 출력에 넣지 않는다.
- 저장소에 커밋되지 않은 개인 로컬 파일에 의존하지 않는다. 입력은 공유되는 저장소 파일과 PokeAPI로 제한한다.
- 알 수 없는 장소명·습득·진화 조건을 추측하거나 미확인을 불가능으로 바꾸지 않는다. 외부 데이터와 Pokémon 콘텐츠의 사용·재배포 조건을 별도로 확인한다.

## 검증

- `verify_bundle()` 통과
- 전체 대상 작업 시 포켓몬 ID 151종·기술 ID 165종을 정제 데이터와 대조한다. 진화·획득 기록은 포켓몬 ID 집합, 머신 매핑·획득 기록은 TM/HM 55개 번호의 중복·누락을 확인한다. 개수 일치만으로 모든 사실이나 경로가 완전하다고 판단하지 않는다.
- 기술별 Red·Blue 타입, 레벨업·머신 습득, 진화·획득처는 해당 소스와 연결해 표본 및 작업 범위 전체를 대조한다. `verify_bundle()`이 네 가지 별도 정제 파일의 출처나 내용을 검증한다고 주장하지 않는다.
- 보강 산출물이 있으면 해당 스키마와 누락 상태를 검증하고, 같은 고정 입력으로 재실행해 결과 해시를 비교한다. 선택적 원본이 없으면 원본 대조·재생성 미검증으로 보고한다.
