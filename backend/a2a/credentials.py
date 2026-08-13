"""파트너 자격증명 읽기 층 (D93).

`MAINTQ_A2A_<PARTNER>_CLIENT_ID` / `..._CLIENT_SECRET` 를 **읽기만** 한다.
파트너 자격증명은 이 레포의 **세 번째 갈래**다 — 수집 스크립트 키가 아니고(런타임에 읽는다),
LLM 키와도 다르다(이 자격증명으로 나가는 요청은 돈을 움직인다, S5).

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
- **실패를 예외로 던지지 않는다.** 미설정·부분설정·미지 파트너 전부 `status` 로 돌려준다 (D9).

**토큰 캐시는 여기에 없다.** D93 이 "발급받은 액세스 토큰은 프로세스 메모리 캐시"라고 정했지만
지금은 **소비자가 없다** — 소비자 없는 코드는 회귀 부담만 늘린다(D56 이 OpenAI 클라이언트를
붙이지 않은 이유와 같다). **토큰 캐시는 A2A 호출부가 생기는 스프린트가 만든다.**

⛔ 비밀값은 어디로도 새지 않는다 — `repr`/`str` 은 길이(`secret_len=N`)만 노출하고,
`status_report()` 는 상태 문자열만 담는다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Final

#: 자격증명을 둘 수 있는 파트너. 여기 없는 이름은 env 를 읽지도 않는다.
PARTNERS: Final[tuple[str, ...]] = ("finallq", "insuq")

#: 환경변수 접두어. 전체 이름은 `env_names()` 가 만든다.
ENV_PREFIX: Final[str] = "MAINTQ_A2A_"

__all__ = ["ENV_PREFIX", "PARTNERS", "PartnerCredential", "env_names", "load", "status_report"]


def env_names(partner: str) -> tuple[str, str]:
    """('MAINTQ_A2A_FINALLQ_CLIENT_ID', 'MAINTQ_A2A_FINALLQ_CLIENT_SECRET')

    이름을 만들 뿐 파트너를 검증하지 않는다 — 검증은 `load()` 가 한다.
    """
    base = f"{ENV_PREFIX}{partner.strip().upper()}_CLIENT_"
    return (f"{base}ID", f"{base}SECRET")


@dataclass(frozen=True, repr=False)
class PartnerCredential:
    """읽어온 자격증명 한 벌. `status` 가 결과이고 예외는 던지지 않는다 (D9).

    status:
      - `configured`      — id·secret 둘 다 있다. 이때만 `usable` 이 참이다
      - `incomplete`      — 한쪽만 있다. **부분값으로 호출을 시도하지 않는다**
      - `not_configured`  — 둘 다 없다(공백뿐인 값 포함). 앱 기동·회귀·평가에 영향 없다
      - `unknown_partner` — `PARTNERS` 밖. env 를 읽지 않았다
    """

    partner: str
    status: str
    client_id: str = ""
    client_secret: str = field(default="", repr=False)  # ⛔ repr 에 싣지 않는다

    @property
    def usable(self) -> bool:
        """호출에 쓸 수 있는가 — `configured` 일 때만 참."""
        return self.status == "configured"

    def __repr__(self) -> str:
        """값 대신 길이만 — secret 원문은 로그·에러메시지 어디에도 나오지 않는다."""
        return (
            f"PartnerCredential(partner={self.partner!r}, status={self.status!r}, "
            f"client_id={self.client_id!r}, secret_len={len(self.client_secret)})"
        )

    __str__ = __repr__


def load(partner: str) -> PartnerCredential:
    """`os.environ` 을 **매 호출** 읽어 파트너 자격증명을 만든다 (캐시 없음).

    미설정이어도 예외를 던지지 않는다 — `status='not_configured'` 로 돌려준다.
    """
    key = partner.strip().lower()
    if key not in PARTNERS:
        # env 를 읽지도 않는다 — 이름을 지어내 조회하면 오타가 조용히 통과한다
        return PartnerCredential(partner=key, status="unknown_partner")

    id_name, secret_name = env_names(key)
    # `.env` 의 빈 값(`KEY=`)·공백뿐인 값은 미설정과 같게 취급한다 (D56 과 같은 근거)
    client_id = os.environ.get(id_name, "").strip()
    client_secret = os.environ.get(secret_name, "").strip()

    if client_id and client_secret:
        status = "configured"
    elif client_id or client_secret:
        status = "incomplete"  # ⛔ 한쪽만으로 호출을 시도할 수 있는 상태를 만들지 않는다
    else:
        status = "not_configured"

    return PartnerCredential(
        partner=key,
        status=status,
        client_id=client_id,
        client_secret=client_secret,
    )


def status_report() -> dict[str, str]:
    """파트너별 상태 문자열만 — 값·길이·마스킹본 어느 것도 싣지 않는다."""
    return {partner: load(partner).status for partner in PARTNERS}
