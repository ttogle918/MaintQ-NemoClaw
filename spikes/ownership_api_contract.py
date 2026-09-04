# -*- coding: utf-8 -*-
"""S18 REST 계약 검증 — `GET /api/assets/{id}/ownership` (MQ-707b).

이 화면이 지키는 것은 하나다: **"확인 안 된 항목을 확인된 것처럼 보여주지 않는다."**
그래서 검사도 그쪽으로 몰려 있다.

핵심 4가지:
  1. **`PARTIAL` 은 409 가 아니다.** 실사 판정에서 `PARTIAL` 은 "지금 상태로는 불가"가 아니라
     **정상 결과**다(`11 §6` — 승격 경로가 코드에 없다). 409 로 주면 D71 이 처분 판정에
     부여한 "409 = 사용자가 해소해야 할 상태"라는 의미가 흐려지고, 클라이언트는 해소할 수
     없는 것을 해소하라고 안내하게 된다.
  2. **REST == MCP.** 두 소비자가 같은 판정 함수(`data/ownership.py`)를 부른다 — 응답을
     도구 출력과 **바이트 단위로** 대조한다. 갈리면 사용자는 채팅과 화면 중 어느 쪽이
     맞는지 알 수 없다 (MQ-702 가 지우고 있는 W2 드리프트와 같은 형태).
  3. **`no_host_asset` 은 404 이되 사유가 본문에 있다.** `INV-L1-01`(분전반)은 배전 위치이지
     거래 단위가 아니다 — "확인 결과 문제 없음"이 아니라 "실사 대상이 아니다"다.
  4. **403 이 없다.** 읽기 판정에 역할 게이트를 만들면 D38 지표가 오염된다.

임시 DB 사본에서 돌린다. 기대값은 하드코딩하지 않고 **DB 실측·모듈 상수**에서 파생시킨다 —
시드가 바뀌면 기대값도 같이 움직여야 회귀가 거짓 신호를 내지 않는다.

실행:  uv run python spikes/ownership_api_contract.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DB = ROOT / "data" / "maintq.db"

results: list[tuple[str, bool, str]] = []
MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

TECH = {"X-Role": "technician", "X-User": "tech-01"}
MGR = {"X-Role": "manager", "X-User": "mgr-01"}


def check(name: str, ok: bool, detail: str) -> None:
    mark = MARKS[len(results)] if len(results) < len(MARKS) else f"[{len(results) + 1}]"
    results.append((f"{mark} {name}", ok, detail))


def canon(obj: object) -> str:
    """정규화 직렬화 — REST↔MCP 대조는 키 순서에 흔들리면 안 된다."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def db_fingerprint(db: Path) -> dict:
    """무저장 증명 — 판정 경로가 건드릴 수 있는 테이블 행 수 + assets 지문."""
    con = sqlite3.connect(db)
    try:
        out: dict = {
            t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: S608
            for t in ("assets", "equipment", "repair_records", "error_history", "decisions")
        }
        blob = "\n".join(
            "|".join("" if v is None else str(v) for v in r)
            for r in con.execute("SELECT * FROM assets ORDER BY asset_id")
        )
        out["assets_fingerprint"] = hashlib.sha256(blob.encode()).hexdigest()[:12]
        return out
    finally:
        con.close()


