# 세션 로그 — 2026-08-14 (Sprint 9 계획 확정 + Stage 1)

**브랜치**: `sprint-9-repair-record` (⛔ master 미머지·미푸시 — `git reset --hard` 로 되돌릴 수 있다)
**범위**: Sprint 9 현실성 평가 → 계획 확정 → Stage 1 실행 → Q 시리즈 전사 지도 반영

> ⚠ 같은 날짜의 `2026-08-14.md` 는 **이전 세션**(D97 부품 품번)이다. 이 파일은 그 뒤 세션이다.

## 완료

| 항목 | 커밋 | 주요 파일 |
|---|---|---|
| Sprint 9 현실성 평가(tool-builder) + 사람 결정으로 계획 확정 | `ddb62cb` | `docs/sprints/sprint-9.md` §8·§9 |
| Stage 1 — MQ-901·902·920·921 | `834d003` | `docs/10_DECISIONS.md` · `data/extract_triage.py` · `data/raw/manifest.json` · `backend/manifest.py` · `spikes/citation_render.py` · `data/extract_error_codes.py` |
| Q 시리즈 지도 반영 + D 범위 정합화 + status 갱신 | (이 커밋) | `docs/07_BACKLOG.md` P33~P35 · `TODO_직접할일.md` · `docs/status/maintq-status.html` |

## 결정과 맥락

### D98 — `create_repair_record` 는 세 번째 쓰기 도구, `repair_writer()` 전용 커넥션
- **계기**: P25 가 Sprint 7→8 에서 두 번 이월돼 Sprint 9 의 축 A 가 됐다.
- **대안**: `draft_writer()` 재사용 → `mcp_server/db.py:70~74` 주석이 이미 기각한 형태다
  (*"잠겼다고 믿는 지점이 실제로는 안 잠긴다"*). `expenditure_class` 를 파라미터로 받는 안은
  **LLM 이 자본적/수익적지출을 지어내는** 경로라 기각(D31·D81 과 같은 종류의 위험).

### D99 — `actions` 회수분은 후보 파일에 격리, 승인 시에만 정본 병합
- **계기**: `error_codes_gate()` 는 **파일 단위** 게이트라 `_status` 가 초안이 되면 **65 → 0행**이 된다.
  CLAUDE.md 가 이 사고를 **두 번(MQ-708·MQ-713a)** 기록했다.
- **부수 효과**: 검수 단위를 **변경분 37건**으로 좁힐 수 있다.

### D100 — `actions` 출처는 `actions_manual_id`·`actions_page` 로 따로 보존
- **계기**: iG5A 조치문은 **다른 PDF**(트러블슈팅본)에서 오는데 `manual_page` 는 표준본 페이지다.
  그대로 두면 인용이 거짓이 되고 *"근거 페이지 인용률 100%"* 의 판정 소스가 오염된다.
- **계획서 전제 2건을 정정해서 등재했다** (아래 트러블슈팅 참조).

### D101 — 확장 도구 산출 로직을 `data/maint_value.py` 로, MCP 도구는 얇은 위임
- **계기**: `backend/services/decisions.py:520` 이 스스로 *"산식이 두 벌 존재한다"* 라고 적어 뒀다.
- **선례의 적용이지 새 패턴이 아니다** — `check_disposal_blockers` → `data/rules/engine.py`,
  `verify_ownership` → `data/ownership.py` 가 이미 같은 구조다.
- ⚠ **시한부다**: MQ-908 이 `_metrics()` 를 위임 전환하거나 D101 에서 `:520` 인용을 빼지 않으면
  **스프린트 끝에 D101 이 거짓이 된다.**

### 계획 압축 — §7 순서를 기각하고 평가 권고안 채택 (사람 결정)
- **의논한 것**: 착수 지시는 *"과대면 §7 순서대로 MQ-916 → MQ-907 → MQ-915"* 였다.
- **뒤집힌 이유**: tool-builder 가 트러블슈팅 PDF 를 직접 열어 **p.22~28 에 코드별 `원인|조치사항` 표가
  실재**함을 확인했다. **MQ-907(축 B)을 자를 근거가 사라졌다.** 대신 진짜 컷 후보는
  **MQ-903**(4파일 1,378줄 리팩터가 병렬 슬롯 하나)이었다 → **분할**로 처리.
- **결과**: 컷 2(MQ-915·916) · 분할 1(903→903+922) · 신설 2(920·921) · 소유 이관 4.
  **19 → 20태스크.** ⛔ 숫자는 안 줄었다 — 줄어든 것은 작업량(프론트 라우트 2 + 컴포넌트 3 제거)이다.

## 트러블슈팅

