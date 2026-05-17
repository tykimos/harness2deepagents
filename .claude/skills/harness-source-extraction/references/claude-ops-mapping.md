# Claude-only Operations → DeepAgents Mapping

PRD §16.2 기반 매핑 표.

| Claude operation | DeepAgents mapping | Lossiness |
|---|---|---:|
| `TeamCreate` | `SUBAGENTS` registry 정의 | Low |
| `TaskCreate` | main agent의 planning/delegation 지시 | Medium |
| `SendMessage` | main-agent-mediated handoff | Medium |
| Peer-to-peer team chat | 직접 보존 불가 | High |
| `TeamDelete` | phase boundary / no-op | Low |
| `Agent(..., run_in_background=true)` | parallel delegation 지시 또는 TODO | Medium |
| Phase dependency | prompt-level workflow policy | Medium |
| `TaskUpdate` | main agent의 planning step | Medium |
| `TaskGet` | main agent의 status query (filesystem 기반) | Medium |
| `SendNotification` | log 또는 TODO | High |

## 검출 방법

다음 문자열을 agent body, skill body, settings에서 검색:

```
TeamCreate
TaskCreate
TaskUpdate
TaskGet
TeamDelete
SendMessage
Agent(
run_in_background
TeamMember
TeamLeader
```

각 발견 시 IR `claude_only_operations[]`에 추가:

```yaml
claude_only_operations:
  - operation: "SendMessage"
    count: 3
    locations:
      - file: ".claude/skills/research-orchestrator/SKILL.md"
        line_hint: "Phase 3"
    mapping: "main-agent-mediated handoff"
    lossiness: "medium"
    notes: "Direct peer-to-peer messaging is approximated."
```

## High lossiness 경고

다음 패턴은 항상 high lossiness:
- 동시에 여러 팀원이 양방향 SendMessage (peer-to-peer chat)
- 실시간 작업 재할당 (supervisor 동적 분배)
- 외부 이벤트 트리거 (TaskUpdate cron 등)

이 경우 conversion_report.md의 Limitations에 명시 + manual action 추가.
