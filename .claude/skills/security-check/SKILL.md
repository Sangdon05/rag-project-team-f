---
name: security-check
description: Use before opening a PR or pushing a branch. Scans the tree and branch history for secrets, forbidden files, and risky code/config.
---

# security-check

security-reviewer 에이전트가 쓰는 스킬. PR 전에 비밀 노출, 커밋 금지 파일, 위험한 코드·설정이 없는지 확인한다.
에이전트는 실행하고 분류해 보고만 한다(읽기 전용). 수정 발주와 PR 진행 판정은 오케스트레이터가 한다.
검출은 스크립트가 결정적으로 하므로 낮은 모델(haiku)로 충분하다. 모델의 판단은 WARN 분류에만 쓴다.

구성:

- `rules.json` — 검사 규칙 (비밀 패턴, 금지 경로, .gitignore 프로브, 코드·설정 패턴)
- `scripts/check_security.py` — 검사 스크립트 (stdlib만 사용)

## 언제 실행하는가

- PR을 만들기 직전, 그리고 이미 열린 PR 브랜치에 push하기 직전 (필수)
- 하위 에이전트 보고를 검토할 때, `changed_files`에 코드·설정·`.claude/`가 있으면
- `.env.example`, `docker-compose.yml`, `.gitignore`, `.claude/` 설정을 바꾼 직후

## 절차

1. `git fetch`로 base를 최신으로 만든 뒤 검사를 실행한다.

   ```bash
   uv run python .claude/skills/security-check/scripts/check_security.py
   # base 지정: --base origin/main (기본값)
   ```

2. 검사 범위는 세 가지다.

   | 범위 | 대상 | 이유 |
   | --- | --- | --- |
   | 작업 트리 | tracked + ignore되지 않은 untracked 파일 전체 | `git add .` 한 번에 커밋될 수 있는 것 |
   | 브랜치 기록 | base..HEAD 커밋에서 추가된 줄·파일 | 나중 커밋에서 지워도 push하면 기록에 남는다 |
   | 변경분 | base 이후 추가된 줄 | 코드·설정 패턴은 새로 들어온 것만 본다 |

3. **ERROR**는 모두 고친다. PR을 만들지 않는다.

   | 종류 | 뜻 | 처리 |
   | --- | --- | --- |
   | secret | API 키, 토큰, 개인 키, 로컬 기본값이 아닌 DB 비밀번호 | 값을 지우고 환경 변수로 읽는다. 이미 push됐으면 키를 먼저 폐기(재발급)한다 |
   | secret (브랜치 기록) | 트리에는 없지만 커밋 기록에 남음 | 키 폐기 → 해당 커밋을 rebase로 고쳐 기록에서 제거 → 재검사 |
   | file | `.env`, 키 파일, `runs/`, DB 파일, 개인 설정 등 | `git rm --cached`, `.gitignore` 보강 |
   | gitignore | 필수 무시 규칙이 저장소 `.gitignore`에 없음 | `.gitignore`에 추가. 개인 `.git/info/exclude`는 팀원에게 적용되지 않으므로 인정하지 않는다 |

4. **WARN**은 하나씩 판단한다.

   | 종류 | 처리 |
   | --- | --- |
   | secret-assignment | 실제 값이면 ERROR와 같이 처리. 테스트 더미면 줄에 `security: allow <사유>` 주석 |
   | code | `eval`/`exec`, pickle, `allow_dangerous_deserialization`, `shell=True`, SQL f-string, `verify=False`, 비밀 출력 → 고친다. 모델명·DB 주소 하드코딩은 가드레일 위반이므로 환경 변수로 바꾼다 |
   | claude | `.claude/` 설정의 권한 우회, hooks, MCP 서버. 팀원 PC에서 실행되므로 내용과 출처를 확인한다 |
   | notebook | 출력 셀 지우고 커밋 |
   | size | 생성물이면 커밋하지 않고 재생성 스크립트를 커밋 |
   | deps | `uv add`/`uv remove`로 다시 반영 |

   고치지 않는 WARN은 PR 본문 "보안 점검" 섹션에 `종류 파일:줄 — 사유`를 남긴다.

5. PR 본문에 검사 결과(`ERROR 0, WARN n`)와 WARN 처리 내역을 적는다.

## 규칙 갱신

- 새 외부 서비스 키를 쓰게 되면 `secret_patterns`에 패턴을 추가한다.
- 새 생성물 폴더를 만들면 `.gitignore`와 `forbidden_paths`, `gitignore_probes`에 함께 추가한다.
- `.env.example`의 DB 기본 비밀번호를 바꾸면 `db_url.allowed_passwords`도 바꾼다.
- 규칙을 바꾸면 의도적으로 위반하는 파일을 임시 worktree에 만들어 검사가 잡는지 확인한다 (아래).

```bash
git worktree add --detach "$TMPDIR/secsim" HEAD
# $TMPDIR/secsim 안에 가짜 키·금지 파일을 커밋하고 검사 실행 → 잡히는지 확인
git worktree remove --force "$TMPDIR/secsim"
```

가짜 키는 실행 시점에 조립한다. 키처럼 생긴 문자열을 저장소 파일에 쓰지 않는다.

## 검사의 한계

- 패턴 기반이다. 형식이 알려지지 않은 비밀(임의 문자열 비밀번호 등)은 `secret-assignment` WARN으로만 잡히거나 놓친다.
- 브랜치 기록은 base..HEAD만 본다. main에 이미 들어간 비밀은 잡지 않는다. 필요하면 `--base`를 첫 커밋으로 줘서 전체 기록을 본다.
- 의존성 취약점(CVE)은 보지 않는다. 나중에 도입: `uv export --no-hashes | uvx pip-audit -r /dev/stdin`.
- 런타임 보안(프롬프트 인젝션, 툴 권한)은 이 검사의 범위가 아니다. tool-calling·langchain-rag 스킬 규칙과 평가로 다룬다.

## 하지 않는 것

- 출력이나 PR 본문에 비밀 값을 붙여 넣지 않는다. 검사도 앞 4자만 표시한다.
- 검사를 통과시키려고 `rules.json` 규칙을 지우거나 `security: allow`를 사유 없이 붙이지 않는다.
- push된 키를 "지웠으니 괜찮다"로 처리하지 않는다. 기록에 남으므로 항상 폐기한다.
