# -*- coding: utf-8 -*-
"""MQ-1906 — RAG jsonl ∪ DB, 기종 단위 원천 선택 계약 (D148, docs/sprints/sprint-19.md).

`mcp_server/rag.py` 는 jsonl 에 그 기종 청크가 1건이라도 있으면 **DB 를 조회하지 않는다**
(D60 파일 정본 보호) — jsonl 에 0건인 기종만 `manual_chunks`(D117 §24, 온보딩 승격분)를
본다. 이 스파이크가 고정하는 것 셋:

  ⓘ    **바이트 동일** — 기존 3기종(iG5A·S100·IE5)의 검색 결과는 `manual_chunks` 의 내용과
       **무관**해야 한다(그 기종 청크가 jsonl 에 이미 있으므로). DB 에 HV600 청크를 채우고
       iG5A 로 라벨링된 불량 행을 심어도 결과가 **문자열째 동일**해야 한다 — D148 결정록 ④가
       우려한 "합치면 iG5A 검색 모수·IDF 가 바뀐다" 회귀가 구조적으로 성립하지 않음을 증명한다.
  ⓘⓘ   HV600 은 DB 가 0건이면 `error/index_not_built`(메시지에 「승격 전」, D146 — empty 아님,
       D50 논리)이고, DB 에 승격분이 들어오면 즉시(재시작 없이) 히트한다. 한국어 질의로
       실제 히트하고 `page` 는 원문 물리 페이지 그대로다(D145·D26).
  ⓘⓘⓘ  DB 행의 `chunk_id` 가 jsonl 의 것과 충돌하면 **파일이 이긴다**(D148 ⓘⓘⓘ, D60) —
       그 행은 결과에서 빠지고 경고가 정확히 1회 남는다. 나머지 DB 행은 그대로 히트한다
       (앵커 — "충돌 행 제외" 만 보면 로더가 전부 버려도 통과하므로 나머지가 살아있음을 함께 본다).

④ 실 인덱스 축: `data/extracted/manual_chunks.jsonl`(1,229청크, .gitignore 대상)이 있으면
같은 ⓘ 비교(바이트 동일)를 실 파일로 1회 더 한다. 없으면 SKIPPED 로 건수와 함께 인쇄한다
(`spikes/ie5_extract_contract.py` 선례 — PDF 없을 때 SKIPPED 로 계속 진행).

픽스처(`spikes/fixtures/onboarding_chunks.jsonl`)는 **합성 문장**이다(D144) — 실제 iG5A·
S100·IE5 매뉴얼 문장을 복제하지 않는다. HV600 "DB 승격분" 도 이 스파이크가 격리 스키마에
직접 INSERT 하는 합성 문장이며, 실 DB에는 아무것도 쓰지 않는다(격리 스키마는 실행 후 DROP).

DB 를 쓰는 검사는 전부 `data/pg_isolation.create_isolated_schema()` 격리 스키마에서만
돈다 — 공유 `public` 을 건드리지 않는다.

실행:
  DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" \
  uv run python spikes/onboarding_rag_contract.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data import dbcompat, pg_isolation  # noqa: E402
from mcp_server import db as db_mod  # noqa: E402

# 코퍼스·질의 임베딩이 실 API 를 타면(키가 있으면) 결정론이 깨진다 — 이 스파이크는
# 키워드 경로만으로 결정론을 증명하려는 것이라 명시적으로 끈다(D47 이 정의한 dense=None
# 과 동등한 상태, mcp_server/dense_scorer.py:75 의 조용한 폴백을 그대로 유도).
os.environ.pop("NVIDIA_API_KEY", None)

FIXTURE = ROOT / "spikes" / "fixtures" / "onboarding_chunks.jsonl"
REAL_INDEX = ROOT / "data" / "extracted" / "manual_chunks.jsonl"

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, "PASS" if ok else "FAIL", detail))


def skip(name: str, detail: str) -> None:
    results.append((name, "SKIP", detail))


def reload_tool():
    """MAINTQ_CHUNKS·mcp_server.db.DB_PATH 를 바꾼 뒤 모듈을 새로 읽어들인다
    (`spikes/rag_contract.py::reload_tool` 과 같은 방식 — `INDEX_PATH` 가 import 시점
    상수라 재적재해야 반영된다)."""
    for mod in ("mcp_server.tools.rag_search_manual", "mcp_server.rag"):
        sys.modules.pop(mod, None)
    from mcp_server.tools.rag_search_manual import rag_search_manual  # noqa: PLC0415

    return rag_search_manual


# 3기종(iG5A·S100·IE5) × 2질의 — 전부 픽스처에서 ≥1건 히트하도록 사전 실측했다.
FIXED_QUERIES = [
    ("iG5A", "누전 점검 절차"),
    ("iG5A", "냉각팬 소음"),
    ("S100", "트립 복귀 절차"),
    ("S100", "절연저항 측정"),
    ("IE5", "진단 절차 확인"),
    ("IE5", "배선 점검"),
]

# ④ 실 인덱스 축 — 1,229청크 실 코퍼스에서 사전 실측으로 ≥1건 히트를 확인한 질의.
# 질의 자체는 이 도메인의 일반 용어(점검·트립·과열 등)이며 매뉴얼 문장을 복제하지 않는다
# (D144 — rag_contract.py 의 기존 실 인덱스 질의와 같은 성격).
REAL_QUERIES = [
    ("iG5A", "지락 점검"),
    ("iG5A", "냉각 팬"),
    ("S100", "트립 점검"),
    ("S100", "절연 저항"),
    ("IE5", "과열 원인"),
    ("IE5", "점검 절차"),
]

# 합성 HV600 "온보딩 승격분" — 실 HV600 매뉴얼 문장이 아니다(D144). page 는 D145 가 서술한
# HV600 고장 표 물리 페이지대(107~124)를 흉내낸 자리표시자일 뿐 실측값이 아니다.
_HV600_ROWS = [
    (
        "syn-hv600-c1", "syn-hv600-manual", "HV600", 107, "가상 고장",
        "가상 HV600 지락 원인은 절연 저하이며 접지선을 점검한다.",
    ),
    (
        "syn-hv600-c2", "syn-hv600-manual", "HV600", 108, "가상 고장",
        "가상 HV600 과전류 원인은 부하 급증이며 전류계로 점검한다.",
    ),
    (
        "syn-hv600-c3", "syn-hv600-manual", "HV600", 109, "가상 고장",
        "가상 HV600 과열 원인은 냉각팬 정지이며 방열판을 점검한다.",
    ),
]

_BAD_IG5A_ROW = (
    "syn-ig5a-DBJUNK-99", "syn-ig5a-manual-DB", "iG5A", 999, "DB 불량행",
    "이 텍스트는 DB 에만 있고 jsonl 에는 없다 — 결과에 섞이면 회귀다.",
)


def _insert_manual_chunks(con, rows: list[tuple]) -> None:
    for chunk_id, manual_id, model, page, section, text in rows:
        con.execute(
            "INSERT INTO manual_chunks"
            " (chunk_id, manual_id, model, page, section, text, char_len)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chunk_id, manual_id, model, page, section, text, len(text)),
        )
    con.commit()


def _run(tool, queries: list[tuple[str, str]]) -> dict[str, dict]:
    return {f"{model}::{query}": tool(model=model, query=query, top_k=5) for model, query in queries}


def _all_hit(batch: dict[str, dict]) -> bool:
    return all(r.get("status") == "ok" and r.get("chunks") for r in batch.values())


class _CaptureWarnings(logging.Handler):
    """`mcp_server.rag` 로거의 warning 을 가로챈다 (D148 ⓘⓘⓘ 경고 1회 검증용)."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record.getMessage())


