# 레포 구조 & API 설계 v0.2

> ⚠️ 이 문서는 이 레포의 **내부** API만 다룬다. FinAllQ·InsuQ와의 A2A 연동은
> `docs/A2A_CONTRACTS.md`를 보라 — 아직 M1(계약 계층) 초안 단계.

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
│   │   ├── classify_part_criticality.py  │ 확장 11종 (`full` 에서만 등록 — D69)
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

| 사용자 ID | 역할 | 표시명 |
|---|---|---|
| `tech-01` | technician | 정비사 김OO |
| `mgr-01` | manager | 보전팀장 박OO |

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
     event: tool_result { tool, status, summary, elapsed, pages?, parts? }  # trace 패널용 (완료)
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
POST /api/po/{po_id}/submit          # draft → pending   (technician만)
POST /api/po/{po_id}/approve         # pending → approved (manager만)
POST /api/po/{po_id}/reject          # pending → rejected (manager만, body: {reason} — 필수, D38)
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

### 2.8 수리 증빙 — 제출·서명·반려 (S29 · D85·D98, Sprint 9 신설)

```
GET  /api/repairs?state=pending      # 목록. **역할 무관 조회** — 정비사도 자기 요청 상태를 봐야 한다
GET  /api/repairs/{id}               # 상세. hash_verified 로 서명 해시 재계산 대조 결과를 싣는다(D84 태도)
POST /api/repairs/{id}/submit        # draft → pending    (**technician만**)
POST /api/repairs/{id}/sign          # pending → signed   (**manager만**)
POST /api/repairs/{id}/reject        # pending → rejected (**manager만**, body: {reason} 필수 — D38)
```

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

### 2.4 상태 전이 다이어그램

```
[발주 po_drafts]
draft ──submit(정비사)──▶ pending ──approve(팀장)──▶ approved
                             └──────reject(팀장)──▶ rejected

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
| 부품 특정 정확률 ≥90% | **traces 테이블** | 응답 텍스트가 아니라 다음 순서로 판정 (D66): ① `create_po_draft.input.part_no` → ② 최종 `search_inventory.input.part_no` → ③ 최종 `find_alternative_parts` 결과의 `parts` **단일 건** → ④ 최종 `search_inventory` 결과의 `parts` **단일 건**. 이 값이 expected.part_no 와 일치해야 pass. ③④를 단일 건으로 제한하는 이유는 부품명 조회가 다건을 돌려주기 때문 — 첫 항목을 정답으로 세면 에이전트가 고르지 않은 부품에 점수를 준다. **분모는 part_no가 있는 문항만** (구성: 부품 특정 대상 15 + S3형 3 + S4형 2 — 최종 확정은 사람, TODO 참조) |
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
