# -*- coding: utf-8 -*-
"""lookup_error_code 계약 검증 (docs/04_MCP_TOOLS.md §1).

검증 대상: D13(복합키) · D25(정규화·case-insensitive) · D26(물리 페이지 무가공) ·
          D20(related_parts) · D9(실패는 status) · **D50(0행이면 catalog_not_loaded)**

**합성 픽스처 3행만 쓴다.** `data/extracted/error_codes.json` 을 읽어 넣지 않는다 —
그건 사람 승인 게이트(TODO_직접할일.md)를 코드로 우회하는 것이고, 승인 전 매핑이
회귀 테스트의 기준값이 되면 나중에 승인 결과와 어긋나도 아무도 모른다.
실 DB(`data/maintq.db`)의 **내용**(causes·actions 등)은 읽지 않는다 — 임시 DB 3종만 만든다.

⚠ **예외 1건(⑭, D100)** — `actions_source` 의 실 DB 병합 상태는 합성 픽스처로는
  증명할 수 없다(픽스처는 우리가 만든 것이라 "정확히 이 3건만 병합됐다"의 증거가
  못 된다). 그래서 이 검사만 실 DB 를 **읽기 전용**으로 열되, `model`·`code`·
  `actions_manual_id` 의 NULL 여부와 행 수만 본다 — `causes`·`actions` 등 승인 게이트
  대상 **내용**(조치문 문장)은 여전히 건드리지 않는다. MQ-919(2026-08-17) 가 승인 3건
  (iG5A `RERR`·`ETB`, S100 `FANW`)을 정본에 병합했으므로 이 검사는 "전건 null" 이 아니라
  "그 3건만 채워지고 나머지 67건은 null" 을 확인한다(Sprint 15 MQ-1507 IE5 5건 병합 후
  65→70건 — 그중 IE5 5건도 actions_manual_id 는 채워지지 않아 null 축에 합류한다).

실행:  uv run python spikes/lookup_contract.py
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data import dbcompat, pg_isolation  # noqa: E402
from mcp_server import db as db_mod  # noqa: E402
from mcp_server.tools.lookup_error_code import lookup_error_code  # noqa: E402

_pg_schemas: list[str] = []  # 만든 격리 스키마 — main() 끝에서 한꺼번에 정리

# data/seed.py 의 error_codes DDL 과 같은 제약 (D25 대문자 canonical · D33 코드 형식).
# seed.py 는 MQ-301 이 수정 중이라 import 하지 않고 스키마만 여기서 복제한다.
DDL = """
CREATE TABLE error_codes (
  model        TEXT NOT NULL,
  code         TEXT NOT NULL,
  display_code TEXT,
  error_name   TEXT NOT NULL,
  severity     TEXT NOT NULL,
  causes       TEXT NOT NULL,
  actions      TEXT NOT NULL,
  related_parts TEXT,
  manual_page  INTEGER NOT NULL,
  actions_manual_id TEXT,
  actions_page      INTEGER,
  PRIMARY KEY (model, code),
  CHECK (severity IN ('warning','fault','critical')),
  CHECK (length(code) BETWEEN 2 AND 4
         AND code = upper(code)
         AND code NOT GLOB '*[^A-Z0-9_]*'),
  CHECK ((actions_manual_id IS NULL) = (actions_page IS NULL))
);
"""

# 합성 픽스처 — iG5A/OHT 와 S100/OHT 는 **같은 코드 다른 의미**(D13 복합키 검증용).
# 값은 매뉴얼 추출본이 아니라 이 테스트용으로 지어낸 것이다.
FIXTURE = [
    (
        "iG5A",
        "OHT",
        "OHt",
        "인버터 과열",
        "warning",
        '["냉각팬 고장", "주위 온도 초과"]',
        '["냉각팬 점검", "주위 온도 확인"]',
        '["FAN-IG5-01"]',
        202,
        None,
        None,
    ),
    (
        "iG5A",
        "OCT",
        "OCt",
        "출력 과전류",
        "fault",
        '["출력측 지락"]',
        '["출력 배선 점검"]',
        None,
        203,
        None,
        None,
    ),
    (
        "S100",
        "OHT",
        "oht",
        "방열판 과열(S100 정의)",
        "critical",
        '["방열판 오염"]',
        '["방열판 청소"]',
        "[]",
        30,
        None,
        None,
    ),
]

CONTRACT_KEYS = {
    "status",
    "code",
    "display_code",
    "error_name",
    "severity",
    "causes",
    "actions",
    "related_parts",
    "manual_page",
    "actions_source",
}

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def make_db(path: Path, rows: list[tuple]):
    """`rows` 만 든 격리 DB 를 만든다. Postgres 는 격리 스키마(빈 상태로 시작 —
    clone_data=False, D50 의 '0행' 을 확실히 보장한다), SQLite 는 임시 파일이다."""
    if dbcompat.USE_POSTGRES:
        schema, dsn = pg_isolation.create_isolated_schema("lookup", clone_data=False)
        _pg_schemas.append(schema)
        if rows:
            con = dbcompat.connect_dsn(dsn)
            con.executemany("INSERT INTO error_codes VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
            con.commit()
            con.close()
        return dsn

    con = sqlite3.connect(path)
    con.executescript(DDL)
    con.executemany("INSERT INTO error_codes VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return path


def use(path: Path) -> None:
    """read_only() 가 보는 DB 경로를 갈아끼운다 (mcp_server/db.py 는 건드리지 않는다)."""
    db_mod.DB_PATH = path


def run(tmp: Path) -> None:
    loaded = make_db(tmp / "loaded.db", FIXTURE)
    empty = make_db(tmp / "empty.db", [])
    if dbcompat.USE_POSTGRES:
        # "DB 파일이 없다"의 Postgres 대응 — 도달 불가능한 DSN (짧은 connect_timeout 으로
        # 확실히·빨리 실패하게 한다. trace_persist.py 의 같은 트릭 참고).
        missing = "postgresql://postgres:postgres@127.0.0.1:59999/no_such_db?connect_timeout=2"
    else:
        missing = tmp / "no-such.db"

    # ── ① D6·D13: model enum 강제. 미지원 기종이 조용히 통과하면 안 된다
    use(loaded)
    bad_model = lookup_error_code(model="iS7", code="OHt")
    check(
        "① model enum 강제 (iS7 거부)",
        bad_model["status"] == "error" and "iG5A" in bad_model.get("message", ""),
        f"status={bad_model['status']}, msg={bad_model.get('message', '')[:34]}",
    )

    # ── ② 정상 조회 + 계약 키 (D20 related_parts 포함)
    ok = lookup_error_code(model="iG5A", code="OHt")
    check(
        "② 정상 조회 + D20 related_parts",
        ok["status"] == "ok"
        and ok["error_name"] == "인버터 과열"
        and ok["related_parts"] == ["FAN-IG5-01"]
        and isinstance(ok["causes"], list)
        and isinstance(ok["actions"], list),
        f"name={ok.get('error_name')}, related={ok.get('related_parts')}",
    )

    # ── ③ D25: 입력 표기가 뭐든 같은 행. code 는 대문자 canonical, display_code 는 원표기
    variants = [lookup_error_code(model="iG5A", code=c) for c in ("oht", " OHT ", "OhT")]
    check(
        "③ D25 case-insensitive + canonical/display 분리",
        all(v["status"] == "ok" for v in variants)
        and {v["code"] for v in variants} == {"OHT"}
        and {v["display_code"] for v in variants} == {"OHt"},
        "'oht'·' OHT '·'OhT' → code=OHT / display_code=OHt (입력 반향 아님)",
    )

    # ── ④ D13: 같은 코드, 다른 의미 — 복합키가 실제로 갈라내는가
    ig5a = lookup_error_code(model="iG5A", code="OHT")
    s100 = lookup_error_code(model="S100", code="OHT")
    check(
        "④ D13 복합키 (같은 코드 다른 의미)",
        ig5a["error_name"] != s100["error_name"]
        and s100["severity"] == "critical"
        and s100["display_code"] == "oht",
        f"iG5A={ig5a['error_name']} / S100={s100['error_name']}",
    )

    # ── ⑤ D26: manual_page 는 PDF 물리 페이지 그대로. 오프셋(+16) 환산 흔적이 없어야 한다
    check(
        "⑤ D26 manual_page 무가공 (환산 금지)",
        ig5a["manual_page"] == 202 and s100["manual_page"] == 30,
        f"iG5A p.{ig5a['manual_page']}, S100 p.{s100['manual_page']} (픽스처 값 그대로)",
    )

    # ── ⑥ ★D50: 0행은 not_found 가 아니다. not_found 면 모든 코드가 S4 로 흘러 지표가 가짜 100%
    use(empty)
    zero = lookup_error_code(model="iG5A", code="OHt")
    check(
        "⑥ D50 0행 → error/catalog_not_loaded",
        zero["status"] == "error" and zero.get("reason") == "catalog_not_loaded",
        f"status={zero['status']}, reason={zero.get('reason')}",
    )

    # ── ⑦ D9: DB 파일이 없어도 예외가 아니라 status
    use(missing)
    nodb = lookup_error_code(model="iG5A", code="OHt")
    check(
        "⑦ D9 DB 없음 → 예외 아닌 status:error",
        nodb["status"] == "error" and nodb.get("reason") == "db_error",
        f"status={nodb['status']}, reason={nodb.get('reason')}",
    )

    # ── ⑧ 빈 code → status:error (조회 자체가 성립 안 함)
    use(loaded)
    nocode = lookup_error_code(model="iG5A", code="   ")
    check(
        "⑧ code 누락 → status:error",
        nocode["status"] == "error" and nocode.get("reason") == "code_required",
        f"status={nocode['status']}, reason={nocode.get('reason')}",
    )

    # ── ⑨ ★적재됐는데 없는 코드는 not_found. ⑥과 실제로 갈리는지 + 유사 코드 추측 없음
    unknown = lookup_error_code(model="iG5A", code="XY9")
    guessed = [c for c in ("OHT", "OCT", "OHt", "OCt") if c in unknown.get("message", "")]
    check(
        "⑨ 적재 후 미지 코드 → not_found (유사 코드 추측 없음)",
        unknown["status"] == "not_found"
        and unknown["code"] == "XY9"
        and not guessed
        and not ({"alternatives", "suggestions", "did_you_mean"} & set(unknown)),
        f"status={unknown['status']}, 추측 노출={guessed or '없음'}",
    )

    # ── ⑩ 계약 외 키를 흘리지 않는다 (04 §1 출력 스키마 그대로)
    check(
        "⑩ ok 응답 키가 계약과 동일",
        set(ok) == CONTRACT_KEYS,
        f"초과={sorted(set(ok) - CONTRACT_KEYS) or '없음'}, 누락={sorted(CONTRACT_KEYS - set(ok)) or '없음'}",
    )

    # ── ⑪ 같은 질의 2회 동일 결과 (평가 재현성)
    check(
        "⑪ 결정론 (같은 질의 2회 동일)",
        lookup_error_code(model="iG5A", code="OHt") == ok,
        "동일 dict",
    )

    # ── ⑬ D100 — actions_source 키가 ok 응답 **전건**에 존재 (⑩은 단일 샘플만 봤다).
    #    Stage 4 가 픽스처 3행 모두에 (actions_manual_id, actions_page)=(None, None) 을 넣었으므로
    #    합성 픽스처에서는 전부 null 이어야 한다 — 값 자체보다 **키가 빠지지 않는지**가 핵심이다.
    all_fixture = [
        lookup_error_code(model=m, code=c)
        for m, c in (("iG5A", "OHT"), ("iG5A", "OCT"), ("S100", "OHT"))
    ]
    check(
        "⑬ D100 actions_source 키가 픽스처 전 3행 응답에 존재 · 값은 null (합성 DB)",
        all("actions_source" in r for r in all_fixture)
        and all(r["actions_source"] is None for r in all_fixture),
        f"키 존재={['actions_source' in r for r in all_fixture]} · "
        f"값={[r.get('actions_source') for r in all_fixture]}",
    )


def real_db_actions_source_check(real_db: Path) -> None:
    """⑭ D100 — **실 DB** 병합 상태 실측 대조 (MQ-919 병합 후).

    ⛔ 승인 게이트 대상 **내용**(causes·actions 텍스트 등)은 읽지 않는다 — `model`·`code`·
    `actions_manual_id` 는 구조 컬럼(어느 코드가 병합됐는지)이지 조치문 **문장** 자체가
    아니므로 이 파일의 격리 원칙(합성 픽스처만 실사용값의 기준으로 삼는다)을 어기지 않는다.

    이전 버전은 "전건 null" 을 봤다(병합 전). 승인 4건(iG5A RERR·ETB·NTC, S100 FANW)이 정본에
    병합된 지금 그 검사를 그대로 두면 **위양성 FAIL** 한다 — 그래서 **실측 대조**로 바꾼다:
    채워진 행이 정확히 그 4건인지(양성 축) + 나머지는 여전히 null인지(음성 축)를 함께 본다.
    (`iG5A NTC` 는 2026-08-29 사람이 위임 반려를 뒤집어 승인한 건 — 기계 판정은 STILL_AMBIGUOUS)
    """
    expected_filled = {("iG5A", "RERR"), ("iG5A", "ETB"), ("S100", "FANW"), ("iG5A", "NTC")}
    if dbcompat.USE_POSTGRES:
        con = dbcompat.connect_dsn(pg_isolation.BASE_DATABASE_URL)
    else:
        con = sqlite3.connect(f"file:{real_db.as_posix()}?mode=ro", uri=True)
    try:
        total = con.execute("SELECT count(*) FROM error_codes").fetchone()[0]
        filled_rows = con.execute(
            "SELECT model, code FROM error_codes WHERE actions_manual_id IS NOT NULL"
        ).fetchall()
        null_count = con.execute(
            "SELECT count(*) FROM error_codes WHERE actions_manual_id IS NULL"
        ).fetchone()[0]
    finally:
        con.close()
    filled_keys = {(m, c) for m, c in filled_rows}
    check(
        "⑭ D100 실 DB — actions_source(actions_manual_id) 실측 대조 "
        "(정본 병합 MQ-919 3건 + iG5A NTC 사람 승인 1건 = 4건만 채워짐)",
        filled_keys == expected_filled and null_count == 66 and total > 0,
        f"[양성] 채워짐={sorted(filled_keys)}(기대 {sorted(expected_filled)}) · "
        f"[음성] null={null_count}건(기대 66) · rows={total}(기대 70)",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print(
        "lookup_error_code 계약 검증 — 임시 DB + 합성 픽스처 3행 "
        "(실 DB 는 ⑭ 한 곳만 읽기 전용으로 구조만 본다)\n"
    )
    real_db = ROOT / "data" / "maintq.db"
    if not dbcompat.USE_POSTGRES and not real_db.exists():
        raise SystemExit(f"[중단] {real_db} 가 없습니다 — data/seed.py 를 먼저 실행하세요")
    if dbcompat.USE_POSTGRES:
        _con = dbcompat.connect_dsn(pg_isolation.BASE_DATABASE_URL)
        before = _con.execute("SELECT count(*) FROM error_codes").fetchone()[0]
        _con.close()
    else:
        before = (real_db.stat().st_mtime_ns, real_db.stat().st_size)

    try:
        with tempfile.TemporaryDirectory() as td:
            run(Path(td))

        real_db_actions_source_check(real_db)
    finally:
        for schema in _pg_schemas:
            pg_isolation.drop_isolated_schema(schema)

    if dbcompat.USE_POSTGRES:
        _con = dbcompat.connect_dsn(pg_isolation.BASE_DATABASE_URL)
        after = _con.execute("SELECT count(*) FROM error_codes").fetchone()[0]
        _con.close()
        check(
            "⑫ 실 DB(공유 Postgres) error_codes 행수 불변 — ⑭ 는 SELECT 만",
            before == after,
            f"{'불변' if before == after else f'{before} → {after}'}",
        )
    else:
        after = (real_db.stat().st_mtime_ns, real_db.stat().st_size)
        check(
            "⑫ 실 DB mtime·size 불변 (⑭ 는 mode=ro 로 열어 SELECT 만 — 쓰기 없음)",
            before == after,
            f"{'불변' if before == after else f'{before} → {after}'}",
        )

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 46))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 46))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(
        f"\n통과 ({len(results)}건) — D13·D20·D25·D26·D50 준수. "
        "iG5A 매핑 승인 완료(2026-07-28) — 실데이터는 계속 합성 픽스처로 격리 검증"
        "(승인 결과가 회귀 기준값이 되는 걸 막기 위해, MQ-310 원칙과 동일)"
    )


if __name__ == "__main__":
    main()
