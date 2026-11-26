# 개발 질문 10개: 세 모델의 Vector 검색 비교

> **한눈에:** 같은 질문에서 세 임베딩 모델이 필요한 근거를 얼마나 찾아오는지 살펴본 검색 전용 실험이다. 답변 생성이나 모델 채택을 평가한 결과는 아니다.

| 항목 | 이번 실험 |
|---|---|
| 실험 질문 | 영문 Red·Blue 도감 질문에서 세 모델의 검색 근거 회수와 순위는 어떻게 다른가? |
| 대상 | 전체 151문서, A안 초안 1,504청크; 세 모델에 동일한 개발 후보 10질문 적용 |
| 방법 | A: Vector 단독 검색, 상위 5개(k=5), 필터 없음. 답변 가능 8문항과 범위 밖·정보 부족 2문항 |
| 실행 | 세 모델 × 10질문 = 30건 중 **30건 검색 성공**, 문항당 결과 5개 |
| 결과 | 세 모델 모두 지정 근거 하나 이상 Hit@5 **8/8**. 지정 앵커 모두 회수@5는 Gemma **7/8**, KURE **8/8**, OpenAI **8/8** |
| 의미 | 답변 가능 표본 8개에서 지정 근거의 순위를 관찰했다. 미확정 질문·앵커 후보를 쓴 개발 스모크 테스트이므로 **정식 결과나 모델 채택 근거로 확정할 수 없다**. |

## 모델별 결과와 판단

| 모델 | Hit@5 | 지정 앵커 모두 회수@5 | 눈에 띈 점 |
|---|---:|---:|---|
| Gemma | 8/8 | 7/8 | D01 지정 타입 청크는 5위 밖이나 다른 반환 청크에 타입 정보가 있다. D03 지정 진화 청크는 3위. |
| KURE | 8/8 | 8/8 | 지정 앵커가 모두 3위 이내. D07은 식스테일 1위, 가디 2위. |
| OpenAI | 8/8 | 8/8 | D05 머신 획득 1위·피카츄 머신 습득 5위, D07 가디 3위. |

**판단:** 지정 근거 순위의 관찰이지 모델의 전반적 우열이나 답변 정확도가 아니다. 통제된 속도·비용 비교를 하지 않아 어느 모델이 빠르거나 저렴한지도 알 수 없다. 질문·기대 답과 근거의 사용자 사실 확인, 생성 답변과 거절의 사람 채점은 대기 중이다.

**지표 차이 예시:** Hit@5는 지정 청크가 하나라도 상위 5개에 있으면 적중이다. D01에서 후딘의 종족치 청크만 있어도 적중이다. 반면 지정 앵커 모두 회수@5는 타입과 종족치 두 청크가 모두 있어야 한다. Gemma는 종족치 1위, 지정 타입 청크는 5위 밖이어서 Hit는 적중이지만 모두 회수는 미달이다. 다른 반환 청크의 타입 정보는 아래 D01 설명을 참고한다.

## 지표

`Hit@k_any`: 답변 가능 8문항 중 지정 앵커가 하나 이상 상위 k에 있는 문항. `selected_anchors_complete@k`: 지정 앵커 전부가 상위 k에 있는 문항. 단일 앵커에서는 둘이 같고 다중 앵커에서는 다르다. D09·D10은 분모에서 제외한다. 이는 공식 확정 allowed_evidence에 대한 공식 Hit가 아니다.

| 모델 | Hit@1_any | Hit@3_any | Hit@5_any | complete@1 | complete@3 | complete@5 |
|---|---:|---:|---:|---:|---:|---:|
| gemma | 7/8 | 8/8 | 8/8 | 4/8 | 6/8 | 7/8 |
| kure | 8/8 | 8/8 | 8/8 | 5/8 | 8/8 | 8/8 |
| openai | 8/8 | 8/8 | 8/8 | 5/8 | 7/8 | 8/8 |