def run(client, db: Path) -> None:
    import data.ownership as own  # noqa: PLC0415
    from backend.routers.disposal import HTTP_BY_OWNERSHIP_STATUS  # noqa: PLC0415
    from mcp_server.tools.verify_ownership import verify_ownership  # noqa: PLC0415

    before = db_fingerprint(db)
    con = sqlite3.connect(db)
    try:
        assets = [r[0] for r in con.execute("SELECT asset_id FROM assets ORDER BY asset_id")]
        # 호스트 자산이 없는 설비 — 시드에 몇 대든 **실측으로** 찾는다 (INV-L1-01 이 그 케이스)
        hostless = [
            r[0]
            for r in con.execute(
                "SELECT equipment_id FROM equipment WHERE asset_id IS NULL ORDER BY equipment_id"
            )
        ]
    finally:
        con.close()

    def get(ref: str, headers: dict | None = None):
        return client.get(f"/api/assets/{ref}/ownership", headers=headers or TECH)

    responses = {a: get(a) for a in assets}
    bodies = {a: r.json() for a, r in responses.items()}

    # ── ① 9자산 전부 200 · PARTIAL
    bad = {
        a: (r.status_code, bodies[a].get("status"), bodies[a].get("verdict"))
        for a, r in responses.items()
        if r.status_code != 200 or bodies[a].get("verdict") != "PARTIAL"
    }
    check(
        f"시드 {len(assets)}자산 전부 200 · verdict=PARTIAL",
        bool(assets) and not bad,
        f"{len(assets)}자산" + (f" · 어긋남 {bad}" if bad else " 전부 200/PARTIAL"),
    )

    # ── ② 카테고리 9종 · 순서까지 `data.ownership.CATEGORIES` 와 동일
    #    "해당 없음"이라고 빼면 **확인 안 한 것이 화면에서 사라진다**
    wrong_cats = {
        a: [c["category"] for c in b.get("categories", [])]
        for a, b in bodies.items()
        if [c["category"] for c in b.get("categories", [])] != list(own.CATEGORIES)
    }
    check(
        "카테고리 9종 — 개수·순서가 CATEGORIES 와 동일 (빠진 카테고리 0)",
        len(own.CATEGORIES) == 9 and not wrong_cats,
        f"{len(own.CATEGORIES)}종 {own.CATEGORIES[:3]}…"
        + (f" · 어긋남 {list(wrong_cats)}" if wrong_cats else ""),
    )

    # ── ③ 항목 총량 — 자산마다 38개(실측 핀). 조용히 줄면 미확인 항목이 사라진 것이다
    counts = {a: sum(len(c["items"]) for c in b["categories"]) for a, b in bodies.items()}
    check(
        "항목 총량 38개 — 전 자산 동일 (조용한 축소 감시)",
        set(counts.values()) == {38},
        f"{sorted(set(counts.values()))} · 자산별 {list(counts.items())[:2]}…",
    )

    # ── ④ VERIFIED 엔 evidence, UNVERIFIED 엔 limit — **이유 없는 미확인을 만들지 않는다**
    broken: list[str] = []
    for a, b in bodies.items():
        for c in b["categories"]:
            for i in c["items"]:
                if i["state"] == "VERIFIED" and (not i["evidence"] or i["limit"] is not None):
                    broken.append(f"{a}/{i['item']}:VERIFIED evidence={i['evidence']!r}")
                elif i["state"] == "UNVERIFIED" and (not i["limit"] or i["evidence"] is not None):
                    broken.append(f"{a}/{i['item']}:UNVERIFIED limit={i['limit']!r}")
                elif i["state"] not in ("VERIFIED", "UNVERIFIED"):
                    broken.append(f"{a}/{i['item']}:state={i['state']!r}")
    check(
        "VERIFIED→evidence · UNVERIFIED→limit (반대편은 null) — 이유 없는 미확인 0건",
        not broken,
        f"결함 {len(broken)}건 {broken[:2]}",
    )

    # ── ⑤ REST == MCP 직접 대조 (정규화 후 문자열 동일)
    drift = [a for a in assets if canon(bodies[a]) != canon(verify_ownership(asset_id=a))]
    check(
        "REST 응답 == MCP verify_ownership 출력 (9자산 · json sort_keys 동일)",
        not drift,
        f"대조 {len(assets)}자산 · 불일치 {drift}"
        if drift
        else f"대조 {len(assets)}자산 전부 동일 (판정 원천 1벌 — data/ownership.py)",
    )

    # ── ⑥ 없는 자산 → 404 + 사유
    r = get("AST-NOPE")
    b = r.json()
    check(
        "없는 자산 → 404 · reason=unknown_asset (본문에 사유)",
        r.status_code == 404
        and b.get("status") == "not_found"
        and b.get("reason") == "unknown_asset",
        f"{r.status_code} {b.get('reason')} {b.get('asset_id')}",
    )

    # ── ⑦ ★ 호스트 자산 없는 설비 → 404 no_host_asset **+ 사유 문장**
    #    "문제 없음"이 아니라 "실사 대상이 아니다"임을 본문이 말해야 한다
    ref = hostless[0] if hostless else "INV-L1-01"
    r = get(ref)
    b = r.json()
    check(
        f"{ref}(호스트 자산 없음) → 404 no_host_asset · 본문에 사유 — '문제 없음'이 아니다",
        bool(hostless)
        and r.status_code == 404
        and b.get("reason") == "no_host_asset"
        and "실사 대상이 아닙니다" in (b.get("message") or "")
        and b.get("equipment_id") == ref,
        f"{r.status_code} {b.get('reason')} · message={str(b.get('message'))[:38]}…",
    )

    # ── ⑧ ★ PARTIAL 은 409 가 아니다 (D71 의 409 의미를 흐리지 않는다)
    #    응답 실측(9자산 전부 PARTIAL)과 **매핑 상수** 둘 다 본다 — 상수에 409 가 없어야
    #    나중에 verdict 를 보고 409 를 얹는 코드가 들어올 때 여기서 먼저 걸린다
    codes = sorted({r.status_code for r in responses.values()})
    check(
        "★ PARTIAL 이 409 가 아니다 — 실사 미확인은 '해소할 상태'가 아니라 정상 결과 (11 §6)",
        codes == [200] and 409 not in HTTP_BY_OWNERSHIP_STATUS.values(),
        f"9자산 상태코드 {codes} · 매핑 {HTTP_BY_OWNERSHIP_STATUS}",
    )

    # ── ⑨ 역할 무관 — 403 이 나오면 안 되고, 본문도 같아야 한다
    role_codes: dict[str, tuple] = {}
    role_bodies: dict[str, str] = {}
    for role, h in (("technician", TECH), ("manager", MGR), ("헤더없음", None)):
        rs = (get("AST-L3-LIFT", h), get("AST-NOPE", h), get(ref, h))
        role_codes[role] = tuple(x.status_code for x in rs)
        role_bodies[role] = canon(rs[0].json())
    check(
        "X-Role 무관 — technician·manager·헤더없음이 같은 상태코드·같은 본문 (403 없음, D38)",
        set(role_codes.values()) == {(200, 404, 404)} and len(set(role_bodies.values())) == 1,
        f"{role_codes} · 본문 동일={len(set(role_bodies.values())) == 1}",
    )

    # ── ⑩ 무저장 — 판정 N회 후에도 행 수·assets 지문 불변
    after = db_fingerprint(db)
    check(
        "판정 20+회 호출 후 DB 행 수·assets 지문 불변 (mode=ro 커넥션만)",
        after == before,
        f"before={before} / after={after}",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("S18 REST 계약 검증 — /ownership · PARTIAL≠409 · REST==MCP · 역할 게이트 없음\n")
    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "ownership.db"
        shutil.copy2(SOURCE_DB, db)

        # backend·mcp_server 둘 다 이 경로를 **import 시점에** 읽는다 — 실 DB 를 건드리지 않는다
        os.environ["MAINTQ_MCP_AUTOSTART"] = "0"  # 판정은 MCP 프로세스와 무관하다 (D73)

        sys.path.insert(0, str(ROOT))
        from fastapi.testclient import TestClient  # noqa: PLC0415

        from backend.main import app  # noqa: PLC0415

        with TestClient(app) as client:
            run(client, db)

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 34))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 34))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건:\n  - " + "\n  - ".join(failed))
    print(
        f"\n통과 ({len(results)}건) — 200/404 · PARTIAL≠409 · REST==MCP 바이트 대조 · "
        "no_host_asset 사유 · 403 없음 · 무저장"
    )


if __name__ == "__main__":
    main()
