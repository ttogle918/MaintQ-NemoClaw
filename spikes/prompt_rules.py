# -*- coding: utf-8 -*-
"""시스템 프롬프트·안전 상수 정적 검사 (MQ-303 DoD · MQ-612 확장).

**LLM 을 호출하지 않는다.** 여기서 보는 건 "모델이 잘 따르는가"가 아니라
**"규칙과 기준값이 프롬프트에 실제로 들어 있는가"** 다. 문구가 조용히 사라지거나
방전 대기 기준값이 축소되면(safety-guardrail 규칙 3) 여기서 먼저 깨진다.

MQ-612 가 더한 것 (⑰~㉑, D69) · MQ-706 이 더한 것 (㉒㉓) · Sprint 11 마무리(MQ-1106 후속)가
더한 것 (㉔):
  - 확장 규칙 6개(12~17, Sprint 11 이 16·17 을 더함, D102)는 **전제 도구가 실제로
    등록됐을 때만** 붙는다
  - `prompts.py` 는 `MAINTQ_TOOLS_PROFILE` 을 **읽지 않는다** — env 를 바꿔도 출력이
    바뀌지 않음을 실제로 확인한다. 등록(자식 프로세스)과 지시(백엔드)가 같은 env 를
    각자 해석하면 어긋나기 때문이다
  - 규칙 번호는 **위치로 고정** — 확장 도구가 일부만 등록돼도 번호가 밀리지 않는다
  - ㉔ — Sprint 11 이 `track_deadlines`·`assess_risk_grade` 를 `mcp_server/server.py` 에는
    등록하고 `prompts.py` 의 `EXT_TOOLS` 에는 올리지 않은 채 끝난 일이 실제로 있었다.
    이 스위트는 그동안 `prompts.py` 만 자기참조해서 그 결함을 잡지 못했다(위장 통과) —
    ㉔ 은 `server.py` 소스에서 `full` 블록에 실제 등록된 도구명을 뽑아 `EXT_TOOLS` 와
    직접 대조한다(서버 기동·LLM 호출 없이 정적으로).

실행:  uv run python spikes/prompt_rules.py
"""

from __future__ import annotations

