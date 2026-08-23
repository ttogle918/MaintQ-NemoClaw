"""A2A(에이전트 간 연동) 패키지.

- credentials: 파트너 자격증명 읽기 층 (D93)
- auth_header: M1 Authorization 헤더 생성 (build_auth_header)
- payloads: request-withdrawal / lookup-clause 페이로드 조립 및 partner_links 조회
- client: call_skill() 공용 비동기 HTTP 호출부
"""

from backend.a2a.auth_header import build_auth_header
from backend.a2a.client import (
    A2AClientError,
    A2ATimeoutError,
    A2AUpstreamUnavailableError,
    call_skill,
)
from backend.a2a.credentials import PartnerCredential, load, status_report
from backend.a2a.payloads import (
    build_lookup_clause_payload,
    build_request_withdrawal_payload,
    get_finallq_company_id,
)

__all__ = [
    "A2AClientError",
    "A2ATimeoutError",
    "A2AUpstreamUnavailableError",
    "PartnerCredential",
    "build_auth_header",
    "build_lookup_clause_payload",
    "build_request_withdrawal_payload",
    "call_skill",
    "get_finallq_company_id",
    "load",
    "status_report",
]
