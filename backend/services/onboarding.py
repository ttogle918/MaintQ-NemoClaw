# -*- coding: utf-8 -*-
"""온보딩 스테이징 → 정본 승격·안전 문구 승인 서비스 (D154·D156·D157, MQ-1909).

**상태 전이·정본 쓰기는 이 서비스만 한다.** MCP 도구(`stage_code_normalization`)는
스테이징 4테이블 INSERT 만 하고(D10·D154), `error_codes`·`manual_chunks`·
`onboarding_promotions` 쓰기와 `onboarding_code_rows`/`onboarding_safety_candidates`의
`staged→approved/rejected` 전이는 전부 여기(`backend/routers/onboarding.py`)를 거친다
(`routers/po.py`·`routers/decisions.py`와 같은 태도 — D10·D81).

⚠ 사람 커넥션(`backend.db.connect()`)만 쓴다 — MCP 가드 커넥션(`mcp_server.db.*`)과
섞지 않는다(둘은 프로세스가 다르다, D15).

병합 규칙 전문은 `docs/10_DECISIONS.md` D156 — 여기서 다시 옮기지 않는다.
"""

from __future__ import annotations

import json
import re
import sqlite3
from itertools import zip_longest

from backend.agent import prompts
from backend.agent.safety_source import SEED_MODELS
from backend.agent.safety_source import resolve as resolve_safety
from backend.db import connect
from backend.services.decisions import now_utc_sql
from data.doc_fields import iso_utc

#: 시드 3기종은 파일이 정본(D148) — 온보딩 승격 대상이 아니다.
#: 정의는 `backend.agent.safety_source.SEED_MODELS` 한 곳(여기는 재수출 — 순환 import 회피).

#: `data/chunk_manual.py` 와 같은 청크 상한(D53 — 넘으면 나누되 자르지 않는다).
MAX_CHARS = 900

#: 구역명 → 한국어 (고정 사전, LLM 무관). `Backup …` 은 접두 일치로 별도 처리한다.
SECTION_KO: dict[str, str] = {
    "Fault": "고장",
    "Minor Faults/Alarms": "경알람",
    "Parameter Setting Errors": "파라미터 설정 오류",
    "Auto-Tuning Errors": "오토튜닝 오류",
}

_BACKUP_PREFIX = "Backup"
_BACKUP_KO = "백업·복원 오류"

_MINUTE_NUM_RE = re.compile(r"(\d+)\s*분")


def section_ko(section_en: str) -> str:
    """구역 영문명 → 한국어. `SECTION_KO` 고정 사전 + `Backup` 접두 규칙(D156).

    사전에 없는 구역명은 원문을 그대로 돌려준다 — 매뉴얼 원문 구역명 전체를 미리
    다 알 수 없어(HV600 실측 5종만 확인) 매핑 없는 값을 지어내지 않는다(환각 방지,
    절대규칙 6과 같은 태도). 이 fallback 은 명세에 명시돼 있지 않다 — 구현 중 채운
    빈 자리이며 최종 보고에 별도로 적는다.
    """
    if section_en in SECTION_KO:
        return SECTION_KO[section_en]
    if section_en.startswith(_BACKUP_PREFIX):
        return _BACKUP_KO
    return section_en


class OnboardingError(Exception):
    """검증 실패 — 라우터가 `http_status`·`reason`·`message`·`extra` 를 그대로 응답에 싣는다."""

    def __init__(self, http_status: int, reason: str, message: str, **extra: object) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.reason = reason
        self.message = message
        self.extra = extra


def _json_list(raw: object) -> list:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return raw
    value = json.loads(raw)
    return value if isinstance(value, list) else []


def _pages(raw: object) -> list[int]:
    pages = _json_list(raw)
    return [int(p) for p in pages]


def _ordered_rows(rows: list[dict], primary_row_id: int) -> list[dict]:
    """primary 행 먼저, 나머지는 `ordinal` 오름차순 (D156 순서 규칙)."""
    primary = next(r for r in rows if r["row_id"] == primary_row_id)
    rest = sorted((r for r in rows if r["row_id"] != primary_row_id), key=lambda r: r["ordinal"])
    return [primary, *rest]


