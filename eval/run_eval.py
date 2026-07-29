# -*- coding: utf-8 -*-
"""평가 실행 하네스 (MQ-502) — `eval/testset.json` 20문항을 실 에이전트 루프로 돌려 5지표를 낸다.

**무엇을 하는가.** `eval/score.py`(4지표: 부품 특정·근거 인용·안전 경고·시퀀스)와
`eval/judge.py`(환각률)를 소비해 실 서버(`backend.main:app`)에 `POST /api/chat` 을 실제로
쳐서 채점한다. `replay` 파라미터를 쓰지 않는다 — 실 루프가 실 MCP 도구를 호출해야
지표가 의미를 갖는다.

**비용 안전장치.** `--dry-run` 은 스키마 검증 + 비용 추정만 하고 API 호출·서버 기동 자체를
하지 않는다 (exit 0). 실행에는 `--yes` 또는 대화형 확인이 필요하다.

**`MAINTQ_MCP_AUTOSTART` 를 이 파일에서 건드리지 않는다.** env 딕셔너리는 부모 프로세스의
`os.environ` 을 그대로 상속한다 — 기본값(1, MCP 기동)을 그대로 쓴다. `sp3_sse_events.py`
처럼 `"0"` 으로 끄면 실 루프가 도구를 하나도 못 불러 20문항이 "도구 서버 연결 불가"로
조용히 전부 fail 한다 — 그래서 서버 기동 뒤 `GET /health` 로 `mcp:true` 를 확인하고,
아니면 즉시 `SystemExit` 한다(참사가 티가 나게).

**`test_` 접두 금지.** `.claude/settings.json` 의 Stop 훅이 매 턴 `pytest eval/ -q` 를
자동 실행한다. 이 파일은 실 LLM 호출을 포함하므로 pytest 가 뭔가를 테스트로 오인하면
매 턴 실비용 API 호출 사고가 된다 — 함수·파일명에 `test_` 를 쓰지 않는다.

**이 파일은 `eval/testset.json` 을 읽기만 한다.** 만들거나 고치지 않는다 — 그 파일은
사람이 `eval/testset_draft.json` 을 검수해 직접 반영한다(`guard_writes.py` 훅이 Claude
의 직접 반영을 차단, MQ-501/MQ-505 참조).

관련 결정: D40(LLM 폴백 금지)·D42(MCP lifespan 단독 소유)·D55(재생 표식 분모 제외)·
D56(env 상속)·D38(403 vs 409).

실행:
    uv run python eval/run_eval.py --testset eval/testset_draft.json --dry-run
    uv run python eval/run_eval.py --yes                # 실 20문항 (비용 발생, 사람 승인 필요)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval import score  # noqa: E402 — sys.path 설정 후여야 한다
from eval.judge import judge_hallucination  # noqa: E402

SOURCE_DB = ROOT / "data" / "maintq.db"
PORT = 8091
BASE_URL = f"http://127.0.0.1:{PORT}"

#: docs/09_RUNTIME.md §2 의 루프 상한 — 여기서는 비용 추정 문구용 참조값일 뿐,
#: 실 루프 동작은 backend/agent/loop.py 가 소유한다(이 상수를 복제해도 그 값을 바꾸지 못한다).
MAX_LLM_CALLS_PER_TURN = 10

#: 문항당 타임아웃(초) — 스트림 수신 + trace 조회 포함.
ITEM_TIMEOUT_S = 180.0

# X-User 는 ASCII 사용자 ID (D36) — data/seed.py 의 users 시드와 일치해야 한다.
TECH = {"X-Role": "technician", "X-User": "tech-01"}
MGR = {"X-Role": "manager", "X-User": "mgr-01"}

#: 실행 실패 문항을 response_text 에 남기는 표식 — ItemResult 스키마를 늘리지 않고도
#: write_report/aggregate 가 "그 문항만 실행 실패"를 식별할 수 있게 한다.
_EXEC_FAILED_PREFIX = "[EXECUTION_FAILED] "

_REQUIRED_TOP_KEYS = ("id", "input", "equipment_id", "role", "expected")
_REQUIRED_EXPECTED_KEYS = (
    "branch",
    "part_no",
    "safety_required",
    "expect_not_found",
    "expect_hold",
)
_VALID_BRANCHES = {"s1_pipeline", "s2_alternative", "s3_root_cause", "s4_not_found"}


@dataclass
class ItemResult:
    item_id: str
    branch: str
    expected: dict
    events: list[dict]  # GET /trace 의 events 그대로 (score.py 입력 형태)
    response_text: str  # SSE token 이벤트 누적 (traces엔 없음, D41)
    verdicts: list  # eval.score.Verdict 리스트, score_session() 반환
    judge: object | None  # eval.judge.JudgeVerdict | None
    elapsed_s: float


# ────────────────────────────────────────────── testset 로드·검증


def load_testset(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"[중단] testset 파일이 없습니다: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"[중단] testset 최상위는 배열이어야 합니다: {path}")
    return data


def validate_testset(items: list[dict]) -> None:
    """필수 키·enum·S3/S4 의 part_no·S3 의 expect_hold 를 검증한다.

    위반 시 위반 문항 id 를 나열하고 `SystemExit(1)` — 잘못된 기대값으로 채점하면
    "좋은 성적"이 가짜가 된다.
    """
    violations: list[str] = []
    for idx, item in enumerate(items):
        item_id = item.get("id", f"<id 없음, index={idx}>")
        reasons: list[str] = []

        for key in _REQUIRED_TOP_KEYS:
            if key not in item:
                reasons.append(f"'{key}' 키 없음")

        expected = item.get("expected")
        if not isinstance(expected, dict):
            reasons.append("'expected' 가 dict 아님/없음")
        else:
            missing = [k for k in _REQUIRED_EXPECTED_KEYS if k not in expected]
            if missing:
                reasons.append(f"expected 필수 키 누락: {missing}")

            branch = expected.get("branch")
            if branch not in _VALID_BRANCHES:
                reasons.append(f"branch enum 위반: {branch!r} (허용 {sorted(_VALID_BRANCHES)})")

            if branch in ("s3_root_cause", "s4_not_found") and expected.get("part_no") is not None:
                reasons.append(f"{branch} 인데 part_no != null: {expected.get('part_no')!r}")

            if branch == "s3_root_cause" and expected.get("expect_hold") is not True:
                reasons.append("s3_root_cause 인데 expect_hold != True")

        if reasons:
            violations.append(f"{item_id}: {'; '.join(reasons)}")

    if violations:
        print(f"[testset 검증 실패] {len(violations)}개 문항이 계약을 위반합니다:")
        for v in violations:
            print(f"  - {v}")
        raise SystemExit(1)


def estimate_cost(items: list[dict]) -> str:
    n = len(items)
    return (
        f"문항 {n}개 × 최대 {MAX_LLM_CALLS_PER_TURN}회 LLM 호출(MAX_LLM_CALLS_PER_TURN) = "
        f"최대 {n * MAX_LLM_CALLS_PER_TURN}회. 실측 평균 3~5회/문항 예상. 계속하시겠습니까? [y/N]"
    )


# ────────────────────────────────────────────── 서버 기동 (sp3 패턴 자체 구현, import 의존 없음)


def _start_server(db_copy: Path, port: int) -> subprocess.Popen:
    """`uv run uvicorn backend.main:app` 을 자식 프로세스로 띄운다.

    env 는 부모 `os.environ` 을 **그대로 상속**한다 — `MAINTQ_MCP_AUTOSTART` 를 여기서
    건드리지 않는 게 핵심(기본값 1 유지, GEMINI_API_KEY 등도 자연히 상속된다, D56).
    """
    env = {**os.environ, "MAINTQ_DB": str(db_copy)}
    return subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "backend.main:app",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


async def _wait_ready(base_url: str, timeout: float = 60.0) -> bool:
    """`/health` 폴링 — 요청은 적게, 타임아웃은 넉넉히 (Windows 소켓 바인딩 창 회피,
    `spikes/sp3_sse_events.py` `wait_ready()` 와 같은 이유)."""
    deadline = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            async with httpx.AsyncClient(timeout=timeout / 3) as c:
                r = await c.get(f"{base_url}/health")
                if r.status_code == 200:
                    return True
        except Exception:  # noqa: BLE001 — 아직 바인딩 전이면 연결 자체가 거부된다
            await asyncio.sleep(min(1.0 * attempt, 3.0))
    return False


def _parse_sse_frame(buf: str, on_event) -> str:
    """수신 버퍼에서 완성된 SSE 프레임(`event:`/`data:`)을 뽑아 콜백하고 잔여 버퍼를 돌려준다."""
    while "\n\n" in buf:
        frame, buf = buf.split("\n\n", 1)
        ev_name, data = None, None
        for line in frame.split("\n"):
            if line.startswith("event:"):
                ev_name = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if ev_name:
            on_event(ev_name, data or {})
    return buf


# ────────────────────────────────────────────── 문항 실행


async def run_item(base_url: str, item: dict) -> ItemResult:
    """문항 하나를 실 에이전트 루프로 실행하고 채점한다.

    `replay` 파라미터 없음(실 루프) — SSE 를 자체 파싱해 `response_text` 를 모으고,
    스트림 종료 후 `GET /trace` 로 채점용 events 를 가져온다.
    """
    item_id = item["id"]
    expected = item["expected"]
    branch = expected.get("branch", "")
    headers = MGR if item.get("role") == "manager" else TECH
    session_id = f"EVAL-{item_id}"

    payload = {
        "session_id": session_id,
        "message": item["input"],
        "equipment_id": item.get("equipment_id"),
    }

    t0 = time.monotonic()
    token_chunks: list[str] = []
    buf = ""

    async with httpx.AsyncClient(timeout=ITEM_TIMEOUT_S) as c:
        async with c.stream(
            "POST", f"{base_url}/api/chat", json=payload, headers=headers
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise RuntimeError(
                    f"POST /api/chat 실패: {resp.status_code} {body[:200]!r}"
                )

            def _on_event(ev_name: str, data: dict) -> None:
                if ev_name == "token":
                    token_chunks.append(str(data.get("text", "")))

            async for chunk in resp.aiter_text():
                buf = _parse_sse_frame(buf + chunk, _on_event)

        trace_resp = await c.get(f"{base_url}/api/chat/{session_id}/trace", headers=headers)

    elapsed_s = time.monotonic() - t0
    response_text = "".join(token_chunks)
    events = trace_resp.json().get("events", [])

    verdicts = score.score_session(events, expected)
    judge = None
    if expected.get("expect_not_found"):
        judge = await judge_hallucination(item["input"], response_text)

    return ItemResult(
        item_id=item_id,
        branch=branch,
        expected=expected,
        events=events,
        response_text=response_text,
        verdicts=verdicts,
        judge=judge,
        elapsed_s=elapsed_s,
    )


async def _run_all(base_url: str, items: list[dict]) -> list[ItemResult]:
    """문항 루프. 한 문항이 예외를 내도 나머지는 계속 실행한다(엣지 케이스 명세)."""
    results: list[ItemResult] = []
    total = len(items)
    for i, item in enumerate(items, start=1):
        item_id = item.get("id", f"#{i}")
        print(f"[{i}/{total}] {item_id} 실행 중...")
        t0 = time.monotonic()
        try:
            result = await run_item(base_url, item)
        except Exception as exc:  # noqa: BLE001 — 이 문항만 "실행 실패", 나머지는 계속
            elapsed = time.monotonic() - t0
            expected = item.get("expected") or {}
            print(f"  [실행 실패] {item_id}: {exc}")
            result = ItemResult(
                item_id=item_id,
                branch=expected.get("branch", ""),
                expected=expected,
                events=[],
                response_text=f"{_EXEC_FAILED_PREFIX}{exc}",
                # 근거 없이 pass 를 주지 않는다 — 빈 이벤트로 채점하면 자연히 fail 로 계상된다.
                verdicts=score.score_session([], expected),
                judge=None,
                elapsed_s=elapsed,
            )
        results.append(result)
    return results


def check_permission_403(base_url: str) -> tuple[bool, str]:
    """문항 루프와 별개 1회 — 승인 큐 첫 pending 건에 technician 으로 approve 시도 (403 기대).

    pending 건이 없으면 임의로 pass 처리하지 않고 `(False, "N/A")` 를 즉시 돌려준다.
    """
    with httpx.Client(timeout=30.0) as c:
        r = c.get(f"{base_url}/api/po", params={"state": "pending"}, headers=MGR)
        items = (r.json() or {}).get("items", [])
        if not items:
            return False, "N/A"
        po_id = items[0]["po_id"]
        r2 = c.post(f"{base_url}/api/po/{po_id}/approve", headers=TECH)
        detail = ""
        try:
            detail = str(r2.json().get("detail", ""))[:120]
        except Exception:  # noqa: BLE001 — 상태 코드만 있어도 판정엔 충분
            pass
        return r2.status_code == 403, f"{r2.status_code} {detail}"


# ────────────────────────────────────────────── 집계·리포트


def aggregate(results: list) -> dict:
    """5지표 집계. `has_replay()` 로 재생 오염 세션을 분모에서 제외한다 (D55).

    **실행 실패 문항도 전 지표 분모에서 제외한다.** `score_session([], expected)` 로 채점하면
    `part`/`citation`/`safety` 는 자연히 fail 로 떨어지지만, `sequence` 는
    `_judge_sequence` 가 "create_po_draft 미호출"을 근거로 **공허하게 PASS** 를 반환한다
    (`eval/score.py` — 도구가 아예 안 불린 것과 "정확히 호출 안 했다"를 구분 못 함).
    서버가 죽어 문항이 통째로 실행 안 됐는데 "시퀀스 제약 준수"로 집계되면 "좋은 것만
    보고"의 역설이 된다 — 이 지표는 애초에 **측정 불가**이지 합격이 아니다. 그래서 replay
    와 같은 방식으로 분모에서 뺀다. 실패 사실 자체는 `failed_items`/문항별 상세에서
    계속 눈에 띄게 보고한다(감추지 않는다) — 집계 수치만 정직해지는 것이다.
    """
    kept = [
        r
        for r in results
        if not score.has_replay(r.events) and not r.response_text.startswith(_EXEC_FAILED_PREFIX)
    ]
    excluded_replay = sum(1 for r in results if score.has_replay(r.events))
    excluded_failed = len(results) - len(kept) - excluded_replay

    metrics: dict[str, dict] = {}
    for metric in ("part", "citation", "safety", "sequence"):
        passed, total = score.metric_rate([r.verdicts for r in kept], metric)
        metrics[metric] = {
            "passed": passed,
            "total": total,
            "rate": (passed / total) if total else None,
        }

    judged = [r for r in kept if r.judge is not None]
    hallucinated = sum(1 for r in judged if r.judge.hallucinated)
    metrics["hallucination"] = {
        "hallucinated": hallucinated,
        "total": len(judged),
        "rate": (hallucinated / len(judged)) if judged else None,
    }

    failed_items = [r.item_id for r in results if r.response_text.startswith(_EXEC_FAILED_PREFIX)]

    return {
        "n_items": len(results),
        "n_kept": len(kept),
        "excluded_replay": excluded_replay,
        "excluded_failed": excluded_failed,
        "metrics": metrics,
        "failed_items": failed_items,
    }


def _metric_row(label: str, d: dict, goal: float, *, lower_is_better: bool = False) -> str:
    if d["total"] == 0:
        return f"| {label} | 0/0 | N/A | N/A |"
    rate = d["rate"]
    count = d.get("passed", d.get("hallucinated"))
    ok = (rate <= goal) if lower_is_better else (rate >= goal)
    return f"| {label} | {count}/{d['total']} | {rate:.1%} | {'PASS' if ok else 'FAIL'} |"


def write_report(results, agg, perm_result, out_dir: Path) -> Path:
    """`eval/results/{날짜}.md`+`.json` 생성. 5지표 전부(좋은 것만 골라내지 않는다)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = out_dir / f"{stamp}.json"
    md_path = out_dir / f"{stamp}.md"

    perm_ok, perm_detail = perm_result
    perm_verdict = "N/A" if perm_detail == "N/A" else ("PASS" if perm_ok else "FAIL")

    json_payload = {
        "generated_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "aggregate": agg,
        "permission_403": {"passed": perm_ok, "detail": perm_detail, "verdict": perm_verdict},
        "items": [
            {
                "item_id": r.item_id,
                "branch": r.branch,
                "expected": r.expected,
                "response_text": r.response_text,
                "elapsed_s": r.elapsed_s,
                "verdicts": [
                    {
                        "metric": v.metric,
                        "passed": v.passed,
                        "detail": v.detail,
                        "applicable": v.applicable,
                    }
                    for v in r.verdicts
                ],
                "judge": (
                    {"hallucinated": r.judge.hallucinated, "rationale": r.judge.rationale}
                    if r.judge is not None
                    else None
                ),
            }
            for r in results
        ],
    }
    json_path.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    m = agg["metrics"]
    lines: list[str] = [
        f"# MaintQ 평가 결과 — {stamp}",
        "",
        "> ⚠ **경고**: `related_parts.seed.json` 은 아직 사람 검수 전이다(D12) — 이 결과의 부품",
        "> 특정 정확률을 최종 실적으로 인용하지 말 것. `eval/testset.json` 도 초안",
        "> (`eval/testset_review_notes.md`) 기반일 수 있다 — testset 확정 전 잠정치.",
        "",
        f"완주: {agg['n_items']}문항 (재생 오염으로 분모 제외 {agg['excluded_replay']}건 · "
        f"실행 실패로 분모 제외 {agg['excluded_failed']}건 — 실행 실패는 아래 문항별 상세 참조)",
    ]
    if agg["failed_items"]:
        lines.append(f"실행 실패: {len(agg['failed_items'])}건 — {', '.join(agg['failed_items'])}")
    lines += [
        "",
        "## 5지표",
        "",
        "| 지표 | 통과/분모 | 비율 | 판정 |",
        "|---|---|---|---|",
        _metric_row("부품 특정 정확률 (목표 ≥90%)", m["part"], 0.90),
        _metric_row("근거 페이지 인용률 (목표 100%)", m["citation"], 1.00),
        _metric_row("안전 경고 누락 0건 (목표 100%)", m["safety"], 1.00),
        _metric_row("미지 코드 환각률 (목표 0%)", m["hallucination"], 0.0, lower_is_better=True),
        _metric_row("시퀀스 제약 준수 (목표 100%)", m["sequence"], 1.00),
        f"| 권한 위반 403 (목표 100%) | - | - | {perm_verdict} ({perm_detail}) |",
        "",
        "## 문항별 상세",
        "",
    ]
    for r in results:
        lines.append(f"### {r.item_id} ({r.branch})")
        if r.response_text.startswith(_EXEC_FAILED_PREFIX):
            lines.append(f"- **실행 실패**: {r.response_text[len(_EXEC_FAILED_PREFIX):]}")
        else:
            for v in r.verdicts:
                mark = "PASS" if v.passed else "FAIL"
                applicable = "" if v.applicable else " (분모 제외)"
                lines.append(f"- [{mark}] {v.metric}{applicable}: {v.detail}")
            if r.judge is not None:
                lines.append(
                    f"- [judge] hallucinated={r.judge.hallucinated} — {r.judge.rationale}"
                )
        lines.append(f"- elapsed: {r.elapsed_s:.1f}s")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def diff_against_previous(agg: dict, out_dir: Path) -> str:
    """`out_dir` 내 최신 `.json` 과 비교. 없으면 "최초 실행"."""
    if not out_dir.exists():
        return "최초 실행 — 비교 대상 없음"
    prior = sorted(out_dir.glob("*.json"))
    if not prior:
        return "최초 실행 — 비교 대상 없음"

    prev_path = prior[-1]
    try:
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return f"최초 실행 — 이전 결과 로드 실패 ({prev_path.name}: {exc})"

    prev_metrics = (prev.get("aggregate") or {}).get("metrics", {})
    lines = [f"이전 결과({prev_path.stem}) 대비:"]
    for key in ("part", "citation", "safety", "sequence", "hallucination"):
        cur = agg["metrics"].get(key, {})
        old = prev_metrics.get(key, {})
        cur_rate, old_rate = cur.get("rate"), old.get("rate")
        if cur_rate is None or old_rate is None:
            lines.append(f"  - {key}: 비교 불가 (분모 0)")
        else:
            delta = (cur_rate - old_rate) * 100
            lines.append(f"  - {key}: {old_rate:.1%} → {cur_rate:.1%} ({delta:+.1f}pt)")
    return "\n".join(lines)


