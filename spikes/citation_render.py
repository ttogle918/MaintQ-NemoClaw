# -*- coding: utf-8 -*-
"""MQ-312 — manifest 로더 + 인쇄 페이지 환산 검증 (D19 · D26 · D32 · D49).

검증 질문 (범위: **SSE 경로**만 — REST 경로의 동치 검증은 `spikes/api_contract.py` 참조):
  오프셋 산술이 `manifest.to_print_page()` **한 함수**에만 있고 (D32 —
  SSE 의 `sse.citation_for()` 와 REST 의 `backend.services.po._attach_print_pages()`,
  D57 이 둘 다 이 함수를 호출만 할 뿐 자체 산술을 하지 않는다),
  payload 의 `page` 는 언제나 PDF 물리 원본이며 (D26),
  환산 결과가 1 미만이면 음수를 노출하지 않는가 (D49)?

파일 I/O 는 manifest 읽기뿐이고 DB·네트워크·LLM 을 쓰지 않는다.
폴백 검증은 임시 경로를 MANIFEST_PATH 에 주입해서 하며 `data/raw/` 는 건드리지 않는다.

실행:  uv run python spikes/citation_render.py
"""

from __future__ import annotations

import inspect
import json
import logging
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import manifest, sse  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def data_of(event: sse.SseEvent) -> dict:
    """block 이벤트에서 citation payload 만 꺼낸다."""
    return event.data["data"]