표본은 답변 가능 8문항뿐이며 하나의 고정 매핑으로 계산한 관찰치다. 수치 차이만으로 일반화하거나 모델을 선택하지 않는다.

## 실제 질문과 기대 답

아래는 [개발 후보 제안서](../../docs/proposals/dev-vector-10-draft-20261125.md)의 미확정 기대 답이다. 질문은 실제 검색 입력 그대로다.

| 문항 | 질문 | 기대 답 |
|---|---|---|
| D01 | 후딘을 파티에 넣으려고 하는데, 무슨 타입이고 스피드와 특수 종족치는 각각 얼마인가요? | 에스퍼, 스피드 120·특수 135 |
| D02 | 식스테일을 그대로 키울 때 레벨 35에 배우는 기술과 그 기술의 타입은 무엇인가요? | 화염방사, 불꽃 |
| D03 | 이브이를 샤미드나 부스터로 진화시키려면 각각 어떤 돌을 써야 하나요? | 샤미드 물의돌, 부스터 불꽃의돌 |
| D04 | 무지개 게임코너 교환소에서 캐이시를 받을 때, Red와 Blue의 코인 조건과 기록된 레벨은 어떻게 다른가요? | Red 180코인·레벨 9, Blue 120코인·레벨 6 |
| D05 | 피카츄에게 10만볼트를 머신으로 가르치려면 어떤 머신이 필요한가요? 그 머신을 얻는 것으로 기록된 장소와 방법 한 가지도 알려 주세요. | TM24, 갈색체육관 NPC 보상 |
| D06 | 갸라도스가 전기·바위·땅 타입 기술을 받을 때 각각 기본 타입 상성 배율은 얼마인가요? | 전기 4배, 바위 2배, 땅 0배 |
| D07 | 7번도로의 야생 등장 기록에서 가디와 식스테일은 각각 어느 버전에 기록되어 있고, 레벨은 얼마인가요? | 가디 Red 18·20, 식스테일 Blue 18·20 |
| D08 | 리자몽이 자신의 타입과 같은 일반적인 공격 기술을 사용할 때 적용되는 자속 보정은 얼마이고, 해당 타입은 무엇인가요? | 1.5배, 불꽃·비행 |

D06은 기본 상성이지 실제 피해량이 아니다. D08의 비행 기술 예시는 가정이지 습득을 뜻하지 않는다. 각 문서와 청크는 [전체 코퍼스 안내](../../pokedex_v3a/chunks/README.md)에서 확인할 수 있다.

## 유형 및 고정 후보의 검색 순위

순위는 해당 청크의 상위 5개 중 실제 순위이고, `상위 5위 밖`은 검색 결과에 없다는 뜻이다. 단일 앵커 5문항(D02·D03·D04·D06·D08), 다중 앵커 3문항(D01·D05·D07), 근거 없음 2문항(D09·D10)이다. 30행의 모든 후보 ID와 문서·행은 `score.json`의 `results`에 있다.

| qid | 유형 | 원문 내 지정 후보와 확인 행 |
|---|---|---|
| D01 | 다중 앵커: 타입·종족치 | `pokemon:65#profile` — `documents/065_후딘.md:6`; `pokemon:65#stats` — `documents/065_후딘.md:16` |
| D02 | 단일 앵커: 레벨업 | `pokemon:37#learnset_level` — `documents/037_식스테일.md:39` |
| D03 | 단일 앵커: 분기 진화 | `pokemon:133#evolution` — `documents/133_이브이.md:20,22` |
| D04 | 단일 앵커: 버전별 교환 | `pokemon:63#encounter` — `documents/063_캐이시.md:142,143` |
| D05 | 다중 앵커: 습득·획득 | `pokemon:25#learnset_machine` — `documents/025_피카츄.md:59`; `pokemon:25#machine_acquisition` — `documents/025_피카츄.md:90` |
| D06 | 단일 앵커: 방어 상성 | `pokemon:130#defense_matchup` — `documents/130_갸라도스.md:134,135,138` |
| D07 | 다중 앵커: 두 포켓몬 등장 | `pokemon:58#encounter` — `documents/058_가디.md:130`; `pokemon:37#encounter` — `documents/037_식스테일.md:128` |
| D08 | 단일 앵커: 자속 보정 | `pokemon:6#stab` — `documents/006_리자몽.md:119` |