def build_error_code_row(
    rows: list[dict], norms: dict[int, dict], primary_row_id: int, manual_id: str
) -> dict:
    """D156 병합 규칙 — 병합된 `error_codes` 행 1개를 만든다 (DB 접근 없는 순수 함수).

    `rows` 의 각 항목은 최소 `row_id`·`ordinal`·`model`·`code`·`display_code`·
    `section_en`·`name_en`·`causes_en`·`pages`·`norm_id` 를 담아야 한다.
    `norms` 는 `{norm_id: {name_ko, causes_ko, ...}}`.
    """
    ordered = _ordered_rows(rows, primary_row_id)
    primary = ordered[0]
    primary_norm = norms[primary["norm_id"]]
    multi = len(ordered) > 1

    causes: list[str] = []
    actions: list[str] = []
    seen_actions: set[str] = set()
    for row in ordered:
        norm = norms[row["norm_id"]]
        prefix = f"[{section_ko(row['section_en'])}·{norm['name_ko']}] " if multi else ""
        for item in _json_list(norm["causes_ko"]):
            cause_text = (item.get("cause") or "").strip()
            if cause_text:
                causes.append(f"{prefix}{cause_text}")
            for sol in item.get("solutions") or []:
                sol_text = (sol or "").strip()
                if not sol_text:
                    continue
                text = f"{prefix}{sol_text}"
                if text not in seen_actions:
                    seen_actions.add(text)
                    actions.append(text)

    severity = "fault" if primary["section_en"] == "Fault" else "warning"
    manual_page = min(_pages(primary["pages"]))

    return {
        "model": primary["model"],
        "code": primary["code"],
        "display_code": primary["display_code"],
        "error_name": f"{primary_norm['name_ko']} ({primary['name_en']})",
        "severity": severity,
        "causes": causes,
        "actions": actions,
        "related_parts": [],
        "manual_page": manual_page,
        "actions_manual_id": manual_id,
        "actions_page": manual_page,
    }


def _cause_parts(ko_item: dict, en_item: dict) -> tuple[str, str]:
    """원인 1건 → (한국어 부분, 원문 부분). 청크 분할의 최소 단위다(D53 — 원인 안에서는 자르지 않는다).

    빈 `cause`·빈 `solutions` 는 해당 줄을 생략한다(빈 「원인: 」 줄을 만들지 않는다).
    """
    cause_ko = (ko_item.get("cause") or "").strip()
    sol_ko = "; ".join(s.strip() for s in (ko_item.get("solutions") or []) if (s or "").strip())
    cause_en = (en_item.get("cause") or "").strip()
    sol_en = "; ".join(s.strip() for s in (en_item.get("solutions") or []) if (s or "").strip())
    ko_lines = []
    if cause_ko:
        ko_lines.append(f"원인: {cause_ko}")
    if sol_ko:
        ko_lines.append(f"조치: {sol_ko}")
    en_body = " / ".join(x for x in (cause_en, sol_en) if x)
    return "\n".join(ko_lines), (f"[원문] {en_body}" if en_body else "")


def _render(header: str, parts: list[tuple[str, str]]) -> str:
    """D156 청크 본문 — 헤더 → 한국어 원인·조치 줄들 → `[원문]` 줄들."""
    ko = [k for k, _ in parts if k]
    en = [e for _, e in parts if e]
    return "\n".join([header, *ko, *en])


def _pack_chunks(header: str, parts: list[tuple[str, str]], max_chars: int) -> list[str]:
    """원인 단위로 그리디 패킹해 `max_chars` 이하 청크들을 만든다.

    **자르지 않는다(D53)** — 원인 1건만으로 이미 `max_chars` 를 넘으면 그 원인 하나로
    청크 하나를 만든다(초과를 허용하지, 문장을 잘라내지 않는다).
    """
    if not parts:
        return [header]
    packed: list[str] = []
    current: list[tuple[str, str]] = []
    for part in parts:
        candidate = [*current, part]
        if not current or len(_render(header, candidate)) <= max_chars:
            current = candidate
        else:
            packed.append(_render(header, current))
            current = [part]
    packed.append(_render(header, current))
    return packed


