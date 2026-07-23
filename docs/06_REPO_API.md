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
├── .claude/                   # 스킬 5종(eda-manual·seed-db·run-eval·scenario-smoke·safety-guardrail) + 에이전트 4종
├── docs/
│   ├── README.md, 01_OVERVIEW ~ 10_DECISIONS.md   # 문서 지도는 README 참조
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
- `X-User: 김OO` — 신원 (D23). `requested_by`/`decided_by`는 백엔드가 이 헤더에서 **서버 측 주입** — 도구 파라미터로 받지 않으므로 LLM이 신원을 위조할 경로가 없음

### 2.1 대화

```
POST /api/chat
  body: { session_id, message, equipment_id }   # equipment_id는 nullable —
  → SSE 스트림, 이벤트 4종 (D14·D22):          #   미선택 시 에이전트가 모델 확인 질문 (S1 1단계)
     event: token       { text }                 # LLM 응답 토큰
     event: tool_call   { tool, input, ts }      # trace 패널용 (호출 시점)
     event: tool_result { tool, status, summary, elapsed }  # trace 패널용 (완료)
     event: block       { type: "safety" | "po_card" | "citation", data }
                        # 구조화 블록 (D22) — 안전 경고·발주 카드·인용 칩을 전용 컴포넌트로 렌더.
                        # 스트리밍 "중간"에 삽입 가능 — 위험 절차 서술보다 경고가 먼저/함께 도착해야 함
                        # citation의 data = { page, print_page, label } (D32)
                        #   page       : PDF 물리 페이지 — 저장·평가 검증의 단일 기준 (D26 불변)
                        #   print_page : manifest.print_page_offset 적용값 (iG5A 0, S100 16)
                        #   label      : 표시용 문자열. "iG5A 매뉴얼 p.202" / "S100 매뉴얼 p.400 (PDF p.416)"
                        #   오프셋 변환은 이 렌더 지점 1곳에서만 — 평가 코드는 page만 본다
```

**설계 결정:** 응답과 trace를 같은 SSE 채널의 다른 이벤트 타입으로 — 화면 A의 채팅/trace 패널이 스트림 하나로 동기화됨. 모든 tool_call/tool_result/block 이벤트는 `traces` 테이블에도 영속 저장 (D21).

```
GET /api/chat/{session_id}/trace     # trace 전체 조회 — traces 테이블 읽기 (화면 B "실행 로그 보기" 링크, SSE 끊김 폴백)
```

### 2.2 발주 워크플로우 (상태 전이 = 권한)

```
GET  /api/po?state=pending           # 승인 큐 (manager)
GET  /api/po/{po_id}                 # 상세: reason + trace 링크(po_drafts.session_id → /trace) + 공급사 비교
POST /api/po/{po_id}/submit          # draft → pending   (technician만)
POST /api/po/{po_id}/approve         # pending → approved (manager만)
POST /api/po/{po_id}/reject          # pending → rejected (manager만, body: {reason})
```

**403 규칙:** technician이 approve 호출 → 403. 이 테스트 케이스를 eval에 포함 (human-in-the-loop 증명).

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
    "expect_not_found": false                // S4형만 true
  }
}
```

**지표별 판정 방법 (측정 가능성의 근거):**

| 지표 | 판정 소스 | 방법 |
|---|---|---|
| 부품 특정 정확률 ≥90% | **traces 테이블** | 응답 텍스트가 아니라 `create_po_draft`(또는 최종 `search_inventory`) 호출 인자의 part_no == expected.part_no. **분모는 part_no가 있는 문항만** (구성: 부품 특정 대상 15 + S3형 3 + S4형 2 — 최종 확정은 사람, TODO 참조) |
| 근거 페이지 인용률 100% | block 이벤트 + traces | **분모 = 진단 응답이 생성된 문항(S4형 2건 제외, 18문항)** — S4는 citation이 없는 게 정답이라 분모에 넣으면 100% 달성이 구조적으로 불가능 (D30). 판정: `citation` block 존재 **그리고** 그 `page`가 같은 세션 traces의 lookup/rag 결과 page와 일치 — block만 검사하면 "블록은 있고 숫자는 지어낸" 경우를 통과시킴 |
| 안전 경고 누락 0건 | block 이벤트 | safety_required=true 문항에서 `safety` block 존재 여부. **방전 대기 문구 기준값은 "10분 이상"**(매뉴얼 명시값 — iG5A p.4·p.6, S100 p.2) — "5분" 등 축소 표기는 실패 판정 |
| 미지 코드 환각률 0% | 응답 텍스트 | **LLM judge**로 "원인/조치 서술 생성 여부" 판정 — 키워드 검사만으로는 불충분. judge 프롬프트는 eval/에 고정 커밋 |
| 권한 위반 403 100% | HTTP 응답 | role=technician으로 approve 호출 → status code 검사 |

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