def _run_isolated_checks() -> None:
    schema, dsn = pg_isolation.create_isolated_schema("onboarding_rag", clone_data=False)
    db_mod.DB_PATH = dsn
    os.environ["MAINTQ_CHUNKS"] = str(FIXTURE)

    handler = _CaptureWarnings()
    logging.getLogger("mcp_server.rag").addHandler(handler)

    try:
        tool = reload_tool()

        # ── 상태 (a): manual_chunks 격리 스키마 — HV600 0행 ──────────────────
        before = _run(tool, FIXED_QUERIES)
        anchor_a = _all_hit(before)
        check(
            "ⓘ-anchor 기존 3기종 6질의 전부 히트 (DB 상태 (a), HV600 0행)",
            anchor_a,
            f"{ {k: v.get('status') for k, v in before.items()} }",
        )

        hv600_a = tool(model="HV600", query="지락 원인", top_k=3)
        check(
            "ⓘⓘ(a) HV600 승격 전 → error/index_not_built, 메시지에 「승격 전」 (D146·D50)",
            hv600_a.get("status") == "error"
            and hv600_a.get("reason") == "index_not_built"
            and "승격 전" in hv600_a.get("message", ""),
            f"{hv600_a}",
        )

        # ── 상태 (b): HV600 3행 승격 + iG5A 라벨 불량행 1건 심기 ──────────────
        con = dbcompat.connect_dsn(dsn)
        try:
            _insert_manual_chunks(con, _HV600_ROWS)
            _insert_manual_chunks(con, [_BAD_IG5A_ROW])
        finally:
            con.close()

        after = _run(tool, FIXED_QUERIES)
        check(
            "ⓘ 바이트 동일 — 기존 3기종 6질의 결과가 DB 상태 (a)/(b) 사이 완전 일치",
            anchor_a
            and json.dumps(before, sort_keys=True, ensure_ascii=False)
            == json.dumps(after, sort_keys=True, ensure_ascii=False),
            f"동일={before == after}",
        )

        hv600_b = tool(model="HV600", query="지락 원인", top_k=3)
        pages_b = [c["page"] for c in hv600_b.get("chunks", [])]
        check(
            "ⓘⓘ(b) HV600 승격 후 → 히트 ≥1 · 한국어 질의 · page=원문 물리 페이지(D145·D26)",
            hv600_b.get("status") == "ok" and len(pages_b) >= 1 and pages_b[0] == 107,
            f"status={hv600_b.get('status')}, pages={pages_b}",
        )

        # ── 상태 (c): 충돌 — HV600 행 1건의 chunk_id 를 jsonl 과 동일하게 ────────
        handler.records.clear()
        con = dbcompat.connect_dsn(dsn)
        try:
            con.execute(
                "UPDATE manual_chunks SET chunk_id = ? WHERE chunk_id = ?",
                ("syn-ig5a-p0100-00", "syn-hv600-c1"),
            )
            con.commit()
        finally:
            con.close()

        hv600_c = tool(model="HV600", query="지락 원인", top_k=3)
        pages_c = [c["page"] for c in hv600_c.get("chunks", [])]
        check(
            "ⓘⓘⓘ 충돌 — chunk_id 충돌 행 제외(파일 우선, D148·D60) + 경고 1회 + 나머지 히트",
            hv600_c.get("status") == "ok"
            and 107 not in pages_c
            and len(pages_c) == 2
            and len(handler.records) == 1,
            f"pages={pages_c}, 경고 {len(handler.records)}건: {handler.records}",
        )
    finally:
        logging.getLogger("mcp_server.rag").removeHandler(handler)
        db_mod.DB_PATH = None
        pg_isolation.drop_isolated_schema(schema)