def build_chunks(rows: list[dict], norms: dict[int, dict], manual_id: str) -> list[dict]:
    """D156 청크 규칙 — 포함 행마다 청크 1건 이상 (DB 접근 없는 순수 함수).

    `rows` 의 각 항목은 `build_error_code_row` 와 같은 최소 필드를 담아야 한다.
    """
    chunks: list[dict] = []
    for row in rows:
        norm = norms[row["norm_id"]]
        causes_ko_items = _json_list(norm["causes_ko"])
        causes_en_items = _json_list(row["causes_en"])
        header = (
            f"[{row['display_code']}] {norm['name_ko']} ({row['name_en']})"
            f" — {section_ko(row['section_en'])}"
        )
        # zip_longest — 모양이 어긋나도(적재 시 `shape_matches` 가 막지만) 원인을 조용히 버리지 않는다.
        parts = [
            _cause_parts(ko_item or {}, en_item or {})
            for ko_item, en_item in zip_longest(causes_ko_items, causes_en_items, fillvalue={})
        ]
        texts = _pack_chunks(header, parts, MAX_CHARS)
        page = min(_pages(row["pages"]))
        section = f"Troubleshooting · {row['section_en']}"
        base_id = f"{manual_id}-onb-{row['code'].lower()}-r{row['row_id']}"
        multi = len(texts) > 1
        for i, text in enumerate(texts, start=1):
            chunk_id = f"{base_id}-c{i}" if multi else base_id
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "manual_id": manual_id,
                    "model": row["model"],
                    "page": page,
                    "section": section,
                    "text": text,
                    "char_len": len(text),
                }
            )
    return chunks


# ── DB 접근 함수 ─────────────────────────────────────────────────────────────


def list_batches() -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT b.batch_id, b.model, b.manual_id, b.loaded_at,"
            " (SELECT count(*) FROM onboarding_code_rows r"
            "  WHERE r.batch_id = b.batch_id) AS rows,"
            " (SELECT count(*) FROM onboarding_code_rows r"
            "  WHERE r.batch_id = b.batch_id AND r.state = 'staged') AS staged,"
            " (SELECT count(*) FROM onboarding_code_rows r"
            "  WHERE r.batch_id = b.batch_id AND r.state = 'approved') AS approved,"
            " (SELECT count(*) FROM onboarding_code_rows r"
            "  WHERE r.batch_id = b.batch_id AND r.state = 'rejected') AS rejected,"
            " (SELECT count(DISTINCT n.row_id) FROM onboarding_normalizations n"
            "  JOIN onboarding_code_rows r2 ON r2.row_id = n.row_id"
            "  WHERE r2.batch_id = b.batch_id) AS normalized_rows"
            " FROM onboarding_batches b ORDER BY b.batch_id"
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["loaded_at"] = iso_utc(d["loaded_at"])  # D39 — UTC 명시(Z)
        out.append(d)
    return out