| qid | Gemma | KURE | OpenAI |
|---|---|---|---|
| D01 | `pokemon:65#profile`: 상위 5위 밖, `pokemon:65#stats`: 1 | `pokemon:65#profile`: 2, `pokemon:65#stats`: 1 | `pokemon:65#profile`: 2, `pokemon:65#stats`: 1 |
| D02 | `pokemon:37#learnset_level`: 1 | `pokemon:37#learnset_level`: 1 | `pokemon:37#learnset_level`: 1 |
| D03 | `pokemon:133#evolution`: 3 | `pokemon:133#evolution`: 1 | `pokemon:133#evolution`: 1 |
| D04 | `pokemon:63#encounter`: 1 | `pokemon:63#encounter`: 1 | `pokemon:63#encounter`: 1 |
| D05 | `pokemon:25#learnset_machine`: 1, `pokemon:25#machine_acquisition`: 2 | `pokemon:25#learnset_machine`: 1, `pokemon:25#machine_acquisition`: 3 | `pokemon:25#learnset_machine`: 5, `pokemon:25#machine_acquisition`: 1 |
| D06 | `pokemon:130#defense_matchup`: 1 | `pokemon:130#defense_matchup`: 1 | `pokemon:130#defense_matchup`: 1 |
| D07 | `pokemon:58#encounter`: 1, `pokemon:37#encounter`: 4 | `pokemon:58#encounter`: 2, `pokemon:37#encounter`: 1 | `pokemon:58#encounter`: 3, `pokemon:37#encounter`: 1 |
| D08 | `pokemon:6#stab`: 1 | `pokemon:6#stab`: 1 | `pokemon:6#stab`: 1 |

### 해석상 주의할 문항

- **D01:** Gemma는 지정 `profile`을 상위 5개에 회수하지 못했으므로 선택 앵커 완전 회수는 실패다. 그러나 `stats` 1위는 스피드 120·특수 135를 담고, 2위 `pokemon:65#defense_matchup`의 `documents/065_후딘.md:132`, 5위 `pokemon:65#stab`의 같은 문서 116행에는 에스퍼 타입에 대한 정보가 있다. 본문과 원문 행 모두 확인한 **사후 탐색적 대체 근거**이며, 지정 매핑·점수에는 추가하지 않았다. 따라서 근거 전체를 못 찾았다고 볼 수 없다. 실제 답변의 충족 여부는 별도 사람 판단이다.
- **D03:** Gemma는 지정 이브이 진화 청크가 3위지만, 1위 `pokemon:134#evolution`의 `documents/134_샤미드.md:23,25` 및 2위 `pokemon:136#evolution`의 `documents/136_부스터.md:23,25` 진화도에도 이브이→샤미드 물의돌과 이브이→부스터 불꽃의돌이 함께 있다. 두 청크 모두 같은 사실을 담는 사후 탐색적 후보로, 지정 매핑에 추가하지 않았다. KURE에서는 각각 3위·2위, OpenAI에서는 각각 2위·4위에 있다.
- **D05:** `learnset_machine`의 59행은 피카츄의 TM24·10만볼트 습득이고 `machine_acquisition`의 90행은 TM24 갈색체육관 NPC 보상이다. 서로 다른 사실이므로 두 앵커를 따로 센다. 기록은 일부 획득 경로에 한정된다.
- **D07:** 가디의 Red 7번도로 레벨 18·20 (`documents/058_가디.md:130`)과 식스테일의 Blue 동일 도로 레벨 18·20 (`documents/037_식스테일.md:128`)이 둘 다 필요하다.

