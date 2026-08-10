# -*- coding: utf-8 -*-
"""verify_ownership — 중고 설비 실사 체크리스트 판정 (S18, `12 §6` 9개 카테고리).

**이 파일은 얇은 래퍼다.** 판정 로직·문안·상수는 전부 `data/ownership.py` 에 있다 (MQ-707b).
이유는 소비자가 둘이기 때문이다 — 이 MCP 도구와 `GET /api/assets/{id}/ownership` (REST).
두 곳에 같은 판정을 복제하면 한쪽만 고쳐질 때 **같은 자산이 채팅과 화면에서 다르게 보인다**
(MQ-702 가 지우고 있는 W2 드리프트와 같은 형태). `data/` 는 두 프로세스가 공유해도 되는
데이터 계층이다 (D73) — `data.rules.engine` 선례와 동형이고, `backend` ↔ `mcp_server`
상호 import 만 금지된다 (D15). `server.py:28` 이 레포 루트를 sys.path 에 넣는다.

여기 남는 것은 세 가지뿐이다:
  1. `DESCRIPTION` — `04 §9` 가 **"코드 정본"으로 인용**한다. 옮기지 않는다.
  2. 커넥션 수명 (`read_only()`) — 읽기 전용이다 (D10). `data/ownership.py` 는 DB 경로를 모른다.
  3. 예외 → `status` 껍데기 (D9·D46). 도구는 예외를 던지지 않는다.

판정이 왜 이렇게 생겼는지(원천 없음 → 무조건 UNVERIFIED · PARTIAL 승격 불가 · 외부 기관
런타임 미호출 · "값을 어디서 읽는가" B-1 규약)는 `data/ownership.py` 모듈 docstring 에 있다.
"""

from __future__ import annotations

import sqlite3

import data.ownership as _own

from ..db import read_only

# 반복 고장 문턱의 **정본은 이 파일 옆의 `get_error_history`** 다 (D2·D29). `data/ownership.py`
# 는 `mcp_server` 를 import 할 수 없어(D15) 같은 값을 다시 적어 두는데, 그 복제를 규율이
# 아니라 **import 시점 단언**으로 잠근다 — 어긋나면 MCP 서버가 기동하다 죽는다.
# 조용히 어긋나면 같은 자산의 "반복 고장 패턴"이 도구마다 다르게 판정된다.
from .get_error_history import REPEAT_THRESHOLD, REPEAT_WINDOW_DAYS

assert (_own.REPEAT_WINDOW_DAYS, _own.REPEAT_THRESHOLD) == (
    REPEAT_WINDOW_DAYS,
    REPEAT_THRESHOLD,
), (
    "반복 고장 문턱이 get_error_history 와 data/ownership.py 사이에서 어긋났다 (D2·D29) — "
    f"tools={(REPEAT_WINDOW_DAYS, REPEAT_THRESHOLD)} / "
    f"data={(_own.REPEAT_WINDOW_DAYS, _own.REPEAT_THRESHOLD)}"
)

DESCRIPTION = (
    "중고 설비를 사거나 팔기 전 실사 체크리스트 9개 카테고리를 판정한다. "
    "권리관계(담보·리스·압류)·정비 이력·법정 요건·시장가 등 '이 설비를 믿고 거래해도 되는가'를 "
    "물을 때 호출할 것. 결과는 확인된 것과 확인되지 않은 것을 나눠서 준다. "
    "verdict 가 PARTIAL 이면 '대체로 안전'이 아니라 '미확인 항목이 남았다'는 뜻이며, "
    "PARTIAL 은 어떤 추가 확인으로도 VERIFIED 로 승격되지 않는다 — 사용자에게 안전하다고 "
    "말하지 말고 남은 항목과 계약상 배분(진술보장·특약)을 안내할 것. "
    "이 도구는 외부 기관(등기·국세청)을 조회하지 않는다 — UNVERIFIED 항목을 "
    "추측으로 메우지 말 것. "
    # 두 파라미터가 스키마상 전부 optional 이라(둘 중 하나 필수는 스키마로 표현되지 않는다)
    # 인자 없이 호출 → invalid_input → 재시도 루프가 스키마로 막히지 않는다. 여기서 막는다.
    "asset_id 또는 equipment_id 중 하나는 반드시 넘길 것 — 둘 다 비우면 조회 없이 거부된다. "
    "설비(인버터) 식별자만 알면 equipment_id 로 호출하면 호스트 자산으로 해석된다."
)

# `spikes/asset_tools_contract.py` ⑰⑱ 이 방어선을 잠근다:
#   ⑰ 상수 방어선 — `FIXED_UNVERIFIED` 의 카테고리 집합·항목 총량 핀 고정
#   ⑱ 동적 방어선 — 상수 표를 통째로 비워도 VERIFIED 에 도달하지 못하는지 확인
# ⚠ ⑱ 은 **`data.ownership.FIXED_UNVERIFIED`(정본)를 갈아끼운다.** 아래 별칭이 아니다 —
#   `_own.verify` 가 호출 시점에 자기 모듈 전역을 읽으므로 그래야 실제로 효과가 있다.
#   별칭을 갈아끼우면 아무 일도 일어나지 않은 채 검사는 **여전히 PASS 한다**(공허한 통과).
FIXED_UNVERIFIED = _own.FIXED_UNVERIFIED  # 읽기 전용 별칭 — ⑰ 의 핀 고정용

# 재노출 — 다른 모듈·회귀가 도구 이름으로 참조한다 (`asset_tools_contract` 는 `_fact`·`_knows`
# 로 B-1 구조 방어를 직접 검사한다). 값의 정본은 `data/ownership.py` 다.
CATEGORIES = _own.CATEGORIES
RISK_BY_ITEM = _own.RISK_BY_ITEM
MITIGATION_BY_ITEM = _own.MITIGATION_BY_ITEM
NOT_CONSIDERED = _own.NOT_CONSIDERED
DISCLAIMER = _own.DISCLAIMER
VERIFIED = _own.VERIFIED
UNVERIFIED = _own.UNVERIFIED
PARTIAL = _own.PARTIAL
FACT_KEYS = _own.FACT_KEYS
_fact = _own._fact
_knows = _own._knows


def verify_ownership(asset_id: str | None = None, equipment_id: str | None = None) -> dict:
    """실사 체크리스트 9개 카테고리를 판정한다. 예외를 던지지 않는다 (D9·D46)."""
    try:
        # 인자 검증은 **DB 를 열기 전에** 한다 — 커넥션을 먼저 열면 DB 가 없을 때
        # `invalid_input` 이어야 할 호출이 `db_missing` 으로 바뀐다 (이관 전 순서 유지).
        bad = _own.invalid_ref(asset_id, equipment_id)
        if bad is not None:
            return bad
        with read_only() as con:
            return _own.verify(con, asset_id=asset_id, equipment_id=equipment_id)
    except FileNotFoundError as e:
        return {"status": "error", "reason": "db_missing", "message": str(e)}
    except sqlite3.Error as e:
        return {"status": "error", "reason": "db_error", "message": str(e)}
    except Exception as e:  # noqa: BLE001 — engine·파싱 예외까지 status 로 닫는다 (D9)
        return {
            "status": "error",
            "reason": "internal_error",
            "message": f"{type(e).__name__}: {e}",
        }
