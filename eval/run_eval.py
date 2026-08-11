# -*- coding: utf-8 -*-
"""평가 실행 하네스 (MQ-502) — `eval/testset.json` 20문항을 실 에이전트 루프로 돌려 5지표를 낸다.

**무엇을 하는가.** `eval/score.py`(4지표: 부품 특정·근거 인용·안전 경고·시퀀스)와
`eval/judge.py`(환각률)를 소비해 실 서버(`backend.main:app`)에 `POST /api/chat` 을 실제로
쳐서 채점한다. `replay` 파라미터를 쓰지 않는다 — 실 루프가 실 MCP 도구를 호출해야
지표가 의미를 갖는다.

**비용 안전장치.** `--dry-run` 은 스키마 검증 + 비용 추정 + **D88 프로파일 가드 확인**만 한다
(exit 0, 위반 시 exit 2). 실행에는 `--yes` 또는 대화형 확인이 필요하다.

**`--dry-run` 은 LLM 을 단 1회도 호출하지 않는다.** 가드가 읽는 `/health` 는 실측값(D69 의
`tools` = `list_tools()` 개수)이라 서버가 있어야 얻을 수 있으므로, dry-run 도 **임시 포트에
서버를 띄워 `/health` 만 읽고 즉시 내린다** — 문항 루프(`_run_stage`)에는 들어가지 않으므로
모델 호출은 0회다. "가드를 순수 함수로 분리"(`profile_violations`)와 "실측 health 조회"를
둘 다 하는 이유: 가드 로직은 스파이크가 서버 없이 검증하고, 실행 경로는 가짜값이 아닌
실측으로 판정해야 하기 때문이다.

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

**결과물은 한 타임스탬프로 4개다** (MQ-713a — 4차 평가 전 계측):

    {stamp}.json          5지표 + meta + 문항별 상세 (items[].session_id 로 아래와 이어진다)
    {stamp}.md            사람이 읽는 리포트
    {stamp}.traces.jsonl  ★ 임시 DB 의 `traces` 전량 (tool_payload 포함, D76-2)
    {stamp}.server.log    ★ 자식 서버 stderr 원문 — 잘림 계측 `[LLM_END]` 의 원본

`--repeat N`(N>1) 이면 회차별 산출물이 `{stamp}.r{k}.traces.jsonl`·`{stamp}.r{k}.server.log`
로 갈리고, `.json`/`.md` 는 **합산 1벌**에 회차별 요약(`rounds[]`)과 흔들림(`flip`)을 함께 싣는다.
N==1 이면 파일 이름은 3차까지와 **완전히 같다**(접미사 없음).

**`--repeat` 가 왜 있는가 (MQ-713b, `data/analysis/eval_gap_3rd.md §6` 후보 3).** 3차 분석 §4 의
실측: 같은 코드·같은 문항인데 2차와 3차에서 **판정이 뒤집힌 문항이 7개**였다. 그 위에서
프롬프트를 고치고 단일 실행으로 4차를 돌리면 나온 증감이 **수정 효과인지 응답 요동인지
구분되지 않는다.** 그래서 회차를 반복해 문항×지표별로 `안정 통과 / 안정 실패 / 흔들림` 을
먼저 가른다 — 튜닝의 성패는 **`안정 실패` → `안정 통과` 로 넘어간 칸**으로만 판정한다.
⛔ 회차는 **DB 사본·서버·포트를 각각 새로 만든다**(독립 표본). 공유하면 1회차가 쌓은
`po_drafts`·`traces` 를 2회차가 보게 되어 요동이 아니라 누적 상태를 재게 된다.

`.traces.jsonl` 이 필요한 이유: `_start_server` 가 DB **사본**으로 서버를 띄우고 종료 시
사본을 폐기하므로, 실 DB 보호는 되지만 **판정 근거가 실행과 함께 사라졌다.** 3차 평가에서
`traces` 가 0행이라 "도구가 실제로 무엇을 반환했는지"를 사후 대조하지 못했다.

관련 결정: D40(LLM 폴백 금지)·D42(MCP lifespan 단독 소유)·D55(재생 표식 분모 제외)·
D56(env 상속)·D38(403 vs 409)·D69(프로파일 게이트)·**D88(이중 게이트)**·
D21(trace 영속화)·**D76-2(`tool_payload`)**.

실행:
    uv run python eval/run_eval.py --testset eval/testset_draft.json --dry-run
    uv run python eval/run_eval.py --yes                # 실 20문항 (비용 발생, 사람 승인 필요)
    uv run python eval/run_eval.py --yes --repeat 3     # 반복 3회차 — 비용도 정확히 3배
    uv run python eval/run_eval.py --yes --allow-full-profile   # full 프로파일 의도적 실행
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# `judge_hallucination`(eval/judge.py) 은 스폰된 백엔드 서버가 아니라 **이 프로세스 자신**
# 에서 `get_client()`(D40) 를 직접 호출한다 — backend/main.py 의 lifespan 이 하는
# load_dotenv() 는 이 프로세스엔 적용되지 않으므로 여기서 직접 한 번 더 로드해야 한다
# (2026-07-29 실 20문항 실행에서 S4 문항만 매번 "MAINTQ_LLM_MODEL 없음"으로 실패해 발견).
load_dotenv(ROOT / ".env", override=False)

from backend.agent.loop import (  # noqa: E402 — 마커 형식은 생산자(loop.py)가 정본이다
    LLM_END_MARKER,
    TRUNCATION_REASONS,
)
from eval import score  # noqa: E402 — sys.path 설정 후여야 한다
from eval.judge import JudgeVerdict, judge_hallucination  # noqa: E402

SOURCE_DB = ROOT / "data" / "maintq.db"

#: ⛔ 고정 포트를 쓰지 않는다. `--repeat` 가 회차마다 서버를 새로 띄우는데, Windows 는
#: `taskkill` 직후 같은 포트를 다시 bind 하는 창에서 실패하거나 **직전 회차의 소켓에 붙는다**
#: (`_shutdown_server` docstring 이 기록한 그 자리다). 회차마다 `_free_port()` 로 잡는다.

#: core 프로파일의 도구 수 (04_MCP_TOOLS §1~§7). 확장 8종(§8~§15)은 `MAINTQ_TOOLS_PROFILE=full`
#: 에서만 등록된다 (D69) — 그래서 실측 개수가 7을 넘으면 core 가 아니다.
CORE_TOOL_COUNT = 7

#: docs/09_RUNTIME.md §2 의 루프 상한 — 여기서는 비용 추정 문구용 참조값일 뿐,
#: 실 루프 동작은 backend/agent/loop.py 가 소유한다(이 상수를 복제해도 그 값을 바꾸지 못한다).
MAX_LLM_CALLS_PER_TURN = 10

#: 문항당 타임아웃(초) — 스트림 수신 + trace 조회 + (S4형 문항) judge 호출까지 포함.
#: judge_hallucination 은 `get_client()`(D40) 를 직접 호출하는 별도 네트워크 호출이라
#: httpx.AsyncClient(timeout=...) 의 보호 범위 밖이다 — asyncio.wait_for 로 별도로 감싼다
#: (2026-07-29 실 20문항 실행 중 무제한 대기로 60분+ 멈춤 관측, 사후 수정).
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
    #: 문항 ↔ traces 덤프를 잇는 키. 결과 JSON 의 `items[]` 에 실어야 `.traces.jsonl` 과
    #: 대조가 성립한다 — 3차까지 없어서 원본 대조(MQ-703 명세)를 하지 못했다.
    session_id: str = ""
    #: 몇 회차의 결과인가 (`--repeat`). 단일 실행이면 항상 1 — 기존 소비자는 무시해도 된다.
    #: 회차를 문항에 실어야 `{stamp}.r{k}.traces.jsonl` 과 문항을 짝지을 수 있다.
    round: int = 1


def session_id_for(item_id: str) -> str:
    """문항 id → 세션 id. **한 곳에서만 만든다** — 실행 경로와 실행 실패 경로가 갈리면
    실패한 문항의 trace 를 덤프에서 못 찾는다."""
    return f"EVAL-{item_id}"


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


def estimate_cost(items: list[dict], repeat: int = 1) -> str:
    """비용 문구. **`repeat` 를 곱해서 보여 준다** — 반복 실행은 비용이 정확히 N 배다.
    곱하지 않으면 사람이 1 회분 비용에 동의하고 3 회분을 쓰게 된다.
    """
    n = len(items)
    rounds = f" × {repeat}회차" if repeat > 1 else ""
    return (
        f"문항 {n}개{rounds} × 최대 {MAX_LLM_CALLS_PER_TURN}회 LLM 호출(MAX_LLM_CALLS_PER_TURN) = "
        f"최대 {n * repeat * MAX_LLM_CALLS_PER_TURN}회. 실측 평균 3~5회/문항 예상. "
        "계속하시겠습니까? [y/N]"
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


def _shutdown_server(proc: subprocess.Popen) -> bytes:
    """스폰한 서버를 **프로세스 트리째** 정리하고 stderr 를 회수한다.

    `proc` 는 `uv run uvicorn ...` 이라 실제 서버는 손자 프로세스다. `proc.terminate()`
    는 직계 자식(`uv`)만 죽이므로 uvicorn 과 그 밑의 MCP 서버(D15, 프로세스 분리)가
    **고아로 살아남아 상속받은 stderr 파이프 쓰기 핸들을 계속 쥔다.** 그러면
    `communicate()` 는 EOF 를 영원히 받지 못한다 — 타임아웃 없는 두 번째
    `communicate()` 호출이 무한 블록되는 경로였다(2026-08-05 실측: 20문항 실행이 전부
    끝난 뒤 46분간 CPU 0% 로 정지, `eval/results/` 미생성). 2026-07-30 세션이
    'Windows 소켓 문제'로 분류했던 증상과 같은 자리다.

    그래서 **트리 전체를 죽인 뒤** stderr 를 읽고, 마지막 회수에도 반드시 상한을 둔다.
    stderr 는 진단 편의를 위한 것이므로 회수 실패는 평가 실패가 아니다 — 빈 바이트를
    돌려주고 계속 진행한다(여기서 예외를 던지면 이미 끝난 20문항 결과가 통째로 날아간다).
    """
    if os.name == "nt":
        # taskkill /T 는 자식 트리까지 함께 종료한다. 이미 죽은 PID 면 조용히 실패한다.
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
        )
    else:
        proc.terminate()

    for attempt in (10, 5):
        try:
            _, err = proc.communicate(timeout=attempt)
            return err or b""
        except subprocess.TimeoutExpired:
            proc.kill()
    print("[경고] 서버 stderr 회수 실패 — 고아 프로세스가 남았을 수 있습니다(집계는 계속합니다)")
    return b""


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


# ────────────────────────────────────────────── D88 프로파일 가드


def profile_violations(health: dict) -> list[str]:
    """`/health` 응답을 받아 D88 위반 사유를 돌려준다. **순수 함수** — 네트워크·부작용 없음.

    두 신호를 **OR 로 겹친다**. 한쪽만 보면 각각 사각이 남는다:

    - `tools_profile` — `backend/main.py:111` 이 backend 프로세스의 env 를 **에코**한 값이고,
      같은 파일 105행이 스스로 "참고값"이라고 규정한다. MCP 자식(D15, 별도 프로세스)이 다른
      env 로 떴다면 이 값이 `core` 여도 실제로는 확장 8종이 등록돼 있을 수 있다.
    - `tools` — `list_tools()` **실측** 개수(D69 가 정본으로 규정). 다만 MCP 미기동이면
      `None` 이라 이것만으로도 판정을 세울 수 없다.

    → 둘 중 **하나라도** 걸리면 위반. 빈 dict(= health 조회 실패)는 `tools_profile` 이 없으므로
    자연히 위반으로 떨어진다 — **모르는 상태를 통과로 세지 않는다**(fail-closed).
    """
    reasons: list[str] = []
    profile = health.get("tools_profile")
    if profile != "core":
        reasons.append(f"tools_profile={profile!r} — 기대 'core' (backend env 에코, main.py:111)")
    tools = health.get("tools") or 0
    if tools > CORE_TOOL_COUNT:
        reasons.append(f"tools={tools} — 기대 ≤{CORE_TOOL_COUNT} (list_tools() 실측, main.py:110)")
    return reasons


def enforce_profile_guard(health: dict, *, allow_full_profile: bool) -> None:
    """D88 이중 게이트. 위반이면 **왜 막혔는지·어떻게 푸는지**를 출력하고 `SystemExit(2)`.

    조용히 종료하지 않는다 — 종료코드만 남기면 CI 로그에서 "왜 2인지"를 알 수 없다.
    """
    reasons = profile_violations(health)
    if not reasons:
        return

    if allow_full_profile:
        print("[--allow-full-profile] D88 가드를 명시적으로 우회합니다:")
        for r in reasons:
            print(f"  - {r}")
        print(
            "  ⚠ 이 실행의 지표는 core 프로파일 기준 결과와 **같은 축에 놓을 수 없습니다**"
            " (D69) — 결과 MD 의 meta 로 구분하십시오."
        )
        return

    print("[중단] D88 프로파일 가드 — 평가는 core 프로파일에서만 유효합니다.")
    for r in reasons:
        print(f"  - 위반: {r}")
    print(
        "  왜 막는가: 확장 8종(04 §8~§15)이 등록된 상태의 점수는 core 기준 지표와 분모가 달라"
        " 이전 회차와 비교할 수 없습니다. 사후에는 어느 프로파일로 돌았는지 복원할 수 없어"
        " 결과 전체가 무효가 됩니다."
    )
    print(
        "  어떻게 푸는가: ① MAINTQ_TOOLS_PROFILE 을 unset 하거나 'core' 로 두고 다시 실행"
        " — 이 값은 자식 MCP 서버로 상속되므로 셸 세션 전체에서 지워야 합니다."
        " ② 의도한 full 실행이면 --allow-full-profile 을 명시하십시오."
    )
    raise SystemExit(2)


def build_meta(health: dict) -> dict:
    """결과 JSON·MD 머리말에 실을 실행 환경 기록 (D56 — 제공자는 env 우선, 기본 gemini).

    `llm_model` 은 **기본값을 두지 않는다.** `llm_provider` 가 미설정 시 `gemini` 로
    떨어지는 건 `backend/agent/llm.py:get_client()` 가 실제로 그렇게 동작하기 때문이지만,
    모델명은 그런 폴백이 없다(키가 없으면 그냥 실패한다). 없는데 값을 채우면 회차 비교의
    근거가 통째로 거짓이 된다 — 모르면 `null` 이다.

    D88 이 `tools_profile`·`tools` 를 실은 논리("3차가 full 로 돌았는지 사후에 알 수 없다")가
    모델명에도 그대로 적용되는데 그것만 빠져 있었다: `llm_provider: gemini` 만으로는
    `gemini-2.5-flash` 인지 `flash-lite` 인지 구분되지 않는다.
    """
    return {
        "tools_profile": health.get("tools_profile"),
        "tools": health.get("tools"),
        # `or` — .env 의 빈 키를 미설정과 같게 본다 (backend/agent/llm.py:310 과 같은 근거).
        "llm_provider": os.environ.get("MAINTQ_LLM_PROVIDER") or "gemini",
        "llm_model": (os.environ.get("MAINTQ_LLM_MODEL") or "").strip() or None,
    }


def meta_line(meta: dict) -> str:
    """콘솔 한 줄 요약 — dry-run 과 실행이 **같은 문자열**을 쓴다(한쪽만 갱신되는 걸 막는다)."""
    return (
        f"tools_profile={meta.get('tools_profile')} · tools={meta.get('tools')} · "
        f"llm_provider={meta.get('llm_provider')} · llm_model={meta.get('llm_model')}"
    )


def _free_port() -> int:
    """비어 있는 로컬 포트를 하나 잡아 돌려준다 (dry-run 프로브 · **매 회차 서버**).

    고정 포트를 쓰면 **다른 스위트가 띄워 둔 서버의 `/health` 를 읽어** 가드 판정이
    남의 env 로 오염된다 — 그 순간 이 가드는 "무엇을 측정했는지 모르는 검사"가 된다.
    `--repeat` 에서는 이유가 하나 더 붙는다: 회차 N 의 서버가 회차 N-1 의 소켓에 붙으면
    **두 회차가 같은 DB 사본을 보게 되어 독립성이 조용히 깨진다.**
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def probe_health() -> dict:
    """서버를 임시 포트에 띄워 `/health` 만 읽고 즉시 내린다. **LLM 호출 0회.**

    실패하면 빈 dict — `profile_violations` 가 fail-closed 로 받는다.
    DB 는 `_start_server` 와 같은 방식으로 **사본**을 쓴다(`data/maintq.db` 에 쓰지 않는다).
    """
    if not SOURCE_DB.exists():
        print(f"[경고] {SOURCE_DB} 가 없어 /health 프로브를 건너뜁니다 — 프로파일 확인 불가")
        return {}

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory() as td:
        db_copy = Path(td) / "probe.db"
        shutil.copy2(SOURCE_DB, db_copy)
        proc = _start_server(db_copy, port)
        try:
            if not asyncio.run(_wait_ready(base_url, timeout=60.0)):
                print(f"[경고] /health 프로브 서버가 뜨지 않았습니다 ({base_url})")
                return {}
            return httpx.get(f"{base_url}/health", timeout=10.0).json()
        except Exception as exc:  # noqa: BLE001 — 프로브 실패는 "모르는 상태"로 넘긴다
            print(f"[경고] /health 프로브 실패: {exc}")
            return {}
        finally:
            _shutdown_server(proc)


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


