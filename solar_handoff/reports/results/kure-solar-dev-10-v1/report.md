# KURE·Solar 개발 질문 검색 비교: 독립 채점

**요약:** 동일한 Red·Blue 개발 질문 10개, 동일 151문서·1,504청크에 대해 KURE와 Solar를 각각 벡터 A 및 BM25+벡터 B로 비교했다. 조건별 10건, 총 40건의 저장된 검색 결과를 독립적으로 다시 채점했다. 답변 가능한 8문항에서 **네 조건 모두 지정 근거 Hit@5는 8/8로 동률**이다. 지정된 필수 앵커를 모두 회수한 비율은 KURE A·B 8/8, Solar A·B 7/8이다. 이는 작은 개발 표본과 고정된 임시 앵커 기준이며, 일반적인 모델 우열이나 답변 정확도의 결론이 아니다.

## 결과

| 조건 | Hit@1 | Hit@3 | Hit@5 | 모두 회수@1 | 모두 회수@3 | 모두 회수@5 | complete-MRR@5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| KURE A 벡터 | 8/8 | 8/8 | 8/8 | 5/8 | 8/8 | 8/8 | 0.7917 (19/24) |
| KURE B 결합 | 7/8 | 8/8 | 8/8 | 5/8 | 7/8 | 8/8 | 0.7542 (181/240) |
| Solar A 벡터 | 8/8 | 8/8 | 8/8 | 5/8 | 7/8 | 7/8 | 0.7500 (3/4) |
| Solar B 결합 | 7/8 | 8/8 | 8/8 | 5/8 | 7/8 | 7/8 | 0.7083 (17/24) |

- **Hit@k:** D01~D08 중 지정 청크 하나 이상이 k위 안에 있는 문항 수. **모두 회수@k:** 그 문항의 지정 필수 앵커가 전부 k위 안에 있는 문항 수. D09·D10은 분모에서 제외한다.
- **complete-MRR@5:** 문항마다 필수 앵커의 순위 중 가장 늦은 순위의 역수를 계산해 8문항 평균을 낸다. 앵커 하나라도 상위 5개에 없으면 그 문항은 0이다. 예를 들어 D05에서 KURE A의 두 순위는 1·3이므로 기여값은 1/3이다. 상위 5개만 관찰하므로 5위 밖의 정확한 순위는 알 수 없다.
- D01에서 Solar A·B는 지정 `profile`이 5위 밖이지만 `stats`가 1위라 Hit@5는 성공, 지정 앵커 모두 회수@5는 미달이다. Solar의 반환 상위 5개 본문을 확인한 범위에서는 후딘 타입을 직접 나타내는 대체 청크도 찾지 못했다. 이는 전체 코퍼스나 5위 밖에 대체 근거가 없다는 뜻은 아니다.
- D05는 머신을 피카츄가 배울 수 있다는 사실과 머신 획득 장소가 각각 필요하다. KURE A 순위 1·3이 B에서 2·5로 내려가 모두 회수@3이 1건 줄었다. Solar는 A의 2·1에서 B의 2·3으로 바뀌었다. 두 모델 모두 B의 1위가 지정 앵커가 아니므로 Hit@1이 8/8에서 7/8로 낮아졌다.
- KURE는 기존 저장 결과를 재사용했고 Solar는 새 Upstage 질의 임베딩을 사용했다. 따라서 이 표는 새로운 두 모델의 독립 반복 실험이나 통제된 속도·비용 비교가 아니다.

## 실제 질문과 필수 앵커별 순위

아래 순위는 상위 5개 내 순위다. `—`는 상위 5개에 없음을 뜻한다. `A/B`는 해당 모델의 벡터/결합 순서다. 원문 위치는 `pokedex_v3a/` 기준이다. 앵커는 기존 개발 검색의 **임시 고정 매핑**이며 공식 확정된 허용 근거가 아니다.

