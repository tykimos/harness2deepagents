# conversion_report.md 템플릿

PRD §19 기반. 13개 섹션 순서대로.

```markdown
# harness2deepagents Conversion Report

> **Mode:** {full | audit_only}
> **Conversion score:** {0.00~1.00} ({해석})
> **Generated:** {ISO timestamp}

## Summary

{한 단락 요약: 발견한 agents/skills 수, orchestrator 여부, 패턴, 결과 요약}

## Source Discovery

- Root: `{path}`
- Source fingerprint: `{sha256}`
- Detected files:
  - agents: {N}개 ({list 또는 "none"})
  - skills: {N}개
  - orchestrator candidate: `{path}` (또는 "synthetic")
  - mcp config: `{.mcp.json}` 또는 "none"
  - settings: `{.claude/settings.json}` 또는 "none"

## Detected Harness Architecture

- Pattern: `{pipeline | fanout_fanin | ... | unknown}` (confidence {0.00~1.00})
- Evidence: {list}
- Execution mode: `{agent_team | subagents | hybrid | unknown}` (confidence {0.00~1.00})
- Workspace dir: `{_workspace 또는 N/A}`

## Agents

| Name | Role summary | Model hint | Skills attached | Warnings |
|---|---|---|---|---|
| {agent.name} | {description, 80자 내외} | {model} | {skill list} | {warning list 또는 -} |

## Skills

| Name | Description (truncated) | Size | Portable | Warnings |
|---|---|---:|---|---|
| {skill.name} | {description, 100자 내외} | {bytes} | {true/false} | {warning list} |

## Orchestrator

- Found: {true/false}
- Source: `{path}` 또는 "synthetic prompt generated"
- Detected operations:

| Operation | Count | Mapping |
|---|---:|---|
| TeamCreate | 1 | subagents registry |
| TaskCreate | 3 | planning/delegation instructions |
| SendMessage | 2 | main-agent-mediated handoff |

## DeepAgents Mapping

원본 → 변환 결과:

| Source | Target |
|---|---|
| `.claude/agents/analyst.md` | SUBAGENTS[0] (`analyst`) |
| `.claude/skills/research/` | `app/skills/research/` |
| Orchestrator skill | `MAIN_SYSTEM_PROMPT` |
| Pattern strategy | Delegation Policy block in main prompt |

## Claude-only Operations

| Operation | Count | Mapping | Lossiness |
|---|---:|---|---|
| TeamCreate | 1 | subagents registry | low |
| SendMessage | 2 | main-agent-mediated handoff | medium |
| Peer chat | — | not preserved | high |

## Tools and MCP

- MCP servers detected: {list}
- Required env vars: {list}
- Tool stubs generated: {list, with file:line}
- Secret scan: {pass | warn | fail}

## Generated Files

```text
{output_dir}/
├── harness.deepagents.ir.yaml
├── conversion_report.md
├── app/
│   ├── agent.py
│   ├── config.py
│   ├── tools.py
│   ├── mcp_tools.py        ← MCP 감지 시
│   ├── smoke_test.py
│   ├── requirements.txt
│   ├── pyproject.toml
│   ├── README.md
│   ├── .mcp.json           ← MCP 감지 시 (마스킹됨)
│   └── skills/
│       └── ...
└── logs/
    └── validation.json
```

## Validation Results

| Stage | Status | Notes |
|---|---|---|
| ir_yaml_parse | pass | |
| ir_required_fields | pass | |
| required_files | pass | |
| python_compile | pass | |
| skill_copy | pass | 5/5 skills copied |
| secret_scan | warn | 3 masked literals |
| smoke_test | warn | deepagents not installed in this env |
| raw_langgraph_emitter | pass | |

## Warnings

- `{warning_id}`: {설명, 출처, 후속 조치}
- ...

## Manual Actions

- [ ] **Implement** `web_search_stub` in `app/tools.py:15`. Reason: agent `analyst.md` references web research but no concrete tool was configured. Source: IR.tools.stubs_required[0].
- [ ] **Configure** MCP env var `FILESYSTEM_ROOT` in your environment. Source: IR.tools.mcp_servers[0].
- [ ] **Review** `MAIN_SYSTEM_PROMPT` in `agent.py` for fidelity to original orchestrator. Source: extractor confidence {0.00~1.00}.

## Run Commands

```bash
cd {output_dir}/app
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...    # your key
python smoke_test.py                # import-level check
python agent.py                     # default invocation
```

## Limitations

- DeepAgents API may evolve; `create_deep_agent` signature could change. See README for upgrade guidance.
- `TeamCreate`/`SendMessage` peer-to-peer messaging from the original Harness is approximated by main-agent-mediated handoff (medium-to-high lossiness).
- MCP servers are not auto-started; implement `mcp_tools.py` after reviewing `app/.mcp.json`.
- Live invocation is not validated by smoke test — run a controlled invocation before production use.
- Re-running `harness2deepagents` writes to a new timestamped directory by default. Existing edits in old output are preserved.
```

## 점수 해석 박스 (점수 < 0.5 시 보고서 최상단에 추가)

```markdown
> ⚠️ **Conversion score: {score}** — 이 산출물은 감사용입니다.
> 실행 가능성을 보장하지 않습니다. Manual Actions 섹션의 항목을 모두 처리한 후 재검증하세요.
```