## 근거 없음 문항의 실제 상위 5개

D09 질문은 “영문 Red·Blue에서 리아코의 종족치를 알려 주세요.”, D10 질문은 “영문 Red·Blue에서 피카츄의 종족별 포획률 수치는 얼마인가요?”이다. D09는 코퍼스 대상 범위 밖, D10은 현재 코퍼스의 해당 정보 부족이라는 제안서 분류다. 기대 대응은 각각 범위 밖 또는 현재 문서에서 확인할 수 없음을 설명하고 수치를 추측하지 않는 것이다. D10의 부재는 제안서가 기재한 표기 범위의 관찰이고, 이 채점에서 전체 코퍼스의 모든 표현을 독립 재검사한 것은 아니다. 관련 없는 후보를 돌려주었다는 관찰은 거절의 성공도 실패도 아니다. 생성 답변이 없으므로 거절 평가·점수는 없고 사람의 거절 채점은 `pending`이다.

| 문항 | Gemma 1위 | KURE 1위 | OpenAI 1위 |
|---|---|---|---|
| D09 | 루주라 진화 `pokemon:124#evolution` | 캥카 진화 `pokemon:115#evolution` | 롱스톤 진화 `pokemon:95#evolution` |
| D10 | 피카츄 획득처 `pokemon:25#encounter` | 피카츄 획득처 `pokemon:25#encounter` | 피카츄 종족치 `pokemon:25#stats` |

| 문항 | 모델 | 실제 1 → 5위 청크 ID |
|---|---|---|
| D09 | gemma | `pokemon:124#evolution` → `pokemon:83#evolution` → `pokemon:114#evolution` → `pokemon:115#evolution` → `pokemon:108#evolution` |
| D09 | kure | `pokemon:115#evolution` → `pokemon:123#evolution` → `pokemon:113#evolution` → `pokemon:106#evolution` → `pokemon:44#learnset_level` |
| D09 | openai | `pokemon:95#evolution` → `pokemon:131#evolution` → `pokemon:144#evolution` → `pokemon:83#evolution` → `pokemon:137#evolution` |
| D10 | gemma | `pokemon:25#encounter` → `pokemon:25#profile` → `pokemon:25#stats` → `pokemon:25#defense_matchup` → `pokemon:25#learnset_level` |
| D10 | kure | `pokemon:25#encounter` → `pokemon:25#learnset_level` → `pokemon:25#stats` → `pokemon:25#profile` → `pokemon:26#encounter` |
| D10 | openai | `pokemon:25#stats` → `pokemon:25#learnset_level` → `pokemon:25#encounter` → `pokemon:25#defense_matchup` → `pokemon:25#profile` |

## A/B/C 범위와 다음 단계

| 구성 | 검색 방식 | 이번 상태 |
|---|---|---|
| A | Vector 단독 | 개발 후보로 검색만 실행 |
| B | BM25 + Vector 결합 | 미실행 |
| C | B의 결합 후보 재정렬 | 미실행 |

현재 A의 세 모델 결과를 기준선으로 보존하고 승인·발주 후 동일한 청크·질문·최종 k 등으로 B와 C를 비교한다. B/C는 동일 후보 생성 설정과 질문별 실제 후보 풀을 쓴다. 별도의 전체 답변 평가에서는 생성 모델·프롬프트·출력 및 컨텍스트 제한·툴 설정도 통일하고 답변 품질·근거 적합성·정보 부족 대응을 사람이 평가해야 한다. 정식 평가셋 확정·잠금과 승인 입력·실행 조건 확인은 별도 게이트다.

## 부록: 실행 기록과 한계

