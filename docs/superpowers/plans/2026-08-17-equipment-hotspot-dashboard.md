# 설비 하이라이트 대시보드 (C+D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 독립된 신규 화면 `/technician/equipment-status`(목록→드릴다운)에서 9개 설비 자산을 매뉴얼 도면 위에 냉각팬·키패드·제어보드 3개 하이라이트로 보여준다. 색은 우선순위 규칙(🔴 이상탐지 > 🔵 최근수리 > 🟠 곧점검)으로 기존 진단·수리 이력 + 신규 생애주기 mock 데이터에서 유도한다. 하이라이트 클릭 시 매뉴얼 근접 이미지(냉각팬) 또는 CSS 확대(키패드·제어보드)로 드릴다운하고, 기존 진단 텍스트(`causes`/`actions`)·수리 서명 정보를 재사용해 보여준다.

**Architecture:** 색 판정 로직(여러 테이블 조인)은 `data/hotspot_status.py`(공유 데이터 계층, D73)에 두고 새 REST 엔드포인트 `GET /api/assets/{asset_id}/hotspot-status`가 위임한다(`data/maint_value.py` 선례와 동일 패턴). 하이라이트 좌표·이미지 경로는 DB가 아니라 프론트 정적 상수(`frontend/lib/hotspots.ts`)로 관리한다(실물 도면과 1:1 좌표라 DB화할 이유가 없음, 스펙 §4-3). `part_lifecycle_mock`은 읽기 전용 신규 시드 테이블 — 쓰기 도구 신설 없음(D10과 무관).

**Tech Stack:** Python 3.11 / FastAPI / SQLite (백엔드) · Next.js 14 (App Router) / React / TypeScript, 인라인 스타일(`sx()` 헬퍼) (프론트) · `pdfplumber`(이미지 자산 준비, 1회성)

## Global Constraints

- MCP 도구 신설 없음 — 이 기능은 읽기 전용 REST 대시보드다. `mcp_server/`는 건드리지 않는다
- `data/` 모듈은 `mcp_server`를 import하지 않는다 (D15)
- 색 판정 산식은 `data/hotspot_status.py` **한 곳**에만 있다 — 프론트는 응답을 옮겨 적기만 한다
- "이상탐지"는 기존 `error_history`+`error_codes.related_parts`+`repair_records`를 재해석할 뿐, 새 탐지 로직(센서·임계치)을 만들지 않는다 (spec §4-5)
- 하이라이트 대상은 매뉴얼에 실제 라벨된 부품만(냉각팬·키패드) + 근사 배치 1개(제어보드, `approximate:true` 고지 필수) — 그 외 부품은 하이라이트하지 않는다 (spec §1)
- `manual_page`(물리)→`print_page`(인쇄) 오프셋 변환은 `backend.manifest.to_print_page()` 한 함수에만 위임한다 (D26·D32·D57) — 재구현 금지
- `part_lifecycle_mock`은 화면에 mock임을 고지한다(D65 태도)
- 프론트 상태·색 매핑은 `frontend/lib/mappers.tsx` 한 곳만 거친다 (D87) — 신규 컴포넌트는 `components/asset/*.tsx`에 둬 `spikes/ui_honesty_contract.py` L2 글롭에 자동 편입시킨다
- 크롭 이미지는 `frontend/public/manuals/`에 커밋한다. 화면에 출처 고지("LS ELECTRIC ○○ 사용설명서 p.○")를 항상 표시한다 — 이미 사용자 승인됨(spec §4-2). 원본 PDF는 `data/raw/`(git 제외)에만 둔다
- 커밋 메시지는 한국어, `uv run ruff check` / `npx tsc --noEmit` / `npm run build`를 실제로 실행해 확인한 뒤에만 "통과"라고 쓴다

---

## Task 1: 매뉴얼 도면 이미지 자산 준비

**Files:**
- Create: `frontend/public/manuals/ig5a_hotspot_base.png`
- Create: `frontend/public/manuals/ig5a_fan_detail.png`
- Create: `frontend/public/manuals/s100_hotspot_base.png`
- Create: `frontend/lib/hotspots.ts`

**Interfaces:**
- Produces: `Hotspot` 타입, `MODEL_HOTSPOTS: Record<string, Hotspot[]>`, `MODEL_BASE_IMAGE: Record<string, string>`, `MODEL_CITATION: Record<string, string>` — 이후 Task 7(`EquipmentHotspotDiagram`)이 이 상수를 쓴다.

- [ ] **Step 1: 매뉴얼 페이지를 크롭해 정적 자산으로 저장**

원본은 `data/raw/iG5A_User_Manual_Standard_KR_210303.pdf`(물리 p.22 그림 1-2 · p.23 그림 1-4)와 `data/raw/S100_Manual_Korean_V4.2.pdf`(물리 p.19 1.2.1 분해도) — 둘 다 `data/raw/manifest.json`에 등록된 매뉴얼이다(id: `ig5a-manual` offset 0, `s100-manual` offset 16). **원본 PDF는 건드리지 않는다** — 렌더 후 크롭한 PNG만 새로 만든다.

```bash
mkdir -p frontend/public/manuals
uv run python -c "
import pdfplumber

with pdfplumber.open('data/raw/iG5A_User_Manual_Standard_KR_210303.pdf') as pdf:
    p22 = pdf.pages[21].to_image(resolution=200).original
    p22.crop((215, 1215, 1405, 1933)).save('frontend/public/manuals/ig5a_hotspot_base.png')
    p23 = pdf.pages[22].to_image(resolution=200).original
    p23.crop((215, 1215, 1405, 1923)).save('frontend/public/manuals/ig5a_fan_detail.png')

with pdfplumber.open('data/raw/S100_Manual_Korean_V4.2.pdf') as pdf:
    p19 = pdf.pages[18].to_image(resolution=200).original
    p19.crop((71, 546, 1218, 1863)).save('frontend/public/manuals/s100_hotspot_base.png')

print('done')
"
```

Expected: `done` 출력, 3개 PNG 파일 생성. 파일을 열어 육안으로 확인 — `ig5a_hotspot_base.png`는 "전면 덮개 제거 시"(그림 1-2, 냉각팬·키패드·단자대 라벨 포함) 그림 전체가 잘리지 않고 담겨야 하고, `ig5a_fan_detail.png`는 "인버터 냉각 팬을 교체할 때"(그림 1-4) 그림이, `s100_hotspot_base.png`는 "1.2.1 0.4~22kW 제품군" 분해도(냉각팬·키패드·제어단자대 라벨 포함) 전체가 담겨야 한다. 잘렸으면 크롭 박스를 조정해 재실행한다.

- [ ] **Step 2: `frontend/lib/hotspots.ts` 작성**

좌표는 위 크롭 이미지를 육안 검수해 정한 값이다(그림 내 상대 위치 — 이미지 폭/높이에 대한 %, 좌상단 원점). 픽셀이 아니라 %인 이유: 화면 렌더 크기가 달라져도(반응형) 좌표가 깨지지 않는다.

```typescript
/**
 * 설비 하이라이트 대시보드 — 매뉴얼 도면 좌표 (Sprint 10 브레인스토밍 C, spec §4-3).
 *
 * DB 가 아니라 정적 상수다 — 실물 도면과 1:1 매칭이라 좌표가 바뀔 이유가 없다.
 * 좌표는 크롭된 이미지(`frontend/public/manuals/*.png`) 기준 %(좌상단 원점)다.
 *
 * ⚠ 라이선스: LS ELECTRIC 매뉴얼 도면 원본. 비상업적 학습·포트폴리오 목적으로만 사용 —
 *   화면에 `citation` 을 항상 표시할 것(spec §4-2, 사용자 승인 완료).
 */

