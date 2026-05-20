---
name: port-validation
description: "생성된 DeepAgents 앱이 import/compile/smoke test 가능한지, secret leak이 없는지, skill copy가 완전한지, raw LangGraph emitter 패턴이 없는지 7단계로 검증하는 스킬. logs/validation.json 생성 + 실패 시 emitter에게 fix 요청 1회. live invocation은 절대 수행하지 않음. port-validator 에이전트가 사용."
---

# Port Validation

DeepAgents 포팅 결과를 7단계로 검증하는 작업 스킬. 결정적 검증은 `scripts/`로 위임.

## 7단계 Validation Pipeline

### Stage 1: Source validation

- IR 경로 존재 확인 (`<output_dir>/harness.deepagents.ir.yaml`)
- IR YAML parse 가능 여부
- Source fingerprint 일치 여부 (선택)

```bash
python scripts/validate_port.py source --output <output_dir>
```

실패 → `fail`. extractor에 IR 재생성 요청.

### Stage 2: IR validation

- 필수 필드 존재: `schema_version`, `source`, `target`, `harness`, `agents`, `skills`
- agents 배열 비어있지 않음 (또는 skills_only 모드 표시 있음)
- target.runtime == "deepagents"
- target.emit_raw_langgraph == false

실패 → `fail`. emitter 진행 차단.

### Stage 3: Output file validation

필수 파일 존재 확인:
- `app/agent.py`
- `app/config.py`
- `app/tools.py`
- `app/smoke_test.py`
- `app/requirements.txt`
- `app/pyproject.toml`
- `app/README.md`
- `app/skills/` (skill 있으면)
- `app/mcp_tools.py` (MCP 감지 시)
- `app/.mcp.json` (감지 시)

```bash
python scripts/validate_port.py files --output <output_dir>
```

누락 → `fail`. emitter에 누락 파일 생성 요청.

### Stage 4: Python syntax validation

```bash
python -m compileall <output_dir>/app
```

- 모든 `.py` 파일이 syntax 통과해야 함
- 실패 시 에러 메시지에서 파일:라인 추출하여 emitter에게 전달

`SyntaxError`만 fail. `ImportError` (deepagents 미설치) → `warn`으로 처리하고 README에 설치 지침 강조.

### Stage 5: Skill copy validation

- IR `skills[]` 항목 수 == `app/skills/` 하위 디렉토리 수
- 각 skill 폴더에 `SKILL.md` 존재
- `.git`, `__pycache__` 같은 제외 대상이 복사되지 않았는지

```bash
python scripts/validate_port.py skills --ir <output_dir>/harness.deepagents.ir.yaml --output <output_dir>/app/skills
```

불일치 → `fail`. emitter에 누락 skill 복사 요청.

### Stage 6: Secret scan

`scripts/secret_scan.py`로 출력 전체 스캔:

| 패턴 | 분류 |
|---|---|
| `sk-` (API key prefix) | fail (raw) / warn (masked) |
| `AKIA` | fail / warn |
| `ghp_`, `gho_`, `ghu_`, `ghs_` (GitHub tokens) | fail / warn |
| `xoxb-` (Slack) | fail / warn |
| `-----BEGIN PRIVATE KEY-----` | fail / warn |
| `api_key = "..."` (literal) | fail / warn |
| `token = "..."` | fail / warn |
| `password = "..."` | fail / warn |
| `***REDACTED***` (mask 발견) | warn (의도된 마스킹) |

```bash
python scripts/secret_scan.py --output <output_dir> --report
```

raw secret 발견 → `fail`. emitter에게 즉시 마스킹 + 재방출 요청. **원본 파일 절대 그대로 두지 않음**.

### Stage 7: Smoke import test

```bash
cd <output_dir>/app && python -c "import agent; assert hasattr(agent, 'agent')"
```

- import 성공 + `agent` 객체 존재 → `pass`
- ImportError (deepagents not installed) → `warn` → `not_run`. README에 `pip install -r requirements.txt` 지침 강조
- AttributeError, NameError → `fail`. emitter에 보고

**Live invocation 절대 금지** — `agent.invoke(...)` 호출하지 않음.

### Stage 8 (Anti-pattern check)

`<output_dir>/app/` 전체에서:
- `from langgraph.graph import` 등장 → `fail` (DeepAgents only 위반)
- `langgraph.graph.StateGraph` 사용 → `fail`
- `from langchain.agents import create_agent` (단일 에이전트) → `warn`

```bash
python scripts/validate_port.py anti-patterns --output <output_dir>/app
```

raw LangGraph emitter 발견 시 → `fail`. emitter에게 재방출 요청.

### Stage 9 (Tool registration check) — v0.2

IR `tools.stubs_required[]`가 비어있지 않다면, `app/tools.py`가 다음을 모두 충족해야 한다:

1. `from langchain_core.tools import tool` import 존재 (각 stub에 `@tool` 데코레이터 적용 의무)
2. IR이 요구한 모든 stub 함수가 정의되어 있음
3. `TOOLS = [...]` 리스트에 그 stub들이 **자동 등록**되어 있음 (변수명으로 참조)
4. `TOOLS`가 빈 리스트(`[]`)가 아니어야 함

```bash
python scripts/validate_port.py tools --ir <output_dir>/harness.deepagents.ir.yaml --output <output_dir>/app/tools.py
```

판정:

| 상황 | 분류 |
|---|---|
| 모든 IR stub이 정의 + TOOLS에 등록 | `pass` |
| 정의는 됐지만 TOOLS에 빠진 stub 존재 | `fail` — emitter가 등록 누락 |
| `@tool` 데코레이터 없는 함수가 TOOLS에 들어감 | `fail` — LLM에 args schema가 노출되지 않음 |
| IR이 strict 모드인데 mock_fallback 본문 detected (혹은 그 반대) | `warn` — mode 불일치 |
| IR `tools.stubs_required[]`가 빈 배열 | `not_run` (skip) |

이 단계가 v0.1엔 없었고, 그 결과 LLM이 도구를 인지하지 못해 워크플로우가 silent failure에 빠지는 사례가 발생했다. v0.2부터 필수 게이트.

### Stage 10 (Stream timeout sanity) — v0.2

`<output_dir>/app/.env.example`에 다음 패턴이 있어야 한다:

- `LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S=` (값은 600 이상 권장)

누락 시 → `warn`. reasoning 모델(gpt-5.x, o3, claude-opus extended thinking)에서 mid-stream timeout으로 워크플로우가 죽는 사례가 빈번하다.

판정:

| 상황 | 분류 |
|---|---|
| 라인 존재 + 값 ≥ 300 | `pass` |
| 라인 존재 + 값 < 300 | `warn` (reasoning 모델에서 위험) |
| 라인 부재 | `warn` + remediation: "Add LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S=600 to .env.example" |

### Stage 11 (Gitignore presence) — v0.2

`<output_dir>/app/.gitignore`가 존재하고 다음 패턴을 포함해야 한다:

- `.env` (단독 라인)
- `.env.*` 또는 그와 동등
- `!.env.example` (allowlist)

판정:

| 상황 | 분류 |
|---|---|
| 파일 존재 + 3개 패턴 모두 포함 | `pass` |
| 파일 존재 + 패턴 일부 누락 | `warn` + remediation 라인 명시 |
| 파일 부재 | `fail` — `.env` 커밋 위험. emitter에 즉시 fix 요청 |

## 출력 형식

`<output_dir>/logs/validation.json`:

```json
{
  "status": "pass | pass_with_warnings | fail",
  "checks": [
    {"name": "ir_yaml_parse", "status": "pass", "details": []},
    {"name": "ir_required_fields", "status": "pass", "details": []},
    {"name": "required_files", "status": "pass", "details": []},
    {"name": "python_compile", "status": "pass", "details": []},
    {"name": "skill_copy", "status": "pass", "details": []},
    {"name": "secret_scan", "status": "warn", "details": ["Potential token pattern in .mcp.json was masked"]},
    {"name": "smoke_test", "status": "pass", "details": []},
    {"name": "raw_langgraph_emitter", "status": "pass", "details": []},
    {"name": "tool_registration", "status": "pass", "details": ["3/3 stubs registered with @tool"]},
    {"name": "stream_timeout_sanity", "status": "pass", "details": ["LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S=600"]},
    {"name": "gitignore_presence", "status": "pass", "details": [".env, .env.*, !.env.example all present"]}
  ],
  "fix_requests_sent": 0,
  "fix_loop_exhausted": false
}
```

`_workspace/03_validator_summary.md`: 사람이 읽을 수 있는 요약 (오케스트레이터/reporter용).

## 작업 원칙

- **부분 실패 보존** — 한 단계가 실패해도 나머지를 계속 실행한다.
- **심각도 명확히** — `pass` / `warn` / `fail` / `not_run`. 모호한 'partial' 같은 상태 만들지 않는다.
- **Fix loop 1회** — 같은 이슈에 대해 emitter에게 fix 요청은 최대 1회. 두 번째 실패는 오케스트레이터에게 에스컬레이트.
- **Live API 호출 금지** — import + 객체 존재까지만 확인.
- **결정적 검증은 scripts에 위임** — LLM이 정규식/compileall 흉내내지 않음.

## 안전 규칙

- raw secret 발견 시 details에 위치만 기록하고 secret 값 자체는 절대 노출하지 않음 (마스킹된 길이/타입만 기록 가능)
- 검증 실행 중 출력 파일 수정하지 않음 (read-only 검증)
- 스크립트 실행은 `<output_dir>` 하위로 제한

## 참고

- secret 패턴 전체 목록: `references/secret-patterns.md`
- compileall 에러 파싱 가이드: `references/compile-error-parsing.md`
- 검증 단계별 임계값: `references/validation-thresholds.md`