- 실행 ID `vector-dev-10-v1`, `real_run`, 검색 전용. UTC: 2026-11-25 14:55:55.397165 ~ 14:56:02.611149. `status=scoring_pending`, `human_judgment=pending`; 생성 없음. 최종 평가 결과가 아니다.
- 검색은 exact cosine Vector 단독, 순차 스캔, 거리 다음 청크 ID 순 정렬, `k=5`, 필터 `null`. 같은 원문 질문에 클라이언트 접두사·분할 없음. 모델별 1,504벡터. 인덱스 `v3a_full_151_20261125_v1`, 스키마 `pokedex_v3a_full_v1`.
- [raw.json](raw.json), [score.json](score.json), [질문](questions.json), [개발 후보 제안서](../../docs/proposals/dev-vector-10-draft-20261125.md), [전체 코퍼스와 청크](../../pokedex_v3a/chunks/README.md). 원본 SHA-256 `9a76848d3e757ac2ba1565ed54ebe205303bbe9fdcd11389237fb911a5e9f2b8`.
- 질문 직렬화 SHA-256 `d926f26b383b0f7ed2ea540a3a365895461ccc8619e4fbf7a2017e79b36813e1`; 질문 파일과 제안서 D01–D10의 질문·순서가 일치. 선택 앵커 맵 SHA-256 `b566872114a04bd72802a30dbba6a11b6deaa4f9f96c9c8c38fd4edee08dc6a8` (qid 순 UTF-8 JSON, 공백 없는 구분자). 초안 청크 SHA-256 `b976ed9d0d6f88dc1c2ad875af11cf4f3556a0f0c7f4fab888ca324376a9ba54`; 제안서 SHA-256 `478853967af096003bb0591496617c56ca65014f5dcaf60702d671c83862199b`. 해시는 승인이나 사실성을 증명하지 않는다.
- 기존 점수 기록에는 150개 후보의 ID·문서·제목·섹션·원문 행 및 문서 해시를 로컬 초안 청크와 비교하고, 87개 고유 청크의 본문을 원문 행에서 재구성한 검증이 남아 있다. 해당 43개 문서 해시·행 범위·본문 해시와 16개 지정 사실 행을 확인한 기록이다. 원본과 설정의 인덱스 버전·설정 해시는 일치하나, DB/API에 접근하지 않은 오프라인 확인은 운영 인덱스 동일성·실행 중 상태·조건 전체의 유효성이나 사실성·정식 승인을 독립 증명하지 않는다.

- 모델 설정 사본: Gemma `embeddinggemma-2:bf16` 768차원, KURE `kure-v1:f32` 1024차원, OpenAI `text-embedding-3-small` 1536차원; 모델 digest·테이블은 [config.json](config.json) 참조. OpenAI는 불변 리비전이 아닌 provider alias다. 서버 내부 전처리·실제 실행 조건 전체는 미확인이다.
- 원본에 기록된 배치 사용량: Gemma `prompt_eval_count=302`, KURE `prompt_eval_count=304`, OpenAI `prompt_tokens=516`, `total_tokens=516`. 모델 간 토큰 수는 직접 비교하지 않는다. 실청구 비용은 `unknown`이다.
- 임베딩은 모델별 10문항 배치였으며 질문별 임베딩 시간은 `unknown`; 통제된 지연시간·처리량 벤치마크가 아니므로 질문당 성능을 추정하지 않는다. 원본의 배치·검색 시간은 `raw.json`에 보존한다.
- 모든 상위 5개 후보 및 원문 메타데이터, 각 문항의 앵커 순위와 분자·분모는 `score.json`에 기록했다. 점수는 검색 회수의 기계적 집계일 뿐 사람의 정답·근거 적합성 채점이 아니다.
- 평가셋 확정·잠금, 실제 응답과 근거를 대조한 사람 채점, 정식 평가 및 최종 모델 선택은 별도 작업이다. 최종 평가셋은 접근하거나 검증하지 않았다.
