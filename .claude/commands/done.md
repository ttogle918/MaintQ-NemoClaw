---
description: 세션을 마무리하고 작업 내용을 세션 로그로 기록합니다. 커밋 안 된 변경이 있으면 먼저 확인합니다. 사용법 /done
---

현재 세션을 마무리합니다.

`.claude/skills/done/SKILL.md` 를 따라 진행하세요:

1. `git status` · `git diff --stat HEAD` 로 커밋 안 된 변경을 확인하고, 있으면 커밋 여부를 묻는다.
2. 세션 정보를 수집한다 — 작업 범위, 완료 항목, **의논 내용과 결정 맥락**(왜 이 방향인지,
   검토한 대안), 이번 세션에 추가된 결정(D번호), 트러블슈팅 이슈, 다음 세션 할 일.
3. `docs/sessions/YYYY-MM-DD.md` 에 기록한다.
4. 이번 세션에 **설계 결정이 추가됐으면** `docs/10_DECISIONS.md` 반영 여부를 확인하고,
   D 범위 표기(CLAUDE.md · README.md · docs/README.md · .claude/agents/reviewer.md)가
   최신인지 점검한다 — 이 넷은 자주 어긋난다.
5. 세션 로그를 커밋한다.
