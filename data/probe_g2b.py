# -*- coding: utf-8 -*-
"""조달청 오픈API 접근 권한 프로브 (A4·A7 · 확장 범위 D67) — 읽기만 하고 아무것도 저장하지 않는다.

**이 스크립트가 있는 이유.** 2026-08-13 세션 계획이 *"`DATA_GO_KR_SERVICE_KEY` 는
`.env` 에 이미 있다"* 로 적혀 있어 **호출이 될 것처럼 읽혔는데, 실측하니 안 된다.**
data.go.kr 은 **키 발급과 서비스별 활용신청이 별개**여서 키가 채워져 있어도
신청 안 한 서비스는 `HTTP 403 SERVICE_KEY_IS_NOT_REGISTERED_ERROR` 로 막힌다.
그 사실을 다음 사람이 코드 한 줄로 다시 확인할 수 있게 남긴다.

⚠ **위조 키 대조군이 판정에 들어 있다 (CLAUDE.md 부재검사 규칙).**
`403` 하나만 보면 *"활용신청이 안 됐다"* 와 *"키가 만료·오타다"* 를 **구분하지 못한다**.
그래서 매 엔드포인트를 **실제 키**와 **명백한 위조 키**로 각각 때리고 **응답을 비교**한다:

  - 두 응답이 **같다**  → 서버가 우리 키를 **알아보지도 못한다** = 활용신청 미승인
  - 두 응답이 **다르다** → 키는 인식된다 = 다른 원인(파라미터·기간·쿼터)
  - 실제 키만 **200**  → ✅ 승인됨

**2026-08-14 실측: 3개 엔드포인트 전부 "두 응답이 같다".** 신청 절차는
`TODO_직접할일.md §데이터 확보` 에 있다(사람 손이 필요하다).

실행: `uv run --with python-dotenv python data/probe_g2b.py`
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from dotenv import load_dotenv

BASE = "https://apis.data.go.kr/1230000"
BOGUS_KEY = "A" * 88  # 형식만 그럴듯한 명백한 위조 키 — 대조군

# (라벨, 경로, 추가 파라미터) — data_list.md §후속조사가 고른 3개만 본다
ENDPOINTS: list[tuple[str, str, dict[str, str]]] = [
    (
        "종합쇼핑몰 MAS계약품목 (품목별 계약단가)",
        "/at/ShoppingMallPrdctInfoService/getMASCntrctPrdctInfoList",
        {},
    ),
    (
        "개방표준 계약정보 (실거래가)",
        "/ao/PubDataOpnStdService/getDataSetOpnStdCntrctInfo",
        {"cntrctCnclsBgnDate": "20260101", "cntrctCnclsEndDate": "20260131"},
    ),
    (
        "개방표준 낙찰정보 (낙찰가 보조)",
        "/ao/PubDataOpnStdService/getDataSetOpnStdScsbidInfo",
        {"bidNtceBgnDt": "202601010000", "bidNtceEndDt": "202601312359"},
    ),
]


def call(path: str, key: str, extra: dict[str, str]) -> tuple[int, str]:
    """(status, body) 를 돌려준다. 예외를 던지지 않는다 — 프로브라 실패도 관측값이다."""
    params = {"pageNo": "1", "numOfRows": "2", "type": "json", **extra}
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}&serviceKey={urllib.parse.quote(key, safe='')}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310 — 고정 호스트
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 — 네트워크 실패도 결과로 인쇄한다
        return -1, repr(e)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")  # Windows cp949 콘솔 대응

    load_dotenv(".env")
    key = os.environ.get("DATA_GO_KR_SERVICE_KEY", "")
    if not key:
        print("⛔ .env 에 DATA_GO_KR_SERVICE_KEY 가 없다. 발급부터 필요하다.")
        return 1

    print(f"키 길이 {len(key)}자 (인코딩키면 % 포함) · 위조 대조군 {len(BOGUS_KEY)}자\n")
    approved = 0
    for label, path, extra in ENDPOINTS:
        real_st, real_body = call(path, key, extra)
        bogus_st, bogus_body = call(path, BOGUS_KEY, extra)
        same = (real_st, real_body) == (bogus_st, bogus_body)

        if real_st == 200 and not same:
            verdict = "✅ 승인됨"
            approved += 1
        elif same:
            verdict = "❌ 활용신청 미승인 (실제 키 = 위조 키, 서버가 알아보지 못함)"
        else:
            verdict = "🔶 키는 인식됨 — 다른 원인(파라미터·기간·쿼터)"

        print(f"[{label}]")
        print(f"  실제 키 HTTP {real_st} · 위조 키 HTTP {bogus_st} · 응답 동일: {same}")
        print(f"  판정: {verdict}")
        print(f"  응답: {real_body[:160].replace(chr(10), ' ')}\n")

    print(f"승인된 엔드포인트 {approved}/{len(ENDPOINTS)}")
    if approved == 0:
        print("→ TODO_직접할일.md §데이터 확보 의 활용신청 3건이 선행 조건이다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
