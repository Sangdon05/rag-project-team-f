# API 설계안 목록

FastAPI 서비스(`api/`)의 슬라이스별 설계안을 모은다. 설계안은 [api-architect](../../../.claude/agents/api-architect.md)가 작성하고, 구현은 설계안을 원본으로 삼는다([api-invariants](../../../.claude/skills/api-invariants/SKILL.md) R14).

새 설계안을 만들면 아래 표에 링크를 추가한다. 링크가 없으면 doc-sync 검사에서 고아 문서(ERROR)가 된다.

| 슬라이스 | 설계안 | 상태 | 요약 |
| --- | --- | --- | --- |
| health | [health.md](health.md) | 검토 중 | `GET /health`. 0절에 전 슬라이스 공통 사항(응답 형식, 기반 예외, 예외→HTTP 매핑, 환경 변수) |
| suggestion | [suggestion.md](suggestion.md) | 검토 중 | `GET /api/v1/suggestion?level=`, 등급별 추천 질문(fake 데이터, `SuggestionProvider` 포트) |
| chat | [chat.md](chat.md) | 검토 중 | `POST /api/v1/chat`, mock·llm 답변 생성기, `[n]` 출처, 대화 검증 판정 순서 |
| documents | [documents.md](documents.md) | 검토 중 | `GET /api/v1/documents/{source_ref_id}`, 원문 Markdown (`DocumentStore` 포트, `API_DOCUMENTS_DIR`) |

상태: `초안` → `검토 중` → `확정`. 확정은 사용자(팀원)가 정한다. api-implementer는 `검토 중` 이상이면 구현하고, `초안`은 발주서에 명시된 경우에만 구현한다.

health처럼 규칙이 없는 슬라이스도 짧은 설계안(엔드포인트 명세만)을 둔다. [api-implementation](../../../.claude/skills/api-implementation/SKILL.md)의 예시 코드는 설계안을 대신하지 않는다.

요구사항과 진행 기록: [API 엔드포인트 스펙](../../archives/specs/2026-11-26-api-endpoints.md), [계획](../../archives/plans/2026-11-26-api-endpoints.md) (완료·보관)

후속 확인 사항(PR #9 리뷰 지적, 다른 파트 합류 후 정리): [api-dev-env-followups.md](../../proposals/api-dev-env-followups.md)
