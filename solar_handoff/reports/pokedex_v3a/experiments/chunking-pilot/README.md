# 3문서 청킹 후보 — 격리 파일럿

이 폴더는 `pokedex_v3a`의 pending 문서 **118·129·151**만 다룬다. 별도 허가된 로컬 DB와 로컬·외부 API 모델을 사용한 검색 파일럿이 완료됐다. 당시 파일럿 허가는 문서 사실에 대한 사람의 검토·승인이나 운영 인덱싱 허가가 아니었다. 151개 문서의 기존 등록부는 계속 pending이며 후속 승인 기록은 [승인 overlay](../../chunks/approval-overlay.md)를 따른다. 평가 질의·정답은 청크 생성기의 입력이 아니다.

## 실행 결과와 판정

- A 29개와 B 48개는 청킹 변형이지 정식 검색 방식 A/B가 아니다. 118·129·151 문서와 같은 질문을 접두사 없이 사용해 3모델 exact cosine k=5 검색을 비교했다. 15문항 중 범위 밖 CP15를 제외한 14문항의 **완전 근거** 결과다. 여러 앵커가 모두 발견된 최초 순위를 쓰고 미스의 역순위는 0이다.

| 모델 | 청크 | Hit@1 | Hit@3 | Hit@5 | MRR@5 |
| --- | --- | ---: | ---: | ---: | ---: |
| KURE | A | 12/14 | 14/14 | 14/14 | 0.928571 |
| KURE | B | 8/14 | 13/14 | 14/14 | 0.755952 |
| Gemma | A | 8/14 | 12/14 | 14/14 | 0.734524 |
| Gemma | B | 8/14 | 11/14 | 13/14 | 0.702381 |
| OpenAI | A | 7/14 | 10/14 | 13/14 | 0.645238 |
| OpenAI | B | 6/14 | 10/14 | 10/14 | 0.535714 |

- B는 Gemma CP09, OpenAI CP03·CP09·CP12·CP14에서 A의 Hit@5 적중이 미스로 바뀌어 무회귀 게이트를 충족하지 못한다. KURE B는 Hit@5 회귀는 없지만 개선도 없고 상위 순위가 악화됐다. 사용자는 이 소규모 결과와 전체 10주제·예외 설명을 보고 **제목 기반 A안을 전체 청킹 설계로 확정**했다. KURE A는 이 3문서·14문항·동일 입력·무접두사 조건에서만 유망하며 일반 모델 순위나 별도 held-out 평가가 아니다.
- 당시 A안 확정은 원본 문서의 사실 검토·승인 상태 변경, 임베딩 모델 최종 선택, 151문서 청크 생성 요청이나 운영 인덱싱 승인이 아니었다. 이후 별도 사용자 허가로 [전체 오프라인 초안](../../chunks/README.md) 1,504개가 생성됐고, 후속 전체 승인 의사의 서명 없는 별도 기록도 생성·읽기 검증됐다. 기존 문서 등록부와 청크는 모두 pending이며 독립 인증·최신 신뢰·철회 관리는 미구현이다. 전체 운영 적재와 이 3문서 실험은 별개이며 상세는 [승인 overlay](../../chunks/approval-overlay.md)를 따른다. 향후 표 추가 분할 등 경계 변경에는 별도 재평가와 사용자 의사결정이 필요하다.
- Gemma `embeddinggemma-2:bf16`은 768차원·`chunking_pilot_3doc_v1`, KURE `kure-v1:f32`는 1024차원·`chunking_pilot_kure_v1`, OpenAI `text-embedding-3-small`은 1536차원·`chunking_pilot_openai_v1` 기록이다. KURE는 `truncate:false` 요청이지만 서버 내부 변환·잘림은 보이지 않는다. OpenAI에는 청크와 질문 원문이 외부 API로 전송됐으며 사용량 미기록으로 비용은 알 수 없다. 모델 revision은 불변으로 보장되지 않는다.
- CP15는 점수 분모에서 제외했다. 답변 생성과 범위 밖 거절은 평가하지 않았다. 질의·정답 앵커는 `queries/`, Gemma 원본은 `results/raw_search_v1.json`, 세 모델의 상세 독립 채점은 [score.md](multimodel-v1/eval/comparison-v1/score.md)와 `multimodel-v1/eval/comparison-v1/score.json`에 있다. KURE·OpenAI 실제 원본은 `multimodel-v1/results/real-v1/`에 있으며 `results/kure/`, `results/openai/`는 보존할 모의 자료다. 실제 결과 디렉터리의 `pending`은 성공 후에도 남는다.
- 파일 외 DB에 테스트 스키마와 클러스터 전역 NOLOGIN 역할이 존재한다. DB는 로컬 전용이며 스키마·역할·데이터와 파일 기록은 별도 사용자 승인 없이 삭제하지 않는다. 자세한 제한은 [storage](storage.md), [loader](loader.md) 참조.

