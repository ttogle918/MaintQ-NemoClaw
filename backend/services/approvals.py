# -*- coding: utf-8 -*-
"""통합 승인 큐 — 발주·처분·(수리)를 한 목록으로 조립한다 (D85).

────────────────────────────────────────────────────────────────────────────────
★ `/api/po` 를 확장하지 않고 새 경로를 만든 이유 (D85)
────────────────────────────────────────────────────────────────────────────────
`services/po.py` 의 `_PO_SELECT` 는 `parts`·`suppliers` 를 JOIN 한다 — 처분서를 그 형태에
담으면 **응답의 절반이 NULL** 이 된다. 더 무거운 이유는 `/api/po` 에 `spikes/api_contract.py`
28건 + 프론트 `mappers.tsx` + 완료 기준 *"권한 위반 403 차단 100%"* 의 판정 경로가 걸려
있다는 것이다. 형태를 흔들면 **지표가 흔들린다.**

그래서 이 모듈은 **읽기 전용 조립기**다. 원본 서비스의 함수를 그대로 호출해 공통 형태로
투영할 뿐, `/api/po` 의 경로·응답에는 한 줄도 손대지 않는다.

────────────────────────────────────────────────────────────────────────────────
★ `state` 를 공통 어휘로 정규화하지 않는다
────────────────────────────────────────────────────────────────────────────────
발주의 `approved` 와 처분의 `signed` 는 **다른 사건**이다. 한 필드로 뭉개면 D39·D63 이
구분해 둔 책임 귀속이 API 경계에서 사라진다. 그래서 `state` 는 **각 종류의 원 문자열
그대로** 싣고, "무엇으로 보이게 할 것인가"는 프론트의 전역 매퍼(D87)가 정한다.

★ 지어내지 않는 필드
  `urgency`  — 처분서에는 긴급도 개념이 없다 → **`null`**. `normal` 로 채우면 없는 사실이 생긴다.
  `verdict`·`requires_override` — 발주에는 판정이 없다 → **`null`**. `false` 는 "차단 아님"
                                  이라는 **주장**이 되므로 쓰지 않는다 (D62 태도).

★ `repair` 는 Sprint 9(MQ-909)부터 실제로 채워진다.
  enum 에 미리 넣어 둔 덕분에 Sprint 9 가 **계약 변경 없이** `repair_records` 를 연결한다.
  시드 12건(11 signed + 1 draft) 이 전부 필터 없는 조회에 그대로 나온다 — "0건이 정상"이던
  옛 서술은 사실이 아니게 됐다.
"""

from __future__ import annotations


from backend.services import decisions as dec_svc
from backend.services import po as po_svc
from backend.services import repairs as repair_svc

# 판별자. 셋 다 실제로 채워진다 (Sprint 9 부터 `repair` 도 포함).
KINDS: tuple[str, ...] = ("po", "disposal", "repair")


class InvalidKind(ValueError):
    """`KINDS` 밖의 값 → 422. 모르는 종류를 0건으로 돌려주면 오타가 '해당 없음'으로 읽힌다."""

    def __init__(self, value: object) -> None:
        self.value = value
        super().__init__(f"kind 는 {'|'.join(KINDS)} 이어야 합니다: {value!r}")


def _po_item(po: dict) -> dict:
    qty = po.get("qty")
    name = po.get("part_name") or po.get("part_no") or ""
    return {
        "kind": "po",
        "id": po["po_id"],
        "title": f"{name} ×{qty}" if qty is not None else name,
        "state": po["state"],  # 원 어휘 그대로 (draft|pending|approved|rejected)
        "urgency": po.get("urgency"),
        "requested_by": po.get("requested_by"),
        "requested_by_name": po.get("requested_by_name") or "",
        "created_at": po.get("created_at"),
        "detail_path": f"/api/po/{po['po_id']}",
        "verdict": None,  # 발주에는 처분 판정이 없다 — false 가 아니라 null 이다
        "requires_override": None,
    }


def _decision_item(d: dict) -> dict:
    mode = d.get("disposal_mode") or "SALE"
    label = dec_svc.DISPOSAL_MODE_LABELS.get(mode, mode)
    return {
        "kind": "disposal",
        "id": d["decision_id"],
        "title": f"{d['asset_id']} {label} 처분",
        "state": d["state"],  # 원 어휘 그대로 (draft|pending|signed|rejected)
        "urgency": None,  # 처분서에는 긴급도가 없다 — 지어내지 않는다
        "requested_by": d.get("requested_by"),
        "requested_by_name": d.get("requested_by_name") or "",
        "created_at": d.get("created_at"),
        "detail_path": f"/api/decisions/{d['decision_id']}",
        "verdict": d.get("verdict_at_signing"),
        "requires_override": d.get("requires_override"),
    }


def _repair_item(r: dict) -> dict:
    label = repair_svc.WORK_TYPE_LABELS.get(r.get("work_type"), r.get("work_type"))
    return {
        "kind": "repair",
        "id": r["repair_id"],
        "title": f"{r['equipment_id']} 수리 · {label}",
        "state": r["state"],  # 원 어휘 그대로 (draft|pending|signed|rejected)
        "urgency": None,  # 수리 증빙에는 긴급도가 없다 — 지어내지 않는다
        "requested_by": r.get("requested_by"),
        "requested_by_name": r.get("requested_by_name") or "",
        "created_at": r.get("created_at"),
        "detail_path": f"/api/repairs/{r['repair_id']}",
        "verdict": None,  # 수리 증빙에는 처분 판정이 없다 — false 가 아니라 null 이다
        "requires_override": None,
    }


def list_approvals(
    state: str | None = None,
    kind: str | None = None,
    db_path: str | None = None,
) -> list[dict]:
    """통합 큐. `created_at DESC` 정렬.

    ⚠ `/api/po` 의 정렬(긴급 우선)을 여기로 옮기지 않는다 — 통합 큐에 발주 전용 정렬 규칙을
      끌어오면 처분서가 항상 뒤로 밀린다. 두 목록은 정렬 기준이 다른 게 정상이다.
    """
    if kind is not None and kind not in KINDS:
        raise InvalidKind(kind)

    items: list[dict] = []
    if kind in (None, "po"):
        items += [_po_item(p) for p in po_svc.list_pos(state, db_path)]
    if kind in (None, "disposal"):
        items += [_decision_item(d) for d in dec_svc.list_decisions(state, db_path)]
    if kind in (None, "repair"):
        items += [_repair_item(r) for r in repair_svc.list_repairs(state, db_path)]

    items.sort(key=lambda i: (i.get("created_at") or "", i["id"]), reverse=True)
    return items
