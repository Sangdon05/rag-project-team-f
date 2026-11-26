# 개발 질문 리라이트 전후: KURE·Solar B 검색 비교

**결론:** 같은 151문서·1,504청크와 개발 질문 10개에 대한 저장된 B 검색을 오프라인에서 독립 채점했다. 답변 가능 8문항에서 KURE의 지정 앵커 전체 회수@3은 7/8→8/8로 좋아졌지만 Hit@1은 7/8→6/8, complete-MRR@5는 0.7542→0.6875로 낮아졌다. Solar의 지정 앵커 지표는 모두 동일하다. 두 모델 모두 Hit@5는 8/8로 같다. 지표가 상충하므로 이 결과만으로 리라이트 채택이나 모델 우열을 확정할 수 없다.

## 점수

| 조건 | Hit@1 | Hit@3 | Hit@5 | 전체@1 | 전체@3 | 전체@5 | complete-MRR@5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| KURE 원문 | 7/8 | 8/8 | 8/8 | 5/8 | 7/8 | 8/8 | 0.7542 (181/240) |
| KURE 리라이트 후 | 6/8 | 8/8 | 8/8 | 4/8 | 8/8 | 8/8 | 0.6875 (11/16) |
| Solar 원문 | 7/8 | 8/8 | 8/8 | 5/8 | 7/8 | 7/8 | 0.7083 (17/24) |
| Solar 리라이트 후 | 7/8 | 8/8 | 8/8 | 5/8 | 7/8 | 7/8 | 0.7083 (17/24) |

Hit@k는 지정 앵커 중 **하나 이상**, 전체@k는 지정 필수 앵커 **모두**가 상위 k개에 있는 문항 수다. complete-MRR@5는 각 문항에서 가장 늦게 발견된 지정 앵커 순위의 역수 평균이며, 하나라도 5위 밖이면 그 문항은 0이다. 예를 들어 D05 KURE에서 두 앵커는 2·5위→2·3위이므로 전체@3이 개선된다. D02 KURE는 단일 지정 앵커가 1위→2위, D07은 두 앵커 중 하나가 2위→3위로 후퇴했다.

D01 Solar는 지정 타입 앵커 `pokemon:65#profile`이 전후 모두 5위 밖이다. 다만 리라이트 후 5위의 `pokemon:65#defense_matchup` 본문에는 후딘의 에스퍼 타입이 명시되어 있어 대체 근거가 존재한다. 위 숫자는 사전 고정된 잠정 앵커만 계산했고, 이 대안을 사후에 넣지 않았다. 따라서 지정 앵커 누락은 모든 근거의 부재나 답변 실패가 아니다. 다른 문항의 대안 근거 전체를 완전 열거하지도 않았다.

D09는 기존 제안의 범위 밖, D10은 코퍼스 정보 부족 문항으로 분류되어 지표 분모에서 제외했다. D10 부재를 이번에 코퍼스 전체에서 재조사한 것은 아니다. 둘 모두 검색 후보는 실제 반환되었지만 답변 생성이 없으므로 거절 점수는 **미측정**이다. 이 개발 표본과 앵커는 공식 사용자 소유 평가셋이 아니다.

## 비교 조건과 검증

