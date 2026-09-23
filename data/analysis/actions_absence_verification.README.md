# `actions_absence_verification.md` 는 공개 레포에 없다 (D144)

원래 이 자리에 있던 분석 문서는 **정본 고장 표의 원인·조치 문장 40건(162건 중)** 을 본문에
인용한다 — 매뉴얼 표현의 재배포에 해당해 git 추적에서 제외했다. 파일은 로컬에 그대로 있다.

- 이 문서가 다룬 주제: "iG5A·S100 고장 표에 조치(actions)가 **원문에 없는** 행이 몇이고,
  그걸 어떻게 확인했나" — 결론은 `docs/10_DECISIONS.md` D99·D106 과
  `docs/sprints/sprint-13.md` 에 남아 있다
- 기계 판정 리포트는 재생성할 수 있다: `uv run python data/verify_actions_absence.py`
  → `data/extracted/actions_absence_verification.json` (구조 견본은
  `data/extracted/samples/actions_absence_verification.sample.json`)
