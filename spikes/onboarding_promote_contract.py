# -*- coding: utf-8 -*-
"""MQ-1909 — 온보딩 승격·안전 승인 사람 전용 API 계약 (D156·D157·D10·D81, docs/sprints/sprint-19.md).

고정하는 것:
  Ⓐ 순수 함수 — D156 병합 규칙(접두·severity·빈 cause 제외·중복 제거·900자 원인 단위 분할)과
     안전 문안 숫자 검증(`check_safety_text`, safety-guardrail 규칙 1·3). DB 없이 돈다.
  Ⓑ REST — 권한 403(technician) 4종 · 미등록 사용자 400 · promote 검증 reason 전종 ·
     **원자성**(chunk_id 충돌 → `error_codes`·행 state·promotions 불변) · 정상 승격 후
     `lookup_error_code` ok·manual_page 일치 · `rag.search("HV600", 한국어)` 히트(D148) ·
     안전 승인 `number_not_in_source`·`wait_value_mismatch`·`already_approved_for_model` ·
     `GET /status` 네 상태(none·onboarding·safety_pending·ready — `safety_source.resolve` 를 실제로
     호출하는지 호출 수 앵커 포함).
  앵커: 정상 승격 1건·정상 승인 1건이 **실제로 행을 만든다**(부재 검사만으로 통과하지 않게).

픽스처는 **합성 문장**이다(D144) — 실제 HV600 매뉴얼 문장을 복제하지 않는다. 구조만 실측
HV600 표를 흉내낸다(같은 코드가 Fault·Minor·Backup 3구역 · 같은 구역 안 이름이 다른 CE 쌍).

DB 쓰기는 전부 `data/pg_isolation.create_isolated_schema()` 격리 스키마에서만 한다 — 공유
`public` 에는 승격·승인하지 않는다(사람 H3·H4 몫). 사람 커넥션(`backend.db`)과 읽기 도구
커넥션(`mcp_server.db`)을 둘 다 같은 격리 DSN 으로 돌린다.

실행:
  DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" \\
  uv run python spikes/onboarding_promote_contract.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 라우터 계약만 본다 — MCP stdio 서브프로세스를 띄우지 않는다(api_contract 와 같은 탈출구).
os.environ["MAINTQ_MCP_AUTOSTART"] = "0"
# 키가 있으면 dense 경로가 실 API 를 탄다 — 키워드 경로만으로 결정론을 본다(onboarding_rag_contract 선례).
os.environ.pop("NVIDIA_API_KEY", None)
os.environ["MAINTQ_CHUNKS"] = str(ROOT / "spikes" / "fixtures" / "onboarding_chunks.jsonl")

from data import dbcompat, pg_isolation  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, bool(ok), detail))


# ── Ⓐ 순수 함수 ──────────────────────────────────────────────────────────────


def _row(row_id, ordinal, section, name_en, causes_en, pages, display="oH", code="OH"):
    return {
        "row_id": row_id, "ordinal": ordinal, "model": "HV600", "code": code,
        "display_code": display, "section_en": section, "name_en": name_en,
        "causes_en": json.dumps(causes_en), "pages": json.dumps(pages), "norm_id": row_id * 10,
    }


def run_pure() -> None:
    from backend.services import onboarding as svc  # noqa: PLC0415

    check(
        "Ⓐ-1 SECTION_KO 고정 사전 + Backup 접두",
        svc.section_ko("Fault") == "고장"
        and svc.section_ko("Minor Faults/Alarms") == "경알람"
        and svc.section_ko("Parameter Setting Errors") == "파라미터 설정 오류"
        and svc.section_ko("Auto-Tuning Errors") == "오토튜닝 오류"
        and svc.section_ko("Backup Function Operating Mode Display and Errors") == "백업·복원 오류",
        "5종 매핑",
    )

    en = [{"cause": "syn cause A", "solutions": ["syn sol 1", "syn sol 2"]}]
    rows = [
        _row(2, 5, "Minor Faults/Alarms", "Syn Overheat", en, [115, 116]),
        _row(1, 9, "Fault", "Syn Overheat", en, [108, 107]),
        _row(3, 1, "Backup Function Operating Mode Display and Errors", "Syn Overheat", en, [120]),
    ]
    norms = {
        10: {"name_ko": "가상 과열", "causes_ko": json.dumps([
            {"cause": "가상 원인 가", "solutions": ["가상 조치 1", "가상 조치 1", "가상 조치 2"]},
            {"cause": "", "solutions": ["가상 조치 3"]},
        ])},
        20: {"name_ko": "가상 과열 알람", "causes_ko": json.dumps([
            {"cause": "가상 원인 나", "solutions": ["가상 조치 1"]}])},
        30: {"name_ko": "가상 백업 오류", "causes_ko": json.dumps([
            {"cause": "가상 원인 다", "solutions": ["가상 조치 4"]}])},
    }
    ec = svc.build_error_code_row(rows, norms, primary_row_id=1, manual_id="syn-manual")
    check(
        "Ⓐ-2 error_name = name_ko (name_en) · display/code = primary · manual_page = min(primary.pages)",
        ec["error_name"] == "가상 과열 (Syn Overheat)" and ec["display_code"] == "oH"
        and ec["code"] == "OH" and ec["manual_page"] == 107
        and ec["actions_manual_id"] == "syn-manual" and ec["actions_page"] == 107
        and ec["related_parts"] == [],
        f"{ec['error_name']!r} page={ec['manual_page']}",
    )
    check(
        "Ⓐ-3 순서 primary 먼저 → ordinal 오름차순 · 2행 이상 [구역·이름] 접두 · 빈 cause 제외",
        ec["causes"] == [
            "[고장·가상 과열] 가상 원인 가",
            "[백업·복원 오류·가상 백업 오류] 가상 원인 다",
            "[경알람·가상 과열 알람] 가상 원인 나",
        ],
        f"{ec['causes']}",
    )
    check(
        "Ⓐ-4 actions 평탄화 · 완전 동일 문자열만 중복 제거(순서 유지) · 접두가 다르면 유지",
        ec["actions"] == [
            "[고장·가상 과열] 가상 조치 1",
            "[고장·가상 과열] 가상 조치 2",
            "[고장·가상 과열] 가상 조치 3",
            "[백업·복원 오류·가상 백업 오류] 가상 조치 4",
            "[경알람·가상 과열 알람] 가상 조치 1",
        ],
        f"{ec['actions']}",
    )
    check("Ⓐ-5 severity: primary 구역 Fault → 'fault'", ec["severity"] == "fault", ec["severity"])
    ec2 = svc.build_error_code_row(rows, norms, primary_row_id=2, manual_id="syn-manual")
    check(
        "Ⓐ-6 severity: primary 구역 Fault 아님 → 'warning' (critical 자동 부여 없음)",
        ec2["severity"] == "warning" and ec2["manual_page"] == 115,
        f"{ec2['severity']} page={ec2['manual_page']}",
    )
    single = svc.build_error_code_row([rows[1]], {10: norms[10]}, 1, "syn-manual")
    check(
        "Ⓐ-7 1행 그룹은 접두 없음",
        single["causes"] == ["가상 원인 가"] and single["actions"][0] == "가상 조치 1",
        f"{single['causes']}",
    )

    chunks = svc.build_chunks(rows, norms, "syn-manual")
    c1 = [c for c in chunks if c["chunk_id"] == "syn-manual-onb-oh-r1"]
    check(
        "Ⓐ-8 청크 id·page=min(row.pages)·section·헤더·[원문]·char_len",
        len(c1) == 1 and c1[0]["page"] == 107 and c1[0]["section"] == "Troubleshooting · Fault"
        and c1[0]["text"].startswith("[oH] 가상 과열 (Syn Overheat) — 고장\n원인: 가상 원인 가\n조치: ")
        and "[원문] syn cause A / syn sol 1; syn sol 2" in c1[0]["text"]
        and c1[0]["char_len"] == len(c1[0]["text"]) and len(chunks) == 3,
        f"n={len(chunks)} ids={[c['chunk_id'] for c in chunks]}",
    )

    # 900자 분할 — 원인 12건 × ~150자. 자르지 않고 원인 단위로 나뉘는지.
    long_en = [{"cause": f"syn long cause {i} " + "x" * 60, "solutions": ["y" * 30]} for i in range(12)]
    long_ko = [{"cause": f"가상 긴 원인 {i} " + "가" * 60, "solutions": ["나" * 30]} for i in range(12)]
    lrow = _row(7, 0, "Fault", "Syn Long", long_en, [110], code="LG", display="LG")
    lchunks = svc.build_chunks([lrow], {70: {"name_ko": "가상 긴", "causes_ko": json.dumps(long_ko)}}, "m")
    all_text = "\n".join(c["text"] for c in lchunks)
    check(
        "Ⓐ-9 900자 초과 → 원인 단위 분할(-c1..) · 각 ≤900 · 원인 12건 전부 보존(절단 없음, D53)",
        len(lchunks) >= 2
        and all(c["char_len"] <= svc.MAX_CHARS for c in lchunks)
        and [c["chunk_id"] for c in lchunks] == [f"m-onb-lg-r7-c{i}" for i in range(1, len(lchunks) + 1)]
        and all(f"가상 긴 원인 {i} " + "가" * 60 in all_text for i in range(12))
        and all(f"syn long cause {i} " in all_text for i in range(12))
        and all(c["text"].startswith("[LG] 가상 긴 (Syn Long) — 고장\n") for c in lchunks),
        f"청크 {len(lchunks)}개 · 길이 {[c['char_len'] for c in lchunks]}",
    )
    huge_ko = [{"cause": "가" * 1200, "solutions": []}]
    huge_en = [{"cause": "z" * 10, "solutions": []}]
    hrow = _row(8, 0, "Fault", "Syn Huge", huge_en, [111], code="HG", display="HG")
    hchunks = svc.build_chunks([hrow], {80: {"name_ko": "가상 거대", "causes_ko": json.dumps(huge_ko)}}, "m")
    check(
        "Ⓐ-10 원인 1건이 단독으로 900자 초과 → 자르지 않고 그대로 1청크(D53)",
        len(hchunks) == 1 and "가" * 1200 in hchunks[0]["text"] and hchunks[0]["chunk_id"] == "m-onb-hg-r8",
        f"len={hchunks[0]['char_len']}",
    )

    cases = [
        ("5분 대기", None, "number_not_in_source"),
        ("전원 차단 후 대기", None, None),
        ("5 분 대기", None, "number_not_in_source"),
        ("10분 이상 대기", 10, None),
        ("5분 이상 대기", 10, "wait_value_mismatch"),
        ("15분 대기", 5, "wait_value_mismatch"),
        ("5분(또는 3분) 대기", 5, "wait_value_mismatch"),
        ("충분히 대기", 5, "wait_value_mismatch"),
    ]
    got = [(t, n, svc.check_safety_text(t, n)) for t, n, _ in cases]
    check(
        "Ⓐ-11 안전 문안 숫자 검증 8케이스 (규칙 1 원문에 없는 숫자 · 규칙 3 명시값·경계 15분≠5분)",
        all(g[2] == c[2] for g, c in zip(got, cases, strict=True)),
        f"{[g[2] for g in got]}",
    )


# ── Ⓑ REST (격리 스키마) ───────────────────────────────────────────────────────

MANUAL_ID = "syn-hv600-iopm"
TECH = {}  # 헤더 없음 = X-Role technician · X-User tech-01 (D108 기본값)
MGR = {"X-Role": "manager", "X-User": "mgr-01"}


def _cause(tag: str, n: int = 1) -> tuple[list, list]:
    en = [{"cause": f"syn {tag} cause {i}", "solutions": [f"syn {tag} fix {i}"]} for i in range(n)]
    ko = [{"cause": f"가상 {tag} 원인 {i}", "solutions": [f"가상 {tag} 조치 {i}"]} for i in range(n)]
    return en, ko


def seed_fixture(dsn: str) -> dict:
    """합성 HV600 배치 1건 — 반환: {key: row_id}·{key: norm_id}·{key: cand_id}."""
    con = dbcompat.connect_dsn(dsn)
    ids: dict = {"row": {}, "norm": {}, "cand": {}}
    try:
        batch_id = con.execute(
            "INSERT INTO onboarding_batches (model, manual_id, pdf_sha256, candidates_sha256, loaded_by)"
            " VALUES ('HV600', ?, 'syn-pdf', 'syn-cand', 'spike') RETURNING batch_id",
            (MANUAL_ID,),
        ).fetchone()["batch_id"]
        ids["batch"] = batch_id
        specs = [
            # key, ordinal, code, display, section, name_en, pages, source_flags, name_ko, tag
            ("oh_f", 0, "OH", "oH", "Fault", "Syn Heatsink Overheat", [107], [], "가상 방열판 과열", "과열"),
            ("oh_m", 20, "OH", "OH", "Minor Faults/Alarms", "Syn Heatsink Overheat", [115, 116], [],
             "가상 방열판 과열 알람", "과열알람"),
            ("oh_b", 30, "OH", "oH", "Backup Function Operating Mode Display and Errors",
             "Syn Heatsink Overheat", [120], [], "가상 백업 과열", "백업"),
            ("ce_f", 1, "CE", "CE", "Fault", "Syn Modbus Error", [107], [], "가상 통신 오류", "통신"),
            ("ce_m1", 21, "CE", "CE", "Minor Faults/Alarms", "Syn Modbus Error", [116], [],
             "가상 통신 오류 알람", "통신알람"),
            ("ce_m2", 22, "CE", "CE", "Minor Faults/Alarms", "Syn Go-To-Freq", [116], [],
             "가상 통신 이상 시 지정 주파수 운전", "통신주파수"),
            ("gf", 2, "GF", "GF", "Fault", "Syn Ground Fault", [108], ["injection_suspect"], "가상 지락", "지락"),
            ("uv", 3, "UV", "Uv", "Fault", "Syn Undervoltage", [109], [], "가상 저전압", "저전압"),
            ("lf", 4, "LF", "LF", "Fault", "Syn Output Phase Loss", [110], [], "가상 결상", "결상"),
            ("pf_f", 5, "PF", "PF", "Fault", "Syn Input Phase Loss", [110], [], "가상 입력 결상", "입력결상"),
            ("pf_m", 23, "PF", "PF", "Minor Faults/Alarms", "Syn Input Phase Loss", [117], [],
             "가상 입력 결상 알람", "입력결상알람"),
        ]
        for key, ordinal, code, display, section, name_en, pages, flags, name_ko, tag in specs:
            en, ko = _cause(tag, 2)
            rid = con.execute(
                "INSERT INTO onboarding_code_rows (batch_id, ordinal, model, code, display_code,"
                " section_en, name_en, causes_en, pages, source_flags)"
                " VALUES (?, ?, 'HV600', ?, ?, ?, ?, ?, ?, ?) RETURNING row_id",
                (batch_id, ordinal, code, display, section, name_en,
                 json.dumps(en), json.dumps(pages), json.dumps(flags)),
            ).fetchone()["row_id"]
            ids["row"][key] = rid
            nid = con.execute(
                "INSERT INTO onboarding_normalizations (row_id, name_ko, causes_ko, confidence, flags, staged_by)"
                " VALUES (?, ?, ?, 'high', '[]', 'spike') RETURNING norm_id",
                (rid, name_ko, json.dumps(ko, ensure_ascii=False)),
            ).fetchone()["norm_id"]
            ids["norm"][key] = nid
        # oh_f 재정규화 1건 더 — norms 는 norm_id 내림차순, 첫 항목이 최신. 최신 norm 에는 low 플래그.
        en, ko = _cause("과열", 2)
        ids["norm"]["oh_f_v2"] = con.execute(
            "INSERT INTO onboarding_normalizations (row_id, name_ko, causes_ko, confidence, flags, staged_by)"
            " VALUES (?, '가상 방열판 과열(재)', ?, 'low', '[\"low_confidence\"]', 'spike') RETURNING norm_id",
            (ids["row"]["oh_f"], json.dumps(ko, ensure_ascii=False)),
        ).fetchone()["norm_id"]

        cands = [
            ("dw10", 0, 20, "discharge_wait", 10),
            ("dw10b", 1, 21, "discharge_wait", 10),
            ("live", 2, 66, "live_work", None),
            ("other", 3, 7, "other", None),
        ]
        for key, ordinal, page, kind, wait in cands:
            ids["cand"][key] = con.execute(
                "INSERT INTO onboarding_safety_candidates (batch_id, ordinal, model, page, kind, quote_en,"
                " wait_minutes_in_text) VALUES (?, ?, 'HV600', ?, ?, ?, ?) RETURNING cand_id",
                (batch_id, ordinal, page, kind, f"syn quote {key}", wait),
            ).fetchone()["cand_id"]
        con.commit()
    finally:
        con.close()
    return ids


def _q(dsn: str, sql: str, params=()) -> list:
    con = dbcompat.connect_dsn(dsn)
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def run_rest(client, dsn: str, ids: dict) -> None:
    from backend.services import onboarding as svc  # noqa: PLC0415
    from mcp_server.tools.lookup_error_code import lookup_error_code  # noqa: PLC0415

    R, N, C = ids["row"], ids["norm"], ids["cand"]

    def body(code, keys, primary, ack=(), norm_override=None):
        norm_override = norm_override or {}
        return {
            "model": "HV600", "code": code, "primary_row_id": R[primary],
            "rows": [{"row_id": R[k], "norm_id": norm_override.get(k, N[k])} for k in keys],
            "acknowledged_flags": list(ack),
        }

    # resolve 호출 수 앵커 — 서비스가 MQ-1910 resolve 를 실제로 부르는지.
    calls: list[str] = []
    real_resolve = svc.resolve_safety

    def counting(model):
        calls.append(model)
        return real_resolve(model)

    svc.resolve_safety = counting

    # ── status: none / onboarding ──
    s_none = client.get("/api/onboarding/status", params={"model": "iG5A"})
    s_onb = client.get("/api/onboarding/status", params={"model": "HV600"})
    s_bad = client.get("/api/onboarding/status", params={"model": "XYZ"})
    check("Ⓑ-status-none iG5A(배치 0) → none", s_none.status_code == 200 and s_none.json()["state"] == "none",
          f"{s_none.status_code} {s_none.json()}")
    check("Ⓑ-status-onboarding HV600(배치 1·승격 0) → onboarding",
          s_onb.status_code == 200 and s_onb.json() == {"model": "HV600", "state": "onboarding"},
          f"{s_onb.json()}")
    check("Ⓑ-status-422 model ∉ MODELS", s_bad.status_code == 422, f"{s_bad.status_code}")

    # ── 권한 403 4종 + 400 ──
    r403 = [
        client.post("/api/onboarding/promote", json=body("OH", ["oh_f", "oh_m", "oh_b"], "oh_f"), headers=TECH),
        client.post(f"/api/onboarding/rows/{R['lf']}/reject", json={"note": "x"}, headers=TECH),
        client.post(f"/api/onboarding/safety/{C['dw10']}/approve",
                    json={"approved_text": "10분 대기", "text_reviewed": True}, headers=TECH),
        client.post(f"/api/onboarding/safety/{C['other']}/reject", json={"note": "x"}, headers=TECH),
    ]
    check("Ⓑ-1 technician(헤더 누락) → 쓰기 4종 전부 403", all(r.status_code == 403 for r in r403),
          f"{[r.status_code for r in r403]}")
    r400 = client.post(f"/api/onboarding/rows/{R['lf']}/reject", json={"note": "x"},
                       headers={"X-Role": "manager", "X-User": "ghost-99"})
    check("Ⓑ-2 manager 이지만 users 에 없는 X-User → 400", r400.status_code == 400, f"{r400.status_code}")

    # ── GET batches / groups ──
    gb = client.get("/api/onboarding/batches", headers=MGR)
    b = next((x for x in gb.json() if x["batch_id"] == ids["batch"]), {}) if gb.status_code == 200 else {}
    check("Ⓑ-3 GET /batches 집계(rows 11·staged 11·normalized_rows 11)",
          gb.status_code == 200 and b.get("rows") == 11 and b.get("staged") == 11
          and b.get("approved") == 0 and b.get("normalized_rows") == 11 and b.get("manual_id") == MANUAL_ID,
          f"{b}")
    gg = client.get(f"/api/onboarding/batches/{ids['batch']}/groups", params={"state": "staged"})
    groups = {g["code"]: g for g in gg.json()} if gg.status_code == 200 else {}
    oh_rows = groups.get("OH", {}).get("rows", [])
    oh_f = next((r for r in oh_rows if r["row_id"] == R["oh_f"]), {})
    check("Ⓑ-4 GET /groups — 코드별 그룹 · section_ko · norms norm_id 내림차순(최신 먼저)",
          gg.status_code == 200 and set(groups) == {"OH", "CE", "GF", "UV", "LF", "PF"}
          and len(oh_rows) == 3 and oh_f.get("section_ko") == "고장"
          and [n["norm_id"] for n in oh_f.get("norms", [])] == [N["oh_f_v2"], N["oh_f"]]
          and groups["OH"]["promoted"] is False,
          f"codes={sorted(groups)} norms={[n['norm_id'] for n in oh_f.get('norms', [])]}")
    g404 = client.get("/api/onboarding/batches/999999/groups")
    g422 = client.get(f"/api/onboarding/batches/{ids['batch']}/groups", params={"state": "bogus"})
    check("Ⓑ-5 GET /groups 없는 batch 404 · state 밖 422", g404.status_code == 404 and g422.status_code == 422,
          f"{g404.status_code} {g422.status_code}")

    # ── promote 검증 ──
    def post(b_, headers=MGR):
        return client.post("/api/onboarding/promote", json=b_, headers=headers)

    before_ec = _q(dsn, "SELECT count(*) AS n FROM error_codes")[0]["n"]
    r = post({**body("OH", ["oh_f"], "oh_f"), "model": "iG5A"})
    check("Ⓑ-6 시드 기종 → 422 seed_model_not_onboardable",
          r.status_code == 422 and r.json().get("reason") == "seed_model_not_onboardable", f"{r.status_code} {r.json()}")
    r = post({**body("OH", ["oh_f"], "oh_f"), "model": "XYZ"})
    check("Ⓑ-7 model 밖 → 422 invalid_model", r.status_code == 422 and r.json().get("reason") == "invalid_model",
          f"{r.status_code}")
    r = post({"model": "HV600", "code": "OH", "primary_row_id": 999999,
              "rows": [{"row_id": 999999, "norm_id": N["oh_f"]}]})
    check("Ⓑ-8 없는 row_id → 404", r.status_code == 404, f"{r.status_code}")
    r = post(body("OH", ["oh_f", "gf"], "oh_f"))
    check("Ⓑ-9 다른 그룹 섞임 → 422 mixed_group",
          r.status_code == 422 and r.json().get("reason") == "mixed_group" and r.json().get("row_ids") == [R["gf"]],
          f"{r.status_code} {r.json()}")
    r = post({**body("OH", ["oh_f", "oh_m", "oh_b"], "oh_f"), "primary_row_id": R["ce_f"]})
    check("Ⓑ-10 primary_row_id ∉ rows → 422", r.status_code == 422, f"{r.status_code} {r.json()}")
    r = post(body("OH", ["oh_f", "oh_m", "oh_b"], "oh_f", norm_override={"oh_m": N["oh_f"]}))
    check("Ⓑ-11 norm_id 가 그 row 소속 아님 → 422 norm_mismatch",
          r.status_code == 422 and r.json().get("reason") == "norm_mismatch", f"{r.status_code} {r.json()}")
    r = post(body("OH", ["oh_f", "oh_m"], "oh_f"))
    check("Ⓑ-12 그룹 staged 행 누락 → 422 group_incomplete + 누락 row_ids",
          r.status_code == 422 and r.json().get("reason") == "group_incomplete"
          and r.json().get("row_ids") == [R["oh_b"]], f"{r.status_code} {r.json()}")
    r = post(body("OH", ["oh_f", "oh_m", "oh_b"], "oh_f", norm_override={"oh_f": N["oh_f_v2"]}))
    check("Ⓑ-13 선택 norm 의 flags 미확인 → 422 flags_not_acknowledged + 목록",
          r.status_code == 422 and r.json().get("reason") == "flags_not_acknowledged"
          and r.json().get("flags") == ["low_confidence"], f"{r.status_code} {r.json()}")
    r = post(body("GF", ["gf"], "gf"))
    check("Ⓑ-14 행 source_flags 미확인 → 422 flags_not_acknowledged",
          r.status_code == 422 and r.json().get("flags") == ["injection_suspect"], f"{r.status_code} {r.json()}")
    after_ec = _q(dsn, "SELECT count(*) AS n FROM error_codes")[0]["n"]
    staged_now = _q(dsn, "SELECT count(*) AS n FROM onboarding_code_rows WHERE state='staged'")[0]["n"]
    check("Ⓑ-15 검증 실패 9건 뒤 error_codes·staged 행 불변 (앵커: 기준값 > 0)",
          before_ec == after_ec and before_ec > 0 and staged_now == 11, f"error_codes {before_ec}→{after_ec} staged={staged_now}")

    # ── 원자성: chunk_id 충돌 ──
    look_uv_before = lookup_error_code("HV600", "UV")
    con = dbcompat.connect_dsn(dsn)
    try:
        con.execute(
            "INSERT INTO manual_chunks (chunk_id, manual_id, model, page, section, text, char_len)"
            " VALUES (?, ?, 'HV600', 1, 'syn', 'syn blocker', 11)",
            (f"{MANUAL_ID}-onb-uv-r{R['uv']}", MANUAL_ID),
        )
        con.commit()
    finally:
        con.close()
    r = post(body("UV", ["uv"], "uv"))
    uv_ec = _q(dsn, "SELECT count(*) AS n FROM error_codes WHERE model='HV600' AND code='UV'")[0]["n"]
    uv_state = _q(dsn, "SELECT state FROM onboarding_code_rows WHERE row_id=?", (R["uv"],))[0]["state"]
    uv_promo = _q(dsn, "SELECT count(*) AS n FROM onboarding_promotions WHERE code='UV'")[0]["n"]
    check("Ⓑ-16 원자성 — chunk_id 충돌 → 409 chunk_id_conflict · error_codes 0 · 행 staged · promotions 0",
          r.status_code == 409 and r.json().get("reason") == "chunk_id_conflict"
          and uv_ec == 0 and uv_state == "staged" and uv_promo == 0,
          f"{r.status_code} {r.json().get('reason')} ec={uv_ec} state={uv_state} promo={uv_promo}")

    # ── 정상 승격 (앵커) ──
    look_before = lookup_error_code("HV600", "OH")
    check("Ⓑ-17 승격 전 lookup(HV600, OH) → not_found (D146 — 유사 코드 제안 없음)",
          look_before.get("status") == "not_found" and look_uv_before.get("status") == "not_found",
          f"{look_before.get('status')}")
    r = post(body("OH", ["oh_m", "oh_b", "oh_f"], "oh_f"))
    j = r.json() if r.status_code == 201 else {}
    ec = j.get("error_code", {})
    check("Ⓑ-18 정상 승격 → 201 · 응답 셰이프 · primary 표기(oH)·error_name·severity·actions_source",
          r.status_code == 201 and isinstance(j.get("promo_id"), int)
          and ec.get("display_code") == "oH" and ec.get("error_name") == "가상 방열판 과열 (Syn Heatsink Overheat)"
          and ec.get("severity") == "fault" and ec.get("manual_page") == 107
          and ec.get("actions_source") == {"manual_id": MANUAL_ID, "page": 107}
          and ec.get("causes", [""])[0].startswith("[고장·가상 방열판 과열] ")
          and len(j.get("chunk_ids", [])) == 3,
          f"{r.status_code} {json.dumps(j, ensure_ascii=False)[:300]}")
    db_ec = _q(dsn, "SELECT * FROM error_codes WHERE model='HV600' AND code='OH'")
    db_rows = _q(dsn, "SELECT state, reviewed_by FROM onboarding_code_rows WHERE code='OH'")
    db_promo = _q(dsn, "SELECT row_ids, chunk_ids, promoted_by FROM onboarding_promotions WHERE code='OH'")
    db_chunks = _q(dsn, "SELECT chunk_id, embedding FROM manual_chunks WHERE chunk_id LIKE ?",
                   (f"{MANUAL_ID}-onb-oh-%",))
    check("Ⓑ-19 앵커 — 실제 행 생성: error_codes 1 · 청크 3(embedding NULL) · 행 3 approved(reviewed_by) · promotions 1",
          len(db_ec) == 1 and len(db_chunks) == 3 and all(c["embedding"] is None for c in db_chunks)
          and len(db_rows) == 3 and all(x["state"] == "approved" and x["reviewed_by"] == "mgr-01" for x in db_rows)
          and len(db_promo) == 1 and json.loads(db_promo[0]["row_ids"])[0] == R["oh_f"]
          and db_promo[0]["promoted_by"] == "mgr-01",
          f"ec={len(db_ec)} chunks={len(db_chunks)} rows={db_rows} promo={db_promo}")
    look = lookup_error_code("HV600", "OH")
    check("Ⓑ-20 승격 후 lookup_error_code(HV600, OH) → ok · manual_page 일치",
          look.get("status") == "ok" and look.get("manual_page") == ec.get("manual_page") == 107,
          f"{look.get('status')} page={look.get('manual_page')}")
    r = post(body("OH", ["oh_f", "oh_m", "oh_b"], "oh_f"))
    check("Ⓑ-21 재승격 → 409 already_promoted", r.status_code == 409 and r.json().get("reason") == "already_promoted",
          f"{r.status_code} {r.json()}")

    # CE — 같은 구역 안 이름이 다른 쌍도 접두로 구분
    r = post(body("CE", ["ce_f", "ce_m1", "ce_m2"], "ce_m1"))
    ce = r.json().get("error_code", {}) if r.status_code == 201 else {}
    prefixes = sorted({c.split("] ")[0] + "]" for c in ce.get("causes", [])})
    check("Ⓑ-22 CE(같은 구역 이름 반복) — 3행 접두 3종 구분 · primary 경알람 → warning",
          r.status_code == 201 and ce.get("severity") == "warning" and len(prefixes) == 3
          and "[경알람·가상 통신 이상 시 지정 주파수 운전]" in prefixes, f"{r.status_code} {prefixes}")

    # GF — 플래그 확인 후 승격 · 확인 목록이 이력에 남는다
    r = post(body("GF", ["gf"], "gf", ack=["injection_suspect"]))
    gf_promo = _q(dsn, "SELECT acknowledged_flags FROM onboarding_promotions WHERE code='GF'")
    check("Ⓑ-23 플래그 확인 후 승격 201 · acknowledged_flags 기록",
          r.status_code == 201 and gf_promo and json.loads(gf_promo[0]["acknowledged_flags"]) == ["injection_suspect"],
          f"{r.status_code} {gf_promo}")

    # ── rag.search — 한국어 질의로 승격 청크 히트 (MQ-1906 경로) ──
    for mod in ("mcp_server.tools.rag_search_manual", "mcp_server.rag"):
        sys.modules.pop(mod, None)
    from mcp_server import rag  # noqa: PLC0415

    hits = rag.search("HV600", "방열판 과열 원인", top_k=3)
    check("Ⓑ-24 rag.search(HV600, 한국어) 히트 ≥1 · 승격 청크 · page 원문 물리 페이지",
          len(hits) >= 1 and hits[0]["chunk_id"].startswith(f"{MANUAL_ID}-onb-oh-") and hits[0]["page"] in (107, 115, 120),
          f"{[(h['chunk_id'], h['page']) for h in hits]}")

    # ── reject ──
    r_empty = client.post(f"/api/onboarding/rows/{R['lf']}/reject", json={"note": "  "}, headers=MGR)
    r_ok = client.post(f"/api/onboarding/rows/{R['lf']}/reject", json={"note": "가상 번역 오류"}, headers=MGR)
    r_again = client.post(f"/api/onboarding/rows/{R['lf']}/reject", json={"note": "다시"}, headers=MGR)
    r_404 = client.post("/api/onboarding/rows/999999/reject", json={"note": "x"}, headers=MGR)
    lf = _q(dsn, "SELECT state, review_note FROM onboarding_code_rows WHERE row_id=?", (R["lf"],))[0]
    check("Ⓑ-25 행 반려 — 공백 note 422 · 200 {row_id, state:rejected} · 재반려 409 · 없음 404",
          r_empty.status_code == 422 and r_ok.status_code == 200
          and r_ok.json() == {"row_id": R["lf"], "state": "rejected"}
          and r_again.status_code == 409 and r_404.status_code == 404 and lf["state"] == "rejected",
          f"{r_empty.status_code} {r_ok.status_code} {r_again.status_code} {r_404.status_code} {lf}")
    # PF — 누락 방지 → 한 행을 먼저 반려하면 나머지로 승격 가능
    r1 = post(body("PF", ["pf_f"], "pf_f"))
    client.post(f"/api/onboarding/rows/{R['pf_m']}/reject", json={"note": "가상 중복 알람"}, headers=MGR)
    r2 = post(body("PF", ["pf_f"], "pf_f"))
    r3 = post(body("PF", ["pf_m"], "pf_m"))
    check("Ⓑ-26 group_incomplete → 누락 행 반려 후 승격 201 · 반려 행 포함 시도는 already_promoted 가 먼저",
          r1.status_code == 422 and r1.json().get("reason") == "group_incomplete"
          and r2.status_code == 201 and r3.status_code == 409,
          f"{r1.status_code} {r2.status_code} {r3.status_code}")

    # ── status: safety_pending ──
    s_pend = client.get("/api/onboarding/status", params={"model": "HV600"})
    check("Ⓑ-status-safety_pending 승격 ≥1 · 안전 승인 0 → safety_pending",
          s_pend.json() == {"model": "HV600", "state": "safety_pending"}, f"{s_pend.json()}")

    # ── safety ──
    ls = client.get("/api/onboarding/safety", params={"model": "HV600"})
    check("Ⓑ-27 GET /safety 셰이프(4건 · also_pages list · staged)",
          ls.status_code == 200 and len(ls.json()) == 4
          and set(ls.json()[0]) == {"cand_id", "page", "also_pages", "kind", "quote_en", "wait_minutes_in_text",
                                    "state", "approved_text", "approved_by", "approved_at", "text_reviewed_at"}
          and all(x["state"] == "staged" and x["also_pages"] == [] for x in ls.json()),
          f"{ls.status_code} n={len(ls.json())}")

    def approve(key, text, reviewed=True):
        return client.post(f"/api/onboarding/safety/{C[key]}/approve",
                           json={"approved_text": text, "text_reviewed": reviewed}, headers=MGR)

    a1 = approve("live", "가상 문안 — 5분 대기")
    a2 = approve("dw10", "가상 문안 — 5분 이상 대기")
    a3 = approve("dw10", "가상 문안 — 110분 대기")
    a4 = approve("dw10", "가상 문안 — 10분 이상 대기", reviewed=False)
    a5 = approve("dw10", "가상 문안 — 10분 이상 대기", reviewed="true")
    a6 = approve("dw10", "   ")
    check("Ⓑ-28 number_not_in_source(원문 숫자 없음) 422",
          a1.status_code == 422 and a1.json().get("reason") == "number_not_in_source", f"{a1.status_code} {a1.json()}")
    check("Ⓑ-29 wait_value_mismatch(5분·110분 ≠ 10분) 422",
          a2.status_code == 422 and a2.json().get("reason") == "wait_value_mismatch"
          and a3.status_code == 422 and a3.json().get("reason") == "wait_value_mismatch",
          f"{a2.status_code} {a3.status_code}")
    check("Ⓑ-30 text_reviewed false·문자열 \"true\" 422 · 공백 문안 422",
          a4.status_code == 422 and a5.status_code == 422 and a6.status_code == 422,
          f"{a4.status_code} {a5.status_code} {a6.status_code}")
    still = _q(dsn, "SELECT count(*) AS n FROM onboarding_safety_candidates WHERE state='approved'")[0]["n"]
    ok = approve("dw10", "가상 문안 — 전원 차단 후 10분 이상 대기")
    row = _q(dsn, "SELECT state, approved_text, approved_by, approved_at, text_reviewed_at"
                  " FROM onboarding_safety_candidates WHERE cand_id=?", (C["dw10"],))[0]
    check("Ⓑ-31 앵커 — 정상 승인 200 · 행 approved·문안·승인자·두 날짜 기록 (실패 6건 동안 approved 0)",
          still == 0 and ok.status_code == 200 and row["state"] == "approved"
          and row["approved_text"] == "가상 문안 — 전원 차단 후 10분 이상 대기"
          and row["approved_by"] == "mgr-01" and row["approved_at"] is not None
          and row["text_reviewed_at"] is not None, f"{ok.status_code} {row}")
    dup = approve("dw10b", "가상 문안 — 10분 이상 대기")
    check("Ⓑ-32 같은 기종 discharge_wait 2번째 승인 → 409 already_approved_for_model (D157)",
          dup.status_code == 409 and dup.json().get("reason") == "already_approved_for_model",
          f"{dup.status_code} {dup.json()}")
    again = approve("dw10", "가상 문안 — 10분 이상 대기")
    check("Ⓑ-33 이미 approved 후보 재승인 → 409", again.status_code == 409, f"{again.status_code}")
    rj0 = client.post(f"/api/onboarding/safety/{C['other']}/reject", json={"note": ""}, headers=MGR)
    rj1 = client.post(f"/api/onboarding/safety/{C['other']}/reject", json={"note": "가상 무관 문구"}, headers=MGR)
    rj2 = client.post(f"/api/onboarding/safety/{C['other']}/reject", json={"note": "다시"}, headers=MGR)
    check("Ⓑ-34 안전 후보 반려 — 공백 422 · 200 · 재반려 409",
          rj0.status_code == 422 and rj1.status_code == 200 and rj2.status_code == 409,
          f"{rj0.status_code} {rj1.status_code} {rj2.status_code}")

    # ── Ⓑ-36 시드 기종 안전 후보 승인·반려 차단 (D109 ⓐ·D148) ──
    # IE5 는 enum 에 있지만 안전 문구를 확장하지 않는다. 별도 IE5 배치를 만들어(HV600 배치
    # 집계 Ⓑ-3·iG5A 배치 0 Ⓑ-status-none 을 건드리지 않게 이 시점에) 후보 1건을 심는다.
    con = dbcompat.connect_dsn(dsn)
    try:
        ie5_batch = con.execute(
            "INSERT INTO onboarding_batches (model, manual_id, pdf_sha256, candidates_sha256, loaded_by)"
            " VALUES ('IE5', 'syn-ie5', 'syn-pdf', 'syn-cand-ie5', 'spike') RETURNING batch_id"
        ).fetchone()["batch_id"]
        ie5_cand = con.execute(
            "INSERT INTO onboarding_safety_candidates (batch_id, ordinal, model, page, kind, quote_en,"
            " wait_minutes_in_text) VALUES (?, 0, 'IE5', 9, 'discharge_wait', 'syn quote ie5', 10)"
            " RETURNING cand_id",
            (ie5_batch,),
        ).fetchone()["cand_id"]
        con.commit()
    finally:
        con.close()
    s_app = client.post(f"/api/onboarding/safety/{ie5_cand}/approve",
                        json={"approved_text": "가상 문안 — 10분 이상 대기", "text_reviewed": True}, headers=MGR)
    s_rej = client.post(f"/api/onboarding/safety/{ie5_cand}/reject", json={"note": "가상"}, headers=MGR)
    ie5_row = _q(dsn, "SELECT state FROM onboarding_safety_candidates WHERE cand_id=?", (ie5_cand,))
    # 양성 앵커: 같은 요청 셰이프가 HV600 에서는 200 을 받았다(Ⓑ-31 ok) · IE5 후보 행이 실제로 존재.
    check("Ⓑ-36 시드 기종(IE5) 안전 후보 승인·반려 → 422 seed_model_not_onboardable · 행 staged 유지"
          " (앵커: HV600 같은 셰이프 200 · IE5 행 1건)",
          s_app.status_code == 422 and s_app.json().get("reason") == "seed_model_not_onboardable"
          and s_rej.status_code == 422 and s_rej.json().get("reason") == "seed_model_not_onboardable"
          and len(ie5_row) == 1 and ie5_row[0]["state"] == "staged" and ok.status_code == 200,
          f"approve={s_app.status_code} {s_app.json().get('reason')} reject={s_rej.status_code}"
          f" {s_rej.json().get('reason')} ie5_rows={ie5_row} hv600_ok={ok.status_code}")

    # ── Ⓑ-37 D39 — 저장은 UTC(now_utc_sql), GET 은 `Z` 붙은 ISO ──
    iso_z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    ls2 = client.get("/api/onboarding/safety", params={"model": "HV600"}).json()
    appr = next((x for x in ls2 if x["cand_id"] == C["dw10"]), {})
    gb2 = client.get("/api/onboarding/batches", headers=MGR).json()
    b2 = next((x for x in gb2 if x["batch_id"] == ids["batch"]), {})
    gg2 = client.get(f"/api/onboarding/batches/{ids['batch']}/groups", params={"state": "staged"}).json()
    norm_ts = [n["created_at"] for g in gg2 for r_ in g["rows"] for n in r_["norms"]]
    stamps = [appr.get("approved_at"), appr.get("text_reviewed_at"), b2.get("loaded_at"), *norm_ts]
    raw = row["approved_at"]  # 저장값(naive) — UTC 벽시계와 5분 이내여야 한다
    try:
        skew = abs((datetime.now(timezone.utc).replace(tzinfo=None)
                    - datetime.strptime(str(raw)[:19], "%Y-%m-%d %H:%M:%S")).total_seconds())
    except ValueError:
        skew = float("inf")
    check("Ⓑ-37 D39 — GET 시각 전부 `…Z` ISO · 저장 approved_at 이 UTC 벽시계 ±300s"
          " (앵커: 검사한 시각 ≥ 4개)",
          len(stamps) >= 4 and all(isinstance(t, str) and iso_z.match(t) for t in stamps) and skew <= 300,
          f"n={len(stamps)} bad={[t for t in stamps if not (isinstance(t, str) and iso_z.match(t))]}"
          f" sample={stamps[:2]} skew={skew:.0f}s")

    # ── Ⓑ-38 GET /batches `manual_doc` — manifest `file` stem (D19 단일 원천, 계약 확장) ──
    # 실 manifest 의 `hv600-iopm` 을 가리키는 행 0건짜리 배치를 이 시점에 심는다(앞선 집계·
    # status 검사를 건드리지 않게 — status 는 promotions 로 판정해 배치 수 1→2 는 무영향).
    con = dbcompat.connect_dsn(dsn)
    try:
        real_batch = con.execute(
            "INSERT INTO onboarding_batches (model, manual_id, pdf_sha256, candidates_sha256, loaded_by)"
            " VALUES ('HV600', 'hv600-iopm', 'syn-pdf', 'syn-cand-real', 'spike') RETURNING batch_id"
        ).fetchone()["batch_id"]
        con.commit()
    finally:
        con.close()
    gb3 = client.get("/api/onboarding/batches", headers=MGR)
    by_id = {x["batch_id"]: x for x in gb3.json()} if gb3.status_code == 200 else {}
    real_b, syn_b = by_id.get(real_batch, {}), by_id.get(ids["batch"], {})
    base_keys = {"batch_id", "model", "manual_id", "loaded_at", "rows", "staged", "approved",
                 "rejected", "normalized_rows"}
    check("Ⓑ-38 GET /batches manual_doc — hv600-iopm → 'TOEPC71061732'(양성) · manifest 밖 id → null"
          " · 기존 9필드 불변",
          real_b.get("manual_doc") == "TOEPC71061732"
          and "manual_doc" in syn_b and syn_b["manual_doc"] is None
          and base_keys <= set(real_b) and set(real_b) - base_keys == {"manual_doc"},
          f"real={real_b.get('manual_id')}→{real_b.get('manual_doc')!r}"
          f" syn={syn_b.get('manual_id')}→{syn_b.get('manual_doc', '<키 없음>')!r}"
          f" extra={sorted(set(real_b) - base_keys)}")

    # ── status: ready ──
    n_before = len(calls)
    s_ready = client.get("/api/onboarding/status", params={"model": "HV600"})
    from backend.agent.safety_source import resolve  # noqa: PLC0415

    entry = resolve("HV600")
    check("Ⓑ-status-ready 승격 ≥1 + 승인 1건 → ready · resolve 가 승인 문안·페이지를 돌려준다",
          s_ready.json() == {"model": "HV600", "state": "ready"}
          and entry is not None and entry.text == "가상 문안 — 전원 차단 후 10분 이상 대기" and entry.page == 20,
          f"{s_ready.json()} entry={entry and (entry.text, entry.page)}")
    check("Ⓑ-35 앵커 — /status 가 safety_source.resolve 를 실제로 호출(두 벌 판정 금지)",
          len(calls) >= 2 and len(calls) > n_before and set(calls) == {"HV600"},
          f"resolve 호출 {len(calls)}회: {calls}")
    svc.resolve_safety = real_resolve


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    print("온보딩 승격·안전 승인 사람 전용 API 계약 검증 (D156·D157 · MQ-1909)\n")

    run_pure()

    if not dbcompat.USE_POSTGRES:
        check("Ⓑ 전체 (DB 격리 스키마 검사)", False, "DATABASE_URL 미설정")
    else:
        import backend.db as bdb  # noqa: PLC0415
        from mcp_server import db as mdb  # noqa: PLC0415

        schema, dsn = pg_isolation.create_isolated_schema("onboarding_promote")
        bdb.DB_PATH = dsn
        mdb.DB_PATH = dsn
        try:
            ids = seed_fixture(dsn)
            from fastapi.testclient import TestClient  # noqa: PLC0415

            from backend.main import app  # noqa: PLC0415

            with TestClient(app) as client:
                run_rest(client, dsn, ids)
        finally:
            bdb.DB_PATH = None
            mdb.DB_PATH = None
            pg_isolation.drop_isolated_schema(schema)

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 40))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 40))
    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(f"\n통과 ({len(results)}건) — D156 병합·원자성 · D157 기종당 승인 1건 · 권한 403 · status 4상태 확인")


if __name__ == "__main__":
    main()