export interface Hotspot {
  partNo: string; // parts.part_no 와 매칭 — 있으면 실 데이터 조회 가능
  label: string;
  x: number; // 기본 도면 이미지 폭에 대한 % (0-100)
  y: number; // 기본 도면 이미지 높이에 대한 % (0-100)
  /** true 면 도면에 정확한 라벨이 없는 근사 배치 — 화면에 고지 필요 */
  approximate?: boolean;
  /** 있으면 클릭 시 이 실제 근접 이미지로 전환. 없으면 기본 도면을 이 좌표 중심으로 CSS 확대한다 */
  detailImage?: string;
}

export const IG5A_HOTSPOTS: Hotspot[] = [
  {
    partNo: "FAN-IG5-01",
    label: "냉각팬",
    x: 45,
    y: 72,
    detailImage: "/manuals/ig5a_fan_detail.png",
  },
  { partNo: "KPD-IG5-01", label: "키패드", x: 47, y: 25 },
  { partNo: "PCB-IG5-CTRL", label: "제어보드", x: 50, y: 48, approximate: true },
];

export const S100_HOTSPOTS: Hotspot[] = [
  { partNo: "FAN-S100-01", label: "냉각팬", x: 63, y: 28 },
  { partNo: "KPD-S100-01", label: "키패드", x: 51, y: 48 },
  { partNo: "PCB-S100-CTRL", label: "제어보드", x: 53, y: 54, approximate: true },
];

export const MODEL_HOTSPOTS: Record<string, Hotspot[]> = {
  iG5A: IG5A_HOTSPOTS,
  S100: S100_HOTSPOTS,
};

export const MODEL_BASE_IMAGE: Record<string, string> = {
  iG5A: "/manuals/ig5a_hotspot_base.png",
  S100: "/manuals/s100_hotspot_base.png",
};

/** 화면에 항상 표시할 출처 고지 (spec §4-2 라이선스 조항). */
export const MODEL_CITATION: Record<string, string> = {
  iG5A: "LS ELECTRIC iG5A 사용설명서 물리 p.22 (그림 1-2, 전면 덮개 제거 시)",
  S100: "LS ELECTRIC S100 사용설명서 인쇄 p.3 · PDF p.19 (1.2.1 분해도)",
};

export const FAN_DETAIL_CITATION =
  "LS ELECTRIC iG5A 사용설명서 물리 p.23 (그림 1-4, 인버터 냉각 팬을 교체할 때)";
```

- [ ] **Step 3: 타입 체크**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 에러 없음.

- [ ] **Step 4: Commit**

```bash
git add frontend/public/manuals frontend/lib/hotspots.ts
git commit -m "$(cat <<'EOF'
[M3] 설비 하이라이트 도면 이미지 + 좌표 상수 (spec §4-2·§4-3)

iG5A/S100 매뉴얼 물리 p.22·23·19 크롭. 출처 고지는 화면에서 항상 표시(라이선스
조항 준수, 사용자 승인 완료). 좌표는 정적 상수 — DB 화하지 않는다.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `part_lifecycle_mock` 시드 테이블

**Files:**
- Modify: `data/seed.py`

**Interfaces:**
- Produces: `part_lifecycle_mock(equipment_id, part_no, next_maintenance_due)` 테이블 — 이후 Task 3(`data/hotspot_status.py`)이 이 테이블을 읽는다.

- [ ] **Step 1: `SCHEMA`에 `§19 part_lifecycle_mock` 추가**

`data/seed.py`의 `SCHEMA` триple-quoted 문자열 끝(§18 `partner_links` 정의 뒤, 현재 파일 기준 `CREATE TABLE partner_links (...)` 닫는 `);` 바로 다음, 문자열을 닫는 `"""` 바로 앞)에 추가:

```sql
-- §19 part_lifecycle_mock — 생애주기 경고(D) 목업 (Sprint 10 브레인스토밍).
-- ⛔ 실 텔레메트리·정비 이력에서 유도하지 않는다 — 사용자가 명시적으로 "새 가짜 필드,
--    부품별 다음 점검일 직접 부여"를 선택했다. 화면에 mock 고지 필수(D65).
CREATE TABLE part_lifecycle_mock (
  equipment_id TEXT NOT NULL REFERENCES equipment,
  part_no      TEXT NOT NULL REFERENCES parts,
  next_maintenance_due DATE NOT NULL,
  PRIMARY KEY (equipment_id, part_no)
);
```

- [ ] **Step 2: 시드 데이터 + 함수 추가**

`data/seed.py`에서 `PART_CLASS` 딕셔너리 정의가 끝나는 지점 근처(§ "parts.part_class 40종" 섹션 뒤)에 다음을 추가:

```python
# ── part_lifecycle_mock — 생애주기 경고(D) 목업 데이터 ───────────────────────
# 하이라이트 대상 부품(냉각팬·키패드·제어보드, frontend/lib/hotspots.ts 와 part_no 짝) ×
# asset_id 가 있는 9개 설비 = 27행. offset_days 는 오늘(시드 실행일) 기준
# next_maintenance_due 오프셋 — 이미 지난 것(음수)·임박·여유 있는 것을 섞어 데모 다양성을 준다.
PART_LIFECYCLE_MOCK: list[tuple[str, str, int]] = [
    ("INV-L1-02", "FAN-IG5-01", -12),
    ("INV-L1-02", "KPD-IG5-01", 45),
    ("INV-L1-02", "PCB-IG5-CTRL", 210),
    ("INV-L3-01", "FAN-IG5-01", 18),
    ("INV-L3-01", "KPD-IG5-01", 95),
    ("INV-L3-01", "PCB-IG5-CTRL", -5),
    ("INV-L3-02", "FAN-IG5-01", 300),
    ("INV-L3-02", "KPD-IG5-01", -30),
    ("INV-L3-02", "PCB-IG5-CTRL", 60),
    ("INV-L4-03", "FAN-IG5-01", 8),
    ("INV-L4-03", "KPD-IG5-01", 150),
    ("INV-L4-03", "PCB-IG5-CTRL", 40),
    ("INV-L2-01", "FAN-S100-01", 55),
    ("INV-L2-01", "KPD-S100-01", -18),
    ("INV-L2-01", "PCB-S100-CTRL", 120),
    ("INV-L2-02", "FAN-S100-01", 25),
    ("INV-L2-02", "KPD-S100-01", 400),
    ("INV-L2-02", "PCB-S100-CTRL", -2),
    ("INV-L3-03", "FAN-S100-01", 175),
    ("INV-L3-03", "KPD-S100-01", 33),
    ("INV-L3-03", "PCB-S100-CTRL", 9),
    ("INV-L4-01", "FAN-S100-01", -22),
    ("INV-L4-01", "KPD-S100-01", 80),
    ("INV-L4-01", "PCB-S100-CTRL", 250),
    ("INV-L4-02", "FAN-S100-01", 47),
    ("INV-L4-02", "KPD-S100-01", 15),
    ("INV-L4-02", "PCB-S100-CTRL", -40),
]


def seed_part_lifecycle_mock(con: sqlite3.Connection, today: date) -> int:
    """§19 part_lifecycle_mock 적재. `today`(--today 인자)기준 상대 오프셋 — 데모 날짜가

    밀려도 임박/여유 분포가 유지된다.
    """
    rows = [
        (equipment_id, part_no, (today + timedelta(days=offset)).isoformat())
        for equipment_id, part_no, offset in PART_LIFECYCLE_MOCK
    ]
    con.executemany("INSERT INTO part_lifecycle_mock VALUES (?,?,?)", rows)
    return len(rows)
```

- [ ] **Step 3: `main()`에서 호출**

`data/seed.py`의 `main()`에서 `seed_masters(con)` 바로 다음 줄(현재 `seed_inventory(con, rng)` 앞)에 추가:

```python
        seed_masters(con)
        n_lifecycle = seed_part_lifecycle_mock(con, args.today)
        seed_inventory(con, rng)
```

그리고 `if with_codes:` 블록 근처(콘솔 출력부, `print(f"[잔가곡선] ...")` 바로 다음 줄)에 추가:

```python
        print(f"[생애주기 목업] part_lifecycle_mock {n_lifecycle}행 (D — mock, 실 텔레메트리 아님)")
```

- [ ] **Step 4: 자가 검증(`verify()`)에 검사 추가**

`data/seed.py`의 `verify()` 함수 안, 기존 마지막 검사(㉚ actions 병합 검증) 바로 다음에 추가:

```python
    # ㉛ part_lifecycle_mock — 27행 · FK 정합(각 equipment 의 model 과 part_no 모델이 일치) (Sprint 10)
    rows_pl = con.execute(
        "SELECT p.equipment_id, e.model, p.part_no FROM part_lifecycle_mock p"
        " JOIN equipment e ON e.equipment_id = p.equipment_id"
    ).fetchall()
    mismatched = [
        (r["equipment_id"], r["model"], r["part_no"])
        for r in rows_pl
        if (r["model"] == "iG5A" and "IG5" not in r["part_no"])
        or (r["model"] == "S100" and "S100" not in r["part_no"])
    ]
    check(
        "㉛ part_lifecycle_mock 27행 · 모델-부품 정합 (Sprint 10 브레인스토밍 D)",
        len(rows_pl) == 27 and not mismatched,
        f"행수={len(rows_pl)} (기대 27) · 모델 불일치 {len(mismatched)}건 {mismatched[:3]}",
    )
```

`verify()`의 독스트링 마지막 줄(`... (MQ-919) 1건(㉚)이 뒤에 붙는다.`)을 다음으로 교체:

```python
    (MQ-919) 1건(㉚) · part_lifecycle_mock 1건(㉛, Sprint 10 브레인스토밍 D)이 뒤에 붙는다.
    """
```

같은 방식으로 파일 상단 docstring(5~9행, `검증 : ...`)의 `+ actions 병합 검증(㉚, MQ-919)` 뒤에 ` + part_lifecycle_mock(㉛)`을 추가한다.

- [ ] **Step 5: 재시드 + 회귀**

```bash
uv run python data/seed.py --with-error-codes
```

Expected: 출력에 `[생애주기 목업] part_lifecycle_mock 27행 ...`이 보이고, 검증 표에 `㉛ part_lifecycle_mock 27행 · 모델-부품 정합`이 `PASS`로 뜬다. 마지막 줄 `전부 통과 (N건)`의 N이 기존보다 1 늘어야 한다(㉛ 추가분).

- [ ] **Step 6: Commit**

```bash
git add data/seed.py
git commit -m "$(cat <<'EOF'
[M1] part_lifecycle_mock 시드 신설 — 생애주기 경고(D) mock 데이터 (spec §3)

하이라이트 대상 부품 × asset_id 있는 9설비 = 27행. 실 텔레메트리 아님(D65),
화면 고지는 Task 9 에서 붙인다. 자가검증 ㉛ 추가.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `data/hotspot_status.py` — 색 판정 공유 로직

**Files:**
- Create: `data/hotspot_status.py`

**Interfaces:**
- Produces: `hotspot_status(con: sqlite3.Connection, *, asset_id: str, today: date) -> dict` · `MODEL_HOTSPOT_PARTS: dict[str, list[str]]` — 이후 Task 4(백엔드 서비스)가 이 함수를 호출한다.

- [ ] **Step 1: `data/hotspot_status.py` 작성**

```python
# -*- coding: utf-8 -*-
"""설비 하이라이트 색 판정 — 공유 데이터 계층 (D101·D73, spec §4-5·§4-6).

색 우선순위(부품 단위): 🔴 이상탐지 > 🔵 최근 수리 > 🟠 곧 점검 > 없음.
"이상탐지"는 새 탐지 로직(센서·임계치)이 아니라 기존 `error_history`+`error_codes.related_parts`+
`repair_records` 를 재해석하는 것뿐이다 — 이 프로젝트에 실시간 텔레메트리가 없다(spec §4-5).

커넥션은 호출자가 `mode=ro`로 열어 넘긴다 — `mcp_server`를 import하지 않는다(D15).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

# 최근 수리로 볼 기간(일) · 곧 점검으로 볼 기간(일). spec §4-5 제안값.
N_RECENT_REPAIR_DAYS = 90
M_UPCOMING_DAYS = 60

# frontend/lib/hotspots.ts 의 partNo 와 짝이어야 한다 — 한쪽만 바뀌면 조용히 어긋난다.
MODEL_HOTSPOT_PARTS: dict[str, list[str]] = {
    "iG5A": ["FAN-IG5-01", "KPD-IG5-01", "PCB-IG5-CTRL"],
    "S100": ["FAN-S100-01", "KPD-S100-01", "PCB-S100-CTRL"],
}


def hotspot_status(con: sqlite3.Connection, *, asset_id: str, today: date) -> dict:
    eq = con.execute(
        "SELECT equipment_id, model FROM equipment WHERE asset_id = ? ORDER BY equipment_id",
        (asset_id,),
    ).fetchone()
    if eq is None:
        return {"status": "not_found", "reason": "no_equipment_for_asset"}

    equipment_id, model = eq["equipment_id"], eq["model"]
    part_nos = MODEL_HOTSPOT_PARTS.get(model)
    if part_nos is None:
        return {"status": "error", "reason": "unknown_model", "message": f"model={model!r}"}

    diagnoses = _latest_diagnosis_by_part(con, equipment_id, model, part_nos)
    repairs = _latest_signed_repair_by_part(con, equipment_id, part_nos)
    due = _lifecycle_due_by_part(con, equipment_id, part_nos)

    parts_status = []
    for part_no in part_nos:
        diag = diagnoses.get(part_no)
        repair = repairs.get(part_no)
        diag_at = diag["occurred_at"] if diag else None
        repair_at = repair["signed_at"] if repair else None

        if diag_at and (repair_at is None or diag_at > repair_at):
            color, basis = "red", diag
        elif repair_at and _within_days(repair_at, today, N_RECENT_REPAIR_DAYS):
            color, basis = "blue", repair
        elif part_no in due and (due[part_no] - today).days <= M_UPCOMING_DAYS:
            color, basis = "orange", {"next_maintenance_due": due[part_no].isoformat()}
        else:
            color, basis = None, {}

        parts_status.append({"part_no": part_no, "color": color, "basis": basis})

    return {"status": "ok", "equipment_id": equipment_id, "model": model, "parts": parts_status}


def _latest_diagnosis_by_part(
    con: sqlite3.Connection, equipment_id: str, model: str, part_nos: list[str]
) -> dict[str, dict]:
    """부품별 마지막 진단 이벤트. `occurred_at` 오름차순으로 훑어 마지막 값이 남게 한다."""
    rows = con.execute(
        "SELECT h.code, h.occurred_at, e.related_parts, e.causes, e.actions, e.manual_page"
        " FROM error_history h JOIN error_codes e ON e.model = ? AND e.code = h.code"
        " WHERE h.equipment_id = ? ORDER BY h.occurred_at",
        (model, equipment_id),
    ).fetchall()
    latest: dict[str, dict] = {}
    for row in rows:
        related = json.loads(row["related_parts"] or "[]")
        for part_no in part_nos:
            if part_no in related:
                latest[part_no] = {
                    "code": row["code"],
                    "occurred_at": row["occurred_at"],
                    "causes": json.loads(row["causes"]),
                    "actions": json.loads(row["actions"]),
                    "manual_page": row["manual_page"],
                }
    return latest


def _latest_signed_repair_by_part(
    con: sqlite3.Connection, equipment_id: str, part_nos: list[str]
) -> dict[str, dict]:
    """부품별 마지막 **서명된** 수리 기록. draft/pending 은 세지 않는다(spec §4-5 — "서명된")."""
    rows = con.execute(
        "SELECT r.repair_id, r.parts, r.signed_at, u.display_name AS performed_by_name"
        " FROM repair_records r LEFT JOIN users u ON u.user_id = r.performed_by"
        " WHERE r.equipment_id = ? AND r.state = 'signed' AND r.signed_at IS NOT NULL"
        " ORDER BY r.signed_at",
        (equipment_id,),
    ).fetchall()
    latest: dict[str, dict] = {}
    for row in rows:
        parts_in_record = json.loads(row["parts"] or "[]")
        for part_no in part_nos:
            if part_no in parts_in_record:
                latest[part_no] = {
                    "repair_id": row["repair_id"],
                    "signed_at": row["signed_at"],
                    "performed_by_name": row["performed_by_name"],
                }
    return latest


def _lifecycle_due_by_part(
    con: sqlite3.Connection, equipment_id: str, part_nos: list[str]
) -> dict[str, date]:
    rows = con.execute(
        "SELECT part_no, next_maintenance_due FROM part_lifecycle_mock WHERE equipment_id = ?",
        (equipment_id,),
    ).fetchall()
    return {
        row["part_no"]: date.fromisoformat(row["next_maintenance_due"])
        for row in rows
        if row["part_no"] in part_nos
    }


def _within_days(iso_datetime: str, today: date, days: int) -> bool:
    d = date.fromisoformat(iso_datetime[:10])
    return (today - d).days <= days
```

- [ ] **Step 2: 수동 확인**

```bash
uv run python -c "
import sqlite3
from datetime import date
from data.hotspot_status import hotspot_status

con = sqlite3.connect('data/maintq.db')
con.row_factory = sqlite3.Row
r = hotspot_status(con, asset_id='AST-L3-CONV', today=date.today())
print(r)
assert r['status'] == 'ok'
assert r['model'] == 'iG5A'
assert {p['part_no'] for p in r['parts']} == {'FAN-IG5-01', 'KPD-IG5-01', 'PCB-IG5-CTRL'}
r2 = hotspot_status(con, asset_id='NOPE', today=date.today())
assert r2 == {'status': 'not_found', 'reason': 'no_equipment_for_asset'}
print('OK')
"
```

Expected: `OK` 출력. `AST-L3-CONV`(`INV-L3-01`)는 Task 2 시드에서 `PCB-IG5-CTRL` 오프셋 -5일(이미 지남 → M=60일 이내이므로 `orange` 후보) — 다만 `INV-L3-01`에 그 부품을 겨냥한 진단·수리 이력이 없으면 `orange`가, 있으면 `red`/`blue`가 우선한다. 출력된 `color`가 이 우선순위 규칙과 일치하는지 눈으로 확인한다.

- [ ] **Step 3: 정적 검사**

```bash
uv run ruff check data/hotspot_status.py
```

Expected: 에러 없음.

- [ ] **Step 4: Commit**

```bash
git add data/hotspot_status.py
git commit -m "$(cat <<'EOF'
[M2] data/hotspot_status.py 신설 — 하이라이트 색 우선순위 판정 (spec §4-5, D101·D73)

새 탐지 로직 없음 — error_history+error_codes.related_parts+repair_records 재해석뿐.
red/blue basis 에 기존 진단 causes·actions·수리 서명 정보를 실어 프론트가 재조회 없이
쓰게 한다(spec §4-4 "기존 진단 텍스트 재사용").

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 백엔드 REST — `GET /api/assets/{asset_id}/hotspot-status`

**Files:**
- Create: `backend/services/hotspot_status.py`
- Create: `backend/routers/hotspot_status.py`
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: `data.hotspot_status.hotspot_status`(Task 3), `backend.manifest.to_print_page`(기존)
- Produces: `GET /api/assets/{asset_id}/hotspot-status` — 이후 Task 5(프론트 API)가 이 경로를 호출한다.

- [ ] **Step 1: `backend/services/hotspot_status.py` 작성**

`red` basis 의 `manual_page`(물리)에 `print_page`(인쇄)를 붙인다 — 오프셋 산술은 `backend.manifest.to_print_page()` 한 곳에만 위임한다(D26·D32·D57, `backend/services/po.py`의 `_attach_print_pages`와 같은 태도).

```python
# -*- coding: utf-8 -*-
"""설비 하이라이트 상태 서비스 — `data.hotspot_status` 위임 (D101·D73).

