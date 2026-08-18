# -*- coding: utf-8 -*-
"""도구 프로파일 계약 검증 — `MAINTQ_TOOLS_PROFILE` 게이트와 확장 등록 블록 (D69·D80·D9).

## 왜 별도 스위트인가

`sp2_mcp_roundtrip.py:59` 와 `mcp_client_contract.py:84` 는 도구 목록을 **부분집합**으로
비교한다(`EXPECTED_TOOLS <= names`) — 코어 기준선을 보는 검사라 그게 맞다. 다만 그래서
**core 에서도 full 에서도 똑같이 통과**하고, 결과적으로 `mcp_server/server.py` 의 확장
등록 블록(import 7 + 데코레이터 7)과 D80 `required` 노출·타입 폭이 **자동 회귀 0건**이었다.
확장 도구를 하나 빠뜨려도 어떤 스위트도 빨간 줄을 내지 않는 상태였다.

이 파일은 그 공백만 덮는다. **`sp2` 의 19건은 건드리지 않는다** — core 기준선이다.

## 무엇을 보는가

  ① `full` 기동 → 도구 **18종**(코어 7 + 확장 11). 부분집합이 아니라 **집합 동일**
  ② D80 — `classify_expenditure`·`assess_repair_value`·`generate_disposal_document` 의
     `inputSchema.required` 집합. 기본값을 두는 순간 optional 로 노출되어 LLM 이 인자 없이
     호출 → `invalid_input` → 재시도하는 낭비 루프가 생긴다.
     `generate_disposal_document.reason` 은 여기에 더해 **D81 의 방어선**이기도 하다 —
     사유 없는 처분 초안은 승인자가 판단 근거를 되짚을 수 없다
  ③ D9 — `amount`·`repair_cost` 가 `int|str` **유니온으로 남아 있는가**. 타입을 좁히면
     LLM 이 문자열을 넣은 순간 pydantic 이 본체 진입 전에 예외를 던져 도구가 `status` 로
     실패를 못 돌려준다 (`server.py` 의 `line_id` 주석과 같은 이유)
  ④ enum 밖 프로파일 → **exit code ≠ 0**. 폴백하면 "어느 프로파일로 돌았는지 모르는
     실행 결과"가 남는다
  ⑤ `core` 기동 → 정확히 7종이고 **확장 이름이 하나도 없다**(게이트의 반대 방향)

## 실 DB 를 건드리지 않는다

서브프로세스를 띄우는 스위트가 늘면 `data/maintq.db` 를 WAL 로 공유하는 경합이 늘어난다
(Stage 4 가 관측한 플래키의 원인). 그래서 **임시 폴더의 DB 사본**을 `MAINTQ_DB` 로
가리키게 하고(`mcp_server/db.py:21` 이 지원), 이 스위트는 도구를 **호출하지 않는다** —
스키마만 읽으므로 DB 를 열 일 자체가 거의 없다.

실행:  uv run python spikes/tools_profile_contract.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp_server" / "server.py"
SOURCE_DB = ROOT / "data" / "maintq.db"

CORE_TOOLS = {
    "lookup_error_code",
    "rag_search_manual",
    "search_inventory",
    "find_alternative_parts",
    "get_supplier_quotes",
    "get_error_history",
    "create_po_draft",
}
EXT_TOOLS = {
    "check_disposal_blockers",
    "verify_ownership",
    "classify_part_criticality",
    "get_maintenance_metrics",
    "classify_expenditure",
    "assess_repair_value",
    "build_evidence_bundle",
    "generate_disposal_document",
    "create_repair_record",
    "track_deadlines",
    "assess_risk_grade",
}

# D80 — 필수 파라미터에 기본값을 두지 않는다. 이 집합이 **정확히** 일치해야 한다:
#   빠지면(=기본값이 생기면) LLM 이 인자 없이 부를 수 있고,
#   늘면 선택적이어야 할 값이 필수가 되어 정당한 호출이 막힌다.
EXPECTED_REQUIRED = {
    "classify_expenditure": {"part_class", "repair_scope", "amount"},
    "assess_repair_value": {"equipment_id", "failed_part", "repair_cost"},
    # `asset_id`·`equipment_id` 는 either-or 라 스키마상 optional 이다 (D80 의 공백).
    # 따라서 required 는 `reason` **하나뿐**이어야 한다.
    "generate_disposal_document": {"reason"},
    # D98 — downtime_hours·model·error_code·note 만 optional. 나머지 5개가 required.
    "create_repair_record": {"equipment_id", "work_type", "repair_scope", "cost", "parts"},
}

# D81 — 이 키들이 **어느 도구 스키마에도 없어야** 한다. LLM 이 BLOCKING 우회를 요청하거나
# 신원을 위조하는 호출 자체가 구조적으로 불가능해야 하기 때문이다 (D10 태도의 복제).
# `write_tool_contract` ⑮ 가 `generate_disposal_document` 를 직접 보지만, 여기서는
# **전 도구**를 훑는다 — 새 도구가 조용히 이 키를 열고 들어오는 경로를 닫는다.
FORBIDDEN_PARAMS = {"override", "override_reason", "reviewed_by", "requested_by", "session_id"}

# D9 — 넓게 받아 도구 안에서 판정한다. 좁히면 스키마가 예외를 던져 status 를 못 돌려준다.
EXPECTED_UNION = {
    ("classify_expenditure", "amount"): {"integer", "string"},
    ("assess_repair_value", "repair_cost"): {"integer", "string"},
    ("get_maintenance_metrics", "window_months"): {"integer", "string"},
    ("create_repair_record", "cost"): {"integer", "string"},
    # `downtime_hours` 는 optional(default None) 이라 anyOf 에 "null" 브랜치가 함께 실린다 —
    # `cost` 는 필수라 이 브랜치가 없다. 둘의 차이 자체가 D80 의 증거다.
    ("create_repair_record", "downtime_hours"): {"integer", "number", "string", "null"},
}

results: list[tuple[str, bool, str]] = []

MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"


def check(name: str, ok: bool, detail: str) -> None:
    mark = MARKS[len(results)] if len(results) < len(MARKS) else f"[{len(results) + 1}]"
    results.append((f"{mark} {name}", ok, detail))


def child_env(profile: str, db: Path) -> dict[str, str]:
    """자식 프로세스 env. `MAINTQ_DB` 로 **사본**을 가리켜 실 DB 경합을 피한다."""
    env = {k: v for k, v in os.environ.items() if v is not None}
    env["MAINTQ_TOOLS_PROFILE"] = profile
    env["MAINTQ_DB"] = str(db)
    return env


async def list_tools(profile: str, db: Path) -> dict[str, object]:
    """서버를 stdio 로 띄우고 도구 목록을 받아 `{name: inputSchema}` 로 돌려준다."""
    params = StdioServerParameters(
        command=sys.executable, args=[str(SERVER)], env=child_env(profile, db)
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            return {t.name: (t.inputSchema or {}, t.description or "") for t in listed.tools}


def types_of(schema: dict, param: str) -> set[str]:
    """파라미터가 받는 JSON 타입 집합. `anyOf` 유니온과 단일 `type` 을 함께 다룬다."""
    prop = (schema.get("properties") or {}).get(param)
    if prop is None:
        return set()
    if "anyOf" in prop:
        return {b.get("type") for b in prop["anyOf"] if b.get("type")}
    return {prop["type"]} if prop.get("type") else set()


async def run(db: Path) -> None:
    full = await list_tools("full", db)

    # ─ ① 집합 동일 — 부분집합이 아니다 (이 스위트의 존재 이유)
    names = set(full)
    check(
        "full 프로파일 → 도구 18종 (코어 7 + 확장 11, 집합 동일)",
        names == CORE_TOOLS | EXT_TOOLS,
        f"{len(names)}종 · 누락={sorted((CORE_TOOLS | EXT_TOOLS) - names) or '없음'} "
        f"· 초과={sorted(names - (CORE_TOOLS | EXT_TOOLS)) or '없음'}",
    )

    # ─ ② D80 — required 집합이 정확히 일치
    bad_required = []
    for tool, want in EXPECTED_REQUIRED.items():
        schema = full.get(tool, ({}, ""))[0]
        got = set(schema.get("required") or [])
        if got != want:
            bad_required.append(f"{tool}: {sorted(got)} ≠ {sorted(want)}")
    check(
        "D80 — 필수 파라미터가 스키마 required 로 노출 (기본값을 두면 optional 이 된다)",
        not bad_required,
        "; ".join(bad_required)
        or "classify_expenditure 3종 · assess_repair_value 3종 · generate_disposal_document reason 일치",
    )

    # ─ D81 — 우회·신원 파라미터가 **전 도구** 스키마에 없는가 (미래의 도구까지 잠근다)
    leaked_params = sorted(
        f"{tool}.{p}"
        for tool, (schema, _) in full.items()
        for p in FORBIDDEN_PARAMS & set(schema.get("properties") or {})
    )
    check(
        "D81·D23 — override·override_reason·reviewed_by·requested_by·session_id 가 전 도구 스키마에 부재",
        not leaked_params,
        f"누출={leaked_params or '없음'} · 검사 대상 {len(full)}종",
    )

    # ─ ③ D9 — 타입 폭을 좁히지 않았는가
    narrowed = []
    for (tool, param), want in EXPECTED_UNION.items():
        got = types_of(full.get(tool, ({}, ""))[0], param)
        if got != want:
            narrowed.append(f"{tool}.{param}: {sorted(got)} ≠ {sorted(want)}")
    check(
        "D9 — 숫자 파라미터가 int|str 유니온으로 남아 있다 (좁히면 status 를 못 돌려준다)",
        not narrowed,
        "; ".join(narrowed) or "amount·repair_cost·window_months·cost·downtime_hours 전부 유니온",
    )

    # ─ 확장 11종 description — 오케스트레이션의 절반 (04_MCP_TOOLS 공통 원칙 1)
    empty_desc = sorted(t for t in EXT_TOOLS if not full.get(t, ({}, ""))[1].strip())
    # 처분 판정은 `disposal_date` 없이 부르면 늘 INSUFFICIENT_FACTS 로 수렴하므로(D62),
    # 도구 DESCRIPTION 이 말하지 않는 몫을 **파라미터 스키마 설명**이 유도해야 한다.
    hinted = {
        t: bool(
            (
                (full.get(t, ({}, ""))[0].get("properties") or {}).get("disposal_date") or {}
            ).get("description")
        )
        for t in ("check_disposal_blockers", "build_evidence_bundle", "generate_disposal_document")
    }
    check(
        "확장 11종 description 존재 · disposal_date 파라미터에 유도 문구 (S9·S10 데모 방어)",
        not empty_desc and all(hinted.values()),
        f"빈 description={empty_desc or '없음'} · disposal_date 설명={hinted}",
    )

    # ─ ⑤ core 는 반대 방향으로 잠근다 — 확장이 하나도 새지 않는가
    core = await list_tools("core", db)
    leaked = sorted(EXT_TOOLS & set(core))
    check(
        "core 프로파일 → 정확히 7종 · 확장 도구 0종 누출 (기본값이 core 인 이유 = 평가 오염 방지)",
        set(core) == CORE_TOOLS and not leaked,
        f"{len(core)}종 · 누출={leaked or '없음'}",
    )


def run_bad_profile(db: Path) -> None:
    """enum 밖 값 → 폴백하지 않고 죽는다 (D69). 조용히 core 로 떨어지면 안 된다."""
    proc = subprocess.run(  # noqa: S603
        [sys.executable, str(SERVER)],
        env=child_env("bogus", db),
        capture_output=True,
        text=True,
        # text=True 만 두면 자식 출력을 **로케일 기본 인코딩**으로 디코딩한다.
        # 한국어 Windows(cp949)에서 자식이 UTF-8 로 쓰면 진단 메시지가 깨져
        # 아래 문자열 대조가 위양성 FAIL 한다 (MQ-704 가 PYTHONIOENCODING=utf-8 로 재현).
        encoding="utf-8",
        errors="replace",
        timeout=60,
        input="",
    )
    message = (proc.stderr or "") + (proc.stdout or "")
    check(
        "enum 밖 프로파일 → exit code ≠ 0 (폴백 금지 · 어느 프로파일로 돌았는지 모르는 상태를 만들지 않는다)",
        proc.returncode != 0 and "MAINTQ_TOOLS_PROFILE" in message,
        f"exit={proc.returncode} · 메시지에 키 이름 포함={'MAINTQ_TOOLS_PROFILE' in message}",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("도구 프로파일 계약 — D69 게이트 · D80 required · D9 타입 폭 (임시 DB 사본)\n")
    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "profile.db"
        shutil.copy2(SOURCE_DB, db)
        asyncio.run(run(db))
        run_bad_profile(db)

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 40))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 40))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건:\n  - " + "\n  - ".join(failed))
    print(f"\n통과 ({len(results)}건) — D69 프로파일 게이트 양방향 · D80 required · D9 타입 폭 확인")


if __name__ == "__main__":
    main()
