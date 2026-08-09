# -*- coding: utf-8 -*-
"""자산 조회 · 처분 사전판정 서비스 (S9 · MQ-611).

**판정을 어디서 가져오는가 (D73).**
`mcp_server` 를 import 하지 않는다 (D15 — 두 런타임 프로세스의 상호 import 금지).
대신 `data.rules.engine` 을 backend 가 **직접** import 한다. `data/` 는 매뉴얼·시드·룰
카탈로그가 있는 **공유 데이터 계층**이고, 사람용 REST 판정이 에이전트 도구 노출
설정(D69 `core`/`full`)에 종속되면 안 되기 때문이다 — `core` 프로파일에서는 확장 도구가
등록조차 되지 않아 "MCP 호출로만 판정" 안은 REST 를 통째로 죽인다.

**읽기 전용이다.** 이 모듈에는 INSERT/UPDATE/DELETE 가 없다. `precheck()` 는 이름 그대로
판정만 하고 `decisions`·`flags` 어디에도 흔적을 남기지 않는다 — 처분의 확정은 서명으로만
이뤄진다(D10 과 같은 태도: 권한을 코드 수준에서 아예 주지 않는다).
**규율이 아니라 구조로 보증한다** — 이 모듈은 `mode=ro` URI 커넥션(`read_only()`)만 쓰므로
쓰기를 시도해도 SQLite 가 거부한다. `backend.db.connect()`(쓰기 가능·자동 commit)는 쓰지 않는다.

**계층 1·2 는 DB 사본에서 읽는다** (`load_*_from_db`). 정본은 `data/rules/**.json` 이지만
(D60) 사람용 API 가 판정하는 대상은 "지금 DB 에 적재된 카탈로그"여야 한다 — 파일로
판정하면 DB 가 비어 있어도 200 이 나가고, 그 순간 503 게이트가 거짓말이 된다.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from contextlib import contextmanager

import backend.db as _backend_db  # DB_PATH 를 **호출 시점에** 읽는다 (아래 read_only 주석)
from backend.db import BUSY_TIMEOUT_MS
from backend.services.po import iso_utc
from data.rules import engine  # D73 — 공유 데이터 계층. mcp_server 는 import 하지 않는다


@contextmanager
def read_only(db_path: Path | None = None):
    """판정 전용 **읽기 전용** 커넥션.

    `backend.db.connect()` 를 쓰지 않는 이유: 그건 쓰기 가능 커넥션이고 종료 시 `commit()`
    한다(`backend/db.py:41`). 그러면 이 모듈의 무저장 보증이 **규율에 걸린다** —
    "INSERT 를 안 썼으니 안전하다"는 주장은 다음 사람이 한 줄 추가하면 무너진다.

    `mcp_server/db.py:61` 이 `mode=ro` URI 로 **물리적으로** 막는 것과 같은 태도를 취한다.
    D10 이 "도구에 UPDATE 권한 자체를 주지 않는다"로 human-in-the-loop 을 강제한 것처럼,
    보증은 문서가 아니라 **구조**가 해야 한다.

    ⛔ `backend/db.py` 를 고치지 않는다 — 공유 파일이고 다른 라우터는 쓰기가 필요하다.

    ⚠ `DB_PATH` 를 **모듈 로드 시점에 이름으로 바인딩하지 않는다.** `from backend.db import DB_PATH`
      로 받으면 그 시점 값이 고정돼, 회귀가 `backend.db.DB_PATH` 를 갈아끼워도(임시 DB 픽스처)
      이 모듈은 계속 실 DB 를 본다 — 검사가 조용히 엉뚱한 대상을 보게 된다.
    """
    path = db_path or _backend_db.DB_PATH
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()

# 판정하지 않고 목록만 볼 때 쓰는 컬럼 순서 (SELECT * 의 순서에 의존하지 않기 위해)
_EQUIPMENT_COLUMNS = ("equipment_id", "line_id", "model", "installed_at", "location")

PRECHECK_NOTE = "판정 결과이며 처분 요청이 생성되지 않았습니다. 확정은 서명으로만 이뤄집니다."

# 라우터가 HTTP 를 매핑할 때 쓰는 어휘. **엔진이 단일 출처**다 (D79)
VERDICTS = engine.VERDICTS
DISPOSAL_MODES = engine.DISPOSAL_MODES


class AssetNotFound(Exception):
    """존재하지 않는 자산 → 404."""


class InvalidDisposalMode(ValueError):
    """`engine.DISPOSAL_MODES` 밖의 값 → 422.

    허용 목록을 여기서 다시 적지 않는다 — 엔진이 단일 출처다(폴백 금지).
    `ValueError` 를 상속하는 이유: pydantic 검증기(`field_validator`)가 잡아
    FastAPI 의 422 로 그대로 흘러가야 하기 때문이다.
    """

    def __init__(self, value: object) -> None:
        self.value = value
        super().__init__(
            f"disposal_mode 는 {'|'.join(engine.DISPOSAL_MODES)} 이어야 합니다: {value!r}"
        )


class RuleCatalogError(Exception):
    """룰 카탈로그가 판정에 쓸 수 없는 상태 → 503.

    500 이 아닌 이유: 요청이 잘못된 게 아니라 **서버 설정/적재가 미완**이다.
    클라이언트가 할 행동(재시도·관리자 문의)이 다르다.
    """

    def __init__(self, reason: str, message: str) -> None:
        self.reason, self.message = reason, message
        super().__init__(f"{reason}: {message}")


def validate_disposal_mode(value: object) -> str:
    """`engine.DISPOSAL_MODES` 단일 출처 검증."""
    if not isinstance(value, str) or value not in engine.DISPOSAL_MODES:
        raise InvalidDisposalMode(value)
    return value


def now_utc_iso() -> str:
    """응답 시각 — UTC ISO-8601 (D39, `services/po.iso_utc` 와 같은 형태)."""
    return iso_utc(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")) or ""


# ───────────────────────────────────────────────────────────────── 조회


def list_assets(
    line_id: int | None = None,
    status: str | None = None,
    db_path: Path | None = None,
) -> list[dict]:
    """자산 목록. `line_id`·`status` 필터.

    `status` 는 허용값을 여기서 다시 열거하지 않는다 — 목록은 스키마의 CHECK 가 정본이고
    코드에 두 번째 사본을 만들면 스키마가 늘 때 조용히 어긋난다. 모르는 값은 0건이 된다.
    """
    sql = (
        "SELECT a.*, (SELECT COUNT(*) FROM equipment e WHERE e.asset_id = a.asset_id)"
        " AS equipment_count FROM assets a"
    )
    where, args = [], []
    if line_id is not None:
        where.append("a.line_id = ?")
        args.append(line_id)
    if status is not None:
        where.append("a.status = ?")
        args.append(status)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY a.line_id, a.asset_id"
    with read_only(db_path) as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def get_asset(asset_id: str, db_path: Path | None = None) -> dict | None:
    """자산 상세 + 하위 equipment 목록 (D68 — 처분의 단위는 호스트 설비)."""
    with read_only(db_path) as con:
        row = con.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        if row is None:
            return None
        asset = dict(row)
        cols = ", ".join(_EQUIPMENT_COLUMNS)
        asset["equipment"] = [
            dict(r)
            for r in con.execute(
                f"SELECT {cols} FROM equipment WHERE asset_id = ? ORDER BY equipment_id",  # noqa: S608
                (asset_id,),
            ).fetchall()
        ]
    return asset


# ───────────────────────────────────────────────────────────────── 판정

# 판정 어휘(D79) → 버킷 이름. **키 집합이 `engine.VERDICTS` 와 같아야** 한다 —
# 엔진이 어휘를 늘렸는데 여기가 모르면 우선순위에서 조용히 빠진다.
_VERDICT_BUCKET = {
    "BLOCKED": "blockers",
    "HOLD": "holds",
    "INSUFFICIENT_FACTS": "insufficient",
    "CONDITIONAL": "preconditions",
    "CLEAR": None,  # 아무 버킷도 차지 않았을 때의 기본값
}
assert set(_VERDICT_BUCKET) == set(engine.VERDICTS), (
    "판정 어휘가 엔진과 어긋났다 (D79) — engine.VERDICTS 를 단일 출처로 맞출 것"
)


def _decide(buckets: dict[str, list]) -> str:
    """버킷 → 최상위 verdict. 우선순위는 `engine.VERDICTS` 순서 그대로다.

    `engine.check_disposal_blockers` 와 같은 판정을 내야 하며, 두 경로가 어긋나면
    `spikes/disposal_api_contract.py` ⑯ 이 잡는다(파일 로더 경로와 대조).
    """
    for verdict in engine.VERDICTS:
        bucket = _VERDICT_BUCKET[verdict]
        if bucket is None:
            return verdict
        if buckets[bucket]:
            return verdict
    raise AssertionError("engine.VERDICTS 에 기본값(CLEAR) 자리가 없다")


def _checklist(preconditions: list[dict]) -> list[dict]:
    """PRECONDITION 룰의 `resolve_options` 를 항목화한다. **각 항목에 근거를 붙인다.**

    근거가 없는 항목은 만들지 않는다 — "무엇을 하라"는 지시가 조문 없이 화면에 뜨면
    사용자는 그게 법정 요구인지 담당자 관행인지 구분할 수 없다. D61 로드 게이트가
    근거 없는 룰을 이미 막으므로 실제로는 발생하지 않고, 발생해도 원본 판정은
    `preconditions[]` 에 그대로 남아 사라지지 않는다.
    """
    items = []
    for f in preconditions:
        citations = list(f["citations"])
        if not citations:
            continue
        for action in f["resolve_options"]:
            items.append(
                {
                    "rule_id": f["rule_id"],
                    "label": f["label"],
                    "action": action,
                    "citations": citations,
                    "law_refs": list(f["law_refs"]),
                    "requires_expert_review": f["requires_expert_review"],
                }
            )
    return items


def _load_catalog(con: sqlite3.Connection) -> tuple[dict, dict]:
    """계층 1·2 DB 사본 로드. **엔진이 던지는 예외를 여기서 흡수한다.**

    `load_rules_from_db` 는 근거 없는 룰(D61)·미등록 법령 참조·필수 컬럼 NULL 에
    `RuleIntegrityError` 를 던지고, JSON 파싱 실패도 같은 예외다. 어느 쪽이든
    "요청이 잘못된 것"이 아니라 "카탈로그가 판정에 못 쓰는 상태"이므로 503 이다.
    """
    try:
        laws = engine.load_laws_from_db(con)
        rules = engine.load_rules_from_db(con, laws)
    except engine.RuleIntegrityError as exc:
        raise RuleCatalogError("rule_catalog_invalid", str(exc)) from exc
    except sqlite3.Error as exc:  # 테이블 자체가 없는 경우 포함
        raise RuleCatalogError("rule_catalog_not_loaded", str(exc)) from exc
    # 계층 1(법령)이 비면 판정을 진행하지 않는다 — MCP 도구와 같은 게이트다
    # (`mcp_server/tools/check_disposal_blockers.py` 의 `if not laws`).
    # 지금은 전 룰이 `law_refs` 를 가져 `RuleIntegrityError` 로 먼저 걸리지만,
    # **계약 전용 룰(`source_type:"CONTRACT"`)만 남는 구성에서는 법령 0행인데 판정이 진행된다.**
    # 그러면 "근거를 조회한 결과 해당 없음"과 "근거가 아예 안 실렸다"가 구분되지 않는다 —
    # D50 이 `error_codes` 0행에서 막으려던 것과 정확히 같은 형태다.
    if not laws:
        raise RuleCatalogError(
            "rule_catalog_not_loaded",
            "law_refs 테이블이 비어 있습니다 — 계층 1 없이는 판정 근거를 인용할 수 없습니다",
        )
    if not rules:
        raise RuleCatalogError(
            "rule_catalog_not_loaded",
            "rules 테이블이 비어 있습니다 — data/seed.py 로 근거 계층을 적재하세요",
        )
    return laws, rules


def precheck(
    asset_id: str,
    *,
    disposal_mode: str,
    disposal_date: str | None = None,
    at: date | None = None,
    db_path: Path | None = None,
) -> dict:
    """처분 사전판정. **저장하지 않는다.**

    `engine.build_facts()` 를 반드시 경유한다 (D62). `dict(row)` 를 판정기에 직접 넘기면
    NULL 이 "값 있음"으로 읽혀 `INSUFFICIENT_FACTS` 가 조용히 `CLEAR` 로 바뀐다.
    `ASSET_FACT_COLUMNS` 안의 값은 `facts` 에서, 밖의 값(이름·카테고리 등)은 `row` 에서 읽는다.
    """
    mode = validate_disposal_mode(disposal_mode)
    at = at or date.today()

    with read_only(db_path) as con:
        row = con.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        if row is None:
            raise AssetNotFound(asset_id)
        laws, rules = _load_catalog(con)

    facts = engine.build_facts(row, disposal_mode=mode, disposal_date=disposal_date)

    try:
        findings = [engine.evaluate_rule(r, facts, laws) for r in rules.values()]
    except (KeyError, ValueError, TypeError) as exc:
        # 트리거 형식 오류·미등록 법령 등 — 카탈로그 결함이지 요청 결함이 아니다
        raise RuleCatalogError("rule_catalog_invalid", f"{type(exc).__name__}: {exc}") from exc

    buckets: dict[str, list[dict]] = {
        "blockers": [
            f.__dict__
            for f in findings
            if f.verdict == "TRIGGERED" and f.disposal_type == "BLOCKING"
        ],
        "preconditions": [
            f.__dict__
            for f in findings
            if f.verdict == "TRIGGERED" and f.disposal_type == "PRECONDITION"
        ],
        "holds": [f.__dict__ for f in findings if f.verdict == "HOLD"],
        "insufficient": [f.__dict__ for f in findings if f.verdict == "INSUFFICIENT_FACTS"],
    }
    verdict = _decide(buckets)

    # 해소 경로는 "지금 막고 있는 것"만 모은다 — 통과한 룰의 옵션까지 섞으면
    # 사용자가 무엇을 하면 풀리는지가 흐려진다. 순서 보존 dedup.
    resolve_options: list[str] = []
    for group in ("blockers", "holds", "insufficient", "preconditions"):
        for f in buckets[group]:
            for opt in f["resolve_options"]:
                if opt not in resolve_options:
                    resolve_options.append(opt)

    missing_facts: list[str] = []
    for f in buckets["insufficient"]:
        for name in f["missing_facts"]:
            if name not in missing_facts:
                missing_facts.append(name)

    return {
        # 처분 판정의 대상은 인버터가 아니라 호스트 설비다 (D68)
        "asset_id": row["asset_id"],
        "asset_name": row["name"],  # ASSET_FACT_COLUMNS 밖 → row 에서 읽는다
        "disposal_mode": facts["disposal_mode"],  # 안 → facts
        "disposal_date": facts.get("disposal_date"),
        "evaluated_at": at.isoformat(),  # 판정 기준일(날짜)
        "generated_at": now_utc_iso(),  # 응답 시각(UTC ISO-8601, D39)
        "verdict": verdict,
        **buckets,
        "checklist": _checklist(buckets["preconditions"]),
        "resolve_options": resolve_options,
        "missing_facts": missing_facts,
        "facts_used": dict(facts),
        # W2 — 문구를 복제하지 않는다. 엔진이 단일 출처다 (D73).
        # 복제본을 두면 엔진이 문장을 고칠 때 **REST 만 조용히 옛 문구를 낸다** — 사용자는
        # 같은 판정을 도구로 볼 때와 화면으로 볼 때 다른 한계 고지를 읽게 된다.
        # `engine.X` 로 **모듈 참조**한다 — `from … import DISCLAIMER` 는 로드 시점에 값을
        # 고정해 버려서, 이 파일이 다시 복제본을 갖는 것과 같아진다(Sprint 5 W1 유형).
        # `list(...)` 로 새 리스트를 만드는 이유: 응답 객체를 받은 쪽이 append 하면
        # 엔진 상수가 프로세스 전역에서 오염된다.
        "not_considered": list(engine.NOT_CONSIDERED),
        "disclaimer": engine.DISCLAIMER,
        "note": PRECHECK_NOTE,
    }


def precheck_detail(result: dict[str, Any]) -> str:
    """409 본문의 `detail` — 왜 막혔는지를 한 줄로. verdict 별로 할 일이 다르다."""
    verdict = result["verdict"]
    if verdict == "BLOCKED":
        rules = ", ".join(f["rule_id"] for f in result["blockers"])
        return f"법정 차단 사유 {len(result['blockers'])}건으로 처분할 수 없습니다: {rules}"
    if verdict == "HOLD":
        rules = ", ".join(f["rule_id"] for f in result["holds"])
        return f"경계 구간이라 단정하지 않습니다 — 전문가 검토가 필요합니다: {rules}"
    if verdict == "INSUFFICIENT_FACTS":
        return (
            "확인되지 않은 사실이 있어 판정할 수 없습니다 (조건 미해당이 아닙니다): "
            f"{', '.join(result['missing_facts'])}"
        )
    raise AssertionError(f"409 대상이 아닌 verdict: {verdict}")
