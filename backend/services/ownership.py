# -*- coding: utf-8 -*-
"""중고 설비 실사 판정 서비스 — `GET /api/assets/{id}/ownership` (S18, MQ-707b).

**판정을 어디서 가져오는가 (D73).**
`mcp_server` 를 import 하지 않는다 (D15 — 두 런타임 프로세스의 상호 import 금지).
판정은 `data/ownership.py` 에 한 벌만 있고 MCP 도구(`verify_ownership`)와 이 서비스가
**같은 함수**를 부른다. 복제본을 두면 같은 자산이 채팅(도구)과 화면(REST)에서 다르게
보이고, 사용자는 어느 쪽이 맞는지 알 수 없다. 회귀 `spikes/ownership_api_contract.py` 가
REST 응답과 MCP 도구 출력을 **직접 대조**한다.

`services/disposal.py` 와 같은 이유로 `data/` 를 직접 읽는다 — 사람용 REST 판정이 에이전트
도구 노출 설정(D69 `core`/`full`)에 종속되면 안 된다. `core` 프로파일에서는 확장 도구가
등록조차 되지 않아 "MCP 호출로만 판정" 안은 REST 를 통째로 죽인다.

⚠ `import data.ownership as _own` — **모듈 참조**다. `from data.ownership import verify` 로
  받으면 그 시점 값이 이름에 고정돼, 이 파일이 판정 함수의 사본을 갖는 것과 같아진다
  (Sprint 5 W1 의 `DB_PATH` 로드시점 고정 사고와 같은 유형).

**읽기 전용이다.** 커넥션은 `mode=ro` URI 뿐이라(`services/disposal.read_only`) 쓰기를
시도해도 SQLite 가 거부한다 — 보증은 문서가 아니라 구조가 한다 (D10 과 같은 태도).
"""

from __future__ import annotations

import sqlite3

import data.ownership as _own

# ⛔ 세 번째 `mode=ro` 커넥션 헬퍼를 만들지 않는다. `services/disposal.read_only` 는
#    `backend.db.DB_PATH` 를 **호출 시점에** 읽고(회귀가 임시 DB 로 갈아끼울 수 있어야 한다)
#    busy_timeout 까지 같은 값으로 건다. 복제하면 둘 중 하나만 고쳐진다.
from backend.services.disposal import read_only

# `04 §9` 어휘 재노출 — 라우터가 HTTP 를 매핑할 때 쓴다. 정본은 `data/ownership.py` 다.
STATUSES = _own.STATUSES
NOT_FOUND_REASONS = _own.NOT_FOUND_REASONS
CATEGORIES = _own.CATEGORIES


def verify(
    *,
    asset_id: str | None = None,
    equipment_id: str | None = None,
    db_path: str | None = None,
) -> dict:
    """실사 판정 1건. 반환은 MCP 도구와 **같은 dict** 다 (`04 §9`).

    예외를 던지지 않고 `status` 로 닫는다 (D9) — 라우터가 status→HTTP 만 매핑하면 되도록.
    `AssetNotFound` 같은 예외를 쓰지 않는 이유: `not_found` 의 세 reason
    (`unknown_asset`·`unknown_equipment`·`no_host_asset`)이 **본문에 사유로 실려야** 하는데,
    예외로 올리면 라우터가 그 사유를 다시 조립하게 되고 문구가 두 벌이 된다.
    """
    try:
        with read_only(db_path) as con:
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


def verify_ref(ref: str, db_path: str | None = None) -> dict:
    """URL 경로 식별자 1칸으로 자산·설비를 **등록부에서 판별해** 판정한다.

    MCP 도구는 `asset_id`·`equipment_id` 를 따로 받지만 URL 에는 칸이 하나뿐이다.
    그래서 **추측이 아니라 조회로** 가른다 — `assets` 에 있으면 자산, 아니면 `equipment`
    에 있는지 보고, 둘 다 아니면 자산으로 넘겨 `unknown_asset` 이 나오게 한다
    (`/api/assets` 경로에서 모르는 식별자는 자산 미등록으로 읽는 게 맞다).

    ★ `INV-L1-01`(분전반)이 이 분기의 존재 이유다. 설비로 판별돼 `no_host_asset` 이
      나와야 하며, 그건 **"문제 없음"이 아니라 "실사 대상이 아니다"** 라는 사유다.
      자산으로만 조회하면 `unknown_asset` 이 되어 그 사유가 사라진다.

    ⛔ 폴백이 아니다 — 어느 쪽으로도 판별되지 않은 식별자를 **고쳐 주지 않는다**.

    판별 조회의 실패도 `verify()` 와 **같은 status 어휘**로 닫는다 (D9). 판별에서만 예외가
    새면 같은 장애가 경로에 따라 500 트레이스백과 `status:"error"` 로 갈린다.
    """
    try:
        with read_only(db_path) as con:
            known_asset = (
                con.execute("SELECT 1 FROM assets WHERE asset_id = ?", (ref,)).fetchone()
                is not None
            )
            known_equipment = not known_asset and (
                con.execute("SELECT 1 FROM equipment WHERE equipment_id = ?", (ref,)).fetchone()
                is not None
            )
    except sqlite3.Error as e:
        return {"status": "error", "reason": "db_error", "message": str(e)}
    except Exception as e:  # noqa: BLE001
        return {
            "status": "error",
            "reason": "internal_error",
            "message": f"{type(e).__name__}: {e}",
        }

    if known_equipment:
        return verify(equipment_id=ref, db_path=db_path)
    return verify(asset_id=ref, db_path=db_path)
