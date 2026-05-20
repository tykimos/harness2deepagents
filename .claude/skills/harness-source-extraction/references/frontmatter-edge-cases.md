# Frontmatter Edge Cases

## 정상 frontmatter

```markdown
---
name: analyst
description: "Analyzes requirements"
model: opus
---

# Analyst
...
```

## 변형 1: frontmatter 없음

처리:
- 파일명 기반 id/name 생성 (`analyst.md` → id: `analyst`, name: `analyst`)
- description = body 첫 heading 또는 첫 paragraph 발췌
- Warning: `frontmatter_missing`

## 변형 2: 잘못된 YAML

```markdown
---
name: analyst
description: This: has: colons: in: it
---
```

처리:
- raw body fallback
- description 필드는 body에서 재추출 시도
- Warning: `frontmatter_parse_failed`, `details: <YAML parse error>`

## 변형 3: 알려지지 않은 키

```markdown
---
name: analyst
custom_field: foo
team_role: lead
---
```

처리:
- known fields만 추출
- 나머지는 `extra_frontmatter` 필드에 보관 (IR에 반영)
- Warning 없음

## 변형 4: 한국어 description

```markdown
---
name: analyst
description: "요구사항을 분석합니다"
---
```

처리:
- 그대로 보존
- length 검사는 byte 단위가 아닌 character 단위

## 변형 5: 다중 라인 description

```yaml
description: |
  This agent analyzes
  requirements deeply.
```

처리:
- newline 보존
- description_length는 결합 후 길이

## 변형 6: tools 필드 형식 변형

```yaml
tools: ["WebSearch", "Read"]      # array
tools: "WebSearch, Read"           # comma-separated string
tools:                             # YAML list
  - WebSearch
  - Read
```

처리: 모두 array로 정규화. 문자열이면 `,` split.

## 변형 7: skills 필드 변형

```yaml
skills:
  - research
skills: research,analysis
skills: ["research"]
```

처리: 모두 array로 정규화.

## 변형 8: 중복 키

```yaml
name: analyst
name: researcher  # duplicate
```

처리: 마지막 값 사용 (YAML 표준). Warning: `duplicate_frontmatter_key`.
