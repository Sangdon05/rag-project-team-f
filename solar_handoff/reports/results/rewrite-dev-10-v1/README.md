# 개발 질문 리라이트 10건 (오프라인 구현)

질문 파일 `results/vector-dev-10-v1/questions.json`의 SHA-256을 고정한다. 답안·평가 앵커·청크를 읽거나 전송하지 않는다. GPT Responses API에는 공통 지시문과 질문 한 건만 전송하고 qid는 전송하지 않는다. `config.json`에서 `gpt-6-luna`, reasoning low, store/stream false, truncation disabled를 고정하며 temperature는 보내지 않는다. GPT 설정은 결정적 결과를 보장하지 않는다. GPT 사용 시 과금될 수 있으며 비용은 미확인으로 저장한다.

## 검증과 실행

프로젝트 환경에서 `python-dotenv`가 필요하다. 승인된 scratch 경로를 TEMP/TMP/TMPDIR로 지정하고 아래를 실행한다 (Windows git-bash). 테스트는 실제 질문과 모의 응답만 사용하며 외부 호출은 없다.

```sh
export TEMP='C:/Users/lexus/AppData/Local/hermes/profiles/blank/cache/scratch'
export TMP="$TEMP" TMPDIR="$TEMP"
cd results/rewrite-dev-10-v1
python -B -m unittest -v test_runner
python -B runner.py preflight
python -B runner.py run
```

`preflight`는 API를 호출하지 않는다. `run`은 부모가 독립 확인 후 실행한다. API 키는 프로세스 환경의 `OPENAI_API_KEY` 또는 저장소 루트 `.env`에서 읽으며 출력·저장하지 않는다. API 키뿐 아니라 환경과 `.env`의 알려진 인증정보 유사 값에 대해 질문, 송신 본문, 결과, 로그, 파일 경로 및 소스 파일을 검사한다. 충돌하면 예외 없이 중단하므로 짧거나 일반적인 값도 실행을 막을 수 있다. 키·환경 내용은 출력하지 않는다. 기존 산출물이 하나라도 있으면 실행 및 재개가 거부되므로 보존하고 별도 판단을 받는다.

질문별 요청 파일, fsync된 호출 시작 이벤트, 원본 응답 및 결과를 배타 생성한다. 호출 타임아웃 등 결과 불명은 즉시 중단하며 재시도나 원문 대체를 하지 않는다. HTTP 오류, 미완료 및 안전하게 기록할 수 없는 응답도 중단한다. 완료된 응답의 거절·형식 오류·빈 출력·UTF-8 한도 초과는 이유를 기록하고 원문으로 대체한다. 비밀 충돌이 포함된 응답은 유출 방지를 위해 원본을 저장하지 않고 중단한다.

10건 모두 처리한 경우에만 `rewritten_queries.json`을 배타 생성한다. 입력 순서의 각 항목은 `qid`, `original_question`, `search_query`, `status`만 가진다. 검색부는 동일한 `search_query`를 BM25와 각 모델의 질의 임베딩에 쓰고 리랭커는 `original_question`을 사용해야 한다. 이 폴더는 검색·임베딩·리랭킹·답변 생성을 구현하거나 호출하지 않는다.

형식 검사는 의미 보존이나 새 대상 추가 방지를 증명하지 못한다. 모든 리라이트와 fallback을 독립 사람 평가자가 원문과 대조해야 한다. 개체 검증 규칙이나 평가 정답을 사용하지 않는다. 이 구현의 오프라인 테스트는 실제 모델 API 호환성·출력 품질을 입증하지 않는다.