| 문항과 실제 질문 | 지정 앵커 및 확인 원문 | KURE A/B | Solar A/B |
|---|---|---:|---:|
| D01 후딘을 파티에 넣으려고 하는데, 무슨 타입이고 스피드와 특수 종족치는 각각 얼마인가요? | `pokemon:65#profile` 타입, `documents/065_후딘.md:6` | 2/3 | —/— |
| D01 계속 | `pokemon:65#stats` 종족치, `documents/065_후딘.md:16` | 1/1 | 1/1 |
| D02 식스테일을 그대로 키울 때 레벨 35에 배우는 기술과 그 기술의 타입은 무엇인가요? | `pokemon:37#learnset_level`, `documents/037_식스테일.md:39` | 1/1 | 1/1 |
| D03 이브이를 샤미드나 부스터로 진화시키려면 각각 어떤 돌을 써야 하나요? | `pokemon:133#evolution`, `documents/133_이브이.md:20,22` | 1/1 | 1/1 |
| D04 무지개 게임코너 교환소에서 캐이시를 받을 때, Red와 Blue의 코인 조건과 기록된 레벨은 어떻게 다른가요? | `pokemon:63#encounter`, `documents/063_캐이시.md:142,143` | 1/1 | 1/1 |
| D05 피카츄에게 10만볼트를 머신으로 가르치려면 어떤 머신이 필요한가요? 그 머신을 얻는 것으로 기록된 장소와 방법 한 가지도 알려 주세요. | `pokemon:25#learnset_machine` 습득, `documents/025_피카츄.md:59` | 1/2 | 2/2 |
| D05 계속 | `pokemon:25#machine_acquisition` 획득, `documents/025_피카츄.md:90` | 3/5 | 1/3 |
| D06 갸라도스가 전기·바위·땅 타입 기술을 받을 때 각각 기본 타입 상성 배율은 얼마인가요? | `pokemon:130#defense_matchup`, `documents/130_갸라도스.md:134,135,138` | 1/1 | 1/1 |
| D07 7번도로의 야생 등장 기록에서 가디와 식스테일은 각각 어느 버전에 기록되어 있고, 레벨은 얼마인가요? | `pokemon:58#encounter` 가디, `documents/058_가디.md:130` | 2/2 | 2/3 |
| D07 계속 | `pokemon:37#encounter` 식스테일, `documents/037_식스테일.md:128` | 1/1 | 1/1 |
| D08 리자몽이 자신의 타입과 같은 일반적인 공격 기술을 사용할 때 적용되는 자속 보정은 얼마이고, 해당 타입은 무엇인가요? | `pokemon:6#stab`, `documents/006_리자몽.md:119` | 1/1 | 1/1 |

**앵커 한계:** 같은 사실이 다른 청크에도 있을 수 있다. 기존 세 모델 벡터 보고서의 Gemma D01에서는 지정 타입 청크가 없어도 반환된 후딘 방어 상성이나 자속 청크에서 타입을 확인한 사후 대안이 있었다. D03에서도 샤미드·부스터 진화 청크가 대안 후보로 관찰됐다. 이 같은 사후 가능성을 고정 매핑에 추가하지 않았으며, 한 모델의 지정 앵커 미회수를 곧바로 근거 전체의 부재나 답변 실패로 해석해서는 안 된다. 다른 모든 문항·후보에 대해 대안 근거를 빠짐없이 검토한 것은 아니다. 자세한 기존 관찰은 [기존 Vector 보고서](../vector-dev-10-v1/report.md) 참고.

## 근거 부족 질문: 반환 후보만 관찰

D09 “영문 Red·Blue에서 리아코의 종족치를 알려 주세요.”는 대상 범위 밖, D10 “영문 Red·Blue에서 피카츄의 종족별 포획률 수치는 얼마인가요?”는 코퍼스 정보 부족이라는 기존 개발 제안의 분류다. D10의 부재를 이번에 코퍼스 전체에서 재검사하지 않았다. 다음은 실제 반환 ID이며, **거절 성공·실패 점수가 아니다**. 답변 생성이 없어서 거절 평가는 pending이다.

