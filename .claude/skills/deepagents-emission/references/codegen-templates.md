# Codegen Templates

`assets/*.tmpl` 파일의 placeholder 변수와 의미.

## Placeholder 문법

`{{ VAR_NAME }}` — 대문자 + 언더스코어. `emit_deepagents.py`의 `render_template()`이 dict 매핑으로 치환. 미정의 키는 빈 문자열로 치환.

## 공통 변수

| 변수 | 의미 | 출처 |
|---|---|---|
| `{{SOURCE_ROOT}}` | 원본 프로젝트 경로 | IR.source.root |
| `{{GENERATED_AT}}` | ISO 타임스탬프 | now() |
| `{{PROJECT_NAME}}` | pyproject 이름 | "converted-harness-deepagents" |
| `{{APP_NAME_DEFAULT}}` | 앱 이름 기본값 | "converted_harness" |
| `{{MODEL_DEFAULT}}` | 모델 식별자 기본값 | IR.target.model.default |
| `{{ARCHITECTURE_PATTERN}}` | 감지된 패턴 | IR.harness.architecture_pattern.value |
| `{{PATTERN_CONFIDENCE}}` | 패턴 신뢰도 | IR.harness.architecture_pattern.confidence |
| `{{AGENT_COUNT}}` | agents 수 | len(IR.agents) |
| `{{SKILL_COUNT}}` | skills 수 | len(IR.skills) |

## 템플릿별 추가 변수

### `agent.py.tmpl`
- `{{MAIN_SYSTEM_PROMPT}}` — 합성된 main prompt (raw string으로 삽입). `synthesize_main_prompt(ir)`의 결과
- `{{SUBAGENTS_LITERAL}}` — Python list literal (사람이 읽고 수정 가능한 형태). `render_subagents_literal()`의 결과

### `config.py.tmpl`
- 공통 변수만 사용

### `tools.py.tmpl`
- `{{TOOL_STUBS}}` — 함수 정의 묶음 (각 stub: docstring + NotImplementedError)
- `{{TOOLS_LIST}}` — TOOLS 배열 안의 주석 처리된 항목들 (사용자가 unconmment하여 활성화)

### `mcp_tools.py.tmpl`
- `{{MCP_SERVERS}}` — 감지된 server 이름 리스트
- `{{MCP_ENV_VARS}}` — 필요한 env var 리스트

### `README.md.tmpl`
- `{{MCP_STATUS}}` — "detected and copied (secrets masked)" 또는 "not detected"
- `{{EXTRA_ENV_VARS_TABLE}}` — MCP env var 추가 안내 (선택)

## 템플릿 추가 시 규칙

1. 새 placeholder는 `emit_deepagents.py`의 `common_vars` dict에 추가
2. 미정의 placeholder는 빈 문자열로 치환되므로 누락에 안전
3. raw string(`r"""..."""`) 안에 placeholder를 둘 때 trailing 따옴표 충돌 주의
4. JSON/Python literal은 `json.dumps`로 미리 escape 후 placeholder에 삽입

## 안전 규칙

- 템플릿 안에 secret 하드코딩 금지 (env var만 사용)
- 템플릿 수정 후에는 `python -m compileall` 통과 확인
