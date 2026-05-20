# Mapping Rules: Harness → DeepAgents

PRD §16 기반 매핑 규칙 요약.

## 핵심 매핑

| Harness | DeepAgents |
|---|---|
| `.claude/agents/*.md` | `SUBAGENTS` 배열 항목 |
| agent name | subagent `name` |
| agent description | subagent `description` (routing) |
| agent body | subagent `system_prompt` (raw string 보존) |
| `.claude/skills/*` | `app/skills/*` (그대로 복사) |
| orchestrator skill | main `system_prompt` |
| `CLAUDE.md` | README + runtime notes |
| `_workspace/` | filesystem/artifact policy in main prompt |
| `.mcp.json` | masked `app/.mcp.json` + `mcp_tools.py` TODO |

## Claude team operation 매핑

| Claude operation | DeepAgents | Lossiness |
|---|---|---:|
| `TeamCreate` | `SUBAGENTS` registry 정의 | Low |
| `TaskCreate` | main agent의 planning/delegation 지시 | Medium |
| `SendMessage` | main-agent-mediated handoff | Medium |
| Peer-to-peer team chat | 직접 보존 불가 | High |
| `TeamDelete` | phase boundary / no-op | Low |
| `Agent(..., run_in_background=true)` | parallel delegation 지시 또는 TODO | Medium |
| Phase dependency | prompt-level workflow policy | Medium |

## 아키텍처 패턴 → prompt 전략

| 패턴 | DeepAgents prompt 전략 |
|---|---|
| Pipeline | main agent가 ordered phase checklist를 따름 |
| Fan-out/Fan-in | main agent가 독립 작업을 위임 후 종합 |
| Expert Pool | main agent가 description 기반 subagent 선택 |
| Producer-Reviewer | main agent가 draft 위임 후 review; 1회 revise 가능 |
| Supervisor | main agent가 supervisor 역할로 동적 배정 |
| Hierarchical | main agent가 broad subagents에게 위임, subagent가 요약 보고 |
| Hybrid | phase별 정책 블록 |

## Skill 매핑 우선순위

1. Agent frontmatter `skills` 필드 (explicit)
2. Agent body의 정확한 skill 이름 mention (high confidence)
3. Description keyword overlap (medium confidence)
4. Orchestrator가 명시한 agent-skill mapping
5. Fallback: shared skill을 main agent 레벨에 등록