- B는 BM25 상위 20 + 모델별 exact cosine 상위 20을 동일 가중 RRF(상수 60, 동점 ID 오름차순)로 결합하여 최종 5개를 선택한다. BM25는 NFKC·casefold, 한글 연속어와 중첩 2음절, ASCII 단어, 중복 질의어 제거, k1=1.2, b=0.75다. 원문과 리라이트 각각 모델별 10건, 총 B 결과 40행이다. 후자는 **20회 검색 결과**이며 임베딩 호출 20회가 아니다.
- 후속 리라이트 검색은 KURE 로컬 임베딩 1회(10개), Solar API 3회(4·4·2개) 기록이다. KURE `prompt_eval_count=316`; Solar 배치 prompt/total 각각 228/228, 246/246, 78/78, 합계 552/552. 기존 원문 Solar는 223+245+78=546, KURE 기존 벡터 실행은 304다. GPT 리라이트 10회 입력 1,594·출력 940·합계 2,534 토큰. 토크나이저별 사용량을 서로 직접 비교하지 않는다. 비용은 기록상 unknown이다.
- KURE `kure-v1:f32` 기록 revision `7ee043f328640021d761e48b673634035e252880c6805a5c61696d10b2ca1d6c`, `truncate=false`, `num_ctx=8192`; Solar 질의 `solar-embedding-2-query`, 문서 `solar-embedding-2-passage`, 1024차원. Solar 실제 alias의 불변 revision, 토크나이저 일치와 서버 잘림은 미확인. `conservative_unverified` 바이트 제한은 토큰 검증이 아니다.
- 기록된 인덱스 `v3a_full_151_20261125_v1`, 모델별 벡터 digest와 청크 스냅샷·인덱스 설정 digest를 전후 대조했다. 각 B의 전체 후보에서 RRF와 top5를 재계산했으며 40행 top5 200개 각각의 ID·본문·본문 해시·출처 메타데이터와 스냅샷, 관련 원문 40개 해시를 확인했다. 요청·응답·결과·이벤트 및 KURE/Solar 호출 마커를 확인했다. 기록 일치는 실제 서버 전처리나 실행 당시 DB를 독립 관찰한 증거가 아니며 `invalid_condition` 확정은 미확인이다.
- 이 작업은 DB·API·네트워크·`.env`·최종 평가셋에 접근하지 않았다. 실제 기록의 코드·질문·설정·리라이트 해시와 각종 순위는 [score.json](score.json), 검색 전후 원본은 [이전 raw](../kure-solar-dev-10-v1/raw.json)와 [이번 raw](raw.json), 독립 의미 검토는 [semantic-review.md](../rewrite-dev-10-v1/semantic-review.md)에 있다. 실행 전 mock 설명만 담긴 이 폴더의 기존 README 첫머리는 실제 완료된 raw보다 이전 상태다.
- 이번에는 리라이트 후 C 재정렬, 답변 생성과 사람 채점은 없다. 이전 C는 원문 질의 조건이므로 후속 리라이트 결과로 혼동하지 않는다. 사람의 의미 동등성·답변/인용/거절 평가는 pending이다.

## 문항별 원문·실제 검색어·후보

각 모델의 전/후는 실제 B 상위 5개이며 `순위. 이름 — 섹션 [청크 ID]` 형식이다. 앵커 순위의 `—`는 상위 5개 밖이다. **같은 검색어와 같은 결과는 별도 관찰**이다. D09·D10은 원문으로 대체된 검색어이고, 이 실행에서는 양 모델 모두 실제 top5 ID 순서도 동일했다. 변경 문항도 top5가 우연히 같을 수 있다. 원문 위치·줄과 후보별 상세는 score.json에 있다.

### D01
- 원문: 후딘을 파티에 넣으려고 하는데, 무슨 타입이고 스피드와 특수 종족치는 각각 얼마인가요?
- 실제 검색어: 포켓몬 후딘의 타입은 무엇이며, 스피드 종족치와 특수 종족치는 각각 얼마인가요?
- 변화 및 관찰: 파티 편성 배경을 생략했다. 지정 앵커 순위는 두 모델 모두 불변이나 Solar 후 5위에 타입을 명시한 대체 방어 상성 청크가 들어왔다.
- **KURE 앵커 순위:** `pokemon:65#profile` 3→3; `pokemon:65#stats` 1→1
  - 전: 1. 후딘 — 종족치 [`pokemon:65#stats`] → 2. 후딘 — 획득처 [`pokemon:65#encounter`] → 3. 후딘 — 기본 정보 [`pokemon:65#profile`] → 4. 뮤 — 종족치 [`pokemon:151#stats`] → 5. 모다피 — 종족치 [`pokemon:69#stats`]
  - 후: 1. 후딘 — 종족치 [`pokemon:65#stats`] → 2. 후딘 — 방어 상성 (약점과 저항) [`pokemon:65#defense_matchup`] → 3. 후딘 — 기본 정보 [`pokemon:65#profile`] → 4. 뮤 — 종족치 [`pokemon:151#stats`] → 5. 모다피 — 종족치 [`pokemon:69#stats`]
