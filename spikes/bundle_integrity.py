# -*- coding: utf-8 -*-
"""근거 번들 무결성 회귀 (MQ-705) — `build_evidence_bundle` 5키 재설계의 방어선.

이 스위트가 지키는 것은 **"해시가 무엇을 증명하는가"** 다. 번들 해시는 서명 산출물이라
결함이 조용히 살아남으면 *"근거가 변조되지 않았음"* 이라는 문장 자체가 빈 약속이 된다.

  W5 원천 일원화 — 판정이 본 조문·사실과 해시로 고정한 조문·사실이 **같은 객체**인가 (⑨⑱)
  W6 `rule_hash`  — 같은 `rule_version` 안에서 룰 본문이 바뀌면 해시가 움직이는가 (③④)
  W7 `evaluated[]`— CLEAR 자산에서도 "무엇을 평가했는가"가 남는가 (⑤⑮)
  계약 근거        — `contracts[]` 가 `law_text_unavailable` 을 유발하지 않는가 (⑥⑦)
  N1              — `hash_spec` 이 번들 **밖**인가 · 해시 동일의 기준이 바이트가 아닌가 (⑩⑬)
  N2              — 조립 도중 자산이 바뀌거나 사라지면 멈추는가 (⑪⑫)
  D10             — 이 도구는 `decisions` 에 아무것도 쓰지 않는다 (⑭㉑)

★ **깨지지 않는 검사는 방어선이 아니다.** 아래 4종은 뮤턴트로 먼저 깨뜨려 확인했다
  (MQ-705 보고에 전후 출력 첨부):
    ⓐ `rule_hash` 제거      → ③ FAIL
    ⓑ `evaluated[]` 제거    → ⑤ FAIL
    ⓒ 주입 대신 `load_laws()` 재호출 → ⑨ FAIL
    ⓓ 자산 재읽기 제거      → ⑪ FAIL

★ **실 DB 는 읽기만 한다.** 픽스처는 전부 임시 폴더의 사본이고(WAL 사이드카 포함),
  마지막 검사가 실 DB 의 mtime·size 불변을 직접 확인한다.

실행:  uv run python spikes/bundle_integrity.py
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mcp_server.db as mcp_db  # noqa: E402
import mcp_server.tools.build_evidence_bundle as bundle_mod  # noqa: E402
from data.rules import engine  # noqa: E402

# ⚠ 이 스파이크는 두 도구를 **대조**하려고 둘 다 import 한다. 대조 대상인
#   `build_evidence_bundle` 자신은 `check_disposal_blockers` 를 import 하면 안 된다 (⑲).
from mcp_server.tools.build_evidence_bundle import (  # noqa: E402
    HASH_SPEC,
    build_evidence_bundle,
    canonical_json,
    compute_bundle_hash,
    rule_hash,
)
from mcp_server.tools.check_disposal_blockers import check_disposal_blockers  # noqa: E402

REAL_DB = mcp_db.DB_PATH
BUNDLE_SRC = Path(bundle_mod.__file__)

# 처분일을 고정한다 — 오늘 날짜를 쓰면 `months_since_acquisition` 이 매일 달라져
# 기대 verdict 가 흔들린다 (D62 와 같은 유형의 조용한 드리프트).
PROBE_DATE = "2026-09-01"

MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    """번호는 자동 부여 — 손으로 박으면 검사를 끼워 넣을 때마다 뒤가 전부 밀린다."""
    mark = MARKS[len(results)] if len(results) < len(MARKS) else f"[{len(results) + 1}]"
    results.append((f"{mark} {name}", ok, detail))


def call(**kwargs) -> dict:
    """도구 호출. **예외가 새어나오면 그 자체가 계약 위반**이라 실패 dict 로 바꿔 기록한다 (D9)."""
    try:
        out = build_evidence_bundle(**kwargs)
    except Exception as exc:  # noqa: BLE001
        return {"status": f"!!예외누출 {type(exc).__name__}: {exc}"}
    return out if isinstance(out, dict) else {"status": f"!!dict 아님 {type(out).__name__}"}


def eb(res: dict) -> dict:
    return res.get("evidence_bundle") or {}


# ── 픽스처 ────────────────────────────────────────────────────────────────────


def copy_db(src: Path, dst: Path) -> Path:
    """DB 사본. WAL 사이드카가 있으면 함께 가져온다 — 안 옮기면 사본이 원본보다 낡는다."""
    shutil.copy2(src, dst)
    for suffix in ("-wal", "-shm"):
        side = src.with_name(src.name + suffix)
        if side.exists():
            shutil.copy2(side, dst.with_name(dst.name + suffix))
    return dst


def write(db: Path, statements: list[tuple[str, tuple]]) -> list[int]:
    """픽스처 DB 에만 쓴다. `foreign_keys` 는 기본 OFF 라 자산 DELETE 도 가능하다."""
    con = sqlite3.connect(db)
    try:
        counts = [con.execute(sql, args).rowcount for sql, args in statements]
        con.commit()
        return counts
    finally:
        con.close()


def all_fetched(dst: Path) -> Path:
    """인용 조문이 **전부** 채워진 사본. 해시 안정성은 여기서만 검증할 수 있다 —
    실 DB 는 미수집 1건(`KR-CITA-ENF-31`)의 상태에 따라 검사가 켜졌다 꺼졌다 한다."""
    copy_db(REAL_DB, dst)
    con = sqlite3.connect(dst)
    try:
        for (rid,) in con.execute("SELECT law_ref_id FROM law_refs").fetchall():
            text = f"[합성 픽스처] {rid} 조문 원문"
            con.execute(
                "UPDATE law_refs SET text=?, text_hash=?, fetch_status='FETCHED' "
                "WHERE law_ref_id=?",
                (text, engine.text_hash(text), rid),
            )
        con.commit()
    finally:
        con.close()
    return dst


def all_pending(dst: Path) -> Path:
    """조문 원문이 **하나도** 없는 사본 — `law_text_unavailable` 경로가 살아 있는지 본다."""
    copy_db(REAL_DB, dst)
    write(
        dst,
        [("UPDATE law_refs SET text=NULL, text_hash=NULL, fetch_status='PENDING'", ())],
    )
    return dst


# 계약 근거만 있고 법령 참조가 **없는** 합성 룰. `contract_refs` 를 일부러 역순으로 넣어
# 정렬이 조립 시점에 일어나는지도 함께 본다.
CONTRACT_ONLY_RULE = (
    "ZZ-CONTRACT-ONLY",
    1,
    "계약 전용 합성 룰",
    "권리관계",
    "PRECONDITION",
    "CONTRACT",
    "[]",
    json.dumps(["Z약관", "A약관"], ensure_ascii=False),
    "합성 픽스처 — 계약 근거만으로 발화하는 룰",
    json.dumps(["disposal_mode"]),
    json.dumps({"all_of": [{"field": "disposal_mode", "op": "eq", "value": "SALE"}]}),
    None,
    "합성 픽스처 메시지",
    "[]",
    "HIGH",
    0,
)


def contract_only(dst: Path) -> Path:
    """조문은 **전부 미수집**, 룰은 **계약 근거만** 있는 사본.

    이 조합에서 번들이 성공해야 "계약 근거는 `law_text_unavailable` 검사 대상이 아니다"가
    증명된다 — 조문이 하나도 없는데도 계약 근거만으로 서명 재료가 나오는가.
    """
    all_pending(dst)
    write(
        dst,
        [
            ("DELETE FROM rules", ()),
            (
                "INSERT INTO rules (rule_id, rule_version, label, category, disposal_type,"
                " source_type, law_refs, contract_refs, interpretation, required_facts,"
                " trigger, boundary, message, resolve_options, confidence,"
                " requires_expert_review) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                CONTRACT_ONLY_RULE,
            ),
        ],
    )
    return dst


@contextmanager
def use_db(path: Path):
    """도구가 볼 DB 를 사본으로 바꾼다. `MAINTQ_DB` 도 함께 심어 자식 프로세스에 상속시킨다."""
    saved_path, saved_env = mcp_db.DB_PATH, os.environ.get("MAINTQ_DB")
    mcp_db.DB_PATH = path
    os.environ["MAINTQ_DB"] = str(path)
    try:
        yield
    finally:
        mcp_db.DB_PATH = saved_path
        if saved_env is None:
            os.environ.pop("MAINTQ_DB", None)
        else:
            os.environ["MAINTQ_DB"] = saved_env


@contextmanager
def patched_engine(hook):
    """`engine.check_disposal_blockers` 를 감싼다.

    "판정 **직후**" 를 재현할 수 있는 유일한 지점이다 — 도구는 이 함수를 부른 뒤에
    번들을 조립하고 자산을 다시 읽으므로, 여기서 DB 를 건드리면 그 사이 창을 정확히 친다.
    """
    original = engine.check_disposal_blockers

    def wrapper(facts, at=None, *, laws=None, rules=None):
        return hook(original, facts, at, laws, rules)

    engine.check_disposal_blockers = wrapper
    try:
        yield
    finally:
        engine.check_disposal_blockers = original


def decisions_count(db: Path) -> int:
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    finally:
        con.close()


def sorted_by(items: list[dict], *keys: str) -> bool:
    def key(item: dict):
        return tuple(str(item.get(k)) for k in keys)

    return [key(i) for i in items] == sorted(key(i) for i in items)


def fullwidth(text: str) -> str:
    """ASCII 영숫자를 전각으로. NFKC 를 거치면 원문과 같은 문자열이 된다."""
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in text)


# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:  # noqa: PLR0915 — 검사 나열이라 분할하면 오히려 추적이 어렵다
    # 없으면 stdout 이 파이프일 때 콘솔 코드페이지(cp949)로 인코딩돼
    # '—' 같은 문자에서 UnicodeEncodeError 로 죽는다. 회귀 러너는 출력을 캡처한다.
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    if not REAL_DB.exists():
        raise SystemExit(f"목업 DB 가 없습니다: {REAL_DB} — data/seed.py 를 먼저 실행하세요")
    before_stat = (REAL_DB.stat().st_mtime_ns, REAL_DB.stat().st_size)
    decisions_before = decisions_count(REAL_DB)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        fetched = all_fetched(tmp / "fetched.db")
        pending = all_pending(tmp / "pending.db")
        contracts_db = contract_only(tmp / "contract_only.db")

        # ── ①② 멱등 · `built_at` 은 해시 밖 ────────────────────────────────
        with use_db(fetched):
            b1 = call(asset_id="AST-L3-CONV", disposal_date=PROBE_DATE)
            b2 = call(asset_id="AST-L3-CONV", disposal_date=PROBE_DATE)
        check(
            "같은 입력 2회 → bundle_hash 동일 (멱등)",
            b1.get("status") == "ok"
            and b1.get("bundle_hash") == b2.get("bundle_hash")
            and str(b1.get("bundle_hash") or "").startswith("sha256:"),
            f"status={b1.get('status')}/{b2.get('status')} hash={str(b1.get('bundle_hash'))[:22]}…",
        )

        # `built_at` 은 초 단위라 연속 두 호출이 같은 값을 낼 수 있다 — 그러면 이 검사가
        # **공허하게 통과**한다. 시계를 고정해 두 값이 실제로 다르게 만든 뒤 해시를 본다.
        class Clock:
            def __init__(self, moment: datetime) -> None:
                self._moment = moment

            def now(self, tz=None):  # noqa: ANN001 — datetime.now 시그니처를 흉내낸다
                return self._moment

        saved_dt = bundle_mod.datetime
        try:
            with use_db(fetched):
                bundle_mod.datetime = Clock(datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
                t1 = call(asset_id="AST-L3-CONV", disposal_date=PROBE_DATE)
                bundle_mod.datetime = Clock(datetime(2031, 12, 31, 23, 59, 59, tzinfo=timezone.utc))
                t2 = call(asset_id="AST-L3-CONV", disposal_date=PROBE_DATE)
        finally:
            bundle_mod.datetime = saved_dt
        check(
            "built_at 만 다른 두 응답 → bundle_hash 동일 (built_at 은 번들 밖)",
            t1.get("built_at") != t2.get("built_at")
            and t1.get("bundle_hash") == t2.get("bundle_hash")
            and t1.get("status") == "ok",
            f"built_at {t1.get('built_at')} vs {t2.get('built_at')} · "
            f"hash 동일={t1.get('bundle_hash') == t2.get('bundle_hash')}",
        )

        # ── ③ W6 — 룰 본문 1글자 변경(같은 rule_version) → rule_hash 변경 ────
        drifted = all_fetched(tmp / "rule_drift.db")
        changed = write(
            drifted,
            [
                (
                    "UPDATE rules SET message = message || '.' WHERE rule_id = 'VAT-INVOICE'",
                    (),
                )
            ],
        )[0]
        with use_db(drifted):
            b3 = call(asset_id="AST-L3-CONV", disposal_date=PROBE_DATE)

        def entry(res: dict, key: str, rule_id: str) -> dict:
            return next(
                (r for r in eb(res).get(key) or [] if r.get("rule_id") == rule_id),
                {},
            )

        base_rule, drift_rule = entry(b1, "rules", "VAT-INVOICE"), entry(b3, "rules", "VAT-INVOICE")
        check(
            "W6 — 룰 본문 1글자 변경(rule_version 동일) → rule_hash·bundle_hash 변경",
            changed == 1
            and bool(base_rule.get("rule_hash"))
            and base_rule.get("rule_version") == drift_rule.get("rule_version")
            and base_rule.get("rule_hash") != drift_rule.get("rule_hash")
            and b1.get("bundle_hash") != b3.get("bundle_hash"),
            f"변경 {changed}행 · v{base_rule.get('rule_version')} "
            f"{str(base_rule.get('rule_hash'))[:18]}… → {str(drift_rule.get('rule_hash'))[:18]}…",
        )

        # ── ④ 룰 **메타** 변경은 rule_hash 를 흔들지 않는다 ──────────────────
        #    (동시에 "이 해시 함수가 상수가 아님"도 확인한다 — 안 그러면 ④ 는 공허하다)
        con = sqlite3.connect(f"file:{fetched.as_posix()}?mode=ro", uri=True)
        try:
            con.row_factory = sqlite3.Row
            laws_fx = engine.load_laws_from_db(con)
            rules_fx = engine.load_rules_from_db(con, laws_fx)
        finally:
            con.close()
        probe_rule = rules_fx["VAT-INVOICE"]
        meta_before = rule_hash(probe_rule)
        probe_rule.revision_note = "개정 사유 문구를 다듬었다"
        probe_rule.authored_by = "검수자 이름 오타 수정"
        probe_rule.reviewed_at = "2026-08-10"
        meta_after = rule_hash(probe_rule)
        probe_rule.message = probe_rule.message + "."
        body_after = rule_hash(probe_rule)
        check(
            "W6 — 메타(revision_note·authored_by·reviewed_at) 변경은 rule_hash 불변 · 본문은 변경",
            meta_before == meta_after and meta_before != body_after,
            f"메타 불변={meta_before == meta_after} · 본문 변경={meta_before != body_after}",
        )

        # ── ⑤ W7 — CLEAR 자산에서도 evaluated[] 는 비지 않는다 ────────────────
        with use_db(fetched):
            clear = call(asset_id="AST-L3-LIFT", disposal_mode="SCRAP", disposal_date=PROBE_DATE)
        check(
            "W7 — CLEAR 자산(laws·rules 빈 배열)도 evaluated[] 가 비지 않는다",
            clear.get("status") == "ok"
            and clear.get("verdict") == "CLEAR"
            and eb(clear).get("laws") == []
            and eb(clear).get("rules") == []
            and len(eb(clear).get("evaluated") or []) == len(rules_fx)
            and bool(clear.get("bundle_hash")),
            f"verdict={clear.get('verdict')} laws={len(eb(clear).get('laws') or [])} "
            f"rules={len(eb(clear).get('rules') or [])} "
            f"evaluated={len(eb(clear).get('evaluated') or [])}(룰 {len(rules_fx)}종)",
        )

        # ── ⑥ 계약 근거는 해시로 고정되지 않는다고 **번들이 스스로 말한다** ──
        contracts = eb(b1).get("contracts") or []
        check(
            "계약 근거 — contracts[] 전 항목이 hash_fixed:false · text_hash:null · note 동반",
            bool(contracts)
            and all(
                set(c) == {"contract_ref", "text_hash", "hash_fixed", "note"}
                and c["hash_fixed"] is False
                and c["text_hash"] is None
                and bool(str(c.get("note") or "").strip())
                for c in contracts
            ),
            f"{[c.get('contract_ref') for c in contracts]}",
        )

        # ── ⑦ 계약 근거는 `law_text_unavailable` 을 유발하지 않는다 ──────────
        #    조문이 **하나도** 수집되지 않은 DB + 계약 근거만 있는 룰 → 그래도 성공해야 한다.
        with use_db(contracts_db):
            conly = call(asset_id="AST-L3-LIFT", disposal_date=PROBE_DATE)
        conly_refs = [c.get("contract_ref") for c in eb(conly).get("contracts") or []]
        check(
            "계약 근거 — 조문 0건 수집 상태에서도 contract_refs 만으로 번들 성공 (검사 대상 아님)",
            conly.get("status") == "ok"
            and eb(conly).get("laws") == []
            and conly_refs == ["A약관", "Z약관"]
            and "missing_law_refs" not in conly,
            f"status={conly.get('status')} reason={conly.get('reason', '-')} contracts={conly_refs}",
        )

        # ── ⑧ 리스트 4종 명시 정렬 ────────────────────────────────────────────
        #    한 건짜리 리스트에서는 정렬 검사가 공허하다 — 2건 이상인 표본을 함께 요구한다.
        laws_l = eb(b1).get("laws") or []
        rules_l = eb(b1).get("rules") or []
        eval_l = eb(b1).get("evaluated") or []
        contracts_l = eb(b1).get("contracts") or []
        check(
            "리스트 4종 명시 정렬 (laws→law_ref_id · rules·evaluated→(rule_id,rule_version) "
            "· contracts→contract_ref)",
            min(len(laws_l), len(rules_l), len(eval_l), len(contracts_l)) >= 2
            and sorted_by(laws_l, "law_ref_id")
            and sorted_by(rules_l, "rule_id", "rule_version")
            and sorted_by(eval_l, "rule_id", "rule_version")
            and sorted_by(contracts_l, "contract_ref"),
            f"laws {len(laws_l)} rules {len(rules_l)} evaluated {len(eval_l)} "
            f"contracts {len(contracts_l)} (전부 ≥2 여야 검사가 유효)",
        )

        # ── ⑨ W5 — 해시에 실린 조문이 **판정에 주입된 그 객체**에서 왔는가 ────
        #    주입된 LawRef 의 `text_hash` 를 판정 직전에 표식으로 바꾼다. 도구가 조문을
        #    다시 로드하면(옛 W5 결함) 표식이 사라지므로 여기서 잡힌다.
        sentinel_prefix = "sha256:5e14e1"

        def sentinel_hook(original, facts, at, laws, rules):
            for rid, law in (laws or {}).items():
                law.text_hash = f"{sentinel_prefix}{rid}"
            return original(facts, at, laws=laws, rules=rules)

        with use_db(fetched), patched_engine(sentinel_hook):
            injected = call(asset_id="AST-L3-CONV", disposal_date=PROBE_DATE)
        law_hashes = [law.get("text_hash") for law in eb(injected).get("laws") or []]
        check(
            "W5 — 번들의 text_hash 가 판정에 **주입된 laws 객체**에서 나온다 (재로드 아님)",
            injected.get("status") == "ok"
            and bool(law_hashes)
            and all(str(h).startswith(sentinel_prefix) for h in law_hashes),
            f"status={injected.get('status')} text_hash={[str(h)[:20] for h in law_hashes]}",
        )

        # ── ⑩ N1 — 해시 동일의 기준은 바이트가 아니라 NFKC+공백 정규화 ────────
        variant = copy.deepcopy(eb(b1))
        variant["facts"]["asset_id"] = fullwidth(str(variant["facts"]["asset_id"]))
        variant["contracts"][0]["note"] = variant["contracts"][0]["note"].replace(" ", "   ", 1)
        check(
            "N1 — 전각/연속 공백 변형은 바이트가 달라도 같은 해시 (hash_spec 이 뜻하는 바)",
            canonical_json(variant) != canonical_json(eb(b1))
            and compute_bundle_hash(variant) == b1.get("bundle_hash"),
            f"직렬화 다름={canonical_json(variant) != canonical_json(eb(b1))} · "
            f"해시 동일={compute_bundle_hash(variant) == b1.get('bundle_hash')}",
        )

        # ── ⑪ N2 — 판정 직후 자산 UPDATE → asset_modified ─────────────────────
        modified_db = all_fetched(tmp / "asset_modified.db")
        touched: list[int] = []

        def update_hook(original, facts, at, laws, rules):
            out = original(facts, at, laws=laws, rules=rules)
            touched.append(
                write(
                    modified_db,
                    [
                        (
                            "UPDATE assets SET lien_creditor = ? WHERE asset_id = ?",
                            ("판정 직후 외부에서 바뀐 값", "AST-L3-CONV"),
                        )
                    ],
                )[0]
            )
            return out

        with use_db(modified_db), patched_engine(update_hook):
            mod_res = call(asset_id="AST-L3-CONV", disposal_date=PROBE_DATE)
        check(
            "N2 — 판정 직후 자산 행 UPDATE → error/asset_modified (스냅샷을 조용히 서명하지 않는다)",
            touched == [1]
            and mod_res.get("status") == "error"
            and mod_res.get("reason") == "asset_modified",
            f"UPDATE {touched}행 · status={mod_res.get('status')} reason={mod_res.get('reason')}",
        )

        # ── ⑫ 판정 직후 자산 DELETE → asset_disappeared ──────────────────────
        gone_db = all_fetched(tmp / "asset_gone.db")
        removed: list[int] = []

        def delete_hook(original, facts, at, laws, rules):
            out = original(facts, at, laws=laws, rules=rules)
            removed.append(
                write(gone_db, [("DELETE FROM assets WHERE asset_id = ?", ("AST-L3-CONV",))])[0]
            )
            return out

        with use_db(gone_db), patched_engine(delete_hook):
            gone_res = call(asset_id="AST-L3-CONV", disposal_date=PROBE_DATE)
        check(
            "N2 — 판정 직후 자산 행 DELETE → error/asset_disappeared",
            removed == [1]
            and gone_res.get("status") == "error"
            and gone_res.get("reason") == "asset_disappeared",
            f"DELETE {removed}행 · status={gone_res.get('status')} reason={gone_res.get('reason')}",
        )

        # ── ⑬ N1 — `hash_spec` 은 번들 **밖** · 번들은 정확히 5키 (D83) ────────
        check(
            "N1·D83 — hash_spec 은 번들 밖 · evidence_bundle 은 정확히 5키 · 해시 대상은 번들뿐",
            b1.get("hash_spec") == HASH_SPEC
            and "hash_spec" not in eb(b1)
            and "built_at" not in eb(b1)
            and set(eb(b1)) == {"laws", "rules", "evaluated", "contracts", "facts"}
            and compute_bundle_hash(eb(b1)) == b1.get("bundle_hash"),
            f"hash_spec={b1.get('hash_spec')} 번들키={sorted(eb(b1))}",
        )

        # ── ⑭ D10 — 여기까지 번들을 십수 번 만들었지만 `decisions` 는 한 행도 늘지 않았다 ─
        #    (마지막 검사가 실 DB 의 mtime·size·행수를 한 번 더 확인한다)
        check(
            "D10 — decisions 행 수 불변 (이 도구에는 쓰기 커넥션이 없다)",
            decisions_before == decisions_count(REAL_DB),
            f"{decisions_before} → {decisions_count(REAL_DB)}행",
        )

        # ── ⑮ evaluated[] 는 ID 목록일 뿐 — text_hash 를 요구하지 않는다 ──────
        eval_keys = {frozenset(e) for e in eval_l}
        check(
            "D83 — evaluated[] 항목은 {rule_id,rule_version,verdict,law_refs} 뿐 (text_hash 없음)",
            bool(eval_keys)
            and eval_keys == {frozenset({"rule_id", "rule_version", "verdict", "law_refs"})}
            and all("text_hash" not in e for e in eval_l),
            f"키집합={[sorted(k) for k in eval_keys]}",
        )

        # ── ⑯ 실 DB — 미수집 1건이 있어도 그것을 인용하지 않는 자산은 성공한다 ─
        real_spdl = call(asset_id="AST-L2-SPDL", disposal_date=PROBE_DATE)
        con = sqlite3.connect(f"file:{REAL_DB.as_posix()}?mode=ro", uri=True)
        try:
            cita = con.execute(
                "SELECT fetch_status FROM law_refs WHERE law_ref_id='KR-CITA-ENF-31'"
            ).fetchone()
        finally:
            con.close()
        # 실 DB 의 수집 상태가 바뀌어도 이 검사가 의미를 잃지 않도록, 그 조문을 강제로
        # 미수집으로 되돌린 사본에서도 같은 결과를 요구한다.
        forced = copy_db(REAL_DB, tmp / "cita_pending.db")
        write(
            forced,
            [
                (
                    "UPDATE law_refs SET text=NULL, text_hash=NULL, fetch_status='PENDING' "
                    "WHERE law_ref_id='KR-CITA-ENF-31'",
                    (),
                )
            ],
        )
        with use_db(forced):
            forced_spdl = call(asset_id="AST-L2-SPDL", disposal_date=PROBE_DATE)
        check(
            "실 DB — KR-CITA-ENF-31 미수집 상태에서도 AST-L2-SPDL SALE 번들 성공 (인용 없음)",
            real_spdl.get("status") == "ok" and forced_spdl.get("status") == "ok",
            f"실 DB status={real_spdl.get('status')}"
            f"(KR-CITA-ENF-31={cita[0] if cita else '없음'}) · "
            f"강제 미수집 사본 status={forced_spdl.get('status')}",
        )

        # ── ⑰ `law_text_unavailable` 경로 생존 (합성 픽스처) ──────────────────
        #    실 DB 에서는 MQ-701 수집 이후 발화하지 않는다. 그렇다고 경로를 지우면
        #    새 룰이 미수집 조문을 인용하는 순간 **해시할 근거 없는 번들**이 나간다.
        with use_db(pending):
            unavailable = call(asset_id="AST-L3-LIFT", disposal_date=PROBE_DATE)
        check(
            "미수집 조문 인용 → error/law_text_unavailable + missing_law_refs (경로 생존)",
            unavailable.get("status") == "error"
            and unavailable.get("reason") == "law_text_unavailable"
            and "KR-VAT-32" in (unavailable.get("missing_law_refs") or []),
            f"reason={unavailable.get('reason')} missing={unavailable.get('missing_law_refs')}",
        )

        # ── ⑱ 번들의 facts 는 판정이 쓴 facts_used **그 객체**다 (재조립 아님) ─
        seen_facts: list[dict] = []

        def capture_hook(original, facts, at, laws, rules):
            out = original(facts, at, laws=laws, rules=rules)
            seen_facts.append(out["facts_used"])
            return out

        with use_db(fetched), patched_engine(capture_hook):
            captured = call(asset_id="AST-L3-CONV", disposal_date=PROBE_DATE)
        same_object = bool(seen_facts) and eb(captured).get("facts") is seen_facts[-1]
        check(
            "W5 — 번들 facts 가 판정의 facts_used 와 **같은 객체** (값만 같은 재조립본이 아니다)",
            captured.get("status") == "ok" and same_object,
            f"동일 객체={same_object} · facts 키 {len(eb(captured).get('facts') or {})}개",
        )

    # ── ⑲ DoD ⑰ — 판정 **도구**를 import 하지 않는다 (W5 회귀 차단) ───────────
    src = BUNDLE_SRC.read_text(encoding="utf-8")
    import_lines = [
        line
        for line in src.splitlines()
        if re.match(r"\s*(from|import)\s", line) and "check_disposal_blockers" in line
    ]
    probe_code = (
        "import sys;"
        "import mcp_server.tools.build_evidence_bundle as m;"
        "print('LEAK' if 'mcp_server.tools.check_disposal_blockers' in sys.modules else 'CLEAN')"
    )
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", probe_code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    module_clean = proc.stdout.strip().endswith("CLEAN")
    check(
        "W5 회귀 차단 — build_evidence_bundle 이 check_disposal_blockers 도구를 import 하지 않는다",
        not import_lines and module_clean,
        f"import 문 {import_lines or '없음'} · 자식 프로세스 sys.modules={proc.stdout.strip() or proc.stderr.strip()[:60]}",
    )

    # ── ⑳ 두 도구의 실패 어휘 대조 (자산 해석 로직을 복제했으므로 감시가 필요하다) ─
    shared_cases = (
        {"asset_id": "AST-NOPE"},
        {"equipment_id": "EQ-NOPE"},
        {"equipment_id": "INV-L1-01"},  # 호스트 자산 없음 (분전반)
        {"asset_id": "AST-L3-CONV", "equipment_id": "INV-L2-01"},  # 서로 다른 자산
        {},  # 둘 다 미지정
        {"asset_id": 123},
        {"asset_id": "AST-L3-CONV", "disposal_mode": "SELL"},
        {"asset_id": "AST-L3-CONV", "disposal_date": "내일"},
    )
    # 실패 응답에 허용되는 키. `_asset_ref.err(reason, message, **extra)` 가 공용화되면서
    # **실패 경로로 계약 밖 키를 늘릴 수 있게 됐다** — 13키 화이트리스트(`_ENGINE_CONTRACT_KEYS`)는
    # 성공 경로만 잠근다. 성공 축을 막아 놓고 실패 축을 열어 두면 같은 드리프트가 반대편으로 샌다.
    # `build_evidence_bundle` 만 `missing_law_refs`(law_text_unavailable)를 정당하게 더 싣는다.
    failure_keys_allowed = {"status", "reason", "message", "asset_id", "equipment_id"}
    key_leaks = []
    gaps = []
    for kwargs in shared_cases:
        judge = check_disposal_blockers(**kwargs)
        built = call(**kwargs)
        for label, out, allowed in (
            ("판정", judge, failure_keys_allowed),
            ("번들", built, failure_keys_allowed | {"missing_law_refs"}),
        ):
            if out.get("status") in ("error", "not_found"):
                extra = set(out) - allowed
                if extra:
                    key_leaks.append(f"{label}{kwargs}: {sorted(extra)}")
        if (judge.get("status"), judge.get("reason")) != (built.get("status"), built.get("reason")):
            gaps.append(
                f"{kwargs}: 판정={judge.get('status')}/{judge.get('reason')} "
                f"vs 번들={built.get('status')}/{built.get('reason')}"
            )
    check(
        "두 도구의 status·reason 어휘 일치 — 자산 해석·입력 검증 8케이스 직접 대조",
        not gaps,
        "; ".join(gaps) or f"{len(shared_cases)}케이스 일치",
    )
    check(
        "실패 응답도 계약 밖 키를 늘리지 않는다 (공용 err(**extra) 우회 차단)",
        not key_leaks,
        "; ".join(key_leaks) or f"{len(shared_cases)}케이스 × 2도구 초과 키 0건",
    )

    # ── ㉒ 두 도구의 **성공 경로 verdict** 일치 (파일 정본 vs DB 사본) ──────────
    #
    #   ⑳ 은 8케이스가 **전부 실패 케이스**라 성공 경로를 하나도 대조하지 않았다.
    #   두 도구는 이제 **서로 다른 사본**으로 판정한다 —
    #     `check_disposal_blockers` → 파일 정본(`load_laws`)
    #     `build_evidence_bundle`   → DB 사본(`load_laws_from_db`, W5 원천 일원화)
    #   사본이 갈리면 **같은 자산에 두 verdict** 가 나온다. `asset_tools_contract ㊹` 가
    #   MCP↔REST 축으로 전이적으로 덮긴 하지만 그건 **우연한 커버리지**지 설계된 방어선이 아니다.
    #   여기서 명시적으로 잠근다. ㉒(정본==사본)와 짝이다 — 그쪽이 원인, 이쪽이 증상을 본다.
    verdict_gaps = []
    for asset in ("AST-L3-CONV", "AST-L4-WRAP", "AST-L2-SPDL", "AST-L4-DUST", "AST-L3-LIFT"):
        for mode in ("SALE", "SCRAP"):
            kw = {"asset_id": asset, "disposal_mode": mode, "disposal_date": "2026-09-01"}
            j, b = check_disposal_blockers(**kw), call(**kw)
            # 번들이 `law_text_unavailable` 로 정상 거부하는 경우는 verdict 를 내지 않는다 —
            # 그건 판정 불일치가 아니라 증빙 생성 거부다(설계된 동작).
            if b.get("status") != "ok":
                continue
            if j.get("verdict") != b.get("verdict"):
                verdict_gaps.append(f"{asset}/{mode}: 파일={j.get('verdict')} DB={b.get('verdict')}")
    check(
        "두 도구의 성공 경로 verdict 일치 — 파일 정본 판정 == DB 사본 판정 (10조합)",
        not verdict_gaps,
        "; ".join(verdict_gaps) or "10조합 일치",
    )

    # ── ㉒ 실 DB 사본이 파일 정본과 **본문까지** 같은가 (D60·D82) ─────────────
    #
    #   ★ 이 번들은 **DB 사본으로 판정하고 그 사본을 해시한다**(W5 원천 일원화).
    #     그래서 DB 가 정본과 어긋나면 **서명이 폐지된 조문 원문에 걸린다** — 계층 3의 존재
    #     이유가 통째로 무너지는 자리다. 그런데 그걸 보는 검사가 어디에도 없었다:
    #
    #       `data/seed.py` ⑬   → `law_ref_id` **집합만** 비교. 본문이 달라도 통과한다
    #       `data/seed.py` ⑭   → 행 수 + 근거 없는 룰 0건. 룰 본문 미비교
    #       `spikes/rules_db_load.py` ①② → dataclass 전 필드 동치지만 **파일에서 갓 만든
    #                            임시 DB** 를 본다(㉕가 실 DB 미접근을 단언한다). 실 DB 를 열지 않는다
    #       `asset_tools_contract` ㊹㊺ → verdict 축만. `text_hash` 는 `evaluate_rule` 이
    #                            읽지 않으므로 **원리적으로** 검출 불가
    #
    #     실제로 열려 있는 창이다: `fetch_laws.py` 는 **파일만** 쓰고 DB 는 `seed.py` 를 거쳐야 한다.
    #     조문 개정(D75 `force=True`) 후 재시드를 빠뜨리면 파일·DB 가 둘 다 `FETCHED` 인데
    #     `text_hash` 만 다른 상태가 된다. 실측으로 확인했다 — 그 상태에서 ⑬ 은 True 를 낸다.
    #
    #   dataclass 동치로 본다. 로더 둘이 같은 dataclass 를 만들므로 필드가 늘어도 자동으로 덮인다.
    file_laws = engine.load_laws()
    file_rules = engine.load_rules(file_laws)
    with sqlite3.connect(f"file:{REAL_DB.as_posix()}?mode=ro", uri=True) as _con:
        _con.row_factory = sqlite3.Row
        db_laws = engine.load_laws_from_db(_con)
        db_rules = engine.load_rules_from_db(_con, db_laws)
    law_gap = sorted(k for k in set(file_laws) | set(db_laws) if file_laws.get(k) != db_laws.get(k))
    rule_gap = sorted(
        k for k in set(file_rules) | set(db_rules) if file_rules.get(k) != db_rules.get(k)
    )
    check(
        "실 DB 사본 == 파일 정본 (본문·해시까지 · 재시드 누락 감지) — 서명이 폐지 원문에 걸리는 것을 막는다",
        not law_gap and not rule_gap,
        f"laws 불일치={law_gap or '없음'} rules 불일치={rule_gap or '없음'} "
        f"(파일 {len(file_laws)}·{len(file_rules)} / DB {len(db_laws)}·{len(db_rules)})",
    )

    # ── ㉑ D10 — 실행 전체를 통틀어 실 DB 에 아무것도 쓰지 않았다 ─────────────
    after_stat = (REAL_DB.stat().st_mtime_ns, REAL_DB.stat().st_size)
    decisions_after = decisions_count(REAL_DB)
    check(
        "실 DB 불변 (mtime·size·decisions 행수) — 픽스처는 전부 임시 사본이었다 (D10)",
        before_stat == after_stat and decisions_before == decisions_after,
        f"{REAL_DB.name} size={after_stat[1]} · decisions {decisions_before}→{decisions_after}행",
    )

    width = max(len(name) for name, _, _ in results)
    print("─" * (width + 52))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 52))

    failed = [name for name, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건:\n  - " + "\n  - ".join(failed))
    print(
        f"\n통과 ({len(results)}건) — W5(원천 일원화·주입)·W6(rule_hash)·W7(evaluated)·"
        "계약 근거·N1(hash_spec)·N2(asset_modified) · D9·D10·D62·D82·D83 준수"
    )


if __name__ == "__main__":
    main()
