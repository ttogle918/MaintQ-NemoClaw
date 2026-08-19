# -*- coding: utf-8 -*-
"""LLM 응답 카세트 — 개발 가속용 응답 캐시 (D105 · 설계 스펙 2026-08-19).

**기본 꺼짐.** `MAINTQ_LLM_CACHE=on` 일 때만 동작한다 — D40 이 *"테스트용 스크립트 응답으로
자동 대체하지 않는다(가짜 응답을 진짜로 착각하는 사고를 막기 위해)"* 라고 정한 태도를 따라
명시적 옵트인으로 둔다.

**이 모듈은 네트워크를 타지 않는다.** 실제 호출은 감싸인 `inner` 가 한다.

⚠ **캐시 히트는 D55 재생이다.** `CachingClient.last_hit` 을 `run_turn` 이 읽어
`trace.replay = True` 로 켜고, 그러면 `eval/score.py:has_replay()` 가 그 세션을 지표
분모에서 제외한다. **그 한 줄이 빠지면 히트가 지표에 조용히 섞인다** — 이 설계에서 가장
빠뜨리기 쉬운 지점이라 회귀가 따로 그것만 본다.

저장은 `data/cache/llm/<key>.json` 이고 **git 미추적**이다. 언제 지워도 된다.
⛔ `data/external/store.py`(D103)를 쓰지 않는다 — 그건 git 추적·append-only 외부 원본용이라
성격이 정반대다.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Final

from backend.agent.llm import LlmDelta, ToolUse

ENV_FLAG: Final[str] = "MAINTQ_LLM_CACHE"
CACHE_ROOT: Final[Path] = Path(__file__).resolve().parents[2] / "data" / "cache" / "llm"
SCHEMA: Final[str] = "maintq.llmcache.v1"

#: 사이드카 히트율 통계 파일명 — 캐시 항목(sha256 hex 64자 파일명)과 겹치지 않는다.
#: 프로세스 경계를 넘겨야 하는 상황(`eval/run_eval.py::_start_server` 가 백엔드를 별도
#: OS 서브프로세스로 띄운다)에서 인스턴스 카운터 대신 이 파일을 읽고 쓴다 — 설계 스펙
#: §6-2. 로그로 풀지 않는 이유는 이 파일 상단 독스트링이 아니라 태스크 브리프(Task 7)를
#: 참조: 2026-08-12 사고 이력(로그 증설이 서버 이벤트 루프를 멈춘 적이 있다) 때문에
#: `eval/run_eval.py::_start_server` 근처에는 로그를 늘리지 않는다.
STATS_NAME: Final[str] = "_stats.json"


def cache_enabled() -> bool:
    """`MAINTQ_LLM_CACHE` 가 정확히 `on` 일 때만 True. 빈 값·미설정은 꺼짐(D56 선례)."""
    return (os.environ.get(ENV_FLAG) or "").strip().lower() == "on"


def cache_key(
    *,
    provider: str,
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
) -> str:
    """호출 입력 전체의 sha256.

    `provider`·`model` 을 넣는 이유: 모델을 바꾸면 **반드시 미스가 나야 한다.**
    안 그러면 flash 로 만든 응답을 flash-lite 결과로 착각한다.
    """
    blob = json.dumps(
        {
            "provider": provider,
            "model": model,
            "system": system,
            "messages": messages,
            "tools": tools,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def encode_delta(delta: LlmDelta) -> dict[str, Any]:
    """`("text"|"tool_use"|"end", payload)` → JSON 직렬화 가능 dict."""
    kind, payload = delta
    if kind == "tool_use" and isinstance(payload, ToolUse):
        return {"kind": kind, "id": payload.id, "name": payload.name, "input": payload.input}
    return {"kind": kind, "value": payload}


def decode_delta(raw: dict[str, Any]) -> LlmDelta:
    kind = raw.get("kind")
    if kind == "tool_use":
        return ("tool_use", ToolUse(id=raw["id"], name=raw["name"], input=raw.get("input") or {}))
    return (str(kind), raw.get("value"))


#: `decode_delta` 가 받아도 되는 kind 화이트리스트. 이 밖은 캐시 파일 손상으로 본다.
_KNOWN_KINDS = frozenset({"text", "tool_use", "end"})


def _load_cached_deltas(path: Path) -> list[LlmDelta] | None:
    """캐시 파일을 로드·검증한다. 손상됐으면 `None`(미스로 취급)을 돌려준다.

    `decode_delta` 는 예상 밖 `kind`(예: `None`)에도 예외 없이 `("None", None)` 을
    돌려준다 — 그 관용성이 손상된 캐시 파일을 조용히 이상한 델타로 재생하지 않도록,
    로드 시점에서 `_schema`·`deltas` 형태·`kind` 화이트리스트를 검사한다(D62 — 모름을
    통과로 바꾸지 않는다). 캐시는 개발 보조물이라 손상됐다고 예외를 던져 실행을 죽이지
    않는다 — 캐시가 없는 것처럼 미스로 폴백한다.
    """
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        # UnicodeDecodeError 는 OSError 의 하위 클래스가 아니다(ValueError 계열) —
        # 파일 바이트가 깨져 UTF-8 디코딩이 실패하는 경우도 명시적으로 잡아야
        # 손상 캐시가 예외로 새지 않고 미스로 폴백한다.
        return None
    if not isinstance(record, dict) or record.get("_schema") != SCHEMA:
        return None
    raw_deltas = record.get("deltas")
    if not isinstance(raw_deltas, list):
        return None
    for raw in raw_deltas:
        if not isinstance(raw, dict) or raw.get("kind") not in _KNOWN_KINDS:
            return None
    try:
        return [decode_delta(raw) for raw in raw_deltas]
    except (KeyError, TypeError):
        return None


def stats_path(root: Path | None = None) -> Path:
    """사이드카 통계 파일 경로. `root` 를 안 주면 기본 캐시 디렉터리(`CACHE_ROOT`)."""
    base = Path(root) if root is not None else CACHE_ROOT
    return base / STATS_NAME


def reset_stats(root: Path | None = None) -> None:
    """사이드카 통계 파일을 지운다. 없으면 무동작(예외를 내지 않는다).

    `eval/run_eval.py` 가 실행 시작 시 부른다 — 이번 실행의 수치만 재기 위해서다.
    """
    try:
        stats_path(root).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        # 계측용 파일이다 — 삭제가 안 돼도(권한 등) 실행을 막지 않는다.
        pass


def read_stats(root: Path | None = None) -> dict[str, int]:
    """사이드카에서 `{"hits": int, "misses": int}` 를 읽는다.

    파일이 없거나 손상됐으면 `{"hits": 0, "misses": 0}` 을 돌려준다 — 카세트 본체
    (`_load_cached_deltas`)와 같은 태도로, 계측 파일이 깨졌다고 실행을 죽이지 않는다.
    """
    try:
        record = json.loads(stats_path(root).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"hits": 0, "misses": 0}
    if not isinstance(record, dict):
        return {"hits": 0, "misses": 0}
    hits, misses = record.get("hits"), record.get("misses")
    if not isinstance(hits, int) or not isinstance(misses, int):
        return {"hits": 0, "misses": 0}
    return {"hits": hits, "misses": misses}


def stats_line(root: Path | None = None) -> str:
    """`캐시 히트 N/M (히트율 X%)` — **사이드카 파일에서 읽는** 모듈 레벨 버전.

    ⚠ `CachingClient.stats_line()`(인스턴스 메서드, 아래)과 이름이 같지만 다른 함수다.
    인스턴스 메서드는 그 인스턴스 하나가 겪은 호출만 본다. 이 함수는 프로세스 경계를
    넘어 사이드카 파일에 누적된 값을 읽는다 — `run_eval.py` 가 서브프로세스로 띄운
    백엔드 서버 안의 `CachingClient` 인스턴스에는 접근할 수 없으므로, 서버가 매 호출마다
    갱신해 둔 이 파일을 CLI 프로세스가 읽어 인쇄한다(설계 스펙 §6-2).
    """
    stats = read_stats(root)
    hits, misses = stats["hits"], stats["misses"]
    total = hits + misses
    rate = (hits / total * 100) if total else 0.0
    return f"캐시 히트 {hits}/{total} (히트율 {rate:.1f}%)"


def _bump_stats(root: Path | None, *, hit: bool) -> None:
    """사이드카 통계를 read-modify-write 로 1 증가시킨다.

    개발 보조물이라 경합은 고려하지 않는다 — 단일 프로세스 전제(`SessionStore` 독스트링이
    같은 전제를 적어 뒀다). 🔴 이 함수의 실패가 LLM 호출을 죽이면 안 된다 — 계측이지
    기능이 아니다. 그래서 파일 IO/직렬화 실패를 조용히 삼킨다.
    """
    try:
        stats = read_stats(root)
        if hit:
            stats["hits"] += 1
        else:
            stats["misses"] += 1
        path = stats_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")
    except (OSError, ValueError):
        pass


class CachingClient:
    """`LlmClient` 데코레이터 — 응답만 재생하고 도구 실행은 그대로 둔다.

    ⚠ `last_hit` 은 `stream()` **호출 시점에** 확정된다(조회가 동기라서). `run_turn` 은
    델타 루프 첫 회차에서 이 값을 읽어 `trace.replay` 를 켠다 — `_safe_stream` 이
    async generator 라 `stream()` 이 첫 델타를 당길 때 비로소 호출되기 때문이다.
    """

    def __init__(
        self,
        inner: Any,
        *,
        provider: str,
        model: str,
        root: Path | None = None,
    ) -> None:
        self._inner = inner
        self._provider = provider
        self._model = model
        self._root = Path(root) if root is not None else CACHE_ROOT
        self.last_hit: bool = False
        self.hits: int = 0
        self.misses: int = 0

    def _path(self, key: str) -> Path:
        return self._root / f"{key}.json"

    def stream(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ):
        key = cache_key(
            provider=self._provider,
            model=self._model,
            system=system,
            messages=messages,
            tools=tools,
        )
        path = self._path(key)
        if path.exists():
            deltas = _load_cached_deltas(path)
            if deltas is not None:
                self.last_hit = True
                self.hits += 1
                _bump_stats(self._root, hit=True)

                async def replay():
                    for d in deltas:
                        yield d

                return replay()
            # 손상된 캐시 파일 — 미스로 취급하고 아래 inner 호출 경로로 진행한다.

        self.last_hit = False
        self.misses += 1
        _bump_stats(self._root, hit=False)
        inner_stream = self._inner.stream(system=system, messages=messages, tools=tools)

        async def record_and_yield():
            captured: list[LlmDelta] = []
            async for delta in inner_stream:
                captured.append(delta)
                yield delta
            # 스트림이 끝까지 온 경우에만 기록한다 — 도중에 끊긴 응답을 캐시하면
            # 다음 실행이 잘린 답을 "정상"으로 재생한다.
            if not captured:
                # 빈 델타 목록은 캐시하지 않는다. 이 카세트를 나중에 히트로 재생하면
                # `record_and_yield` 가 아니라 `replay()`(위)가 델타를 하나도 안 흘리고
                # 끝난다 — `run_turn` 의 델타 소비 루프 본문이 **한 번도 실행되지 않아**
                # `trace.replay = True` 배선(loop.py)도 함께 건너뛴다. 그러면 캐시 히트가
                # `eval/score.has_replay()` 의 분모에서 빠지지 않고 **무표식으로 지표에
                # 섞인다** — 도중에 끊긴 응답을 캐시하지 않는 것과 같은 이유(잘못된 재생
                # 방지)로, 빈 응답에도 같은 원칙을 적용한다.
                return
            self._root.mkdir(parents=True, exist_ok=True)
            payload = {
                "_schema": SCHEMA,
                "provider": self._provider,
                "model": self._model,
                "deltas": [encode_delta(d) for d in captured],
            }
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

        return record_and_yield()

    def stats_line(self) -> str:
        """`캐시 히트 N/M (히트율 X%)`. 실익이 있는지 **재고 나서** 판단하기 위한 실측치다.

        ⚠ 이 **인스턴스** 메서드는 `self.hits`/`self.misses` 만 본다 — 이 인스턴스가
        생성된 뒤 겪은 호출만 반영한다. 프로세스 경계를 넘는 누적치가 필요하면(예:
        `eval/run_eval.py` 가 서브프로세스로 띄운 서버 안의 인스턴스) 모듈 레벨
        `llm_cache.stats_line(root=...)` 를 쓴다 — 그건 사이드카 파일에서 읽는다.
        """
        total = self.hits + self.misses
        rate = (self.hits / total * 100) if total else 0.0
        return f"캐시 히트 {self.hits}/{total} (히트율 {rate:.1f}%)"