- **SOLAR 앵커 순위:** `pokemon:65#profile` —→—; `pokemon:65#stats` 1→1
  - 전: 1. 후딘 — 종족치 [`pokemon:65#stats`] → 2. 뮤 — 종족치 [`pokemon:151#stats`] → 3. 썬더 — 종족치 [`pokemon:145#stats`] → 4. 삐삐 — 종족치 [`pokemon:35#stats`] → 5. 후딘 — 획득처 [`pokemon:65#encounter`]
  - 후: 1. 후딘 — 종족치 [`pokemon:65#stats`] → 2. 뮤 — 종족치 [`pokemon:151#stats`] → 3. 삐삐 — 종족치 [`pokemon:35#stats`] → 4. 썬더 — 종족치 [`pokemon:145#stats`] → 5. 후딘 — 방어 상성 (약점과 저항) [`pokemon:65#defense_matchup`]

### D02
- 원문: 식스테일을 그대로 키울 때 레벨 35에 배우는 기술과 그 기술의 타입은 무엇인가요?
- 실제 검색어: 식스테일을 진화시키지 않고 키울 때 레벨 35에 배우는 기술과 그 기술의 타입은 무엇인가요?
- 변화 및 관찰: ‘그대로’를 ‘진화시키지 않고’로 해석했다. 이 해석은 사람 확인이 필요하다. KURE의 지정 레벨업 앵커가 1→2위로 후퇴했고 Solar는 1위를 유지했다.
- **KURE 앵커 순위:** `pokemon:37#learnset_level` 1→2
  - 전: 1. 식스테일 — 레벨업으로 배우는 기술 [`pokemon:37#learnset_level`] → 2. 식스테일 — 획득처 [`pokemon:37#encounter`] → 3. 식스테일 — 기술머신·비전머신으로 배우는 기술 [`pokemon:37#learnset_machine`] → 4. 식스테일 — 종족치 [`pokemon:37#stats`] → 5. 식스테일 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:37#stab`]
  - 후: 1. 식스테일 — 획득처 [`pokemon:37#encounter`] → 2. 식스테일 — 레벨업으로 배우는 기술 [`pokemon:37#learnset_level`] → 3. 식스테일 — 기술머신·비전머신으로 배우는 기술 [`pokemon:37#learnset_machine`] → 4. 식스테일 — 종족치 [`pokemon:37#stats`] → 5. 식스테일 — 진화 [`pokemon:37#evolution`]
- **SOLAR 앵커 순위:** `pokemon:37#learnset_level` 1→1
  - 전: 1. 식스테일 — 레벨업으로 배우는 기술 [`pokemon:37#learnset_level`] → 2. 식스테일 — 방어 상성 (약점과 저항) [`pokemon:37#defense_matchup`] → 3. 식스테일 — 기본 정보 [`pokemon:37#profile`] → 4. 식스테일 — 공격 상성 (식스테일과 같은 타입 기술이 잘 통하는 타입) [`pokemon:37#attack_matchup`] → 5. 식스테일 — 기술머신·비전머신으로 배우는 기술 [`pokemon:37#learnset_machine`]
  - 후: 1. 식스테일 — 레벨업으로 배우는 기술 [`pokemon:37#learnset_level`] → 2. 식스테일 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:37#stab`] → 3. 식스테일 — 기술머신·비전머신으로 배우는 기술 [`pokemon:37#learnset_machine`] → 4. 식스테일 — 기본 정보 [`pokemon:37#profile`] → 5. 식스테일 — 종족치 [`pokemon:37#stats`]

