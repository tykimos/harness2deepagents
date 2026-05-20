# Secret Detection Patterns

PRD §17.3 + 확장.

## 검출 패턴

| 패턴 | label | 의미 |
|---|---|---|
| `sk-[A-Za-z0-9_\-]{16,}` | openai_or_anthropic_key | OpenAI / Anthropic API key prefix |
| `AKIA[0-9A-Z]{16}` | aws_access_key | AWS access key ID |
| `ghp_[A-Za-z0-9]{36}` | github_pat | GitHub personal access token |
| `gho_[A-Za-z0-9]{36}` | github_oauth | GitHub OAuth token |
| `ghu_[A-Za-z0-9]{36}` | github_user | GitHub user-to-server token |
| `ghs_[A-Za-z0-9]{36}` | github_server | GitHub server-to-server token |
| `xoxb-[A-Za-z0-9-]+` | slack_bot | Slack bot token |
| `-----BEGIN [A-Z ]*PRIVATE KEY-----` | private_key | PEM-encoded private key |

## Scan 대상 / 비대상

**대상 확장자:**
- `.py`, `.json`, `.toml`, `.yaml`, `.yml`
- `.env`, `.cfg`, `.ini`, `.sh`

**비대상 (false positive 회피):**
- `.md`, `.txt`, `.rst` (문서 — 패턴 자체를 설명하는 경우 多)
- 바이너리 (`.png`, `.pdf`, `.so` 등)
- `.git/`, `__pycache__/`, `.venv/`, `node_modules/`

이유: SKILL.md / 문서 파일은 secret 패턴을 *언급*하는 경우가 많다 (예: 이 문서). 실제 secret은 코드와 config에 위치한다.

## 분류 기준

| 발견 | status | 후속 조치 |
|---|---|---|
| Raw secret in `.py`/`.json`/`.toml` 등 | fail | 즉시 `***REDACTED***`로 마스킹 + 재방출 |
| `***REDACTED***` 마커 발견 | warn | 보고에만 기록 (의도된 마스킹) |
| 발견 없음 | pass | — |

## Pattern 추가 시 규칙

1. `validate_port.py`와 `secret_scan.py` 두 파일 모두 갱신
2. `extract_harness.py` SECRET_PATTERNS도 동기화
3. label은 snake_case로 유일
4. 정규식은 false positive를 줄이기 위해 prefix + 길이를 함께 확인 (예: `sk-` + 16자 이상)
5. 새 패턴 추가 후 `port-validation`의 SKILL.md 본문 표 갱신

## 동시 처리: 마스킹

`secret_scan.py --redact` 모드는 발견된 secret을 `***REDACTED***`로 inline 치환 후 파일을 다시 쓴다. emitter의 fix loop에서 호출.

원본(`.claude/`)에는 절대 마스킹 적용하지 않는다 — 출력(`ports/deepagents{_TS}/`)에만 적용.