### 계획서가 사실이라고 주장한 것 3건이 실측으로 거짓이었다
- **증상**: 계획서 §3 이 *"`ig5a-troubleshooting` 은 `print_page_offset: 0`"* 을 전제로 D100 을 설계.
- **원인**: `data/raw/manifest.json:28` 이 `0` 으로, `page_note` 도 *"물리 = 인쇄"* 로 **잘못 적혀 있었다.**
  PDF 실측은 물리 p.20→인쇄 "19", p.22→"21", p.24→"23", p.28→"27" 이므로 **offset = 1**.
- **왜 지금까지 안 들켰나**: `manifest.manual_entry()` 는 조회 키가 **model** 이고 `role="primary"` 를
  우선하는데 이 PDF 는 `supplement` 이라 **소비 경로가 아예 없었다.** 틀린 채로 조용히 살아 있었다.
- **해결**: MQ-920 이 정정 + `manual_id` 키 조회 3종 신설. `citation_render` **13 → 18건**.
- **커밋**: `834d003`

### `extract_error_codes.py` 가 정본을 무조건 덮어쓴다 (65→0행 사고 경로)
- **증상**: MQ-905 DoD 가 *"재실행 후 `error_codes.json` 해시 불변"* 을 요구하는데 **성립할 수 없었다.**
- **원인**: `:483 OUTPUT.write_text(...)` 가 조건 없이 쓰고 `:474 generated_at = date.today()` 라
  **내용이 같아도 해시가 바뀐다.** 게다가 `:473` 이 `_status` 를 재유도한다.
- **해결**: MQ-921 이 `write_canonical()` 가드 신설 — `generated_at` 제외 정준 직렬화가 같으면
  **쓰지 않는다.** `_status` 승인→초안 되돌림은 **exit 2 로 무조건 중단**. `--candidates-only` 신설.
- **검증**: 2회 연속 실행 후 sha256 `2033f896…4a981d` **불변**, `generated_at` 이 `2026-08-05` 로 남았다
  (오늘 계산값 `2026-08-14` 가 기록되지 않았다 = 가드 작동).
- **커밋**: `834d003`

### MQ-910 이 D32 를 위반한다 (코디네이터 발견 · tool-builder 미검출)
- **증상**: 명세가 `lookup_error_code` 출력에 `print_page` 를 싣게 했다.
- **원인**: **고치려는 그 파일의 docstring**(`mcp_server/tools/lookup_error_code.py:11`)이
  *"환산은 백엔드 렌더 1곳(`backend/manifest.py`)만 담당한다 (D32)"* 라고 적어 뒀고,
  `mcp_server/rag.py:23` 도 같다. 실제로 **`mcp_server` 는 manifest 를 읽지 않는다**(grep 0건).
- **해결**: D100 을 `actions_source: {manual_id, page}` 로 등재하고 **`print_page` 를 뺐다.**
  대안 ④ 로 세워 기각 근거를 문서에 남겼다.

### 계획의 가정을 데이터가 뒤집었다 — iG5A 라벨
- **증상**: MQ-902 DoD 는 *"iG5A 결측 11건이 전부 `SOURCE_MISSING`"* 을 기대했으나 실측은
  **`CELL_SPLIT` 8 / `SOURCE_MISSING` 3**.
- **원인**: 파서가 아니라 **양성 축의 적용 범위**다. iG5A 추출은 ASCII 코드 토큰이 아니라 **한글 명칭**으로
  조인해서, 조치문 추출에 **성공한** 코드가 6·4건 있는 페이지에서도 토큰이 0 이다.
  → ⛔ **iG5A 에서 `code_tokens_found` 를 소스 유무의 증거로 쓰면 안 된다.**
- **대응**: 라벨을 고치지 않고 **실측을 그대로 적었다**(명세의 명시 규칙 — 계획이 데이터를 이기지 않는다).
  대신 독립 축 `probe_supplement()` 를 추가 — **결측 11건 중 명칭 실재 10건, `EST` 1건만 부재.**
  **MQ-905 의 전제를 뒷받침하는 것은 라벨이 아니라 이 실측이다.**

### reviewer 가 잡은 것 — 경고가 산문에만 있으면 증발한다
- **증상**: `anchor_conflict` 경고가 리포트 산문에만 있고 `extract_triage.json` 의 `label` 은
  여전히 `SOURCE_MISSING` 이었다. **MQ-905 가 `label` 로 필터링하면 경고가 통째로 사라진다.**
- **해결**: `PageVerdict` 에 **`anchor_conflict: bool`·`scanned: bool`** 구조화 필드 신설
  (`asdict` 로 JSON 자동 반영). `LABELS` 에 **`UNSCANNED`** 추가 — 스캔 불가를 `SOURCE_MISSING` 으로
  접는 것은 *"재지 못함"* 을 **결론**으로 바꾸는 것이다(D65).
  실측 결과 `p.202`·`p.204` 2건이 `anchor_conflict=True` 로 실렸다.
