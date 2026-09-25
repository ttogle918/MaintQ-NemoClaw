# 레포 구조 & API 설계 v0.2

> ⚠️ 이 문서는 이 레포의 **내부** API만 다룬다. FinAllQ·InsuQ와의 A2A 연동은
> `docs/A2A_CONTRACTS.md`를 보라 — 아직 M1(계약 계층) 초안 단계.
> 단, `/api/a2a/*` 는 이 레포 **내부** REST 표면(라우터 `backend/routers/a2a.py`)이다 — 외부
> 스킬 스키마 자체는 여전히 `A2A_CONTRACTS.md`/A2A_Q 레포가 정본이다.

## 0. 전체 아키텍처

```
[정비사 UI]──┐
[팀장 UI]  ──┤→ [FastAPI 백엔드] → [Agent Loop (LLM)] → [MCP 서버] → [SQLite 목업 DB]
             │        │                                      │
             │        └── SSE 스트림 (token/tool_call/       └── [벡터스토어 (매뉴얼 RAG)]
             │             tool_result/block — D14·D22)
```

설계 원칙: **MCP 서버와 백엔드를 프로세스 분리.** 목업 DB를 실제 ERP로 갈아끼울 때 MCP 서버만 교체하면 되는 구조 = "실전 연동 가능성" 어필 포인트.

---

## 1. 레포 구조 (모노레포)

