# -*- coding: utf-8 -*-
"""LLM 제공자 계약 검증 (D40 · D56) — **SDK 호출 없음, 네트워크 불필요**.

D56 이 정한 것:
  - `MAINTQ_LLM_PROVIDER` 분기 (gemini 기본 | anthropic), 키는 제공자별
  - env 는 OS 환경변수 우선, `.env` 는 빈 곳만 채움 (`load_dotenv(override=False)`)
  - 도구 스키마·메시지 역할·스트림 델타 변환은 클라이언트 클래스 안 — 루프는 제공자를 모른다

여기서 검증하는 건 **변환 순수 함수**(gemini_schema/declarations/contents/chunk_deltas)와
`get_client()` 분기·실패 경로다. 실 Gemini 스트림 관통(C-5)은 키가 있어야 하므로
수동 스모크 대상이고, 이 스파이크의 범위가 아니다.

실행:  uv run python spikes/llm_provider_contract.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.agent.llm import (  # noqa: E402
    EliceClient,
    GeminiClient,
    ToolUse,
    elice_chunk_delta,
    elice_finalize_tool_calls,
    elice_messages,
    elice_tools,
    gemini_chunk_deltas,
    gemini_contents,
    gemini_declarations,
    gemini_schema,
    get_client,
)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


#: get_client 가 보는 env 전부 — 컨텍스트 안에서 이것만 통제하고 나머지는 건드리지 않는다.
#: `MAINTQ_LLM_CACHE` 도 포함한다 — Task 4 가 `get_client()` 에 이 여섯 번째 env 키를
#: 추가해 켜져 있으면 `CachingClient` 로 감싸므로(D104), 안 비우면 ⑩·⑬ 의
#: `isinstance(c, GeminiClient)` 판정이 환경에 따라 흔들린다.
_ENV_KEYS = (
    "MAINTQ_LLM_PROVIDER",
    "MAINTQ_LLM_MODEL",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "ELICE_API_KEY",
    "ELICE_LLM_URL",
    "MAINTQ_LLM_CACHE",
)


@contextmanager
def env(**vals: str):
    """지정한 키만 설정하고 나머지 LLM env 는 비운 뒤, 끝나면 원상 복구한다."""
    saved = {k: os.environ.get(k) for k in _ENV_KEYS}
    try:
        for k in _ENV_KEYS:
            os.environ.pop(k, None)
        for k, v in vals.items():
            os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def run() -> None:
    # ── ① 스키마 정리 — 표시용 키 제거, 계약 키 보존 (★ 음성: title 이 사라짐)
    raw = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "lookup_error_code_input",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "model": {"type": "string", "enum": ["iG5A", "S100"], "title": "Model"},
            "code": {"type": "string", "description": "에러코드"},
        },
        "required": ["model", "code"],
    }
    s = gemini_schema(raw)
    check(
        "① gemini_schema — title/additionalProperties/$schema 제거, 계약 키 보존",
        s
        == {
            "type": "object",
            "properties": {
                "model": {"type": "string", "enum": ["iG5A", "S100"]},
                "code": {"type": "string", "description": "에러코드"},
            },
            "required": ["model", "code"],
        },
        f"keys={sorted(s)}",
    )

    # ── ② 중첩 재귀 — items 안 properties 까지 정리된다
    nested = gemini_schema(
        {
            "type": "array",
            "items": {
                "type": "object",
                "title": "Item",
                "properties": {"qty": {"type": "integer", "default": 1}},
            },
        }
    )
    check(
        "② gemini_schema — items/properties 재귀 (중첩 title·default 제거)",
        nested == {"type": "array", "items": {"type": "object", "properties": {"qty": {"type": "integer"}}}},
        str(nested),
    )

    # ── ③ 선언 변환 — 파라미터 없는 도구는 parameters 생략
    decls = gemini_declarations(
        [
            {"name": "lookup_error_code", "description": "코드 조회", "input_schema": raw},
            {"name": "ping", "description": "무인자", "input_schema": {"type": "object"}},
        ]
    )
    check(
        "③ gemini_declarations — 이름·설명 보존, 무인자 도구는 parameters 없음",
        decls[0]["name"] == "lookup_error_code"
        and "parameters" in decls[0]
        and decls[1] == {"name": "ping", "description": "무인자"},
        f"{[sorted(d) for d in decls]}",
    )

    # ── ④ 이력 변환 — assistant→model, user 유지 (루프 이력은 이 두 역할뿐)
    contents = gemini_contents(
        [
            {"role": "user", "content": "OHt 에러"},
            {"role": "assistant", "content": "과열입니다."},
            {"role": "user", "content": "[도구 결과 lookup_error_code] 과열"},
        ]
    )
    check(
        "④ gemini_contents — assistant→model, 평문 user 유지",
        [c["role"] for c in contents] == ["user", "model", "user"]
        and contents[1]["parts"] == [{"text": "과열입니다."}],
        f"roles={[c['role'] for c in contents]}",
    )

    # ── ⑤ chunk 정규화 — text part → ("text", …)
    ids = iter(range(1, 100))

    def next_id() -> str:
        return f"fc-{next(ids)}"

    chunk_text = NS(candidates=[NS(content=NS(parts=[NS(text="안녕", function_call=None)]))])
    check(
        "⑤ gemini_chunk_deltas — text part 정규화",
        gemini_chunk_deltas(chunk_text, next_id) == [("text", "안녕")],
        "",
    )

    # ── ⑥ function_call → ToolUse (id 없으면 합성)
    fc = NS(id=None, name="lookup_error_code", args={"model": "iG5A", "code": "OHt"})
    chunk_fc = NS(candidates=[NS(content=NS(parts=[NS(text=None, function_call=fc)]))])
    deltas = gemini_chunk_deltas(chunk_fc, next_id)
    ok6 = deltas == [
        ("tool_use", ToolUse(id="fc-1", name="lookup_error_code", input={"model": "iG5A", "code": "OHt"}))
    ]
    check("⑥ function_call → ToolUse, id 합성(fc-N)", ok6, str(deltas))

    # ── ⑦ args=None → 빈 dict, SDK 가 준 id 는 그대로
    fc2 = NS(id="srv-9", name="ping", args=None)
    chunk_fc2 = NS(candidates=[NS(content=NS(parts=[NS(text=None, function_call=fc2)]))])
    d7 = gemini_chunk_deltas(chunk_fc2, next_id)
    check(
        "⑦ args=None → {}, SDK id 보존",
        d7 == [("tool_use", ToolUse(id="srv-9", name="ping", input={}))],
        str(d7),
    )

    # ── ⑧ provider 오타 → 실패 (조용히 기본값으로 흘리지 않는다)
    # ⚠ "openai" 는 더 이상 오타 예시로 못 쓴다 — Elice/실 OpenAI 게이트웨이 진단용으로
    # PROVIDERS 에 실제로 추가됐다(EliceClient 재사용, base_url="https://api.openai.com").
    with env(MAINTQ_LLM_PROVIDER="openai_typo", MAINTQ_LLM_MODEL="x", GEMINI_API_KEY="k"):
        try:
            get_client()
            check("⑧ provider 오타 → RuntimeError", False, "예외 없음")
        except RuntimeError as e:
            check("⑧ provider 오타 → RuntimeError", "MAINTQ_LLM_PROVIDER" in str(e), str(e)[:60])

    # ── ⑨ 기본 provider = gemini — 키 없으면 GEMINI 키를 요구 (D40 폴백 금지 유지)
    with env(MAINTQ_LLM_MODEL="gemini-2.5-flash"):
        try:
            get_client()
            check("⑨ 기본 gemini — 키 없으면 실패", False, "예외 없음")
        except RuntimeError as e:
            check(
                "⑨ 기본 gemini — 키 없으면 실패 (GEMINI_API_KEY 안내, 폴백 없음)",
                "GEMINI_API_KEY" in str(e) and "provider=gemini" in str(e),
                str(e)[:80],
            )

    # ── ⑩ GOOGLE_API_KEY 만 있어도 GeminiClient 가 만들어진다 (네트워크 호출 없음)
    with env(GOOGLE_API_KEY="fake-key", MAINTQ_LLM_MODEL="gemini-2.5-flash"):
        c = get_client()
        check("⑩ GOOGLE_API_KEY 인정 → GeminiClient", isinstance(c, GeminiClient), type(c).__name__)

    # ── ⑪ provider=anthropic 경로 회귀 — 키 없으면 ANTHROPIC_API_KEY 안내
    with env(MAINTQ_LLM_PROVIDER="anthropic", MAINTQ_LLM_MODEL="m"):
        try:
            get_client()
            check("⑪ anthropic — 키 없으면 실패", False, "예외 없음")
        except RuntimeError as e:
            check(
                "⑪ anthropic — 키 없으면 실패 (ANTHROPIC_API_KEY 안내)",
                "ANTHROPIC_API_KEY" in str(e),
                str(e)[:60],
            )

    # ── ⑬ D56 — .env 의 빈 키는 미설정과 같다 (기본값을 지우면 안 된다)
    # .env.example 을 복사하면 `MAINTQ_LLM_PROVIDER=` 같은 빈 키가 생기고 dotenv 가
    # 빈 문자열로 os.environ 에 넣는다. `.get(키, 기본값)` 패턴은 이걸 "설정됨"으로 봐서
    # 기본값이 사라진다 — Stage 1 브라우저 검증에서 CORS 가 정확히 이걸로 전멸했다.
    with env(MAINTQ_LLM_PROVIDER="", GOOGLE_API_KEY="fake-key", MAINTQ_LLM_MODEL="gemini-2.5-flash"):
        c13 = get_client()
    check(
        "⑬ D56 — 빈 문자열 provider → 기본 gemini 적용 (★ 음성: .get 패턴이면 RuntimeError)",
        isinstance(c13, GeminiClient),
        type(c13).__name__,
    )

    # ── ⑭ D56 — 빈 MAINTQ_CORS_ORIGINS 도 기본 범위(3000~3005) 유지
    saved_cors = os.environ.get("MAINTQ_CORS_ORIGINS")
    os.environ["MAINTQ_CORS_ORIGINS"] = ""
    try:
        import backend.main as _main  # noqa: PLC0415 — env 설정 후 import 가 요점

        cors_ok = "http://localhost:3003" in _main.ALLOWED_ORIGINS
    finally:
        if saved_cors is None:
            os.environ.pop("MAINTQ_CORS_ORIGINS", None)
        else:
            os.environ["MAINTQ_CORS_ORIGINS"] = saved_cors
    check(
        "⑭ D56 — 빈 MAINTQ_CORS_ORIGINS → 기본 dev 범위 유지 (브라우저 검증 실측 결함)",
        cors_ok,
        f"origins={len(_main.ALLOWED_ORIGINS)}개",
    )

    # ── ⑫ OS env 우선 — load_dotenv(override=False) 가 기존 값을 덮지 않는다 (D56)
    # (a) 우리 코드가 그렇게 부르는지 — main.py 소스에 override=False 가 박혀 있어야 한다.
    #     True 로 바뀌면 .env 가 OS 환경변수를 조용히 덮어 "어느 키로 돌았는지"가 사라진다.
    main_src = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
    src_ok = "load_dotenv(override=False)" in main_src
    # (b) 그 호출이 실제로 그렇게 동작하는지 — 임시 .env 로 실측 (★ 음성: 빈 키는 채워진다)
    from dotenv import load_dotenv  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as td:
        envfile = Path(td) / ".env"
        envfile.write_text("MAINTQ_SENTINEL_A=file\nMAINTQ_SENTINEL_B=file\n", encoding="utf-8")
        os.environ["MAINTQ_SENTINEL_A"] = "os"
        os.environ.pop("MAINTQ_SENTINEL_B", None)
        try:
            load_dotenv(envfile, override=False)
            behave_ok = (
                os.environ.get("MAINTQ_SENTINEL_A") == "os"  # OS 값 유지
                and os.environ.get("MAINTQ_SENTINEL_B") == "file"  # 빈 곳은 채움
            )
        finally:
            os.environ.pop("MAINTQ_SENTINEL_A", None)
            os.environ.pop("MAINTQ_SENTINEL_B", None)
    check(
        "⑫ D56 — OS env 우선 (main.py override=False + dotenv 실측)",
        src_ok and behave_ok,
        f"src={src_ok}, os유지·빈곳채움={behave_ok}",
    )

    # ── D115 — Elice 게이트웨이 (InsuQ ai-engine/insuq_ai/generation/llm.py 이식)

    # ── ⑮ elice_tools — OpenAI tool-calling 스키마 변환, input_schema 그대로 실림
    etools = elice_tools(
        [{"name": "lookup_error_code", "description": "코드 조회", "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}}}]
    )
    check(
        "⑮ elice_tools — type:function 래핑, name·description·parameters 보존",
        etools == [{
            "type": "function",
            "function": {
                "name": "lookup_error_code",
                "description": "코드 조회",
                "parameters": {"type": "object", "properties": {"code": {"type": "string"}}},
            },
        }],
        str(etools),
    )

    # ── ⑯ elice_messages — user/assistant 그대로, tool 은 JSON 텍스트로 평탄화한 user 메시지
    # (네이티브 tool_calls 페어를 합성하면 Gemini가 이전 턴 thought_signature 를 요구해
    # 400 이 난다 — 실측 확인, anthropic_messages 와 같은 이유로 같은 해법을 쓴다)
    emsgs = elice_messages(
        [
            {"role": "user", "content": "OHt 에러"},
            {"role": "assistant", "content": "확인 중"},
            {"role": "tool", "name": "lookup_error_code", "content": {"cause": "과열"}},
        ]
    )
    ok16 = (
        [m["role"] for m in emsgs] == ["user", "assistant", "user"]
        and "lookup_error_code" in emsgs[2]["content"]
        and "과열" in emsgs[2]["content"]
    )
    check("⑯ elice_messages — tool 결과를 JSON 텍스트로 평탄화한 user 메시지로 (thought_signature 회피)", ok16, f"roles={[m['role'] for m in emsgs]}")

    # ── ⑰ elice_chunk_delta — 본문 텍스트 델타 정규화 (SDK 없이 가짜 chunk)
    chunk_text = NS(choices=[NS(delta=NS(content="안녕", tool_calls=None), finish_reason=None)])
    text17, frags17, finish17 = elice_chunk_delta(chunk_text)
    check("⑰ elice_chunk_delta — 텍스트 델타 정규화", text17 == "안녕" and frags17 == [] and finish17 is None, f"{text17!r},{frags17},{finish17}")

    # ── ⑱ elice_chunk_delta — tool_call 조각(index·id·function.name/arguments) 추출
    tc_frag = NS(index=0, id="call_abc", function=NS(name="lookup_error_code", arguments='{"model":'))
    chunk_tc = NS(choices=[NS(delta=NS(content=None, tool_calls=[tc_frag]), finish_reason=None)])
    text18, frags18, finish18 = elice_chunk_delta(chunk_tc)
    check(
        "⑱ elice_chunk_delta — tool_call 조각 추출(부분 arguments 포함)",
        text18 is None and frags18 == [{"index": 0, "id": "call_abc", "name": "lookup_error_code", "arguments": '{"model":'}],
        f"{frags18}",
    )

    # ── ⑲ elice_chunk_delta — finish_reason 은 마지막 청크에만 실린다
    chunk_end = NS(choices=[NS(delta=NS(content=None, tool_calls=None), finish_reason="tool_calls")])
    _, _, finish19 = elice_chunk_delta(chunk_end)
    check("⑲ elice_chunk_delta — finish_reason 정규화", finish19 == "tool_calls", str(finish19))

    # ── ⑳ elice_finalize_tool_calls — 여러 청크에 걸쳐 쪼개진 arguments 를 index 순서로 합친다
    acc: dict[int, dict] = {}
    for frag in (
        {"index": 1, "id": "call_2", "name": "search_insurance_clause", "arguments": None},
        {"index": 0, "id": "call_1", "name": "lookup_error_code", "arguments": '{"model":'},
        {"index": 0, "id": None, "name": None, "arguments": '"iG5A"}'},
        {"index": 1, "id": None, "name": None, "arguments": '{"question":"q"}'},
    ):
        idx = frag["index"]
        cur = acc.setdefault(idx, {"id": frag["id"] or f"call_{idx}", "name": "", "args": ""})
        if frag["id"]:
            cur["id"] = frag["id"]
        if frag["name"]:
            cur["name"] = frag["name"]
        if frag["arguments"]:
            cur["args"] += frag["arguments"]
    finalized = elice_finalize_tool_calls(acc)
    check(
        "⑳ elice_finalize_tool_calls — index 오름차순, 조각난 JSON arguments 병합·파싱",
        finalized == [
            ToolUse(id="call_1", name="lookup_error_code", input={"model": "iG5A"}),
            ToolUse(id="call_2", name="search_insurance_clause", input={"question": "q"}),
        ],
        str(finalized),
    )

    # ── ㉑ provider=elice — 키 없으면 ELICE_API_KEY 안내
    with env(MAINTQ_LLM_PROVIDER="elice", MAINTQ_LLM_MODEL="gemini-3.5-flash-lite"):
        try:
            get_client()
            check("㉑ elice — 키 없으면 실패", False, "예외 없음")
        except RuntimeError as e:
            check("㉑ elice — 키 없으면 실패 (ELICE_API_KEY 안내)", "ELICE_API_KEY" in str(e), str(e)[:80])

    # ── ㉒ provider=elice — 키는 있지만 ELICE_LLM_URL 없으면 실패(base_url 없이 게이트웨이 특정 불가)
    with env(MAINTQ_LLM_PROVIDER="elice", MAINTQ_LLM_MODEL="gemini-3.5-flash-lite", ELICE_API_KEY="k"):
        try:
            get_client()
            check("㉒ elice — ELICE_LLM_URL 없으면 실패", False, "예외 없음")
        except RuntimeError as e:
            check("㉒ elice — ELICE_LLM_URL 없으면 실패", "ELICE_LLM_URL" in str(e), str(e)[:80])

    # ── ㉓ provider=elice — 키·URL 다 있으면 EliceClient (네트워크 호출 없음)
    with env(
        MAINTQ_LLM_PROVIDER="elice",
        MAINTQ_LLM_MODEL="gemini-3.5-flash-lite",
        ELICE_API_KEY="k",
        ELICE_LLM_URL="https://mlapi.run/fake-deploy-id",
    ):
        c23 = get_client()
    check("㉓ elice — 키·URL 모두 있으면 EliceClient", isinstance(c23, EliceClient), type(c23).__name__)


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("LLM 제공자 계약 검증 (D40 · D56 — SDK 호출·네트워크 없음)\n")
    run()

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 44))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 44))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(f"\n통과 ({len(results)}건) — 변환 순수함수 · provider 분기 · OS env 우선 확인")


if __name__ == "__main__":
    main()
