# 답변 생성 소량 시험 실행기

실제 12건 생성은 `real-v1/events.jsonl`에 보존됐다. 독립 근거 대조와 실행 조건은 [보고서](report.md)를 참고한다. 사람 채점은 pending이며 공식 평가는 아니다.

이 실제 실험은 아래 실행기의 비밀 문자열 이스케이프 누락 보안 수정 전에 수행됐다. 실행 기록에는 당시 runner 코드 해시가 없어 정확한 실행 버전을 증명할 수 없다. 수정된 현재 runner의 해시는 이전 코드와 다르며, 현재 코드로 재실행하는 것은 기존 실행을 그대로 재현했다는 증거가 아니다. 기존 입력과 이벤트 기록은 수정하지 않았다.

검색은 실행하지 않는다. 준비된 입력 6건(A/B × D05/D09/D10) 각각에 두 모델을 호출하므로 완료 시 생성 요청은 총 12건이다. 동일 case의 질문·5청크 텍스트·한국어 시스템 지침은 두 모델에 동일하며, A/B의 청크는 다를 수 있다. 실험 결과의 품질과 근거는 독립 평가자가 판단한다. 이 폴더는 공식 평가셋이 아니다.

## 설정과 실행 (추후 별도 승인 후)

`config.example.json`은 환경 변수 이름과 정책만 담는다. `OPENAI_CHAT_MODEL`, `OLLAMA_CHAT_MODEL`에 각각 사용자가 선택한 실제 모델 ID를 환경변수로 주고, `OPENAI_API_KEY`는 비밀 관리 방식으로 현재 프로세스에만 제공한다. 이 세 설정 키는 각각 해당 이름만 허용한다. 모델명과 키를 설정 파일이나 명령행에 넣지 않는다. 네트워크, 비용 및 입력의 외부 전송은 실행 전에 별도로 확인한다.

다음 변수에 입력 생성자가 확인한 **실제 경로**를 넣고 실행한다. 네 원본은 `inputs.json`의 `source_sha256` 네 항목에 각각 대응한다. 입력·원본의 경로는 공개되지 않았으므로 아래는 실행 템플릿이다. `OUTPUT_DIR`은 부모 디렉터리가 이미 존재하는, 아직 존재하지 않는 새 디렉터리여야 한다. 값에 꺾쇠괄호를 입력하지 않는다.

```sh
python results/answer-generation-smoke-v1/runner.py \
  --input "$INPUT_JSON" --config "$CONFIG_JSON" --output "$OUTPUT_DIR" \
  --a-raw "$A_RAW" --b-raw "$B_RAW" --questions "$QUESTIONS" --chunks "$CHUNKS"
```

`config.example.json`을 직접 지정하거나 승인된 설정을 별도 경로에 준비한다. OpenAI는 고정 공식 TLS Responses 엔드포인트, `reasoning.effort=low`, `store=false`, `stream=false`, `max_output_tokens`를 사용하고 temperature/top_p를 보내지 않는다. Ollama는 `127.0.0.1` 또는 `::1` HTTP 원점만 허용하며 `temperature=0`, `num_predict`, `num_ctx`, `stream=false`를 보낸다. 정수 설정 범위는 `max_output_tokens` 1–4096, `num_ctx` 1–32768, `timeout_seconds` 1–300이다. 프록시와 리디렉션은 비활성화하고 각 HTTP 응답 본문은 최대 16 MiB로 제한한다. 설정된 HTTP 타임아웃은 소켓 작업에 적용되며 전체 요청에 대한 엄격한 벽시계 시간 제한은 아니다. 양쪽 모델 설정을 기록한 후 첫 OpenAI 요청 전에 `/api/tags`로 선택한 로컬 모델의 digest를 확인·기록한다. 각 case의 첫 OpenAI 요청 전에도 digest를 확인해 변경되거나 조회에 실패하면 해당 case의 양쪽 생성 요청을 보내지 않는다. 로컬 생성 전후에도 다시 조회한다. 중간에 변경될 가능성을 원자적으로 차단하지는 못한다. OpenAI 모델 alias가 불변이라는 보장은 없고, 응답이 제공한 실제 model 값도 별도로 기록한다. num_ctx/max output이 충분한지는 모델별 별도 확인이 필요하다.

## 보존 및 안전 정책