### D03
- 원문: 이브이를 샤미드나 부스터로 진화시키려면 각각 어떤 돌을 써야 하나요?
- 실제 검색어: 이브이를 샤미드 또는 부스터로 진화시키려면 각각 어떤 진화의 돌을 사용해야 하나요?
- 변화 및 관찰: 돌을 진화의 돌로 풀어 썼다. 두 모델 모두 지정 앵커 1위와 top5 순서가 그대로다.
- **KURE 앵커 순위:** `pokemon:133#evolution` 1→1
  - 전: 1. 이브이 — 진화 [`pokemon:133#evolution`] → 2. 샤미드 — 진화 [`pokemon:134#evolution`] → 3. 부스터 — 진화 [`pokemon:136#evolution`] → 4. 쥬피썬더 — 진화 [`pokemon:135#evolution`] → 5. 이브이 — 획득처 [`pokemon:133#encounter`]
  - 후: 1. 이브이 — 진화 [`pokemon:133#evolution`] → 2. 샤미드 — 진화 [`pokemon:134#evolution`] → 3. 부스터 — 진화 [`pokemon:136#evolution`] → 4. 쥬피썬더 — 진화 [`pokemon:135#evolution`] → 5. 이브이 — 획득처 [`pokemon:133#encounter`]
- **SOLAR 앵커 순위:** `pokemon:133#evolution` 1→1
  - 전: 1. 이브이 — 진화 [`pokemon:133#evolution`] → 2. 샤미드 — 진화 [`pokemon:134#evolution`] → 3. 부스터 — 진화 [`pokemon:136#evolution`] → 4. 쥬피썬더 — 진화 [`pokemon:135#evolution`] → 5. 샤미드 — 종족치 [`pokemon:134#stats`]
  - 후: 1. 이브이 — 진화 [`pokemon:133#evolution`] → 2. 샤미드 — 진화 [`pokemon:134#evolution`] → 3. 부스터 — 진화 [`pokemon:136#evolution`] → 4. 쥬피썬더 — 진화 [`pokemon:135#evolution`] → 5. 샤미드 — 종족치 [`pokemon:134#stats`]

### D04
- 원문: 무지개 게임코너 교환소에서 캐이시를 받을 때, Red와 Blue의 코인 조건과 기록된 레벨은 어떻게 다른가요?
- 실제 검색어: 포켓몬 Red와 Blue의 무지개 게임코너 교환소에서 캐이시를 받을 때 필요한 코인 수와 기록된 레벨은 각각 어떻게 다른가요?
- 변화 및 관찰: 코인 조건을 코인 수로 구체화해 의미가 좁아졌을 가능성이 있다. 두 모델 지정 앵커는 1위 유지, KURE top5 동일, Solar 3·4위 교체.
- **KURE 앵커 순위:** `pokemon:63#encounter` 1→1
  - 전: 1. 캐이시 — 획득처 [`pokemon:63#encounter`] → 2. 폴리곤 — 획득처 [`pokemon:137#encounter`] → 3. 쁘사이저 — 획득처 [`pokemon:127#encounter`] → 4. 삐삐 — 획득처 [`pokemon:35#encounter`] → 5. 미뇽 — 획득처 [`pokemon:147#encounter`]
  - 후: 1. 캐이시 — 획득처 [`pokemon:63#encounter`] → 2. 폴리곤 — 획득처 [`pokemon:137#encounter`] → 3. 쁘사이저 — 획득처 [`pokemon:127#encounter`] → 4. 삐삐 — 획득처 [`pokemon:35#encounter`] → 5. 미뇽 — 획득처 [`pokemon:147#encounter`]
- **SOLAR 앵커 순위:** `pokemon:63#encounter` 1→1
  - 전: 1. 캐이시 — 획득처 [`pokemon:63#encounter`] → 2. 폴리곤 — 획득처 [`pokemon:137#encounter`] → 3. 미뇽 — 획득처 [`pokemon:147#encounter`] → 4. 삐삐 — 획득처 [`pokemon:35#encounter`] → 5. 쁘사이저 — 획득처 [`pokemon:127#encounter`]
  - 후: 1. 캐이시 — 획득처 [`pokemon:63#encounter`] → 2. 폴리곤 — 획득처 [`pokemon:137#encounter`] → 3. 삐삐 — 획득처 [`pokemon:35#encounter`] → 4. 미뇽 — 획득처 [`pokemon:147#encounter`] → 5. 쁘사이저 — 획득처 [`pokemon:127#encounter`]

