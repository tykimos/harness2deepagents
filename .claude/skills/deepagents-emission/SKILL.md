---
name: deepagents-emission
description: "harness.deepagents.ir.yaml을 입력으로 받아 실행 가능한 DeepAgents Python 앱(agent.py, config.py, tools.py, mcp_tools.py, smoke_test.py, requirements.txt, pyproject.toml, README.md, app/skills/*)을 생성하는 코드 방출 스킬. create_deep_agent 기반 main agent + subagents 구조. raw LangGraph 절대 생성 금지. deepagents-emitter 에이전트가 사용."
---

# DeepAgents Emission

IR을 입력으로 DeepAgents 앱 코드를 생성하는 작업 스킬. 코드 생성은 `scripts/emit_deepagents.py` + `assets/*.j2` Jinja2 템플릿으로 결정적 처리한다.

## 핵심 원칙

1. **DeepAgents only** — `from deepagents import create_deep_agent`만 사용. `langgraph.graph`, 단일 `create_agent` import 금지.
2. **IR이 single source of truth** — IR에 없는 정보는 생성하지 않는다. IR 보강이 필요하면 extractor에게 요청.
3. **프롬프트 평탄화 금지** — agents → SUBAGENTS 배열로 분리. main prompt에 모든 agent body를 합치지 않는다.
4. **모델 env var는 한 곳** — `config.py`에만 `os.getenv("DEEPAGENTS_MODEL", "anthropic:claude-sonnet-4-6")`. agent.py에 모델명 하드코딩 금지.
5. **기존 output 보존** — `ports/deepagents/`가 있으면 `ports/deepagents_YYYYMMDD_HHMMSS/`로 폴백.

## 방출 9단계

### 1. Output 디렉토리 결정

```bash
python scripts/emit_deepagents.py resolve-output --root <root>
# stdout: ports/deepagents/  또는  ports/deepagents_YYYYMMDD_HHMMSS/
```

**Path traversal 차단** — 출력 경로가 `<root>` 하위인지 검증.

### 2. IR 로드 + 검증

```bash
python scripts/emit_deepagents.py load-ir --path _workspace/01_extractor_ir.yaml
```

필수 필드 누락 시 emit 중단 + extractor에 IR 보강 요청.

### 3. Main system prompt 합성

PRD §13.7 블록 구조로 합성:

```text
# Converted Harness Orchestrator
<원본 orchestrator prompt 또는 synthetic prompt>

# Conversion Notes
- This app was converted from RevFactory Harness output.
- Use DeepAgents subagents instead of Claude Code Agent Teams.
- Treat TeamCreate as the available subagent registry.
- Treat TaskCreate as planning and delegation.
- Treat SendMessage as result handoff mediated by the main agent.

# Delegation Policy
<IR workflow.delegation_policy>

# Artifact Policy
<IR artifacts.workspace_dir + artifact_conventions>

# Safety and Validation Policy
<tool warnings, MCP warnings, TODO stubs>
```

오케스트레이터 미발견 시: agents/skills를 기반으로 synthetic prompt 합성. 패턴별 prompt 전략은 PRD §16.3 표 참조.

### 4. Subagent 합성

각 IR `agents[]` 항목을 dict로:

```python
{
    "name": "<agent_name>",
    "description": "<routing description from IR.description>",
    "system_prompt": r'''<원본 agent body + DeepAgents Runtime Notes 부록>''',
    "skills": ["/skills/<skill_name>/", ...],  # IR.deepagents.skills
}
```

DeepAgents Runtime Notes 부록 (각 subagent prompt 끝에 추가):
```text
# DeepAgents Runtime Notes
You are running as a DeepAgents subagent.
Return concise, structured results to the main agent.
Write large intermediate outputs to the filesystem when appropriate.
Do not assume direct peer-to-peer SendMessage; communicate through task results.
```

### 5. 코드 템플릿 렌더링

Jinja2 렌더링:

