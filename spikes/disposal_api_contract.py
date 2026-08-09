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

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


TECH = {"X-Role": "technician", "X-User": "tech-01"}
MGR = {"X-Role": "manager", "X-User": "mgr-01"}


def row_counts(db: Path) -> dict[str, int]:
    """무저장 증명용 — 판정 경로가 건드릴 수 있는 테이블의 행 수 + assets 지문."""
    con = sqlite3.connect(db)
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


def probe_dates(db: Path) -> dict[str, str]:
    """`acquired_at + DISPOSAL_PROBE_MONTHS` — 시드가 만든 규칙을 그대로 재사용한다."""
    sys.path.insert(0, str(ROOT))
    from data.seed import DISPOSAL_PROBE_MONTHS, _shift_months  # noqa: PLC0415

    con = sqlite3.connect(db)
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


def precheck(client, asset_id: str, mode: str, when: str | None = None, headers=None):
    body: dict = {"disposal_mode": mode}
    if when is not None:
        body["disposal_date"] = when
    return client.post(
        f"/api/assets/{asset_id}/disposal/precheck", json=body, headers=headers or TECH
    )


def run(client, db: Path, probe: dict[str, str]) -> None:
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

    con = sqlite3.connect(db)
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
            file_verdict = engine.check_disposal_blockers(facts)["verdict"]
            rest_verdict = precheck(client, asset_id, mode, probe[asset_id]).json()["verdict"]
            if file_verdict != rest_verdict:
                mismatch.append(f"{asset_id}: REST={rest_verdict} vs 파일={file_verdict}")
    finally:
        con.close()
    check(
        "⑳ REST(DB 사본) 판정 == engine.check_disposal_blockers(파일 정본) — 두 벌이 어긋나면 여기서 잡힌다",
        not mismatch,
        "; ".join(mismatch) or "5자산 일치",
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


def run_static_checks() -> None:
    """D71 매핑이 D79 어휘 5종을 전부 덮는가 — HTTP 없이 상수만 본다."""
    from backend.routers.disposal import HTTP_BY_VERDICT  # noqa: PLC0415
    from data.rules import engine  # noqa: PLC0415

    check(
        "㉔ D71 매핑 키 == engine.VERDICTS 5종 · 409 는 정확히 BLOCKED·HOLD·INSUFFICIENT_FACTS",
        set(HTTP_BY_VERDICT) == set(engine.VERDICTS)
        and {v for v, c in HTTP_BY_VERDICT.items() if c == 409}
        == {"BLOCKED", "HOLD", "INSUFFICIENT_FACTS"},
        f"{HTTP_BY_VERDICT}",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("S9 REST 계약 검증 — D71 HTTP 매핑 · 무저장 · 역할 게이트 없음 (임시 DB 사본)\n")
    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "disposal.db"
        shutil.copy2(SOURCE_DB, db)
        empty = Path(td) / "no_rules.db"
        shutil.copy2(SOURCE_DB, empty)
        con = sqlite3.connect(empty)
        con.execute("DELETE FROM rules")
        con.commit()
        con.close()

        os.environ["MAINTQ_DB"] = str(db)
        os.environ["MAINTQ_MCP_AUTOSTART"] = "0"  # 판정은 MCP 와 무관하다 (D73)

        sys.path.insert(0, str(ROOT))
        from fastapi.testclient import TestClient  # noqa: PLC0415

        from backend.main import app  # noqa: PLC0415

        probe = probe_dates(db)
        with TestClient(app) as client:
            run(client, db, probe)
            run_catalog_outage(client, empty)
        run_static_checks()

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
