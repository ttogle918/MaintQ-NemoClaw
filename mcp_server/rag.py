# -*- coding: utf-8 -*-
"""매뉴얼 본문 검색 — 키워드 + dense **하이브리드** 리트리버 (D47·D48).

구현체를 MCP 서버 쪽에 둔다 (D48). `backend/rag/` 를 만들지 않고, `from backend...` 도
하지 않는다 — 도구는 별도 프로세스에서 돌기 때문에 백엔드를 import 하면 D15 프로세스
분리가 코드 공유로 깨진다.

입력 인덱스는 MQ-305 산출물 `data/extracted/manual_chunks.jsonl` 이다 (키 7개 고정:
chunk_id/manual_id/model/page/section/text/char_len). 이 모듈은 인덱스를 **읽기만** 한다.

설계 요점
  - **하이브리드 인터페이스 고정** (D47): `search(model, query, top_k, dense=None)` 이
    키워드 스코어와 dense 스코어를 **둘 다 받아 가중 융합**한다. `dense=None` 이면
    키워드 점수만 쓴다. 임베딩 모델·벡터스토어·가중치는 **D51 에서 사람이 정한다** —
    이 모듈은 어떤 임베딩도 고르지 않고, 어떤 모델도 import 하지 않는다.
  - **model 필터를 가장 먼저** 적용한다 (04_MCP_TOOLS §2 "model 필터 필수", D28 과 같은
    논리). 스코어링·IDF 모수 전부 필터 이후 집합에서만 계산된다.
  - **결정론**: 같은 인덱스 + 같은 질의 = 항상 같은 결과. 질의 토큰은 정렬해 합산하고,
    정렬 키는 `(-score, page, chunk_id)` 다 (동점은 page 오름차순). 평가(D30 인용률)가
    재현되려면 이게 성립해야 한다.
  - **text 를 절단하지 않는다** (D53). 길이 상한은 청킹 단계(MAX_CHARS=900)에서 이미
    걸려 있고, 절차 문단이 중간에서 끊기면 에이전트가 뒷부분을 지어낸다.
  - **page 를 가공하지 않는다** (D26). 인쇄 페이지 환산은 backend/manifest.py 한 곳 (D32).

키워드 스코어러에 **IDF 를 넣은 이유** (rag_sizing.md §6·§7-4 결정 요청에 대한 답):
  스프린트 명세는 "토큰 포함 빈도 / 청크 길이 정규화"만 규정했으나, 그대로 두면 '점검'·
  '인버터' 같이 문서 전반에 깔린 낱말이 'GFT'·'지락' 같은 희귀 토큰을 압도한다
  (rag_sizing §6 실패 3·4번). 이건 의미 이해 부족이 아니라 **가중치 부재**라서 dense 없이
  고칠 수 있다. IDF 는 인덱스만으로 결정되는 값이라 결정론도 깨지지 않는다.
  04_MCP_TOOLS §2 의 입출력 계약은 그대로다 — 스코어링은 계약 밖의 내부 구현이다.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

_DEFAULT_INDEX = (
    Path(__file__).resolve().parent.parent / "data" / "extracted" / "manual_chunks.jsonl"
)

# 계약 테스트가 실 인덱스를 건드리지 않고 합성 인덱스를 물릴 수 있게 갈아끼우기 가능
# (mcp_server/db.py 의 DB_PATH 와 같은 방식)
INDEX_PATH = Path(os.environ.get("MAINTQ_CHUNKS") or _DEFAULT_INDEX)

MODELS = ("iG5A", "S100", "IE5")

DEFAULT_TOP_K = 3
MAX_TOP_K = 10

# ── 하이브리드 가중치 (D47) ──────────────────────────────────────────────
# **실측값이 아니다.** eval 세트가 아직 없어 비대칭 숫자를 적을 근거가 없으므로
# "정보 없음 = 동률"인 자리표시자를 둔다. 실제 값은 **D51 에서 eval 로 조정**한다
# (rag_sizing.md §7-3: 그 전에 숫자를 넣으면 지어내는 것).
# dense=None 인 동안에는 KEYWORD_WEIGHT 가 순위에 영향을 주지 않는다(단조 스케일).
KEYWORD_WEIGHT = 1.0
DENSE_WEIGHT = 1.0

# dense scorer 주입 규약 (D47): (query, chunks) -> chunks 와 **같은 길이·같은 순서**의 점수열.
# chunks 는 model 필터가 이미 적용된 원본 청크 dict 리스트다.
DenseScorer = Callable[[str, list[dict]], Sequence[float]]

# 인덱스는 있지만 정렬용 부동소수가 미세하게 갈리는 경우까지 "동점"으로 보고
# page 오름차순 규칙이 실제로 발동하게 한다 (결정론 강화)
_SCORE_PRECISION = 9

# 라틴/숫자 런과 한글 런만 토큰 후보로 본다 (기호·공백은 버린다)
_TOKEN_RUN = re.compile(r"[a-z0-9]+|[가-힣]+")


class IndexNotBuilt(RuntimeError):
    """인덱스를 **사용할 수 있는 상태가 아니다** — 파일 없음/빈 인덱스/해독 불가.

    이걸 "검색 결과 없음(empty)"과 절대 섞지 않는다. empty 는 "매뉴얼에 그런 내용이
    없다"는 신호라, 인덱스 미구축을 empty 로 주면 에이전트가 절차를 지어낼 여지가 생긴다
    (D50 이 error_codes 0행에서 내린 판단과 같은 논리).
    """


def tokenize(text: str) -> list[str]:
    """결정론적 토크나이저 — 외부 의존성 없음.

    한글은 형태소 분석기 없이 **2음절 바이그램**으로 자른다. 조사가 붙은 표기
    ('지락이'·'출력측에')와 질의 표기('지락'·'출력측')가 정확 일치하지 않는 문제를
    의존성 없이 흡수하기 위한 것이다(Lucene CJKBigram 과 같은 발상).
    라틴/숫자는 런 단위 그대로 — 'OCt'·'GFT'·'FAN-IG5-01' 같은 정확 토큰이 이 도메인의
    강점이라 쪼개지 않는다 (D47 이 키워드를 남겨 둔 이유).
    """
    tokens: list[str] = []
    for run in _TOKEN_RUN.findall(text.lower()):
        if run[0].isascii() or len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


class _Doc:
    """청크 1건 + 스코어링용 파생값. 원본 dict(`chunk`)는 절대 변형하지 않는다 (D53·D26)."""

    __slots__ = ("chunk", "tf", "ntok")

    def __init__(self, chunk: dict) -> None:
        self.chunk = chunk
        tokens = tokenize(chunk.get("text", ""))
        self.tf: Counter[str] = Counter(tokens)
        self.ntok = len(tokens)


class _ModelIndex:
    """model 필터 적용 후의 검색 모수. IDF 도 이 집합에서만 계산한다."""

    __slots__ = ("docs", "idf")

    def __init__(self, docs: list[_Doc]) -> None:
        self.docs = docs
        n = len(docs)
        df: Counter[str] = Counter()
        for d in docs:
            df.update(d.tf.keys())
        # smoothed IDF — 항상 양수라 점수 부호가 뒤집히지 않는다
        self.idf = {t: math.log(1.0 + n / (1.0 + c)) for t, c in df.items()}


_CACHE: dict = {"sig": None, "models": {}}


def _signature(path: Path) -> tuple:
    st = path.stat()
    return (str(path), st.st_mtime_ns, st.st_size)


def _load(path: Path) -> dict:
    """인덱스를 읽어 model 별로 전처리한다. 같은 파일이면 캐시 재사용(멱등)."""
    if not path.exists():
        raise IndexNotBuilt(
            f"매뉴얼 인덱스가 없습니다: {path} — data/chunk_manual.py 를 먼저 실행하세요"
        )
    sig = _signature(path)
    if _CACHE["sig"] == sig:
        return _CACHE["models"]

    by_model: dict[str, list[_Doc]] = {}
    total = 0
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise IndexNotBuilt(f"인덱스 {lineno}행을 읽을 수 없습니다: {e}") from e
            model = rec.get("model")
            if model not in MODELS:
                # 알 수 없는 기종 라벨은 조용히 섞이면 안 된다 (D6·D13)
                raise IndexNotBuilt(f"인덱스 {lineno}행의 model 이 enum 밖입니다: {model!r}")
            by_model.setdefault(model, []).append(_Doc(rec))
            total += 1

    if total == 0:
        raise IndexNotBuilt(f"매뉴얼 인덱스가 비어 있습니다: {path}")

    models = {m: _ModelIndex(docs) for m, docs in by_model.items()}
    _CACHE["sig"] = sig
    _CACHE["models"] = models
    return models


def _keyword_scores(mi: _ModelIndex, q_tokens: list[str]) -> list[float]:
    """토큰 빈도 × IDF / 길이 정규화. q_tokens 는 **정렬된** 리스트여야 한다(합산 순서 고정)."""
    scores: list[float] = []
    for d in mi.docs:
        s = 0.0
        for t in q_tokens:
            tf = d.tf.get(t)
            if tf:
                s += mi.idf.get(t, 0.0) * tf
        # 긴 청크가 단순 빈도로 유리해지는 걸 눌러 준다 (+10 은 짧은 청크 폭주 완충)
        scores.append(s / math.log(d.ntok + 10))
    return scores


def _normalize(values: list[float]) -> list[float]:
    """최댓값 스케일 정규화 — 0 은 0으로 유지된다(min-max 와 달리 '무매칭'이 살아나지 않는다).

    두 스코어러의 단위가 다르므로(키워드 합 vs 코사인) 융합 전에 같은 눈금으로 맞춘다.
    단조 변환이라 dense=None 일 때 키워드 순위는 바뀌지 않는다.
    """
    top = max(values, default=0.0)
    if top <= 0:
        return [0.0] * len(values)
    return [v / top for v in values]


def search(
    model: str,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    dense: DenseScorer | None = None,
) -> list[dict]:
    """매뉴얼 청크를 검색해 상위 top_k 를 돌려준다.

    반환: `[{chunk_id, manual_id, model, page, section, text, score}, ...]`
    `score` 는 **디버깅·튜닝용 내부 값**이다. 04_MCP_TOOLS §2 계약에는 없으므로
    도구 레이어(`tools/rag_search_manual.py`)가 제거한다.

    실패는 예외로 던진다 — status 변환은 도구 레이어의 책임이다 (D9).
    """
    if model not in MODELS:
        raise ValueError(f"model은 {'|'.join(MODELS)} 이어야 합니다: {model!r}")

    k = top_k if isinstance(top_k, int) and not isinstance(top_k, bool) else DEFAULT_TOP_K
    k = max(1, min(MAX_TOP_K, k))

    models = _load(INDEX_PATH)

    # ── model 필터 **먼저** (04 §2 · D28 과 같은 논리)
    mi = models.get(model)
    if mi is None or not mi.docs:
        # 인덱스는 있는데 이 기종 청크가 0건 = 부분 구축 상태. empty 로 주면
        # "이 기종 매뉴얼엔 그 내용이 없다"는 거짓 신호가 된다 (IndexNotBuilt 참조)
        raise IndexNotBuilt(f"인덱스에 {model} 청크가 없습니다 — 재구축이 필요합니다")

    q_tokens = sorted(set(tokenize(query)))
    kw = _normalize(_keyword_scores(mi, q_tokens))

    if dense is None:
        dn = [0.0] * len(mi.docs)
        weights = (KEYWORD_WEIGHT, 0.0)
    else:
        raw = dense(query, [d.chunk for d in mi.docs])
        if len(raw) != len(mi.docs):
            raise ValueError(
                f"dense scorer 가 {len(mi.docs)}개가 아니라 {len(raw)}개 점수를 반환했습니다"
            )
        # 음수·NaN(코사인 하한, 미계산 표시)은 0 으로 눌러 융합을 오염시키지 않는다
        dn = _normalize([v if isinstance(v, (int, float)) and v > 0 else 0.0 for v in raw])
        weights = (KEYWORD_WEIGHT, DENSE_WEIGHT)

    ranked: list[tuple[float, int, str, dict]] = []
    for i, d in enumerate(mi.docs):
        fused = weights[0] * kw[i] + weights[1] * dn[i]
        if fused <= 0:
            continue  # 무매칭은 순위에 넣지 않는다 → 0건이면 도구가 empty (D9)
        page = d.chunk.get("page")
        ranked.append((round(fused, _SCORE_PRECISION), page, d.chunk.get("chunk_id", ""), d.chunk))

    # 동점은 page 오름차순, 그래도 같으면 chunk_id — 전순서라 결과가 항상 재현된다
    ranked.sort(key=lambda r: (-r[0], r[1], r[2]))

    out: list[dict] = []
    for score, _page, _cid, chunk in ranked[:k]:
        hit = dict(chunk)  # 원본 청크를 그대로 (text 절단 없음 D53 · page 무가공 D26)
        hit["score"] = score
        out.append(hit)
    return out
