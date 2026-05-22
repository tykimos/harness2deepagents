<p align="right"><sub><b>🇬🇧 English</b> · <a href="README_ko.md">🇰🇷 한국어</a></sub></p>

# harness2deepagents

**A Claude Code skill that auto-converts Claude Code agent teams built with RevFactory `/harness` into runnable LangChain DeepAgents Python apps.**

`/harness` owns the strength of "declarative agent team design"; `harness2deepagents` takes that output and turns it into **a Python package you can boot immediately with `langgraph dev`, complete with the default UI (`langchain-ai/deep-agents-ui`) already wired up**.

- **Version:** v0.2.0
- **Source format:** `.claude/agents/*.md`, `.claude/skills/*/SKILL.md`, `.mcp.json`, `CLAUDE.md`
- **Target:** Python app built around `from deepagents import create_deep_agent`
- **Default UI:** [`langchain-ai/deep-agents-ui`](https://github.com/langchain-ai/deep-agents-ui) (auto-wired)
- **Forbidden:** raw LangGraph emitter, single `create_agent` apps, hard-coded secrets

---

## At a glance

```mermaid
flowchart LR

    subgraph SRC["INPUT — RevFactory Harness artifacts"]
        A1[".claude/agents/*.md"]
        A2[".claude/skills/*/SKILL.md"]
        A3[".mcp.json"]
        A4["CLAUDE.md"]
    end

    subgraph H2D["harness2deepagents (this skill)"]
        direction TB
        E1["1·extractor"]
        E2["2·emitter"]
        E3["3·validator"]
        E4["4·reporter"]
        E1 --> E2 --> E3 --> E4
        E3 -. "fix loop ×1" .-> E2
    end

    subgraph OUT["OUTPUT — ports/deepagents/"]
        O1["app/agent.py"]
        O2["app/skills/*"]
        O3["app/langgraph.json"]
        O4["app/bootstrap_ui.sh"]
        O5["app/.env.example"]
        O6["app/.gitignore"]
        O7["conversion_report.md"]
    end

    SRC --> H2D --> OUT
```

---

## When to use it

| Trigger | Behavior |
|---|---|
| `/harness2deepagents` | Find `.claude/` in the current directory and convert it into `ports/deepagents/` (full mode) |
| `/harness2deepagents audit only` | Produce only IR + `conversion_report` — no code emission |
| `/h2d` | Alias for full mode |
| "Convert this .claude to DeepAgents" / "Migrate this harness" / "Port my Claude Code team to LangChain" | Natural-language triggers |

When **not** to use it:

- "Build me a harness" → use `/harness` (this skill converts, it does not author)
- "Build a LangGraph graph for me" → out of scope (raw LangGraph is intentionally rejected)
- "How do I install the deepagents library" → generic question

---

## The 4-agent team

`harness2deepagents` is not a monolithic converter — it's a 4-agent team running a **Pipeline + Producer-Reviewer** pattern.

```mermaid
graph TB

    User([User])

    Orchestrator{{"orchestrator<br/>(harness2deepagents)"}}

    subgraph Team["harness2deepagents-team"]
        direction LR
        Extractor["📥 harness-extractor<br/>.claude → IR YAML"]
        Emitter["⚙️ deepagents-emitter<br/>IR → app/ code"]
        Validator["🛡️ port-validator<br/>11-stage validation"]
        Reporter["📝 conversion-reporter<br/>IR + validation → report"]
    end

    User -->|"/harness2deepagents"| Orchestrator
    Orchestrator -->|TeamCreate + TaskCreate| Team
    Extractor -->|IR yaml| Emitter
    Emitter -->|app/*| Validator
    Validator -->|"fix request (×1)"| Emitter
    Validator -->|validation.json| Reporter
    Emitter --> Reporter
    Reporter -->|"✅ Service-ready handoff"| User
```

| # | Member | Input | Output | Responsibility |
|---|--------|-------|--------|----------------|
| 1 | **harness-extractor** | `.claude/*`, `.mcp.json`, `CLAUDE.md` | `_workspace/01_extractor_ir.yaml` | Parsing + pattern inference + secret masking |
| 2 | **deepagents-emitter** | IR YAML | `output_dir/app/*` (12 files) | Deterministic codegen, `@tool` wrapping, UI wiring |
| 3 | **port-validator** | `output_dir/app/*` | `logs/validation.json` | compile / secret / smoke / anti-pattern checks (11 stages) |
| 4 | **conversion-reporter** | IR + validation.json | `conversion_report.md` + quality score | Service-ready handoff checklist |

In `audit_only` mode only extractor + reporter run, and code emission is blocked.

---

## Conversion workflow (7 phases)

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant O as Orchestrator
    participant X as extractor
    participant E as emitter
    participant V as validator
    participant R as reporter

    U->>O: /harness2deepagents
    O->>O: Phase 1 — pick mode<br/>(full / audit_only)<br/>(tools_mode: mock_fallback / strict_stub)
    O->>O: Phase 2 — TeamCreate + TaskCreate

    O->>X: Phase 3 — Extract
    Note over X: parse .claude/agents, skills, .mcp.json<br/>score orchestrator candidates<br/>infer architecture pattern<br/>mask secrets
    X-->>O: 01_extractor_ir.yaml

    alt mode == full
        O->>E: Phase 4 — Emit
        Note over E: synthesize main prompt<br/>build SUBAGENTS array<br/>@tool auto-wrap<br/>copy app/skills/<br/>langgraph.json + bootstrap_ui.sh
        E-->>O: ports/deepagents/app/*

        O->>V: Phase 5 — Validate (11 stages)
        Note over V: YAML parse · required files · compile<br/>· skill copy · secret scan · smoke import<br/>· anti-pattern · @tool · stream timeout · gitignore
        alt validation fail
            V->>E: SendMessage(fix)
            E->>V: re-emit
        end
        V-->>O: logs/validation.json
    end

    O->>R: Phase 6 — Report
    Note over R: merge IR + validation<br/>13-section conversion_report<br/>quality score (0.0~1.0)
    R-->>O: conversion_report.md

    O->>U: Phase 7 — Service-ready handoff<br/>(8-step run checklist)
```

---

## Generated app layout

```mermaid
graph LR

    Root["ports/deepagents/"]
    Root --> IR["harness.deepagents.ir.yaml<br/>(final IR)"]
    Root --> Report["conversion_report.md"]
    Root --> Logs["logs/validation.json"]
    Root --> App["app/"]

    App --> Agent["agent.py<br/>create_deep_agent +<br/>MAIN_SYSTEM_PROMPT +<br/>SUBAGENTS = [...]"]
    App --> Config["config.py<br/>Settings(model, app_name, ...)"]
    App --> Tools["tools.py<br/>@tool wrap +<br/>mock_fallback or<br/>strict_stub"]
    App --> Smoke["smoke_test.py"]
    App --> Reqs["requirements.txt"]
    App --> Proj["pyproject.toml"]
    App --> Readme["README.md<br/>(provider matrix +<br/>run sequences)"]
    App --> LG["⭐ langgraph.json<br/>graphs.deepagent →<br/>./agent.py:agent"]
    App --> Env["⭐ .env.example<br/>(5 providers)"]
    App --> Boot["⭐ bootstrap_ui.sh<br/>(chmod 0o755)"]
    App --> GI["⭐ .gitignore<br/>(protects .env)"]
    App --> Skills["skills/<br/>(copied from .claude/skills)"]
    App --> Mcp["(optional) .mcp.json +<br/>mcp_tools.py"]
```

⭐ marked items are **shipped by default from v0.2**, so users can launch deep-agents-ui with zero extra wiring.

---

## Default UI runtime topology

```mermaid
flowchart LR

    Browser[("🌐 Browser<br/>http://localhost:3000")]

    subgraph UIProc["Next.js UI process"]
        UI["langchain-ai/deep-agents-ui<br/>(./ui/ — cloned by bootstrap_ui.sh)"]
        EnvLocal["ui/.env.local<br/>NEXT_PUBLIC_DEPLOYMENT_URL=http://127.0.0.1:2024<br/>NEXT_PUBLIC_AGENT_ID=deepagent"]
    end

    subgraph BackendProc["Python backend process"]
        LGDev["langgraph dev --port 2024"]
        LGJson["langgraph.json<br/>graphs.deepagent → agent:agent"]
        AgentPy["agent.py<br/>create_deep_agent(...)"]
        Subagents["SUBAGENTS[]<br/>= original Harness agents"]
        ToolsPy["tools.py<br/>@tool wrapped"]
        SkillsDir["skills/<br/>(filesystem)"]
    end

    subgraph Provider["LLM provider (selected via .env)"]
        direction TB
        Anth["Anthropic"]
        Oai["OpenAI"]
        Az["Azure OpenAI"]
        Bed["Bedrock"]
        Vx["Vertex"]
    end

    Browser <-->|"LangGraph SDK<br/>WebSocket/HTTP"| UIProc
    UIProc <-->|"HTTP/WS :2024"| BackendProc
    LGDev --> LGJson --> AgentPy
    AgentPy --> Subagents
    AgentPy --> ToolsPy
    AgentPy --> SkillsDir
    AgentPy <-->|init_chat_model| Provider
```

**Run sequence (the generated app's README walks you through this):**

```bash
cd ports/deepagents/app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # uncomment a provider block + fill in keys
set -a; source .env; set +a
python smoke_test.py             # import sanity check

# Terminal A — backend
langgraph dev --port 2024 --no-browser
# → check http://127.0.0.1:2024/ok

# Terminal B — UI (bootstrap only once)
bash bootstrap_ui.sh
cd ui && yarn install            # Node 20+ recommended
yarn dev                         # http://localhost:3000
```

---

## Provider matrix (provider-agnostic)

`DEEPAGENTS_MODEL` follows LangChain's `init_chat_model` format. **Any provider works with zero code changes** — just edit `.env`.

```mermaid
flowchart TB

    Env["DEEPAGENTS_MODEL=<br/>provider:model"]

    Env --> Router{"init_chat_model<br/>(langchain)"}

    Router -->|"anthropic:claude-sonnet-4-6"| Anth["langchain-anthropic<br/>ANTHROPIC_API_KEY"]
    Router -->|"openai:gpt-4o"| Oai["langchain-openai<br/>OPENAI_API_KEY"]
    Router -->|"azure_openai:&lt;deployment&gt;"| Az["⭐ langchain-openai<br/>AZURE_OPENAI_API_KEY<br/>AZURE_OPENAI_ENDPOINT<br/>OPENAI_API_VERSION=<br/>2025-01-01-preview<br/>AZURE_OPENAI_DEPLOYMENT_NAME"]
    Router -->|"bedrock_converse:..."| Bed["langchain-aws<br/>AWS_ACCESS_KEY_ID<br/>AWS_SECRET_ACCESS_KEY<br/>AWS_REGION"]
    Router -->|"google_vertexai:..."| Vx["langchain-google-vertexai<br/>GOOGLE_APPLICATION_CREDENTIALS"]
```

| Provider | `DEEPAGENTS_MODEL` example | Required env | Extra install |
|---|---|---|---|
| **Anthropic** (default) | `anthropic:claude-sonnet-4-6` | `ANTHROPIC_API_KEY` | — (already bundled) |
| **OpenAI** | `openai:gpt-4o` | `OPENAI_API_KEY` | — (already bundled) |
| **Azure OpenAI** | `azure_openai:<deployment-name>` | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `OPENAI_API_VERSION=2025-01-01-preview`, `AZURE_OPENAI_DEPLOYMENT_NAME` | — (already bundled) |
| **AWS Bedrock** | `bedrock_converse:anthropic.claude-3-5-sonnet-...` | AWS keys + region | `pip install langchain-aws` |
| **Google Vertex** | `google_vertexai:gemini-1.5-pro` | GCP credentials | `pip install langchain-google-vertexai` |

> **Azure caveat:** `azure_openai:<deployment>` uses the **Azure deployment name**, not the OpenAI model id. GPT-5.x deployments require `OPENAI_API_VERSION=2025-01-01-preview` or newer.
>
> **Reasoning-model caveat** (gpt-5.x / o3 / claude-opus-extended-thinking): without `LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S=600`, runs abort with `StreamChunkTimeoutError`. The generated `.env.example` includes this by default.

---

## Validator 11-stage pipeline (v0.2)

`port-validator` checks the emitter's output across 11 stages. Any failure triggers one fix request to the emitter.

```mermaid
flowchart TB

    Start([emitter done])
    S1["1·IR YAML parse"]
    S2["2·required files present"]
    S3["3·python -m compileall app"]
    S4["4·skill folder count matches"]
    S5["5·Secret scan<br/>sk-, AKIA, ghp_, BEGIN PRIVATE KEY"]
    S6["6·smoke import<br/>import agent; agent.agent"]
    S7["7·Anti-pattern<br/>no 'from langgraph.graph'"]
    S8["⭐ 8·Tool registration (v0.2)<br/>@tool + TOOLS auto-registered +<br/>matches IR stubs"]
    S9["⭐ 9·Stream timeout sanity (v0.2)<br/>LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S ≥ 300"]
    S10["⭐ 10·Gitignore presence (v0.2)<br/>.env / .env.* / !.env.example"]
    S11["11·write validation.json"]

    Done([hand off to reporter])
    Fail{{"⚠️ Any stage fail"}}
    FixLoop["SendMessage to emitter<br/>(fix request, ×1)"]

    Start --> S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7 --> S8 --> S9 --> S10 --> S11 --> Done
    S1 & S2 & S3 & S4 & S5 & S6 & S7 & S8 & S9 & S10 -.->|fail| Fail
    Fail --> FixLoop --> S1
```

⭐ (stages 8/9/10) are **new in v0.2** — regression guards added after seeing v0.1 output break in real-world operation.

---

## Mapping rules (Harness → DeepAgents)

```mermaid
graph LR

    subgraph HARNESS["Harness side"]
        H_O["orchestrator skill"]
        H_A["agents/*.md"]
        H_S["skills/*"]
        H_C["CLAUDE.md"]
        H_W["_workspace/"]
        H_M[".mcp.json"]
        H_Op["Claude ops<br/>(TeamCreate / TaskCreate /<br/>SendMessage / parallel)"]
    end

    subgraph DA["DeepAgents side"]
        D_M["MAIN_SYSTEM_PROMPT<br/>(orchestrator + Notes +<br/>Delegation + Artifact + Safety)"]
        D_S["SUBAGENTS = [...]<br/>(name + desc + prompt + skills)"]
        D_Sk["app/skills/*<br/>(original structure preserved)"]
        D_R["README + runtime notes"]
        D_F["filesystem/artifact policy"]
        D_Mcp["masked .mcp.json +<br/>mcp_tools.py TODO"]
        D_Reg["subagent registry +<br/>delegation policy +<br/>main-agent-mediated handoff"]
    end

    H_O ==> D_M
    H_A ==> D_S
    H_S ==> D_Sk
    H_C ==> D_R
    H_W ==> D_F
    H_M ==> D_Mcp
    H_Op ==> D_Reg
```

| Harness | DeepAgents | Lossiness |
|---|---|---|
| `.claude/agents/*.md` body | subagent `system_prompt` (preserved as raw string) | Low |
| agent name / description | subagent `name` / `description` | Low |
| `.claude/skills/*/` whole tree | `app/skills/*/` (copied verbatim) | Low |
| `TeamCreate` | `SUBAGENTS` registry | Low |
| `TaskCreate` | main agent planning instruction | Medium |
| `SendMessage` | main-agent-mediated handoff | Medium |
| Peer-to-peer team chat | (cannot be expressed directly) | **High** |
| `Agent(..., run_in_background=true)` | parallel delegation instruction or TODO | Medium |

**Principle:** preserve the 4-axis separation of Who(agent) / How(skill) / When(orchestration) / What left(artifact). **No prompt flattening** — never merge several agent bodies into one main prompt.

---

## Mode matrix

```mermaid
flowchart TB

    U([User input])
    M{Mode}
    Tm{Tool policy}

    U --> M
    M -->|"default"| Full["full mode<br/>extract + emit + validate + report"]
    M -->|"'audit only',<br/>'분석만',<br/>'점검만'"| Audit["audit_only mode<br/>extract + report only<br/>(no code emission)"]

    Full --> Tm
    Tm -->|"default ⭐"| MF["mock_fallback (v0.2 default)<br/>stubs return MOCK data<br/>workflow runs end-to-end"]
    Tm -->|"'strict',<br/>'엄격',<br/>'raise on stub'"| SS["strict_stub<br/>stub calls raise NotImplementedError"]
```

**Why is `mock_fallback` the v0.2 default?** v0.1 shipped `raise NotImplementedError` + `TOOLS = []` by default, so the first tool call killed the workflow. That made demos, CI runs, and offline use impossible.

Even in mock mode, the emitter embeds **one or two reference implementations** (Z.AI / Tavily / FAL / httpx, etc.) as comments in each stub's docstring, so going from mock to real never starts from zero.

---

## Quick Start

### 1. Run it from a directory that has Harness artifacts

```bash
cd /path/to/your/harness-project   # has .claude/agents, .claude/skills
# In Claude Code:
/harness2deepagents
```

### 2. After conversion (~tens of seconds) you'll see

```
✅ DeepAgents app conversion complete
- output: ports/deepagents/
- conversion score: 0.92/1.00
- manual actions: 3
- tools_mode: mock_fallback

📋 Service-ready checklist:
1. cd ports/deepagents/app
2. python3 -m venv .venv && source .venv/bin/activate
3. pip install -r requirements.txt
4. cp .env.example .env  # fill in provider keys
5. set -a; source .env; set +a
6. python smoke_test.py
7. langgraph dev --port 2024 --no-browser
8. (optional) bash bootstrap_ui.sh && cd ui && yarn install && yarn dev
```

The checklist works as-is (thanks to the v0.2 regression guards).

### 3. Audit-only — just check convertibility

```bash
/harness2deepagents audit only
```

→ Produces only `_workspace/01_extractor_ir.yaml` + `conversion_report.md`. No code emitted.

---

## v0.2.0 operational pitfall catalogue

Pitfalls discovered while actually running v0.1 output all the way to a LangGraph backend + deep-agents-ui frontend. v0.2's emitter/validator now block all of these **at codegen time**.

| # | Symptom | v0.1 cause | v0.2 auto-prevention |
|---|---|---|---|
| F1 | First tool call hits `NotImplementedError` → workflow dies | stub `raise` + `TOOLS = []` | **mock_fallback default** + `TOOLS` auto-registered |
| F2 | LLM doesn't even know the tool exists | plain function (no args schema exposed) | **`@tool` decorator mandatory** (Stage 8 check) |
| F3 | Risk of committing `.env` | no `.gitignore` | **`app/.gitignore` auto-generated** (Stage 10 check) |
| F4 | `StreamChunkTimeoutError: 583 chunks then 120s silence` | langchain-openai default 120s is too short for reasoning models | `.env.example` includes **`LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S=600`** (Stage 9 check) |
| F5 | Azure GPT-5.x deployment doesn't respond | `OPENAI_API_VERSION=2024-10-21` is too old | Provider notes recommend **`2025-01-01-preview`** |
| F6 | Launching the UI is non-obvious (yarn install + Node 20) | README mentioned only `bash bootstrap_ui.sh` | README now has the **exact 3-command sequence** + Node version |
| F7 | Default `recursion_limit=25` runs out fast | DeepAgents plan/todo nodes consume cycles | README recommends **`recursion_limit=50`** |
| F8 | Confusion over where to run `langgraph dev` | langgraph.json location unclear | README spells out **`cd app && langgraph dev`** |
| F9 | `.env` vars don't take effect | `source .env` missing | README spells out **`set -a; source .env; set +a`** |
| F10 | `from langchain_core.tools import tool` import missing | langchain-core absent from requirements.txt | **Added to the minimum requirements** |

These were treated as **emitter/validator defects**, not mere documentation gaps. From v0.2 onward, every new build prevents them at codegen time.

---

## Error handling

```mermaid
flowchart TB

    Start([conversion start])
    Check{".claude/agents or<br/>.claude/skills present?"}
    NoSrc[["❌ exit immediately<br/>'no RevFactory Harness artifacts'<br/>no files created"]]
    ExtErr{extractor partial<br/>parse failure?}
    ExtWarn["proceed with available IR +<br/>log warnings"]
    EmitErr{emitter stage fail?}
    EmitRetry["1 retry"]
    EmitPartial["keep partial output +<br/>flag to reporter"]
    ValErr{validator fail<br/>(compile/secret)?}
    ValFix["fix request to<br/>emitter (×1)"]
    ValStill{still failing?}
    ValPartial["report it"]
    Done([reporter → User])

    Start --> Check
    Check -->|"no"| NoSrc
    Check -->|"yes"| ExtErr
    ExtErr -->|"yes"| ExtWarn
    ExtErr -->|"no"| EmitErr
    ExtWarn --> EmitErr
    EmitErr -->|"yes"| EmitRetry
    EmitErr -->|"no"| ValErr
    EmitRetry --> EmitPartial
    EmitPartial --> ValErr
    ValErr -->|"yes"| ValFix
    ValErr -->|"no"| Done
    ValFix --> ValStill
    ValStill -->|"yes"| ValPartial
    ValStill -->|"no"| Done
    ValPartial --> Done
```

| Situation | Strategy |
|---|---|
| No `.claude/` artifacts found | Exit immediately with a clear message, no files written |
| Partial extractor parse failure | Proceed with available IR + log warnings |
| Emitter stage failure | Retry once; if still failing, keep partial output |
| Validator fail | One fix request to emitter → re-validate → if still failing, reporter flags it |
| `ports/deepagents/` already exists | Create `ports/deepagents_YYYYMMDD_HHMMSS/` instead (never overwrite) |
| `audit_only` tries to trigger emit | Orchestrator blocks it |
| Team member stalls | Leader detects and restarts; if it still fails, reporter runs on partial results |

---

## Invariant safety rules

- 🔒 **Original `.claude/` is read-only** — never modified
- 🔒 **Output path stays inside the project root** — path-traversal blocked
- 🔒 **Secret masking** — `sk-...`, `AKIA...`, `ghp_...`, `BEGIN PRIVATE KEY` patterns are never exposed in IR / code / report
- 🔒 **No external API calls** — live invocation is forbidden (smoke_test only imports)
- 🔒 **No auto-launching of MCP servers** — `mcp_tools.py` is a TODO stub only
- 🔒 **No raw-LangGraph emitter** — blocked by Stage 7 anti-pattern check
- 🔒 **`.env` commits blocked** — emit auto-generates `.gitignore`

---

## Directory layout (this skill itself)

```
~/.claude/skills/harness2deepagents/
├── SKILL.md                       # orchestrator (the skill's entry point)
├── README.md                      # ← this file (English, default)
├── README_ko.md                   # Korean version
└── references/
    ├── ir-schema-summary.md       # IR YAML schema summary
    ├── mapping-rules.md           # Harness ops → DeepAgents mapping
    ├── usage-examples.md          # invocation examples + trigger patterns
    └── edge-cases.md              # EC-001 ~ EC-010

# Sister skills in the same working tree
~/.claude/skills/
├── harness-source-extraction/     # used by extractor (.claude → IR)
├── deepagents-emission/           # used by emitter (IR → app/)
│   ├── SKILL.md
│   ├── assets/                    # 11 *.tmpl codegen templates
│   ├── scripts/emit_deepagents.py # deterministic codegen engine
│   └── references/
│       ├── codegen-templates.md
│       ├── prompt-synthesis.md
│       ├── mcp-handling.md
│       └── tool-adapters.md       # v0.2 — provider-specific reference impls
├── port-validation/               # used by validator (11 stages)
└── conversion-reporting/          # used by reporter

# Agents in the same working tree
~/.claude/agents/
├── harness-extractor.md
├── deepagents-emitter.md
├── port-validator.md
└── conversion-reporter.md
```

---

## Further reading

| Doc | Contents |
|---|---|
| `SKILL.md` | orchestrator / 7-phase workflow / operational pitfall catalogue |
| `references/ir-schema-summary.md` | `harness.deepagents.ir.yaml` schema (PRD §12.2) |
| `references/mapping-rules.md` | Harness ↔ DeepAgents mapping rules (PRD §16) |
| `references/usage-examples.md` | trigger keywords / invocation patterns / run sequences |
| `references/edge-cases.md` | EC-001 ~ EC-010 |
| `../deepagents-emission/SKILL.md` | 9-step emit procedure / template variables |
| `../deepagents-emission/references/tool-adapters.md` | web_search / fetch_url / image_gen — Z.AI / Tavily / FAL implementations |
| `../port-validation/SKILL.md` | 11-stage validation procedure |
| `../conversion-reporting/SKILL.md` | 13-section report structure + quality-score weights |

---

## In one line

> **`/harness` designs the agent team; `/harness2deepagents` turns it into a runnable LangChain DeepAgents app — UI included, provider-agnostic, operational pitfalls auto-prevented.**
