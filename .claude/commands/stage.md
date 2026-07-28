---
description: 스프린트의 특정 스테이지를 실행합니다. 병렬 구현 → 회귀 → 설계 검토 → 커밋 후 수동 체크리스트를 출력하고 멈춥니다. 사용법 /stage [번호]
---

Stage $ARGUMENTS 를 실행합니다.

`.claude/skills/stage/SKILL.md` 의 실행 흐름을 따라 아래 파이프라인을 수행하세요:

1. `docs/sprints/` 의 최신 파일로 현재 스프린트 N을 확인하고, `sprint-{N}.md` 에서
   Stage $ARGUMENTS 태스크 목록을 읽는다.
2. 이전 스테이지 완료 여부 확인 (미완료면 경고 후 사용자 확인).
3. 태스크 수만큼 **tool-builder** 를 병렬 실행한다.
   프론트엔드 태스크는 `frontend/` 범위임을 명시해 전달한다.
4. **eval-runner** 로 회귀를 검증한다. MaintQ의 회귀 스위트는 고정이다:
   ```
   uv run python data/seed.py --with-error-codes --today 2026-07-23
   uv run python spikes/sp2_mcp_roundtrip.py
   uv run python spikes/write_tool_contract.py
   uv run python spikes/api_contract.py
   uv run python spikes/sp3_sse_events.py
   (frontend 변경 시) npx tsc --noEmit && npx next build
   ```
   실패 시 해당 태스크 tool-builder만 재실행.
5. **reviewer** 로 설계 준수를 점검한다 (D1~D39 + `docs/04_MCP_TOOLS.md` 계약).
   FAIL이면 수정 후 재검증 — **커밋 불가**.
6. reviewer PASS 즉시 커밋한다 (접두어 `[M1]`~`[M4]`, 한국어 OK).
7. `docs/sprints/sprint-{N}.md` 체크리스트를 갱신한다.
8. 수동 테스트 체크리스트를 출력하고 대기한다.

**절대 규칙 확인** — 커밋 전 reviewer가 반드시 본다:
MCP 도구는 `po_drafts` draft INSERT만(D10) · 안전 문구는 매뉴얼 근거 필수 ·
미지 코드에 유사 코드 추측 금지 · `data/raw/` 읽기 전용.
