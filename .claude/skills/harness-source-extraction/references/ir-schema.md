# IR Schema (harness2deepagents/v1)

PRD §12.2 기반 전체 스키마.

```yaml
schema_version: "harness2deepagents/v1"

metadata:
  generated_at: "2026-05-06T00:00:00+09:00"
  generator: "harness2deepagents"
  generator_version: "0.1.0"
  mode: "full|audit_only"

source:
  root: "."
  source_fingerprint: "sha256:<hash>"
  assumed_generator: "revfactory/harness"
  claude_base: true
  detected_files:
    claude_md: "CLAUDE.md"
    agents:
      - ".claude/agents/analyst.md"
    skills:
      - ".claude/skills/research/SKILL.md"
    orchestrators:
      - ".claude/skills/research-orchestrator/SKILL.md"
    mcp:
      - ".mcp.json"
    settings:
      - ".claude/settings.json"
    workspace:
      - "_workspace/"

harness:
  name: "converted_harness"
  summary: "One paragraph summary of the detected Harness."
  architecture_pattern:
    value: "supervisor"
    confidence: 0.82
    evidence:
      - "orchestrator mentions supervisor"
      - "multiple agents assigned dynamically"
  execution_mode:
    value: "agent_team|subagents|hybrid|unknown"
    confidence: 0.75
  workspace_dir: "_workspace"
  artifact_conventions:
    - "phase_agent_artifact.md"

target:
  runtime: "deepagents"
  emit_raw_langgraph: false
  output_dir: "ports/deepagents/app"
  model:
    env_var: "DEEPAGENTS_MODEL"
    default: "anthropic:claude-sonnet-4-6"
  package_manager: "uv|pip|unknown"

agents:
  - id: "analyst"
    name: "analyst"
    source_file: ".claude/agents/analyst.md"
    description: "Analyzes requirements and produces structured findings."
    system_prompt: "..."
    model_hint: "opus"
    deepagents:
      subagent_name: "analyst"
      description: "Use for requirements analysis and structured findings."
      skills:
        - "research"
      tools:
        - "web_search_stub"
    skills_detected:
      explicit: ["research"]
      inferred: ["analysis-method"]
    tools_detected:
      explicit: []
      inferred: ["web"]
    inputs: ["user_request"]
    outputs: ["analysis_report"]
    communication:
      receives_from: []
      sends_to: ["reviewer"]
      notes: "Sends analysis report to reviewer."
    warnings: []

skills:
  - id: "research"
    name: "research"
    source_dir: ".claude/skills/research"
    target_dir: "app/skills/research"
    description: "Use for research tasks..."
    description_length: 120
    skill_md_size_bytes: 4500
    portable_to_deepagents: true
    references: ["references/method.md"]
    scripts: ["scripts/extract.py"]
    assets: []
    used_by_agents: ["analyst"]
    warnings: []

orchestrator:
  found: true
  source_file: ".claude/skills/research-orchestrator/SKILL.md"
  name: "research-orchestrator"
  description: "Coordinates the research team..."
  prompt: "..."
  detected_operations:
    - operation: "TeamCreate"
      count: 1
      mapping: "subagents registry"
    - operation: "TaskCreate"
      count: 3
      mapping: "planning/delegation instructions"
    - operation: "SendMessage"
      count: 2
      mapping: "main-agent-mediated result handoff"
  warnings: []

workflow:
  phases:
    - id: "phase_1"
      name: "Research"
      agents: ["analyst"]
      depends_on: []
      mode: "subagent"
      expected_outputs: ["research_notes.md"]
  delegation_policy:
    summary: "Main agent plans first, delegates to specialized subagents, then synthesizes."
    rules:
      - "Use analyst for initial research."
      - "Use reviewer before final answer."
  review_policy:
    enabled: true
    reviewer_agents: ["reviewer"]
    retry_limit: 1

tools:
  mcp_servers:
    - name: "filesystem"
      source: ".mcp.json"
      env_vars: ["FILESYSTEM_ROOT"]
      copied: true
      warnings: []
  langchain_tools: []
  stubs_required:
    - name: "web_search_stub"
      reason: "Agent prompt references web research but no concrete tool is configured."
      source_agent: "analyst"
  environment_variables:
    - name: "ANTHROPIC_API_KEY"
      required: true
      source: "model provider"
    - name: "DEEPAGENTS_MODEL"
      required: false
      default: "anthropic:claude-sonnet-4-6"

artifacts:
  workspace_dir: "_workspace"
  output_files: []
  generated_files:
    - "app/agent.py"
    - "app/config.py"
    - "app/README.md"

quality:
  conversion_score: 0.78
  blockers: []
  warnings:
    - "SendMessage semantics are approximated through main-agent-mediated handoff."
  manual_actions:
    - "Implement web_search_stub in app/tools.py."

validation:
  yaml_parse: "pass"
  python_compile: "pass|fail|not_run"
  skill_copy: "pass|fail"
  secret_scan: "pass|warn|fail"
  smoke_test: "pass|fail|not_run"
```

## 설계 원칙

1. IR은 사람이 읽을 수 있어야 한다.
2. IR은 codegen의 단일 source of truth.
3. 원본 prompt는 가능하면 보존.
4. 자동 요약은 원본 prompt를 대체하지 않음.
5. 모든 warning은 원인과 후속 조치를 포함.