| 질문 | 조건 | 실제 후보 1 → 5위 |
|---|---|---|
| D09 | KURE A | `pokemon:115#evolution` → `pokemon:123#evolution` → `pokemon:113#evolution` → `pokemon:106#evolution` → `pokemon:44#learnset_level` |
| D09 | KURE B | `pokemon:115#evolution` → `pokemon:113#evolution` → `pokemon:123#evolution` → `pokemon:114#evolution` → `pokemon:124#evolution` |
| D09 | Solar A | `pokemon:26#stats` → `pokemon:82#profile` → `pokemon:123#evolution` → `pokemon:82#stats` → `pokemon:26#profile` |
| D09 | Solar B | `pokemon:113#evolution` → `pokemon:123#evolution` → `pokemon:114#evolution` → `pokemon:124#evolution` → `pokemon:122#evolution` |
| D10 | KURE A | `pokemon:25#encounter` → `pokemon:25#learnset_level` → `pokemon:25#stats` → `pokemon:25#profile` → `pokemon:26#encounter` |
| D10 | KURE B | `pokemon:25#profile` → `pokemon:25#encounter` → `pokemon:25#stats` → `pokemon:25#learnset_level` → `pokemon:25#learnset_machine` |
| D10 | Solar A | `pokemon:25#encounter` → `pokemon:25#profile` → `pokemon:25#stats` → `pokemon:25#learnset_level` → `pokemon:60#encounter` |
| D10 | Solar B | `pokemon:25#profile` → `pokemon:25#encounter` → `pokemon:25#stats` → `pokemon:25#learnset_level` → `pokemon:25#learnset_machine` |

## 구성·사용량과 한계

- A는 exact cosine 벡터 상위 5개. B는 BM25 상위 20개와 벡터 상위 20개를 동일 가중 RRF(상수 60)로 결합해 상위 5개를 반환한다. 동점은 청크 ID 오름차순. 구체적 설정은 [config.json](config.json)과 기존 [하이브리드 설정](../hybrid-dev-10-v1/config.json)에 기록돼 있다. C 재정렬은 이번 비교에서 실행하지 않았다.
- 실행 원본에 기록된 인덱스는 `v3a_full_151_20261125_v1`, 원본 상태 `completed`. 모델별 1,504개 벡터 및 동일 청크 연결은 원본 preflight의 기록이다. 오프라인 대조는 실행 당시 DB 상태, 서버 전처리, 승인 상태를 직접 증명하지 않는다. 기록된 설정 및 버전의 불일치는 발견하지 않았으나 전체 실행 조건 검증은 불가능하므로 `invalid_condition` 확정 여부는 미확인이다.
- Solar 질의 모델 `solar-embedding-2-query`, 문서 모델 `solar-embedding-2-passage`, 1024차원. 새 질의 10개를 4·4·2로 3회 전송한 기록이다. 배치별 prompt/total tokens는 각각 223/223, 245/245, 78/78, 합계 **546/546**. 입력별 사용량은 제공되지 않았다. KURE 기존 벡터 실행 기록에는 prompt_eval_count 304가 있으며 이번에 다시 호출한 사용량이 아니다. 서로 다른 토크나이저의 숫자를 비용이나 성능으로 직접 비교하지 않는다. 실제 청구액·단가는 확인할 수 없어 비용 추정 불가다.
- Solar 토크나이저 일치성과 서버 잘림 여부는 **미검증**이다. 입력 바이트 수나 배치 사용량은 토큰 수 및 잘림 없음의 증거가 아니다. provider alias의 불변 revision은 미확인이다.
- 검색 결과만의 소규모 개발 스모크 테스트다. 생성 답변, 사실성·인용 적합성·거절의 사람 채점은 없다. 질문·앵커는 미확정이며 정식 최종 평가나 모델 채택 판단이 아니다. 최종 평가셋은 열람·검증·해시하지 않았다.

