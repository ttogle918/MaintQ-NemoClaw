# 발주서 화면 직접 생성·수정 (P39 범위 축소판, P41 ② 선결과제) — 설계

**작성일**: 2026-08-21 · **브레인스토밍**: 같은 날 대화 · **상태**: 사용자 승인 완료

## 0. 배경 — 왜 필요한가

`docs/07_BACKLOG.md` P41("실제 서류 양식 기반 발주 결재 + 부서·권한 분리")의 ②("화면에서 직접 생성·수정")는 **P39 그 자체**다. P41은 단독 착수 불가 — P39 → P41 순서가 강제된다.

P39 원 요청(2026-08-17 브레인스토밍): *"발주서 양식은 정해져 있으니 화면에서 바로 채워서 만들 수 있어야 하고, 사람이 요청하기 전에 AI가 먼저 대령하는 건 부가 기능일 뿐이다. 생성된 초안은 전부 수정 가능해야 한다."*

지금은 정반대 구조다 — `create_po_draft`는 **MCP 도구로만** 존재(REST 경로 없음, 에이전트 채팅에서만 호출), 생성된 초안은 **불변 스냅샷**이다.

### 0-1. 범위 축소 — 발주서만

P39 원안은 발주서·처분서·수리증빙 3종을 다루지만, P41이 실제로 필요로 하는 건 발주서뿐이다. 처분서(룰엔진 판정 결과라 자유수정 개념 자체가 없음)·수리증빙까지 같이 가면 각각 "수정 가능한 초안이 어디까지 허용되는지" 별도 설계가 필요해 스코프가 크게 늘어난다. **이 스펙은 발주서(`po_drafts`)만 다룬다.** 처분서·수리증빙의 화면 직접 생성은 이 스펙이 닫지 않는다 — 필요해지면 이 설계의 패턴(데이터 계층 이관 + REST 두 엔드포인트)을 복제하면 된다.

## 1. 목표 / 비목표

**목표**: 정비사가 채팅을 거치지 않고 화면에서 발주 초안을 직접 만들고, `draft` 상태인 동안 수정할 수 있게 한다. 채팅 경로(`create_po_draft` MCP 도구)는 부가 기능으로 계속 남는다.

**비목표 (명시적 범위 밖)**:
- **처분서·수리증빙 화면 생성** — §0-1
- **P41 ①(실제 양식 확보)·③(부서 분리, 이미 완료 D108)·④(지연 발송)** — 이 스펙은 P41 ②만 닫는다
- **발주 2단계 결재·승인 한도 차등** — P9 자리, 이 스펙과 무관. 기존 `draft→pending→approved/rejected` 상태 머신·권한(D38)은 무변경
- **초안 삭제** — 요청에 없었다. `state='draft'`에서 더 못 쓰게 됐으면 반려 경로(submit 후 reject)로 흡수
- **동시 수정 충돌 처리(낙관적 락 등)** — 지금 다른 MaintQ 쓰기 경로 어디에도 없다. 새로 도입할 이유 없음(YAGNI)

## 2. 새 D-결정 후보 (번호는 구현 시점에 확정)

> 화면이 `po_drafts`를 **직접 생성**하는 첫 REST 경로(`POST /api/po`)를 연다. D18("승인은 채팅 밖 승인 큐 화면")·D29("에러 이력은 명시적 기록 API, 채팅 자동 기록 안 함")의 정신 — *레코드 상태 변경은 사람 전용 API를 지난다* — 은 그대로 지키되, 지금까지 "생성" 자체는 MCP 도구(채팅) 전용이었던 선례를 처음 깬다. 근거는 P39 요청 원문 그대로: AI가 먼저 초안을 대령하는 건 부가 기능이고, 주 경로는 사람이 화면에서 직접 만드는 것. 채팅 경로는 폐지하지 않고 병행 — 두 경로 모두 같은 `data/po_draft.py` 로직을 거치므로 결과물(검증 규칙·저장 형태)은 동일하다.

기각 대안: ① 채팅 경로만 유지하고 화면은 prefill로 우회(처분서 선례, `06_REPO_API.md §2.2`) — P39 요청이 명시적으로 거부한 방식이다("AI가 먼저 대령하는 건 부가 기능일 뿐") ② 화면 생성을 매니저도 허용 — 요청 시나리오("정비사가 만들고 팀장이 승인")와 맞지 않고 권한 모델을 불필요하게 넓힌다.

## 3. `data/po_draft.py` — 공유 산출 로직 계층

`data/maint_value.py`(D73·D101)와 같은 패턴 — `mcp_server`도 `backend`도 import하지 않는, 커넥션을 인자로 받는 순수 모듈(D15 유지, "두 프로세스는 코드를 공유하지 않는다"는 서로 import하지 않는다는 뜻이지 로직을 한 곳에 두지 말라는 뜻이 아니다).

```python
def next_po_id(con: sqlite3.Connection) -> str: ...

def validate_and_price(
    con: sqlite3.Connection, *,
    part_no: str, qty: int, supplier_id: str,
    model: str | None, error_code: str | None,
) -> dict:
    """단가·MOQ 조회(D31), 에러코드 FK 검증(D33). status 기반 반환(D9).
    성공 시 {"status": "ok", "unit_price": int, "moq": int}."""

def insert_draft(
    con: sqlite3.Connection, *,
    po_id: str, part_no: str, qty: int, supplier_id: str,
    model: str | None, error_code: str | None, evidence: dict | None,
    unit_price: int, reason: str, urgency: str,
    requested_by: str | None = None, session_id: str | None = None,
) -> None: ...
```