### D05
- 원문: 피카츄에게 10만볼트를 머신으로 가르치려면 어떤 머신이 필요한가요? 그 머신을 얻는 것으로 기록된 장소와 방법 한 가지도 알려 주세요.
- 실제 검색어: 피카츄에게 10만볼트를 가르칠 수 있는 머신은 무엇이며, 그 머신을 얻는 것으로 기록된 장소와 획득 방법 한 가지는 무엇인가요?
- 변화 및 관찰: 두 부분 질문을 유지했다. KURE의 머신 획득 앵커가 5→3위로 상승해 전체@3을 회복했고 Solar 앵커 순위와 top5는 동일하다.
- **KURE 앵커 순위:** `pokemon:25#learnset_machine` 2→2; `pokemon:25#machine_acquisition` 5→3
  - 전: 1. 피카츄 — 획득처 [`pokemon:25#encounter`] → 2. 피카츄 — 기술머신·비전머신으로 배우는 기술 [`pokemon:25#learnset_machine`] → 3. 라이츄 — 진화 [`pokemon:26#evolution`] → 4. 붐볼 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:101#stab`] → 5. 피카츄 — 머신은 어디서 얻나요? [`pokemon:25#machine_acquisition`]
  - 후: 1. 피카츄 — 획득처 [`pokemon:25#encounter`] → 2. 피카츄 — 기술머신·비전머신으로 배우는 기술 [`pokemon:25#learnset_machine`] → 3. 피카츄 — 머신은 어디서 얻나요? [`pokemon:25#machine_acquisition`] → 4. 라이츄 — 진화 [`pokemon:26#evolution`] → 5. 붐볼 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:101#stab`]
- **SOLAR 앵커 순위:** `pokemon:25#learnset_machine` 2→2; `pokemon:25#machine_acquisition` 3→3
  - 전: 1. 피카츄 — 획득처 [`pokemon:25#encounter`] → 2. 피카츄 — 기술머신·비전머신으로 배우는 기술 [`pokemon:25#learnset_machine`] → 3. 피카츄 — 머신은 어디서 얻나요? [`pokemon:25#machine_acquisition`] → 4. 라이츄 — 진화 [`pokemon:26#evolution`] → 5. 붐볼 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:101#stab`]
  - 후: 1. 피카츄 — 획득처 [`pokemon:25#encounter`] → 2. 피카츄 — 기술머신·비전머신으로 배우는 기술 [`pokemon:25#learnset_machine`] → 3. 피카츄 — 머신은 어디서 얻나요? [`pokemon:25#machine_acquisition`] → 4. 라이츄 — 진화 [`pokemon:26#evolution`] → 5. 붐볼 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:101#stab`]

### D06
- 원문: 갸라도스가 전기·바위·땅 타입 기술을 받을 때 각각 기본 타입 상성 배율은 얼마인가요?
- 실제 검색어: 포켓몬 갸라도스가 전기·바위·땅 타입 기술을 받을 때 각각 기본 타입 상성 배율
- 변화 및 관찰: 질문을 검색 구문으로 바꿨다. 두 모델의 지정 방어 상성 앵커는 1위로 동일하며 하위 후보가 달라졌다.
- **KURE 앵커 순위:** `pokemon:130#defense_matchup` 1→1
  - 전: 1. 갸라도스 — 방어 상성 (약점과 저항) [`pokemon:130#defense_matchup`] → 2. 갸라도스 — 공격 상성 (갸라도스와 같은 타입 기술이 잘 통하는 타입) [`pokemon:130#attack_matchup`] → 3. 갸라도스 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:130#stab`] → 4. 파라스 — 방어 상성 (약점과 저항) [`pokemon:46#defense_matchup`] → 5. 라프라스 — 방어 상성 (약점과 저항) [`pokemon:131#defense_matchup`]
  - 후: 1. 갸라도스 — 방어 상성 (약점과 저항) [`pokemon:130#defense_matchup`] → 2. 갸라도스 — 공격 상성 (갸라도스와 같은 타입 기술이 잘 통하는 타입) [`pokemon:130#attack_matchup`] → 3. 갸라도스 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:130#stab`] → 4. 파라스 — 방어 상성 (약점과 저항) [`pokemon:46#defense_matchup`] → 5. 투구푸스 — 방어 상성 (약점과 저항) [`pokemon:141#defense_matchup`]
