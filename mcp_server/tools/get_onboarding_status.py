# -*- coding: utf-8 -*-
"""get_onboarding_status — 기종별 온보딩 진행 현황 (읽기 전용, D154, `onboarding`
프로파일 전용, docs/04_MCP_TOOLS.md §25).

승격 여부·검수 진행률을 한눈에 보여준다 — 사람 검수·승격·안전 문구 승인 전 화면과
데모 스크립트가 진행 상황을 확인하는 자리다.
"""

from __future__ import annotations

from ..db import read_only

DESCRIPTION = (
    "기종 하나의 온보딩 진행 현황(배치 수, 스테이징 행 상태별 개수, 정규화 완료·저신뢰 "
    "행 수, 승격된 코드 수, 안전 문구 후보 상태)을 조회한다. 읽기 전용."
)

VALID_MODELS = ("iG5A", "S100", "IE5", "HV600")

_STATES = ("staged", "approved", "rejected")


def get_onboarding_status(model: str) -> dict:
    if model not in VALID_MODELS:
        return {
            "status": "error",
            "reason": "invalid_model",
            "message": f"model 은 {' | '.join(VALID_MODELS)} 이어야 합니다: {model!r}",
        }

    try:
        with read_only() as con:
            batches = con.execute(
                "SELECT count(*) AS n FROM onboarding_batches WHERE model = ?", (model,)
            ).fetchone()["n"]

            rows = dict.fromkeys(_STATES, 0)
            for r in con.execute(
                "SELECT state, count(*) AS n FROM onboarding_code_rows"
                " WHERE model = ? GROUP BY state",
                (model,),
            ).fetchall():
                rows[r["state"]] = r["n"]

            normalized_rows = con.execute(
                "SELECT count(DISTINCT r.row_id) AS n"
                " FROM onboarding_code_rows r"
                " JOIN onboarding_normalizations n ON n.row_id = r.row_id"
                " WHERE r.model = ?",
                (model,),
            ).fetchone()["n"]

            low_confidence_rows = con.execute(
                "SELECT count(*) AS n FROM ("
                "  SELECT n.confidence FROM onboarding_code_rows r"
                "  JOIN onboarding_normalizations n ON n.row_id = r.row_id"
                "  JOIN ("
                "    SELECT row_id, MAX(norm_id) AS max_norm_id"
                "    FROM onboarding_normalizations GROUP BY row_id"
                "  ) latest ON latest.row_id = n.row_id AND latest.max_norm_id = n.norm_id"
                "  WHERE r.model = ?"
                ") t WHERE t.confidence = 'low'",
                (model,),
            ).fetchone()["n"]

            promoted_codes = con.execute(
                "SELECT count(*) AS n FROM onboarding_promotions WHERE model = ?", (model,)
            ).fetchone()["n"]

            safety = dict.fromkeys(_STATES, 0)
            for r in con.execute(
                "SELECT state, count(*) AS n FROM onboarding_safety_candidates"
                " WHERE model = ? GROUP BY state",
                (model,),
            ).fetchall():
                safety[r["state"]] = r["n"]
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "reason": "db_error", "message": str(e)}

    return {
        "status": "ok",
        "model": model,
        "batches": batches,
        "rows": rows,
        "normalized_rows": normalized_rows,
        "low_confidence_rows": low_confidence_rows,
        "promoted_codes": promoted_codes,
        "safety": safety,
    }
