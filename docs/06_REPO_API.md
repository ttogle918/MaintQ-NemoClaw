# 레포 구조 & API 설계 v0.2

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
│   └── seed.py                # 목업 DB 시드 (케이스 맵 구현)
│
├── mcp_server/
│   ├── server.py              # MCP 엔트리포인트
│   ├── tools/                 # 도구 (파일당 1도구)
│   │   ├── lookup_error_code.py
│   │   ├── rag_search_manual.py
│   │   ├── get_error_history.py
│   │   ├── search_inventory.py
│   │   ├── find_alternative_parts.py
│   │   ├── get_supplier_quotes.py
│   │   └── create_po_draft.py
│   └── db.py                  # 읽기 전용 커넥션 / draft INSERT 전용 분리
│
├── backend/
│   ├── main.py                # FastAPI 앱
│   ├── sse.py                 # SSE 이벤트 4종 인코더 (D14·D22, citation 오프셋 변환 D32)
│   ├── db.py                  # 백엔드 DB 커넥션 (mcp_server 와 코드 공유 안 함 — D15)
│   ├── deps.py                # X-Role/X-User 파싱 + 403 강제
│   ├── services/
│   │   └── po.py              # 신원 stamp(D37) · 상태 전이 · 표시명 매핑(D36)
│   ├── agent/
│   │   ├── loop.py            # 에이전트 루프 (도구 호출 오케스트레이션)
│   │   ├── prompts.py         # 시스템 프롬프트 (안전 가드레일 규칙 포함)
│   │   └── trace.py           # trace 이벤트 발행
│   ├── routers/
│   │   ├── chat.py            # 대화 (SSE)
│   │   ├── po.py              # 발주 승인 워크플로우
│   │   └── equipment.py       # 라인/장비 컨텍스트
│   └── rag/
│       ├── ingest.py          # 매뉴얼 청킹·임베딩 (model 메타데이터 부착)
│       └── retriever.py
│
├── frontend/                  # 화면 A(진단 콘솔) + 화면 B(승인 큐)
│
├── spikes/                    # 개발 전 기술 검증 (09_RUNTIME §4) — 회귀 테스트로 유지
│   ├── sp2_mcp_roundtrip.py   # MCP stdio 왕복 · status 반환 · D10 쓰기 격리
│   ├── sp3_sse_events.py      # SSE 이벤트 4종 · block 중간 삽입 · A1 순서
│   ├── write_tool_contract.py # create_po_draft 경계 (D10·D23·D31·D33·D34·D37)
│   └── api_contract.py        # 권한 403 · 전이 409 · D29 이력 기록
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
GET  /api/equipment/{id}/history     # 장비별 에러 이력 (이력 탭)
POST /api/equipment/{id}/errors      # 에러 발생 이력 기록 (D29) — body: {code, occurred_at?, action_taken?, part_replaced?}
                                     #   error_history INSERT. technician만. requested 주체는 X-User에서 주입
```

**D29 — 이력 기록은 명시적 액션이다.** 채팅 진입 시 자동 기록하지 않는다. 자동 기록하면 `get_error_history`의 `count`가 실제 고장 횟수가 아니라 **질문 횟수**가 되어, 같은 에러를 세 번 물어본 것만으로 `repeated=true`(S3 근본원인 모드)가 잘못 켜진다. 화면 A에 "이 고장 이력에 기록" 액션이 필요하다 — 와이어프레임 반영 대상.
MCP 도구가 아니라 백엔드 쓰기이므로 D10("도구는 po_drafts draft INSERT만")은 그대로 유지된다.

### 2.4 상태 전이 다이어그램

```
draft ──submit(정비사)──▶ pending ──approve(팀장)──▶ approved
                             └──────reject(팀장)──▶ rejected
※ MCP 도구는 draft 생성만 가능. API는 전이만 담당. 생성/전이 주체 분리.
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
