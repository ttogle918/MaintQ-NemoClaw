# -*- coding: utf-8 -*-
"""_asset_ref — 자산 참조 해석 + 처분 인자 파싱 공용 헬퍼. **이 파일은 도구가 아니다.**

────────────────────────────────────────────────────────────────────────────────
왜 있는가
────────────────────────────────────────────────────────────────────────────────
`check_disposal_blockers`(`04 §8`) 와 `build_evidence_bundle`(`04 §14`) 은 **같은 자산 참조
규약**을 쓴다 — `asset_id | equipment_id` 둘 중 하나 필수, `equipment.asset_id` 로 해석,
`disposal_mode` enum 검증, `disposal_date` ISO 검증. Sprint 6~7 을 지나며 이 약 90행이
파일 두 곳에 복제됐고, MQ-706(`generate_disposal_document`)이 세 번째 사본을 만들기 직전이었다.

복제의 위험은 코드량이 아니라 **드리프트**다. 한쪽만 고치면 같은 입력에 두 도구가 다른
`reason` 을 내고, 사용자는 "판정은 되는데 문서는 안 되는" 이유를 알 수 없게 된다.
그래서 실패 어휘를 한 곳에 둔다. (`spikes/bundle_integrity.py` 가 두 도구의 reason 을 직접
대조하는 회귀를 **계속 유지**한다 — 이 모듈은 대조를 없애는 게 아니라 통과를 구조로 보장한다.)

────────────────────────────────────────────────────────────────────────────────
⛔ 이 모듈이 **하지 않는** 것 — DoD ⑰ 의 경계
────────────────────────────────────────────────────────────────────────────────
  - **판정하지 않는다.** verdict·버킷·우선순위(D79)는 `data.rules.engine` 안에만 있다.
    여기엔 `engine.DISPOSAL_MODES` 조회 말고 엔진 호출이 없다.
  - **`build_evidence_bundle` 이 `check_disposal_blockers` 를 import 하는 경로를 만들지
    않는다** (W5 회귀 방지 — 번들이 판정 도구의 13키 계약을 경유하면 `facts_used`·
    `laws_used` 를 얻을 수 없고 원천이 다시 둘로 갈린다). 이 모듈은 두 도구 **어느 쪽도**
    import 하지 않으므로 자식 `sys.modules` 에도 판정 도구가 올라오지 않는다.
  - **DB 를 열지 않는다.** 커넥션은 호출자가 `read_only()` 로 열어 넘긴다 — 판정·해시·
    재읽기가 같은 커넥션·같은 사본을 봐야 하기 때문이다 (`build_evidence_bundle` N2).

────────────────────────────────────────────────────────────────────────────────
파일명 앞의 `_` — "도구 아님"의 표식
────────────────────────────────────────────────────────────────────────────────
`mcp_server/tools/` 는 "파일당 도구 1개" 규약이라, 도구가 아닌 파일은 언더스코어로 구분한다.
등록은 `server.py` 가 `@mcp.tool` 로 **명시**하므로 디렉터리 스캔이 없고 이 파일은 애초에
등록 후보가 아니다. 그 사실은 추측이 아니라 `spikes/tools_profile_contract.py` ① 이
core 7종·full 14종을 단언해 실측으로 잠근다.

예외를 던지지 않는다 (D9). `mcp_server` 는 `backend` 를 import 하지 않는다 (D15).
`data.rules.engine` 은 데이터 계층이라 허용된다 (D73).
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any, NamedTuple

from data.rules import engine

# "문자열이 아닌 값이 들어왔다" 를 None(미지정)과 구분하기 위한 표식.
# 둘을 뭉치면 `asset_id=123` 이 조용히 "asset_id 미지정" 이 된다.
NOT_TEXT = object()


def err(reason: str, message: str, **extra: Any) -> dict:
    """실패는 예외가 아니라 `status` 로 돌려준다 (D9)."""
    return {"status": "error", "reason": reason, "message": message, **extra}


def as_text(value: object) -> object:
    """문자열로 확정되는 값만 통과시킨다. 숫자·dict·list 는 추정하지 않는다."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return NOT_TEXT


