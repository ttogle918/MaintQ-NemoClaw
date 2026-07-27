# -*- coding: utf-8 -*-
"""시스템 프롬프트·안전 상수 정적 검사 (MQ-303 DoD).

**LLM 을 호출하지 않는다.** 여기서 보는 건 "모델이 잘 따르는가"가 아니라
**"규칙과 기준값이 프롬프트에 실제로 들어 있는가"** 다. 문구가 조용히 사라지거나
방전 대기 기준값이 축소되면(safety-guardrail 규칙 3) 여기서 먼저 깨진다.

실행:  uv run python spikes/prompt_rules.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.agent.prompts import (  # noqa: E402
    DANGER_KEYWORDS,
    MODELS,
    RULES,
    SAFETY_BASELINE,
    SAFETY_SOURCES,
    SYSTEM_PROMPT,
    build_system_prompt,
    needs_safety_block,
)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def _has_key(obj: object, key: str) -> bool:
    """중첩 dict/list 안에 key 가 하나라도 있으면 True."""
    if isinstance(obj, dict):
        return key in obj or any(_has_key(v, key) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_has_key(v, key) for v in obj)
    return False


def run() -> None:
    prompt = build_system_prompt("iG5A", equipment_id="INV-L3-01")
    safety_text = str(SAFETY_BASELINE["text"])

    # ── ① 규칙 11개가 전부 있는가 (개수 + 근거 결정 태그)
    tags = ("D1", "D5", "D12", "D28", "D35", "A2", "A6", "D31", "D23", "D6", "D13", "D46", "D30")
    missing_tags = [t for t in tags if t not in SYSTEM_PROMPT]
    check(
        "① 규칙 11개 + 결정 태그 전건 존재",
        len(RULES) == 11 and not missing_tags,
        f"RULES={len(RULES)}, 누락 태그={missing_tags or '없음'}",
    )

    # ── ② 방전 대기 기준값 — "10분 이상" 필수 / "5분" 금지 (사람 승인 2026-07-18)
    ok_10 = "10분 이상" in safety_text and "10분 이상" in prompt
    no_5 = "5분" not in safety_text and "5분" not in prompt
    check(
        "② 기준값 '10분 이상' 포함 · '5분' 미포함",
        ok_10 and no_5,
        f"10분이상={ok_10}, 5분부재={no_5}",
    )

    # ── ③ 근거 페이지는 PDF 물리 페이지 그대로 (D26). 환산 금지
    pages = SAFETY_BASELINE["pages"]
    check(
        "③ pages = 물리 페이지 (iG5A 4 / S100 2)",
        pages == {"iG5A": 4, "S100": 2},
        f"{pages}",
    )

    # ── ④ print_page 키 부재 — 환산 소유자는 MQ-312 뿐 (D32·D49)
    check(
        "④ SAFETY_BASELINE 에 print_page 키 없음",
        not _has_key(SAFETY_BASELINE, "print_page"),
        "중첩 포함 재귀 검사",
    )

    # ── ⑤ model enum 강제 (D6·D13) — 폴백 없이 ValueError
    try:
        build_system_prompt("iS7")
        raised = False
    except ValueError:
        raised = True
    both_ok = all(build_system_prompt(m).endswith("이 값을 쓴다") for m in MODELS)
    check(
        "⑤ build_system_prompt('iS7') → ValueError, enum 2종은 통과",
        raised and both_ok and tuple(MODELS) == ("iG5A", "S100"),
        f"ValueError={raised}, MODELS={MODELS}",
    )

    # ── ⑥ S4 환각 금지 (D5·D50)
    check(
        "⑥ 미지 코드 추측 금지 + not_found/catalog_not_loaded 구분",
        "추측" in prompt and "not_found" in prompt and "catalog_not_loaded" in prompt,
        "추측 금지 · 미적재는 별도 안내",
    )

    # ── ⑦ A2 — 견적 턴에서 발주하지 않는다
    check(
        "⑦ A2 '다음 턴' 발주 규칙",
        "다음 턴" in prompt and "create_po_draft" in prompt,
        "견적 제시 턴 자동 호출 금지",
    )

    # ── ⑧ A6·D31 — MOQ 임의 상향 금지
    check(
        "⑧ MOQ 미달 시 임의 상향 금지",
        "moq_not_met" in prompt and "상향" in prompt and "MOQ" in prompt,
        "도구 거부 후 사용자 재확인",
    )

    # ── ⑨ D23·D31·D37 — 신원·단가 지어내기 금지
    check(
        "⑨ 신원(requested_by)·단가(unit_price) 지어내기 금지",
        "requested_by" in prompt and "unit_price" in prompt and "도구 파라미터가 아니" in prompt,
        "서버 주입 — LLM 위조 경로 차단",
    )

    # ── ⑩ D46 — 타임아웃·연결 실패 공백을 지식으로 메우지 않는다 (규칙 10 추가분)
    check(
        "⑩ 타임아웃/실패는 '확인하지 못했다'로 명시",
        "확인하지 못했다" in prompt and "timeout" in prompt and "메우지 마라" in prompt,
        "09_RUNTIME §3 원칙",
    )

    # ── ⑪ 안전 문구 창작 금지 + 인용은 시스템 생성 (D26·D30·D32)
    check(
        "⑪ 안전 문구 창작 금지 · 페이지 인용은 시스템이 생성",
        "창작하지 마라" in prompt
        and "페이지 번호를 네가 문장에 적지" in prompt
        and "인쇄 페이지 환산도 하지" in prompt,
        "safety-guardrail 규칙 1 · D32",
    )

    # ── ⑫ D1 도구 경계 — 정의=lookup / 절차=RAG
    check(
        "⑫ D1 경계: 정의는 lookup, 절차는 rag_search_manual",
        "lookup_error_code" in prompt
        and "rag_search_manual" in prompt
        and "코드 정의를 RAG 로 찾지" in prompt,
        "경계를 흐리는 문구 없음",
    )

    # ── ⑬ S2·S3 분기 (D20·D28·D35·A8)
    check(
        "⑬ S2 compat_confirmed 분기 · S3 hold 보류 블록",
        "compat_confirmed" in prompt and "hold" in prompt and "repeated" in prompt,
        "보류는 po_card variant",
    )

    # ── ⑭ 안전 문구의 매뉴얼 근거가 상수로 남아 있는가 (safety-guardrail 규칙 1)
    src_pages = {(s["model"], s["page"]) for s in SAFETY_SOURCES}
    # 기종별로 "10분 이상"을 명시한 원문이 최소 1건 있어야 기준값이 근거를 갖는다
    baseline_quoted = {
        m
        for m in MODELS
        for s in SAFETY_SOURCES
        if s["model"] == m and "10분 이상" in str(s["quote"])
    }
    check(
        "⑭ SAFETY_SOURCES 에 매뉴얼 원문·페이지 기록",
        {("iG5A", 4), ("S100", 2)} <= src_pages
        and baseline_quoted == set(MODELS)
        and all(str(s["quote"]).strip() for s in SAFETY_SOURCES),
        f"{len(SAFETY_SOURCES)}건, 기준값 원문 보유={sorted(baseline_quoted)}",
    )

    # ── ⑮ 위험 키워드 판정 (safety-guardrail 규칙 2) — MQ-306 이 쓰는 헬퍼
    # "방열핀…이물질"·"냉각팬…확인"은 실 Gemini 스모크(C-5, 2026-07-27)에서 안전 블록
    # 없이 통과했던 실측 문장 유형이다 — 키워드를 줄이면 여기서 다시 잡힌다 (★ 음성).
    check(
        "⑮ needs_safety_block — 위험 키워드 감지 (내부 작업 확장 + 띄어쓰기 정규화)",
        needs_safety_block("커버를 열고 단자대 절연 측정을 진행합니다")
        and needs_safety_block("방열핀에 이물질이 끼어 있는지 확인하십시오")
        and needs_safety_block("인버터 냉각팬이 정상 동작하는지 확인하십시오")
        # 실 Gemini 스모크(C-5)에서 게이트를 통과했던 실측 변주 — 띄어쓰기·외래어
        and needs_safety_block("냉각 팬 및 히트싱크 점검을 진행하십시오")
        and not needs_safety_block("에러 이력을 조회했습니다")
        and "활선" in DANGER_KEYWORDS,
        f"키워드 {len(DANGER_KEYWORDS)}종",
    )

    # ── ⑯ 기종 미확정이면 확인 질문 (D6·D13 + S1 1단계)
    unknown = build_system_prompt(None, equipment_id=None)
    check(
        "⑯ model=None → '미확정' + 확인 질문 지시",
        "미확정" in unknown and "확인하는 질문" in unknown,
        "폴백으로 한쪽 기종을 고르지 않음",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("MQ-303 — 시스템 프롬프트·안전 상수 정적 검사 (LLM 호출 없음)\n")
    run()

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 46))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 46))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(f"\n통과 ({len(results)}건) — 규칙 11개 · '10분 이상' 기준값 · 물리 페이지 유지 확인")


if __name__ == "__main__":
    main()