| 템플릿 | 출력 | 입력 |
|---|---|---|
| `assets/agent.py.tmpl` | `app/agent.py` | main_prompt, subagents, tools_imports, skills_path |
| `assets/config.py.tmpl` | `app/config.py` | model_env_var, model_default, app_name_default |
| `assets/tools.py.tmpl` | `app/tools.py` | tool_stubs[] |
| `assets/mcp_tools.py.tmpl` | `app/mcp_tools.py` | (MCP 감지 시만) |
| `assets/smoke_test.py.tmpl` | `app/smoke_test.py` | — |
| `assets/requirements.txt.tmpl` | `app/requirements.txt` | extra_deps |
| `assets/pyproject.toml.tmpl` | `app/pyproject.toml` | project_name, source, target |
| `assets/README.md.tmpl` | `app/README.md` | source_summary, env_vars, run_commands, mcp_actions |
| `assets/langgraph.json.tmpl` | `app/langgraph.json` | (deep-agents-ui 기본 연동) graph id=`deepagent` |
| `assets/env.example.tmpl` | `app/.env.example` | model_default, app_name_default, mcp_env_vars_block |
| `assets/bootstrap_ui.sh.tmpl` | `app/bootstrap_ui.sh` | (chmod 0o755) — langchain-ai/deep-agents-ui clone + wire |
| `assets/gitignore.tmpl` | `app/.gitignore` | `.env`/`.env.*`/`!.env.example`/`__pycache__`/`.venv`/`ui/` 등 보호 |

```bash
python scripts/emit_deepagents.py render --ir _workspace/01_extractor_ir.yaml --out <output_dir>/app
```

### 6. Skills 디렉토리 복사

`.claude/skills/*/`를 `<output_dir>/app/skills/*/`로 복사:

- `SKILL.md`, `references/`, `scripts/`, `assets/` 보존
- `.git`, `.venv`, `__pycache__`, `.DS_Store` 제외
- 원본 파일 절대 수정 금지
- 이름 충돌 시 `{name}__{idx}`로 deterministic rename + warning

```bash
python scripts/emit_deepagents.py copy-skills --ir _workspace/01_extractor_ir.yaml --out <output_dir>/app/skills
```

### 7. MCP 처리

`.mcp.json` 발견 시:
- secret-like literal 마스킹 (`sk-...` → `***REDACTED***`) 후 `<output_dir>/app/.mcp.json`으로 복사
- env var 참조는 그대로 유지
- `mcp_tools.py`에 adapter TODO 생성 (load_mcp_tools 함수 stub)
- README에 MCP 후속 작업 안내 추가

### 8. Tool stub 생성

**핵심 원칙 (v0.2 갱신, 운영 경험 기반):**

- 도구는 항상 `langchain_core.tools.@tool` 데코레이터로 정의한다. plain function은 도구 메타데이터(name, args schema, description)가 LLM에 노출되지 않을 위험이 있다.
- **기본 동작은 `mock_fallback` 모드** — stub은 명확히 라벨된 MOCK 데이터를 반환하여 키 없이도 워크플로우가 끝까지 돈다. 이전 `NotImplementedError`만 raise하던 정책은 첫 호출에서 워크플로우를 죽여 운영 가치가 거의 없었다.
- **`TOOLS` 리스트는 모든 생성된 stub을 자동 등록한다.** 이전엔 `TOOLS = []`로 비워두는 정책이었지만, 그 결과 LLM이 도구를 알지조차 못해 "정의는 됐으나 호출 불가" 상태가 되어 운영 사고를 유발.
- IR에 `tools_mode: "strict_stub"`가 명시되어 있으면 `mock_fallback` 대신 `raise NotImplementedError`로 폴백. 사용자가 강한 실패를 원하는 경우 옵션 제공.

**기본 (mock_fallback) 템플릿:**

```python
from langchain_core.tools import tool

@tool
def web_search_stub(query: str, count: int = 5) -> str:
    """Search the web for information.

    Returns MOCK data by default. Replace this body with a real adapter
    (Tavily / SerpAPI / DuckDuckGo / Z.AI web_search / MCP web-search) for
    production. The MOCK keeps the workflow runnable end-to-end during
    development and demo without external credentials.

    Source: <agent_or_skill_name from IR>
    Inferred purpose: <reason from IR>

    Args:
        query: Natural-language search query.
        count: Number of results to return (advisory).
    """
    return (
        f"[MOCK web_search_stub for query: {query!r}]\n\n"
        "1. https://example.com/result-1 — top result snippet\n"
        "2. https://example.com/result-2 — secondary perspective\n"
        "3. https://example.com/result-3 — competitor/community reference\n"
        "[end of mock results — implement a real adapter before production]"
    )


TOOLS = [
    web_search_stub,
    # ...other generated stubs registered automatically
]
```