def resolve_asset_id(
    con: sqlite3.Connection, asset_id: str | None, equipment_id: str | None
) -> tuple[str | None, dict | None]:
    """(asset_id, 실패 응답) 중 하나를 채워 돌려준다. `04 §8`·`§14` 가 같은 reason 을 쓴다.

    `equipment_id` 만 주어지면 `equipment.asset_id` 로 해석한다 (D68). 그 값이 NULL 이면
    `no_host_asset` — `INV-L1-01`(분전반)이 정확히 이 케이스다. **배전 위치는 거래 단위가
    아니므로** 처분 판정 대상이 될 수 없고, 이를 `unknown_*` 이나 `CLEAR` 로 뭉개면
    "판정할 수 없는 대상"이 "판정 결과 문제 없음"으로 읽힌다.

    둘 다 주어졌는데 서로 다른 자산을 가리키면 `invalid_input` 이다 — 한쪽을 조용히 이기게
    하면 사용자가 물은 것과 다른 자산의 판정을 돌려주게 된다.
    """
    resolved: str | None = None
    if equipment_id is not None:
        row = con.execute(
            "SELECT asset_id FROM equipment WHERE equipment_id = ?", (equipment_id,)
        ).fetchone()
        if row is None:
            return None, {
                "status": "not_found",
                "reason": "unknown_equipment",
                "equipment_id": equipment_id,
                "message": f"등록되지 않은 설비입니다: {equipment_id}",
            }
        if row["asset_id"] is None:
            return None, {
                "status": "not_found",
                "reason": "no_host_asset",
                "equipment_id": equipment_id,
                "message": (
                    f"{equipment_id} 에 연결된 호스트 자산이 없습니다 — 처분 판정의 대상은 "
                    "거래 단위인 자산(assets)이며 이 설비에는 그 자산이 지정돼 있지 않습니다. "
                    "판정 결과가 '문제 없음'인 것이 아닙니다."
                ),
            }
        resolved = row["asset_id"]

    if asset_id is not None and resolved is not None and asset_id != resolved:
        return None, err(
            "invalid_input",
            f"asset_id({asset_id}) 와 equipment_id 가 가리키는 자산({resolved}) 이 다릅니다. "
            "하나만 지정하세요.",
        )
    return (asset_id or resolved), None


class DisposalArgs(NamedTuple):
    """검증을 통과한 처분 인자. 여기까지 온 값은 **더 고쳐 쓰지 않는다.**"""

    asset_id: str | None
    equipment_id: str | None
    disposal_mode: str
    disposal_date: str | None


def parse_disposal_args(
    asset_id: object,
    equipment_id: object,
    disposal_mode: object,
    disposal_date: object,
) -> tuple[DisposalArgs | None, dict | None]:
    """(검증 통과 인자, 실패 응답) 중 하나를 채워 돌려준다. 예외를 던지지 않는다 (D9·D46).

    ⛔ **폴백하지 않는다.** 이 함수의 존재 이유는 "고쳐 주기"가 아니라 "되돌리기"다 —
      `'SELL'` 을 `SALE` 로 보정하면 오타 하나가 `VAT-INVOICE` 트리거(`eq "SALE"`)를 빗나가
      `CONDITIONAL` 이어야 할 판정을 `CLEAR` 로 만든다. 읽을 수 없는 날짜를 오늘로 메우면
      "처분일을 모른다"가 "오늘 처분한다"가 된다 (D62).

    `asset_id`·`equipment_id` 는 **둘 중 하나 필수**다. MCP 스키마로는 either-or 를 표현할 수
    없으므로(D80 의 공백) 도구 시그니처상 둘 다 optional 이고, 그 공백을 여기서 닫는다.

    `disposal_mode` 의 미지정(None)은 도구 시그니처 기본값과 같은 뜻인 `"SALE"` 로 본다.
    값이 **있는데** enum 밖이면 위 이유로 `invalid_input` 이다.
    """
    parsed_asset = as_text(asset_id)
    parsed_equipment = as_text(equipment_id)
    for name, value in (("asset_id", parsed_asset), ("equipment_id", parsed_equipment)):
        if value is NOT_TEXT:
            return None, err("invalid_input", f"{name} 는 문자열 식별자입니다 (예: 'AST-L3-CONV')")
    if parsed_asset is None and parsed_equipment is None:
        return None, err("invalid_input", "asset_id 또는 equipment_id 중 하나는 필요합니다")

    parsed_mode = as_text(disposal_mode)
    mode: Any = "SALE" if parsed_mode is None else parsed_mode
    if mode is NOT_TEXT or mode not in engine.DISPOSAL_MODES:
        return None, err(
            "invalid_input",
            f"disposal_mode 는 {' | '.join(engine.DISPOSAL_MODES)} 중 하나여야 합니다: "
            f"{disposal_mode!r} (대소문자·유사어를 임의로 해석하지 않습니다)",
        )

    parsed_date = as_text(disposal_date)
    if parsed_date is NOT_TEXT:
        return None, err(
            "invalid_input", "disposal_date 는 ISO 날짜 문자열입니다 (예: '2026-08-09')"
        )
    if parsed_date is not None:
        try:
            date.fromisoformat(parsed_date)  # type: ignore[arg-type]
        except ValueError:
            return None, err(
                "invalid_input",
                f"disposal_date 를 ISO 날짜로 읽을 수 없습니다: {disposal_date!r} "
                "(예: '2026-08-09'). 모르는 날짜를 오늘로 대체하지 않습니다.",
            )

    return DisposalArgs(parsed_asset, parsed_equipment, mode, parsed_date), None  # type: ignore[arg-type]
