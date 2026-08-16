# -*- coding: utf-8 -*-
"""시스템 프롬프트·안전 상수 정적 검사 (MQ-303 DoD · MQ-612 확장).

**LLM 을 호출하지 않는다.** 여기서 보는 건 "모델이 잘 따르는가"가 아니라
**"규칙과 기준값이 프롬프트에 실제로 들어 있는가"** 다. 문구가 조용히 사라지거나
방전 대기 기준값이 축소되면(safety-guardrail 규칙 3) 여기서 먼저 깨진다.

MQ-612 가 더한 것 (⑰~㉑, D69) · MQ-706 이 더한 것 (㉒㉓):
  - 확장 규칙 4개(12·13·14·15)는 **전제 도구가 실제로 등록됐을 때만** 붙는다
  - `prompts.py` 는 `MAINTQ_TOOLS_PROFILE` 을 **읽지 않는다** — env 를 바꿔도 출력이
    바뀌지 않음을 실제로 확인한다. 등록(자식 프로세스)과 지시(백엔드)가 같은 env 를
    각자 해석하면 어긋나기 때문이다
  - 규칙 번호는 **위치로 고정** — 확장 도구가 일부만 등록돼도 번호가 밀리지 않는다

실행:  uv run python spikes/prompt_rules.py
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ★ DoD — **env 를 설정하지 않은 상태**에서 개수 고정을 본다.
#
# 다만 셸에 `MAINTQ_TOOLS_PROFILE=full` 이 export 돼 있다고 **FAIL 시키지 않는다.**
# 데모·평가 세션에서 그 값을 export 한 채 회귀를 돌리는 일이 실제로 있고, 그때 나는
# 빨간 줄은 결함이 아니라 **환경 잡음**이다 — 잡음에 무뎌지면 진짜 실패도 같이 흘려보낸다.
# 그래서 여기서 **직접 걷어내고(pop) 그 사실을 detail 에 남긴다.** 프롬프트 모듈은 이
# 값을 애초에 읽지 않으므로(⑳ 이 그것을 증명한다) 걷어내도 검사 대상은 달라지지 않는다.
_ENV_AT_IMPORT = os.environ.pop("MAINTQ_TOOLS_PROFILE", None)

from backend.agent.prompts import (  # noqa: E402
    CORE_TOOLS,
    DANGER_KEYWORDS,
    EXT_RULES,
    EXT_TOOLS,
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

    # ─────────────────────────────────────────────────────────────────────────
    # MQ-612 (D69) — 도구 프로파일과 프롬프트의 분리
    # ─────────────────────────────────────────────────────────────────────────

    # ── ⑰ 개수 고정 — **env 미설정 상태**에서 규칙 11 + 확장 4
    #
    # ★ MQ-706: 새 규칙 15(`generate_disposal_document`)를 `RULES` 가 아니라 `EXT_RULES` 에
    #   넣었다. sprint-7 MQ-706 DoD 는 `len(RULES)==12` 라고 적었으나, 그러면 **코어 프로파일
    #   프롬프트에 `full` 전용 도구의 사용법이 실린다** — 같은 DoD 의 "tool_names=CORE_7 일 때
    #   0건 누출"과 양립할 수 없다(㉒ 가 그 누출을 직접 본다). 규칙 총량은 11+4=15 로 늘었다.
    env_note = (
        "env 미설정"
        if _ENV_AT_IMPORT is None
        else f"env {_ENV_AT_IMPORT!r} 를 스파이크 진입 시 제거함(검사 대상 아님)"
    )
    check(
        "⑰ env 미설정 상태에서 RULES 11개 · EXT_RULES 4개 고정 (D69)",
        len(RULES) == 11
        and len(EXT_RULES) == 4
        and os.environ.get("MAINTQ_TOOLS_PROFILE") is None
        and len(CORE_TOOLS) == 7
        and len(EXT_TOOLS) == 9,
        f"RULES={len(RULES)} EXT_RULES={len(EXT_RULES)} "
        f"CORE={len(CORE_TOOLS)} EXT={len(EXT_TOOLS)} · {env_note}",
    )

    # ── ⑱ 코어 7종만 등록된 실행 → 확장 규칙·확장 도구명이 **한 글자도** 없다
    core_prompt = build_system_prompt("iG5A", tool_names=list(CORE_TOOLS))
    ext_rule_leak = [i + 12 for i, r in enumerate(EXT_RULES) if r[:24] in core_prompt]
    ext_tool_leak = [t for t in EXT_TOOLS if t in core_prompt]
    check(
        "⑱ tool_names=코어7 → EXT 규칙·확장 도구명 부재 (없는 도구 사용법 지시 금지)",
        not ext_rule_leak and not ext_tool_leak and "사용 가능한 도구 (7종)" in core_prompt,
        f"규칙 누출={ext_rule_leak or '없음'} · 도구명 누출={ext_tool_leak or '없음'}",
    )

    # ── ⑲ 확장 16종 등록 → EXT 규칙 4개 + 각 근거 D 태그
    all_tools = [*CORE_TOOLS, *EXT_TOOLS]
    full_prompt = build_system_prompt("iG5A", tool_names=all_tools)
    ext_missing = [i + 12 for i, r in enumerate(EXT_RULES) if r[:24] not in full_prompt]
    # 규칙 12=D59·D62·D79 / 13=D65 / 14=D2·S3 / 15=D81·D63·D10
    ext_tags = ("D59", "D62", "D79", "D65", "D2", "S3", "D81", "D63")
    tag_missing = [t for t in ext_tags if t not in full_prompt]
    numbered = all(f"\n{n}. " in full_prompt for n in (12, 13, 14, 15))
    check(
        "⑲ tool_names=전체15 → EXT 규칙 4개 + D 태그 전건 · 규칙 번호 12·13·14·15",
        not ext_missing
        and not tag_missing
        and numbered
        and "사용 가능한 도구 (16종)" in full_prompt
        and all(t in full_prompt for t in EXT_TOOLS),
        f"규칙 누락={ext_missing or '없음'} · 태그 누락={tag_missing or '없음'} · 번호={numbered}",
    )

    # ── ⑳ 프롬프트는 env 를 읽지 않는다 (D69 의 핵심) — **실제로 바꿔 본다**
    #    소스 grep 만으로는 간접 참조를 못 잡으므로 재임포트 후 출력 동일성까지 본다.
    src = (ROOT / "backend" / "agent" / "prompts.py").read_text(encoding="utf-8")
    src_clean = "MAINTQ_TOOLS_PROFILE" not in src.replace(
        "`MAINTQ_TOOLS_PROFILE`", ""
    ) and "os.environ" not in src
    os.environ["MAINTQ_TOOLS_PROFILE"] = "full"
    try:
        reloaded = importlib.reload(importlib.import_module("backend.agent.prompts"))
        same_default = reloaded.build_system_prompt("iG5A", equipment_id="INV-L3-01") == build_system_prompt(
            "iG5A", equipment_id="INV-L3-01"
        )
        env_ext_leak = [t for t in EXT_TOOLS if t in reloaded.SYSTEM_PROMPT]
    finally:
        # 진입 시 pop 한 상태로 되돌린다 — 원래 값을 복원하지 않는 게 의도다(⑰ 참조).
        os.environ.pop("MAINTQ_TOOLS_PROFILE", None)
        importlib.reload(importlib.import_module("backend.agent.prompts"))
    check(
        "⑳ MAINTQ_TOOLS_PROFILE=full 로 재임포트해도 프롬프트 불변 (env 를 읽지 않는다)",
        src_clean and same_default and not env_ext_leak,
        f"소스에 env 참조 없음={src_clean} · 출력 동일={same_default} · 누출={env_ext_leak or '없음'}",
    )

    # ── ㉑ 부분 등록 — 번호는 위치로 고정된다(규칙 14 만 붙어도 "14.")
    partial = build_system_prompt("iG5A", tool_names=[*CORE_TOOLS, "assess_repair_value"])
    present = {n: f"\n{n}. " in partial for n in (12, 13, 14, 15)}
    check(
        "㉑ 확장 도구 일부만 등록 → 해당 규칙만 · 번호 밀림 없음",
        present == {12: False, 13: True, 14: True, 15: False}
        and "check_disposal_blockers" not in partial
        and "generate_disposal_document" not in partial
        and "규칙 (13개" in partial,
        f"규칙 존재={present} · 헤더 13개={'규칙 (13개' in partial}",
    )

    # ─────────────────────────────────────────────────────────────────────────
    # MQ-706 (D81·D63) — 처분 서류는 초안까지
    # ─────────────────────────────────────────────────────────────────────────

    # ── ㉒ 쓰기 도구의 규칙이 **코어 프로파일로 새지 않는가** (게이트의 핵심 방향)
    #    `generate_disposal_document` 는 full 에서만 등록된다 — 코어 실행 프롬프트에
    #    이 이름이나 규칙 15 의 문구가 있으면 "없는 도구의 사용법"을 지시하는 상태다.
    rule15 = EXT_RULES[3]
    core_leak = [
        s
        for s in ("generate_disposal_document", rule15[:24], "처분 서류는 초안까지")
        if s in core_prompt
    ]
    check(
        "㉒ tool_names=코어7 → generate_disposal_document·규칙 15 문구 0건 누출 (D69 게이트)",
        not core_leak and "규칙 (11개" in core_prompt,
        f"누출={core_leak or '없음'} · 코어 규칙 헤더 11개={'규칙 (11개' in core_prompt}",
    )

    # ── ㉓ full 프로파일에서 규칙 15 가 실제로 **무엇을 금지하는지** 확인한다.
    #    개수만 세면 문구가 통째로 바뀌어도 통과한다 — D81 이 막으려는 건 문구가 아니라
    #    "LLM 이 override 를 요청하거나 사유를 대신 쓰는" 경로다.
    must_have = ("초안만", "override", "네 권한이 아니", "next_step", "law_text_unavailable")
    missing15 = [s for s in must_have if s not in rule15]
    check(
        "㉓ 규칙 15 — 초안 한정 · override 는 권한 아님 · 사유 대필 금지 · 미생성 사실 명시 (D81·D63)",
        not missing15
        and "generate_disposal_document" in full_prompt
        and rule15[:24] in full_prompt,
        f"규칙 15 누락 문구={missing15 or '없음'}",
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
