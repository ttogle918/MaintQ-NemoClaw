# -*- coding: utf-8 -*-
"""rag_search_manual 계약 검증 (MQ-314) — docs/04_MCP_TOOLS.md §2.

핵심은 셋이다:
  **D53** 반환 text 가 원본 청크와 완전히 동일한가 (절단 금지 — 절차 문단이 중간에서
         끊기면 에이전트가 뒷부분을 지어낸다)
  **D26** page 가 무가공 PDF 물리 페이지인가 (인용률 판정이 이 값을 traces 와 대조)
  **미구축 ≠ empty** 인덱스가 없을 때 empty 를 주면 "매뉴얼에 없다"는 잘못된 신호가 된다

합성 인덱스로 돈다 — `MAINTQ_CHUNKS` 로 갈아끼워 실 인덱스(1,229청크 — iG5A 표준본 342 +
iG5A 트러블슈팅 44 + S100 649 + IE5 194, D110)를 건드리지 않는다.
실 인덱스는 마지막 두 케이스에서만 읽기 전용으로 확인한다.

실행:  uv run python spikes/rag_contract.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


# 절단이 일어나는지 보려면 400자를 넘는 청크가 있어야 한다 (기존 상한이 400자였다)
LONG_TEXT = (
    "출력측 지락이 의심되면 먼저 인버터 출력 단자 U·V·W 의 배선을 분리하고 "
    "절연저항계로 각 상과 접지 사이의 절연저항을 측정한다. " * 12
)

FIXTURE = [
    {
        "chunk_id": "ig5a-manual-p0204-00",
        "manual_id": "ig5a-manual",
        "model": "iG5A",
        "page": 204,
        "section": "12.2 고장 대책",
        "text": LONG_TEXT,
        "char_len": len(LONG_TEXT),
    },
    {
        "chunk_id": "ig5a-manual-p0202-00",
        "manual_id": "ig5a-manual",
        "model": "iG5A",
        "page": 202,
        "section": "12.1 보호 기능",
        "text": "과열 보호는 냉각팬 이상이나 주위 온도 상승에서 동작한다. 지락 점검은 별도 절차다.",
        "char_len": 44,
    },
    {
        "chunk_id": "s100-manual-p0416-00",
        "manual_id": "s100-manual",
        "model": "S100",
        "page": 416,
        "section": "9.1 트립",
        "text": "S100 출력측 지락 트립은 접지 절연 상태를 확인한 뒤 복귀시킨다.",
        "char_len": 36,
    },
]


def write_index(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def reload_tool():
    """MAINTQ_CHUNKS 를 바꾼 뒤 모듈을 새로 읽어들인다."""
    for mod in ("mcp_server.tools.rag_search_manual", "mcp_server.rag"):
        sys.modules.pop(mod, None)
    from mcp_server.tools.rag_search_manual import rag_search_manual  # noqa: PLC0415

    return rag_search_manual


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("rag_search_manual 계약 검증 (합성 인덱스)\n")

    with tempfile.TemporaryDirectory() as td:
        idx = Path(td) / "chunks.jsonl"
        write_index(idx, FIXTURE)
        os.environ["MAINTQ_CHUNKS"] = str(idx)
        tool = reload_tool()

        # ── ① model 필터
        r = tool(model="iG5A", query="출력측 지락 점검 절차", top_k=5)
        pages = [c["page"] for c in r.get("chunks", [])]
        check(
            "① model 필터 — iG5A 질의에 S100 청크 없음",
            r["status"] == "ok" and 416 not in pages,
            f"status={r['status']}, pages={pages}",
        )

        # ── ② 결정론
        r2 = tool(model="iG5A", query="출력측 지락 점검 절차", top_k=5)
        check("② 같은 질의 2회 → 동일 결과", r == r2, "완전 일치")

        # ── ③ 계약 키 3개뿐 (score·chunk_id 노출 금지)
        keys = {k for c in r["chunks"] for k in c}
        check(
            "③ 청크 키가 text/page/section 뿐 (score 없음)",
            keys == {"text", "page", "section"},
            f"{sorted(keys)}",
        )

        # ── ④ ★ D53 — 절단 없음
        top = r["chunks"][0]
        original = next(f["text"] for f in FIXTURE if f["page"] == top["page"])
        check(
            "④ D53 text 무절단 (원본과 완전 동일)",
            top["text"] == original and len(top["text"]) > 400,
            f"{len(top['text'])}자 · 원본 {len(original)}자 · 동일={top['text'] == original}",
        )

        # ── ⑤ D26 page 무가공
        check(
            "⑤ D26 page 는 물리 페이지 정수 무가공",
            all(isinstance(c["page"], int) for c in r["chunks"]) and 204 in pages,
            f"pages={pages}",
        )

        # ── ⑥ 매칭 0건 → empty
        r3 = tool(model="iG5A", query="냉장고 컴프레서 가스 충전", top_k=3)
        check(
            "⑥ 매칭 없음 → empty (error 아님)",
            r3["status"] == "empty" and r3["chunks"] == [],
            f"status={r3['status']}",
        )

        # ── ⑦ model enum
        bad = tool(model="iS7", query="점검", top_k=3)
        check(
            "⑦ model enum 강제",
            bad["status"] == "error" and bad.get("reason") == "invalid_model",
            f"reason={bad.get('reason')}",
        )

        # ── ⑧ query 누락
        noq = tool(model="iG5A", query="   ", top_k=3)
        check(
            "⑧ query 필수",
            noq["status"] == "error" and noq.get("reason") == "query_required",
            f"reason={noq.get('reason')}",
        )

        # ── ⑨ ★ 인덱스 미구축 ≠ empty
        os.environ["MAINTQ_CHUNKS"] = str(Path(td) / "does-not-exist.jsonl")
        tool2 = reload_tool()
        miss = tool2(model="iG5A", query="지락 점검", top_k=3)
        check(
            "⑨ 인덱스 미구축 → error/index_not_built (empty 아님)",
            miss["status"] == "error" and miss.get("reason") == "index_not_built",
            f"status={miss['status']}, reason={miss.get('reason')}",
        )

        # ── ⑩ 빈 인덱스도 미구축으로 (empty 와 섞이면 안 된다)
        empty_idx = Path(td) / "empty.jsonl"
        empty_idx.write_text("", encoding="utf-8")
        os.environ["MAINTQ_CHUNKS"] = str(empty_idx)
        tool3 = reload_tool()
        er = tool3(model="iG5A", query="지락 점검", top_k=3)
        check(
            "⑩ 빈 인덱스 → error (empty 와 구분)",
            er["status"] == "error" and er.get("reason") == "index_not_built",
            f"reason={er.get('reason')}",
        )

        # ── ⑪ top_k 상한
        os.environ["MAINTQ_CHUNKS"] = str(idx)
        tool4 = reload_tool()
        many = tool4(model="iG5A", query="지락 점검 절차 절연", top_k=999)
        check(
            "⑪ top_k 과대 입력도 안전",
            many["status"] in ("ok", "empty") and len(many.get("chunks", [])) <= 10,
            f"status={many['status']}, {len(many.get('chunks', []))}건",
        )

    # ── ⑫ 실 인덱스 (읽기 전용)
    os.environ.pop("MAINTQ_CHUNKS", None)
    real = ROOT / "data" / "extracted" / "manual_chunks.jsonl"
    if real.exists():
        before = real.stat().st_mtime_ns
        tool5 = reload_tool()
        rr = tool5(model="iG5A", query="OCt 출력측 지락 점검 절차", top_k=3)
        ok = rr["status"] == "ok" and all(
            isinstance(c["page"], int) and c["text"] for c in rr["chunks"]
        )
        check(
            "⑫ 실 인덱스 검색 + 파일 불변",
            ok and real.stat().st_mtime_ns == before,
            f"status={rr['status']}, {len(rr.get('chunks', []))}건, "
            f"pages={[c['page'] for c in rr.get('chunks', [])]}",
        )

        # ── ⑬ ★ D110 — IE5 실 인덱스 검색 (RAG 대상 편입 확인)
        before2 = real.stat().st_mtime_ns
        ie5 = tool5(model="IE5", query="냉각핀 과열 원인", top_k=3)
        n_hits = len(ie5.get("chunks", []))
        check(
            "⑬ D110 IE5 실 인덱스 검색 + 파일 불변",
            ie5["status"] == "ok"
            and n_hits > 0  # 양성 축 — 상태만 ok 인 것으로는 부족하다 (CLAUDE.md 부재검사 규칙)
            and all(isinstance(c["page"], int) and c["text"] for c in ie5["chunks"])
            and real.stat().st_mtime_ns == before2,
            f"status={ie5['status']}, {n_hits}건, "
            f"pages={[c['page'] for c in ie5.get('chunks', [])]}",
        )
    else:
        check("⑫ 실 인덱스 검색", False, "manual_chunks.jsonl 없음 — chunk_manual.py 먼저 실행")
        check("⑬ D110 IE5 실 인덱스 검색", False, "manual_chunks.jsonl 없음 — chunk_manual.py 먼저 실행")

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 44))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 44))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(
        f"\n통과 ({len(results)}건) — D53 무절단 · D26 page 무가공 · 미구축≠empty · "
        "D110 IE5 실 인덱스 검색 확인"
    )


if __name__ == "__main__":
    main()