def _print_summary(agg: dict, perm_result: tuple[bool, str]) -> None:
    """5지표 항상 전부 콘솔 출력 — 좋은 것만 보고 금지."""
    print("=== 5지표 요약 ===")
    m = agg["metrics"]

    def _console_line(label: str, d: dict, goal: float, *, lower_is_better: bool = False) -> None:
        if d["total"] == 0:
            print(f"  {label}: 0/0 (N/A)")
            return
        rate = d["rate"]
        count = d.get("passed", d.get("hallucinated"))
        ok = (rate <= goal) if lower_is_better else (rate >= goal)
        print(f"  {label}: {count}/{d['total']} = {rate:.1%} ({'PASS' if ok else 'FAIL'})")

    _console_line("부품 특정 정확률(목표 ≥90%)", m["part"], 0.90)
    _console_line("근거 페이지 인용률(목표 100%)", m["citation"], 1.00)
    _console_line("안전 경고 누락 0건(목표 100%)", m["safety"], 1.00)
    _console_line("미지 코드 환각률(목표 0%)", m["hallucination"], 0.0, lower_is_better=True)
    _console_line("시퀀스 제약 준수(목표 100%)", m["sequence"], 1.00)

    perm_ok, perm_detail = perm_result
    perm_verdict = "N/A" if perm_detail == "N/A" else ("PASS" if perm_ok else "FAIL")
    print(f"  권한 위반 403(목표 100%): {perm_verdict} ({perm_detail})")

    if agg["excluded_replay"]:
        print(f"  [주의] 재생 세션 {agg['excluded_replay']}건이 분모에서 제외됐습니다(정상은 0).")
    if agg["excluded_failed"]:
        print(
            f"  [주의] 실행 실패 {agg['excluded_failed']}건이 전 지표 분모에서 제외됐습니다"
            f"(정상은 0) — 문항: {', '.join(agg['failed_items'])}"
        )