**Strict 모드 (IR `tools_mode: "strict_stub"`):**

```python
@tool
def web_search_stub(query: str) -> str:
    """TODO: implement. Calling this raises NotImplementedError until wired."""
    raise NotImplementedError(
        "web_search_stub is a placeholder. Implement before calling, "
        "or rerun emitter with tools_mode=mock_fallback."
    )
```

**Concrete reference implementations (commented in tools.py docstring):**

각 stub에 운영용 어댑터 예시 1개를 docstring 주석으로 함께 emit한다. 사용자가 mock에서 real로 갈 때 0부터 시작하지 않도록:

```python
@tool
def web_search_stub(query: str, count: int = 5) -> str:
    """...
    
    Reference implementation (Z.AI web_search):
        from zai import ZaiClient
        client = ZaiClient(api_key=os.environ["ZAI_API_KEY"])
        resp = client.web_search.web_search(
            search_engine="search-prime", search_query=query,
            count=count, search_recency_filter="noLimit",
        )
        return format_results(resp.search_result)
    
    Reference implementation (Tavily):
        from tavily import TavilyClient
        client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
        return client.search(query=query, max_results=count)
    """
    ...
```

`fetch_url_stub`는 Z.AI Web Reader (`POST https://api.z.ai/api/paas/v4/reader`) 또는 `httpx + readability-lxml`를 reference로 제시.
`image_generation_stub`는 Z.AI cogview-4 / FAL flux-schnell / Replicate / Azure OpenAI gpt-image를 reference로 제시. mock 모드에서는 1×1 PNG placeholder를 실제로 디스크에 쓴다 (workflow의 후속 단계가 파일 경로를 받아쓰므로).

**위험한 도구 (shell exec, raw exec, eval 등):** 여전히 기본 disabled. `TOOLS`에 포함하지 않고, docstring 상단에 `# DANGEROUS — review before enabling` 명시.

### 9. IR 최종본 이동

`_workspace/01_extractor_ir.yaml` → `<output_dir>/harness.deepagents.ir.yaml`로 복사 (원본도 보존).

## 코드 템플릿 핵심 규칙

### `agent.py` 필수 요소

- 헤더 docstring: "DeepAgents app generated by harness2deepagents"
- `from deepagents import create_deep_agent`
- `from config import SETTINGS`
- `from tools import TOOLS`
- `MAIN_SYSTEM_PROMPT = r'''...'''` (raw string으로 prompt 보존)
- `SUBAGENTS = [...]` (사람이 수정하기 쉬운 list of dict)
- `agent = create_deep_agent(...)` 단일 호출
- `def invoke(user_message): ...`
- `if __name__ == "__main__": ...`

### `config.py` 필수 요소

- `@dataclass(frozen=True) class Settings`
- `app_name`, `model`, `enable_mcp`, `dry_run` env var 처리
- `SETTINGS = Settings()` 인스턴스

### `requirements.txt` 최소

```
deepagents
langchain
langchain-core            # @tool 데코레이터 (tools.py가 의존)
langchain-anthropic
langchain-openai          # OpenAI + Azure OpenAI 기본 지원
langgraph-cli[inmem]      # `langgraph dev` 로 deep-agents-ui 백엔드 서빙
python-dotenv
pyyaml
requests                  # fetch_url_stub reference impl + Z.AI Web Reader 등
```

`zai-sdk`, `tavily-python`, `httpx`, `readability-lxml` 같은 provider-specific 패키지는 README의 "Choose your provider" 표에 옵션으로 안내. 기본 requirements에는 넣지 않는다 (사용자가 선택한 어댑터만 설치하도록 가벼움 유지).

### `.env.example` 필수 라인