- **SOLAR 앵커 순위:** `pokemon:130#defense_matchup` 1→1
  - 전: 1. 갸라도스 — 방어 상성 (약점과 저항) [`pokemon:130#defense_matchup`] → 2. 갸라도스 — 공격 상성 (갸라도스와 같은 타입 기술이 잘 통하는 타입) [`pokemon:130#attack_matchup`] → 3. 라프라스 — 방어 상성 (약점과 저항) [`pokemon:131#defense_matchup`] → 4. 갸라도스 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:130#stab`] → 5. 프테라 — 공격 상성 (프테라와 같은 타입 기술이 잘 통하는 타입) [`pokemon:142#attack_matchup`]
  - 후: 1. 갸라도스 — 방어 상성 (약점과 저항) [`pokemon:130#defense_matchup`] → 2. 갸라도스 — 공격 상성 (갸라도스와 같은 타입 기술이 잘 통하는 타입) [`pokemon:130#attack_matchup`] → 3. 갸라도스 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:130#stab`] → 4. 갸라도스 — 기본 정보 [`pokemon:130#profile`] → 5. 꼬마돌 — 공격 상성 (꼬마돌과 같은 타입 기술이 잘 통하는 타입) [`pokemon:74#attack_matchup`]

### D07
- 원문: 7번도로의 야생 등장 기록에서 가디와 식스테일은 각각 어느 버전에 기록되어 있고, 레벨은 얼마인가요?
- 실제 검색어: 7번도로 야생 포켓몬 등장 기록에서 가디와 식스테일은 각각 어느 버전에 등장하며 레벨은 얼마인가요?
- 변화 및 관찰: ‘기록되어’를 ‘등장하며’로 바꾸어 실제 등장으로 읽힐 가능성이 있으나 기록 범위는 남았다. KURE 가디 앵커는 2→3위, Solar는 3위 유지다.
- **KURE 앵커 순위:** `pokemon:58#encounter` 2→3; `pokemon:37#encounter` 1→1
  - 전: 1. 식스테일 — 획득처 [`pokemon:37#encounter`] → 2. 가디 — 획득처 [`pokemon:58#encounter`] → 3. 식스테일 — 기본 정보 [`pokemon:37#profile`] → 4. 딱충이 — 획득처 [`pokemon:14#encounter`] → 5. 단데기 — 획득처 [`pokemon:11#encounter`]
  - 후: 1. 식스테일 — 획득처 [`pokemon:37#encounter`] → 2. 식스테일 — 기본 정보 [`pokemon:37#profile`] → 3. 가디 — 획득처 [`pokemon:58#encounter`] → 4. 딱충이 — 획득처 [`pokemon:14#encounter`] → 5. 단데기 — 획득처 [`pokemon:11#encounter`]
- **SOLAR 앵커 순위:** `pokemon:58#encounter` 3→3; `pokemon:37#encounter` 1→1
  - 전: 1. 식스테일 — 획득처 [`pokemon:37#encounter`] → 2. 식스테일 — 기본 정보 [`pokemon:37#profile`] → 3. 가디 — 획득처 [`pokemon:58#encounter`] → 4. 망키 — 획득처 [`pokemon:56#encounter`] → 5. 식스테일 — 진화 [`pokemon:37#evolution`]
  - 후: 1. 식스테일 — 획득처 [`pokemon:37#encounter`] → 2. 식스테일 — 기본 정보 [`pokemon:37#profile`] → 3. 가디 — 획득처 [`pokemon:58#encounter`] → 4. 망키 — 획득처 [`pokemon:56#encounter`] → 5. 꼬렛 — 획득처 [`pokemon:19#encounter`]

