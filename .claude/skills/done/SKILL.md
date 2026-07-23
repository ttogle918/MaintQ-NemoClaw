---
name: done
description: 세션을 마무리하고 작업 내용·결정 맥락을 세션 로그로 기록한다. 커밋 안 된 변경이 있으면 먼저 확인한다. 사용자가 /done을 호출할 때 사용.
---

# /done — 세션 마무리

## 목적

세션에서 한 일을 `docs/sessions/YYYY-MM-DD.md` 에 기록한다.
`/stage` 가 스테이지 단위 커밋을 처리하므로 `/done` 의 주 역할은 **로그와 결정 정합성 점검**이다.

---

## Step 1: 커밋 안 된 변경 확인

```bash
git status
git diff --stat HEAD
```

있으면 커밋 여부를 묻는다. 커밋한다면 `[M1]`~`[M4]` 접두어를 쓴다.

---

## Step 2: 세션 정보 수집

```bash
git log --oneline -15
git branch --show-current
```

수집 항목:
- 날짜 · 브랜치 · 작업 범위 한 줄
- 완료 작업 (항목 + 주요 파일)
- **의논 내용과 결정 맥락** — 왜 이 방향인지, 검토하고 버린 대안. 이게 가장 중요하다.
  결과만 남기면 다음 세션에 같은 논의를 반복한다
- **이번 세션에 추가된 결정 (D번호)** 과 그 계기
- 트러블슈팅 — 증상 / 원인 / 해결 / 관련 커밋. 없으면 "없음"
- 다음 세션에 할 것
- 사람 승인 대기 항목의 변화 (`TODO_직접할일.md`)

---

## Step 3: 결정 정합성 점검 ← MaintQ 특유

이번 세션에 결정(D번호)이 추가됐으면 **D 범위 표기가 네 곳에서 어긋나기 쉽다.** 확인한다:

```bash
grep -rn "D1~D" CLAUDE.md README.md docs/README.md .claude/agents/reviewer.md
```

`docs/10_DECISIONS.md` 의 마지막 D번호와 일치해야 한다.

추가로:
- 새 결정이 `docs/04_MCP_TOOLS.md`·`05_DB_SCHEMA.md`·`06_REPO_API.md` 계약에 반영됐는가
- 계약이 바뀌었으면 `spikes/` 회귀가 그걸 검증하는가

---

## Step 4: 세션 로그 작성

`docs/sessions/YYYY-MM-DD.md`:

```markdown
# 세션 로그 — YYYY-MM-DD

**브랜치**: {branch} · **범위**: {한 줄}

## 완료
- {항목} — `{주요 파일}`

## 결정과 맥락
### D{N} — {제목}
- **계기**: {무엇을 하다 발견했는지}
- **대안**: {검토하고 버린 것과 이유}

## 트러블슈팅
### {증상}
- **원인**: / **해결**: / **커밋**: `{hash}`

## 검증 상태
- 회귀: seed {n} · SP2 {n} · write_tool {n} · api {n} · SP3 {n}

## 다음 세션
1. ...

## 사람 승인 대기
- [ ] {TODO_직접할일.md 항목}
```

---

## Step 5: 완료 선언

```
✅ 세션 마무리
세션 로그: docs/sessions/YYYY-MM-DD.md
다음: {다음 작업}
```

세션 로그를 커밋한다 (`[M{n}] docs: 세션 로그 YYYY-MM-DD`).