`multimodel-v1/results/kure/`와 `multimodel-v1/results/openai/`의 모의 산출물 6개는 로컬에만 보존하며 Git에 커밋하거나 공유하지 않는다. 재현에 필요한 파일럿 청크와 실제 결과는 사용자 지정 생성물 예외다. 모의 파일은 [별도 안내](multimodel-v1/MOCK_RESULTS_NOTICE.md)를 따른다.

## 파일럿 후보와 확정 A 규칙 (pilot-chunks-v2)

- **A:** 고정 제목과 순서에 따른 기존 v3a 절 단위. 문서 제목과 상위 제목을 제외한 본문에 `{이름} — {절 제목}`을 붙인다. `## 기술`과 `## 타입 · 상성`의 첫 하위 제목 앞 본문은 각각 첫 자식 청크에 배정한다. 프로필은 `기본 정보`. 코드 펜스 내부 제목은 무시한다. 129번은 원본 Red·Blue 머신 습득 데이터가 비어 있어 머신 획득처 절을 생략한다. 001은 저장된 v3a 파일럿 본문과 비교하는 메모리 전용 테스트이며 출력하지 않는다.
- **B:** A와 같은 절에서 `encounter`, `learnset_machine`, `machine_acquisition`에 표 본문 행이 **10개를 초과**하는 경우에만, 원문 순서의 연속된 최대 10행씩 분할한다. 10행 이하는 그대로, 다른 절도 그대로다. 표가 여러 개이거나 모호하면 실패한다. 각 분할은 같은 이름·주제와 표 머리글·해당 행을 포함한다. 제목 머리말 뒤에 생성된 안내문 `이 표는 원문 표의 일부입니다. 요약과 주의문은 원문 전체의 설명입니다.`을 넣는다. 이 문장은 게임 사실이나 원문 인용이 아닌 분할 맥락이다. 원문의 도입·요약·한계·표 뒤 문장은 각 분할에 반복한다. 표 뒤 문장을 포함한 비빈 원문 줄은 보존한다. 공유 도입·표 머리글·주석 중복은 허용하지만 데이터 행은 각 후보 안에서 정확히 한 번씩 보존한다.
- A ID는 `pokemon:{id}#{section}`, B의 분할 ID는 `pokemon:{id}#{section}:rows-001-010`과 같다. A와 B는 별도 JSONL 네임스페이스이고 같은 ID라도 동일 저장 네임스페이스에 합치지 않는다. 모든 청크에 정확한 설정의 SHA-256을 기록한다. 행 번호는 해당 절의 표 본문 기준 1부터 시작한다. 규칙 변경은 새 설정과 별도 버전이 필요하다.

확정 A의 전체 주제는 `profile`, `stats`, `evolution`, `learnset_level`, `learnset_machine`, `machine_acquisition`, `stab`, `attack_matchup`, `defense_matchup`, `encounter`다. 표·주의문을 포함한 원문 절을 보존하고 긴 표도 자동 분할하지 않는다. 머신 습득 기록이 없는 10·11·13·14·129·132번은 `machine_acquisition`만 생략하며 `learnset_machine`은 유지한다. 빈 획득 기록은 획득 불가의 증거가 아니다. 당시 151종 × 10 − 6 = **1,504**는 잠재 산술값이었다. 이후 별도 허가로 생성된 1,504개 오프라인 초안과 검증 범위는 [초안 기록](../../chunks/README.md)을 따른다. 상세 기준은 [chunking 스킬](../../../.claude/skills/chunking/SKILL.md)을 따른다.