- **함께**: `citation_render ⑨` 의 양성 축이 `len(by_id) > len(primary)` 라 **supplement 축이 죽어도
  통과**했다(P30 유형) → supplement 를 **이름으로** 세도록 교체.

## 검증 상태

**spikes 28스위트 / 640건**(635 + citation_render 5) · seed 자가검증 **26** · pytest **46** ·
`ruff` 통과 · 프론트 라우트 10(변경 없음).
스위트별 변화: `citation_render 13 → 18`. **그 밖 전부 무증감. 감소 0 · 실패 0 · 재시도 0.**
재시드 후 `error_codes` **65행**. Windows 소켓 고갈 징후 없음(스위트 1개씩 분리 호출).

## Q 시리즈 전사 지도 반영 (신규)

`../A2A_Q/Q시리즈_시나리오맵_S1-S18.html`(기준 2026-08-14 · FinAllQ Sprint 10 완료)을 읽고
백로그에 **P33·P34·P35** 신설:

- **P33 🔴 시나리오 번호 충돌** — MaintQ 의 `S19`(수리 증빙 서명) vs 지도의 `S19`(FinAllQ 기업 온보딩,
  **이미 구현 완료**). 지도는 MaintQ 몫으로 S1~S4·S9·S10·S17·S18 을 **인정하고 있어 다른 번호는 맞다**
  — 어긋난 것은 `S19` 하나다. **번호는 문서에만 있고 DB·도구 계약·enum 에는 없다** → 회귀를 안 깨고
  바꿀 수 있다. ⛔ 세 프로젝트 공유 체계라 **사람 협의 필요** → `TODO_직접할일.md`
- **P34 MaintQ 발신 A2A 경계 시나리오 8종** — S5·S7·S11·S12·S13·S14·S16.
  지도의 핵심 관찰: FinAllQ 는 *"레일(S20 결재 + S21 FDS + 감사)이 이미 다 깔려 있고 빠진 것은
  **바깥으로 난 문**(Agent Card · :9001)"* — **양쪽 다 문만 없다.**
- **P35 나가는 A2A 호출의 차단기** — 지도가 명시한 FinAllQ 교훈(*"AI 장애가 코어로 번지지 않게 차단기.
  A2A 에서 남의 에이전트를 부를 때도 같은 경계가 필요하다"*) + 감사 페이로드 **화이트리스트** 규약.

## 결정 정합성 점검 (D 범위 표기)

`D1~D97`(일부는 `D1~D96` 으로 **더 낡아 있었다**) → **`D1~D101`** 로 6곳 갱신:
`CLAUDE.md` · 루트 `README.md` · `docs/README.md` · `docs/00_MVP_SCOPE.md` ·
`.claude/agents/reviewer.md` · `docs/status/maintq-status.html`.
⚠ `.claude/agents/reviewer.md` 가 낡아 있던 것은 **실제 위험**이었다 — Stage 2 의 reviewer 가
*"D1~D97 을 검토하라"* 는 지시를 받아 **D98~D101 을 그냥 지나칠 수 있었다.**
→ sprint-9 §9-4 의 MQ-918 ⓐ 항목은 **여기서 선행 처리됐다.**

## 다음 세션

1. **`/stage 2`** — MQ-903(`data/maint_value.py` 3종 위임) · MQ-904(`repair_records` DDL + `repair_hash`) ·
   MQ-905(iG5A 11건 후보 추출). ⚠ MQ-905 는 `--candidates-only` 로만 돌린다.
2. **착수 전 결정 2건** — ⓐ MQ-908 의 `decisions._metrics()` 방침(안 정하면 D101 이 거짓이 된다)
   ⓑ `S19` 번호 충돌 방향(P33)
3. 수동 체크리스트(sprint-9 §10 / 이전 턴 출력)는 **아직 미확인** — 특히
   **트러블슈팅 PDF 22쪽 쪽번호가 "21" 인지** 눈으로 확인.

## 사람 승인 대기

- [ ] 🔴 **`S19` 번호 충돌 방향 결정** (신규 — P33)
- [ ] 🔴 `actions` 후보 37건 검수 + **안전 문구 검수** (G1 — MQ-911 이 검수 패키지를 산출한 뒤)
- [ ] `SAFETY_BASELINE`·`QUALIFIED_WORKER_NOTE` 문안 검수 (G4 — 기존)
- [ ] `RESIDUAL_AT_LIFE_END=0.50`·`FLOOR=0.10` 가정 동의 (G5 — 기존, **축 C 를 막지 않는다**)
- [ ] `KR-CITA-ENF-31` 등록 제목 정정 승인 (기존)
- [ ] A2A 연결 승인·파트너 자격증명 실값 (기존, `PARTNER_LINKS_MOCK=True`)
