# 독립 멀티모델 검색 채점

상태: 사용자 승인 후 KURE·OpenAI 실제 검색 결과와 기존 Gemma 결과를 독립 채점했다. 결과는 [comparison-v1/score.md](comparison-v1/score.md)와 `comparison-v1/score.json`에 있다. `results/kure/`, `results/openai/`는 보존할 모의 파일이므로 채점 대상으로 쓰지 않는다. 회귀 테스트는 파일이 있는 경우 읽기 전용으로 거부 여부를 확인한다. 검색은 `multimodel-v1/run.py` 소유이며 이 채점기는 DB·API·모델·네트워크·`.env`에 접근하지 않는다.

모의 디렉터리의 산출물 6개는 로컬에만 보존하며 Git에 커밋하거나 공유하지 않는다. 재현에 필요한 청크와 실제 파일럿 결과만 사용자 지정 생성물 예외다. 자세한 내용은 [모의 결과 안내](../MOCK_RESULTS_NOTICE.md)를 따른다.

## 실제 실행 후 채점

독립 평가자가 `results/real-v1/kure/`와 `results/real-v1/openai/` 각각에 실제 실행의 `raw_search_v1.json`, `vector_manifest_v1.json`이 완전히 생성되었는지, 실행 이력과 보존 상태를 확인한 뒤 raw 파일 바이트의 SHA-256을 별도로 동결한다. 해시만으로 실제 실행 또는 출처 진위를 증명할 수 없다. `pending`은 성공 후에도 남으므로 완료의 증거가 아니다. 입력의 진위는 운영자가 별도 확인해야 한다. 원본·모의 파일은 수정하지 않는다.

저장소 루트에서 `<...>`를 독립 동결한 **64자리 소문자 SHA-256**으로 교체하고, 사용하지 않은 출력 버전명을 지정한다:

```sh
export PYTHONDONTWRITEBYTECODE=1 TMP="$TMPDIR" TEMP="$TMPDIR"
python pokedex_v3a/experiments/chunking-pilot/multimodel-v1/eval/score_models.py --kure-sha256 <KURE_RAW_SHA256> --openai-sha256 <OPENAI_RAW_SHA256> --output-version <NEW_OUTPUT_VERSION>
```

기존 출력 디렉터리는 덮어쓰지 않는다. `comparison-v1`은 이미 존재하므로 재실행 시 새 출력 버전이 필요하다. `eval/comparison-v1/score.json`, `score.md`에 각각 상세 증거·요약을 저장했다. 출력 도중 실패하면 부분 디렉터리가 남을 수 있으므로 보존하고 새 버전명으로 처리한다. CLI는 명시된 `results/real-v1` 경로만 사용한다. 두 새 raw의 해시와 파일 내부 config 해시, 모델·차원·query prefix·truncate·검색 설정, 공개 질문 및 청크/manifest 링크, 30개 행·각 5개 후보의 ID·원문/근거 메타데이터 및 content hash, 77개 벡터 manifest 레코드와 canonical manifest 해시를 검사한다. 원래 채점기의 고정 입력·원문·출처 포인터 검증과 기존 Gemma 점수 재계산 일치 검사도 수행한다.

raw에는 `run_type: real`과 KURE는 `provider: ollama`, OpenAI는 `provider: openai`가 필수다. 이 필드는 임의로 바꿀 수 있으므로 필드·해시·경로가 모두 맞아도 실제 실행이나 출처의 진위를 입증하지 못한다. 별도의 실행 이력 확인과 외부에서 동결한 해시가 필요하다.

## 점수와 한계

동일 원문 문서, 줄 번호, 실제 청크 본문이 모두 일치해야 각 앵커를 찾은 것으로 센다. 첫 완전 순위는 모든 앵커의 최초 순위 중 최댓값이고, 완전 Hit@1/3/5와 MRR@5의 분모는 14다. CP15는 범위 밖으로 별도 보존하고 거절 성공으로 세지 않는다. JSON은 후보별 근거와 Gemma 대비 및 모델별 A/B 순위·Hit@5 변화를 기록한다. 이 A/B는 청킹 변형이지 정식 검색 방법 A/B가 아니다. 모델 간 원시 유사도는 비교하지 않고, 검색 품질·답변 품질이나 모델의 전반적인 우열을 주장하지 않는다. OpenAI 모델 digest는 런타임 기록에 없어 null이다. 실제 서버 내부의 자동 프롬프트·잘림 및 벡터가 실제 모델에서 나온 사실은 오프라인 파일만으로 확인할 수 없다.

## 재현 테스트

```sh
export PYTHONDONTWRITEBYTECODE=1 TMP="$TMPDIR" TEMP="$TMPDIR"
python -m unittest discover -s pokedex_v3a/experiments/chunking-pilot/multimodel-v1/eval -p 'test_*.py' -v
python -m unittest discover -s pokedex_v3a/experiments/chunking-pilot/tests -p 'test_score_pilot.py' -v
python pokedex_v3a/experiments/chunking-pilot/scripts/score_pilot.py --check
```

테스트는 고정 Gemma 입력에서 파생한 **합성** KURE/OpenAI 레코드를 메모리와 `$TMPDIR`에서만 만들며, 실측 성능이나 실제 실행으로 취급하지 않는다. 기존 모의 파일이 없으면 해당 회귀 테스트는 건너뛴다.