def list_groups(batch_id: int, state: str) -> list[dict]:
    if state not in ("staged", "all"):
        raise OnboardingError(422, "invalid_state", f"state 는 staged|all 이어야 합니다: {state!r}")

    with connect() as con:
        batch = con.execute(
            "SELECT batch_id, model FROM onboarding_batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        if not batch:
            raise OnboardingError(404, "batch_not_found", f"batch_id {batch_id} 가 없습니다")
        model = batch["model"]

        sql = (
            "SELECT row_id, ordinal, model, code, display_code, section_en, name_en,"
            " causes_en, pages, source_flags, state"
            " FROM onboarding_code_rows WHERE batch_id = ?"
        )
        args: list[object] = [batch_id]
        if state == "staged":
            sql += " AND state = 'staged'"
        sql += " ORDER BY code, ordinal"
        rows = con.execute(sql, args).fetchall()

        row_ids = [r["row_id"] for r in rows]
        norms_by_row: dict[int, list[dict]] = {rid: [] for rid in row_ids}
        if row_ids:
            placeholders = ",".join(["?"] * len(row_ids))
            norm_rows = con.execute(
                "SELECT norm_id, row_id, name_ko, causes_ko, confidence, flags,"
                " staged_by, created_at FROM onboarding_normalizations"
                f" WHERE row_id IN ({placeholders}) ORDER BY row_id, norm_id DESC",
                row_ids,
            ).fetchall()
            for nr in norm_rows:
                norms_by_row[nr["row_id"]].append(dict(nr))

        promoted_codes = {
            r["code"] for r in con.execute("SELECT code FROM error_codes WHERE model = ?", (model,)).fetchall()
        }

    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["code"], []).append(dict(r))

    out: list[dict] = []
    for code, group_rows in groups.items():
        out.append(
            {
                "model": model,
                "code": code,
                "promoted": code in promoted_codes,
                "rows": [
                    {
                        "row_id": gr["row_id"],
                        "ordinal": gr["ordinal"],
                        "display_code": gr["display_code"],
                        "section_en": gr["section_en"],
                        "section_ko": section_ko(gr["section_en"]),
                        "name_en": gr["name_en"],
                        "causes_en": _json_list(gr["causes_en"]),
                        "pages": _pages(gr["pages"]),
                        "source_flags": _json_list(gr["source_flags"]),
                        "state": gr["state"],
                        "norms": [
                            {
                                "norm_id": n["norm_id"],
                                "name_ko": n["name_ko"],
                                "causes_ko": _json_list(n["causes_ko"]),
                                "confidence": n["confidence"],
                                "flags": _json_list(n["flags"]),
                                "staged_by": n["staged_by"],
                                "created_at": iso_utc(n["created_at"]),
                            }
                            for n in norms_by_row.get(gr["row_id"], [])
                        ],
                    }
                    for gr in group_rows
                ],
            }
        )
    return out


def get_status(model: str) -> dict:
    if model not in prompts.MODELS:
        raise OnboardingError(
            422, "invalid_model", f"model 은 {'|'.join(prompts.MODELS)} 이어야 합니다: {model!r}"
        )
    with connect() as con:
        batches = con.execute(
            "SELECT count(*) AS n FROM onboarding_batches WHERE model = ?", (model,)
        ).fetchone()["n"]
        promoted = con.execute(
            "SELECT count(*) AS n FROM onboarding_promotions WHERE model = ?", (model,)
        ).fetchone()["n"]

    if batches == 0:
        return {"model": model, "state": "none"}
    if promoted == 0:
        return {"model": model, "state": "onboarding"}

    # D157 — 판정을 두 벌로 만들지 않는다. MQ-1910 `safety_source.resolve()` 를 그대로 호출한다
    # (정확히 1건 승인일 때만 값, 0·2건·DB 예외는 None = fail closed → safety_pending).
    entry = resolve_safety(model)
    return {"model": model, "state": "ready" if entry is not None else "safety_pending"}


def _advisory_lock(con, key: str) -> None:
    """트랜잭션 단위 advisory lock — 같은 `(model, code)` 승격·같은 기종 안전 승인을 직렬화한다.

    검증(SELECT)과 쓰기 사이의 경합 창을 닫는다. DB 제약(`error_codes` PK·
    `onboarding_promotions UNIQUE`)이 최후 방어선이지만, D157 의 「기종당 승인 1건」은
    DB 제약이 없어 여기서만 막힌다(2건이 되면 resolve 가 None 으로 fail closed 할 뿐이다).
    """
    con.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (key,)).fetchone()


def _integrity_reason(exc: Exception) -> tuple[int, str]:
    """쓰기 단계 제약 위반 → (HTTP, reason). 모르는 위반은 422 `integrity`."""
    msg = str(exc)
    if "manual_chunks" in msg:
        return 409, "chunk_id_conflict"
    if "error_codes" in msg or "onboarding_promotions" in msg:
        return 409, "already_promoted"
    return 422, "integrity"


