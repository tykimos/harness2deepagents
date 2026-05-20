# IR Schema Summary (harness2deepagents/v1)

`harness.deepagents.ir.yaml`의 핵심 필드 요약. 전체 스키마는 `harness-source-extraction/references/ir-schema.md` 참조 (PRD §12.2 기반).

## 최상위 키

```yaml
schema_version: "harness2deepagents/v1"
metadata: { generated_at, generator, generator_version, mode }
source: { root, source_fingerprint, detected_files }
harness: { name, summary, architecture_pattern, execution_mode, workspace_dir }
target: { runtime: "deepagents", emit_raw_langgraph: false, output_dir, model }
agents: [...]
skills: [...]
orchestrator: { found, source_file, name, description, prompt, detected_operations }
workflow: { phases, delegation_policy, review_policy }
tools: { mcp_servers, langchain_tools, stubs_required, environment_variables }
artifacts: { workspace_dir, output_files, generated_files }
quality: { conversion_score, blockers, warnings, manual_actions }
validation: { yaml_parse, python_compile, skill_copy, secret_scan, smoke_test }
```

## 불변 규칙

- `target.runtime`은 항상 `"deepagents"`
- `target.emit_raw_langgraph`는 항상 `false`
- 모든 source 경로는 root 기준 상대 경로
- `confidence` 필드는 0.0~1.0 범위
- secret-like literal은 절대 IR에 포함하지 않음 (마스킹 + warning만)

## Confidence와 Evidence

자동 추론 결과는 항상 다음 패턴:

```yaml
architecture_pattern:
  value: "supervisor"
  confidence: 0.82
  evidence:
    - "orchestrator name contains 'supervisor'"
    - "TaskCreate uses dynamic assignee"
```