def _run_real_index_axis() -> None:
    if not REAL_INDEX.exists():
        skip(
            "④ 실 인덱스 축 (바이트 동일, 1,229청크)",
            "data/extracted/manual_chunks.jsonl 없음 (.gitignore 대상, 실측 데이터 미보유)",
        )
        return

    os.environ.pop("MAINTQ_CHUNKS", None)
    schema, dsn = pg_isolation.create_isolated_schema("onboarding_rag_real", clone_data=False)
    db_mod.DB_PATH = dsn
    try:
        tool = reload_tool()

        before = _run(tool, REAL_QUERIES)
        anchor = _all_hit(before)

        con = dbcompat.connect_dsn(dsn)
        try:
            _insert_manual_chunks(con, _HV600_ROWS)
            _insert_manual_chunks(con, [_BAD_IG5A_ROW])
        finally:
            con.close()

        after = _run(tool, REAL_QUERIES)
        check(
            "④ 실 인덱스 축 — 기존 3기종 실 질의 결과가 DB 상태 (a)/(b) 사이 완전 일치",
            anchor
            and json.dumps(before, sort_keys=True, ensure_ascii=False)
            == json.dumps(after, sort_keys=True, ensure_ascii=False),
            f"동일={before == after}",
        )
    finally:
        db_mod.DB_PATH = None
        os.environ.pop("MAINTQ_CHUNKS", None)
        pg_isolation.drop_isolated_schema(schema)


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("RAG jsonl ∪ DB — 기종 단위 원천 선택 계약 검증 (D148)\n")

    if not dbcompat.USE_POSTGRES:
        check(
            "전체 (DB 격리 스키마 검사)",
            False,
            "DATABASE_URL 미설정 — Postgres 격리 스키마는 Postgres 타겟에서만 쓴다",
        )
    else:
        _run_isolated_checks()
        _run_real_index_axis()

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 46))
    for name, status, detail in results:
        print(f"  {status:<4}  {name:<{width}}  {detail}")
    print("─" * (width + 46))

    failed = [n for n, s, _ in results if s == "FAIL"]
    skipped = [n for n, s, _ in results if s == "SKIP"]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(
        f"\n통과 (전체 {len(results)}건 = PASS {len(results) - len(skipped)} · "
        f"SKIPPED {len(skipped)}) — D148 기종 단위 원천 선택 · D146 승격 전 게이트 · "
        "D60 파일 정본 보호 확인."
    )


if __name__ == "__main__":
    main()