## 검증과 재현

독립 스크립트 [score_offline.py](score_offline.py)는 원본 40행의 `(모델, 방법, qid)` 유일성과 각 top5 중복 없음·1~5위, D01~D10 질문 UTF-8 바이트 및 ID 동일성, 원본과 3개 Solar 배치 기록, 200개 후보의 본문과 SHA-256을 로컬 1,504청크 스냅샷에 대조한다. KURE A의 10개 top5 ID 순서는 기존 벡터 원본과 하이브리드 벡터 후보에, KURE B의 10개 순서는 기존 하이브리드 원본에 각각 대조한다. 독립 계산한 KURE A의 모든 k별 점수는 기존 벡터 및 하이브리드 점수에, KURE B는 기존 하이브리드 점수에 정확히 일치한다. 각 KURE 문항의 앵커 순위도 기존 점수와 일치한다. 이 검사는 검색을 다시 실행하거나 원점수로 RRF를 재계산하는 검사가 아니다. 원본 상태와 저장된 스냅샷의 일관성 검사이며 사실적 승인·실행 당시 DB의 독립 검증은 아니다.

저장소 루트의 Git Bash에서 실제 실행한 명령(재생성은 최초 1회 `--write`, 기존 파일이 있으면 덮어쓰지 않음):

```bash
export TEMP='C:/Users/lexus/AppData/Local/hermes/profiles/blank/cache/scratch' TMP="$TEMP" TMPDIR="$TEMP" PYTHONDONTWRITEBYTECODE=1
python results/kure-solar-dev-10-v1/score_offline.py --check
python -m unittest discover -s results/kure-solar-dev-10-v1 -p test_score_offline.py -v
sha256sum results/kure-solar-dev-10-v1/score_offline.py results/kure-solar-dev-10-v1/test_score_offline.py results/kure-solar-dev-10-v1/score.json
```

결과: `--check` PASS, 오프라인 테스트 **10개 통과**. 누락 행, 중복 후보·조건, 질문·본문·배치 변조, KURE 순위 변경과 다중 앵커 계산을 확인했다. 파일 및 입력 해시는 다음과 같으며 나머지 입력 해시와 모든 조건·후보는 [score.json](score.json)에 있다.

| 항목 | SHA-256 |
|---|---|
| raw.json | `214d77577c1a61a3d00d8a6a31e5ed5f51f2c8778ce1063ef62b6e97b36095d5` |
| config.json | `1a487ab8c005a9be78be0b6887ca291eeac7271b12d2b8c3b43346df9d2f001f` |
| score.json | `df2d79fafad8315ca0ba6f742c600c9a25a65d2ef94c2e4c797062b9fa56f047` |
| score_offline.py | `30b7aed77608e845757cf72dff08cf780dde9113c6736318188a10e0bac8472e` |
| test_score_offline.py | `63b72dfe58da2fb735e70cc2a9151d588ec0b9d9098a6fcb8309382c48eeba39` |
| 고정 앵커 맵, 공백 없는 UTF-8 JSON | `b566872114a04bd72802a30dbba6a11b6deaa4f9f96c9c8c38fd4edee08dc6a8` |
| 질문 파일 및 정규 JSON | `d926f26b383b0f7ed2ea540a3a365895461ccc8619e4fbf7a2017e79b36813e1` |
| 청크 스냅샷 | `b976ed9d0d6f88dc1c2ad875af11cf4f3556a0f0c7f4fab888ca324376a9ba54` |

**작업 중 제약 위반:** 시작 시 프로젝트 일반 규칙을 잘못 우선해 `git fetch --dry-run origin main`을 한 번 실행했고 원격에 접속했다. 이는 이번 발주의 네트워크 금지 위반이다. 이후 DB·API·네트워크·`.env` 접근이나 재검색·재임베딩·답변 생성을 하지 않았다. Git dry-run은 검색 데이터 수집이 아니며 이 비교 점수에는 사용하지 않았다.