def _reject_seed_model(model: str) -> None:
    """시드 3기종은 온보딩 승격·안전 문구 승인 대상이 아니다 (D148·D109 ⓐ).

    iG5A·S100 의 안전 문구는 `prompts.SAFETY_BASELINE` 정적 상수가 정본이고, IE5 는
    안전 문구를 확장하지 않는다(D109 ⓐ). 시드 기종 후보가 DB 에서 승인되면
    `safety_source.resolve()` 가 IE5 에 대해 값을 돌려줄 수 있으므로 여기서 막는다
    (resolve 쪽에도 같은 방어가 있다 — 이중화).
    """
    if model in SEED_MODELS:
        raise OnboardingError(
            422,
            "seed_model_not_onboardable",
            f"{model} 은 시드 기종이라 온보딩 승격·안전 문구 승인 대상이 아닙니다(D148·D109, 파일이 정본)",
        )


def promote(
    *,
    model: str,
    code: str,
    primary_row_id: int,
    rows_in: list[dict],
    acknowledged_flags: list[str],
    promoted_by: str,
) -> dict:
    """`POST /promote` 핵심 로직 (D156). 하나라도 실패하면 아무것도 쓰지 않는다."""
    model = (model or "").strip()
    code = (code or "").strip().upper()

    if model not in prompts.MODELS:
        raise OnboardingError(
            422, "invalid_model", f"model 은 {'|'.join(prompts.MODELS)} 이어야 합니다: {model!r}"
        )
    _reject_seed_model(model)
    if not rows_in:
        raise OnboardingError(422, "rows_required", "rows 는 최소 1건 이상이어야 합니다")

    norm_by_row: dict[int, int] = {}
    for r in rows_in:
        rid = int(r["row_id"])
        if rid in norm_by_row:
            # 같은 row_id 를 두 번 보내면 어느 norm 을 쓸지 모호하다 — 조용히 하나를 고르지 않는다.
            raise OnboardingError(
                422, "duplicate_row", f"row_id {rid} 가 rows 에 두 번 있습니다", row_ids=[rid]
            )
        norm_by_row[rid] = int(r["norm_id"])
    row_ids = list(norm_by_row.keys())

    with connect() as con:
        _advisory_lock(con, f"onboarding-promote:{model}:{code}")

        existing = con.execute(
            "SELECT 1 FROM error_codes WHERE model = ? AND code = ?", (model, code)
        ).fetchone()
        if existing:
            raise OnboardingError(
                409, "already_promoted", f"{model}/{code} 는 이미 승격되었습니다"
            )

        db_rows: dict[int, dict] = {}
        for rid in row_ids:
            row = con.execute(
                "SELECT row_id, batch_id, ordinal, model, code, display_code, section_en,"
                " name_en, causes_en, pages, source_flags, state"
                " FROM onboarding_code_rows WHERE row_id = ? FOR UPDATE",
                (rid,),
            ).fetchone()
            if not row:
                raise OnboardingError(404, "row_not_found", f"row_id {rid} 가 없습니다")
            db_rows[rid] = dict(row)

        mismatched = [
            rid for rid, row in db_rows.items() if row["model"] != model or row["code"] != code
        ]
        if mismatched:
            raise OnboardingError(
                422,
                "mixed_group",
                f"row_id {mismatched} 는 {model}/{code} 그룹이 아닙니다",
                row_ids=mismatched,
            )

        not_staged = [rid for rid, row in db_rows.items() if row["state"] != "staged"]
        if not_staged:
            raise OnboardingError(
                409,
                "row_not_staged",
                f"row_id {not_staged} 는 staged 상태가 아닙니다",
                row_ids=not_staged,
            )

        if primary_row_id not in db_rows:
            raise OnboardingError(
                422,
                "primary_row_not_in_rows",
                f"primary_row_id {primary_row_id} 가 rows 목록에 없습니다",
            )

        norms: dict[int, dict] = {}
        for rid, norm_id in norm_by_row.items():
            norm_row = con.execute(
                "SELECT norm_id, row_id, name_ko, causes_ko, flags"
                " FROM onboarding_normalizations WHERE norm_id = ?",
                (norm_id,),
            ).fetchone()
            if not norm_row or norm_row["row_id"] != rid:
                raise OnboardingError(
                    422,
                    "norm_mismatch",
                    f"norm_id {norm_id} 는 row_id {rid} 소속이 아닙니다",
                    row_id=rid,
                    norm_id=norm_id,
                )
            db_rows[rid]["norm_id"] = norm_id
            norms[norm_id] = dict(norm_row)

        staged_group = con.execute(
            "SELECT row_id FROM onboarding_code_rows"
            " WHERE model = ? AND code = ? AND state = 'staged'",
            (model, code),
        ).fetchall()
        staged_ids = {r["row_id"] for r in staged_group}
        missing = sorted(staged_ids - set(row_ids))
        if missing:
            raise OnboardingError(
                422,
                "group_incomplete",
                "그룹의 staged 행 중 body 에 없는 행이 있습니다 — 포함하거나 먼저 반려하십시오",
                row_ids=missing,
            )

        needed: set[str] = set()
        for row in db_rows.values():
            needed |= {str(f) for f in _json_list(row["source_flags"])}
        for norm in norms.values():
            needed |= {str(f) for f in _json_list(norm["flags"])}
        ack = {str(f) for f in (acknowledged_flags or [])}
        unacknowledged = sorted(needed - ack)
        if unacknowledged:
            raise OnboardingError(
                422,
                "flags_not_acknowledged",
                "확인하지 않은 플래그가 있습니다",
                flags=unacknowledged,
            )

        primary_batch_id = db_rows[primary_row_id]["batch_id"]
        manual_id = con.execute(
            "SELECT manual_id FROM onboarding_batches WHERE batch_id = ?", (primary_batch_id,)
        ).fetchone()["manual_id"]

        ordered_rows = _ordered_rows(list(db_rows.values()), primary_row_id)
        error_row = build_error_code_row(ordered_rows, norms, primary_row_id, manual_id)
        chunks = build_chunks(ordered_rows, norms, manual_id)

        # ── 쓰기: 한 트랜잭션. 제약 위반은 전부 rollback 후 4xx 로 분류한다 ──
        try:
            con.execute(
                "INSERT INTO error_codes (model, code, display_code, error_name, severity,"
                " causes, actions, related_parts, manual_page, actions_manual_id, actions_page)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    error_row["model"],
                    error_row["code"],
                    error_row["display_code"],
                    error_row["error_name"],
                    error_row["severity"],
                    json.dumps(error_row["causes"], ensure_ascii=False),
                    json.dumps(error_row["actions"], ensure_ascii=False),
                    json.dumps(error_row["related_parts"]),
                    error_row["manual_page"],
                    error_row["actions_manual_id"],
                    error_row["actions_page"],
                ),
            )
            for chunk in chunks:
                con.execute(
                    "INSERT INTO manual_chunks"
                    " (chunk_id, manual_id, model, page, section, text, char_len)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (
                        chunk["chunk_id"],
                        chunk["manual_id"],
                        chunk["model"],
                        chunk["page"],
                        chunk["section"],
                        chunk["text"],
                        chunk["char_len"],
                    ),
                )
            for rid in row_ids:
                cur = con.execute(
                    "UPDATE onboarding_code_rows"
                    " SET state = 'approved', reviewed_by = ?, reviewed_at = ?"
                    " WHERE row_id = ? AND state = 'staged'",
                    (promoted_by, now_utc_sql(), rid),
                )
                if cur.rowcount != 1:
                    con.rollback()
                    raise OnboardingError(
                        409, "row_not_staged", f"row_id {rid} 는 staged 상태가 아닙니다",
                        row_ids=[rid],
                    )
            promo = con.execute(
                "INSERT INTO onboarding_promotions"
                " (model, code, primary_row_id, row_ids, norm_ids, chunk_ids,"
                " acknowledged_flags, promoted_by)"
                " VALUES (?,?,?,?,?,?,?,?) RETURNING promo_id",
                (
                    model,
                    code,
                    primary_row_id,
                    json.dumps([r["row_id"] for r in ordered_rows]),
                    json.dumps([r["norm_id"] for r in ordered_rows]),
                    json.dumps([c["chunk_id"] for c in chunks]),
                    json.dumps(sorted(ack)),
                    promoted_by,
                ),
            ).fetchone()
        except sqlite3.IntegrityError as exc:
            con.rollback()
            http, reason = _integrity_reason(exc)
            raise OnboardingError(http, reason, f"승격 쓰기가 제약에 걸려 전부 되돌렸습니다: {exc}") from exc

    return {
        "promo_id": promo["promo_id"],
        "model": model,
        "code": code,
        "error_code": {
            "code": error_row["code"],
            "display_code": error_row["display_code"],
            "error_name": error_row["error_name"],
            "severity": error_row["severity"],
            "causes": error_row["causes"],
            "actions": error_row["actions"],
            "manual_page": error_row["manual_page"],
            "actions_source": {
                "manual_id": error_row["actions_manual_id"],
                "page": error_row["actions_page"],
            },
        },
        "chunk_ids": [c["chunk_id"] for c in chunks],
    }