`mcp_server`를 import하지 않는다(D15). `print_page` 부착은 이 파일의 유일한 책임이다
(D32 — 오프셋 산술 자체는 `backend.manifest.to_print_page()`에 위임하고 재구현하지 않는다).
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.manifest import to_print_page
from data import hotspot_status as data_hotspot

from .disposal import read_only


def get(asset_id: str) -> dict:
    today = datetime.now(timezone.utc).date()
    with read_only() as con:
        result = data_hotspot.hotspot_status(con, asset_id=asset_id, today=today)
    if result.get("status") == "ok":
        model = result["model"]
        for part in result["parts"]:
            page = part.get("basis", {}).get("manual_page")
            if part["color"] == "red" and isinstance(page, int):
                part["basis"]["print_page"] = to_print_page(model, page)
    return result
```

- [ ] **Step 2: `backend/routers/hotspot_status.py` 작성**

`backend/routers/maint_value.py`의 `_status_code`/응답 조립 패턴을 따른다.

```python
# -*- coding: utf-8 -*-
"""설비 하이라이트 상태 REST 노출 (spec §4-6, D73).

```
GET /api/assets/{asset_id}/hotspot-status
```

역할 게이트를 두지 않는다 — 읽기 판정이라 403이 나오지 않는다(`maint_value.py` 선례와
같은 이유). `core` 프로파일에서도 동작한다(MCP 프로세스를 거치지 않는다).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from backend.deps import Caller, caller
from backend.services import hotspot_status as svc

router = APIRouter(prefix="/api/assets", tags=["hotspot-status"])


def _status_code(result: dict) -> int:
    status = result.get("status")
    if status == "ok":
        return 200
    if status == "not_found":
        return 404
    return 500


@router.get("/{asset_id}/hotspot-status")
def get_hotspot_status(asset_id: str, c: Caller = Depends(caller)) -> JSONResponse:
    """부품별 하이라이트 색(red/blue/orange/null) + 근거. 자산에 연결된 인버터가 없으면 404."""
    result = svc.get(asset_id)
    return JSONResponse(status_code=_status_code(result), content=result)
```

- [ ] **Step 3: `backend/main.py`에 라우터 등록**

`backend/main.py`를 열어 다른 `app.include_router(...)` 줄들 옆에 추가:

```python
from backend.routers import hotspot_status  # 다른 라우터 import 옆에 추가
...
app.include_router(hotspot_status.router)  # 다른 include_router 옆에 추가
```

- [ ] **Step 4: 수동 확인 + 회귀**

```bash
uv run python data/seed.py --with-error-codes
nohup uv run uvicorn backend.main:app --port 8021 > /tmp/hotspot_test.log 2>&1 &
sleep 3
curl -s "http://127.0.0.1:8021/api/assets/AST-L3-CONV/hotspot-status"
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8021/api/assets/NOPE/hotspot-status"
kill %1
uv run python spikes/api_contract.py
uv run ruff check backend
```

Expected: 첫 호출이 `{"status":"ok","equipment_id":"INV-L3-01","model":"iG5A","parts":[...]}`, 두 번째가 **404**. `api_contract.py`가 무증감 통과(이 라우터는 기존 계약을 건드리지 않는다).

- [ ] **Step 5: Commit**

```bash
git add backend/services/hotspot_status.py backend/routers/hotspot_status.py backend/main.py
git commit -m "$(cat <<'EOF'
[M3] GET /api/assets/{asset_id}/hotspot-status 신설 (spec §4-6, D73)

print_page 부착은 backend.manifest.to_print_page() 한 곳에만 위임(D32).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 프론트 API 배관

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Consumes: `GET /api/assets/{asset_id}/hotspot-status`(Task 4)
- Produces: `getHotspotStatus(role, assetId) => Promise<ApiHotspotStatus>` · `type ApiHotspotStatus` · `type ApiHotspotPart` — 이후 Task 8·9(목록·상세 화면)가 쓴다.

- [ ] **Step 1: `frontend/lib/api.ts`에 타입·함수 추가**

`getAsset` 정의 바로 아래에 추가:

```ts
export interface ApiHotspotPart {
  part_no: string;
  color: "red" | "blue" | "orange" | null;
  basis: Record<string, unknown>;
}

export interface ApiHotspotStatus {
  status: string;
  equipment_id?: string;
  model?: string;
  parts?: ApiHotspotPart[];
  reason?: string;
  [k: string]: unknown;
}

export const getHotspotStatus = (role: Role, assetId: string) =>
  apiFetch<ApiHotspotStatus>(
    `/api/assets/${encodeURIComponent(assetId)}/hotspot-status`,
    role
  );
```

- [ ] **Step 2: 타입 체크**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 에러 없음.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "$(cat <<'EOF'
[M3] frontend: GET hotspot-status 배관 (getHotspotStatus, ApiHotspotStatus)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `mappers.tsx` — 하이라이트 색 어휘 (D87)

**Files:**
- Modify: `frontend/lib/mappers.tsx`

**Interfaces:**
- Produces: `hotspotColorView(color) => HotspotColorLabel` — 이후 Task 7(`EquipmentHotspotDiagram`)이 이 함수만으로 색을 정한다.

- [ ] **Step 1: 파일 끝(`relativeTime` 함수 앞)에 추가**

```tsx
/* -------------------------------------------------------------------------- */
/* 설비 하이라이트 색 어휘 (Sprint 10 브레인스토밍 C, spec §4-5) —              */
/* EquipmentHotspotDiagram 전용. ⛔ 이 절 밖(컴포넌트 파일)에 "red"|"blue"|      */
/* "orange" 문자열 비교나 색 토큰이 있으면 안 된다 (D87, ui_honesty_contract L2). */

export type HotspotColor = "red" | "blue" | "orange";

const HOTSPOT_COLOR_LABEL: Record<HotspotColor, string> = {
  red: "이상탐지",
  blue: "최근 수리",
  orange: "곧 점검",
};

const HOTSPOT_COLOR_DOT: Record<HotspotColor, string> = {
  red: "var(--error-tx)",
  blue: "var(--blue-tx)",
  orange: "var(--orange-tx)",
};

export interface HotspotColorLabel {
  text: string;
  dotColor: string | null;
  known: boolean;
}

/** `color` 가 `null`이면 "정상"(색 없음) — 모르는 값이 오면 원문 그대로 + 무색 처리. */
export function hotspotColorView(color: string | null | undefined): HotspotColorLabel {
  if (color === null || color === undefined) {
    return { text: "정상", dotColor: null, known: true };
  }
  const label = HOTSPOT_COLOR_LABEL[color as HotspotColor];
  if (!label) {
    return { text: color, dotColor: null, known: false };
  }
  return { text: label, dotColor: HOTSPOT_COLOR_DOT[color as HotspotColor], known: true };
}
```

- [ ] **Step 2: 타입 체크**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 에러 없음.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/mappers.tsx
git commit -m "$(cat <<'EOF'
[M3] mappers: hotspotColorView 추가 — 하이라이트 색 전역 매핑 1곳 (D87)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `EquipmentHotspotDiagram` 컴포넌트

**Files:**
- Create: `frontend/components/asset/EquipmentHotspotDiagram.tsx`

**Interfaces:**
- Consumes: `MODEL_HOTSPOTS`·`MODEL_BASE_IMAGE`·`MODEL_CITATION`·`FAN_DETAIL_CITATION`(Task 1), `hotspotColorView`(Task 6), `ApiHotspotPart`(Task 5)
- Produces: `<EquipmentHotspotDiagram model parts />` — 이후 Task 9(상세 화면)가 이 컴포넌트를 쓴다. 내부에 기본 뷰(도면+원형 하이라이트+옆 목록) + 클릭 시 확대 패널을 전부 포함한다(자체 상태로 선택된 부품을 관리 — 상세 화면은 이 컴포넌트를 통째로 얹기만 하면 된다).

- [ ] **Step 1: `EquipmentHotspotDiagram.tsx` 작성**

```tsx
"use client";

import { useState } from "react";
import { Mono } from "@/components/ui/Mono";
import type { ApiHotspotPart } from "@/lib/api";
import {
  FAN_DETAIL_CITATION,
  MODEL_BASE_IMAGE,
  MODEL_CITATION,
  MODEL_HOTSPOTS,
  type Hotspot,
} from "@/lib/hotspots";
import { hotspotColorView } from "@/lib/mappers";
import { sx } from "@/lib/sx";

/**
 * 설비 하이라이트 도면 (Sprint 10 브레인스토밍 C, spec §4-1·§4-4).
 *
 * 기본 뷰: 매뉴얼 도면 위 3개 하이라이트 원 + 옆 목록(색 있는 것만). 원과 목록 항목은
 * 같은 상세 패널을 연다(spec §4-1 "도면 위 원과 옆 목록 항목은 같은 상세 패널을 연다").
 *
 * 확대 뷰: 냉각팬은 매뉴얼 실제 근접 이미지로 전환(`detailImage`), 나머지는 기본 도면을
 * 그 좌표 중심으로 CSS `transform: scale()` 확대한다(spec §4-4 — 별도 이미지 없음).
 */
export function EquipmentHotspotDiagram({
  model,
  parts,
}: {
  model: string;
  parts: ApiHotspotPart[];
}) {
  const [selected, setSelected] = useState<string | null>(null);

  const hotspots = MODEL_HOTSPOTS[model];
  const baseImage = MODEL_BASE_IMAGE[model];
  const citation = MODEL_CITATION[model];

  if (!hotspots || !baseImage) {
    return (
      <div style={sx("font:12px 'Pretendard';color:var(--dim)")}>
        이 모델({model})의 도면이 등록돼 있지 않습니다.
      </div>
    );
  }

  const statusByPart = new Map(parts.map((p) => [p.part_no, p]));
  const selectedHotspot = hotspots.find((h) => h.partNo === selected) ?? null;
  const selectedStatus = selected ? statusByPart.get(selected) : undefined;

  return (
    <div style={sx("display:flex;flex-direction:column;gap:12px")}>
      <div style={sx("display:flex;gap:16px;flex-wrap:wrap")}>
        <div
          style={sx(
            "position:relative;width:min(560px,100%);border:1px solid var(--line);" +
              "border-radius:8px;overflow:hidden;background:var(--panel)"
          )}
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- 크롭된 정적 자산, 최적화 불필요 */}
          <img
            src={baseImage}
            alt={`${model} 도면`}
            style={sx("display:block;width:100%;height:auto")}
          />
          {hotspots.map((h) => {
            const status = statusByPart.get(h.partNo);
            const view = hotspotColorView(status?.color ?? null);
            return (
              <button
                key={h.partNo}
                onClick={() => setSelected(h.partNo)}
                aria-label={h.label}
                style={sx(
                  `position:absolute;left:${h.x}%;top:${h.y}%;transform:translate(-50%,-50%);` +
                    "width:28px;height:28px;border-radius:50%;cursor:pointer;" +
                    (view.dotColor
                      ? `border:2px solid ${view.dotColor};background:${view.dotColor}33`
                      : "border:1.5px dashed var(--line2);background:transparent")
                )}
              />
            );
          })}
        </div>

        <div style={sx("flex:1;min-width:200px;display:flex;flex-direction:column;gap:8px")}>
          <span style={sx("font:700 12px 'Pretendard';color:var(--ink)")}>하이라이트 항목</span>
          {hotspots
            .map((h) => ({ h, status: statusByPart.get(h.partNo) }))
            .filter(({ status }) => status?.color)
            .map(({ h, status }) => {
              const view = hotspotColorView(status!.color);
              return (
                <button
                  key={h.partNo}
                  onClick={() => setSelected(h.partNo)}
                  style={sx(
                    "display:flex;align-items:center;gap:8px;text-align:left;cursor:pointer;" +
                      "border:1px solid var(--line2);background:var(--raise);border-radius:7px;" +
                      "padding:7px 10px"
                  )}
                >
                  <span
                    style={sx(
                      `width:9px;height:9px;border-radius:50%;background:${view.dotColor}`
                    )}
                  />
                  <span style={sx("font:700 12px 'Pretendard';color:var(--ink)")}>{h.label}</span>
                  <span style={sx("font:11px 'Pretendard';color:var(--dim)")}>{view.text}</span>
                </button>
              );
            })}
          {hotspots.every((h) => !statusByPart.get(h.partNo)?.color) && (
            <span style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>
              하이라이트된 부위가 없습니다.
            </span>
          )}
          <span style={sx("font:11px 'Pretendard';color:var(--dim2);margin-top:4px")}>
            {citation}
          </span>
        </div>
      </div>

      {selectedHotspot && (
        <DetailPanel
          model={model}
          hotspot={selectedHotspot}
          status={selectedStatus}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

function DetailPanel({
  model,
  hotspot,
  status,
  onClose,
}: {
  model: string;
  hotspot: Hotspot;
  status: ApiHotspotPart | undefined;
  onClose: () => void;
}) {
  const view = hotspotColorView(status?.color ?? null);
  const baseImage = MODEL_BASE_IMAGE[model];

  return (
    <div
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:14px;" +
          "display:flex;gap:16px;flex-wrap:wrap"
      )}
    >
      <div
        style={sx(
          "position:relative;width:min(420px,100%);height:260px;border-radius:6px;" +
            "overflow:hidden;background:var(--raise)"
        )}
      >
        {hotspot.detailImage ? (
          // eslint-disable-next-line @next/next/no-img-element -- 크롭된 정적 자산
          <img
            src={hotspot.detailImage}
            alt={`${hotspot.label} 근접`}
            style={sx("display:block;width:100%;height:100%;object-fit:contain")}
          />
        ) : (
          <div
            style={sx(
              `position:absolute;inset:0;background-image:url(${baseImage});` +
                "background-repeat:no-repeat;background-size:280%;" +
                `background-position:${hotspot.x}% ${hotspot.y}%`
            )}
          />
        )}
      </div>

      <div style={sx("flex:1;min-width:220px;display:flex;flex-direction:column;gap:8px")}>
        <div style={sx("display:flex;align-items:center;gap:8px")}>
          <span style={sx("font:700 13px 'Pretendard';color:var(--ink)")}>{hotspot.label}</span>
          <Mono size={11}>{hotspot.partNo}</Mono>
          <span
            style={sx(
              `font:700 11px 'Pretendard';color:${view.dotColor ?? "var(--dim)"}`
            )}
          >
            {view.text}
          </span>
          <div style={sx("flex:1")} />
          <button
            onClick={onClose}
            style={sx(
              "border:1px solid var(--line2);background:transparent;border-radius:6px;" +
                "width:24px;height:24px;cursor:pointer;color:var(--dim)"
            )}
          >
            ✕
          </button>
        </div>

        {hotspot.approximate && (
          <div
            style={sx(
              "border:1.5px dashed var(--orange-tx);border-radius:6px;padding:6px 9px;" +
                "font:11px/1.6 'Pretendard';color:var(--orange-tx)"
            )}
          >
            ⚠ 매뉴얼에 정확한 라벨이 없어 대략적인 영역입니다 — 실제 부품 위치와 다를 수 있습니다.
          </div>
        )}

        <DetailBody color={status?.color ?? null} basis={status?.basis ?? {}} />

        {hotspot.detailImage && (
          <span style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
            {FAN_DETAIL_CITATION}
          </span>
        )}
      </div>
    </div>
  );
}

/** color 별 근거 텍스트 — 값을 검사해 분기하되, 색·문구는 hotspotColorView 가 이미 정했다. */
function DetailBody({
  color,
  basis,
}: {
  color: "red" | "blue" | "orange" | null;
  basis: Record<string, unknown>;
}) {
  if (color === "red") {
    const causes = Array.isArray(basis.causes) ? (basis.causes as string[]) : [];
    const actions = Array.isArray(basis.actions) ? (basis.actions as string[]) : [];
    return (
      <div style={sx("display:flex;flex-direction:column;gap:6px;font:12px/1.6 'Pretendard'")}>
        {typeof basis.code === "string" && (
          <span style={sx("color:var(--dim)")}>
            에러코드 <Mono size={11}>{basis.code}</Mono>
            {typeof basis.occurred_at === "string" && ` · ${basis.occurred_at}`}
          </span>
        )}
        {causes.length > 0 && (
          <div>
            <b style={sx("color:var(--ink)")}>원인</b>
            <ul style={sx("margin:4px 0 0 18px;padding:0;color:var(--ink2)")}>
              {causes.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </div>
        )}
        {actions.length > 0 && (
          <div>
            <b style={sx("color:var(--ink)")}>조치</b>
            <ul style={sx("margin:4px 0 0 18px;padding:0;color:var(--ink2)")}>
              {actions.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </div>
        )}
        {typeof basis.manual_page === "number" && (
          <span style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
            근거:{" "}
            {typeof basis.print_page === "number"
              ? `인쇄 p.${basis.print_page} · PDF p.${basis.manual_page}`
              : `PDF p.${basis.manual_page}`}
          </span>
        )}
      </div>
    );
  }

  if (color === "blue") {
    return (
      <div style={sx("font:12px/1.6 'Pretendard';color:var(--ink2)")}>
        {typeof basis.signed_at === "string" && <div>수리 일자: {basis.signed_at}</div>}
        {typeof basis.performed_by_name === "string" && (
          <div>작업자: {basis.performed_by_name}</div>
        )}
        {typeof basis.repair_id === "string" && (
          <div style={sx("color:var(--dim)")}>
            증빙 <Mono size={11}>{basis.repair_id}</Mono>
          </div>
        )}
      </div>
    );
  }

  if (color === "orange") {
    return (
      <div style={sx("font:12px/1.6 'Pretendard';color:var(--ink2)")}>
        {typeof basis.next_maintenance_due === "string" && (
          <div>다음 점검 예정일: {basis.next_maintenance_due}</div>
        )}
        <span style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
          ⚠ 생애주기 mock 데이터입니다 — 실제 정비 이력에서 유도한 값이 아닙니다.
        </span>
      </div>
    );
  }

  return (
    <div style={sx("font:12px 'Pretendard';color:var(--dim)")}>
      현재 하이라이트된 상태가 없습니다.
    </div>
  );
}
```

이 파일은 `next/image`의 `Image`를 쓰지 않는다 — 크롭 이미지는 반응형 폭에 맞춰 `<img>`로 직접 렌더한다(Next.js `Image`는 고정 크기 최적화가 목적이라 이 용도에 맞지 않는다).

- [ ] **Step 2: 타입 체크**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 에러 없음.

- [ ] **Step 3: D87 확인 — 이 파일에 상태 문자열 리터럴이 없는지**

```bash
rg -n '"red"|"blue"|"orange"' frontend/components/asset/EquipmentHotspotDiagram.tsx
```

Expected: 타입 어노테이션(`color: "red" | "blue" | "orange" | null`)과 `DetailBody`의 분기(`if (color === "red")` 등)에서만 나타난다 — **이건 D87 위반이 아니다.** D87이 금지하는 것은 "색·문구를 정하는 리터럴 맵"이 컴포넌트에 있는 것이다(예: `{red: "빨강"}` 같은 로컬 맵). 여기서는 색·문구 결정은 전부 `hotspotColorView()` 위임이고, `color === "red"` 분기는 **어떤 근거 필드(causes/actions vs signed_at vs next_maintenance_due)를 렌더할지**를 고르는 것뿐 — 색상 코드나 라벨 문자열을 만들지 않는다. (이 구분이 애매하면 reviewer 단계에서 재확인할 것 — `ui_honesty_contract.py` L2 규칙 자체는 `"red"` 같은 임의 문자열을 스캔하지 않고 `STATE_WORDS`(D79 판정 어휘 등) 목록만 스캔하므로 이 파일은 자동 스캔에 걸리지 않는다.)

- [ ] **Step 4: Commit**

```bash
git add frontend/components/asset/EquipmentHotspotDiagram.tsx
git commit -m "$(cat <<'EOF'
[M3] EquipmentHotspotDiagram 신설 — 도면 하이라이트 + 확대 상세 (spec §4-1·§4-4)

색·문구는 hotspotColorView() 한 곳 위임(D87). 확대는 냉각팬만 실제 근접 이미지,
나머지는 CSS 배경 확대. 확대 패널 텍스트는 기존 진단 causes/actions·수리 서명
정보 재사용 — 신규 데이터 생성 없음.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: 목록 화면 `/technician/equipment-status`

**Files:**
- Create: `frontend/app/(console)/technician/equipment-status/page.tsx`

**Interfaces:**
- Consumes: `getAssets`(기존, `frontend/lib/api.ts`), `getHotspotStatus`(Task 5)

- [ ] **Step 1: 페이지 작성**

`frontend/app/(console)/technician/asset/page.tsx`(자산 목록)의 구조를 참고하되, 각 카드에 하이라이트 배지를 붙인다.

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ConsoleFrame, ConsoleHeader, ScreenStack, Spacer } from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Avatar, Divider, Logo } from "@/components/ui/Chip";
import { Mono } from "@/components/ui/Mono";
import { getAssets, getHotspotStatus, type ApiAsset, type ApiHotspotStatus } from "@/lib/api";
import { ROLE_USER_NAME } from "@/lib/role";
import { sx } from "@/lib/sx";

/**
 * `/technician/equipment-status` — 설비 하이라이트 대시보드 목록 (Sprint 10 브레인스토밍 C).
 *
 * 독립된 신규 화면이다(`asset` 목록과 별개, spec §4-1 "독립된 새 대시보드 화면"). 자산마다
 * `hotspot-status`를 조회해 배지(🔴N 🟠N 🔵N)를 붙인다 — 9개뿐이라 병렬 호출로 충분하다.
 */
export default function EquipmentStatusListPage() {
  const [assets, setAssets] = useState<ApiAsset[] | null>(null);
  const [statusByAsset, setStatusByAsset] = useState<Map<string, ApiHotspotStatus>>(new Map());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getAssets("technician")
      .then(async (items) => {
        if (!alive) return;
        setAssets(items);
        setError(null);
        const entries = await Promise.all(
          items.map(async (a) => {
            try {
              return [a.asset_id, await getHotspotStatus("technician", a.asset_id)] as const;
            } catch {
              return [a.asset_id, { status: "error" } as ApiHotspotStatus] as const;
            }
          })
        );
        if (alive) setStatusByAsset(new Map(entries));
      })
      .catch(() => {
        if (alive) {
          setAssets([]);
          setError("백엔드에 연결하지 못했습니다 — 설비 목록을 가져오지 못했습니다.");
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <ScreenStack>
      {error && <StatusBanner tone="error">⚠ {error}</StatusBanner>}
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 13px 'Pretendard';color:var(--ink)")}>설비 하이라이트</span>
          <Mono size={11.5}>{assets === null ? "…" : `${assets.length}대`}</Mono>
          <Spacer />
          <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>
            정비사 {ROLE_USER_NAME.technician}
          </span>
          <Avatar />
        </ConsoleHeader>

        <div style={sx("padding:14px 16px;display:flex;flex-direction:column;gap:10px")}>
          {assets === null ? (
            <div style={sx("font:12.5px 'Pretendard';color:var(--dim);padding:20px 0")}>
              불러오는 중…
            </div>
          ) : (
            assets.map((a) => (
              <EquipmentRow key={a.asset_id} asset={a} status={statusByAsset.get(a.asset_id)} />
            ))
          )}
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}

function EquipmentRow({
  asset,
  status,
}: {
  asset: ApiAsset;
  status: ApiHotspotStatus | undefined;
}) {
  const parts = status?.parts ?? [];
  const counts = { red: 0, orange: 0, blue: 0 };
  for (const p of parts) {
    if (p.color === "red") counts.red += 1;
    else if (p.color === "orange") counts.orange += 1;
    else if (p.color === "blue") counts.blue += 1;
  }

  return (
    <Link
      href={`/technician/equipment-status/${encodeURIComponent(asset.asset_id)}`}
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:11px 14px;" +
          "display:flex;align-items:center;gap:12px;flex-wrap:wrap;text-decoration:none"
      )}
    >
      <Mono size={12}>{asset.asset_id}</Mono>
      <span style={sx("font:700 13px 'Pretendard';color:var(--ink);min-width:180px")}>
        {asset.name}
      </span>
      <span style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>
        라인 {asset.line_id ?? "미배정"}
      </span>
      <div style={sx("flex:1")} />
      {status === undefined ? (
        <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>확인 중…</span>
      ) : status.status !== "ok" ? (
        <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>상태 미상</span>
      ) : (
        <div style={sx("display:flex;gap:8px")}>
          {counts.red > 0 && <Badge color="var(--error-tx)">🔴 {counts.red}</Badge>}
          {counts.orange > 0 && <Badge color="var(--orange-tx)">🟠 {counts.orange}</Badge>}
          {counts.blue > 0 && <Badge color="var(--blue-tx)">🔵 {counts.blue}</Badge>}
          {counts.red + counts.orange + counts.blue === 0 && (
            <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>정상</span>
          )}
        </div>
      )}
    </Link>
  );
}

function Badge({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span style={sx(`font:700 11.5px 'Pretendard';color:${color}`)}>{children}</span>
  );
}
```

- [ ] **Step 2: 타입 체크 + 빌드**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Expected: 에러 없음. 라우트 목록에 `/technician/equipment-status`가 새로 나타난다(정적/동적 여부는 빌드 출력에서 확인).

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/(console)/technician/equipment-status/page.tsx"
git commit -m "$(cat <<'EOF'
[M3] /technician/equipment-status 목록 화면 신설 (spec §4-1 ①)

독립된 신규 화면 — 자산 목록(asset)과 별개. 9개 설비 각각 hotspot-status 병렬 조회
후 🔴🟠🔵 배지로 요약.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: 상세 화면 `/technician/equipment-status/[assetId]`

**Files:**
- Create: `frontend/app/(console)/technician/equipment-status/[assetId]/page.tsx`

**Interfaces:**
- Consumes: `getAsset`(기존), `getHotspotStatus`(Task 5), `EquipmentHotspotDiagram`(Task 7)

- [ ] **Step 1: 페이지 작성**

`frontend/app/(console)/technician/asset/[assetId]/value/page.tsx`의 페치·에러 처리 구조를 따른다.

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { EquipmentHotspotDiagram } from "@/components/asset/EquipmentHotspotDiagram";
import { ConsoleFrame, ScreenStack } from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Mono } from "@/components/ui/Mono";
import { ApiError, getAsset, getHotspotStatus, type ApiAsset, type ApiHotspotStatus } from "@/lib/api";
import { sx } from "@/lib/sx";

/**
 * `/technician/equipment-status/{assetId}` — 설비 하이라이트 상세 (Sprint 10 브레인스토밍 C).
 *
 * 이 화면도 아무것도 저장하지 않는다 — `hotspot-status`는 읽기 전용 집계다.
 */
export default function EquipmentStatusDetailPage({
  params,
}: {
  params: { assetId: string };
}) {
  const assetId = decodeURIComponent(params.assetId);

  const [asset, setAsset] = useState<ApiAsset | null>(null);
  const [status, setStatus] = useState<ApiHotspotStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([getAsset("technician", assetId), getHotspotStatus("technician", assetId)])
      .then(([a, s]) => {
        if (!alive) return;
        setAsset(a);
        setStatus(s);
        setError(null);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setAsset(null);
        setError(
          e instanceof ApiError && e.status === 404
            ? `등록부에 없는 식별자입니다 — ${assetId}`
            : "백엔드에 연결하지 못했습니다 — 설비 정보를 가져오지 못했습니다."
        );
      });
    return () => {
      alive = false;
    };
  }, [assetId]);

  if (error) {
    return (
      <ScreenStack>
        <StatusBanner tone="error">⚠ {error}</StatusBanner>
        <Link
          href="/technician/equipment-status"
          style={sx("font:12px 'Pretendard';color:var(--blue-tx);text-decoration:none")}
        >
          ← 설비 하이라이트 목록으로
        </Link>
      </ScreenStack>
    );
  }

  if (!asset || !status) {
    return (
      <ScreenStack>
        <ConsoleFrame>
          <div style={sx("padding:24px;font:12.5px 'Pretendard';color:var(--dim)")}>
            불러오는 중…
          </div>
        </ConsoleFrame>
      </ScreenStack>
    );
  }

  return (
    <ScreenStack>
      <ConsoleFrame>
        <div style={sx("padding:14px 16px;display:flex;flex-direction:column;gap:14px")}>
          <div style={sx("display:flex;align-items:center;gap:10px")}>
            <Link
              href="/technician/equipment-status"
              style={sx("font:12px 'Pretendard';color:var(--blue-tx);text-decoration:none")}
            >
              ← 목록
            </Link>
            <span style={sx("font:700 14px 'Pretendard';color:var(--ink)")}>{asset.name}</span>
            <Mono size={11.5}>{asset.asset_id}</Mono>
            {status.status === "ok" && <Mono size={11.5}>{status.model}</Mono>}
          </div>

          {status.status !== "ok" ? (
            <div
              style={sx(
                "border:1px dashed var(--line2);border-radius:7px;padding:16px;" +
                  "font:12.5px/1.7 'Pretendard';color:var(--dim)"
              )}
            >
              이 설비의 하이라이트 상태를 확인할 수 없습니다
              {status.status === "not_found" ? " — 연결된 인버터가 없습니다." : "."}
            </div>
          ) : (
            <EquipmentHotspotDiagram model={status.model!} parts={status.parts ?? []} />
          )}
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}
```

- [ ] **Step 2: 타입 체크 + 빌드**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Expected: 에러 없음. 라우트 목록에 `/technician/equipment-status/[assetId]`가 나타난다.

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/(console)/technician/equipment-status/[assetId]/page.tsx"
git commit -m "$(cat <<'EOF'
[M3] /technician/equipment-status/[assetId] 상세 화면 신설 (spec §4-1 ②)

기본 뷰(도면+하이라이트+목록) + 클릭 시 확대는 EquipmentHotspotDiagram 에 위임.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: 전체 회귀 + 수동 확인 + 문서 반영

**Files:**
- Modify: `docs/04_MCP_TOOLS.md` 또는 `docs/06_REPO_API.md`(REST 신설 반영)
- Modify: `docs/05_DB_SCHEMA.md`(§19 반영)
- Modify: `CLAUDE.md`(회귀 기준선 갱신)

- [ ] **Step 1: 전체 회귀**

```bash
uv run python data/seed.py --with-error-codes
uv run --with pytest python -m pytest data/rules/test_rules.py -q
for f in spikes/*.py; do
  name=$(basename "$f" .py)
  out=$(uv run python "$f" 2>&1)
  if [ $? -ne 0 ]; then echo "FAIL: $name"; echo "$out" | tail -5; else echo "OK: $name"; fi
done
uv run ruff check data backend mcp_server spikes
cd frontend && npx tsc --noEmit && npm run build
```

Expected: seed 통과(검증 표에 ㉛ PASS 포함), pytest 46건, spikes 전건 통과(실패 스위트는 CLAUDE.md 규약대로 단독 재실행해 Windows 소켓 고갈인지 진짜 회귀인지 구분), ruff 통과, tsc/build 통과(라우트 2개 증가 — `equipment-status`, `equipment-status/[assetId]`).

특히 다음 두 스위트를 눈여겨본다:
- `spikes/ui_honesty_contract.py` — `L2 스캔 대상 N개` 하한이 이번에 만든 `EquipmentHotspotDiagram.tsx` 1개만큼 자연 증가해야 한다(글롭이 자동 편입, 코드 수정 불필요). 만약 안 늘었으면 파일 위치(`components/asset/`)가 틀린 것이다.
- `spikes/db_concurrency.py` — 새 테이블(`part_lifecycle_mock`)이 FK 있는 스키마 변경이라, 이 스위트가 스키마 전체를 대상으로 하는 검사라면 영향이 없는지 확인.

- [ ] **Step 2: 브라우저 수동 확인**

`data/seed.py` 재시드 후 백엔드(`uv run uvicorn backend.main:app --port 8021`)와 프론트(`NEXT_PUBLIC_API_BASE=http://localhost:8021 npm run dev`)를 띄우고:
- `/technician/equipment-status` — 9개 설비가 나열되고 일부에 🔴/🟠/🔵 배지가 보이는지
- 배지가 있는 설비 클릭 → 상세 화면에서 도면 위 원형 하이라이트가 배지 색과 일치하는지
- 하이라이트 원 클릭 → 냉각팬이면 실제 근접 이미지(그림 1-4)로, 키패드/제어보드면 CSS 확대로 전환되는지
- 확대 패널에 진단 원인/조치문 또는 수리 서명 정보 또는 다음 점검일이 색에 맞게 뜨는지
- 제어보드 하이라이트에 "정확한 위치가 아니다" 경고가 뜨는지
- 도면 아래 출처 고지(LS ELECTRIC 매뉴얼 p.○)가 항상 보이는지

테스트 후 서버 프로세스 종료, DB 재시드로 원복.

- [ ] **Step 3: 문서 반영**

`docs/05_DB_SCHEMA.md`에 §19 `part_lifecycle_mock` 절 추가(§18 뒤, 기존 절 형식대로 CREATE TABLE + 설계 포인트). `docs/06_REPO_API.md`에 `GET /api/assets/{asset_id}/hotspot-status` 1줄 추가. `CLAUDE.md`의 "실측 기준선" 표에서 seed 건수(㉛ 추가분 +1) 및 spikes 건수 변화(영향받은 스위트가 있다면)를 갱신 — 정확한 신규 건수는 Step 1의 실행 결과를 그대로 옮겨 적는다(추측 금지).

```bash
git add docs/05_DB_SCHEMA.md docs/06_REPO_API.md CLAUDE.md
git commit -m "$(cat <<'EOF'
[M1] docs: part_lifecycle_mock(§19)·hotspot-status REST 반영 + 회귀 기준선 갱신

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
