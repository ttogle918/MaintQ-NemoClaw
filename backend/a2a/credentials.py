"""파트너 자격증명 읽기 층 (D93 → D120 이 스킴을 교체).

`<PARTNER>_SERVICE_TOKEN` (예: `INSUQ_SERVICE_TOKEN`) 하나를 **읽기만** 한다.
파트너 자격증명은 이 레포의 **세 번째 갈래**다 — 수집 스크립트 키가 아니고(런타임에 읽는다),
LLM 키와도 다르다(이 자격증명으로 나가는 요청은 돈을 움직인다, S5).

**D120 (2026-08-24) — CLIENT_ID/CLIENT_SECRET(Basic) → SERVICE_TOKEN(Bearer) 로 교체.**
D93 이 만든 `MAINTQ_A2A_<PARTNER>_CLIENT_ID`/`_CLIENT_SECRET` → HTTP Basic 스킴은
**InsuQ·FinAllQ 가 실제로 쓰는 계약과 달랐다** — InsuQ 의 실 인증 필터
(`ServiceTokenFilter.java`)는 `Authorization: Bearer <token>` 한 값만 비교하고,
FinAllQ→InsuQ 2차 홉(`insuq_client.py`)이 이미 이 방식(`INSUQ_SERVICE_TOKEN`)으로 실제
E2E 성공을 냈다. Basic 스킴으로는 자격증명을 채워도 InsuQ 필터가 Bearer 헤더를 못 찾아
401 로 거부한다 — "미설정"이 아니라 "스킴 자체가 틀림"이었다. `env_names()`(튜플 2개)는
`env_name()`(단일 문자열)로 바뀌었고, `client_id`/`client_secret` 필드는 `token` 하나로
합쳐졌다 — 부분설정(`incomplete`) 상태도 값이 하나뿐이라 사라진다.

읽는 곳은 이 모듈 **한 곳**이다:

- **`.env` 를 여기서 읽지 않는다 — `os.environ` 만 본다.** dotenv 로딩은 D56 이
  `backend/main.py` 한 곳으로 못박았다. 두 곳에서 로드하면 "어느 파일의 값이 이겼는지" 를
  디버깅할 수 없다. OS 환경변수가 우선이고 `.env` 는 빈 곳만 채운다(`override=False`).
- **모듈 수준 캐시를 두지 않는다.** `load()` 는 호출할 때마다 `os.environ` 을 읽는다.
  첫 import 시점 값이 굳으면 env 를 갈아끼우며 상태를 검사하는 것이 원리적으로 불가능해지고,
  실운영에서도 "어느 값으로 돌았는지" 를 추적할 수 없다(D56 의 취지).
- **MCP 도구는 이 모듈을 보지 않는다** (D15 — MCP 서버는 별도 프로세스다).
  A2A 호출은 사람 승인 뒤 백엔드가 하는 일이다(절대규칙 1).
- **DB 를 열지 않는다.** 자격증명(actor)은 파트너 대장(subject)과 분리 보관한다 (D93).
- **실패를 예외로 던지지 않는다.** 미설정·미지 파트너 전부 `status` 로 돌려준다 (D9).

**토큰 캐시는 여기에 없다.** D93 이 "발급받은 액세스 토큰은 프로세스 메모리 캐시"라고 정했지만
지금은 **소비자가 없다**(정적 토큰이라 교환·만료 갱신 자체가 없다, D120) — 소비자 없는 코드는
회귀 부담만 늘린다(D56 이 OpenAI 클라이언트를 붙이지 않은 이유와 같다).

⛔ 비밀값은 어디로도 새지 않는다 — `repr`/`str` 은 길이(`token_len=N`)만 노출하고,
`status_report()` 는 상태 문자열만 담는다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Final

#: 자격증명을 둘 수 있는 파트너. 여기 없는 이름은 env 를 읽지도 않는다.
PARTNERS: Final[tuple[str, ...]] = ("finallq", "insuq")

#: 환경변수 접미어. 전체 이름은 `env_name()` 이 만든다 (`<PARTNER>_SERVICE_TOKEN`).
ENV_SUFFIX: Final[str] = "_SERVICE_TOKEN"

#: MaintQ 가 A2A 호출에서 자기 자신을 신고하는 식별자 (`X-A2A-Partner-Id`).
#: InsuQ `CustomerSeeder.java` 의 `PARTNER_ID_MAINTQ_AGENT` 시드값과 정확히 일치해야
#: partner_grant 조회가 통과한다 — 값이 다르면 401/403 이다. 시크릿이 아니라 고정
#: 식별자라 env 로 빼지 않는다(D80 — 필요 없는 유연성은 넣지 않는다).
SELF_PARTNER_ID: Final[str] = "maintq-agent"

__all__ = [
    "ENV_SUFFIX",
    "PARTNERS",
    "SELF_PARTNER_ID",
    "PartnerCredential",
    "env_name",
    "load",
    "status_report",
]


def env_name(partner: str) -> str:
    """'INSUQ_SERVICE_TOKEN'

    이름을 만들 뿐 파트너를 검증하지 않는다 — 검증은 `load()` 가 한다.
    """
    return f"{partner.strip().upper()}{ENV_SUFFIX}"


@dataclass(frozen=True, repr=False)
class PartnerCredential:
    """읽어온 자격증명 한 벌. `status` 가 결과이고 예외는 던지지 않는다 (D9).

    status:
      - `configured`      — 토큰이 있다. 이때만 `usable` 이 참이다
      - `not_configured`  — 토큰이 없다(공백뿐인 값 포함). 앱 기동·회귀·평가에 영향 없다
      - `unknown_partner` — `PARTNERS` 밖. env 를 읽지 않았다
    """

    partner: str
    status: str
    token: str = field(default="", repr=False)  # ⛔ repr 에 싣지 않는다

    @property
    def usable(self) -> bool:
        """호출에 쓸 수 있는가 — `configured` 일 때만 참."""
        return self.status == "configured"

    def __repr__(self) -> str:
        """값 대신 길이만 — 토큰 원문은 로그·에러메시지 어디에도 나오지 않는다."""
        return f"PartnerCredential(partner={self.partner!r}, status={self.status!r}, token_len={len(self.token)})"

    __str__ = __repr__


def load(partner: str) -> PartnerCredential:
    """`os.environ` 을 **매 호출** 읽어 파트너 자격증명을 만든다 (캐시 없음).

    미설정이어도 예외를 던지지 않는다 — `status='not_configured'` 로 돌려준다.
    """
    key = partner.strip().lower()
    if key not in PARTNERS:
        # env 를 읽지도 않는다 — 이름을 지어내 조회하면 오타가 조용히 통과한다
        return PartnerCredential(partner=key, status="unknown_partner")

    # `.env` 의 빈 값(`KEY=`)·공백뿐인 값은 미설정과 같게 취급한다 (D56 과 같은 근거)
    token = os.environ.get(env_name(key), "").strip()
    status = "configured" if token else "not_configured"

    return PartnerCredential(partner=key, status=status, token=token)


def status_report() -> dict[str, str]:
    """파트너별 상태 문자열만 — 값·길이·마스킹본 어느 것도 싣지 않는다."""
    return {partner: load(partner).status for partner in PARTNERS}
