"""처분 문서 문안의 **사람 검수 상태** — `backend` 와 `mcp_server` 가 함께 읽는다 (D73).

왜 `data/` 에 있나
────────────────────────────────────────────────────────────────────────────────
같은 고지 문구가 `mcp_server/tools/generate_disposal_document.py` 와
`backend/services/decisions.py` 두 곳에 **리터럴로 중복**돼 있었다. 한쪽만 고치면
다른 쪽이 계속 옛 문구를 내보내고, 그러면 도구 출력과 REST 응답이 갈린다 —
`generate_disposal_document` 독스트링이 경계한 *"W5 가 계층 1에서 겪은 이원화의 반복"* 그대로다.

`data/` 는 두 프로세스가 공유해도 되는 데이터 계층이고(**D73**), 금지되는 것은
`backend` ↔ `mcp_server` **상호 import** 다. `data/ownership.py` 와 같은 자리·같은 이유다.

⛔ 문구를 하드코딩하지 않고 플래그에서 유도한다
────────────────────────────────────────────────────────────────────────────────
검수가 끝난 뒤에도 "미검수"라고 계속 출력하면 **거짓 경고**가 되고, 경고를 지우면
미검수가 조용히 넘어간다. `data/seed.py` 의 `part_class_caveat()` 과 같은 형태다.
"""

from __future__ import annotations

# 처분 승인서·진술보장서 문안의 사람 검수 여부.
#
# 승인 이력 (related_parts.seed.json 의 `_승인_이력`·seed.py 의 PART_CLASS_REVIEWED 와 같은 수준):
#   2026-08-13 · 사용자 — 19시나리오(판정 5종 전부) 렌더링본을 확인하고 **문안 수정 없이 승인**.
#     검수 자료: `data/analysis/disposal_docs_review.md`
#     함께 확인한 5개 지점을 모두 현행대로 수용한다:
#       ① 진술보장서가 시스템 보유값을 매도인이 "보장"하는 구조
#       ② BLOCKED 문서에 "위반 위험" 과 "자동 차단하지 않는다" 가 함께 오는 것
#       ③ 결재 문서에 `확인되지 않음` 이 남은 채 올라가는 것
#       ④ "근거 (해시 고정)" 절 아래에 해시가 없는 계약 근거가 함께 오는 것
#       ⑤ 매도인/승인자/서명자 호칭 혼용
TEMPLATE_REVIEWED = True
TEMPLATE_REVIEWED_AT = "2026-08-13"

# ── 정비·부품 발주요청서 (02, D118) — data/templates/02_정비부품발주요청서.docx 문구를
#    옮긴 렌더 문안. 아직 사람이 검수하지 않았다 — 승인 전까지는 아래를 False 로 둔다.
PO_REQUEST_TEMPLATE_REVIEWED = False
PO_REQUEST_TEMPLATE_REVIEWED_AT: str | None = None

# ── 설비 이상 진단 보고서 (01, D118) — 같은 이유로 미검수.
DIAGNOSIS_TEMPLATE_REVIEWED = False
DIAGNOSIS_TEMPLATE_REVIEWED_AT: str | None = None

# ── 자금집행요청서 (03, D118·D119) — data/templates/03_자금집행요청서.docx 문구를
#    옮긴 렌더 문안. 아직 사람이 검수하지 않았다 — 승인 전까지는 아래를 False 로 둔다.
FUND_EXECUTION_TEMPLATE_REVIEWED = False
FUND_EXECUTION_TEMPLATE_REVIEWED_AT: str | None = None


def _notice(reviewed: bool, reviewed_at: str | None) -> str:
    """문서 본문·API 응답에 함께 싣는 문안 검수 상태 한 줄.

    ⚠ **검수가 끝나도 줄을 없애지 않는다.** 법적 효력이 있는 문서라
    *"언제 누가 검수했는가"* 가 남는 편이 낫다 — 침묵은 검수 여부를 알려주지 않는다.
    """
    if not reviewed:
        return "문서 문안은 미검수 초안이다 (TODO_직접할일.md)"
    return f"문안 사람 검수 완료 ({reviewed_at})"


def template_review_notice() -> str:
    """처분 승인서·진술보장서(기존)의 검수 상태 — 하위호환을 위해 인자 없이 유지."""
    return _notice(TEMPLATE_REVIEWED, TEMPLATE_REVIEWED_AT)


def po_request_template_review_notice() -> str:
    return _notice(PO_REQUEST_TEMPLATE_REVIEWED, PO_REQUEST_TEMPLATE_REVIEWED_AT)


def diagnosis_template_review_notice() -> str:
    return _notice(DIAGNOSIS_TEMPLATE_REVIEWED, DIAGNOSIS_TEMPLATE_REVIEWED_AT)


def fund_execution_template_review_notice() -> str:
    return _notice(FUND_EXECUTION_TEMPLATE_REVIEWED, FUND_EXECUTION_TEMPLATE_REVIEWED_AT)
