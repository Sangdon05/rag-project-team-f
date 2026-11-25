# 질문 설계 에이전트 — 사용·검증·팀 전달

`question-designer`는 세 페르소나의 가상 질문 후보를 만드는 개발 보조 역할이다. [problem.md](../problem.md)의 3페르소나·S01/S01-B·9개 원질문을 원본으로 삼고, 답변·근거를 제외한 입력만 받아 `draft` 후보를 반환한다. [생성기 문서](../persona-question-generator.md)의 I01~I03 × 세 페르소나 9표현은 별도의 통제 예시다. 두 세트를 공식 문항 수로 합산하지 않는다.

## 구성과 책임

| 구성 | 원본·책임 |
| --- | --- |
| 역할·최소 도구 | [question-designer](../../.claude/agents/question-designer.md). Read만 사용하며 후보 JSON을 응답으로 반환 |
| 생성 절차·출력 계약 | [question-design](../../.claude/skills/question-design/SKILL.md) |
| 질문 전용 입력 추출·구조 검사 | [question_packets.py](../../.claude/skills/question-design/scripts/question_packets.py). 표준 라이브러리만 사용 |
| 자동 검사 | [test_question_design.py](../../tests/test_question_design.py) |
| 공식 평가셋·잠금 | [eval/README.md](../../eval/README.md). 팀원 소유 |

이 역할은 RAG 런타임, 추천 정책, Query Rewrite, 정답 작성·채점을 구현하지 않는다. 추천 성공 기준과 공식 평가 경로의 미정 상태도 바꾸지 않는다. 도구 목록과 지침은 역할 수준의 제한이며 파일 시스템 접근을 격리하는 보안 장치가 아니다. 운영 환경에서 강제 차단이 필요하면 그 환경의 접근 제어를 별도로 설정한다.

## 1. 입력 준비 — 오케스트레이터

저장소 루트에서 실행한다. 다른 패키지·모델·DB가 필요하지 않다.

```bash
uv run python .claude/skills/question-design/scripts/question_packets.py prepare --output runs/question-design/demo-001/input.json
```

- 출력은 `runs/question-design/` 아래만 허용하고 기존 파일을 덮어쓰지 않는다. 재실행은 새 배치 이름을 쓴다.
- 원본 SHA-256, 세 페르소나, 공통 상황, P3-02의 물대포 제외 조건, 질문 원문 9개가 포함된다.
- 원본 전체·답변·필수 확인 사실·근거 위치·오답 기준은 생성 담당에게 전달하지 않는다.
- `problem.md`의 표·제목 형식이 바뀌어 허용 필드가 사라지면 추출을 중단한다. 담당자가 매핑과 테스트를 검토한 뒤 진행한다.

## 2. 질문 후보 제안 — question-designer

작은 배치의 발주 예시다. 대상 3문항은 각 페르소나의 대표 예시이며, 공식 평가셋이 아니다.

```text
task: 세 페르소나의 원질문을 같은 뜻의 자연스러운 표현으로 하나씩 바꿔 질문 후보 3개를 제안한다.
agent: question-designer
inputs: runs/question-design/demo-001/input.json (schema_version=question-design-v1)
targets: P1-01, P2-01, P3-01
relation: paraphrase
outputs: 출력 계약에 맞는 JSON 한 개를 응답으로 반환
done_when: seed 연결·페르소나·상황·정보 요구가 보존되고 모든 후보가 draft다.
constraints: 공식 eval/ 열람·수정, 정답·예상 배율·허용 근거 생성, 파일 쓰기·명령 실행 금지.
```

Claude Code에서는 저장소의 `.claude/agents/` 역할로 호출할 수 있는 정의 형식이다. 실제 자동 인식·실행은 사용 중인 클라이언트에서 확인한다. Hermes나 다른 실행기에서는 이 경로가 자동 인식된다고 가정하지 않는다. 담당자가 역할 본문·question-design 절차·질문 전용 JSON 패킷을 작업 지침과 입력으로 명시해 전달하고, 도구 권한도 실행기에 맞춰 제한한다. 별도 Hermes 플러그인·자동 로더는 이 변경에 포함되지 않는다.

## 3. 결과 저장·검사 — 오케스트레이터

후보 JSON을 `runs/question-design/demo-001/candidates.json`에 저장한 뒤 검사한다.

```bash
uv run python .claude/skills/question-design/scripts/question_packets.py check --input runs/question-design/demo-001/input.json --candidates runs/question-design/demo-001/candidates.json
```