입력은 스키마에 없는 키를 거부하고 네 원본 바이트 SHA-256을 확인한 뒤 같은 바이트를 파싱한다. 6건의 질문은 qid별 질문 원본, 순서와 ID는 Gemma A raw `results` 또는 B raw `final_top5`, 본문·메타데이터는 중복 ID가 없는 청크 스냅샷과 각각 대조한다. 관련 raw 메타데이터와 두 raw의 index_version도 확인한다. 원본 문서 자체는 읽거나 해시 검증하지 않는다. 입력과 원본 및 해시를 모두 함께 바꾸면 이 검증을 통과할 수 있으므로 해시는 자체 일관성 검사이지 출처의 진위나 문서 승인 증명이 아니다. 입력 생성자의 독립 검증이 선행되어야 한다. 프롬프트에는 질문과 ID·본문만 전송하고 정답 필드 등은 허용하지 않는다. 0개 관련 근거인 경우에도 검색 청크 5개는 넣으며 질문 ID에 따른 예외 처리는 없다.

새 출력 디렉터리에 `events.jsonl`을 독점 생성한다. 각 요청 직전 `request_started`를 flush/fsync하고, 성공·실패 후 별도 결과 이벤트를 flush/fsync한다. 작업 프로세스 중단, 타임아웃 등으로 시작 이벤트에 대응하는 결과가 없거나 결과가 `unknown`이면 요청 전송 여부가 불확실하다. 자동 재시도와 이어쓰기는 없고 기존 디렉터리를 덮어쓰지 않는다. 사람이 로그와 공급자 측 상태·비용을 확인한 후 후속 조치를 결정해야 한다. HTTP 오류 상세 본문과 예외 메시지는 기록하지 않으며 나머지 사례는 미실행이다. 로컬 모델 digest 확인 실패/변경 및 출력 잘림도 중단한다. `latency_ms`는 생성 HTTP 호출 시간이며 Ollama digest 조회를 제외한다. 비용은 측정하지 않으며 usage가 없으면 null이다.

현재 실행기는 출력 생성과 네트워크 호출 전에 파싱된 입력·설정·모델과 파생 실행 설정의 문자열 키 및 값을 재귀 검사해 정확한 API 키가 포함되면 중단한다. 결과 텍스트는 실제 API 키가 포함된 경우에만 해당 문자열을 `[REDACTED]`로 바꾸고 `secret_redacted`를 기록한다. 따라서 그 경우 원문을 보존하지 않는다. 예외 메시지, HTTP 오류 본문, API 키 및 전체 요청/응답 JSON은 기록하지 않는다. 키가 아닌 다른 민감 정보나 인코딩·변형된 키는 자동 식별할 수 없으므로 입력·응답과 로그 접근 권한을 별도 관리해야 한다. `[[chunk_id]]` 형식의 인용만 검출하고 ID의 존재만 검사하며, `no_citations`, `has_invalid_citations`와 무효 ID를 기록한다. 인용이 없거나 무효여도 답을 지우거나 새 정보를 만들어 넣지 않으며 이 플래그만으로 성공 여부를 바꾸지 않는다. 구문상 인용이 없는 것과 인용이 반드시 필요한지 여부는 다르다. 다른 형식의 환각 출처와 사실·근거의 의미상 일치는 자동 판정하지 않는다.

## 오프라인 테스트

네트워크 대역과 합성 키만 사용한다. 예시는 Windows Git Bash 기준이며 임시 파일과 자식 프로세스 설정을 지정한다.

```sh
export TMPDIR='C:/Users/lexus/AppData/Local/hermes/profiles/blank/cache/scratch'
export TEMP="$TMPDIR" TMP="$TMPDIR" PYTHONDONTWRITEBYTECODE=1
python -m unittest discover -s results/answer-generation-smoke-v1 -p test_runner.py -v
```

합성 테스트는 원본·입력 위변조와 자체 해시 갱신, 이스케이프 문자를 포함한 비밀의 입력 사전 차단, 설정 제한, 응답 크기 제한, 각 case 전과 로컬 호출 전후 digest 교체, 인용 플래그 및 기존 파일 보존을 확인한다. 12건 생성 요청의 정상 흐름도 stub으로 확인한다. 단위 테스트의 근거 부족 답변은 stub이 반환하는 합성 텍스트다. 이것은 실제 모델의 지시 준수, 주입 방어, 부족 근거 거절, 인용 정확도 또는 운영 준비를 입증하지 않는다. 소량 실제 실험과 독립 근거 대조는 수행됐지만, 사람 채점·정식 전체 평가와 실제 서비스 연동 검증은 아직 남아 있다.