def reject_row(*, row_id: int, note: str, reviewed_by: str) -> dict:
    if not (note or "").strip():
        raise OnboardingError(422, "note_required", "note 는 비어 있을 수 없습니다")
    with connect() as con:
        row = con.execute(
            "SELECT row_id, state FROM onboarding_code_rows WHERE row_id = ? FOR UPDATE",
            (row_id,),
        ).fetchone()
        if not row:
            raise OnboardingError(404, "row_not_found", f"row_id {row_id} 가 없습니다")
        if row["state"] != "staged":
            raise OnboardingError(
                409, "row_not_staged", f"row_id {row_id} 는 staged 상태가 아닙니다"
            )
        con.execute(
            "UPDATE onboarding_code_rows"
            " SET state = 'rejected', reviewed_by = ?, reviewed_at = ?,"
            " review_note = ?"
            " WHERE row_id = ? AND state = 'staged'",
            (reviewed_by, now_utc_sql(), note.strip(), row_id),
        )
    return {"row_id": row_id, "state": "rejected"}


def list_safety(model: str) -> list[dict]:
    if model not in prompts.MODELS:
        raise OnboardingError(
            422, "invalid_model", f"model 은 {'|'.join(prompts.MODELS)} 이어야 합니다: {model!r}"
        )
    with connect() as con:
        rows = con.execute(
            "SELECT cand_id, page, also_pages, kind, quote_en, wait_minutes_in_text, state,"
            " approved_text, approved_by, approved_at, text_reviewed_at"
            " FROM onboarding_safety_candidates WHERE model = ? ORDER BY cand_id",
            (model,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["also_pages"] = _pages(d["also_pages"])
        # D39 — 저장은 UTC naive, 전송은 `Z` 붙은 ISO (브라우저가 로컬로 오해하지 않게)
        d["approved_at"] = iso_utc(d["approved_at"]) if d["approved_at"] else None
        d["text_reviewed_at"] = iso_utc(d["text_reviewed_at"]) if d["text_reviewed_at"] else None
        out.append(d)
    return out


def _minute_values(text: str) -> list[int]:
    return [int(m) for m in _MINUTE_NUM_RE.findall(text)]


def check_safety_text(approved_text: str, wait_minutes_in_text: int | None) -> str | None:
    r"""safety-guardrail 규칙 1·3 — 문안의 대기시간 숫자 검증 (DB 없는 순수 함수).

    반환: 위반 reason 또는 None.
    - 원문에 숫자가 없는데(`None`) 문안에 `\d+\s*분` → `number_not_in_source`
    - 원문 n 인데 문안에 `f"{n}분"` 이 없음 → `wait_value_mismatch`
      (앞 자리 숫자 경계를 본다 — `15분` 안의 `5분` 을 5분으로 세지 않는다)
    - 원문 n 인데 문안에 n 이 아닌 `k분` 이 또 있음 → `wait_value_mismatch`
      (임의 단축·변형 — 「5분(또는 3분)」 처럼 매뉴얼 명시값 옆에 다른 값을 붙이는 경우)
    """
    values = _minute_values(approved_text)
    if wait_minutes_in_text is None:
        return "number_not_in_source" if values else None
    n = int(wait_minutes_in_text)
    exact = re.search(rf"(?<!\d){n}분", approved_text) is not None
    if not exact or any(v != n for v in values):
        return "wait_value_mismatch"
    return None


def approve_safety(
    *, cand_id: int, approved_text: str, text_reviewed: object, approved_by: str
) -> dict:
    with connect() as con:
        head = con.execute(
            "SELECT model FROM onboarding_safety_candidates WHERE cand_id = ?", (cand_id,)
        ).fetchone()
        if not head:
            raise OnboardingError(404, "cand_not_found", f"cand_id {cand_id} 가 없습니다")
        _reject_seed_model(head["model"])
        # 같은 기종 승인을 직렬화 — 「기종당 discharge_wait 승인 1건」(D157)은 DB 제약이 없다.
        _advisory_lock(con, f"onboarding-safety:{head['model']}")
        cand = con.execute(
            "SELECT cand_id, model, kind, wait_minutes_in_text, state"
            " FROM onboarding_safety_candidates WHERE cand_id = ? FOR UPDATE",
            (cand_id,),
        ).fetchone()
        if cand["state"] != "staged":
            raise OnboardingError(
                409, "cand_not_staged", f"cand_id {cand_id} 는 staged 상태가 아닙니다"
            )
        if not isinstance(approved_text, str) or not approved_text.strip():
            raise OnboardingError(422, "approved_text_required", "approved_text 는 비어 있을 수 없습니다")
        if text_reviewed is not True:
            raise OnboardingError(422, "text_reviewed_required", "text_reviewed 는 true 여야 합니다")

        violation = check_safety_text(approved_text, cand["wait_minutes_in_text"])
        if violation == "number_not_in_source":
            raise OnboardingError(
                422,
                "number_not_in_source",
                "원문에 없는 대기시간 숫자가 승인 문안에 있습니다 (safety-guardrail 규칙 1)",
            )
        if violation == "wait_value_mismatch":
            raise OnboardingError(
                422,
                "wait_value_mismatch",
                f"승인 문안의 대기시간이 매뉴얼 명시값 {cand['wait_minutes_in_text']}분 과 다릅니다"
                " (safety-guardrail 규칙 3)",
                expected_minutes=cand["wait_minutes_in_text"],
            )

        now = now_utc_sql()  # D39 — 두 시각을 같은 값으로
        if cand["kind"] == "discharge_wait":
            dup = con.execute(
                "SELECT cand_id FROM onboarding_safety_candidates"
                " WHERE model = ? AND kind = 'discharge_wait' AND state = 'approved'",
                (cand["model"],),
            ).fetchone()
            if dup:
                raise OnboardingError(
                    409,
                    "already_approved_for_model",
                    f"{cand['model']} 에는 이미 승인된 discharge_wait 문구가 있습니다 (D157)",
                    approved_cand_id=dup["cand_id"],
                )

        con.execute(
            "UPDATE onboarding_safety_candidates"
            " SET state = 'approved', approved_text = ?, approved_by = ?,"
            " approved_at = ?, text_reviewed_at = ?"
            " WHERE cand_id = ? AND state = 'staged'",
            (approved_text.strip(), approved_by, now, now, cand_id),
        )
    return {"cand_id": cand_id, "state": "approved"}


def reject_safety(*, cand_id: int, note: str) -> dict:
    if not (note or "").strip():
        raise OnboardingError(422, "note_required", "note 는 비어 있을 수 없습니다")
    with connect() as con:
        cand = con.execute(
            "SELECT cand_id, model, state FROM onboarding_safety_candidates"
            " WHERE cand_id = ? FOR UPDATE",
            (cand_id,),
        ).fetchone()
        if not cand:
            raise OnboardingError(404, "cand_not_found", f"cand_id {cand_id} 가 없습니다")
        _reject_seed_model(cand["model"])
        if cand["state"] != "staged":
            raise OnboardingError(
                409, "cand_not_staged", f"cand_id {cand_id} 는 staged 상태가 아닙니다"
            )
        con.execute(
            "UPDATE onboarding_safety_candidates"
            " SET state = 'rejected', review_note = ? WHERE cand_id = ? AND state = 'staged'",
            (note.strip(), cand_id),
        )
    return {"cand_id": cand_id, "state": "rejected"}