```
MaintQ/
├── README.md                  # 데모 GIF + 아키텍처 + 평가 결과 (첫 화면)
├── CLAUDE.md                  # 프로젝트 메모리 (절대 규칙·컨벤션)
├── TODO_직접할일.md            # 사람 손 필요한 일
├── pyproject.toml             # uv 프로젝트 정의 + 의존성 (D27)
├── uv.lock                    # 재현 가능한 의존성 잠금 (D27)
├── .python-version            # Python 버전 고정 (D27)
├── .gitignore                 # data/raw/*(manifest.json 제외)·*.db·.env·.venv
│                              #   예외: data/raw/external/(응답 JSON + README.md 는 git 추적 — D103,
│                              #   CLAUDE.md 절대규칙 5 예외 ㉠). 캐시 중간 산물(임시 PDF 조각)은 계속 제외
├── .claude/
│   ├── commands/              # /sprint · /stage · /done · /checkpoint
│   ├── skills/                # 도메인 5종 + 워크플로우 3종(sprint·stage·done)
│   ├── agents/                # pm · tool-builder · reviewer · eval-runner · data-extractor
│   └── hooks/                 # 쓰기 가드 · ruff 포맷
├── docs/
│   ├── README.md, 00_MVP_SCOPE.md, 01_OVERVIEW ~ 10_DECISIONS.md   # 문서 지도는 README 참조
│   ├── sprints/               # /sprint·/stage 산출물 (실행 기록)
│   ├── sessions/              # /done 세션 로그 (결정의 맥락)
│   └── (평가 결과 문서는 M4에서 eval/results/ 기반으로 추가)
│
├── data/
│   ├── raw/                   # 매뉴얼 PDF 원본 (git 제외) + manifest.json (출처·버전·해시 대장, D19 — git 포함)
│   ├── extracted/             # error_codes.json (표 추출 결과) + ig5a_code_map.json (비트명↔한글명 매핑, D24)
│   ├── analysis/              # manual_eda.md (EDA 산출물) + ig5a_code_mapping.md (사람 검수표)
│   ├── extract_error_codes.py # 표 추출 파이프라인 (멱등 재실행, manifest 해시 검증 — D19)
│   ├── seed.py                # 목업 DB 시드 (케이스 맵 구현)
│   ├── rules/                 # ★ 근거 계층 — 두 프로세스가 공유해도 되는 데이터 계층 (D73)
│   │   ├── laws/*.json        #   계층 1 법령 스냅샷 (파일이 정본, append-only — D60)
│   │   ├── rules/*.json       #   계층 2 해석 룰 (처분 플래그 전용, disposal_type 필수)
│   │   ├── pending_revisions/ #   개정본 대기 (applied: null|intent|confirmed — D75)
│   │   ├── engine.py          #   룰 엔진 (build_facts·evaluate_rule·check_disposal_blockers)
│   │   ├── fetch_laws.py      #   법령 수집기 (수집 fetch_from_api + 적용 apply_fetch 분리 — 둘 다 완료.
│   │   │                      #   `_store_payload` 가 응답 payload 를 store.py 로 소급 보관 — D103·MQ-1305)
│   │   └── test_rules.py      #   pytest — 발화 가능성·해제 가능성 회귀 (D77·D78)
│   ├── external/               # Sprint 13 신설 — 외부 API 응답 원본 보관 규약 (D103)
│   │   ├── store.py           #   보관 모듈 — 유일한 기입 경로. 봉투·메타 allowlist·내용 주소 멱등
│   │   ├── elice_docvision.py #   Elice DocVision 클라이언트 (D105) — 캐시 우선, 지출 전 예외
│   │   └── test_elice_docvision.py  # pytest — 지출 가드 13건 (네트워크 전 방어선)
│   ├── verify_actions_absence.py    # `actions` 결측 34건 3자 대조 엔진 (파서·Elice·정본, D99 게이트 통과)
│   └── analysis/residual_curve.md  # 잔가곡선 산출 근거 + 호가 데이터 한계 실증 (D72→D74)
│
├── mcp_server/
│   ├── server.py              # MCP 엔트리포인트 (MAINTQ_TOOLS_PROFILE=core|full 게이트 — D69)
│   ├── tools/                 # 도구 (파일당 1도구)
│   │   ├── lookup_error_code.py          ┐
│   │   ├── rag_search_manual.py          │
│   │   ├── get_error_history.py          │ 코어 7종 (프로파일 무관, 항상 등록)
│   │   ├── search_inventory.py           │
│   │   ├── find_alternative_parts.py     │
│   │   ├── get_supplier_quotes.py        │
│   │   ├── create_po_draft.py            ┘ ← 쓰기 도구 ①/3 — po_drafts draft INSERT (D10)
│   │   ├── check_disposal_blockers.py    ┐
│   │   ├── verify_ownership.py           │
│   │   ├── classify_part_criticality.py  │ 확장 13종 (`full` 에서만 등록 — D69)
│   │   ├── get_maintenance_metrics.py    │ 대상은 asset_id (D68)
│   │   ├── classify_expenditure.py       │
│   │   ├── assess_repair_value.py        │
│   │   ├── build_evidence_bundle.py      │ ← 읽기 전용. 저장하지 않는다
│   │   ├── generate_disposal_document.py │ ← 쓰기 도구 ②/3 (decisions draft INSERT, D81)
│   │   ├── create_repair_record.py       ┘ ← 쓰기 도구 ③/3 (repair_records draft INSERT, D98.
│   │   │                                     equipment_id 를 직접 받는 유일한 예외 — D68 ⓑ)
│   │   └── _asset_ref.py                 # §8·§14·§15 공용 자산 참조·인자 검증 (도구 아님)
│   └── db.py                  # read_only / draft_writer(po_drafts) / decision_writer(decisions)
│                              #   / repair_writer(repair_records, D98)
│                              #   — 쓰기 커넥션은 대상 테이블별로 분리한다. TEMP TRIGGER 가
│                              #     UPDATE/DELETE 를 거부하므로 커넥션을 섞으면 잠금이 사라진다
│
├── backend/
│   ├── main.py                # FastAPI 앱
│   ├── sse.py                 # SSE 이벤트 4종 인코더 (D14·D22, citation 오프셋 변환 D32)
│   ├── db.py                  # 백엔드 DB 커넥션 (mcp_server 와 코드 공유 안 함 — D15)
│   ├── deps.py                # X-Role/X-User 파싱 + 403 강제
│   ├── services/
│   │   ├── po.py              # 신원 stamp(D37) · 상태 전이 · 표시명 매핑(D36)
│   │   ├── disposal.py        # 자산 조회 + 처분 사전판정 (data.rules.engine 직접 사용 — D73)
│   │   ├── ownership.py       # 소유권 실사 (REST==MCP 바이트 대조 대상)
│   │   ├── decisions.py       # 처분 결정 전이 — submit·sign(번들 재산출·해시 대조 D84)·reject
│   │   ├── repairs.py         # 수리 증빙 전이 — submit·sign(해시 재대조)·reject (D98, Sprint 9)
│   │   ├── maint_value.py     # data.maint_value 위임 REST 5종 (D101, §2.5)
│   │   └── approvals.py       # 통합 승인 큐 조립 (KINDS = po|disposal|repair — D85)
│   ├── agent/
│   │   ├── loop.py            # 에이전트 루프 (도구 호출 오케스트레이션)
│   │   ├── prompts.py         # 시스템 프롬프트 (안전 가드레일 규칙 포함)
│   │   └── trace.py           # trace 이벤트 발행
│   ├── routers/
│   │   ├── chat.py            # 대화 (SSE)
│   │   ├── po.py              # 발주 승인 워크플로우 — **형태 불변이 계약이다** (D85)
│   │   ├── equipment.py       # 라인/장비 컨텍스트
│   │   ├── disposal.py        # /api/assets — 목록·상세·소유권·처분 사전판정 (D71 HTTP 매핑)
│   │   ├── decisions.py       # /api/decisions — 상세·제출·서명·반려 (§2.6)
│   │   ├── repairs.py         # /api/repairs — 상세·제출·서명·반려 (§2.8, D98)
│   │   ├── maint_value.py     # /api/assets/{id}/metrics 등 확장 REST 5종 (§2.5, D101)
│   │   └── approvals.py       # /api/approvals — 통합 승인 큐, **읽기 전용** (§2.7)
│   ├── rag/
│   │   ├── ingest.py          # 매뉴얼 청킹·임베딩 (model 메타데이터 부착)
│   │   └── retriever.py
│   └── a2a/                   # 파트너 자격증명 읽기 (D93). MCP 는 참조하지 않는다 (D15)
│
├── frontend/                  # 화면 A(진단 콘솔) + 화면 B(승인 큐)
│
├── spikes/                    # 개발 전 기술 검증 (09_RUNTIME §4) — 회귀 테스트로 유지
│   │                          # **32종** (실측 `ls spikes/*.py`). 전체 목록은 CLAUDE.md 회귀 절
│   ├── sp2_mcp_roundtrip.py   # MCP stdio 왕복 · status 반환 · D10 쓰기 격리
│   ├── sp3_sse_events.py      # SSE 이벤트 4종 · block 중간 삽입 · A1 순서
│   ├── write_tool_contract.py # 쓰기 도구 **3종** 경계 (D10·D23·D31·D33·D34·D37·D63·D80·D81·D84·D98)
│   ├── api_contract.py        # 권한 403 · 전이 409 · D29 이력 기록 — /api/po 형태 고정 (D85)
│   ├── bundle_integrity.py    # 번들 5키 · rule_hash · N1·N2 · 두 도구 실패 어휘 대조
│   ├── approvals_contract.py  # 통합 큐 (D85) · BLOCKING 우회 0건 · 서명 없는 확정 0건
│   ├── disposal_sign_contract.py  # 27조합 전수 — 4층 방어선이 각각 독립으로 막는가
│   ├── s10_smoke.py           # 실 서버·실 MCP 로 S9→S10 관통
│   ├── ui_honesty_contract.py # D87 — 미확인 상태가 "확인됨"으로 렌더되지 않는가
│   ├── a2a_identity_contract.py # D91~D96 — partner_links CHECK · request_chain_id "쓰는 쪽 없음" · 자격증명 격리
│   ├── repair_flow_contract.py  # D98 — create_repair_record draft INSERT · /api/repairs 403/409/422 경계
│   └── external_store_contract.py # D103·D105 — store.py 왕복·메타 allowlist·.gitignore 3종·대조 매트릭스 오라클
│
├── eval/
│   ├── testset.json           # 에러코드 20개 + 기대 부품/분기
│   ├── run_eval.py            # 자동 실행 → 정확률·인용률·안전경고 검사
│   └── results/
│
└── .env.example
```

**포인트:** `eval/`과 `docs/`가 1급 시민. "만들었다"가 아니라 "설계했고 검증했다"를 폴더 구조가 말하게 함.

---

## 2. API 설계 (백엔드 REST)

인증은 목업 수준으로 단순화하되, 권한 검사 로직은 실제로 구현:
- `X-Role: technician | manager` — 권한 검사 (403 규칙)
- `X-User: tech-01` — 신원 (D23). `requested_by`/`decided_by`는 백엔드가 이 헤더에서 **서버 측 주입** — 도구 파라미터로 받지 않으므로 LLM이 신원을 위조할 경로가 없음

> ⚠️ **`X-User`는 ASCII 사용자 ID다 (D36).** `X-User: 김OO` 처럼 한글 표시명을 넣으면
> HTTP 헤더 값이 ASCII(latin-1) 범위라 httpx·브라우저 `fetch` 양쪽에서 거부된다 (SP3에서 확인).
> DB에는 ID를 저장하고, 화면 표시명은 서버가 매핑한다.

| 사용자 ID | 역할 | 소속 | 표시명 |
|---|---|---|---|
| `tech-01` | technician | maintenance | 정비사 김OO |
| `tech-02` | technician | maintenance | 정비사 이OO |
| `mgr-01` | manager | maintenance | 보전팀장 박OO |
| `mgr-02` | manager | finance | 재무 담당 최OO |

> 🔴 **`department`(소속)는 헤더에 없다 (D108).** `X-Dept` 같은 헤더를 두지 않는다 — 있으면
> 클라이언트가 자기 부서를 자칭할 수 있다. **서버가 `users.department` 를 `X-User` 로 조회해
> 주입**한다. 그 값을 클라이언트가 읽는 경로는 `GET /api/whoami` 뿐이다 — 아래 §2.0-b.
> ⚠ **`department` 는 권한이 아니다** — 위 표의 `mgr-02`(재무)도 `role` 은 `manager` 라서
> 지금 발주·처분·수리 승인 게이트(`require()`)에 아무 영향이 없다. 승인 자격은 여전히
> `role` 하나로만 결정된다.

### 2.0-b 신원 조회

```
GET /api/whoami                      # {role, user_id, department} — 판정 없음, Caller 값 그대로 반환
                                     #   department 는 X-User 로 서버가 조회한 값 (D108)
```

> **시각 규약 (D39):** DB 저장·API 전송은 **UTC**, 표시만 클라이언트가 로컬로 변환한다.
> API 는 타임존을 명시한 ISO-8601(`2026-07-23T04:51:44Z`)로 내보낸다 — 표기 없는 naive 문자열을
> 보내면 브라우저가 로컬로 해석해 어긋난다(KST 기준 9시간).

### 2.1 대화

```
POST /api/chat
  body: { session_id, message, equipment_id }   # equipment_id는 nullable —
  → SSE 스트림, 이벤트 4종 (D14·D22):          #   미선택 시 에이전트가 모델 확인 질문 (S1 1단계)
     event: token       { text }                 # LLM 응답 토큰
     event: tool_call   { tool, input, ts }      # trace 패널용 (호출 시점)
     event: tool_result { tool, status, summary, elapsed, pages?, parts?, a2a_chain_id? }  # trace 패널용 (완료)
                        # a2a_chain_id = search_insurance_clause·assess_equipment_loan(§04 §19·§20)
                        #   결과에서만 채워지는 선택 필드 (D113, Sprint 16). 나머지 도구는 이 키 자체가
                        #   없다(D30 — payload 바이트 무변화). 채팅 화면은 이 값으로 GET /api/a2a/history
                        #   (§2.9, D114)를 찾아가 InsuQ/FinAllQ 응답 원문을 연다.
                        # pages = 이 결과가 근거로 삼을 수 있는 **PDF 물리 페이지 목록** (D54).
                        #   실 루프는 항상 싣는다(근거 없는 도구·실패 결과는 빈 리스트) —
                        #   인용률 strict 판정(아래 §지표)의 근거 소스. 재생·구 trace 는 키 없음.
                        # elapsed = **호출자(에이전트 루프) 관측 벽시계 초, 타임아웃 대기 포함**.
                        #   도구 내부 실행시간이 아니다 — 화면이 합산해 "총 Ns"로 쓰므로
                        #   사용자가 실제로 기다린 시간이어야 한다. 측정 지점은 loop.py 한 곳.
                        # summary 의 `✗ timeout ·` 접두는 **백엔드가 붙인다** (D44·D46).
                        #   traces 는 평가 판정 소스라(D21·D30) 저장값이 자기설명적이어야 하고,
                        #   payload 에 reason 필드가 없어 프론트는 판별할 수단도 없다
     event: block       { type: "safety" | "po_card" | "citation", data }
                        # 구조화 블록 (D22) — 안전 경고·발주 카드·인용 칩을 전용 컴포넌트로 렌더.
                        # 스트리밍 "중간"에 삽입 가능 — 위험 절차 서술보다 경고가 먼저/함께 도착해야 함
                        # po_card의 data = { variant: "draft" | "hold", ... } (D35)
                        #   draft : 발주서 초안 카드 — 정비사는 "승인 요청"만 (D10·D18)
                        #   hold  : S3 발주 보류 블록 — 원인 확정 전 발주 금지. 발주 카드가 아님
                        #   같은 슬롯에 오는 같은 성격의 블록이라 타입을 늘리지 않고 variant로 구분
                        #   (이벤트 4종 고정 유지 — D14·D22)
                        # citation의 data = { page, print_page, label } (D32)
                        #   page       : PDF 물리 페이지 — 저장·평가 검증의 단일 기준 (D26 불변)
                        #   print_page : manifest.print_page_offset 적용값 (iG5A 0, S100 16)
                        #   label      : 표시용 문자열. "iG5A 매뉴얼 p.202" / "S100 매뉴얼 p.400 (PDF p.416)"
                        #   오프셋 변환은 이 렌더 지점 1곳에서만 — 평가 코드는 page만 본다
```

**설계 결정:** 응답과 trace를 같은 SSE 채널의 다른 이벤트 타입으로 — 화면 A의 채팅/trace 패널이 스트림 하나로 동기화됨. 모든 tool_call/tool_result/block 이벤트는 `traces` 테이블에도 영속 저장 (D21). 재생(`?replay=…`)이 발행·저장하는 **`TraceWriter` 경유 3종(tool_call/tool_result/block)** payload 에는 `replay: true` 표식이 붙는다 (D55) — 합성 행이 실 도구 결과와 구분 불가능하면 실적 판정이 오염되기 때문. `token` 은 저장 대상이 아니라(D41) 표식도 없다. SSE `data` 와 저장 payload 는 표식 포함 그대로 바이트 동일 (D30).

```
GET /api/chat/{session_id}/trace     # trace 전체 조회 — traces 테이블 읽기 (화면 B "실행 로그 보기" 링크, SSE 끊김 폴백)
```

#### 처분서 초안 요청 경로 — **요청은 prefill, 제출은 자산 화면** (MQ-711 착지)

`generate_disposal_document`(`04 §15`)는 **에이전트만** 부를 수 있다(D15·D10). 그래서 자산 화면의
"이 자산의 처분서 초안" 버튼은 **신규 API 를 만들지 않는다** — `/technician?prefill=…&equipment=…` 로
이동해 채팅 컴포저에 문장을 채워 넣고 **전송은 사용자가** 누른다(자동 전송 금지 — 사람이 무엇을
요청하는지 보고 눌러야 한다). **신규 API 0 · 신규 SSE 소비 0.**

> ⚠ **`decision_card` block 은 만들지 않았다.** block 은 `safety` · `po_card` · `citation` **3종 고정**이
> 계약이다(D14·D22 — 이벤트 4종 고정과 같은 층위). 초안 생성 결과를 채팅에서 전용 카드로 렌더하려면
> 4번째 block 타입이 필요한데, 그건 계약 변경이다.
> **대신 `draft → pending` 구간을 자산 화면이 메운다** — 초안 생성 후 자산 화면의 "이 자산의 처분서 초안"
> 목록에서 `submitDecision`(`POST /api/decisions/{id}/submit`)을 누른다.
> 즉 **요청은 채팅(prefill), 제출은 자산 화면**이다. 이 분업은 D18("승인 큐 진입은 채팅 밖")과
> D29("이력 기록은 명시적 액션")를 그대로 따른다.

### 2.2 발주 워크플로우 (상태 전이 = 권한)

```
GET  /api/po?state=pending           # 승인 큐 (manager)
GET  /api/po/{po_id}                 # 상세: reason(한 줄 요약) + evidence(관찰 현상·근거·비고, D34)
                                     #     + model/error_code(D33) + trace 링크(session_id → /trace) + 공급사 비교
                                     # evidence.basis[] 의 각 항목은 `manual_page`(PDF 물리, D26 불변)
                                     #   + 선택적 `print_page`(인쇄 페이지, D57) — model·manual_page 가
                                     #   둘 다 유효할 때만 응답 조립 시점에 계산해 붙는다(저장 안 함).
                                     #   model 미확정(에러코드 승인 전 등)이면 필드가 아예 없다 — 화면은
                                     #   그때 "PDF p." 로 정직하게 병기한다(W-6 표시측, Stage 1)
GET  /api/po/quotes/{part_no}        # 부품 견적 사전 조회 (technician) — 화면이 발주 초안을
                                     #   만들기 전 공급사를 고르는 용도(D111). 견적 없으면 빈 배열(404 아님, D62)
POST /api/po                         # 화면 직접 생성 (technician만, D111 — P39 축소판, 발주서만).
                                     #   응답은 GET /api/po/{po_id} 와 같은 상세 셰이프. 검증 실패는
                                     #   404(no_quote)·422(invalid_input 등) — create_po_draft(MCP)와 동일 규칙
PATCH /api/po/{po_id}                # draft 상태에서만 수정 (technician만, 요청자 본인 아니어도 가능, D111).
                                     #   draft 아니면 409
POST /api/po/{po_id}/submit          # draft → pending   (technician만)
POST /api/po/{po_id}/approve         # pending → approved (manager만)
POST /api/po/{po_id}/reject          # pending → rejected (manager만, body: {reason} — 필수, D38)
POST /api/po/{po_id}/finance-approve # approved → finance_approved (재무부 manager 전용, D119)
                                     #   승인 직후 FinAllQ 출금 요청(S5) 전송 — approve() 자리에서 이동
POST /api/po/{po_id}/finance-reject  # approved → finance_rejected (재무부 manager 전용, body: {reason})
```

**403 규칙:** technician이 approve 호출 → 403. 이 테스트 케이스를 eval에 포함 (human-in-the-loop 증명).
역할 분리는 **양방향**이다 — manager가 submit을 호출해도 403.

**403 vs 409:** 권한이 없으면 403, 권한은 맞지만 현재 상태에서 할 수 없는 전이면 **409** (D38).
둘을 섞으면 "권한 위반 차단 100%" 지표가 순서 오류까지 세게 된다.
반려 사유 누락은 요청 본문 검증이라 422.

### 2.3 컨텍스트

```
GET  /api/equipment                  # 라인/장비 목록 (헤더 선택기 데이터)
                                     # 응답 항목: {equipment_id, line_id, model, installed_at, location,
                                     #             asset_id}
                                     #   asset_id 는 **nullable 가산 필드** (D68) — 이 인버터가 어느
                                     #   호스트 설비에 속하는지. NULL 이면 호스트 자산이 없다는 뜻이며
                                     #   (INV-L1-01 분전반), 확장 도구는 이 경우 no_host_asset 을 낸다.
                                     #   기존 6종 도구·화면의 계약은 무변경 — 가산일 뿐이다
GET  /api/equipment/{id}/history     # 장비별 에러 이력 (이력 탭)
POST /api/equipment/{id}/errors      # 에러 발생 이력 기록 (D29) — body: {code, occurred_at?, action_taken?, part_replaced?}
                                     #   error_history INSERT. technician만. requested 주체는 X-User에서 주입
```

**D29 — 이력 기록은 명시적 액션이다.** 채팅 진입 시 자동 기록하지 않는다. 자동 기록하면 `get_error_history`의 `count`가 실제 고장 횟수가 아니라 **질문 횟수**가 되어, 같은 에러를 세 번 물어본 것만으로 `repeated=true`(S3 근본원인 모드)가 잘못 켜진다. 화면 A에 "이 고장 이력에 기록" 액션이 필요하다 — 와이어프레임 반영 대상.
MCP 도구가 아니라 백엔드 쓰기이므로 D10("도구는 po_drafts draft INSERT만")은 그대로 유지된다.

### 2.5 자산 · 처분 사전판정 (확장 범위 — S9)

```
GET  /api/assets                     # 자산 목록. query: line_id? · status?
                                     #   각 항목에 equipment_count 가산. 모르는 status 는 0건
                                     #   (허용값은 스키마 CHECK 가 정본 — 코드에 사본을 만들지 않는다)
GET  /api/assets/{asset_id}          # 자산 상세 + 하위 equipment 목록 (D68 — 처분의 단위는 호스트 설비)
POST /api/assets/{asset_id}/disposal/precheck
                                     # 처분 사전판정 — **아무것도 저장하지 않는다** (D71)
                                     #   body: { disposal_mode: "SALE"|"SCRAP"|"TRANSFER",
                                     #           disposal_date: "2026-09-01" | null }
```

**경로 이름이 `/disposal` 이 아닌 이유**: 이 POST 는 `decisions`·`flags` 를 건드리지 않는다.
저장하지 않는 POST 를 `/disposal` 로 부르면 **계약이 거짓말이 된다.** 처분 요청 생성·서명은 별도 경로다(Sprint 7).

**응답 본문** (200·409 **같은 형태**, 409 만 `detail` 한 줄이 더 붙는다):

```
asset_id · asset_name · disposal_mode · disposal_date · evaluated_at(판정 기준일) ·
generated_at(응답 시각, UTC ISO-8601 — D39) · verdict ·
blockers[] · preconditions[] · holds[] · insufficient[] ·
checklist[] · resolve_options[] · missing_facts[] · facts_used{} ·
not_considered[] · disclaimer · note      (+ 409 일 때만 detail)
```

> #### ⚠ **`evidence_completeness` 는 이 응답에 없다** (실측 · MQ-712 기록)
>
> `backend/services/disposal.precheck()` 의 반환 dict(`disposal.py:319-343`)에 그 키가 없다.
> **이 값을 내는 것은 MCP 도구 `check_disposal_blockers` 뿐이다**(`check_disposal_blockers.py:171`).
> 프론트는 이 사실을 알고 **없을 때 조용히 넘기지 않고** "근거 수집 상태 미제공" 으로 표시한다
> (`frontend/lib/decisionView.ts:268-277`) — 숨기면 사용자가 근거 상태를 모른 채 판정만 읽는다.
> ⛔ 없는 값을 `COMPLETE` 로 채우지 않는다.
>
> **키를 추가하려면 산식을 공유 계층에 올려야 한다.** `check_disposal_blockers._evidence_completeness`
> 를 `services/disposal.py` 에 **복제하면** Sprint 7 이 계속 잡아온 드리프트를 그대로 재생산한다 —
> W5(판정이 본 조문 ≠ 해시한 조문)·W2(엔진 문구 복제본)가 전부 같은 병이었고, 그때 답은 항상
> **`data.rules.engine` 단일 출처**(D73)였다. 즉 추가한다면 산식을 엔진에 올리고 MCP·REST 양쪽이
> 그것을 부르는 형태여야 하며, 그건 **엔진 계약 변경**이므로 이 태스크 범위 밖이다.
> 지금 상태의 정직성은 이미 확보돼 있다(프론트가 부재를 표시한다).

409 본문을 200 과 같은 형태로 주는 이유: 클라이언트가 **차단 시에도** blockers·holds·insufficient·
resolve_options 를 그대로 렌더할 수 있어야 한다. "안 됩니다"로 끝내지 않는 건 S4(미지 코드 → A/S 안내)와 같은 태도다.

#### HTTP 매핑 (D71)

| 상황 | HTTP | 근거 |
|---|---|---|
| `verdict: BLOCKED` | **409** | 차단 사유를 해소하거나 override(서명·사유 필수) |
| `verdict: HOLD` | **409** | 경계 구간 — 전문가 검토가 필요 |
| `verdict: INSUFFICIENT_FACTS` | **409** | 누락된 사실을 입력해야 판정이 성립 |
| `verdict: CONDITIONAL` · `CLEAR` | **200** | 체크리스트 이행 후 진행 |
| 룰 카탈로그 미적재 | **503** | 서버 **설정** 문제 — 클라이언트가 할 행동(재시도·관리자 문의)이 일반 500 과 다르다 |
| 없는 `asset_id` | **404** | — |
| `disposal_mode` enum 밖 · `disposal_date` 판독 불가 | **422** | 요청 본문 검증 (반려 사유 누락이 422 인 것과 같은 층위) |

- **`HOLD`·`INSUFFICIENT_FACTS` 를 200 으로 주지 않는 이유**: 클라이언트는 200 을 "진행 가능"으로 읽는다. 그러면 D62("알 수 없다 ≠ 통과")가 **API 경계에서 무너진다** — 엔진이 애써 구분해 둔 셋이 HTTP 한 칸에서 뭉개진다.
- **셋을 HTTP 로 나누지 않는 이유**: 셋 다 "지금 상태로는 처분 불가"라 409 가 맞다. 구분은 본문 `verdict` 가 한다 — **HTTP 코드는 행동 유형을, 본문은 사유를 말한다.**
- 매핑표는 코드에서 `set(HTTP_BY_VERDICT) == set(engine.VERDICTS)` 로 **기동 시점에 검증**한다. 새 verdict 가 생겼는데 매핑을 빠뜨리면 런타임 KeyError(500)로 늦게 발견된다.

#### ⚠ precheck 에는 역할 게이트가 없다 (403 이 나오지 않는다)

`require()` 를 호출하지 않는다. **읽기 판정에 403 을 만들면 "권한 위반 403 차단 100%" 지표에
법정 조건 미충족이 섞인다** — D38 이 403(권한)과 409(상태)를 나눈 바로 그 이유다.
처분을 실제로 **확정**하는 경로(제출·서명·반려)에는 역할 게이트가 붙는다 → **§2.6 에서 구현됐다**.
`GET /api/assets/{id}/ownership` 도 같은 이유로 403 이 없다(`spikes/ownership_api_contract.py` 10건이 확인).

#### `core` 프로파일에서도 살아 있다 (D73)

이 엔드포인트는 MCP 도구를 호출하지 않고 `data.rules.engine` 을 직접 import 한다.
`MAINTQ_TOOLS_PROFILE=core`(기본값)에서 `check_disposal_blockers` 도구가 등록되지 않아도 REST 판정은 동작한다 —
**사람용 API 가 에이전트 도구 노출 설정에 종속되면 안 된다.**
D15(백엔드 ↔ MCP 프로세스 분리) 위반이 아니다: 금지되는 것은 `backend` ↔ `mcp_server` **상호 import** 이며
`data/` 는 두 프로세스가 공유해도 되는 데이터 계층이다.

#### 확장 REST 5종 — 보전지표·수리가치·부품등급·지출판정·근거번들 (MQ-908, D73·D101)

```
GET  /api/assets/{asset_id}/metrics?window_months=12   → get_maintenance_metrics 상당
POST /api/equipment/{equipment_id}/repair-value         → assess_repair_value 상당 (무저장)
GET  /api/parts/{part_no}/criticality                   → classify_part_criticality 상당
POST /api/expenditure/classify                          → classify_expenditure 상당 (무저장)
GET  /api/assets/{asset_id}/evidence-bundle              → build_evidence_bundle 상당
```

`backend/routers/maint_value.py`. **앞의 넷은 `data.maint_value`(D101)를 거친다** — 도구 서버
패키지를 import 하지 않는다(D15). **다섯 번째(근거 번들)는 `services/decisions.rebuild_bundle()`
을 그대로 부른다** — `decisions.sign()` 이 서명 시점 재산출에 쓰는 것과 같은 조립이라 세 번째
사본을 만들지 않는다.

- **역할 게이트가 없다** — 전부 읽기 판정이라 이 다섯 경로에서 403 은 나오지 않는다
  (`/disposal/precheck` 와 같은 이유, D38·D71). `POST` 둘은 입력이 본문이라 POST 일 뿐 **아무것도
  저장하지 않는다.**
- **오류 매핑**(도구 `status`/`reason` 을 재포장 없이 그대로 싣는다): `status:"ok"` → 200 ·
  `status:"not_found"`(`unknown_asset`·`unknown_equipment`·`unknown_part`·`no_host_asset`) → 404 ·
  `reason:"invalid_input"` → 422 · `reason:"rule_catalog_not_loaded"` → 503(재시도로 풀림) ·
  `reason:"law_text_unavailable"` → 409(재시도해도 같은 답) · 그 밖 `status:"error"` → 500.
- **`core` 프로파일(D69 기본값)에서도 5경로 전부 산다(D73)** — 앞의 넷은 애초에 MCP 프로세스를
  거치지 않고, 다섯 번째도 `data.rules.engine` 을 직접 쓰는 `rebuild_bundle` 을 거치므로 도구 등록
  여부와 무관하다.

#### 재고 조회 — `GET /api/inventory` (Sprint 10, D73)

```
GET  /api/inventory?part_no=...                          → search_inventory 상당
GET  /api/inventory?part_name=...&model=...               → search_inventory 상당
```

`backend/routers/inventory.py` 가 `data.inventory.search()`(Task 1 에서 도구 로직을 추출)를 그대로 부른다 —
MCP 프로세스를 거치지 않는다. 위 다섯 경로와 같은 규약: 역할 게이트 없음(읽기 판정) · `core` 프로파일에서도
동작(D73) · 오류 매핑은 도구 `status`/`reason` 을 재포장 없이 그대로 싣는다(`invalid_input`·`invalid_model` → 422,
`not_found` → 404).

#### 설비 하이라이트 상태 — `GET /api/assets/{asset_id}/hotspot-status` (Sprint 10, D73)

```
GET  /api/assets/{asset_id}/hotspot-status                → 부품별 하이라이트 색(red/blue/orange/null) + 근거
```

`backend/routers/hotspot_status.py` 가 `data.hotspot_status.hotspot_status()`(§4-5·§4-6)를 그대로 부른다 —
역할 게이트 없음(읽기 판정) · `core` 프로파일에서도 동작(D73) · 연결된 인버터가 없는 자산은 404.

#### 기한 추적 · 위험등급 — `GET /api/deadlines`·`GET /api/{buildings,assets}/{id}/risk-grade` (Sprint 11, MQ-1105, D73·D102)

```
GET  /api/deadlines?asset_id=&window_days=                → track_deadlines 상당
GET  /api/buildings/{building_id}/risk-grade               → assess_risk_grade 상당
GET  /api/assets/{asset_id}/risk-grade                     → assess_risk_grade 상당 (asset_id 해석 편의)
```

`backend/routers/asset_monitoring.py` 가 `backend/services/asset_monitoring.py` 를 거쳐
`data.deadlines.track_deadlines`·`data.risk_grade.risk_grade`(D101)를 그대로 부른다 — 도구
서버 패키지를 import 하지 않는다(D15). `services/maint_value.py`·`services/disposal.py` 와
같은 3단 구조(서비스가 커넥션 열고 위임 → 예외는 `db_missing`/`db_error`/`internal_error` →
라우터가 HTTP 매핑)이고, 세 번째 `mode=ro` 헬퍼를 새로 만들지 않고 `services/disposal.
read_only` 를 재사용한다.

- **역할 게이트가 없다** — 둘 다 읽기 판정이라 이 세 경로에서 403 은 나오지 않는다
  (`/disposal/precheck`·`maint_value.py` 와 같은 이유, D38·D71).
- **오류 매핑**(도구 `status`/`reason` 을 재포장 없이 그대로 싣는다): `status:"ok"` → 200 ·
  `status:"not_found"`(`unknown_asset`·`unknown_building`·`no_building`) → 404 ·
  `reason:"invalid_input"` → 422 · 그 밖 `status:"error"`(`db_missing`·`db_error`·
  `internal_error`·`rule_catalog_not_loaded` 등) → 500.
- `window_days` 가 쿼리 문자열로 왔는데 정수로 파싱되지 않으면 이 표와 별개로 FastAPI 자체
  타입 검증이 422 를 낸다 — 위 표의 `invalid_input` 은 타입은 맞았지만 값이 부적절한 경우
  (음수 등)를 `data.deadlines` 가 판정한 결과다. 두 층위를 섞지 않는다.
- **`core` 프로파일(D69 기본값)에서도 세 경로 전부 산다(D73)** — MCP 프로세스를 애초에
  거치지 않으므로 도구 등록 여부와 무관하다. `GET /api/deadlines`(기본 파라미터)는 시드
  특성상 `items: []` 가 정상이다(D62 — 실패 아님); `window_days=500` 이면 `AST-L2-SPDL` 이
  잡힌다.
- **UI**: `/manager/deadlines`·`/manager/risk-grade` (Sprint 12). Sprint 11 시점엔 이 세 경로를
  보여주는 화면이 범위 밖이었다(§7 참고, `docs/sprints/sprint-11.md`) — Sprint 12(MQ-1203·1204)가
  노출했다.

### 2.6 처분 결정 — 제출·서명·반려 (S10 계층 3 확정 · D85)

```
GET  /api/decisions?state=pending    # 목록. **역할 무관 조회** — 정비사도 자기 요청 상태를 봐야 한다
GET  /api/decisions/{id}             # 상세 + 렌더된 문서·증빙 패키지
                                     #   ★ 저장본이 아니다 (D86) — 응답 조립 시점에 번들에서 렌더한다.
                                     #     저장하면 템플릿이 바뀔 때 저장본이 조용히 낡는다 (D57 선례)
POST  /api/decisions                 # 화면 직접 생성 (**technician만**, P39 — 2026-09-03)
  body: { asset_id, disposal_mode, disposal_date?, reason }
  → GET /api/decisions/{id} 와 같은 상세 셰이프. requested_by 는 **생성 즉시** stamp(D37)
  → 404(없는 자산) · 422(사유 공백 — D5) · 409(인용 룰 소실) · 503(룰 카탈로그 미적재, D71)

PATCH /api/decisions/{id}            # draft 수정 (**technician만**, P39)
  body: POST 와 동일한 4필드
  → 409(draft 아님) · 404(없음) · 그 외 POST 와 같은 매핑

  🔴 **수정은 재판정을 부른다 — 처분에만 있는 성질이다.** `disposal_mode`·`disposal_date` 는
     룰 입력이라 바뀌면 판정도 근거도 달라진다. 그래서 `evidence_bundle`·`bundle_hash`·
     `verdict_at_signing` 을 **새 값으로 덮는다**(발주의 `unit_price`, 수리의
     `expenditure_class` 재산출과 같은 자리).
     판정은 MCP 도구와 **같은 `rebuild_bundle()`** 을 지난다 — 화면이 독자 판정 로직을
     갖지 않는다(갈리면 "화면에서 본 판정"과 "서명 때 나온 판정"이 달라진다).
  ✅ **이것이 서명 게이트를 약화시키지 않는다.** `sign()` 이 서명 시점에 **다시** 재산출·
     대조하기 때문이다(D84 — ③ 이 override 판정보다 **먼저**다). 저장된 해시가 무엇이든
     서명 순간의 사실과 다르면 `EvidenceChanged` 로 막힌다.
     실측: `disposal_sign_contract` 26/26(27조합 전수 BLOCKING 우회 0 · 서명 없는 확정 0) ·
     `approvals_contract` 26/26 무변화.
  ⛔ **`override`·`override_reason`·`reviewed_by` 는 body 에 없다** (D81) — 예외 적용은
     서명 화면 전용이다. 초안 경로가 그걸 받으면 D81 이 막으려던 우회가 그대로 열린다.
  ⛔ **BLOCKED 여도 생성·수정된다** (D63) — 막는 것은 서명이지 초안이 아니다.

POST /api/decisions/{id}/submit      # draft → pending    (**technician만**)
POST /api/decisions/{id}/sign        # pending → signed   (**manager만**)
                                     #   body: { override?: bool, override_reason?: str, note?: str }
                                     #   ★ 이 세 키는 **사람만** 넣을 수 있다 — 도구 스키마에는 없다 (D81)
POST /api/decisions/{id}/reject      # pending → rejected (**manager만**, body: {reason} 필수 — D38)
```

**403 은 양방향이다** — 팀장이 `submit` 을 부르면 403, 정비사가 `sign` 을 부르면 403.
한쪽만 막으면 "권한 위반 차단 100%" 지표가 반쪽이 된다.

#### `sign` 의 409 `reason` 5종 — HTTP 하나로 뭉개지 않는다

| reason | 뜻 | 사용자가 할 일 |
|---|---|---|
| `invalid_transition` | 현재 state 에서 불가한 전이 | 상태 확인 |
| `law_text_unavailable` | 인용 조문 원문 미수집 (`missing_law_refs[]` 동반) | 조문 수집 |
| `cited_rule_missing` | **판정이 인용한 룰만** 카탈로그에서 사라짐 (`missing_rules[]`) | 사람의 재검토. ⚠ **503 이 아니다** — 재시도해도 같은 답이다 |
| `evidence_changed` | 번들 재산출 해시 ≠ 저장 해시 (`bundle_hash`·`recomputed_hash` 동반) | 근거 재확인 |
| `override_required` | 차단 판정인데 `override` 미기재 (`verdict`·`blockers`·`holds`·`insufficient`·`resolve_options` 동반) | 사유와 함께 예외 적용, 또는 사유 해소 |

- **`override_required` 본문이 해소 재료를 함께 싣는 이유**: S4 태도 — "안 된다"로 끝내지 않고
  무엇이 막고 있고 무엇을 하면 풀리는지 함께 준다.
- **503 은 "재시도하라"는 말이다.** 그러니 재시도로 풀리는 것만 503 이다 — 카탈로그 **미적재**
  (`rule_catalog_not_loaded`)가 그것이다. *인용 룰만 사라진* 경우는 근거가 바뀐 것이라 409 다.
  재시도해도 같은 답이 오는 상태에 503 을 주면 클라이언트를 영원히 돌게 만든다.
  ⚠ **예외가 하나 있다 — A2A `policy_blocked`(§2.9, D149).** 샌드박스 모드(`MAINTQ_SANDBOX=
  openshell`)에서 egress 정책이 파트너 호스트를 막을 때도 503 을 쓰는데, 이건 재시도로
  풀리지 않는다(정책이 바뀌기 전까지 항상 같은 결과) — "503 = 재시도하면 풀린다"는 이
  경로에서는 성립하지 않는다는 것을 알고 읽을 것. `Retry-After` 헤더도 없다(재시도를
  유도하지 않는다는 신호).
- **`override_reason` 공백을 pydantic 으로 막지 않는다** — 본문 검증은 라우팅 직후라
  404·`evidence_changed`·`override_required` 보다 **먼저** 실행되어 **D84 가 정한 순서가 깨진다.**
  검증은 `services.decisions.sign()` 안에서 하고 라우터가 422 로 매핑한다. DB CHECK 가 2차 방어선(D63).
- **D84 — 서명 시 번들을 재산출해 해시를 대조**하고, **그 대조를 override 판정보다 먼저** 한다.
  근거가 바뀐 상태에서 override 를 받으면 *"사람이 본 것과 다른 근거에 서명"* 이 된다 —
  **근거 무결성이 권한 판단보다 앞선다.**

### 2.7 통합 승인 큐 (D85) — **읽기 전용**

```
GET /api/approvals?state=pending&kind=disposal
  → { items: [...], kinds: ["po","disposal","repair"] }
```

**항목 공통 필드**: `kind` · `id` · `title` · `state` · `urgency` · `requested_by` ·
`requested_by_name` · `created_at` · `detail_path` · `verdict` · `requires_override`

- **`/api/po` 의 경로·응답 형태는 불변이다.** 형태를 흔들면 `spikes/api_contract.py` 28건 +
  프론트 `mappers.tsx` + **완료 기준 "권한 위반 403 차단 100%" 의 판정 경로**가 함께 흔들린다.
  `services/po.py` 의 `_PO_SELECT` 가 `parts`·`suppliers` 를 JOIN 하므로 처분서를 담으면
  응답의 절반이 NULL 이 된다.
- **`state` 는 각 종류의 원 어휘 그대로다** (변환 금지). `approved`(발주 승인)와 `signed`(처분 확정)는
  **다른 사건**이고, 한 필드로 뭉개면 D39·D63 이 구분해 둔 책임 귀속이 API 경계에서 사라진다.
- **없는 값은 `null` 이지 `false` 가 아니다** — 발주에는 처분 판정이 없으므로 `verdict: null`,
  처분서에는 긴급도가 없으므로 `urgency: null`. 지어내지 않는다 (D62).
- **`kind` enum 밖 값은 422** — 모르는 종류를 0건으로 돌려주면 오타가 "해당 없음"으로 읽힌다.
- **`repair` 는 Sprint 9(MQ-909)부터 실제로 채워진다.** enum 에 미리 넣어 둔 덕분에
  **계약 변경 없이** `repair_records` 를 연결했다 — 시드 12건(서명 11 + draft 1)이 전부
  필터 없는 조회에 그대로 나온다. "0건이 정상"이던 서술은 더 이상 사실이 아니다.
- **POST 가 없다.** 전이는 종류별 경로(`/api/po/*`·`/api/decisions/*`·`/api/repairs/*`)가 각자의
  역할 게이트와 함께 수행한다. 통합 경로에 전이를 두면 `kind` 마다 다른 역할 규칙을 한 함수가
  분기하게 되고, **그 분기가 곧 403 지표의 구멍**이 된다.
- 정렬은 `created_at DESC`. `/api/po` 의 긴급 우선 정렬을 여기로 옮기지 않는다 — 통합 큐에 발주 전용
  정렬을 끌어오면 처분서가 항상 뒤로 밀린다. **두 목록은 정렬 기준이 다른 게 정상이다.**

### 2.8 수리 증빙 — 생성·수정·제출·서명·반려 (S29 · D85·D98, Sprint 9 신설 · **P39 확장**)

```
GET  /api/repairs?state=pending      # 목록. **역할 무관 조회** — 정비사도 자기 요청 상태를 봐야 한다
GET  /api/repairs/{id}               # 상세. hash_verified 로 서명 해시 재계산 대조 결과를 싣는다(D84 태도)

POST  /api/repairs                   # 화면 직접 생성 (**technician만**, P39 — 2026-09-03)
  body: { equipment_id, work_type, repair_scope, cost, parts[],
          downtime_hours?, model?, error_code?, note? }
  → GET /api/repairs/{id} 와 같은 상세 셰이프. performed_by 는 **생성 즉시** stamp(D37)
  → 404(unknown_equipment · unknown_part) · 422(invalid_input · model_code_pair ·
    invalid_model · integrity) · 403(technician 아님)

PATCH /api/repairs/{id}              # draft 수정 (**technician만**, P39)
  body: POST 와 동일한 9필드
  → 409(draft 아님) · 404(없음) · 그 외 POST 와 같은 매핑

POST /api/repairs/{id}/submit        # draft → pending    (**technician만**)
POST /api/repairs/{id}/sign          # pending → signed   (**manager만**)
POST /api/repairs/{id}/reject        # pending → rejected (**manager만**, body: {reason} 필수 — D38)
```

**🔵 POST·PATCH 는 D10 대상이 아니다** (D111 이 `POST /api/po` 에서 정리한 경계와 같다) —
MCP 도구가 아니라 백엔드 쓰기라 처음부터 UPDATE 권한이 있다. 산출 로직은
`data/repair_record.py` 공유 계층에서 `create_repair_record`(MCP)와 **동일하게** 검증된다
(`data/po_draft.py` 선례) — 두 경로의 판정이 갈릴 수 없다.

⛔ **`expenditure_class`·`part_class`·서명 필드는 body 에 없다.** 서버가 산출하거나 사람이
서명으로 채운다 — D31 이 `unit_price` 를 `create_po_draft` 스키마에서 뺀 것과 같은 이유다:
입력으로 받는 순간 사용자가 서버 계산을 덮어쓸 수 있고, 그러면 그 계산의 존재 이유가 사라진다.
PATCH 에서도 **재산출**되며, `update_draft()` 의 SET 절에 서명 필드가 아예 없어 수정으로
서명이 지워지거나 채워지는 경로가 없다.

⚠️ **`_REASON_HTTP` 에 없는 `reason` 은 500 이다.** 모르는 실패를 4xx 로 반올림하지 않는다 —
사용자 잘못이 아닌 것을 사용자 잘못처럼 보이게 하면 원인 추적이 끊긴다.

화면: `/technician/repair/new` · `/technician/repair/{repairId}`(draft 면 수정 폼, 아니면
읽기 전용) · `components/asset/RepairForm.tsx`.

**상태 전이 = 권한** (`routers/po.py`·`routers/decisions.py` 와 같은 태도). MCP 도구
`create_repair_record`(`04 §16`)는 `state='draft'` INSERT 만 하고(D10·D98), 전이는 전부 여기를 통한다.

**403 은 양방향이다** — 정비사가 `sign` 을 부르면 403, 팀장이 `submit` 을 부르면 403.
한쪽만 막으면 "권한 위반 차단 100%" 지표가 반쪽이 된다.

#### `sign` 의 409 `reason` 2종

| reason | 뜻 | 사용자가 할 일 |
|---|---|---|
| `invalid_transition` | 현재 state 에서 불가한 전이 | 상태 확인 |
| `self_sign` | `performed_by == verified_by` — 작업자가 스스로 서명(D4, 진단자/승인자 분리) | 다른 사람에게 서명을 요청 |

- `submit`·`reject` 의 실패도 같은 `invalid_transition` 형태(`{reason, detail, state}`)를 쓴다
  (`routers/decisions.py:_conflict` 와 같은 형태).
- `reject` 의 사유 공백은 pydantic 이 **먼저** 422 로 막는다(D38). 값이 있으면 `note` 컬럼에 저장된다.
- 서명 시 `verified_by`·`signed_at`(UTC, D39)·`record_hash`(`data/repair_hash.compute_record_hash()`,
  D84 태도)를 **같은 UPDATE 에서** 함께 쓴다 — DDL CHECK(`05 §16` 신설 ②)가 하나라도 빠지면 거부한다.
- `verified_by` 컬럼은 서명자뿐 아니라 **반려자도 함께 쓴다** — 별도 `reviewed_by` 컬럼이 없고,
  반려도 "manager 가 그 증빙을 검토했다"는 같은 성격의 사건이다.

### 2.10 결재 문서 docx 다운로드 (D124·D86, 2026-09-04 신설)

```
GET /api/po/{po_id}/documents/{doc}.docx
      doc ∈ diagnosis | po_request | fund_execution        # 01 · 02 · 03
GET /api/decisions/{decision_id}/documents/{doc}.docx
      doc ∈ approval | representation_warranty              # 05 · 06
```

- 응답 `200`: `Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`
  · `Content-Disposition: attachment; filename="..."; filename*=UTF-8''...`
  (한글 파일명은 RFC 5987 `filename*`, ASCII `filename` 은 구형 클라이언트 폴백)
- **저장하지 않는다** (D86) — `data/templates/*.docx` 를 읽어 `io.BytesIO` 로만 조립해 스트림한다.
  디스크에도 DB 에도 남기지 않으며 임시 파일도 만들지 않는다.
- **가용성 규칙은 `documents_preview` 와 같은 조건**을 쓴다 — 두 곳에 다른 조건을 두면
  화면엔 안 보이는데 URL 로는 받아지는 문서가 생긴다:
  - `diagnosis` → `error_code_def` 가 없으면 **404** (미리보기가 `null` 인 바로 그 조건)
  - `fund_execution` → `state ∉ (approved, finance_approved, finance_rejected)` 면 **404**
  - 화이트리스트 밖 `doc`, 없는 `po_id`·`decision_id` → **404**
- **403 이 없다.** 미리보기를 이미 볼 수 있는 사람이면 다운로드도 된다 — 읽기에 새 역할
  게이트를 만들면 D38 지표가 오염된다(`2.7` 통합 승인 큐와 같은 태도).
- ⛔ **04(담보대출심사회신서)는 대상이 아니다** (D118 — FinAllQ 소관).

**신원·서명은 이 엔드포인트만 얹는다** (D23·D37·D81). 필드맵을 만드는 `data/doc_fields.py` 는
`WITHHELD_KEYS` 16키를 **아예 만들지 않으므로**, MCP 도구 경로(`get_document_facts`,
`04 §21`)에는 신원이 흐를 코드 경로 자체가 없다. 서명 전에는 `확인되지 않음` 이 아니라
`(미기재 — 서명 시 기록된다)` 로 남는다 — *"원천이 없다"*(D62)와 *"아직 그 단계가 아니다"* 는
다른 사실이다.

**교정 경로**: 이 엔드포인트는 조회다. 값을 고치려면 `PATCH /api/po`(D111) ·
`/api/repairs` · `/api/decisions`(P39) 또는 `create_po_draft` 새 초안이다 (D10·D125).

### 2.4 상태 전이 다이어그램

```
[발주 po_drafts]                                    ★ Sprint 17 확장 (D119)
draft ──submit(정비사)──▶ pending ──approve(팀장)──▶ approved
                             └──────reject(팀장)──▶ rejected
                                                          │
                                          finance-approve(재무담당자)
                                                          ▼
                                       finance_pending ──┴──▶ finance_approved
                                                          └──▶ finance_rejected

※ `finance_pending` 박스는 개념적 표기일 뿐 실제 DB 상태값이 아니다 — `approved` 자체가
   "재무 승인 대기중"을 겸한다(스키마 단순화). `finance-approve`/`finance-reject` 둘 다
   `ALLOWED_FROM`에서 전이 시작점을 `approved`로 둔다.

[처분 decisions]                                    ★ Sprint 7 신설
draft ──submit(정비사)──▶ pending ──sign(팀장)────▶ signed
  ▲                          └──────reject(팀장)──▶ rejected
  └ generate_disposal_document (MCP 도구, INSERT 만 — D10·D81)

※ 생성/전이 주체 분리는 두 테이블에 **동일하게** 적용된다.
   MCP 도구는 draft INSERT 만 가능하고 UPDATE 권한 자체가 없다 (TEMP TRIGGER).
※ `signed` 로 가는 길은 네 층이 막는다 (완료 기준 ②③):
   ⓐ 도구 스키마에 `override` 키 **부재** (D81)
   ⓑ MCP 커넥션 TEMP TRIGGER (UPDATE/DELETE 거부)
   ⓒ REST `sign()` 의 409 `override_required` / `evidence_changed`
   ⓓ **DDL CHECK 2종** — 서명 3필드 완비 · 차단 verdict 는 override=1 필수
      → 코드 버그·콘솔 SQL·마이그레이션으로도 뚫을 수 없다 (`05 §14`)
```

### 2.9 A2A 크로스도메인 호출 (`backend/routers/a2a.py`, Sprint 16, D112~D114 · **D136**)

> 🔴 **모든 A2A 엔드포인트에 503 이 추가됐다 (D136, 2026-09-09).** 차단기(circuit breaker)가
> 열려 있으면 **네트워크를 타지 않고** `503 + Retry-After` 로 즉시 돌려준다.
> **502 와 구분해서 읽어야 한다** — 502 는 *"닿으려 했는데 못 닿았다"*, 503 은
> *"우리가 스스로 막았다(연속 실패 N회)"* 다. trace 에도 `unavailable` / `circuit_open` 으로
> 나뉘어 남는다. 차단기는 **파트너 단위**이고 **전송계층 실패만** 센다 (D139) —
> **상태코드가 무엇이든 HTTP 응답을 받으면 차단기를 닫는다.** 400·422 같은 계약 실패는 물론
> **502·503·504 도 마찬가지다**: 상대가 살아서 요청을 파싱하고 자기 upstream 이 실패했다고
> 판단해 그 판단을 써 보낸 응답이기 때문이다(죽은 프로세스는 502 를 못 만든다).
> ⛔ 이 구분이 없으면 **2차 홉 장애가 파트너 전체를 막는다** — InsuQ 가 죽으면 FinAllQ 는
> 멀쩡한데 `request-withdrawal`·`request-settlement` 까지 차단된다(2026-09-10 실측).
> ⚠ 상대의 `504`(상대가 판단해 보낸 **응답**)와 우리 타임아웃(**응답 없음**)은 다른 사건이다 —
> 후자는 여전히 도달 불가로 세므로, 아플 만큼 느린 상대에는 차단기가 정상 동작한다.
>
> 🔴 **`policy_blocked` 503 도 있다 (D149, 2026-09-24).** 샌드박스 모드
> (`MAINTQ_SANDBOX=openshell`)에서는 egress 정책상 파트너 호스트가 애초에 열려 있지 않다 —
> **네트워크를 시도하기도 전에** 판정한다(day1 §5.1). `A2ACircuitOpenError` 보다 **먼저** 잡는다.
> 형태가 다르다 — `detail` 이 문자열이 아니라 **dict**: `{"reason": "policy_blocked",
> "message": "..."}`, 그리고 **`Retry-After` 헤더가 없다**(차단기 503 은 있다). 재시도해도
> 절대 풀리지 않는다 — 상대가 아프거나 우리가 연속 실패를 회계한 상태가 아니라 **정책이
> 애초에 막아 둔 상태**이기 때문이다(에러코드는 절대 추측하지 않는다는 태도의 A2A 판). trace 는
> `status=policy_blocked` 로 남고 `backend/a2a/circuit.py` 의 성공/실패 회계에는 들어가지
> 않는다(상대가 살았는지 죽었는지 판단할 근거 자체가 없다 — 시도하지 않았다).
> ⚠ **현재 알려진 결함(MQ-1913 소관, `docs/07_BACKLOG.md` 참고)**: `assess_equipment_loan`·
> `assess_used_equipment_loan`·`search_insurance_clause` MCP 도구 3종은 503 을 받으면
> 이유를 묻지 않고 전부 `circuit_open` 으로 읽는다 — `policy_blocked` 인지 실제 차단기
> 발동인지 이 세 도구의 반환값만으로는 구분할 수 없다.

```
POST /api/a2a/lookup-clause          # InsuQ lookup-clause 스킬 중계 (기존 — Sprint 16 이전 미문서화분 소급 기재)
  body: { question, session_id?, request_chain_id? }
  → InsuQ 응답 그대로(+ request_chain_id 강제 주입, MQ-1602) — 200
  → 504(timeout) · 502(unavailable) · exc.status_code(그 외 A2AClientError, detail 본문)

POST /api/a2a/assess-loan            # FinAllQ assess-loan 스킬 중계 (기존 — Sprint 16 이전 미문서화분 소급 기재, S8)
  body: { loan_amount, purpose, collateral_building_id, session_id?, request_chain_id? }
  → FinAllQ 응답 그대로(+ request_chain_id 강제 주입) — 200
  → 504(timeout) · 502(unavailable) · exc.status_code(그 외)

POST /api/a2a/assess-used-equipment-loan   # FinAllQ 중고 설비 담보 심사 (신규 2026-08-30, S13)
  body: { asset_id, loan_amount, session_id?, request_chain_id? }
  #   호출자는 asset_id 와 금액만 준다 — 담보 건물·연식·점검 이력·**원가**는 빌더가
  #   assets·ownership_checks 에서 파생한다(build_request_withdrawal_payload 관례).
  #   🔵 `inspection_data.original_cost` = `assets.acquisition_cost` (D138). 안 보내면
  #     FinAllQ 가 원가를 `loan_amount` 로 대체해 **감정가가 늘 신청액보다 작아지고
  #     승인이 구조적으로 불가능**해진다(2026-09-10 실 E2E 확인). 출처는
  #     `original_cost_basis` 로 함께 보내고, NULL 이면 키를 생략한다(D62).
  #   ⛔ `book_value` 는 보내지 않는다 — `inspection_data.appraised_value` 는 상대의
  #     감가상각을 통째로 건너뛰는 override 라, 장부가액을 감정가로 둔갑시킨다.
  #   ⚠ equipment_year 는 계약상 제조연도지만 MaintQ 는 그걸 저장하지 않는다 —
  #     acquired_at 의 연도를 보내고 inspection_data.equipment_year_basis 로 그 사실을 알린다.
  → FinAllQ 응답 그대로(+ request_chain_id 강제 주입) — 200
  → 400(없는 asset_id — **발신 전에** 끊는다) · 504 · 502 · exc.status_code

POST /api/a2a/request-settlement     # FinAllQ 매각대금 정산·근저당 말소 (신규 2026-08-30, S12)
  body: { decision_id, sale_amount, outstanding_loan, approved_by,
          prepayment_fee?, session_id?, request_chain_id? }
  #   decision_id 는 **미서명 draft** 를 가리킨다 — 담보 자산은 LIEN-CONSENT(BLOCKING)로
  #   서명이 막혀 있고 그 담보를 푸는 수단이 이 스킬 자신이라, 정산이 서명보다 먼저다.
  #   approved_by 는 **정산 요청 승인자**이지 처분 서명자가 아니다.
  → FinAllQ 응답 + maintq_lien_consent_updated?(해소했을 때만) — 200
  → 400(없는 decision_id · 담보 없는 자산) · 504 · 502 · exc.status_code

  🔴 **이 레포에서 유일하게 A2A 응답이 MaintQ 상태를 바꾸는 경로다.**
     `lien_released` 가 **명시적으로 true** 일 때만 `assets.lien_consent_ref` 에
     `A2A-SETTLE-<chain_id>` 를 쓴다(`backend/services/lien.py`). truthy 검사가 아니라
     `is True` 인 이유는 `"true"` 문자열·`1` 같은 계약 밖 값이 담보를 푸는 걸 막기 위해서다.
     ⛔ **결정을 서명하지 않는다** — 담보만 풀고 서명은 사람이 한다("서명 없는 처분 확정
     0건" 을 A2A 로 우회하지 않는다). ⛔ **빈 문자열을 쓰지 않는다** — `''` 는 `is_null` 을
     False 로 만들어 BLOCKING 룰을 조용히 미발화시킨다(seed 검사 ⑱).
     ⚠ 응답 `remaining_balance` 는 장부 반영 잔액이 아니라 산술 결과다(FinAllQ
     `decide_settlement` 는 DB 조회 0인 순수 함수) — trace 에만 남기고 소비하지 않는다.

POST /api/a2a/notify-asset-change    # InsuQ 부보 목적물 변경 통지 (신규 2026-09-09, S11)
  body: { decision_id, change_type?("REMOVE"|"ADD", 기본 REMOVE), session_id?, request_chain_id? }
  #   🔵 **조립 가드 6종 — 하나라도 어긋나면 발신하지 않고 400** (D142 로 4→6):
  #     ① 미서명 결정 ② 미부보 자산 ③ `policy_id` 없음 ④ `building_id` 없음
  #     ⑤ **건물 결 `partner_links.link_state != 'LINKED'`** ⑥ **요청자 식별자 없음**
  #     ⑤ 는 행이 없을 때도 거부한다 — «반려됐다»(`NOT_LINKED`)와 «대장에 없다»(행 없음)를
  #       뭉개지 않고 오류 메시지에 그대로 싣는다(D62).
  #     ⑥ 이 없으면 빈 요청자 식별자가 나가 수신부가 `schema_validation_failed` 를 낸다
  #       (`request-withdrawal` 이 `error_code=None` 으로 정확히 그 400 을 맞은 전례).
  #   🔵 발신 시 `Idempotency-Key: <decision_id>:<change_type>` 헤더를 함께 싣는다 (D141).
  #     같은 처분의 재전송은 **같은 키** → 상대가 저장된 응답을 재생한다. 같은 키인데 내용이
  #     다르면 **409 `idempotency_conflict`** 로 막힌다(사람이 봐야 할 상황이라 막히는 게 맞다).
  #     ⛔ 난수를 쓰지 않는다 — 재전송이 다른 키가 되면 멱등성이 성립하지 않는다.
  #     ⚠ 계약면(schemas·agent_cards)에 헤더를 적을 자리가 없다 — A2A_Q CP-006 이 진행 중이고,
  #       상대 의미론은 배포된 구현으로 공개받았다(3중 복합키 · payload 다이제스트 비교 · 128자)
  → InsuQ 응답 그대로(+ request_chain_id 강제 주입) — 200
  → 504 · 502 · **503**(차단기) · 400
  ⛔ **조립 단계에서 막힌 요청은 발신하지 않는다** — 아래 넷은 전부 400 이고
     `call_skill` 이 호출조차 되지 않는다(`routers/test_a2a.py` 가 단언):
     ㉠ 미서명 결정 — 계약이 "처분 **확정**에 따른" 변경이라 못박는다.
        **S12 와 정반대다**(S12 는 담보를 푸는 수단이라 서명보다 앞서야 했다)
     ㉡ 부보 아님(`insured=false` 또는 `policy_id` NULL) — 고칠 증권이 없다
     ㉢ `building_id` 없음 ㉣ enum 밖 `change_type`
  ⛔ **응답으로 MaintQ 상태를 바꾸지 않는다** — `receipt_no`·`premium_adjustment` 는
     trace 에만 남는다. 상태를 바꾸는 경로는 여전히 request-settlement 하나뿐이다
  📌 `effective_date` 는 오늘이 아니라 **서명일**(`decisions.signed_at`)이다

GET  /api/a2a/history                # A2A 호출 감사 이력 (신규, D114)
  query: skill? · po_id? · building_id? · chain_id? · limit?(기본 50)
  → { count, items: [{ request_chain_id, skill, session_id, status, request, response, ts }] }
  #   status 는 record_a2a_trace 가 기록한 값(ok|timeout|unavailable|error) — tool_result 행이
  #   아직 없으면 null. response 는 tool_result.tool_payload 원문, 파싱 실패 시 {"_parse_error": true}.
  #   정렬 ts desc, limit 은 필터링 후 적용
```

- **`request_chain_id` 강제 주입 (MQ-1602)**: 두 POST 엔드포인트는 성공 분기에서 `record_a2a_trace` 호출
  **직전** `res["request_chain_id"] = chain_id` 를 실행한다 — 파트너가 응답에 이 값을 echo 하지 않아도
  MCP 도구(§04 §19·§20)가 항상 상관관계 키를 받게 한다.
- **역할 게이트가 없다** — 셋 다 `require()` 를 호출하지 않는다(기존 두 POST 엔드포인트의 기존 관례를
  `GET /history` 가 그대로 따름). 감사 이력을 무인증 노출한다는 점은 리뷰 노트로 남아 있다(Sprint 16
  Stage 1 reviewer 게이트, 비블로커).
- **`GET /api/chat/{session_id}/trace`(§2.1, D76-2 ⓑ)와 다르다** — 그 경로는 `tool_payload` 를
  의도적으로 비운다. `GET /api/a2a/history` 는 `tool LIKE 'a2a:%'` 로 대상을 좁힌 대신 그 원문을 연다
  (D114) — 일반 대화 trace 전체를 노출하지는 않는다.
- **`GET /api/chat` SSE `tool_result` 의 `a2a_chain_id`(D113, §2.1 참조)** 로 채팅 화면이 이 엔드포인트를
  찾아가는 상관관계 키를 받는다 — 실시간 스트림엔 키만 흐르고, 구조화된 원문은 이 GET 이 연다.

### 2.11 온보딩 승격·안전 승인 (`backend/routers/onboarding.py`, D154·D156·D157, Sprint 19 신설)
**신규 절 — D154~D157(확정 2026-09-24, Sprint 19 H0). 인터페이스는 MQ-1909 명세 그대로다.**

> 새 기종(HV600 등) 스테이징 데이터(`05 §25~§29`)를 **정본으로 승격**하는 유일한 문이다 —
> MCP 온보딩 도구(`04 §23~§25`)는 스테이징 INSERT 만 하고, 정본(`error_codes`·`manual_chunks`)
> 쓰기와 상태 전이(`staged→approved/rejected`)는 전부 이 라우터를 거친다(D10·D81·D154 그대로).
> 모든 쓰기는 `deps.caller()` + `deps.require(c, "manager", ...)`. `c.user_id` 가 `users` 에
> 없으면 400.

```
GET  /api/onboarding/batches
  → [{ batch_id, model, manual_id, manual_doc, loaded_at, rows, staged, approved, rejected, normalized_rows }]
     manual_doc = data/raw/manifest.json 의 해당 manual_id `file` stem(예: "TOEPC71061732"), 없으면 null (2026-09-25 추가, D19)

GET  /api/onboarding/batches/{batch_id}/groups?state=staged|all
  → [{ model, code, promoted: bool,
       rows: [{ row_id, ordinal, display_code, section_en, section_ko, name_en, causes_en,
                 pages, source_flags, state,
                 norms: [{ norm_id, name_ko, causes_ko, confidence, flags, staged_by, created_at }] }] }]
  # norms 는 norm_id 내림차순 — 첫 항목이 최신

POST /api/onboarding/promote
  body: { model: str, code: str, primary_row_id: int,
          rows: [{ row_id: int, norm_id: int }], acknowledged_flags: list[str] = [] }
  → 201 { promo_id, model, code,
          error_code: { code, display_code, error_name, severity, causes, actions,
                        manual_page, actions_source },
          chunk_ids: [...] }

POST /api/onboarding/rows/{row_id}/reject
  body: { note: str }
  → 200 { row_id, state: "rejected" }

GET  /api/onboarding/status?model=HV600          (2026-09-25 추가 — 기종 온보딩 뱃지, 읽기 전용)
  → { model, state: "none" | "onboarding" | "safety_pending" | "ready" }
     none=배치 0(기존 기종) · onboarding=승격 코드 0 · safety_pending=승격 ≥1 + safety_source.resolve()=None ·
     ready=승격 ≥1 + resolve 값 있음. model ∉ MODELS → 422

GET  /api/onboarding/safety?model=HV600
  → [{ cand_id, page, also_pages, kind, quote_en, wait_minutes_in_text, state,
       approved_text, approved_by, approved_at, text_reviewed_at }]

POST /api/onboarding/safety/{cand_id}/approve
  body: { approved_text: str, text_reviewed: true }
  → 200

POST /api/onboarding/safety/{cand_id}/reject
  body: { note: str }
  → 200
```

**`POST /promote` 검증 (하나라도 실패하면 아무것도 쓰지 않는다, D156)**:

| 조건 | HTTP | reason |
|---|---|---|
| `model` 이 `prompts.MODELS` 밖 | 422 | `invalid_model` |
| `model` 이 `{iG5A, S100, IE5}`(시드 기종 — 파일이 정본, D148) | 422 | `seed_model_not_onboardable` |
| `error_codes` 에 이미 같은 `(model, code)` | **409** | `already_promoted` |
| `row_id` 가 존재하지 않음 | 404 | — |
| `rows` 가 서로 다른 `(model, code)` 그룹을 섞음 | 422 | `mixed_group` |
| 대상 행이 `state='staged'` 가 아님 | 409 | `row_not_staged` |
| `primary_row_id` 가 `rows` 목록 안에 없음 | 422 | — |
| `norm_id` 가 그 `row_id` 소속이 아님 | 422 | `norm_mismatch` |
| 그룹의 `staged` 행 중 body 에 없는 행이 있음(누락 방지) | 422 | `group_incomplete` + 누락 `row_ids` |
| 선택된 `norm.flags ∪ row.source_flags` 가 `acknowledged_flags` 에 다 포함되지 않음 | 422 | `flags_not_acknowledged` + 목록 |

통과하면 **한 트랜잭션**(`backend.db.connect()`)으로 `INSERT error_codes` 1행 →
`INSERT manual_chunks` N행(`embedding NULL`) → 포함 행 `UPDATE onboarding_code_rows SET
state='approved', reviewed_by, reviewed_at=now` → `INSERT onboarding_promotions`. 병합 규칙
(순서·`error_name`·`severity`·`causes`/`actions` 접두·청크 분할)은 **D156 전문 참조** —
이 문서에서 다시 옮기지 않는다(정본은 결정록 하나).

**`POST /safety/{cand_id}/approve` 검증 (D157·safety-guardrail 규칙 3)**:

| 조건 | HTTP | reason |
|---|---|---|
| 대상 행이 `state='staged'` 가 아님 | 409 | — |
| `approved_text` 공백 | 422 | — |
| `text_reviewed` 가 `true` 가 아님 | 422 | — |
| `wait_minutes_in_text IS NULL` 인데 `approved_text` 에 `\d+\s*분` 이 있음(원문에 없는 숫자를 지어냄) | 422 | `number_not_in_source` |
| `wait_minutes_in_text = n` 인데 `approved_text` 에 `f"{n}분"` 이 없음(임의 단축·변형) | 422 | `wait_value_mismatch` |
| 같은 `model` 에 이미 `approved` 상태 `discharge_wait` 가 있고 이번도 `discharge_wait`(D157 fail-closed 모호성 사전 차단) | **409** | `already_approved_for_model` |

통과하면 `UPDATE ... SET state='approved', approved_text, approved_by=c.user_id,
approved_at=now, text_reviewed_at=now`.

⛔ **승격 취소 API 는 없다** (범위 밖) — 잘못 승격하면 `error_codes`·`manual_chunks`
(`onboarding_promotions.chunk_ids` 로 대상 특정)·`onboarding_promotions` 행을 사람이 SQL 로
직접 정리한다(`TODO_직접할일.md` H10).

**교정 경로**: `POST /rows/{row_id}/reject`(반려, 재정규화 유도) 또는 `safety/{cand_id}/reject` —
승격·안전 승인 자체를 되돌리는 PATCH 는 없다(위 한계 참고). 화면(§ MQ-1911, 컷 후보)이 붙기
전까지는 `curl`/FastAPI `/docs` 로 위 엔드포인트를 직접 호출한다(컷 라인 C2).

### 2.12 사업장 평면도 (`backend/routers/sites.py`, D158, Sprint 19 MQ-1914 신설)

**읽기 전용 · 역할 무관**(`deps.caller()` 헤더 검증만, `require` 없음 — 403 이 없다). 커넥션은
`backend.services.disposal.read_only()`(세션 `default_transaction_read_only=on`). 쓰기 메서드 없음(405).

```
GET /api/sites
  → { items: [{ site_id, name, is_mock, width, height }] }

GET /api/sites/{site_id}/floorplan
  → { site: { site_id, name, is_mock, width, height },
      zones: [{ zone_id, name, kind, x, y, w, h }],                 # kind ∈ assembly|machining|packaging|utility
      equipment: [{ equipment_id, model, zone_id, x, y, location,
                    asset_id | null, asset_name | null }] }         # equipment_id 오름차순
  없는 site_id → 404
```

- 좌표는 **SVG 사용자 단위**(`site.width × site.height` 뷰박스) — 지도 좌표가 아니다(외부 지도 API 없음, D158 ⓑ).
- `asset_name` 은 `assets.name`(호스트 자산이 있을 때만) — `asset_id` NULL(분전반 `INV-L1-01`·HV600
  `INV-HV-01`·`INV-HV-02`)이면 **null** 이다(지어내지 않는다). `asset_id` 는 명세 초안에 없던 가산
  필드다 — 화면이 설비 상태를 `GET /api/assets/{asset_id}/hotspot-status` 로 **기존 API 그대로** 묻기
  위해 필요하다.
- **설비 상태·기종 온보딩 상태는 이 응답에 없다** — 화면이 `hotspot-status`(§2.5)·
  `GET /api/onboarding/status`(§2.11)를 조합한다. 판정 로직을 두 벌 만들지 않는다.
- 위치가 없는 설비는 응답에 나오지 않는다(좌표를 지어내지 않는다) — 시드·마이그레이션은 전 설비에
  위치를 준다(`spikes/site_floorplan_contract.py` ③).
- 화면: `/technician/site` — 점 클릭 → `/technician?equipment=<id>`(§2.1 진입 파라미터, 진단 콘솔이
  그 설비를 선택한 상태로 연다).

---

## 3. 평가셋 스키마 (`eval/testset.json`)

20문항. 각 문항의 구조와 지표 판정 방법을 여기 고정한다 (run-eval 스킬이 이 규격을 따름).

```json
{
  "id": "T01",
  "input": "iG5A 인버터에 OHt 에러 떴어",
  "equipment_id": "INV-L1-01",              // nullable — 모델 확인 질문 유도 케이스는 null
  "role": "technician",                     // 권한 위반 케이스는 여기서 조작
  "expected": {
    "branch": "s1_pipeline | s2_alternative | s3_root_cause | s4_not_found",
    "part_no": "FAN-IG5-01",                // 부품 특정 대상 문항만. S3/S4형은 null
    "safety_required": true,                 // 위험 작업 키워드 → SAFETY block 필수 여부
    "expect_not_found": false,               // S4형만 true
    "expect_hold": false                     // S3형만 true — 발주 보류 시퀀스 판정 (D35·A8)
  }
}
```

> `expect_hold` — `eval/score.py`의 `_judge_sequence`가 이미 이 필드를 읽는다(MQ-310).
> 이 문서 예시가 뒤늦게 반영하는 것뿐 계약 변경은 아니다. `true`면 해당 문항(S3, 발주 보류)에서
> `create_po_draft`가 호출되면 안 된다는 뜻(A8) — S4(미지 코드)도 발주를 호출하면 안 되지만
> 그 판정은 `expect_not_found`로 이미 커버되므로 S4형은 `expect_hold: false`로 둔다.
> `role` 필드는 현재 `eval/score.py`가 참조하지 않는다 — `POST /api/chat`은 role을 게이트하지
> 않으므로(§2.1 대화, `require()`는 `po.py`의 승인 워크플로우에만 있음) 20문항 내에서 role을
> 조작해도 의미가 없다. 권한 위반(403) 지표는 `eval/run_eval.py`의 문항 루프 밖 별도 고정
> 점검(승인 큐 pending 건에 technician으로 approve 시도)이 담당한다.

**지표별 판정 방법 (측정 가능성의 근거):**

| 지표 | 판정 소스 | 방법 |
|---|---|---|
| 부품 특정 정확률 ≥90% | **traces 테이블** | 응답 텍스트가 아니라 다음 순서로 판정 (D66): ① `create_po_draft.input.part_no` → ② 최종 `search_inventory.input.part_no` → **③ 최종 `get_supplier_quotes.input.part_no` (D133 — 견적은 사려는 부품에 대해 받는 것이므로 결론 표명이다)** → ④ 최종 `find_alternative_parts` 결과의 `parts` **단일 건** → ⑤ 최종 `search_inventory` 결과의 `parts` **단일 건**. 이 값이 expected.part_no 와 일치해야 pass. ③④를 단일 건으로 제한하는 이유는 부품명 조회가 다건을 돌려주기 때문 — 첫 항목을 정답으로 세면 에이전트가 고르지 않은 부품에 점수를 준다. **분모는 part_no가 있는 문항만** (구성: 부품 특정 대상 15 + S3형 3 + S4형 2 — 최종 확정은 사람, TODO 참조). 🔵 **실패는 성격별로 나눠 센다 (D135)** — 기대와 **다른 부품을 특정**하면 «오특정», 아무것도 특정하지 못했으면 «미특정». 판정은 `score.part_failure_kind()` 한 곳이 소유하고 `aggregate()` 가 `metrics.part.failures` 로 실어 리포트에 인쇄한다. **합계 하나로 비교하지 않는다** — 오특정은 정비사가 엉뚱한 부품을 발주하게 만들고 미특정은 답을 못 받는 것이라 위험도가 다르다(실측에서 합계가 두 축을 상쇄해 더 위험한 모델이 좋아 보였다, `memo/2026-09-06-noise-floor-20rounds.md`) |
| 근거 페이지 인용률 100% | block 이벤트 + traces | **분모 = 진단 응답이 생성된 문항(S4형 2건 제외, 18문항)** — S4는 citation이 없는 게 정답이라 분모에 넣으면 100% 달성이 구조적으로 불가능 (D30). 판정: `citation` block 존재 **그리고** 그 `page`가 같은 세션 traces의 lookup/rag 결과 page와 일치 — block만 검사하면 "블록은 있고 숫자는 지어낸" 경우를 통과시킴 |

| 안전 경고 누락 0건 | block 이벤트 | safety_required=true 문항에서 `safety` block 존재 여부. **방전 대기 문구 기준값은 "10분 이상"**(매뉴얼 명시값 — iG5A p.4·p.6, S100 p.2) — "5분" 등 축소 표기는 실패 판정 |
| 미지 코드 환각률 0% | 응답 텍스트 | **LLM judge**로 "원인/조치 서술 생성 여부" 판정 — 키워드 검사만으로는 불충분. judge 프롬프트는 eval/에 고정 커밋 |
| 권한 위반 403 100% | HTTP 응답 | role=technician으로 approve 호출 → status code 검사 |

> **인용률 strict 판정 — D54 로 해소 (구 미해소 전제)** — 실 루프(loop.py)는 tool_result 에
> **`pages`(근거 페이지 목록)** 를 항상 싣는다(근거 없는 도구·실패 결과는 빈 리스트).
> `eval/score.py` 는 `pages` 키를 실은 tool_result 가 하나라도 있으면 **strict** 로 판정한다 —
> 인용 page 가 근거 밖이거나 근거가 빈 집합이면 fail ("블록은 있고 숫자는 지어낸" 케이스를 잡는다).
> `pages` 키가 전혀 없는 event 리스트(구 trace·합성 요약본)만 "발행=근거" **degraded** 로 내려간다.
> 재생(`?replay=…`)이 남긴 이벤트는 payload 에 `replay: true` 표식이 있고(D55), 실 DB 채점
> 배선은 `eval.score.has_replay()` 로 그 세션을 분모에서 제외해야 한다 — 재생은 어떤 도구도
> 반환한 적 없는 합성 payload 라 실적에 섞이면 지표가 오염된다.

**시퀀스 판정(scenario-smoke)**: traces의 tool_call 순서를 expected.branch별 기대 시퀀스와 비교.

---

## 부록: 매뉴얼 EDA 체크리스트 (M1 Day 1)

다운로드: LS일렉트릭 공식 다운로드 센터 (ls-electric.com/ko/download, sol.ls-electric.com) — iG5A 완전본, S100 사용설명서

- [ ] 텍스트 레이어 존재 여부 (복사 가능? 스캔본이면 OCR/비전 경로)
- [ ] 에러코드(보호기능) 표 위치·페이지 범위 특정
- [ ] 표 구조: 열 구성(코드/명칭/원인/조치), 병합 셀·줄바꿈 셀 여부
- [ ] 에러코드 총 개수 (기종별) → testset 20개 선정 모수 확인
- [ ] 두 기종 간 동일 표기 코드 목록 (OL, OC 계열 등) → "같은 코드, 다른 의미" 실증
- [ ] 코드별 관련 부품 추정 가능성 (related_parts 수작업 매핑 규모 산정)
- [ ] 안전 경고문 표기 패턴 (⚠ 위험/주의 아이콘) → 가드레일 인용 소스
- [ ] 페이지 수·용량 → 청킹 전략, 임베딩 비용 추정
- 산출물: `data/analysis/manual_eda.md` + 추출 전략 결정 (파서 vs 비전 모델)
