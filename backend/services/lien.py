# -*- coding: utf-8 -*-
"""LIEN-CONSENT 해소 — `assets.lien_consent_ref` 쓰기.

**왜 이 파일이 따로 있는가:** 라우터에 인라인하면 아래 두 불변식이 HTTP 계층에 묻혀
테스트하기 어려워진다. 이 레포에서 제일 조심해야 할 쓰기이므로 순수 함수로 분리한다.

**왜 `flags` 가 아니라 `assets` 인가:** LIEN-CONSENT 룰이 읽는 필드는
`lien_consent_ref` 하나다(`data/rules/rules/LIEN-CONSENT.json` —
trigger: `has_lien eq true` AND `lien_consent_ref is_null`). `flags` 테이블은 해소
라이프사이클이 설계돼 있으나 **쓰기 경로가 없어 0행**이고 룰 평가에 관여하지 않는다 —
거기 쓰는 것은 해소가 아니라 해소한 척이다.
"""

from __future__ import annotations

from backend.db import connect


def resolve_lien_consent(
    decision_id: str, settlement_ref: str, db_path: str | None = None
) -> bool:
    """FinAllQ 정산 판정으로 근저당이 말소됐음을 기록한다. 갱신했으면 `True`.

    LIEN-CONSENT `resolve_options[1]` "대출 상환 후 근저당 말소"의 자동화다.

    🔴 **결정을 서명하지 않는다.** 담보만 풀고 서명은 사람이 한다 —
    "서명 없는 처분 확정 0건" 불변식을 A2A 경로로 우회하지 않는다. `assess-loan` 이
    conditional 판정을 받아도 대출을 자동 실행하지 않는 것과 같은 태도다.

    🔴 **빈 참조를 쓰지 않는다.** `''` 는 `is_null` 을 False 로 만들어 BLOCKING 룰을
    조용히 미발화시킨다(`seed.py` 검사 ⑱). 규약은 `''`="확인된 해당 없음" /
    `NULL`="모름" 이고, A2A 정산은 둘 중 어느 것도 아니다.
    """
    ref = (settlement_ref or "").strip()
    if not ref:
        raise ValueError(
            "빈 참조로 LIEN-CONSENT 를 해소할 수 없다 — 빈 문자열은 BLOCKING 룰을 "
            "조용히 미발화시킨다(seed.py 검사 ⑱)."
        )

    with connect(db_path) as con:
        row = con.execute(
            "SELECT d.asset_id, a.lien_consent_ref FROM decisions d"
            " JOIN assets a ON a.asset_id = d.asset_id"
            " WHERE d.decision_id = ?",
            (decision_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"알 수 없는 decision_id: {decision_id}")
        if row["lien_consent_ref"] is not None:
            # 이미 근거가 있다 — A2A 참조로 덮어쓰면 기존 동의서 출처가 사라진다.
            return False

        con.execute(
            "UPDATE assets SET lien_consent_ref = ? WHERE asset_id = ?",
            (ref, row["asset_id"]),
        )
    return True