# ────────────────────────────────────────────── traces 덤프 (MQ-713a ①)


def dump_traces(db_path: Path, out_path: Path) -> int:
    """임시 DB 가 폐기되기 **전에** `traces` 전량을 JSONL 로 결과 옆에 덤프한다. 반환은 행 수.

    **왜 필요한가.** `_start_server` 는 실 DB 사본으로 서버를 띄우고 종료 시 사본을 폐기한다.
    실 DB 보호는 옳지만 그 결과 **평가의 판정 근거가 실행과 함께 사라졌다** — 3차 평가에서
    `traces` 는 0행이었고, MQ-703 명세가 요구한 `GET /api/chat/{sid}/trace` 원본 대조를
    할 수 없었다(`data/analysis/eval_gap_3rd.md`).

    `tool_payload`(D76-2)를 반드시 싣는다 — 도구가 **실제로 무엇을 반환했는지**가 거기 있고,
    `payload`(SSE data 사본)에는 요약만 있다. 값이 전부 NULL 이면 계측이 안 된 것이므로
    호출부가 그 사실을 눈에 띄게 보고한다.

    ⛔ 인자로 받은 사본 DB 만 연다. `data/maintq.db` 는 열지 않는다.
    """
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT session_id, seq, event_type, tool, payload, tool_payload, ts"
            " FROM traces ORDER BY session_id, seq"
        ).fetchall()
    finally:
        con.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(
                json.dumps(
                    {
                        "session_id": r["session_id"],
                        "seq": r["seq"],
                        "event": r["event_type"],
                        "tool": r["tool"],
                        "data": _loads_or_raw(r["payload"]),
                        "tool_payload": _loads_or_raw(r["tool_payload"]),
                        "ts": r["ts"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return len(rows)


def _loads_or_raw(text: str | None) -> object:
    """저장된 JSON 을 되돌린다. 깨져 있으면 **버리지 않고** 원문 문자열로 남긴다."""
    if text is None:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


def count_tool_payloads(dump_path: Path) -> tuple[int, int]:
    """덤프에서 `(tool_result 행 수, tool_payload 가 채워진 행 수)`.

    "행 수 > 0" 만으로는 D76-2 가 실제로 값을 쓰는지 알 수 없다 — 컬럼은 Sprint 6 에
    있었지만 **쓰는 쪽이 없어** 3차까지 전부 NULL 이었다.
    """
    total = filled = 0
    if not dump_path.exists():
        return (0, 0)
    for line in dump_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("event") != "tool_result":
            continue
        total += 1
        if row.get("tool_payload") not in (None, "", {}):
            filled += 1
    return (total, filled)


# ────────────────────────────────────────────── LLM 종료 사유 집계 (MQ-713a ③)

#: `backend/agent/loop.py:format_llm_end` 가 만든 줄을 되읽는다. 형식 문자열은 생산자가
#: 정본이라 마커 상수를 import 해 쓴다 — 여기서 따로 적으면 조용히 어긋난다.
_LLM_END_RE = re.compile(
    re.escape(LLM_END_MARKER) + r" session=(?P<session>\S+) call=(?P<call>\d+)"
    r" reason=(?P<reason>\S+) truncated=(?P<truncated>[01])"
)


def parse_llm_end(stderr_text: str) -> list[dict]:
    """서버 stderr 에서 `[LLM_END]` 계측 줄을 뽑는다.

    `truncated` 는 줄에 적힌 값을 그대로 믿지 않고 **`reason` 에서 다시 판정**한다
    (`TRUNCATION_REASONS` 가 단일 소스). 두 값이 어긋나면 그 사실을 `mismatch` 로 남긴다 —
    조용히 한쪽을 고르면 "계측했는데 무엇을 셌는지 모르는" 상태가 된다.
    """
    out: list[dict] = []
    for m in _LLM_END_RE.finditer(stderr_text):
        reason = m.group("reason")
        derived = reason in TRUNCATION_REASONS
        out.append(
            {
                "session_id": m.group("session"),
                "call": int(m.group("call")),
                "reason": reason,
                "truncated": derived,
                "mismatch": derived != (m.group("truncated") == "1"),
            }
        )
    return out


def summarize_llm_end(records: list[dict]) -> dict:
    """잘림 집계. **0건과 '계측 실패'를 구분한다** — 이번 계측의 목적이 그 구분이다.

    `measured=False` 는 "잘림이 없었다"가 아니라 "쟀는지조차 모른다"이므로, 이 값이면
    결과 MD 가 잘림 0건이라고 쓰지 않는다.
    """
    reasons: dict[str, int] = {}
    by_session: dict[str, int] = {}
    for r in records:
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
        if r["truncated"]:
            by_session[r["session_id"]] = by_session.get(r["session_id"], 0) + 1
    return {
        "measured": bool(records),
        "llm_calls": len(records),
        "truncated_calls": sum(by_session.values()),
        "truncated_by_session": dict(sorted(by_session.items())),
        "reasons": dict(sorted(reasons.items())),
        "mismatched": sum(1 for r in records if r["mismatch"]),
    }


# ────────────────────────────────────────────── 회차 간 흔들림(flip) 집계 (MQ-713b, 후보 3)
#
# **왜 필요한가.** `data/analysis/eval_gap_3rd.md §4` 의 실측: 같은 코드·같은 문항인데
# 2차와 3차에서 **판정이 뒤집힌 문항이 7개**였다. 그 상태에서 프롬프트를 고치고 4차를
# 단일 실행으로 돌리면, 나온 증감이 **수정의 효과인지 LLM 응답 요동인지 구분할 수 없다.**
# 그래서 후보 4·5(프롬프트 수정)보다 이 계측이 먼저다.
#
# **무엇을 재는가.** 한 문항 × 한 지표를 N 회차에 걸쳐 보고 판정이 일치하는지만 본다.
#   - 전 회차 통과      → `stable_pass`   (개선 판정의 기준선으로 쓸 수 있다)
#   - 전 회차 실패      → `stable_fail`   (여기가 진짜 고칠 대상이다)
#   - 섞임              → `flipped`       (⛔ 이 문항의 증감으로 수정 효과를 주장하지 말 것)
#
# ⛔ **1회차 실행에서 "흔들림 0건"이라고 쓰지 않는다.** 회차가 1이면 뒤집힘은 정의되지
#    않는다 — `measurable: False` 로 내려보내고 MD 도 "측정 불가"라고 쓴다. 잘림 계측에서
#    `measured` 와 "0건"을 가른 것과 같은 이유다.

#: 흔들림을 세는 지표. `score.py` 4지표 + judge 1종. `aggregate` 의 지표 집합과 같아야
#: 한다 — 여기만 늘리면 "재지 않은 지표를 안정적이라고 읽는" 침묵의 구멍이 생긴다.
FLIP_METRICS: tuple[str, ...] = ("part", "citation", "safety", "sequence", "hallucination")


def item_outcomes(result) -> dict[str, bool | None]:
    """한 문항(한 회차)의 지표별 통과 여부. **`None` 은 "이 회차에서 측정되지 않았다"** 다.

    `None` 을 실패로 접으면 흔들림이 부풀려진다 — 분모에서 빠진 것과 떨어진 것은 다르다.
    분모 규칙을 `aggregate()` 와 **같은 근거**로 맞춘다:
      - 실행 실패 문항(`_EXEC_FAILED_PREFIX`)·재생 오염 세션(D55) → 전 지표 `None`
      - `Verdict.applicable=False` → 그 지표만 `None` (`score.metric_rate` 의 분모 규칙)
      - judge 미실행(S4형이 아닌 문항) → `hallucination` 만 `None`

    `hallucination` 은 **축을 뒤집어 담는다** — `hallucinated=True` 가 나쁨이므로
    `passed = not hallucinated`. 흔들림은 "좋음/나쁨이 회차마다 갈리는가"를 세는 것이라
    지표마다 방향이 다르면 같은 표에 실을 수 없다.
    """
    out: dict[str, bool | None] = dict.fromkeys(FLIP_METRICS)

    if result.response_text.startswith(_EXEC_FAILED_PREFIX) or score.has_replay(result.events):
        return out

    for v in result.verdicts:
        if v.metric in out and v.applicable:
            out[v.metric] = bool(v.passed)
    if result.judge is not None:
        out["hallucination"] = not result.judge.hallucinated
    return out


def flip_analysis(rounds: list[list]) -> dict:
    """회차별 `ItemResult` 목록들을 받아 문항×지표 단위 흔들림을 집계한다.

    `rounds[k]` 는 k 회차의 문항 결과 리스트다. 문항 순서가 회차마다 같다고 가정하지 않고
    **`item_id` 로 맞춘다** — 한 회차에서 문항 하나가 통째로 빠져도 나머지가 어긋나지 않는다.
    """
    n_rounds = len(rounds)
    per_item: dict[str, dict[str, list[bool]]] = {}
    order: list[str] = []

    for results in rounds:
        for r in results:
            if r.item_id not in per_item:
                per_item[r.item_id] = {m: [] for m in FLIP_METRICS}
                order.append(r.item_id)
            for metric, passed in item_outcomes(r).items():
                if passed is not None:
                    per_item[r.item_id][metric].append(passed)

    items: dict[str, dict] = {}
    by_metric = {
        m: {"stable_pass": 0, "stable_fail": 0, "flipped": 0, "undetermined": 0}
        for m in FLIP_METRICS
    }
    flipped_cells: list[dict] = []

    for item_id in order:
        cell_out: dict[str, dict] = {}
        for metric in FLIP_METRICS:
            seen = per_item[item_id][metric]
            measured, passed = len(seen), sum(seen)
            # 측정 회차가 2 미만이면 "안정"도 "흔들림"도 주장할 수 없다.
            if measured < 2:
                state = "undetermined"
            elif passed == measured:
                state = "stable_pass"
            elif passed == 0:
                state = "stable_fail"
            else:
                state = "flipped"
            by_metric[metric][state] += 1
            cell_out[metric] = {"passed": passed, "measured": measured, "state": state}
            if state == "flipped":
                flipped_cells.append(
                    {"item_id": item_id, "metric": metric, "passed": passed, "measured": measured}
                )
        items[item_id] = cell_out

    return {
        # 회차가 1이면 뒤집힘은 **정의되지 않는다.** 소비자가 "0건"으로 읽지 못하게 막는 플래그.
        "measurable": n_rounds >= 2,
        "rounds": n_rounds,
        "items": items,
        "by_metric": by_metric,
        "flipped_cells": flipped_cells,
        "n_flipped_cells": len(flipped_cells),
        "flipped_items": sorted({c["item_id"] for c in flipped_cells}),
    }


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
    session_id = session_id_for(item_id)

    payload = {
        "session_id": session_id,
        "message": item["input"],
        "equipment_id": item.get("equipment_id"),
    }

    t0 = time.monotonic()
    token_chunks: list[str] = []
    buf = ""

    async with httpx.AsyncClient(timeout=ITEM_TIMEOUT_S) as c:
        async with c.stream("POST", f"{base_url}/api/chat", json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise RuntimeError(f"POST /api/chat 실패: {resp.status_code} {body[:200]!r}")

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
        try:
            judge = await asyncio.wait_for(
                judge_hallucination(item["input"], response_text), timeout=ITEM_TIMEOUT_S
            )
        except TimeoutError:
            judge = JudgeVerdict(
                hallucinated=True,
                rationale=f"judge 호출이 {ITEM_TIMEOUT_S:.0f}초 내 응답하지 않음 — 보수적으로 fail 처리",
                raw="",
            )

    return ItemResult(
        item_id=item_id,
        branch=branch,
        expected=expected,
        events=events,
        response_text=response_text,
        verdicts=verdicts,
        judge=judge,
        elapsed_s=elapsed_s,
        session_id=session_id,
    )


async def _run_all(base_url: str, items: list[dict], round_idx: int = 1) -> list[ItemResult]:
    """문항 루프. 한 문항이 예외를 내도 나머지는 계속 실행한다(엣지 케이스 명세)."""
    results: list[ItemResult] = []
    total = len(items)
    for i, item in enumerate(items, start=1):
        item_id = item.get("id", f"#{i}")
        print(f"[r{round_idx}][{i}/{total}] {item_id} 실행 중...", flush=True)
        t0 = time.monotonic()
        try:
            result = await run_item(base_url, item)
        except Exception as exc:  # noqa: BLE001 — 이 문항만 "실행 실패", 나머지는 계속
            elapsed = time.monotonic() - t0
            expected = item.get("expected") or {}
            print(f"  [실행 실패] {item_id}: {exc}", flush=True)
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
                # 실행이 실패해도 세션 id 는 남긴다 — 부분적으로 남은 trace 를 덤프에서
                # 찾아야 "어디까지 갔다가 죽었는지"를 볼 수 있다.
                session_id=session_id_for(item_id),
            )
        else:
            print(f"  완료 ({result.elapsed_s:.1f}초)", flush=True)
        # 회차 표기는 실행 경로·실패 경로 **양쪽에** 붙어야 한다 — 실패 문항이 어느 회차
        # 것인지 모르면 흔들림 표에서 그 칸만 회차가 어긋난다.
        result.round = round_idx
        results.append(result)
    return results


async def check_permission_403(base_url: str) -> tuple[bool, str]:
    """문항 루프와 별개 1회 — 승인 큐 첫 pending 건에 technician 으로 approve 시도 (403 기대).

    pending 건이 없으면 임의로 pass 처리하지 않고 `(False, "N/A")` 를 즉시 돌려준다.

    **`_run_all` 과 같은 `asyncio.run()` 호출 안에서 실행한다(async).** 별도의 동기
    `httpx.Client` 로 짜여 있던 구버전은 Windows 에서 방금 닫힌 ProactorEventLoop 직후
    새 동기 소켓 호출이 타임아웃도 없이 멈추는 사례가 실측(2026-07-29~30, 20문항 실행
    2회 연속 재현)됐다 — 이벤트 루프를 닫지 않고 이어서 쓰면 이 경로를 피한다.
    """
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(f"{base_url}/api/po", params={"state": "pending"}, headers=MGR)
        items = (r.json() or {}).get("items", [])
        if not items:
            return False, "N/A"
        po_id = items[0]["po_id"]
        r2 = await c.post(f"{base_url}/api/po/{po_id}/approve", headers=TECH)
        detail = ""
        try:
            detail = str(r2.json().get("detail", ""))[:120]
        except Exception:  # noqa: BLE001 — 상태 코드만 있어도 판정엔 충분
            pass
        return r2.status_code == 403, f"{r2.status_code} {detail}"


async def _run_stage(
    base_url: str, items: list[dict], round_idx: int = 1
) -> tuple[list, tuple[bool, str]]:
    """`_run_all` 과 `check_permission_403` 을 같은 이벤트 루프 안에서 순서대로 실행한다.

    **403 점검의 예외를 여기서 삼킨다.** 이 점검은 문항 루프가 **전부 끝난 뒤**의 부가
    점검인데, 예외가 그대로 올라가면 `main` 이 리포트를 쓰기 전에 죽어 **이미 다 돈 N문항이
    통째로 버려진다.** 2026-08-11 실측: 20문항을 다 돌린 뒤 서버가 응답을 멈춰
    `GET /api/po` 가 `httpx.ReadTimeout` 을 냈고, 그 한 줄 때문에 `.json`·`.md` 가 하나도
    생성되지 않았다(traces 덤프만 `finally` 로 살아남았다). `_run_all` 이 문항별 예외를
    잡는 것과 같은 이유이며, 같은 보호가 여기에만 없었다.

    ⛔ 실패를 `"N/A"`(pending 건 없음)로 접지 않는다 — **점검을 못 한 것과 점검할 게 없는
    것은 다르다.** 사유를 그대로 실어 리포트에 `FAIL (점검 실패 — ReadTimeout)` 로 보인다.
    """
    results = await _run_all(base_url, items, round_idx)
    try:
        perm_result = await check_permission_403(base_url)
    except Exception as exc:  # noqa: BLE001 — 부가 점검 하나로 N문항을 버리지 않는다
        print(f"  [경고] 권한 403 점검 실패: {type(exc).__name__}: {exc}", flush=True)
        perm_result = (False, f"점검 실패 — {type(exc).__name__}")
    return results, perm_result


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


def _llm_end_lines(llm_end: dict) -> list[str]:
    """결과 MD 의 "잘린 턴 N건" 줄.

    **0건과 미계측을 다른 문장으로 쓴다.** 계측이 안 됐는데 "0건"이라고 적으면
    "잘림은 원인이 아니다"라는 결론이 근거 없이 서게 된다 — 3차 분석이 개선과 요동을
    구분하지 못한 것과 같은 종류의 실패다.
    """
    if not llm_end.get("measured"):
        return [
            f"- 잘린 턴: **계측 실패** — `{LLM_END_MARKER}` 마커 0건 "
            "(서버 stderr 미회수이거나 LLM 이 `end` 델타를 흘리지 않음). "
            "**0건이라는 뜻이 아니다.**"
        ]
    reasons = ", ".join(f"{k}×{v}" for k, v in llm_end.get("reasons", {}).items()) or "-"
    line = (
        f"- 잘린 턴: **{llm_end['truncated_calls']}건** / LLM 호출 {llm_end['llm_calls']}회 "
        f"(종료 사유: {reasons})"
    )
    out = [line]
    if llm_end.get("truncated_by_session"):
        out.append(
            "  - 잘린 세션: "
            + ", ".join(f"{k}({v}회)" for k, v in llm_end["truncated_by_session"].items())
        )
    if llm_end.get("mismatched"):
        out.append(
            f"  - ⚠ 마커의 truncated 표기와 reason 판정이 어긋난 줄 {llm_end['mismatched']}건 "
            "— 형식이 갈렸는지 확인하십시오"
        )
    return out


def _traces_dump_lines(dump: dict) -> list[str]:
    if not dump:
        return ["- traces 덤프: 없음"]
    line = f"- traces 덤프: `{dump.get('path')}` — {dump.get('rows')}행"
    tp_total, tp_filled = dump.get("tool_result_rows", 0), dump.get("tool_payload_rows", 0)
    line += f" (tool_result {tp_total}행 중 tool_payload 채워짐 {tp_filled}행, D76-2)"
    out = [line]
    if tp_total and not tp_filled:
        out.append("  - ⚠ tool_payload 가 전부 비었다 — 도구 원본 대조가 불가능하다")
    return out


_FLIP_STATE_LABEL = {
    "stable_pass": "안정 통과",
    "stable_fail": "안정 실패",
    "flipped": "흔들림",
    "undetermined": "판정 불가",
}


def _flip_lines(flip: dict) -> list[str]:
    """결과 MD 의 흔들림 절.

    **1회차 실행에서 "흔들림 없음"이라고 쓰지 않는다.** 회차가 1이면 뒤집힘은 정의되지
    않으므로 "측정 불가"라고 적는다 — `data/analysis/eval_gap_3rd.md §4` 가 지적한
    "개선과 요동을 구분할 수 없다"를 리포트가 스스로 되풀이하지 않게 한다.
    """
    if not flip or not flip.get("measurable"):
        return [
            "## 회차 간 흔들림",
            "",
            f"- **측정 불가** — 실행 회차 {flip.get('rounds', 1) if flip else 1}회. "
            "뒤집힘은 2회차 이상에서만 정의된다(`--repeat 3` 권장). "
            "**흔들림이 없다는 뜻이 아니다.**",
            "- ⛔ 이 상태에서 이전 회차 대비 증감을 **수정의 효과로 주장하지 말 것** "
            "(`data/analysis/eval_gap_3rd.md §4` — 2·3차에서 판정이 뒤집힌 문항이 7개였다).",
            "",
        ]

    bm = flip["by_metric"]
    lines = [
        "## 회차 간 흔들림",
        "",
        f"실행 회차 **{flip['rounds']}회**. 같은 문항·같은 지표의 판정이 회차마다 갈리는지만 본다.",
        "",
        "| 지표 | 안정 통과 | 안정 실패 | **흔들림** | 판정 불가(측정 <2회) |",
        "|---|---|---|---|---|",
    ]
    for metric in FLIP_METRICS:
        d = bm[metric]
        lines.append(
            f"| {metric} | {d['stable_pass']} | {d['stable_fail']} | "
            f"**{d['flipped']}** | {d['undetermined']} |"
        )
    lines += [
        "",
        f"- 흔들린 칸(문항×지표): **{flip['n_flipped_cells']}개** · "
        f"흔들린 문항: {', '.join(flip['flipped_items']) or '없음'}",
    ]
    if flip["flipped_cells"]:
        lines += [
            "",
            "| 문항 | 지표 | 통과/측정 |",
            "|---|---|---|",
        ]
        lines += [
            f"| {c['item_id']} | {c['metric']} | {c['passed']}/{c['measured']} |"
            for c in flip["flipped_cells"]
        ]
        lines += [
            "",
            "> ⛔ **위 문항의 증감으로 수정 효과를 주장하지 말 것.** 회차만 바꿔도 판정이 갈린다.",
            "> 튜닝의 판정은 `안정 실패` → `안정 통과` 로 넘어간 칸으로만 한다.",
        ]
    else:
        lines.append("- 흔들린 칸 0개 — 이 회차 수에서는 판정이 재현됐다.")
    lines.append("")
    return lines


def write_report(
    results,
    agg,
    perm_result,
    out_dir: Path,
    meta: dict,
    *,
    stamp: str | None = None,
    llm_end: dict | None = None,
    traces_dump: dict | None = None,
    rounds: list[dict] | None = None,
    flip: dict | None = None,
    repeat: int = 1,
) -> Path:
    """`eval/results/{날짜}.md`+`.json` 생성. 5지표 전부(좋은 것만 골라내지 않는다).

    `meta`(D88·D56)는 **JSON 최상위 `meta` 키**와 **MD 머리말** 양쪽에 싣는다 — 어느 프로파일·
    어느 제공자·**어느 모델**로 낸 수치인지 결과물만 보고 알 수 있어야 회차 간 비교가 성립한다.

    `stamp` 를 인자로 받는 이유: `traces` 덤프는 임시 DB 가 폐기되기 전(=리포트 작성 전)에
    써야 하는데, 파일명이 같은 타임스탬프여야 짝을 이룬다. 여기서 새로 만들면 두 파일이
    다른 이름으로 갈라져 대조가 수작업이 된다.

    `repeat > 1` 이면 `results` 는 **전 회차를 합친** 목록이고 `agg` 도 그 합산이다
    (분모가 문항수 × 회차). 회차별 수치는 `rounds[]` 에, 회차 간 뒤집힘은 `flip` 에 실린다 —
    합산 하나만 보면 "평균은 올랐는데 매 회차 다른 문항이 통과한" 경우를 놓친다.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = out_dir / f"{stamp}.json"
    md_path = out_dir / f"{stamp}.md"
    llm_end = llm_end or summarize_llm_end([])

    # 회차마다 DB 사본·서버가 따로라 `session_id`(=`EVAL-T01`)는 **회차 안에서만** 고유하다.
    # 합산 `llm_end` 로 문항별 잘림을 세면 3회차 실행에서 같은 수치가 세 번 겹쳐 보인다 —
    # `(회차, 세션)` 키로 본다. 회차 정보가 없으면(단일 실행) 전부 1회차로 읽는다.
    trunc_by_round: dict[tuple[int, str], int] = {}
    if rounds:
        for rd in rounds:
            by_sess = (rd.get("llm_end") or {}).get("truncated_by_session") or {}
            for sid, n in by_sess.items():
                trunc_by_round[(int(rd.get("round", 1)), sid)] = n
    else:
        for sid, n in (llm_end.get("truncated_by_session") or {}).items():
            trunc_by_round[(1, sid)] = n

    perm_ok, perm_detail = perm_result
    perm_verdict = "N/A" if perm_detail == "N/A" else ("PASS" if perm_ok else "FAIL")

    json_payload = {
        "generated_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "meta": meta,
        "repeat": repeat,
        "aggregate": agg,
        # 계측 3종은 지표가 아니므로 `aggregate` 에 섞지 않는다 — 5지표 분모를 흐리지 않게
        # 최상위 별도 키로 둔다.
        "llm_end": llm_end,
        "traces_dump": traces_dump or {},
        "flip": flip or {"measurable": False, "rounds": repeat},
        "rounds": rounds or [],
        "permission_403": {"passed": perm_ok, "detail": perm_detail, "verdict": perm_verdict},
        "items": [
            {
                "item_id": r.item_id,
                "round": r.round,
                # traces 덤프(`{stamp}[.r{회차}].traces.jsonl`)와 문항을 잇는 키
                "session_id": r.session_id,
                "truncated_calls": trunc_by_round.get((r.round, r.session_id), 0),
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
        f"- tools_profile: {meta.get('tools_profile')}",
        f"- tools: {meta.get('tools')}",
        f"- llm_provider: {meta.get('llm_provider')}",
        # 값이 없으면 `null` 그대로 — 지어내지 않는다 (build_meta docstring 참조)
        f"- llm_model: {meta.get('llm_model')}",
        f"- 실행 회차: {repeat}회" + (" (`--repeat`)" if repeat > 1 else " (단일 실행)"),
        "",
        *_llm_end_lines(llm_end),
        *_traces_dump_lines(traces_dump or {}),
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
    ]
    if repeat > 1:
        lines += [
            f"> 위 분모는 **{repeat}회차 합산**이다(문항 {len(results) // repeat}개 × {repeat}회). "
            "회차별 수치는 아래 §회차별 요약, 뒤집힘은 §회차 간 흔들림.",
            "",
        ]
    lines += _flip_lines(flip or {})
    if repeat > 1 and rounds:
        lines += [
            "## 회차별 요약",
            "",
            "| 회차 | part | citation | safety | hallucination | sequence | 실행 실패 |",
            "|---|---|---|---|---|---|---|",
        ]
        for rd in rounds:
            rm = (rd.get("aggregate") or {}).get("metrics", {})

            def _cell(key: str, _rm: dict = rm) -> str:
                d = _rm.get(key) or {}
                return "N/A" if not d.get("total") else f"{d['rate']:.1%}"

            failed = (rd.get("aggregate") or {}).get("failed_items") or []
            lines.append(
                f"| {rd.get('round')} | {_cell('part')} | {_cell('citation')} | "
                f"{_cell('safety')} | {_cell('hallucination')} | {_cell('sequence')} | "
                f"{len(failed)}건 |"
            )
        lines.append("")
    lines += [
        "## 문항별 상세",
        "",
    ]
    for r in results:
        prefix = f"[r{r.round}] " if repeat > 1 else ""
        lines.append(f"### {prefix}{r.item_id} ({r.branch})")
        lines.append(f"- session: `{r.session_id}` (traces 덤프에서 이 키로 찾는다)")
        n_trunc = trunc_by_round.get((r.round, r.session_id), 0)
        if n_trunc:
            lines.append(f"- **잘린 LLM 호출 {n_trunc}건** (MAX_TOKENS/length)")
        if r.response_text.startswith(_EXEC_FAILED_PREFIX):
            lines.append(f"- **실행 실패**: {r.response_text[len(_EXEC_FAILED_PREFIX) :]}")
        else:
            for v in r.verdicts:
                mark = "PASS" if v.passed else "FAIL"
                applicable = "" if v.applicable else " (분모 제외)"
                lines.append(f"- [{mark}] {v.metric}{applicable}: {v.detail}")
            if r.judge is not None:
                lines.append(f"- [judge] hallucinated={r.judge.hallucinated} — {r.judge.rationale}")
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


def _print_flip(flip: dict) -> None:
    """콘솔 요약. `_flip_lines` 와 **같은 규칙** — 1회차면 "0건"이 아니라 "측정 불가"."""
    if not flip.get("measurable"):
        print(
            f"  [주의] 회차 간 흔들림 측정 불가 — 실행 회차 {flip.get('rounds', 1)}회. "
            "'흔들림 0건'이 아닙니다(`--repeat 3` 로 잽니다)."
        )
        return
    print(
        f"  회차 간 흔들림: 문항×지표 {flip['n_flipped_cells']}칸 "
        f"(문항 {len(flip['flipped_items'])}개: {', '.join(flip['flipped_items']) or '없음'})"
    )
    for metric in FLIP_METRICS:
        d = flip["by_metric"][metric]
        print(
            f"    {metric}: 안정통과 {d['stable_pass']} · 안정실패 {d['stable_fail']} · "
            f"흔들림 {d['flipped']} · 판정불가 {d['undetermined']}"
        )


def _print_llm_end(llm_end: dict) -> None:
    """콘솔에도 같은 사실을 싣는다 — MD 를 안 열어도 계측 성패가 보여야 한다."""
    if not llm_end.get("measured"):
        print(
            f"  [주의] 잘림 계측 실패 — {LLM_END_MARKER} 마커 0건. "
            "'잘림 0건'이 아니라 '쟀는지 모른다'입니다."
        )
        return
    print(
        f"  잘린 턴: {llm_end['truncated_calls']}건 / LLM 호출 {llm_end['llm_calls']}회 "
        f"· 종료 사유 {llm_end.get('reasons')}"
    )


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


# ────────────────────────────────────────────── 회차 실행


def _artifact_suffix(round_idx: int, n_rounds: int) -> str:
    """회차 산출물 접미사. **단일 실행이면 접미사가 없다** — 3차까지의 파일 이름
    규약(`{stamp}.traces.jsonl`·`{stamp}.server.log`)을 그대로 둔다."""
    return "" if n_rounds == 1 else f".r{round_idx}"


def _run_round(
    items: list[dict],
    *,
    out_dir: Path,
    stamp: str,
    round_idx: int,
    n_rounds: int,
    allow_full_profile: bool,
) -> dict:
    """한 회차를 통째로 실행한다 — **DB 사본·서버·포트를 회차마다 새로 만든다.**

    ⛔ 회차끼리 DB 를 공유하지 않는다. 공유하면 1회차가 넣은 `po_drafts`·`traces` 를
    2회차가 보게 되어 **회차가 독립 표본이 아니게 된다** — 그 순간 흔들림 수치는
    "요동"이 아니라 "누적 상태의 효과"를 재게 되고, 후보 3 의 목적이 사라진다.

    반환: `{"round", "results", "perm_result", "meta", "llm_end", "llm_records",
            "traces_dump", "aggregate"}`
    """
    suffix = _artifact_suffix(round_idx, n_rounds)
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    traces_dump: dict = {}
    err_bytes = b""

    with tempfile.TemporaryDirectory() as td:
        db_copy = Path(td) / "eval.db"
        shutil.copy2(SOURCE_DB, db_copy)

        proc = _start_server(db_copy, port)
        try:
            if not asyncio.run(_wait_ready(base_url)):
                err = proc.stderr.read().decode("utf-8", "replace")[-800:] if proc.stderr else ""
                raise SystemExit(f"[중단] 서버가 뜨지 않았습니다(회차 {round_idx})\n{err}")

            health = httpx.get(f"{base_url}/health", timeout=10.0).json()
            if not health.get("mcp"):
                raise SystemExit(
                    f"[중단] MCP 가 기동하지 않았습니다({health}) — 이대로 진행하면 전체 문항이 "
                    "'도구 서버 연결 불가'로 조용히 fail 처리됩니다. MAINTQ_MCP_AUTOSTART·"
                    "GEMINI_API_KEY 등 환경을 확인하세요."
                )

            # ★ D88 — **문항 루프(=LLM 호출) 이전**에 막는다. 순서가 반대면 full 로 돌았는지
            #   사후에 알 수 없고, 이미 비용을 쓴 뒤라 되돌릴 수도 없다.
            #   회차마다 서버가 새로 뜨므로 **회차마다 다시 검사한다** — 1회차만 보고 넘어가면
            #   2회차가 다른 env 로 떠도 통과한다.
            enforce_profile_guard(health, allow_full_profile=allow_full_profile)
            meta = build_meta(health)
            print(f"[r{round_idx}/{n_rounds}] 실행 환경 meta: {meta_line(meta)} · port={port}")

            results, perm_result = asyncio.run(_run_stage(base_url, items, round_idx))
        finally:
            err_bytes = _shutdown_server(proc)
            # ★ 임시 디렉터리가 사라지기 **전에** traces 를 결과 옆으로 옮긴다.
            #   덤프 실패로 이미 끝난 문항 결과를 날리지 않는다(집계는 계속한다).
            try:
                dump_path = out_dir / f"{stamp}{suffix}.traces.jsonl"
                rows = dump_traces(db_copy, dump_path)
                tr_rows, tp_rows = count_tool_payloads(dump_path)
                traces_dump = {
                    "path": str(dump_path),
                    "rows": rows,
                    "tool_result_rows": tr_rows,
                    "tool_payload_rows": tp_rows,
                }
                print(
                    f"traces 덤프: {dump_path} — {rows}행 "
                    f"(tool_result {tr_rows}행 중 tool_payload {tp_rows}행)"
                )
                if rows == 0:
                    print("  [주의] traces 가 0행입니다 — 판정 근거를 사후 대조할 수 없습니다.")
            except Exception as exc:  # noqa: BLE001 — 덤프 실패는 평가 실패가 아니다
                print(f"[경고] traces 덤프 실패: {exc}")

    stderr_text = err_bytes.decode("utf-8", "replace") if err_bytes else ""
    if stderr_text.strip():
        print(f"\n[r{round_idx} 서버 stderr 끝부분]\n{stderr_text[-1200:]}")

    log_path = out_dir / f"{stamp}{suffix}.server.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(stderr_text, encoding="utf-8")
    except OSError as exc:
        print(f"[경고] 서버 로그 저장 실패: {exc}")

    # 잘림 계측 — 서버 stderr 의 [LLM_END] 마커를 집계한다 (loop.py 가 생산자).
    # stderr 회수 자체가 실패하면 `measured: False` 로 떨어져 "0건"과 구분된다.
    records = parse_llm_end(stderr_text)
    return {
        "round": round_idx,
        "results": results,
        "perm_result": perm_result,
        "meta": meta,
        "llm_records": records,
        "llm_end": summarize_llm_end(records),
        "traces_dump": traces_dump,
        "aggregate": aggregate(results),
    }


def _merge_perm_results(rounds: list[dict]) -> tuple[bool, str]:
    """회차별 403 결과 합산 — **전 회차 통과일 때만 통과.** 한 회차라도 갈리면 그 사실을 싣는다.

    다수결로 접으면 "3회 중 1회 뚫렸다"가 PASS 로 보고된다 — 권한 게이트에서 그건 실패다.
    """
    if not rounds:
        return False, "N/A"
    pairs = [rd["perm_result"] for rd in rounds]
    details = [d for _, d in pairs]
    if all(d == "N/A" for d in details):
        return False, "N/A"
    all_ok = all(ok for ok, _ in pairs)
    if len({d for d in details}) == 1:
        return all_ok, details[0]
    return all_ok, "회차별 불일치: " + " | ".join(
        f"r{rd['round']}={d}" for rd, d in zip(rounds, details)
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
    parser.add_argument(
        "--allow-full-profile",
        action="store_true",
        help="D88 프로파일 가드 우회 — core 가 아닌 프로파일에서 의도적으로 실행할 때만",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("eval/results"))
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        metavar="N",
        help=(
            "같은 testset 을 N 회차 반복 실행해 **회차 간 흔들림(flip)** 을 잰다 (기본 1). "
            "회차마다 DB 사본·서버를 새로 띄운다. 비용은 정확히 N 배. "
            "eval_gap_3rd.md §4 — 단일 실행으로는 수정 효과와 응답 요동을 구분할 수 없다"
        ),
    )
    args = parser.parse_args()

    if args.repeat < 1:
        raise SystemExit(f"[중단] --repeat 는 1 이상이어야 합니다 (받은 값: {args.repeat})")

    all_items = load_testset(args.testset)
    validate_testset(all_items)
    print(f"testset 검증 통과: {len(all_items)}문항 ({args.testset})")

    items = all_items if args.limit is None else all_items[: args.limit]
    if args.limit is not None:
        print(f"[부분 실행] ({len(items)}/{len(all_items)})")

    if args.repeat > 1:
        print(f"[반복 실행] {args.repeat}회차 — 회차마다 DB 사본·서버를 새로 띄웁니다(독립 표본)")
    print(estimate_cost(items, args.repeat))

    if args.dry_run:
        print("[--dry-run] 스키마 검증 + 비용 추정 + D88 프로파일 가드 — LLM 호출 0회.")
        # 가드는 실측 `/health` 로만 의미가 있다(D69: `tools` 가 정본). 문항 루프에 들어가지
        # 않으므로 서버를 띄워도 모델은 한 번도 불리지 않는다.
        health = probe_health()
        meta = build_meta(health)
        print(f"  meta: {meta_line(meta)}")
        enforce_profile_guard(health, allow_full_profile=args.allow_full_profile)
        print("  D88 프로파일 가드 통과 — 실행하려면 --yes 를 붙이십시오.")
        return

    if not args.yes:
        if not sys.stdin.isatty():
            raise SystemExit("[중단] 비대화형 환경에서는 --yes 없이 진행할 수 없습니다.")
        answer = input("계속 진행합니까? [y/N] ").strip().lower()
        if answer != "y":
            raise SystemExit("[중단] 사용자가 취소했습니다.")

    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    # 리포트·traces 덤프·서버 로그가 **같은 타임스탬프**를 공유해야 짝이 성립한다.
    # 회차별 산출물은 `{stamp}.r{k}.*` 로 갈라지되 stamp 는 공유한다.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    rounds: list[dict] = []
    for k in range(1, args.repeat + 1):
        if args.repeat > 1:
            print(f"\n{'=' * 20} 회차 {k}/{args.repeat} {'=' * 20}")
        rounds.append(
            _run_round(
                items,
                out_dir=args.out_dir,
                stamp=stamp,
                round_idx=k,
                n_rounds=args.repeat,
                allow_full_profile=args.allow_full_profile,
            )
        )

    # 회차별 결과를 합쳐 하나의 리포트로 낸다. 합산 분모는 문항수 × 회차다 —
    # 회차별 수치와 뒤집힘은 `rounds`·`flip` 이 따로 싣는다(합산만 보면 요동이 안 보인다).
    results = [r for rd in rounds for r in rd["results"]]
    meta = rounds[0]["meta"]
    llm_end = summarize_llm_end([rec for rd in rounds for rec in rd["llm_records"]])
    flip = flip_analysis([rd["results"] for rd in rounds])
    perm_result = _merge_perm_results(rounds)

    # 회차마다 meta 가 갈리면 회차 간 비교가 성립하지 않는다 — 감추지 않고 알린다.
    distinct_meta = {json.dumps(rd["meta"], sort_keys=True, ensure_ascii=False) for rd in rounds}
    if len(distinct_meta) > 1:
        print("[경고] 회차별 실행 환경(meta)이 다릅니다 — 회차 간 비교가 성립하지 않습니다:")
        for rd in rounds:
            print(f"  r{rd['round']}: {meta_line(rd['meta'])}")

    traces_dump = rounds[0]["traces_dump"]
    if args.repeat > 1:
        traces_dump = {
            "path": f"{stamp}.r1~r{args.repeat}.traces.jsonl",
            "paths": [rd["traces_dump"].get("path") for rd in rounds],
            "rows": sum(rd["traces_dump"].get("rows", 0) for rd in rounds),
            "tool_result_rows": sum(rd["traces_dump"].get("tool_result_rows", 0) for rd in rounds),
            "tool_payload_rows": sum(
                rd["traces_dump"].get("tool_payload_rows", 0) for rd in rounds
            ),
        }

    agg = aggregate(results)
    diff_text = diff_against_previous(agg, args.out_dir)
    report_path = write_report(
        results,
        agg,
        perm_result,
        args.out_dir,
        meta,
        stamp=stamp,
        llm_end=llm_end,
        traces_dump=traces_dump,
        # `results` 를 그대로 실으면 JSON 이 회차 배만큼 커진다 — 회차 요약만 남긴다.
        rounds=[
            {
                "round": rd["round"],
                "aggregate": rd["aggregate"],
                "llm_end": rd["llm_end"],
                "traces_dump": rd["traces_dump"],
                "permission_403": {"passed": rd["perm_result"][0], "detail": rd["perm_result"][1]},
                "meta": rd["meta"],
            }
            for rd in rounds
        ],
        flip=flip,
        repeat=args.repeat,
    )

    print()
    print(diff_text)
    print()
    _print_summary(agg, perm_result)
    _print_llm_end(llm_end)
    _print_flip(flip)
    print(f"\n리포트: {report_path}")


if __name__ == "__main__":
    main()