```
DEEPAGENTS_MODEL=anthropic:claude-sonnet-4-6
DEEPAGENTS_APP_NAME=converted_harness
DEEPAGENTS_ENABLE_MCP=false
DEEPAGENTS_DRY_RUN=false

# ----- langchain-openai stream tuning (REQUIRED for reasoning models) -----
# Default in langchain-openai is 120s; gpt-5.x / o3 / claude-opus-extended-thinking
# routinely pause longer between stream chunks. Set this to avoid
# StreamChunkTimeoutError mid-run.
LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S=600

ANTHROPIC_API_KEY=

# (provider blocks: OpenAI / Azure OpenAI / Bedrock / Vertex — fill in one)
```

**Azure OpenAI 블록 주의:** GPT-5.x 계열 deployment는 `OPENAI_API_VERSION=2025-01-01-preview` 이상이 필요하다. `.env.example`에 권장값으로 명시한다 (2024-10-21 등 구버전은 호환되지 않을 수 있음).

### `.gitignore` 필수 라인

```
# Secrets — NEVER commit
.env
.env.*
!.env.example

# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
.pytest_cache/

# Tooling
.langgraph_api/
.langgraph_cache/
ui/                       # deep-agents-ui clone (bootstrap_ui.sh로 생성)
node_modules/

# OS / Editor
.DS_Store
*.swp
```

`.env`를 절대 커밋하지 않도록 보호. UI clone(`ui/`)도 무거우므로 제외.

### 기본 UI: langchain-ai/deep-agents-ui

생성되는 모든 DeepAgents 앱은 `langchain-ai/deep-agents-ui`를 기본 프론트엔드로 가진다.

- `app/langgraph.json` — graph id `deepagent` (UI 기본값과 일치)
- `app/bootstrap_ui.sh` — `./ui/`에 deep-agents-ui clone + `ui/.env.local` (URL/agent id) 자동 생성
- `app/.env.example` — Anthropic / OpenAI / Azure OpenAI / Bedrock / Vertex 프로바이더 블록 포함
- README의 "Run with the default UI"가 기본 실행 경로

emit 시 `bootstrap_ui.sh`에는 chmod 0o755 부여. UI 자체는 emit 단계에서 clone하지 않음(사용자가 1회 실행).

## 작업 원칙

- **원본 prompt 보존** — agent body는 raw string(`r'''...'''`)으로 그대로 삽입. 임의 요약 금지.
- **사람이 수정 가능한 코드** — SUBAGENTS는 list literal로 표현. 동적 생성 금지.
- **TODO는 명확히** — 위치, 이유, 출처를 docstring에 모두 표시.
- **너무 큰 prompt(>50KB)** — warning만 기록하고 보존 우선. v0.3+에서 prompts/ 분리 고려.

## 안전 규칙

- 원본 `.claude/` 절대 수정 금지
- 출력 경로는 project root 아래로 제한
- secret literal은 절대 코드/IR에 하드코딩 금지
- raw LangGraph emitter 생성 금지 — 검증 단계에서 차단
- MCP 서버 자동 실행 금지

## 검증 후 재방출 (validator와의 협업)

validator가 fail 보고 시:
1. 받은 fix 지시(파일:라인, 위반 내용)를 IR과 대조
2. 해당 파일만 재렌더링 (전체 재방출 아님)
3. 1회까지만 재시도. 두 번째 실패는 오케스트레이터에게 에스컬레이트.

## README emit 시 필수 섹션 (v0.2)

생성되는 `app/README.md`는 다음 순서로 구성한다. 운영 사용자가 첫 30분 안에 UI까지 띄울 수 있도록 한다.

1. **Source summary** — 어떤 하네스에서 변환됐는지 한 줄
2. **Choose your stack** — 표 형식. Anthropic-only / OpenAI / Azure OpenAI / Bedrock / Vertex / Z.AI(OpenAI 호환 base_url 트릭) 각각의 `DEEPAGENTS_MODEL` 값 + 필요 env vars
3. **Local setup** — 정확한 명령 시퀀스:
   ```
   cd app
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   # .env 편집해서 자기 provider 키 채우기
   set -a; source .env; set +a
   python smoke_test.py        # import 확인
   ```