class Capture(logging.Handler):
    """폴백 경로가 실제로 warning 을 남기는지 보기 위한 임시 핸들러."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def run() -> None:
    manifest.reset_cache()

    # ── ① iG5A 는 오프셋 0 — PDF 병기 없이 깔끔한 한 줄
    ev = sse.citation_for("iG5A", 202)
    d = data_of(ev)
    check(
        "① iG5A p.202 → 'iG5A 매뉴얼 p.202'",
        d["label"] == "iG5A 매뉴얼 p.202" and d["page"] == 202 and d["print_page"] == 202,
        f"{d['label']!r} page={d['page']} print_page={d['print_page']}",
    )

    # ── ② S100 은 offset 16 — 인쇄 우선 + PDF 병기 (D32)
    ev = sse.citation_for("S100", 416)
    d = data_of(ev)
    check(
        "② S100 p.416 → 'S100 매뉴얼 p.400 (PDF p.416)'",
        d["label"] == "S100 매뉴얼 p.400 (PDF p.416)"
        and d["page"] == 416
        and d["print_page"] == 400,
        f"{d['label']!r} page={d['page']} print_page={d['print_page']}",
    )

    # ── ③ D49 핵심 — 안전 지침(물리 p.2)에서 음수가 나오면 안 된다
    ev = sse.citation_for("S100", 2)
    d = data_of(ev)
    check(
        "③ S100 p.2 → 음수 없음, print_page==2 (D49)",
        d["label"] == "S100 매뉴얼 p.2" and d["print_page"] == 2 and d["page"] == 2,
        f"{d['label']!r} print_page={d['print_page']}",
    )

    # ── ④ payload 의 page 는 항상 물리 원본 (D26) — 인용률 판정 기준
    cases = [("iG5A", 4), ("iG5A", 202), ("S100", 2), ("S100", 16), ("S100", 17), ("S100", 416)]
    got = {(m, p): data_of(sse.citation_for(m, p))["page"] for m, p in cases}
    check(
        "④ payload page 는 항상 PDF 물리 원본 (D26)",
        all(got[(m, p)] == p for m, p in cases),
        f"{ {f'{m} p.{p}': v for (m, p), v in got.items()} }",
    )

    # ── ⑤ model enum 강제 (D6 · D13)
    errs = []
    for fn, args in (
        (sse.citation_for, ("iS7", 100)),
        (manifest.to_print_page, ("iS7", 100)),
        (manifest.manual_label, ("iS7",)),
        (manifest.print_page_offset, ("s100",)),  # 대소문자도 enum 밖
    ):
        try:
            fn(*args)
            errs.append(f"{fn.__name__}{args} 가 통과됨")
        except ValueError:
            pass
    check("⑤ model='iS7' → ValueError (D6·D13)", not errs, f"{errs or 'ValueError 4/4'}")

    # ── ⑥ 기존 citation_block 하위 호환 — chat.py 가 아직 이 형태로 호출 중
    sig = list(inspect.signature(sse.citation_block).parameters)
    legacy = sse.citation_block("iG5A 매뉴얼", page=202, print_page=202)
    check(
        "⑥ 기존 citation_block 직접 호출 유지 (하위 호환)",
        sig == ["manual", "page", "print_page", "section"]
        and data_of(legacy)["label"] == "iG5A 매뉴얼 p.202"
        and legacy.data["type"] == "citation",
        f"signature={sig}",
    )

    # ── ⑦ payload 키는 {page, print_page, label} 정확히 (D32 · 06_REPO_API §SSE)
    d = data_of(sse.citation_for("S100", 416))
    check(
        "⑦ payload 키 = {page, print_page, label} (D32)",
        set(d) == {"page", "print_page", "label"} and ev.event == "block",
        f"{sorted(d)}",
    )

    # ── ⑧ 오프셋 경계 — offset 만큼의 페이지까지는 환산하지 않는다 (D49)
    b16, b17 = manifest.to_print_page("S100", 16), manifest.to_print_page("S100", 17)
    check(
        "⑧ D49 경계: S100 p.16→16(미적용) / p.17→1",
        b16 == 16 and b17 == 1,
        f"p.16→{b16}, p.17→{b17}",
    )

    # ── ⑨ manifest 가 오프셋의 단일 원천인가 (D19) — 파일 값과 코드 값 대조
    raw = json.loads((ROOT / "data" / "raw" / "manifest.json").read_text(encoding="utf-8"))
    primary = {
        m["model"]: m["print_page_offset"] for m in raw["manuals"] if m.get("role") == "primary"
    }
    check(
        "⑨ 오프셋 원천은 manifest.json (D19)",
        all(manifest.print_page_offset(k) == v for k, v in primary.items()),
        f"manifest={primary} / 코드={ {m: manifest.print_page_offset(m) for m in manifest.MODELS} }",
    )

    # ── ⑩ section 은 라벨에만 붙고 payload 스키마를 늘리지 않는다
    d = data_of(sse.citation_for("S100", 416, "8.2 보호 기능"))
    check(
        "⑩ section 은 라벨에만 반영",
        d["label"].endswith("· 8.2 보호 기능") and set(d) == {"page", "print_page", "label"},
        f"{d['label']!r}",
    )

    # ── ⑪ manifest 부재 폴백 — offset 0 + warning, 인용은 계속 나간다
    handler = Capture()
    lg = logging.getLogger("backend.manifest")
    prev_level, prev_prop = lg.level, lg.propagate
    lg.setLevel(logging.WARNING)  # basicConfig(CRITICAL) 로 warning 이 막히지 않도록
    lg.propagate = False  # 콘솔에는 안 찍고 여기서만 받는다
    lg.addHandler(handler)
    original = manifest.MANIFEST_PATH
    try:
        with tempfile.TemporaryDirectory() as tmp:
            manifest.MANIFEST_PATH = Path(tmp) / "없는_manifest.json"
            manifest.reset_cache()
            d = data_of(sse.citation_for("S100", 416))
            fallback_ok = d["page"] == 416 and d["print_page"] == 416
            warned = any("manifest" in m for m in handler.messages)

            # 모델 미등록(파일은 있으나 목록에 없음)도 같은 폴백
            partial = Path(tmp) / "partial.json"
            partial.write_text(
                json.dumps(
                    {"manuals": [{"model": "iG5A", "role": "primary", "print_page_offset": 0}]}
                ),
                encoding="utf-8",
            )
            manifest.MANIFEST_PATH = partial
            manifest.reset_cache()
            handler.messages.clear()
            d2 = data_of(sse.citation_for("S100", 416))
            missing_ok = d2["print_page"] == 416 and any("S100" in m for m in handler.messages)
    finally:
        manifest.MANIFEST_PATH = original
        manifest.reset_cache()
        lg.removeHandler(handler)
        lg.setLevel(prev_level)
        lg.propagate = prev_prop

    check(
        "⑪ manifest 부재/모델 미등록 → offset 0 폴백 + warning",
        fallback_ok and warned and missing_ok,
        f"부재={fallback_ok}/warn={warned}, 미등록={missing_ok}",
    )

    # ── ⑫ 캐시: 같은 경로는 1회만 읽고 동일 객체를 돌려준다
    first = manifest.load_manifest()
    check(
        "⑫ load_manifest 1회 캐시",
        manifest.load_manifest() is first and len(first["manuals"]) == 3,
        f"동일 객체, manuals={len(first['manuals'])}건",
    )

    # ── ⑬ 물리 페이지 정합성 — 0/음수 페이지는 조용히 통과시키지 않는다
    bad = []
    for page in (0, -3):
        try:
            manifest.to_print_page("S100", page)
            bad.append(page)
        except ValueError:
            pass
    check("⑬ page < 1 은 ValueError", not bad, f"{bad or '0·-3 모두 거부'}")


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("MQ-312 — manifest 로더 + 인쇄 페이지 환산 (D19·D26·D32·D49)\n")
    logging.basicConfig(level=logging.CRITICAL)  # 폴백 warning 이 콘솔을 어지럽히지 않도록
    run()

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 46))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 46))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[MQ-312 실패] {len(failed)}건: {', '.join(failed)}")
    print(
        f"\nMQ-312 통과 ({len(results)}건) — 오프셋 산술은 to_print_page 1함수"
        "(SSE·REST 공유, D57), page 는 물리 원본"
    )


if __name__ == "__main__":
    main()