# ────────────────────────────────────────────── CLI


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="MaintQ 평가셋 실행 (eval/testset.json)")
    parser.add_argument("--testset", type=Path, default=Path("eval/testset.json"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=Path("eval/results"))
    args = parser.parse_args()

    all_items = load_testset(args.testset)
    validate_testset(all_items)
    print(f"testset 검증 통과: {len(all_items)}문항 ({args.testset})")

    items = all_items if args.limit is None else all_items[: args.limit]
    if args.limit is not None:
        print(f"[부분 실행] ({len(items)}/{len(all_items)})")

    print(estimate_cost(items))

    if args.dry_run:
        print("[--dry-run] 스키마 검증 + 비용 추정만 수행 — API 호출 0회로 종료합니다.")
        return

    if not args.yes:
        if not sys.stdin.isatty():
            raise SystemExit("[중단] 비대화형 환경에서는 --yes 없이 진행할 수 없습니다.")
        answer = input("계속 진행합니까? [y/N] ").strip().lower()
        if answer != "y":
            raise SystemExit("[중단] 사용자가 취소했습니다.")

    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    err_bytes = b""
    with tempfile.TemporaryDirectory() as td:
        db_copy = Path(td) / "eval.db"
        shutil.copy2(SOURCE_DB, db_copy)

        proc = _start_server(db_copy, PORT)
        try:
            if not asyncio.run(_wait_ready(BASE_URL)):
                err = proc.stderr.read().decode("utf-8", "replace")[-800:] if proc.stderr else ""
                raise SystemExit(f"[중단] 서버가 뜨지 않았습니다\n{err}")

            health = httpx.get(f"{BASE_URL}/health", timeout=10.0).json()
            if not health.get("mcp"):
                raise SystemExit(
                    f"[중단] MCP 가 기동하지 않았습니다({health}) — 이대로 진행하면 전체 문항이 "
                    "'도구 서버 연결 불가'로 조용히 fail 처리됩니다. MAINTQ_MCP_AUTOSTART·"
                    "GEMINI_API_KEY 등 환경을 확인하세요."
                )

            results = asyncio.run(_run_all(BASE_URL, items))
            perm_result = check_permission_403(BASE_URL)
        finally:
            proc.terminate()
            try:
                _, err_bytes = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                _, err_bytes = proc.communicate()

    if err_bytes:
        stderr_text = err_bytes.decode("utf-8", "replace")
        if stderr_text.strip():
            print(f"\n[서버 stderr 끝부분]\n{stderr_text[-1200:]}")

    agg = aggregate(results)
    diff_text = diff_against_previous(agg, args.out_dir)
    report_path = write_report(results, agg, perm_result, args.out_dir)

    print()
    print(diff_text)
    print()
    _print_summary(agg, perm_result)
    print(f"\n리포트: {report_path}")


if __name__ == "__main__":
    main()
