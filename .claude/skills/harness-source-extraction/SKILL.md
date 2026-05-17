---
name: harness-source-extraction
description: "RevFactory Harness 산출물(.claude/agents/*.md, .claude/skills/*/SKILL.md, .mcp.json, .claude/settings.json, CLAUDE.md, _workspace/)을 발견하고 파싱하여 harness.deepagents.ir.yaml 중간 표현으로 정제하는 추출 스킬. YAML frontmatter 파싱, 오케스트레이터 점수화, 아키텍처 패턴 추정, Claude-only 연산 감지, MCP 의존성 식별을 모두 담당. harness-extractor 에이전트가 사용."
---

# Harness Source Extraction

Harness source files를 IR로 정제하는 작업 스킬. 결정적 처리는 `scripts/`로 위임하고, 의미론적 판단(오케스트레이터 후보 평가, 패턴 추론)만 LLM이 수행한다.

## 추출 7단계

### 1. Source discovery

```bash
python scripts/extract_harness.py discover --root <project_root> > _workspace/00_discovery.json
```

발견 대상:
- `.claude/agents/*.md`
- `.claude/skills/*/SKILL.md` (대문자 SKILL.md, skill.md 둘 다 지원)
- `CLAUDE.md`, `.mcp.json`, `.claude/settings.json`
- `_workspace/`, `README.md`, `pyproject.toml`, `package.json`

`.claude/agents`도 `.claude/skills`도 없으면 즉시 abort. **이것이 유일한 hard fail 조건**.

### 2. Agent parsing

```bash
python scripts/extract_harness.py parse-agents --root <root> > _workspace/00_agents.json
```

각 agent에서 추출:
- `id`, `name`, `source_file`
- `description`, `system_prompt` (body 전체 보존)
- `model_hint`, `tools` (frontmatter)
- `skills_detected.explicit` (frontmatter `skills` 또는 body에 정확히 등장한 skill 이름)
- `skills_detected.inferred` (description keyword overlap)
- `inputs`, `outputs`, `communication.receives_from/sends_to`

**Frontmatter 부재/오류 시:** raw body fallback. 파일명 기반 id/name 자동 생성. warning 추가.

### 3. Skill parsing

각 skill에서 추출:
- `id`, `name`, `source_dir`, `target_dir`
- `description`, `description_length`, `skill_md_size_bytes`
- `references[]`, `scripts[]`, `assets[]` (recursive inventory)
- `portable_to_deepagents` 판단

**Validation:**
- description 누락 → warning
- description > 1024자 → warning
- SKILL.md > 10MB → DeepAgents loading risk warning

### 4. Orchestrator detection

PRD §13.4 점수표 사용. 후보 점수 계산은 `scripts/extract_harness.py orchestrator-score`로 위임.

| 신호 | 점수 |
|---|---:|
| name에 `orchestrator` | +5 |
| name에 `workflow`/`runner`/`coordinator`/`supervisor` | +4 |
| 한국어 `오케스트레이터`/`워크플로우`/`조율` | +4 |
| `TeamCreate` body 등장 | +5 |
| `TaskCreate` body 등장 | +4 |
| `SendMessage` body 등장 | +4 |
| 2개 이상 agent 이름 mention | +3 |
| phase/dependency/output 섹션 | +3 |
| `_workspace` mention | +2 |
| description에 후속 작업 trigger | +1 |

threshold(예: 8) 미만이면 synthetic orchestrator 권고를 emitter에게 전달.

### 5. Architecture pattern detection

각 패턴 점수 계산. 가장 높은 값 선택. confidence = 점수 / max_possible.

| 패턴 | 신호 |
|---|---|
| pipeline | "phase 1", "phase 2", "depends_on", "sequential" → +2 |
| fanout_fanin | "parallel", "fan-out", "merge", "aggregate", "synthesis" → +3 |
| expert_pool | "expert", "pool", "route", "select" → +2 |
| producer_reviewer | "review", "revise", "approve", "QA", "retry" → +3 |
| supervisor | "supervisor", "coordinator", "assign" dynamic → +3 |
| hierarchical | "parent", "child", "delegate recursively" → +3 |
| hybrid | 복수 패턴 신호가 비슷한 강도 |

confidence < 0.5 → `unknown` 또는 `hybrid`로 기록 + warning.

### 6. Claude-only operation detection

```bash
python scripts/extract_harness.py claude-ops --root <root>
```

탐지 대상: `TeamCreate`, `TeamDelete`, `TaskCreate`, `SendMessage`, `Agent`, `run_in_background`.

각 발견에 대해 IR `claude_only_operations[]`에 기록:
- `operation`, `count`, `mapping` (PRD §16.2 표 참조)

### 7. MCP / tool / settings 분석

- `.mcp.json` parsing → server names, env_vars, raw secret pattern 검출 → 마스킹
- `.claude/settings.json` → MCP/env hints
- agent body의 tool mention → `tools.stubs_required[]`로 후보 등록

## IR 빌드

모든 결과를 `harness.deepagents.ir.yaml`로 직렬화. 스키마는 `references/ir-schema.md` 참조.

```bash
python scripts/extract_harness.py build-ir --root <root> --out _workspace/01_extractor_ir.yaml
```

## 작업 원칙

- **원본 보존 우선** — body, prompt, description의 원본을 IR에 그대로 보존한다. 자동 요약은 별도 필드(`body_summary`)에만 둔다.
- **상대 경로** — 모든 source 경로는 root 기준 relative.
- **Confidence 명시** — 자동 추론 결과는 `confidence` (0.0~1.0)와 `evidence[]`(증거 문자열)와 함께 기록.
- **Secret 절대 IR에 노출 금지** — 패턴 매칭 후 즉시 마스킹.
- **partial failure tolerant** — 한 파일 파싱 실패가 전체 추출을 막지 않는다.

## 안전 규칙

- 원본 `.claude/` 절대 수정 금지 (읽기 전용 처리)
- symlink 따라가지 않음 (기본값)
- glob 시 path traversal 차단

## 결정적 처리는 scripts에 위임

- frontmatter parsing → `scripts/extract_harness.py parse-agents`
- secret pattern → `scripts/extract_harness.py mcp-scan` (또는 별도 secret-scan 스킬)
- source fingerprint (sha256) → `scripts/extract_harness.py fingerprint`

LLM은 다음만 수행:
- 오케스트레이터 후보 점수가 비슷할 때 의미론적 결정 (description 어조 등)
- 패턴 confidence가 모호할 때 hybrid 여부 판단
- skill-agent 매핑이 explicit/inferred 양쪽에 후보가 있을 때 선택

## 참고

- IR 전체 스키마: `references/ir-schema.md` (PRD §12.2 기반)
- 패턴 감지 휴리스틱 상세: `references/pattern-detection.md`
- frontmatter 변형 처리: `references/frontmatter-edge-cases.md`
- Claude ops → DeepAgents 매핑: `references/claude-ops-mapping.md`
