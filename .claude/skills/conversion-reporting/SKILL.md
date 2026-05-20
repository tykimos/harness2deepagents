---
name: conversion-reporting
description: "harness.deepagents.ir.yaml과 logs/validation.json을 통합하여 사람이 읽을 수 있는 conversion_report.md를 작성하는 보고 스킬. PRD §19.1 13개 섹션 구조, 변환 품질 점수(0.0~1.0) 산출, manual actions 도출, run commands 안내, limitations 명시. audit_only 모드에서도 항상 생성. conversion-reporter 에이전트가 사용."
---

# Conversion Reporting

IR과 validation 결과를 통합하여 사람이 읽을 수 있는 변환 보고서를 작성하는 스킬.

## Report 구조 (13개 섹션)

PRD §19.1을 따라 다음 순서:

```markdown
# harness2deepagents Conversion Report

## Summary
- 한 단락 요약 + 변환 점수 + 모드(full|audit_only)

## Source Discovery
- root, detected_files (agents/skills/orchestrator/mcp/settings 카운트)

## Detected Harness Architecture
- pattern (confidence + evidence), execution_mode, workspace_dir

## Agents
- 표: name | role summary | model_hint | skills_attached | warnings

## Skills
- 표: name | description (truncated) | size | portable | warnings

## Orchestrator
- found 여부, source_file, detected_operations 표

## DeepAgents Mapping
- 원본 → DeepAgents 매핑 표
- 패턴별 prompt 전략

## Claude-only Operations
- 표: operation | count | mapping | lossiness (low/medium/high)

## Tools and MCP
- mcp_servers, langchain_tools, stubs_required, environment_variables

## Generated Files
- 트리 또는 표

## Validation Results
- 7단계 status 표 + details

## Warnings
- 모든 warning을 구조화 (출처 + 원인 + 후속 조치)

## Manual Actions
- 동사로 시작하는 체크리스트
- 위치 + 이유 + 출처

## Run Commands
```bash
cd ports/deepagents/app
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python smoke_test.py
```

## Limitations
- lossiness 명시
- DeepAgents API 변화 risk
- TeamCreate/SendMessage 의미 손실
- MCP adapter 미구현
```

## 변환 품질 점수 (0.0~1.0)

PRD §19.2 가중치:

| 항목 | 가중치 | 점수 산출 |
|---|---:|---|
| agents parsed | 0.20 | 성공 파싱 / 발견 |
| skills parsed/copied | 0.20 | 성공 복사 / 발견 |
| orchestrator detected | 0.15 | found=1.0, synthetic=0.5, none=0 |
| pattern detected | 0.10 | confidence 그대로 |
| Claude operations mapped | 0.10 | mapped/detected, lossiness 가중 |
| tools/MCP handled | 0.10 | stub+secret pass=1.0, 누락 시 비율 |
| validation pass | 0.15 | pass=1.0, pass_with_warnings=0.7, fail=0 |

가중평균 → 최종 점수.

해석 표 (보고서에 포함):

| 점수 | 의미 |
|---:|---|
| 0.90~1.00 | 거의 바로 실행 가능 |
| 0.75~0.89 | 소규모 수동 수정 필요 |
| 0.50~0.74 | 구조 보존, tool/prompt 수정 필요 |
| 0.00~0.49 | 감사용 산출물 |

점수 < 0.5인 경우 보고서 최상단에 경고 박스.

## Manual Actions 작성 규칙

각 액션은:
- 동사로 시작 (`Implement`, `Configure`, `Review`, `Replace`, `Set`, `Add`)
- 위치 명시 (`app/tools.py`의 함수명 + 라인)
- 이유 (왜 필요한지)
- 출처 (IR의 어디에서 도출됐는지, 또는 validator/emitter 발견)

좋은 예:
```
- [ ] Implement `web_search_stub` in `app/tools.py:15`. Reason: agent `analyst.md` references web research but no concrete tool was configured. Source: IR.tools.stubs_required[0].
```

나쁜 예 (모호함):
```
- [ ] Fix the search functionality.
```

## Run Commands 작성 규칙

- 실제 실행 가능한 셸 명령
- 환경 변수 설정 포함 (`export ANTHROPIC_API_KEY=...` 등)
- 작업 디렉토리 명시 (`cd <output_dir>/app`)
- 검증 명령 포함 (smoke_test.py)

## Limitations 작성 규칙

다음을 항상 포함:
- DeepAgents API 변화 가능성 (`create_deep_agent` signature)
- TeamCreate/SendMessage의 lossiness (peer-to-peer messaging은 main-agent-mediated handoff로 변환됨)
- MCP server는 자동 실행되지 않음 — adapter 수동 구현 필요
- Live invocation은 검증되지 않음 — 사용자가 직접 테스트해야 함

## 작업 원칙

- **사실 기반** — IR과 validation에 없는 내용은 쓰지 않는다. 추론은 명시적 표시.
- **누락 없이** — 모든 warning, manual action을 보고서에 통합한다.
- **상충 정보는 출처 병기** — 삭제하지 않음.
- **부분 실패에서도 가능한 보고서 생성** — emitter 실패해도 IR 기반으로 작성.
- **사용자 친화적** — 점수 해석, 다음 명령, 제약을 명확히.

## 모드별 동작

### full 모드
- IR + validation.json + emitter 결과 모두 통합
- 출력: `<output_dir>/conversion_report.md`

### audit_only 모드
- IR만 사용 (validation/emitter 결과 없음)
- Validation Results 섹션 = "Not run (audit_only mode)"
- Generated Files 섹션 = "Not generated (audit_only mode)"
- 출력: `_workspace/conversion_report.md` (output_dir 미생성)

## 안전 규칙

- secret 값을 보고서에 노출하지 않음 (마스킹된 사실만 기록)
- IR/validation에 없는 사실을 만들어내지 않음 (hallucination 금지)
- 사용자 액션을 자동 실행하지 않음 (Run Commands는 안내일 뿐)

## 참고

- 보고서 템플릿: `references/report-template.md`
- 점수 계산 예시: `references/scoring-examples.md`
- Manual action 카탈로그: `references/manual-action-catalog.md`