### D08
- 원문: 리자몽이 자신의 타입과 같은 일반적인 공격 기술을 사용할 때 적용되는 자속 보정은 얼마이고, 해당 타입은 무엇인가요?
- 실제 검색어: 리자몽이 자신의 타입과 같은 일반적인 공격 기술을 사용할 때 적용되는 자속 보정 배율은 얼마이며, 리자몽의 해당 타입은 무엇인가요?
- 변화 및 관찰: 자속 보정을 배율로 명확히 했다. 두 모델의 지정 앵커는 1위로 같고 하위 후보는 바뀌었다.
- **KURE 앵커 순위:** `pokemon:6#stab` 1→1
  - 전: 1. 리자몽 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:6#stab`] → 2. 미뇽 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:147#stab`] → 3. 신뇽 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:148#stab`] → 4. 메타몽 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:132#stab`] → 5. 라이츄 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:26#stab`]
  - 후: 1. 리자몽 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:6#stab`] → 2. 미뇽 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:147#stab`] → 3. 신뇽 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:148#stab`] → 4. 리자드 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:5#stab`] → 5. 메타몽 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:132#stab`]
- **SOLAR 앵커 순위:** `pokemon:6#stab` 1→1
  - 전: 1. 리자몽 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:6#stab`] → 2. 메타몽 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:132#stab`] → 3. 미뇽 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:147#stab`] → 4. 시라소몬 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:106#stab`] → 5. 망나뇽 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:149#stab`]
  - 후: 1. 리자몽 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:6#stab`] → 2. 메타몽 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:132#stab`] → 3. 리자드 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:5#stab`] → 4. 시라소몬 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:106#stab`] → 5. 망나뇽 — 자속 보정 (같은 타입 기술 1.5배) [`pokemon:149#stab`]

### D09
- 원문: 영문 Red·Blue에서 리아코의 종족치를 알려 주세요.
- 실제 검색어: 영문 Red·Blue에서 리아코의 종족치를 알려 주세요.
- GPT 원본 출력(검색에 미사용): 영문 Pokémon Red·Blue에서 리아코(Totodile)의 종족치는 얼마인가요?
- 변화 및 관찰: 제공자 출력의 추가 영문 이름 Totodile 및 Pokémon은 금지된 새 표기여서 검토 후 원문으로 대체했다. 검색어가 같은 것과 결과가 같은 것은 별개이며, 실제 top5는 두 모델 각각 전후 같다.
- **KURE 앵커 순위:** 해당 없음(점수 제외)
  - 전: 1. 캥카 — 진화 [`pokemon:115#evolution`] → 2. 럭키 — 진화 [`pokemon:113#evolution`] → 3. 스라크 — 진화 [`pokemon:123#evolution`] → 4. 덩쿠리 — 진화 [`pokemon:114#evolution`] → 5. 루주라 — 진화 [`pokemon:124#evolution`]
  - 후: 1. 캥카 — 진화 [`pokemon:115#evolution`] → 2. 럭키 — 진화 [`pokemon:113#evolution`] → 3. 스라크 — 진화 [`pokemon:123#evolution`] → 4. 덩쿠리 — 진화 [`pokemon:114#evolution`] → 5. 루주라 — 진화 [`pokemon:124#evolution`]
- **SOLAR 앵커 순위:** 해당 없음(점수 제외)
  - 전: 1. 럭키 — 진화 [`pokemon:113#evolution`] → 2. 스라크 — 진화 [`pokemon:123#evolution`] → 3. 덩쿠리 — 진화 [`pokemon:114#evolution`] → 4. 루주라 — 진화 [`pokemon:124#evolution`] → 5. 마임맨 — 진화 [`pokemon:122#evolution`]
  - 후: 1. 럭키 — 진화 [`pokemon:113#evolution`] → 2. 스라크 — 진화 [`pokemon:123#evolution`] → 3. 덩쿠리 — 진화 [`pokemon:114#evolution`] → 4. 루주라 — 진화 [`pokemon:124#evolution`] → 5. 마임맨 — 진화 [`pokemon:122#evolution`]

