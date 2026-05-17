# Main System Prompt 합성 규칙

PRD §13.7 기반.

## 블록 구조

main system prompt는 다음 블록을 순서대로 포함:

```text
# Converted Harness Orchestrator
{원본 orchestrator prompt 또는 synthetic prompt}

# Conversion Notes
- This app was converted from RevFactory Harness output.
- Use DeepAgents subagents instead of Claude Code Agent Teams.
- Treat TeamCreate as the available subagent registry.
- Treat TaskCreate as planning and delegation.
- Treat SendMessage as result handoff mediated by the main agent.

# Delegation Policy
{IR.workflow.delegation_policy.summary}

# Artifact Policy
Use `{workspace_dir}/` for intermediate artifacts.
{artifact conventions, 있으면}

# Safety and Validation Policy
{warnings + tool stubs}
```

## Synthetic prompt 합성 (orchestrator 미발견 시)

패턴별 strategy 문구:

| 패턴 | Strategy |
|---|---|
| pipeline | "Follow an ordered phase checklist. Complete each phase before starting the next." |
| fanout_fanin | "Delegate independent subtasks to subagents in parallel, then synthesize the results." |
| expert_pool | "Select the most relevant subagent based on its description and the task at hand." |
| producer_reviewer | "Delegate a draft to a producer subagent, then a reviewer; revise once if needed." |
| supervisor | "Act as a supervisor: assess state, assign work to subagents dynamically, and integrate results." |
| hierarchical | "Delegate broadly to subagents, which may further delegate or summarize back." |
| hybrid | "Use phase-specific policies. Inspect each phase before deciding which subagents to invoke." |
| unknown | "Plan first, delegate to specialized subagents, synthesize results, return a clear answer." |

이어서 subagent registry와 skill catalog를 ASCII 리스트로 첨부.

## Subagent prompt 합성

각 subagent는 다음 구조:

```text
{원본 agent body}

# DeepAgents Runtime Notes
You are running as a DeepAgents subagent.
Return concise, structured results to the main agent.
Write large intermediate outputs to the filesystem when appropriate.
Do not assume direct peer-to-peer SendMessage; communicate through task results.
```

원본 body는 가능하면 **frontmatter 제거 후** 본문만 사용한다 (skill 파일의 경우). agent 파일의 frontmatter는 메타데이터이므로 prompt에 포함하지 않는다.

## 너무 긴 prompt

prompt 길이 > 50KB 시:
- v0.1: warning만 기록, 그대로 보존
- v0.3+ (예정): `prompts/main.md`, `prompts/subagents/*.md`로 분리하여 `agent.py`에서 import

## raw string 사용

prompt는 항상 raw triple-quoted string(`r"""..."""`)으로 삽입:
- escape 처리 최소화
- 한국어/유니코드 보존
- backslash literal 보존

`"""` 이 prompt 본문에 등장하면 `\"\"\"` 로 변환 (emit script에서 처리).