검사 결과의 `structural_check=pass`는 구조 통과만 뜻한다. 원본이 바뀌었거나 입력 패킷이 변조되면 거부한다. 잘못된 페르소나·상황 연결, 비초안 상태, 정답·근거 등 미등록 필드, 조건 변경의 표시 누락, 같은 문자열의 중복도 거부한다. 문장 속 정답 유출이나 의미 변화까지 완전히 검출하지는 않는다.

다음은 생성 담당과 다른 검토자 또는 팀원이 확인한다.

1. 원래 대상·조건·정보 요구를 보존했는가? 조건이 달라졌다면 관계와 변경 전후를 명시했는가?
2. 연령 고정관념 없이 입력된 지식 수준에 맞는가? 실제 사용자 조사로 오해하게 표현하지 않았는가?
3. 이미 준 정보를 다시 요구하거나, 빠진 상대·현재 기술을 임의로 만들지 않았는가?
4. 정답·배율·허용 근거를 새로 끼워 넣지 않았는가? 원질문에 있던 숫자 전제와 구분했는가?
5. 사용자 입력 부족과 원문 자료 부족을 구분했는가? 같은 정보 요구를 새 고유 문항으로 부풀리지 않았는가?

형식 통과, 독립 의미 검토, 팀원의 채택은 서로 다른 상태로 보고한다. 생성 담당이 자기 결과를 합격 처리하지 않는다.

## 4. 팀원에게 전달할 묶음

PR 외에도 다음 내용을 한 묶음으로 설명하면 다음 담당자가 바로 검토할 수 있다. 메신저 발송은 별도 작업이며 자동 발송하지 않는다.

| 전달물 | 받는 사람이 할 일 |
| --- | --- |
| 변경 목적·에이전트의 책임과 금지 범위 | 기존 Data Engineer·RAG Developer·Eval과 역할이 겹치지 않는지 확인 |
| 위의 실행 명령·대표 발주 1개 | 각자의 환경에서 입력 추출·역할 호출·결과 검사를 재현 |
| 소수의 공개 검토 예시·원본 질문 연결 | 표현 변형인지 조건 변경인지 검토하고 채택·보류 결정 |
| 자동 검사 결과·실제 역할 호출 환경·미검증 항목 | 구조 검사와 생성 품질·실행기 호환성을 구분 |
| 다음 담당과 완료 조건 | 팀원이 질문 채택 후 원문·정답·허용 근거를 검수하고, 직접 공식 평가셋 작성·잠금 |

생성 파일과 원문 트레이스는 `runs/`에 두고 커밋하지 않는다. 공유용 예시는 공개 범위를 검토해 이 문서나 PR에 별도로 선정한다. 잠금이 끝나면 기존 Eval이 검증·실행·사람 채점표 준비·집계를 맡는다. 생성 에이전트는 최종 평가 파일을 받지 않는다.

## 5. 세 페르소나의 생성 동작 확인 예시

2026-11-25에 정답 문서와 대화 이력을 전달받지 않은 독립 Codex 작업자에게 역할 정의·절차·질문 전용 패킷만 제공해 아래 후보 3개를 생성했다. Claude Code/Hermes 실행기에서의 호출 성공을 대신하는 검증은 아니다. 후보의 공식 채택과 팀원의 의미 검수는 대기 상태다.

| 후보 | 원질문 연결 | 반환한 질문 |
| --- | --- | --- |
| Q01 · P1 | P1-01 · S01 | 롱스톤 상대로 전기쇼크랑 전광석화 중 어떤 기술이 통해? |
| Q02 · P2 | P2-01 · S01 | 피카츄만 알고 있는데 롱스톤과 싸우게 됐어요. 어떤 정보부터 확인하면 돼요? |
| Q03 · P3 | P3-01 · S01 | 꼬부기가 롱스톤에게 물대포를 쓸 때 타입 상성 배율과 자속을 각각 구분해서 알려줘. |

각 후보는 `paraphrase`, `draft`로 반환됐고 구조 검사는 통과했다. 답변 가능성·자연스러움·의미 보존은 사람 검토 전이며 RAG 평가 수치로 보고하지 않는다.

## 6. 재현 가능한 검사와 완료 범위

```bash
uv run python -m unittest discover -s tests -p "test_question_design.py" -v
uv run python .claude/skills/doc-sync/scripts/check_docs.py --strict
uv run python .claude/skills/security-check/scripts/check_security.py --base origin/main
```

첫 명령은 추출·계약의 회귀 검사이며 API·모델·DB를 호출하지 않는다. 실제 생성 동작은 위 대표 발주로 별도 확인하고 실행기·후보 수·의미 검토 상태를 기록한다. RAG의 Hit@5·답변 정확도·사람 채점은 기존 평가 흐름에서 측정한다. 질문 후보의 채택률·검토 시간은 실제 팀원 검토가 이루어진 뒤에 기록한다.