4. **Run the backend (langgraph dev)**
   ```
   langgraph dev --port 2024 --no-browser
   # → http://127.0.0.1:2024/ok 응답 확인
   # → Assistant 등록: graph_id=deepagent
   ```
5. **Run with the default UI**
   ```
   bash bootstrap_ui.sh          # langchain-ai/deep-agents-ui clone + .env.local
   cd ui && yarn install         # Node 20+ 권장
   yarn dev                       # http://localhost:3000
   ```
   UI는 별도 로그인 없음. Settings 다이얼로그가 뜨면 deployment URL `http://127.0.0.1:2024` + Assistant ID `deepagent`로 자동 채워져 있음.
6. **Provider notes**
   - Azure OpenAI: `OPENAI_API_VERSION=2025-01-01-preview` 이상 필요 (GPT-5.x 계열)
   - 모든 reasoning 모델: `LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S=600` 이상 권장
7. **Implement real tools** — `tools.py`의 stub들을 어떻게 실 어댑터로 교체할지. 각 stub에 reference impl 주석이 이미 있음을 강조.
8. **Security checklist** — `.env` 절대 커밋 금지 (`.gitignore` 자동 생성됨), 키 회전 권장, MCP secret env-var화 (raw 문자열 금지)

## 운영 배포에서 얻은 함정 모음 (v0.2 changelog)

이 스킬을 통해 emit된 앱을 실제로 끝까지 (UI까지) 띄워본 결과 다음 함정들이 발견되어 v0.2에서 수정되었다. emitter 코드/템플릿을 수정할 때 이 모음을 회귀 체크리스트로 활용한다.

| # | 증상 | 원인 | v0.2 대응 |
|---|---|---|---|
| L1 | 첫 도구 호출에서 워크플로우 즉사 | `raise NotImplementedError` 정책 + `TOOLS = []` 비워둠 | mock_fallback 기본 + `TOOLS`에 모든 stub 자동 등록 |
| L2 | LLM이 도구 자체를 모름 | tools.py에 정의만 있고 노출 안 됨 | `@tool` 데코레이터 의무화 + `TOOLS` 자동 채움 |
| L3 | `.env` 커밋 위험 | `.gitignore` 부재 | `app/.gitignore` 자동 생성 |
| L4 | `StreamChunkTimeoutError: 583 chunks then 120s silence` | 기본 stream_chunk_timeout 120s가 reasoning 모델에 짧음 | `.env.example`에 `LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S=600` 라인 + README provider notes |
| L5 | UI 띄우려면 yarn install이 또 필요한 줄 몰랐음 | README가 `bash bootstrap_ui.sh`만 언급 | README "Run with the default UI"에 정확한 3줄 명령 시퀀스 |
| L6 | Azure GPT-5.x API_VERSION 오작동 | `.env.example`이 구버전 2024-10-21 가리킴 | `2025-01-01-preview` 권장값 + provider notes |
| L7 | recursion_limit 기본 25에서 deep agent가 의외로 빨리 한도 도달 | DeepAgents의 plan/todo 노드가 사이클 소비 | README에 "실제 워크플로우는 `config={'recursion_limit': 50}` 이상 권장" 명시 |
| L8 | `langgraph dev`가 어디서 실행돼야 하는지 모름 | langgraph.json은 app/에 있음 | README에 `cd app && langgraph dev` 명시 |
| L9 | `.env` env-var이 안 먹혀서 키 누락 | `langgraph dev` 시작 전 `source .env` 누락 | README에 `set -a; source .env; set +a` 명시 |
| L10 | 도구가 진짜로 작동했는지 import만으로 알 수 없음 | smoke_test가 import 검사만 | 옵션: `--probe` 플래그로 메타 질문 1회 round-trip (live, 비용 발생, 기본 off) |

## 참고

- 코드 템플릿 상세: `references/codegen-templates.md`
- prompt 합성 규칙 (패턴별): `references/prompt-synthesis.md`
- MCP 처리 규칙: `references/mcp-handling.md`
- Skill 매핑 규칙: `references/skill-assignment.md`
- 도구 어댑터 reference 구현 모음: `references/tool-adapters.md` (web_search / fetch_url / image_generation 각각의 Z.AI / Tavily / FAL 등 구체 예시)