import hashlib
import importlib
import os
import re
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
        "⑤ build_system_prompt('iS7') → ValueError, enum 4종은 통과",
        raised and both_ok and tuple(MODELS) == ("iG5A", "S100", "IE5", "HV600"),
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
    safety_models = {s["model"] for s in SAFETY_SOURCES}
    # 기종별로 "10분 이상"을 명시한 원문이 최소 1건 있어야 기준값이 근거를 갖는다
    baseline_quoted = {
        m
        for m in MODELS
        for s in SAFETY_SOURCES
        if s["model"] == m and "10분 이상" in str(s["quote"])
    }
    # IE5·HV600 은 SAFETY_BASELINE 근거 미확보 — 의도적 제외(D109 ⓐ, D157, 절대규칙 3).
    # HV600 은 정적 상수가 아니라 DB 승인분(onboarding_safety_candidates)에서 나온다 — D157.
    # ⚠ `baseline_quoted <= set(MODELS)` 는 baseline_quoted 자체가 `for m in MODELS` 컴프리헨션
    # 산물이라 **항상 참인 항등식**이었다(뮤턴트로 실증: SAFETY_SOURCES 에서 "10분 이상" 문구를
    # 전부 지워도 이 축은 여전히 통과한다 — reviewer 지적, P30 유형 무력화). 대신 "IE5·HV600 을
    # 뺀 나머지 MODELS 는 반드시 원문 근거를 가져야 한다"는 실질 제약으로 되돌린다. 모델 누출
    # 방지 축(SAFETY_SOURCES 가 가리키는 모델이 MODELS 밖으로 새지 않는가)은 `safety_models <=
    # set(MODELS)` 로 그대로 유지한다.
    required_quoted = set(MODELS) - {"IE5", "HV600"}
    check(
        "⑭ SAFETY_SOURCES 에 매뉴얼 원문·페이지 기록 (IE5·HV600 은 근거 미확보로 의도적 제외 — D109·D157)",
        {("iG5A", 4), ("S100", 2)} <= src_pages
        and safety_models <= set(MODELS)
        and required_quoted <= baseline_quoted  # iG5A·S100 은 "10분 이상" 원문 근거 필수
        and all(str(s["quote"]).strip() for s in SAFETY_SOURCES),
        f"SAFETY_SOURCES 모델={sorted(safety_models)}, MODELS={list(MODELS)}, "
        f"MODELS-SAFETY_SOURCES 차집합={sorted(set(MODELS) - safety_models) or '없음'}, "
        f"{len(SAFETY_SOURCES)}건, 기준값 원문 보유={sorted(baseline_quoted)}, "
        f"필수 보유 대상={sorted(required_quoted)}, 누락={sorted(required_quoted - baseline_quoted) or '없음'}",
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
    # ★ D125: `get_document_facts` 는 도구 목록(EXT_TOOLS 13→14)에만 오르고 **EXT_RULES 는
    #   8개 그대로다.** 읽기 전용 조회라 별도 행동 규칙이 필요 없고, "고칠 수는 없다" 는
    #   경고는 도구 설명 한 줄에 담았다 — 규칙을 늘리면 프롬프트만 길어진다.
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
        "⑰ env 미설정 상태에서 RULES 11개 · EXT_RULES 8개 고정 (D69·D102·D112·D125)",
        len(RULES) == 11
        and len(EXT_RULES) == 8
        and os.environ.get("MAINTQ_TOOLS_PROFILE") is None
        and len(CORE_TOOLS) == 7
        and len(EXT_TOOLS) == 15,
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

    # ── ⑲ 전체 22종 등록 → EXT 규칙 8개 + 각 근거 D 태그
    all_tools = [*CORE_TOOLS, *EXT_TOOLS]
    full_prompt = build_system_prompt("iG5A", tool_names=all_tools)
    ext_missing = [i + 12 for i, r in enumerate(EXT_RULES) if r[:24] not in full_prompt]
    # 규칙 12=D59·D62·D79 / 13=D65 / 14=D2·S3 / 15=D81·D63·D10 / 16=D101·D102 / 17=D101·D102
    # 18=신규(D112) / 19=S8·D112
    ext_tags = ("D59", "D62", "D79", "D65", "D2", "S3", "D81", "D63", "D101", "D102")
    tag_missing = [t for t in ext_tags if t not in full_prompt]
    numbered = all(f"\n{n}. " in full_prompt for n in (12, 13, 14, 15, 16, 17, 18, 19))
    check(
        "⑲ tool_names=전체22 → EXT 규칙 8개 + D 태그 전건 · 규칙 번호 12~19",
        not ext_missing
        and not tag_missing
        and numbered
        and "사용 가능한 도구 (22종)" in full_prompt
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
    present = {n: f"\n{n}. " in partial for n in (12, 13, 14, 15, 16, 17, 18, 19)}
    check(
        "㉑ 확장 도구 일부만 등록 → 해당 규칙만 · 번호 밀림 없음",
        present
        == {
            12: False,
            13: True,
            14: True,
            15: False,
            16: False,
            17: False,
            18: False,
            19: False,
        }
        and "check_disposal_blockers" not in partial
        and "generate_disposal_document" not in partial
        and "track_deadlines" not in partial
        and "assess_risk_grade" not in partial
        and "search_insurance_clause" not in partial
        and "assess_equipment_loan" not in partial
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

    # ─────────────────────────────────────────────────────────────────────────
    # Sprint 11 마무리 (MQ-1106 후속) — 자기참조 위장통과 방지
    # ─────────────────────────────────────────────────────────────────────────

    # ── ㉔ EXT_TOOLS(prompts.py) 가 실제로 server.py 의 `full` 블록에 등록된 도구명과
    #    **정확히 일치**하는가. 위 검사들은 전부 `prompts.py` 안에서만 도는데, 그건
    #    "prompts.py 가 스스로 일관적인가"만 보장할 뿐 "MCP 가 실제로 등록한 도구를
    #    prompts.py 가 빠짐없이 알고 있는가"는 보장하지 못한다 — Sprint 11 이 정확히
    #    이 틈으로 `track_deadlines`·`assess_risk_grade` 를 놓쳤다(서버는 등록, 프롬프트는
    #    누락). `tools_profile_contract.py` 는 서버를 실제로 기동해 이 대조를 하지만,
    #    여기서는 LLM·서브프로세스 없이 `server.py` 소스를 정적으로 읽어 같은 대조를 건다.
    server_src = (ROOT / "mcp_server" / "server.py").read_text(encoding="utf-8")
    _FULL_MARK, _MAIN_MARK = 'if TOOLS_PROFILE == "full":', 'if __name__ == "__main__":'
    full_block = (
        server_src[server_src.index(_FULL_MARK) : server_src.index(_MAIN_MARK)]
        if _FULL_MARK in server_src and _MAIN_MARK in server_src
        else ""
    )
    registered = set(re.findall(r"@mcp\.tool\([^\n]*\)\s*\n\s*def (\w+)\(", full_block))
    prompts_ext = set(EXT_TOOLS)
    check(
        "㉔ prompts.EXT_TOOLS == server.py full 블록 실등록 도구명 (자기참조 위장통과 방지)",
        bool(registered) and prompts_ext == registered,
        f"prompts.EXT_TOOLS={len(prompts_ext)} · server 실등록={len(registered)} · "
        f"prompts 누락(서버엔 있는데 프롬프트에 없음)={sorted(registered - prompts_ext) or '없음'} · "
        f"server 누락(프롬프트엔 있는데 서버에 없음)={sorted(prompts_ext - registered) or '없음'}",
    )


    # ── ㉕ 방전 대기 「10분 이상」 지시의 적용 범위 = iG5A·S100 (2026-09-25 사람 승인, TODO H5)
    #    Stage 5 브라우저 검증: HV600(승인 문구 SC-14 「최소 5분 이상」) 채팅에서 안전 블록은
    #    5분인데 LLM 본문이 10분을 써 한 화면에 두 수치가 공존했다 — 프롬프트가 기종 무관하게
    #    "기준값은 10분 이상" 을 지시했기 때문이다.
    #    음성: HV600 프롬프트에 「10분」 0글자 · SAFETY_BASELINE 본문 미포함.
    #    양성: iG5A·S100 프롬프트엔 「10분 이상」 과 정적 확정 문구가 그대로 있다.
    #    liveness: 두 프롬프트 모두 규칙 10 앵커와 온보딩 문장을 실제로 싣는다(스캐너가 빈
    #    문자열을 보고 음성 축을 위장 통과하지 않게).
    hv = build_system_prompt("HV600", equipment_id="INV-HV-01")
    hv_full = build_system_prompt("HV600", tool_names=list(CORE_TOOLS) + list(EXT_TOOLS))
    statics = {m: build_system_prompt(m) for m in ("iG5A", "S100")}
    onboarding_sentence = "온보딩 기종(HV600 등)은 시스템이 붙이는 승인 문구의 수치를 따르고"
    rule10_anchor = "10. **안전 문구를 창작하지 마라"
    hv_neg = all("10분" not in p and safety_text not in p for p in (hv, hv_full))
    static_pos = all(
        "10분 이상" in p and safety_text in p and 'iG5A·S100 의 기준값은 "10분 이상"' in p
        for p in statics.values()
    )
    anchors = [
        p.count(rule10_anchor) == 1 and onboarding_sentence in p
        for p in (hv, hv_full, *statics.values())
    ]
    check(
        "㉕ 「10분 이상」 지시 범위 = iG5A·S100 — HV600 프롬프트엔 「10분」 0글자 (음성·양성·liveness)",
        hv_neg and static_pos and all(anchors),
        f"HV600 '10분' 출현={hv.count('10분')}+{hv_full.count('10분')} · "
        f"HV600 정적 문구 포함={safety_text in hv} · "
        f"iG5A/S100 '10분 이상'={[statics[m].count('10분 이상') for m in statics]} · "
        f"앵커(규칙10·온보딩 문장) 생존={sum(anchors)}/{len(anchors)}",
    )


    # ── ㉖ 응답 언어 고정 (2026-09-25 데모 다듬기) — Nemotron 답에 중국어 한자가 섞여 네모 글자.
    #    양성: 「응답은 한국어로만 쓴다」 문장이 **모든 조립 경로**(기종 미상·정적 기종·온보딩
    #    기종·full 프로파일·도구 0종)에 실린다 — `_STYLE` 은 `_compose` 한 곳에서 붙지만 경로별로
    #    직접 확인한다. 음성: 프롬프트 자체에 한자(CJK 통합)·가나 0글자 — 금지 예시를 원문으로
    #    싣지 않는다. liveness: 같은 프롬프트에서 한글 음절을 실제로 센다(스캐너가 빈 문자열을
    #    보고 음성 축을 위장 통과하지 않게) + 정규식 자체가 픽스처의 한자·가나를 잡는다.
    lang_sentence = "**응답은 한국어로만 쓴다**"
    cjk = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
    variants = {
        "기종미상": build_system_prompt(None),
        "iG5A": build_system_prompt("iG5A", equipment_id="INV-L3-01"),
        "HV600": build_system_prompt("HV600", equipment_id="INV-HV-01"),
        "full": build_system_prompt("S100", tool_names=list(CORE_TOOLS) + list(EXT_TOOLS)),
        "도구0종": build_system_prompt("iG5A", tool_names=[]),
    }
    missing = [k for k, p in variants.items() if p.count(lang_sentence) != 1]
    cjk_hits = {k: cjk.findall(p) for k, p in variants.items() if cjk.search(p)}
    hangul = sum(len(re.findall(r"[\uac00-\ud7a3]", p)) for p in variants.values())
    oracle = len(cjk.findall("参照 カタカナ ひらがな 한글")) == 2 + 4 + 4
    check(
        "㉖ 응답 언어 고정 — 5개 조립 경로 전부에 문장 1회 · 프롬프트 한자·가나 0글자 (양성·음성·liveness)",
        not missing and not cjk_hits and hangul > 0 and oracle,
        f"문장 누락 경로={missing or '없음'} · 한자/가나 적발={cjk_hits or '0건'} · "
        f"한글 음절={hangul} · 정규식 오라클={'OK' if oracle else 'FAIL'}",
    )

    # ── ㉗ 본문이 안전 블록 **유무**를 단정하지 않게 (2026-09-25 사람 승인, TODO H5 「(추가)」)
    #    웹 콘솔 HV600 「냉각팬 교체 절차」 답: 승인 SAFETY 블록(p.29)이 붙었는데 본문 끝이
    #    "안전 경고는 제공된 근거가 없으므로 드릴 수 없습니다" — 블록 부착은 시스템 몫인데 모델이
    #    그 유무를 단정해 화면이 모순됐다.
    #    양성: 새 문장이 **7개 조립 경로**(기종 미상·iG5A·S100·IE5·HV600 온보딩·full·도구 0종)
    #    전부에 정확히 1회, 그리고 규칙 10 줄 **안에** 있다.
    #    불변: 안전 문구 본문(`SAFETY_BASELINE["text"]`) sha256 고정 · 대기 시간 문장
    #    (정적 기종 「10분 이상」 / 온보딩 문장) · 근거 없으면 서술 금지 문장이 경로마다 그대로.
    #    liveness: 경로마다 규칙 10 앵커가 1회 잡혀야 판정한다(빈 프롬프트·앵커 이동에 눈멀지 않게).
    presence_sentence = "**안전 경고의 유무는 본문에서 언급하지 마라**"
    fail_closed = "매뉴얼 근거 페이지가 없으면 안전 경고도 위험 작업 서술도 하지 않는다."
    wait_static = 'iG5A·S100 의 기준값은 "10분 이상"이다.'
    safety_sha = "0d8042391af660c5f35a1f45bff50146fb471bd6dbf8dc43c79c3905cf2f974a"
    paths = {
        "기종미상": build_system_prompt(None),
        "iG5A": build_system_prompt("iG5A", equipment_id="INV-L3-01"),
        "S100": build_system_prompt("S100"),
        "IE5": build_system_prompt("IE5"),
        "HV600": build_system_prompt("HV600", equipment_id="INV-HV-01"),
        "full": build_system_prompt("S100", tool_names=list(CORE_TOOLS) + list(EXT_TOOLS)),
        "도구0종": build_system_prompt("iG5A", tool_names=[]),
    }

    def _rule10_line(p: str) -> str:
        return next((ln for ln in p.splitlines() if ln.startswith(rule10_anchor)), "")

    alive = {k: p.count(rule10_anchor) == 1 for k, p in paths.items()}
    bad_count = {k: p.count(presence_sentence) for k, p in paths.items() if p.count(presence_sentence) != 1}
    outside = [k for k, p in paths.items() if presence_sentence not in _rule10_line(p)]
    # 새 문장은 근거 없으면 서술 금지 문장 **뒤**에 붙는다 — 앞 문장을 대체하지 않았다는 증거.
    order_bad = [
        k
        for k, p in paths.items()
        if not (fail_closed in _rule10_line(p)
                and _rule10_line(p).index(fail_closed) < _rule10_line(p).find(presence_sentence))
    ]
    wait_bad = [
        k
        for k, p in paths.items()
        if onboarding_sentence not in p
        or ((wait_static in p) != (k != "HV600"))  # 온보딩 기종만 「10분」 문장이 없다(㉕)
    ]
    sha_ok = hashlib.sha256(safety_text.encode("utf-8")).hexdigest() == safety_sha
    check(
        "㉗ 안전 블록 유무 단정 금지 — 7개 조립 경로 규칙 10 에 1회 · 안전 문구·대기 시간·서술 금지 불변 (양성·불변·liveness)",
        all(alive.values()) and not bad_count and not outside and not order_bad
        and not wait_bad and sha_ok,
        f"규칙10 앵커 생존={sum(alive.values())}/{len(alive)} · 출현≠1 경로={bad_count or '없음'} · "
        f"규칙10 밖={outside or '없음'} · 서술금지 문장 뒤 아님={order_bad or '없음'} · "
        f"대기 문장 어긋남={wait_bad or '없음'} · SAFETY_BASELINE sha256 일치={sha_ok}",
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
