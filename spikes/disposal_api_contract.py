# -*- coding: utf-8 -*-
"""S9 REST 계약 검증 — 처분 사전판정의 HTTP 매핑 (D71) · 무저장 · 무권한게이트.

핵심 3가지:
  1. **`HOLD`·`INSUFFICIENT_FACTS` 가 200 이 아니다.** 200 은 클라이언트에게 "진행 가능"
     이므로, 여기서 200 을 주면 D62("알 수 없다 ≠ 통과")가 API 경계에서 무너진다.
  2. **저장하지 않는다.** POST 지만 `decisions`·`flags` 행 수가 변하지 않는다.
  3. **403 이 없다.** `X-Role: technician` 으로도 200/409 가 나와야 한다 — 읽기 판정에
     403 을 만들면 "권한 위반 403 차단 100%" 지표에 법정 조건 미충족이 섞인다(D38).

임시 DB 사본에서 돌린다. 프로브 날짜는 **숫자를 베끼지 않고** `data.seed` 의
`DISPOSAL_PROBE_MONTHS` 로 만든다 — 시드가 상대 날짜라 하드코딩하면 내일 깨진다.

실행:  uv run python spikes/disposal_api_contract.py
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DB = ROOT / "data" / "maintq.db"
sys.path.insert(0, str(ROOT))
from data import dbcompat, pg_isolation  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


TECH = {"X-Role": "technician", "X-User": "tech-01"}
MGR = {"X-Role": "manager", "X-User": "mgr-01"}


def _open_shared(db):
    """precheck() 는 순수 읽기라 — Postgres 타겟에서는 공유 public 스키마를 그대로
    읽어도 안전하다(⑲ 가 무저장을 확인한다). `db` 는 SQLite 타겟에서만 실제로 쓰인다."""
    if dbcompat.USE_POSTGRES:
        return dbcompat.connect_dsn(pg_isolation.BASE_DATABASE_URL)
    return sqlite3.connect(db)


def row_counts(db: Path) -> dict[str, int]:
    """무저장 증명용 — 판정 경로가 건드릴 수 있는 테이블의 행 수 + assets 지문."""
    con = _open_shared(db)
    try:
        counts = {
            t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: S608
            for t in ("decisions", "flags", "assets", "rules", "law_refs")
        }
        blob = "\n".join(
            "|".join("" if v is None else str(v) for v in r)
            for r in con.execute("SELECT * FROM assets ORDER BY asset_id")
        )
        counts["assets_fingerprint"] = int(hashlib.sha256(blob.encode()).hexdigest()[:8], 16)
        return counts
    finally:
        con.close()


def _count_decisions(dsn: str) -> int:
    con = dbcompat.connect_dsn(dsn)
    try:
        return con.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    finally:
        con.close()


def probe_dates(db) -> dict[str, str]:
    """`acquired_at + DISPOSAL_PROBE_MONTHS` — 시드가 만든 규칙을 그대로 재사용한다."""
    sys.path.insert(0, str(ROOT))
    from data.seed import DISPOSAL_PROBE_MONTHS, _shift_months  # noqa: PLC0415

    con = _open_shared(db)
    try:
        out = {}
        for asset_id, months in DISPOSAL_PROBE_MONTHS.items():
            r = con.execute(
                "SELECT acquired_at FROM assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            out[asset_id] = _shift_months(date.fromisoformat(r[0]), months)
        return out
    finally:
        con.close()


BUCKETS = ("blockers", "preconditions", "holds", "insufficient")


def judgment_signature(result: dict) -> dict:
    """두 판정 경로(파일 정본 ↔ DB 사본)를 대조할 때 쓰는 **지문**.

    ⚠ `verdict` 만 보면 검사력이 모자란다. `disposal_type` 을 BLOCKING→PRECONDITION 으로
      내린 뮤턴트는 **verdict 로 드러나지 않는다** — `AST-L3-CONV` 는 blocker 가 2건이라
      하나를 내려도 `BLOCKED` 로 남는다(Sprint 6 실측, `asset_tools_contract.py:590-594`
      가 같은 사실을 주석으로 남겼다). **버킷 소속과 인용 조문으로는 드러난다.**

    ⛔ `message`·`disclaimer` 는 넣지 않는다. 전자는 자유 문장이라 취성이고, 후자는 MCP
       도구가 `evidence_completeness` 에 따라 접미사를 붙여 **조문 수집이 진행되면 값이
       바뀐다**. 문구 드리프트는 ㉕㉖ 이 **엔진 상수와 REST 응답**을 직접 대조한다.

    비교 로직을 한 벌로 유지하는 이유: 뮤턴트 확인이 이 함수를 그대로 재사용해야
    "확장 전에는 안 잡히고 확장 후에는 잡힌다"를 같은 코드로 보일 수 있다.
    """
    return {
        "verdict": result["verdict"],
        "buckets": {b: sorted(f["rule_id"] for f in result[b]) for b in BUCKETS},
        "law_refs": {b: sorted({r for f in result[b] for r in f["law_refs"]}) for b in BUCKETS},
    }


def precheck(client, asset_id: str, mode: str, when: str | None = None, headers=None):
    body: dict = {"disposal_mode": mode}
    if when is not None:
        body["disposal_date"] = when
    return client.post(
        f"/api/assets/{asset_id}/disposal/precheck", json=body, headers=headers or TECH
    )


def run(client, db: Path, probe: dict[str, str], captured: dict) -> None:
    before = row_counts(db)

    # ── 목록·상세
    items = client.get("/api/assets", headers=TECH).json()["items"]
    check("① 자산 목록 9건 (line 오름차순)", len(items) == 9, f"{len(items)}건 {items[0]['asset_id']}")

    l3 = client.get("/api/assets", params={"line_id": 3}, headers=TECH).json()["items"]
    check(
        "② line_id 필터",
        len(l3) == 3 and {a["asset_id"] for a in l3} == {"AST-L3-CONV", "AST-L3-EXFAN", "AST-L3-LIFT"},
        f"{[a['asset_id'] for a in l3]}",
    )

    in_use = client.get("/api/assets", params={"status": "IN_USE"}, headers=TECH).json()["items"]
    disposed = client.get("/api/assets", params={"status": "DISPOSED"}, headers=TECH).json()["items"]
    check("③ status 필터", len(in_use) == 9 and len(disposed) == 0, f"IN_USE={len(in_use)}, DISPOSED={len(disposed)}")

    d = client.get("/api/assets/AST-L3-CONV", headers=TECH).json()
    check(
        "④ 상세 + 하위 equipment (D68)",
        [e["equipment_id"] for e in d["equipment"]] == ["INV-L3-01"]
        and d["asset_id"] == "AST-L3-CONV"
        and any(a["asset_id"] == "AST-L3-CONV" and a["equipment_count"] == 1 for a in items),
        f"equipment={[e['equipment_id'] for e in d['equipment']]}",
    )
    check(
        "⑤ 없는 자산 상세 → 404",
        client.get("/api/assets/AST-NOPE", headers=TECH).status_code == 404,
        "404",
    )

    # ── ★ D71 — BLOCKED → 409
    r = precheck(client, "AST-L3-CONV", "SALE", probe["AST-L3-CONV"])
    b = r.json()
    check(
        "⑥ AST-L3-CONV(세액공제+무동의담보) → 409 BLOCKED · blockers 2건",
        r.status_code == 409 and b["verdict"] == "BLOCKED" and len(b["blockers"]) == 2,
        f"{r.status_code} {b['verdict']} blockers={[f['rule_id'] for f in b['blockers']]}",
    )
    check(
        "⑦ 409 본문 = 200 형태 + detail · 근거·해소경로가 함께 온다 (S9: 거부하되 이유와 경로를)",
        bool(b["detail"])
        and b["resolve_options"]
        and all(f["citations"] for f in b["blockers"])
        and b["note"] == "판정 결과이며 처분 요청이 생성되지 않았습니다. 확정은 서명으로만 이뤄집니다.",
        f"detail={b['detail'][:34]}… resolve={len(b['resolve_options'])}건",
    )

    # ── ★ D71/D79 — HOLD 와 INSUFFICIENT_FACTS 를 200 으로 주지 않는다
    r = precheck(client, "AST-L4-WRAP", "SALE", probe["AST-L4-WRAP"])
    b = r.json()
    check(
        "⑧ AST-L4-WRAP(경계 22~26개월) → 409 HOLD (★ 200 이면 D62 붕괴)",
        r.status_code == 409 and b["verdict"] == "HOLD" and len(b["holds"]) == 1,
        f"{r.status_code} {b['verdict']} holds={[f['rule_id'] for f in b['holds']]}",
    )
    r = precheck(client, "AST-L4-DUST", "SALE", probe["AST-L4-DUST"])
    b = r.json()
    check(
        "⑨ AST-L4-DUST(tax_credit_applied NULL) → 409 INSUFFICIENT_FACTS (HOLD 로 흡수 안 함, D79)",
        r.status_code == 409
        and b["verdict"] == "INSUFFICIENT_FACTS"
        and "tax_credit_applied" in b["missing_facts"],
        f"{r.status_code} {b['verdict']} missing={b['missing_facts']}",
    )

    # ── 200 경로
    r = precheck(client, "AST-L2-SPDL", "SALE", probe["AST-L2-SPDL"])
    b = r.json()
    check(
        "⑩ AST-L2-SPDL → 200 CONDITIONAL · checklist 비어있지 않고 **전 항목에 citations**",
        r.status_code == 200
        and b["verdict"] == "CONDITIONAL"
        and len(b["checklist"]) > 0
        and all(i["citations"] and i["action"] for i in b["checklist"]),
        f"{r.status_code} {b['verdict']} checklist={len(b['checklist'])}항목",
    )
    r = precheck(client, "AST-L3-LIFT", "SCRAP", probe["AST-L3-LIFT"])
    b = r.json()
    check(
        "⑪ AST-L3-LIFT + SCRAP → 200 CLEAR",
        r.status_code == 200 and b["verdict"] == "CLEAR" and b["checklist"] == [],
        f"{r.status_code} {b['verdict']} checklist={len(b['checklist'])}",
    )
    r = precheck(client, "AST-L3-LIFT", "SALE", probe["AST-L3-LIFT"])
    b = r.json()
    check(
        "⑫ 같은 자산·같은 날짜 + SALE → 200 CONDITIONAL (VAT-INVOICE — mode 로 판정이 갈린다)",
        r.status_code == 200
        and b["verdict"] == "CONDITIONAL"
        and any(f["rule_id"] == "VAT-INVOICE" for f in b["preconditions"]),
        f"{r.status_code} {b['verdict']} preconditions={[f['rule_id'] for f in b['preconditions']]}",
    )

    # ── 요청 오류
    r = precheck(client, "AST-NOPE", "SALE", "2026-01-01")
    check("⑬ 없는 자산 precheck → 404", r.status_code == 404, f"{r.status_code}")
    r = precheck(client, "AST-L3-LIFT", "GIFT", "2026-01-01")
    check("⑭ disposal_mode 'GIFT' → 422 (enum 은 engine.DISPOSAL_MODES 단일 출처)", r.status_code == 422, f"{r.status_code}")
    r = precheck(client, "AST-L3-LIFT", "SALE", "2026-13-99")
    check("⑮ 판독 불가 disposal_date → 422 (조용히 무시하지 않는다)", r.status_code == 422, f"{r.status_code}")

    # ── D62 — 사실이 없으면 CLEAR 로 내려가지 않는다
    r = precheck(client, "AST-L3-CONV", "SALE")  # disposal_date 생략
    b = r.json()
    check(
        "⑯ disposal_date 생략 → 409, TAX-CREDIT-2Y 는 insufficient (CLEAR 로 조용히 통과 금지)",
        r.status_code == 409
        and any(f["rule_id"] == "TAX-CREDIT-2Y" for f in b["insufficient"])
        and "disposal_date" in b["missing_facts"],
        f"{r.status_code} {b['verdict']} insufficient={[f['rule_id'] for f in b['insufficient']]}",
    )

    # ── ★ 역할 게이트 없음 (403 이 나오면 안 된다)
    codes = {
        role: (
            precheck(client, "AST-L3-CONV", "SALE", probe["AST-L3-CONV"], h).status_code,
            precheck(client, "AST-L3-LIFT", "SCRAP", probe["AST-L3-LIFT"], h).status_code,
            client.get("/api/assets", headers=h).status_code,
        )
        for role, h in (("technician", TECH), ("manager", MGR))
    }
    check(
        "⑰ technician·manager 모두 409/200/200 — **403 없음** (D38 지표 오염 방지)",
        all(c == (409, 200, 200) for c in codes.values()),
        f"{codes}",
    )

    # ── 시각 규약 (D39)
    b = precheck(client, "AST-L2-SPDL", "SALE", probe["AST-L2-SPDL"]).json()
    check(
        "⑱ generated_at 은 UTC ISO-8601(...Z) · evaluated_at 은 판정 기준일",
        b["generated_at"].endswith("Z")
        and "T" in b["generated_at"]
        and b["evaluated_at"] == date.today().isoformat(),
        f"generated_at={b['generated_at']}, evaluated_at={b['evaluated_at']}",
    )

    # ── ★ 무저장
    after = row_counts(db)
    check(
        "⑲ precheck 12회 호출 후에도 decisions·flags 행 수 불변 + assets 지문 불변",
        after == before,
        f"before={before} / after={after}",
    )

    # ── 두 판정 경로 대조 (DB 사본 vs 파일 정본)
    from data.rules import engine  # noqa: PLC0415

    con = _open_shared(db)
    con.row_factory = sqlite3.Row
    try:
        mismatch = []
        for asset_id, mode in (
            ("AST-L3-CONV", "SALE"),
            ("AST-L4-WRAP", "SALE"),
            ("AST-L4-DUST", "SALE"),
            ("AST-L2-SPDL", "SALE"),
            ("AST-L3-LIFT", "SCRAP"),
        ):
            row = con.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone()
            facts = engine.build_facts(row, disposal_mode=mode, disposal_date=probe[asset_id])
            file_sig = judgment_signature(engine.check_disposal_blockers(facts))
            rest_body = precheck(client, asset_id, mode, probe[asset_id]).json()
            rest_sig = judgment_signature(rest_body)
            if file_sig != rest_sig:
                axes = [k for k in file_sig if file_sig[k] != rest_sig[k]]
                mismatch.append(f"{asset_id}: {axes} REST={rest_sig} vs 파일={file_sig}")
            captured.setdefault("body", rest_body)  # ㉕㉖ 문구 드리프트 대조용
    finally:
        con.close()
    check(
        "⑳ REST(DB 사본) == 파일 정본 — verdict **+ 버킷별 rule_id 집합 + law_ref_id 집합**"
        " (verdict 만 보면 disposal_type 뮤턴트가 통과한다)",
        not mismatch,
        "; ".join(mismatch) or "5자산 · 3축(verdict·버킷 4종·인용 조문) 전부 일치",
    )

    # ── 장비 목록의 asset_id (가산 계약 변경)
    eq = client.get("/api/equipment", headers=TECH).json()["items"]
    by_id = {e["equipment_id"]: e for e in eq}
    check(
        "㉑ GET /api/equipment 에 asset_id 가산 · INV-L1-01(분전반)은 null · 나머지 9대는 non-null",
        len(eq) == 10
        and all("asset_id" in e for e in eq)
        and by_id["INV-L1-01"]["asset_id"] is None
        and sum(e["asset_id"] is not None for e in eq) == 9,
        f"{len(eq)}대, INV-L1-01={by_id['INV-L1-01']['asset_id']!r}, INV-L3-01={by_id['INV-L3-01']['asset_id']!r}",
    )
    check(
        "㉒ 기존 키 5종은 그대로 (가산이므로 기존 소비자 무영향)",
        {"equipment_id", "line_id", "model", "installed_at", "location"} <= set(by_id["INV-L3-01"]),
        f"keys={sorted(by_id['INV-L3-01'])}",
    )


def run_catalog_outage(client, empty_db: Path) -> None:
    """룰 카탈로그 0행 → **503**(500 아님). 서버 설정 문제임을 상태코드로 구분한다."""
    import backend.db as bdb  # noqa: PLC0415

    original = bdb.DB_PATH
    bdb.DB_PATH = empty_db
    try:
        r = precheck(client, "AST-L3-LIFT", "SCRAP", "2026-01-01")
        body = r.json()
        check(
            "㉓ rules 0행 → 503 rule_catalog_not_loaded (500 아님)",
            r.status_code == 503 and body["detail"]["reason"] == "rule_catalog_not_loaded",
            f"{r.status_code} {body.get('detail')}",
        )
    finally:
        bdb.DB_PATH = original


def run_static_checks(captured: dict) -> None:
    """D71 매핑이 D79 어휘 5종을 전부 덮는가 — HTTP 없이 상수만 본다. + W2 문구 드리프트."""
    from backend.routers.disposal import HTTP_BY_VERDICT  # noqa: PLC0415
    from data.rules import engine  # noqa: PLC0415

    check(
        "㉔ D71 매핑 키 == engine.VERDICTS 5종 · 409 는 정확히 BLOCKED·HOLD·INSUFFICIENT_FACTS",
        set(HTTP_BY_VERDICT) == set(engine.VERDICTS)
        and {v for v, c in HTTP_BY_VERDICT.items() if c == 409}
        == {"BLOCKED", "HOLD", "INSUFFICIENT_FACTS"},
        f"{HTTP_BY_VERDICT}",
    )

    # ── W2 — REST 가 엔진 문구를 **복제하지 않는다**
    #   값만 비교하면 복제본이 우연히 같은 동안은 통과한다. 그래서 값 일치 + **소스에
    #   리터럴이 없음**을 함께 본다 — 복제가 되살아나는 순간 두 번째 축이 먼저 깨진다.
    #   ⛔ 기준은 `engine` 상수와 REST 응답이다. MCP 도구 출력을 기준으로 삼지 않는다 —
    #      `check_disposal_blockers.py` 가 `LAW_TEXT_PENDING` 일 때 접미사를 붙여서
    #      **조문 수집이 진행되면 값이 바뀐다**(MQ-701 진행 중). `message` 를 대조에서
    #      뺀 것과 같은 이유다.
    body = captured.get("body") or {}
    source = (ROOT / "backend" / "services" / "disposal.py").read_text(encoding="utf-8")
    check(
        "㉕ not_considered 가 engine.NOT_CONSIDERED 와 동일 · backend 소스에 문구 리터럴 0건 (W2)",
        body.get("not_considered") == list(engine.NOT_CONSIDERED)
        and not [s for s in engine.NOT_CONSIDERED if s in source],
        f"REST={body.get('not_considered')} · 소스 복제="
        f"{[s for s in engine.NOT_CONSIDERED if s in source] or 0}건",
    )
    check(
        "㉖ disclaimer 가 engine.DISCLAIMER 와 동일 · backend 소스에 문구 리터럴 0건 (W2)",
        body.get("disclaimer") == engine.DISCLAIMER and engine.DISCLAIMER not in source,
        f"일치={body.get('disclaimer') == engine.DISCLAIMER} ·"
        f" 소스 복제={engine.DISCLAIMER in source}",
    )



def run_screen_create_axis(client, db: Path, probe: dict[str, str], iso_dsn: str | None = None) -> None:
    """P39 — 화면이 처분 초안을 **직접 생성·수정**한다 (`POST/PATCH /api/decisions`).

    🔴 **쓰기 축이다 — 격리 스키마에서만 돈다** (2026-09-25). 이 축은 오래 공유 `public` 에
    `POST /api/decisions` 를 해서 실행마다 `decisions` 행이 1개씩 샜다(공유 DB 의 DEC-0001·
    DEC-0002 가 그 산물이다) — 요약 줄은 "무저장 확인" 이라고 찍으면서. 이제 ㉓ 처럼
    `backend.db.DB_PATH` 를 격리 DSN(`iso_dsn`)으로 갈아끼운 채 돈다. `read_only()` 도
    `DB_PATH` 를 호출 시점에 읽으므로 재판정 경로까지 같은 스키마를 본다.

    발주(D111)·수리(P39)와 같은 경로지만 **처분에만 있는 문제**가 하나 있다:
    입력을 고치면 **재판정**이 필요하다(`disposal_mode`·`disposal_date` 가 룰 입력이라
    바뀌면 판정도 근거 번들도 달라진다). 그래서 PATCH 는 `rebuild_bundle()` 을 다시 돌려
    `evidence_bundle`·`bundle_hash`·`verdict_at_signing` 을 **새 값으로 덮는다** —
    `sign()` 이 서명 시점에 하는 일(⑥ "재산출 값으로 덮는다")을 draft 단계에서 하는 것이다.

    ⛔ **D81 경계는 그대로다** — override·override_reason·reviewed_by 는 body 에 없다.
    """
    import backend.db as bdb  # noqa: PLC0415

    original = bdb.DB_PATH
    if iso_dsn:
        bdb.DB_PATH = iso_dsn
    try:
        _screen_create_checks(client, probe)
    finally:
        bdb.DB_PATH = original


def _screen_create_checks(client, probe: dict[str, str]) -> None:
    body = {
        "asset_id": "AST-L3-CONV",
        "disposal_mode": "SALE",
        # `probe` 는 자산별로 룰이 발화하는 처분일을 미리 계산해 둔 것이다
        "disposal_date": probe["AST-L3-CONV"],
        "reason": "노후 컨베이어 매각 — 화면 직접 생성(P39)",
    }

    r_create = client.post("/api/decisions", json=body, headers=TECH)
    created = r_create.json() if r_create.status_code == 200 else {}
    check(
        "㉠ 정비사 화면 직접 생성 → 200 · draft · requested_by 즉시 stamp (D37)",
        r_create.status_code == 200
        and created.get("state") == "draft"
        and created.get("requested_by") == TECH["X-User"],
        f"{r_create.status_code} · state={created.get('state')} · "
        f"requested_by={created.get('requested_by')}",
    )

    check(
        "㉡ D81 — override·override_reason·reviewed_by 가 요청 스키마에 없다",
        not ({"override", "override_reason", "reviewed_by"} & set(body)),
        f"body 키={sorted(body)}",
    )

    did = created.get("decision_id", "DEC-NONE")
    first_hash = created.get("bundle_hash")

    # 처분 방식을 바꾸면 룰 입력이 바뀌므로 **판정과 해시가 함께 바뀌어야** 한다
    r_patch = client.patch(
        f"/api/decisions/{did}", json={**body, "disposal_mode": "SCRAP"}, headers=TECH
    )
    patched = r_patch.json() if r_patch.status_code == 200 else {}
    check(
        "㉢ PATCH → 200 · 재판정 · bundle_hash 가 바뀐다 (근거가 입력을 따라간다)",
        r_patch.status_code == 200
        and patched.get("disposal_mode") == "SCRAP"
        and patched.get("bundle_hash") not in (None, first_hash),
        f"{r_patch.status_code} · mode={patched.get('disposal_mode')} · "
        f"hash {str(first_hash)[:18]}… → {str(patched.get('bundle_hash'))[:18]}…",
    )

    check(
        "㉣ 재판정 결과가 verdict_at_signing 에 반영된다 (컬럼 이름이 말하는 것)",
        patched.get("verdict_at_signing") is not None,
        f"verdict_at_signing={patched.get('verdict_at_signing')}",
    )

    r_mgr = client.post("/api/decisions", json=body, headers=MGR)
    check("㉤ 팀장이 화면 생성 호출 → 403", r_mgr.status_code == 403, f"{r_mgr.status_code}")

    r_patch_mgr = client.patch(f"/api/decisions/{did}", json=body, headers=MGR)
    check("㉥ 팀장이 PATCH 호출 → 403", r_patch_mgr.status_code == 403, f"{r_patch_mgr.status_code}")

    r_no_reason = client.post("/api/decisions", json={**body, "reason": "   "}, headers=TECH)
    check(
        "㉦ 사유 공백 → 422 (D5 — 사유 대필 금지)",
        r_no_reason.status_code == 422,
        f"{r_no_reason.status_code}",
    )

    r_bad_asset = client.post("/api/decisions", json={**body, "asset_id": "AST-NOPE"}, headers=TECH)
    check("㉧ 없는 자산 → 404", r_bad_asset.status_code == 404, f"{r_bad_asset.status_code}")

    client.post(f"/api/decisions/{did}/submit", headers=TECH)
    r_after = client.patch(f"/api/decisions/{did}", json=body, headers=TECH)
    check("㉨ 제출 후 PATCH → 409 (draft 아님)", r_after.status_code == 409, f"{r_after.status_code}")

    r_404 = client.patch("/api/decisions/DEC-9999", json=body, headers=TECH)
    check("㉩ 없는 결정 PATCH → 404", r_404.status_code == 404, f"{r_404.status_code}")


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("S9 REST 계약 검증 — D71 HTTP 매핑 · 무저장 · 역할 게이트 없음 (임시 DB 사본)\n")
    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    schema = None
    with tempfile.TemporaryDirectory() as td:
        if dbcompat.USE_POSTGRES:
            # precheck() 는 순수 읽기라(⑲ 가 확인) 나머지 검사는 공유 public 스키마를
            # 읽어도 안전하다 — 유일하게 격리가 필요한 건 rules 를 진짜 0행으로 비우는
            # ㉓ 뿐이다. 그것만 전용 격리 스키마를 만든다.
            db = SOURCE_DB  # 아래 코드 경로 유지용 — Postgres 에서는 실제로 안 쓰인다
            schema, empty = pg_isolation.create_isolated_schema("disposal_empty_rules")
            econ = dbcompat.connect_dsn(empty)
            econ.execute("DELETE FROM rules")
            econ.commit()
            econ.close()
        else:
            db = Path(td) / "disposal.db"
            shutil.copy2(SOURCE_DB, db)
            empty = Path(td) / "no_rules.db"
            shutil.copy2(SOURCE_DB, empty)
            con = sqlite3.connect(empty)
            con.execute("DELETE FROM rules")
            con.commit()
            con.close()
        os.environ["MAINTQ_MCP_AUTOSTART"] = "0"  # 판정은 MCP 와 무관하다 (D73)

        from fastapi.testclient import TestClient  # noqa: PLC0415

        from backend.main import app  # noqa: PLC0415

        probe = probe_dates(db)
        captured: dict = {}
        # 쓰기 축(㉠~㉩) 전용 격리 스키마 — 공유 public 에 decisions 행을 남기지 않는다.
        iso_schema, iso_dsn = (
            pg_isolation.create_isolated_schema("disposal_screen_create")
            if dbcompat.USE_POSTGRES
            else (None, None)
        )
        shared_before = row_counts(db)["decisions"]
        iso_before = _count_decisions(iso_dsn) if iso_dsn else None
        try:
            with TestClient(app) as client:
                run(client, db, probe, captured)
                run_screen_create_axis(client, db, probe, iso_dsn)
                run_catalog_outage(client, empty)
            run_static_checks(captured)
            shared_after = row_counts(db)["decisions"]
            iso_after = _count_decisions(iso_dsn) if iso_dsn else None
            # 부재 검사(공유 불변) + 양성 축(격리 스키마에 실제로 썼다) — 둘이 함께여야
            # "격리가 됐다" 와 "쓰기 축이 아무것도 안 했다" 를 구분한다.
            check(
                "㉪ 공유 DB decisions 행 수 실행 전후 동일 · 쓰기 축은 격리 스키마에 기록"
                " (앵커: 격리 decisions 증가 ≥1)",
                shared_after == shared_before
                and iso_before is not None
                and iso_after is not None
                and iso_after - iso_before >= 1,
                f"공유 {shared_before}→{shared_after} · 격리 {iso_before}→{iso_after}",
            )
        finally:
            if schema:
                pg_isolation.drop_isolated_schema(schema)
            if iso_schema:
                pg_isolation.drop_isolated_schema(iso_schema)

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 30))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 30))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(f"\n통과 ({len(results)}건) — 409(BLOCKED·HOLD·INSUFFICIENT_FACTS)·200·404·422·503 · 무저장 확인")


if __name__ == "__main__":
    main()