각 청크는 `games: ["red", "blue"]`, `version_group: "red-blue"`와 `review_status: "pending"`, `index_eligible: false`를 명시한다. `source_lines`는 1부터 시작하는 실제 문서의 본문 줄 번호, `source_heading_lines`는 제거된 제목 줄이다. 새 안내문은 원문 줄이 아니므로 `source_lines`에 없다. 분할된 `table_rows`는 행 서수·정확한 문서 줄·원문 행을 제공한다. `evidence_path`, `evidence_sha256`, `evidence_sections`, `evidence_reference_indexes`는 근거 파일의 0부터 시작하는 `references` 인덱스와 의존 절을 가리킨다. **행은 정확한 원문 줄로 인용되지만 정제 데이터 레코드에 일대일 연결된 것으로 주장하지 않는다**: 근거 인덱스는 해당 절과 그 의존성에 대한 보수적인 집합이다. 후속 인용기는 이 구분을 유지하고 실제 행별 의미 검증을 별도로 해야 한다.

`chunks/manifest-v2.json`은 원문·근거·스냅샷 입력의 SHA-256, 코드·테스트 해시, 설정 지문 및 출력 해시·건수를 기록한다. 검색 실험에는 `chunks/A-v2.jsonl`과 `chunks/B-v2.jsonl`만 사용한다. 이전 `A.jsonl`, `B.jsonl`, `manifest.json`은 v1 보존본으로 그대로 남기며 v2와 섞지 않는다. canonical snapshot evidence 검증기(`pokedex_v3a/scripts/v3a_document_evidence.py`)로 출처 해시와 참조 ID·포인터를 검증한다. 제목·공백 처리는 같은 스냅샷의 `v3a_pilot_evidence.py`와 프로젝트 chunking 규칙에서 최소 포팅했다. 상위 저장소 `scripts/helper`는 가져오지 않는다. 해당 스냅샷의 코드와 데이터가 필요하며 폴더 단독이 아닌 `pokedex_v3a` 사본에서 실행한다.

기존 `reports/token_lengths.json`은 이전 감사 기록이며 v2의 분할 안내문 토큰 길이를 측정한 결과가 아니다. `scripts/audit_tokens.py`도 저장된 v1 A를 참조하므로 v2 토큰 감사 도구로 간주하지 않는다.
기존 [v2 토큰 감사 기록](reports/token_lengths_v2.json)은 전체 151문서의 절 후보 1,504개를 점검한 기록이다. 당시 감사나 설계 결정은 전체 코퍼스 청크나 운영 산출물 생성 완료를 뜻하지 않았다. 이후 별도 허가된 [오프라인 초안과 감사](../../chunks/README.md)가 존재하며, 후속 승인 의사의 별도 기록과 운영 준비의 한계는 [승인 overlay](../../chunks/approval-overlay.md)를 따른다.

## 실행 (저장소 루트)

```bash
python pokedex_v3a/experiments/chunking-pilot/scripts/prepare_chunks.py --check
python -m unittest discover -s pokedex_v3a/experiments/chunking-pilot/tests -v
```

생성과 테스트는 `TMPDIR`에 임시 파일을 생성하므로 실행자가 허용된 scratch 경로로 지정한다. 최초 생성은 `--check` 없이 실행하며 v2 출력 파일이 하나라도 있으면 중단한다. `--check`는 3문서 파일럿 v2 A/B/manifest 전체만 재생성해 바이트 비교하며 전체 초안을 검증하지 않는다. v1 재현 검사는 아니다. 자동 정리나 덮어쓰기는 하지 않는다. 실행에는 표준 라이브러리 및 같은 스냅샷 코드만 사용한다. 테스트나 검색 결과는 독립 평가자가 별도 판정한다.