`mcp_server/tools/create_po_draft.py`는 이 세 함수를 `read_only()` + `draft_writer()` 두 커넥션으로 감싸는 얇은 래퍼로 축소된다(D10 트리거 경계 그대로 — MCP 커넥션은 여전히 INSERT 전용). **출력 dict는 한 글자도 안 바꾼다** — 순수 리팩터이지 기능 변경이 아니다(`data/maint_value.py` 도입 시와 같은 원칙).

기존 입력 검증(필수 파라미터·urgency enum·model/error_code 쌍 체크, D80)은 도구 파일에 그대로 남는다 — 이건 "산출 로직"이 아니라 스키마 경계 검증이라 공유 계층으로 옮길 이유가 없다. 백엔드 라우터는 Pydantic 모델로 같은 검증을 별도로 한다(FastAPI 관례, 중복이 아니라 각 진입점의 스키마 경계).

## 4. 백엔드 API

### `POST /api/po` (신규)

`require(c, "technician")`. Body: `part_no`·`qty`·`supplier_id`·`reason`·`urgency`(default `"normal"`)·`model?`·`error_code?`·`evidence?` — 지금 `create_po_draft` MCP 도구 입력과 동일 세트.

`requested_by = c.user_id`를 **생성 즉시** stamp한다. 채팅 경로처럼 "도구가 신원 없이 INSERT → 백엔드가 사후 `stamp_identity()`로 채운다"(D23·D37 우회 경로)는 2단계가 필요 없다 — 이 요청 자체가 이미 `X-User` 헤더를 통과한 신뢰된 백엔드 경로이기 때문이다(D52 태도: "role은 OAuth가 아니라 users 테이블/신뢰된 헤더가 정한다"). `session_id`는 NULL(채팅 세션이 없으므로) — 화면 B의 "실행 로그 전체 보기" 링크(`trace_url`)는 이 경로로 만든 발주에서는 자연히 빠진다(세션 자체가 없으니 지어낼 게 없다 — 정직한 결측).

단일 커넥션(`backend/db.connect()`)으로 `validate_and_price` → `insert_draft` 순서 호출. 실패 시 `data/po_draft.py`가 돌려주는 `status`를 그대로 HTTP 상태로 매핑(`not_found`→404, `error`(MOQ·미지코드 등)→422).

### `PATCH /api/po/{po_id}` (신규)

`require(c, "technician")` — **본인 요청 것만이 아니라 technician 역할이면 누구나** 수정 가능(현장 인원이 적어 동료가 대신 수정하는 것도 현실적이라는 사용자 판단, submit 권한과 같은 규칙). `state != 'draft'`면 `409`.

Body는 생성과 같은 필드 세트(부분 수정 허용 — 보낸 필드만 갱신). `part_no`·`supplier_id`·`qty`·`model`·`error_code` 중 하나라도 바뀌면 `validate_and_price`를 **재실행**해 `unit_price`를 다시 스냅샷한다(D31 정신 — 오래된 단가를 그대로 두지 않는다). `reason`·`urgency`·`evidence`만 바뀌면 재조회 없이 그대로 UPDATE.

기존 `GET /api/po`·`GET /api/po/{po_id}`·`submit`·`approve`·`reject`는 무변경.

## 5. 프론트엔드

- **`/technician/po/new`** — 빈 양식(부품·수량·공급사·사유·긴급도, 선택적으로 model/error_code). `?part_no=&qty=&equipment=` 쿼리로 prefill 지원. 제출 시 `POST /api/po` 호출 후 `/technician/po/{po_id}`로 이동
- **`/technician/po/[poId]`** — 상세+수정. `lib/queueState.ts`의 `isDraftState()`(기존 함수 재사용, D87 — 새 로컬 상수 안 만듦)로 분기: `draft`면 수정 폼 + "승인 요청" 버튼(`submitPo` 호출), 그 이상 상태면 읽기 전용 카드(매니저 상세 화면과 같은 정보 밀도, 컴포넌트는 별도 — 기술자 화면 톤이 다름)
- `frontend/components/asset/InventoryDrawer.tsx`의 "발주하러 가기"를 채팅 prefill(`prefillText` 기반 `/technician?prefill=...`)에서 `/technician/po/new?part_no=...&equipment=...`로 교체. 컴포넌트 주석의 "발주는 이 컴포넌트가 직접 만들지 않는다" 문구도 갱신 대상(더 이상 정확하지 않음)
- `lib/api.ts`에 `createPo(role, body)`·`updatePo(role, poId, body)` 추가(기존 `getPo`·`submitPo` 옆)

## 6. 회귀 영향

- `spikes/write_tool_contract.py` — 새 REST 생성 경로가 D10·D31·D33 규칙을 실제로 지키는지(예: `unit_price`가 body로 안 들어가는지, MOQ 미달 거부) 케이스 추가
- `spikes/api_contract.py` — 권한·전이 표에 `POST /api/po`·`PATCH /api/po/{po_id}` 행 추가(technician만 허용, manager는 403 등)
- `spikes/ui_honesty_contract.py` — `app/(console)/**/*.tsx` 글롭이 신규 `technician/po/new`·`technician/po/[poId]` 2파일을 자동 편입(L2 6건×2=12건 자연 증가, 코드 수정 불필요)
- 세 스위트 모두 **기존 파일 확장**으로 충분해 보인다 — 새 스파이크 파일 신설은 구현 단계에서 tool-builder/reviewer가 실제로 필요성이 확인되면 판단

## 7. 열린 질문 (구현 단계로 이관)

- D-결정 정식 번호는 구현 스테이지 1에서 `docs/10_DECISIONS.md` 등재 시 확정(현재 최신은 D110)
- `PATCH` 응답 바디가 `GET /api/po/{po_id}`와 동일 셰이프인지(재사용 가능성) — 구현 시 `_row_to_po` 공유로 자연히 해소될 가능성 높음, 별도 설계 불필요
