# Edge Cases (PRD §20)

## EC-001: agents 없음, skills 있음

- IR 생성, app 생성 가능 (subagents 없음)
- synthetic main agent prompt 생성
- Warning: `skills_only_harness`
- Manual action: subagent를 직접 정의하라는 안내

## EC-002: skills 없음, agents 있음

- subagents 생성
- `app/skills/` 디렉토리 생성하지 않음
- Warning: `agents_without_skills`

## EC-003: orchestrator 없음

- synthetic orchestrator prompt 생성 (agents/skills + 패턴 기반)
- Warning: `orchestrator_not_found`
- 패턴별 기본 prompt 전략 적용

## EC-004: duplicate agent names

- 파일 경로 기반 deterministic id (예: `agents__a`, `agents__b`)
- subagent name은 slug + numeric suffix
- Warning: `duplicate_agent_names` + collision 목록

## EC-005: invalid YAML frontmatter

- raw body fallback
- 파일명 기반 id/name 자동 생성
- Warning: `frontmatter_parse_failed`
- 파일은 IR에서 누락하지 않음

## EC-006: huge SKILL.md (>10MB)

- copy는 수행
- 본문 분석 스킵
- Warning: `skill_md_too_large` + DeepAgents loading risk

## EC-007: secret in config

- 출력에는 마스킹 (`***REDACTED***`)
- Report에는 secret type/위치만 (값 자체는 노출 안 함)
- Manual action: env var로 이전

## EC-008: binary assets

- Copy 그대로 수행
- 본문 분석 skip
- Report에 size/type 기록

## EC-009: existing output directory

- 새 timestamp directory 사용
- Old output 절대 변경하지 않음

## EC-010: Claude-only peer messaging heavy workflow

- main-agent-mediated handoff로 변환
- High lossiness warning
- Manual action: 필요 시 custom shared filesystem protocol 구현 안내
