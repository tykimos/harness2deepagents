# MCP 처리 규칙

PRD §17 기반.

## 감지

다음 파일에서 MCP 힌트 검색:

```text
.mcp.json
.claude/settings.json
CLAUDE.md
.claude/skills/*/SKILL.md
.claude/agents/*.md
```

## 출력 동작

| 상황 | 동작 |
|---|---|
| `.mcp.json` 존재 | secret 마스킹 후 `app/.mcp.json`으로 복사 |
| secret-like literal 존재 | `***REDACTED***`로 치환 + warning |
| env var 참조(`${VAR}`) 존재 | 그대로 유지 + README에 required env var 기록 |
| MCP server command 존재 | 자동 실행 안 함 (mcp_tools.py TODO만 생성) |
| tool name 추론 가능 | `mcp_tools.py`에 TODO adapter 생성 |

## 마스킹 패턴

`secret_scan.py` SECRET_PATTERNS와 동일:
- `sk-[A-Za-z0-9_-]{16,}`
- `AKIA[0-9A-Z]{16}`
- `ghp_[A-Za-z0-9]{36}` (gho_, ghu_, ghs_)
- `xoxb-[A-Za-z0-9-]+`
- `-----BEGIN [A-Z ]*PRIVATE KEY-----`

## env var 참조

`.mcp.json` 안의 `${VAR_NAME}` 또는 `$VAR_NAME` 패턴:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "node",
      "args": ["index.js"],
      "env": {"FILESYSTEM_ROOT": "${FILESYSTEM_ROOT}"}
    }
  }
}
```

→ `${FILESYSTEM_ROOT}`는 그대로 유지. README에 `FILESYSTEM_ROOT` env var 안내 추가.

## mcp_tools.py 생성 정책

- `load_mcp_tools()` 함수 stub만 생성 (빈 list 반환)
- adapter 자동 구현은 v0.1에서 out of scope
- docstring에 단계별 안내:
  1. Review .mcp.json
  2. Set required env vars
  3. Use langchain-mcp-adapters
  4. Return Tool list

## conversion_report.md에 기록할 항목

- 감지된 server 목록
- 필요한 env var 목록
- masking 적용 여부 (secret 발견 시 type만 노출, 값 자체는 절대 노출 금지)
- Manual action: "Configure MCP server X by setting env vars Y, Z and implementing load_mcp_tools()"