### D10
- 원문: 영문 Red·Blue에서 피카츄의 종족별 포획률 수치는 얼마인가요?
- 실제 검색어: 영문 Red·Blue에서 피카츄의 종족별 포획률 수치는 얼마인가요?
- GPT 원본 출력(검색에 미사용): 영문 Pokémon Red·Blue에서 피카츄(Pikachu)의 종족별 포획률(base catch rate)은 얼마인가요?
- 변화 및 관찰: 제공자 출력이 Pikachu, base catch rate, Pokémon 등 새 영문 표기와 해석을 추가하여 검토 후 원문으로 대체했다. 실제 top5는 양 모델 각각 전후 같다.
- **KURE 앵커 순위:** 해당 없음(점수 제외)
  - 전: 1. 피카츄 — 기본 정보 [`pokemon:25#profile`] → 2. 피카츄 — 획득처 [`pokemon:25#encounter`] → 3. 피카츄 — 종족치 [`pokemon:25#stats`] → 4. 피카츄 — 레벨업으로 배우는 기술 [`pokemon:25#learnset_level`] → 5. 피카츄 — 기술머신·비전머신으로 배우는 기술 [`pokemon:25#learnset_machine`]
  - 후: 1. 피카츄 — 기본 정보 [`pokemon:25#profile`] → 2. 피카츄 — 획득처 [`pokemon:25#encounter`] → 3. 피카츄 — 종족치 [`pokemon:25#stats`] → 4. 피카츄 — 레벨업으로 배우는 기술 [`pokemon:25#learnset_level`] → 5. 피카츄 — 기술머신·비전머신으로 배우는 기술 [`pokemon:25#learnset_machine`]
- **SOLAR 앵커 순위:** 해당 없음(점수 제외)
  - 전: 1. 피카츄 — 기본 정보 [`pokemon:25#profile`] → 2. 피카츄 — 획득처 [`pokemon:25#encounter`] → 3. 피카츄 — 종족치 [`pokemon:25#stats`] → 4. 피카츄 — 레벨업으로 배우는 기술 [`pokemon:25#learnset_level`] → 5. 피카츄 — 기술머신·비전머신으로 배우는 기술 [`pokemon:25#learnset_machine`]
  - 후: 1. 피카츄 — 기본 정보 [`pokemon:25#profile`] → 2. 피카츄 — 획득처 [`pokemon:25#encounter`] → 3. 피카츄 — 종족치 [`pokemon:25#stats`] → 4. 피카츄 — 레벨업으로 배우는 기술 [`pokemon:25#learnset_level`] → 5. 피카츄 — 기술머신·비전머신으로 배우는 기술 [`pokemon:25#learnset_machine`]

## 재현

저장소 루트에서 `PYTHONDONTWRITEBYTECODE=1 python results/rewrite-retrieval-dev-10-v1/score_offline.py --check` 및 `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s results/rewrite-retrieval-dev-10-v1 -p test_score_offline.py -v`를 실행한다. 이 스크립트는 고정된 기록만 읽으며 DB·네트워크에 접속하지 않는다.

- 원문 결과 SHA-256: `214d77577c1a61a3d00d8a6a31e5ed5f51f2c8778ce1063ef62b6e97b36095d5`
- 리라이트 결과 SHA-256: `68ad7cc2f55544a0debedb5c099b2709046b60dd932acb30b206b12f26447cd6`
- 실제 검색어 SHA-256: `cf7d9bf848225ae52792718ff632f0d242f6a22e8f3b852b8484048994a7a158`
- 질문 SHA-256: `d926f26b383b0f7ed2ea540a3a365895461ccc8619e4fbf7a2017e79b36813e1`
- 공급자 리라이트 SHA-256: `09e58a4345f43fb37958ce798e4580143444c30e31fb9dfea4bcf227d6b66609`
- 청크 스냅샷 SHA-256: `b976ed9d0d6f88dc1c2ad875af11cf4f3556a0f0c7f4fab888ca324376a9ba54`
- 리라이트 검색 실행 설정의 canonical JSON SHA-256: `fcece6d18ab4b0092b7d36e601966bc5012c90f0ad5fe6e631b59f4b3ecbd072`; 파일 자체의 config.json 해시와는 다르다. 주요 실제 실행 코드의 기록 해시는 score.json에 보존하고 core·live·hybrid·previous 네 파일은 현재 바이트와 대조했다.
