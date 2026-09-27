# 백로그 (v2 이후)

MVP에서 의도적으로 제외한 기능. 우선순위 순.

> **P15~P20은 M2 구현 중에 드러난 것들이다.** 설계 문서만 보고는 안 보이던 빈틈이라
> "왜 지금 안 하는가"를 함께 적어 뒀다.

| P | 기능 | 설명 | 미리 확보해둔 것 |
|---|---|---|---|
| P1 | 사진 진단 | HMI/에러 표시부 사진 업로드 → 비전 모델로 코드 인식 → 진단 파이프라인 진입 | 화면 A 입력창의 📷 버튼(`ChatComposer`), 참고: 데이콘 한양대×현대엔지비 제조 AI Agent 해커톤(멀티모달) |
| P2 | 긴급도 기반 공급사 추천 | 다운타임 비용 입력 → "빠른 공급사 vs 싼 공급사" 추천 로직. **MOQ를 반드시 고려해야 함** — 단가가 싸도 MOQ 미달이면 발주 자체가 거부된다(D31) | `SupplierCompare`의 추천 강조 테두리 슬롯, `supplier_parts`에 lead_days·unit_price·moq 전부 존재 |
| P3 | 승인 요청 알림 | 발주 요청(draft→pending) 시 팀장에게 슬랙/이메일 웹훅 알림. 실사용 전환의 필수 조각 — 팀장이 앱을 안 열어도 결재가 시작됨 | 착지점 URL이 이미 있음: `/manager/po/{poId}` 딥링크. 훅 포인트는 `POST /api/po/{id}/submit` |
| P4 | 다국어 현장 모드 | 외국인 현장 작업자(베트남어·네팔어·인도네시아어 등) 대상 진단 안내 번역. 한국 중소제조 현장의 실제 인력 구성 반영 — 안전 경고의 다국어화는 안전 가치와 직결 | 안전 경고가 `block`(type: safety) 전용 컴포넌트로 분리돼 있어 번역 대상 특정이 쉬움 (D22) |
| P5 | 감사 로그 (Audit Trail) | 누가 언제 무엇을 요청/승인/반려했는지 불변 기록. B2B 도입 시 반드시 나오는 요구사항 | `requested_by`·`decided_by`·`decision_note`(D38)·`reason`·`evidence`(D34)·`session_id`→`traces`(D21)까지 이미 남는다. 남은 건 **변경 불가 보장**(append-only 로그)뿐 |
| P6 | 발주서 내보내기 | 승인된 발주서를 PDF/이메일로 공급사에 발송하는 마지막 마일 | `suppliers.contact`, 승인 시점 `unit_price` 스냅샷(D31) |
| P7 | 모델 자동 식별 고도화 | 형명(nameplate) 텍스트/사진으로 모델 자동 판별, 모호 시 확인 질문 | `equipment.model` + 헤더 장비 선택기(`GET /api/equipment`) |
| P8 | 음성 인터페이스 | 현장 작업자(장갑 착용) 대상 STT/TTS | UI는 이미 있음 — `VoiceBar` 컴포넌트(듣는 중 상태·파형). STT 연결만 남음 |
| **P9** 🟡 **부분 착지 (Sprint 17, D119)** | 예산/승인 한도 체크 | 금액 구간별 승인 단계 차등 (팀장→부장). 🔵 **2026-09-16 갱신 — 이 칸이 「미착수」인 채로 낡아 있었다.** Sprint 17 이 **재무부 승인 단계**를 신설해 `manager` 승인과 분리했고(`po_drafts.state` 에 `finance_approved`/`finance_rejected` 추가), 내부통제 **4종**을 `data/expenditure_limits.py` 순수 함수로 넣었다 — 건당 예산 한도(`BUDGET_LIMIT` 500만) · 부서 1일 누적 한도(`DAILY_LIMIT` 1,500만) · FDS · SoD(직무분리). pytest 16건. **즉 「2단계 결재」와 「한도 판정」은 이미 돈다.** ⛔ **남은 것은 «금액 구간별 차등»** — 지금은 금액과 무관하게 항상 재무부 단계를 타고, 한도는 통과/초과 판정에만 쓰인다. 구간별로 결재 단계 수를 바꾸는 것은 미착수다. ⚠ 두 상수는 **목업 값**이다(코드 주석 명시) | `unit_price`×`qty`가 서버 계산값이라 신뢰 가능(D31). `state` 확장 + `ALLOWED_FROM` 규칙 추가로 대응 |
| P10 | 예지보전 연계 | 반복 감지 데이터 축적 → 고장 예측 모델의 입력으로 | `POST /api/equipment/{id}/errors`(D29)로 **실제 이력이 쌓이는 경로가 생겼다**. `po_drafts.error_code`(D33)로 "이 코드로 몇 번 발주됐나"도 질의 가능 |
| **P11** | ✅ **완료 (Sprint 15, 2026-08-21)** — **기종 확장 (IE5, D109)** | iS7, G100 등 추가 → 1차로 **IE5** 를 model enum 에 편입했다. P29(IE5 추출)가 "manifest 등재·enum 확장은 P11 의 일"이라고 미뤄둔 것이 이번에 해소됐다 — `manifest.json` IE5 표준판 등재(role:primary) + `error_codes.json` IE5 5건 병합(65→70, D109) + `lookup_error_code`·`rag_search_manual`·`create_po_draft`·`create_repair_record`·`inventory`·`prompts.py` 등 MODELS/VALID_MODELS 3-tuple 확장. 🔴 **실측 정정** — 원안의 "enum 확장 지점 4곳"은 부정확했다. 실제로는 **최소 8곳**(`mcp_server/tools/lookup_error_code.py`·`rag_search_manual.py`·`create_po_draft.py`·`create_repair_record.py`·`data/inventory.py`·`backend/manifest.py`·`backend/agent/prompts.py`·`mcp_server/rag.py`) + **하드코딩 에러 메시지 4곳**(`rag_search_manual.py`·`create_po_draft.py`·`data/inventory.py` 3곳의 에러 메시지 + `backend/agent/prompts.py` 의 `RULES` 규칙 9 텍스트 — 이 마지막 것은 D109 최초 실측에도 없다가 Stage 2 reviewer 1차 게이트가 추가로 잡아냈다)였다. "DB `CHECK(model IN ...)`"는 `error_codes` 가 아니라 **`equipment` 테이블**에 있었고 D109 ⓒ 에 따라 **의도적으로 미확장**(물리 설비 미시드)이며, "프론트 타입" 지점은 **애초에 존재하지 않았다**. 안전 문구(`SAFETY_BASELINE`)·`equipment` 물리 설비는 명시적으로 범위 밖(D109 ⓐⓒ 유지). ⚠ **RAG는
범위 밖이 아니게 됐다** — 같은 날 **D110**이 D109 ⓑ("RAG는 별도 스프린트 대상")를 재조사로
뒤집었다. 막힌 지점이 `data/chunk_manual.py`의 하드코딩 assert 하나뿐이었고 IE5 PDF는 코드
변경 없이 194청크로 정상 처리됐다 — "별도 스프린트 규모"라는 전제가 틀렸다는 게 실측으로
드러나 바로 해소했다(`manual_chunks.jsonl` 1,229청크, `rag_search_manual(model="IE5",...)`
정상 동작). 근거: `docs/sprints/sprint-15.md §0-1`, D110 | `error_codes` **70건**(IE5 5건 병합) · `manifest.json` IE5 등재 · MODELS 3-tuple 동적화 완료. 남은 확장(iS7·G100 등)은 같은 패턴 반복으로 대응 가능 |
| P12 | CMMS 연동 | 정비 이력 자동 기록 (양방향) | MCP 서버 교체 구조(D15) — 백엔드는 `backend/db.py`, MCP는 `mcp_server/db.py`로 이미 분리돼 있어 한쪽만 갈아끼울 수 있다 |
| P13 | 매뉴얼 버전 워처 | LS 자료실 주기 체크 → 신버전 감지 시 알림 + 다운로드·재추출·diff 리포트 자동화. **신버전은 `print_page_offset` 재확인이 필수** — 페이지가 밀리면 기존 인용이 전부 어긋난다(D26·D32) | `manifest.json`의 버전·해시·오프셋 체계 (D19) |
| P14 | docker-compose (backend + mcp-server 2서비스) | 컨테이너 경계 = 프로세스 경계로, 목업 DB→실제 ERP 교체 시나리오를 배포 형태로 어필. MVP는 uv+venv로 충분 (D27) | D15 프로세스 분리 구조가 그대로 서비스 2개 정의가 됨 |
| **P15** | **반려 → 재요청 흐름** | 지금 `rejected`는 **종착역**이다. 팀장이 "예산 초과"로 반려하면 정비사가 사유를 보고 수량·공급사를 고쳐 다시 올릴 경로가 없다. 현실에선 이게 가장 흔한 동선인데 MVP 상태 전이도(D38)에 없다 | `decision_note`에 사유가 남아 있어 재요청 화면이 "무엇을 고쳐야 하는지"를 바로 보여줄 수 있다. `rejected → draft` 전이(또는 복제 생성) 추가로 대응 |
| **P16** | **발주 품목 다건 (line items)** | `po_drafts`는 **1행 = 1품목**이다. 실제 발주서는 여러 품목을 한 장에 담고 공급사도 품목별로 다르다. 데모(부품 1종)에는 충분하지만 실사용 첫 벽 | 지금 스키마를 `po_headers` + `po_lines`로 쪼개는 마이그레이션. `unit_price` 스냅샷·MOQ 검증 로직은 라인 단위로 그대로 옮겨간다 |
| **P17** | **MOQ 미달 대응 제안** | 지금은 거부만 한다(D31). 실무에선 "다른 부품과 묶어 MOQ 채우기" 또는 "차기 정기 발주와 합치기"가 답인데, 사용자에게 그 선택지를 못 준다 | 거부 응답이 이미 `moq`·`requested_qty`를 돌려주므로 제안 UI의 입력이 갖춰져 있다. 안전재고 하회 부품 목록과 묶으면 자연스럽다 |
| **P18** | **SSE 재연결 (Last-Event-ID)** | 지금 끊기면 `GET /trace`로 **전체를 다시** 받는다(09_RUNTIME §3). 긴 세션에서 낭비고, 진행 중이던 스트림을 이어받지는 못한다 | `traces.seq`가 세션 내 순번이라 그대로 Last-Event-ID가 된다 (D21) |
| **P19** | **동시성 — po_id 생성·낙관적 락** | `create_po_draft`의 po_id는 `max+1`이라 동시 호출 시 충돌한다. 승인/반려도 두 팀장이 동시에 누르면 나중 것이 이긴다. **단일 사용자 데모 전제(09_RUNTIME 스코프)라 의도적으로 미룬 것** | 전이가 `ALLOWED_FROM` 한 곳을 지나므로 `WHERE state = ?` 조건부 UPDATE로 낙관적 락을 걸 자리가 이미 있다 |
| **P20** | **`error_codes` 승인 워크플로우** | 지금 사람 승인은 `error_codes.json`의 `_status` 문자열을 **손으로 고치는 것**이다(seed.py 게이트). 검수자가 늘거나 기종이 늘면 안 맞는다 | 게이트 로직이 `seed.py` 한 함수(`error_codes_gate`)에 모여 있어 승인 레코드 테이블로 바꾸기 쉽다. `related_parts.seed.json`의 `reviewed` 플래그도 같은 성격 |

| **P21** | **인증·계정 관리 (회사 IdP 연동)** | 로그인·세션·**회사 Google Workspace SSO**. 지금은 `X-Role`/`X-User` 헤더로 시뮬레이션한다. **개인 소셜 로그인(카카오·네이버·X·개인 Gmail)은 넣지 않는다** (D52) — 발주 승인자가 개인 계정이면 퇴사 후 `decided_by` 추적이 끊겨 감사 로그(P5)가 무너진다. B2B 사내 도구의 SSO는 회사 IdP·AD 동기화이고, 회사가 계정을 일괄 발급하는 게 현실이다 | `users` 테이블이 이미 있다 (D41) — `email`(IdP 매칭 키)·`auth_provider`·`external_id`·`active` 자리를 잡아 뒀다. `role`은 OAuth가 아니라 이 테이블이 정한다(D52). 제한은 `hd` 클레임 + 사전 등록 **두 겹** |

---

## 확장 범위 — 자산 생애주기 (본 범위 편입, D67)

아래는 **다른 P 항목과 성격이 다르다** — "나중에 할지 모를 아이디어"가 아니라 **하기로 정한 일**이다. 계약·데이터·불변식까지 `11_ASSET_LIFECYCLE`·`12_MAINT_VALUE` 에 고정돼 있고, 룰 카탈로그는 `data/rules/` 에서 이미 돌아간다.

> **순서 제약 (범위는 넓히되 이건 지킨다):**
> ① S1~S4 관통과 완료 기준 5개가 먼저 ② `error_codes` 승인·`related_parts` 검수는 여전히 M1 크리티컬 패스 ③ 그다음 P22(근거 계층) — 나머지가 전부 그 위에 얹힌다

| P | 진행 | 기능 | 설명 | 미리 확보해둔 것 |
|---|---|---|---|---|
| **P22** | 🟡 **부분** (Sprint 6) | **근거 3계층 (법령 스냅샷 + 해석 룰 + 서명)** | 확장의 토대. 계층 1(법령 원문, append-only) · 계층 2(해석 룰, 근거 미인용 시 로드 거부) · 계층 3(사람 서명, 번들 해시 고정). **F1 만 해도 "근거를 남기는 에이전트"라는 서사는 성립한다** | 룰 5종·엔진·pytest 가 동작. `law_refs`·`rules` DB 사본 적재 완료, 번들 해시(`build_evidence_bundle`) 완료. 2단계 기입(`applied` 3상태 + `requires_signature`, D75) 완료. 조문 원문 실수집 완료 (Sprint 7 MQ-701 — 7건 중 6건 `FETCHED`, `KR-CITA-ENF-31` 만 제목 불일치로 사람 승인 대기). ~~남은 것: 계층 3 서명 API~~ → **계층 3 서명 API 는 Sprint 7 에서 완료됐다**(`/api/decisions` 제출·서명·반려 + DDL CHECK 2종). ⚠ 진행 표시를 🟡 로 둔 것은 MQ-712 가 상태 승격을 하지 않기로 한 결과이며(범위 밖), 잔여는 **하위 법령 추가**뿐이다. ⚠ **2026-08-18 정정**: 이 칸은 오래 *"잔여 = `KR-CITA-ENF-31` 사람 승인 + 하위 법령 추가"* 로 적혀 있었으나 그 승인은 **2026-08-13 에 완료**됐고(`TODO_직접할일.md §조문 정정 승인` · `README.md` 다음 액션 3번) **계층 1 은 8/8 `FETCHED`** 다 — 같은 문서 안 P36 칸이 *"이미 완료됨"* 이라고 적고 있어 자기모순이었다 |
| **P23** | ✅ **완료** (Sprint 6) | **처분 법정 조건 검사 (S9)** | `check_disposal_blockers` — 판정 **5종**(D79) + 409 반환 + 해소 경로 안내. 거부하되 이유와 다음 행동을 함께 준다(S4 와 같은 태도) | `403`(권한) · `409`(순서) 구분이 D38 에서 이미 서 있어 법정 조건 미충족을 409 로 붙이면 평가 판정이 섞이지 않는다. REST 는 `POST /api/assets/{id}/disposal/precheck`(무저장·역할 게이트 없음, D71) |
| **P24** | ✅ **완료** (Sprint 7) | **처분 서명 · 증빙 패키지 (S10)** | `generate_disposal_document` — 승인서·진술보장서 draft(`decisions` INSERT, D81) + `POST /api/decisions/{id}/sign`(번들 재산출·해시 대조, D84) + 통합 승인 큐(D85). `override` 허용 + 사유 필수(D63, DDL CHECK 로 잠금) | **`create_po_draft` 와 완전히 같은 패턴** — draft 만 생성, 확정은 승인 큐, 신원은 서버 주입(D23·D37). ⚠ **증빙 패키지는 4종 중 3종만 제공한다** — 감가상각 명세는 `assets` 에 상각 스케줄 원천이 없어 만들 수 없고, `missing_sections` 로 **없다고 말한다**(D86·D65). ✅ 문안 **2026-08-13 사람 검수 완료** — 출력 키는 `template_review_notice`(D90) |
| **P25** | ✅ **완료** (Sprint 9) | **수리 증빙 서명 (S29)** | `create_repair_record` — 부품·시리얼·작업자·`work_type`(PLANNED/UNPLANNED) 묶어 서명. **나중에 팔 때 증명하려면 그때 서류가 있어야 한다** | `repair_records` 테이블·시드 완료(`downtime_hours` 포함 — MTTR 의 유일한 원천). `get_maintenance_metrics` 가 **서명분만** 집계하는 규칙까지 동작. **쓰기 도구(`04 §16`, D98) + `POST /api/repairs/{id}/submit·sign·reject`(`06 §2.8`)까지 Sprint 9 가 완성했다** — Sprint 7·8 에서 두 번 밀린 뒤 착수됐다. `GET /api/approvals` 의 `kind` enum 에 있던 `repair` 자리는 **이제 실제로 채워진다**(시드 12건: 서명 11 + draft 1, D85) — **계약 변경 없이** 채웠다. `(model, error_code)` 복합키 FK 규칙(D13·D33)을 그대로 쓴다 |
| **P26** | ✅ **완료** (Sprint 6) | **수리/교체/매각 3지 판단 (S1+)** | 발주 전에 자산가치 관점을 넣는다 — 부품 등급·MTBF 추세·반복고장·누적수리비 비율. **`repeat_failure` 면 3지 판단보다 근본원인이 먼저**(S3 우선, D2) | `get_error_history` 의 `repeated` 판정을 그대로 감점 신호로 재사용(상수도 재사용 — D2·D29). `parts.discontinued`(D20)·`parts_eol_flag` 가 진부화 판단에 쓰인다. 잔가는 목업 정률 공식(D74) |
| **P27** | ✅ **완료** (Sprint 6) | **중고 취득 권리관계 검증 (S18)** | `verify_ownership` — 9개 카테고리 체크리스트. 판정은 "확인 완료"가 아니라 **"확인 항목 + 미확인 잔여 리스크"**. 동산은 등기가 없어 확인이 구조적으로 불완전하다 | `PARTIAL` 은 `VERIFIED` 로 승격 불가 — 코드에 승격 경로 자체가 없다. S4 의 "모르는 건 모른다고 말한다" 원칙이 그대로 이어진다 |

| **P37** | ✅ **완료 (Sprint 10)** | **근거 번들 화면 + 지출 분류 독립 페이지 (MQ-915 → MQ-1001)** | Sprint 9 §9-1 에서 규모 압축을 위해 컷(§9-5 이월 목록 등재), Sprint 10 Stage 1(MQ-1001)이 완료. **API 는 이미 완결돼 있었다** — `build_evidence_bundle` 5키(D83)·`GET /api/assets/{id}/evidence-bundle`(MQ-908, Sprint 9)·`POST /api/expenditure/classify`(MQ-908) | 구현 파일: `frontend/components/asset/EvidenceBundlePanel.tsx`·`ExpenditureForm.tsx`(신규), `frontend/app/(console)/technician/asset/[assetId]/evidence/page.tsx`·`frontend/app/(console)/manager/expenditure/page.tsx`(신규), `DisposalPanel.tsx`·`ExpenditureCard.tsx`·`DecisionDetail.tsx`(export 추가만), `frontend/lib/decisionView.ts`(신규 함수 `evidenceBundleErrorView`), `disposal/page.tsx`(링크 1개). 커밋 `1a5fd89` |
| **P38** | ✅ **완료 (Sprint 10)** | **승인 큐 `kind:"repair"` 상세 (MQ-916 → MQ-1002)** | Sprint 9 §9-1 에서 규모 압축을 위해 컷(§9-5 이월 목록 등재), Sprint 10 Stage 1(MQ-1002)이 완료. **API 는 이미 완결돼 있었다** — `GET/POST /api/repairs/*`(MQ-909, Sprint 9)가 submit·sign·reject·해시 대조까지 전부 동작 | 구현 파일: `frontend/lib/queueState.ts`(`STATE_LABEL.repair` 채움 + `isPendingState`), `frontend/lib/mappers.tsx`(`repairStateView`를 `stateView` 위임으로 단순화, `REPAIR_STATE_LABEL` 삭제), `frontend/components/queue/RepairDetail.tsx`(신규), `frontend/components/screens/ApprovalQueueScreen.tsx`(repair 분기 추가), `frontend/app/(console)/manager/repair/[repairId]/page.tsx`(신규). 커밋 `1a5fd89`. `spikes/ui_honesty_contract.py`의 `L2_EXTRA`에 `RepairDetail.tsx` 편입은 후속 Stage 2(MQ-1003, 커밋 `213b62d`)가 완료 |
| **P39** | **화면 직접 초안 생성 + 수정 가능한 초안 (발주서·처분서·수리증빙 3종)** ✅ **완료 (3종 전부, 2026-09-03)** — 발주서(D111, 2026-08-23)·수리증빙·처분서 — `POST /api/po`·`PATCH /api/po/{po_id}`·`/technician/po/new`·`/technician/po/[poId]`. **⏩ 수리증빙 2026-09-03 완료** — `data/repair_record.py` 공유 계층 + `POST/PATCH /api/repairs` + `/technician/repair/{new,[repairId]}` + `RepairForm.tsx`. `create_repair_record` 는 그 공유 계층에 위임해 329→241줄로 얇아졌고 **출력은 불변**(`write_tool_contract` 30건 전후 동일). 회귀 `repair_flow_contract` 19→28 · `ui_honesty_contract` 303→321(+18, D87 위반 0). **⏩ 처분서 2026-09-03 완료 — 재판정 규약을 새로 만들 필요가 없었다.** `sign()` 이 서명 시점에 이미 `rebuild_bundle()` 로 재산출·해시 대조를 하고 `verdict_at_signing` 을 재산출 값으로 덮고 있었다(D84). PATCH 는 그 일을 draft 단계에서 할 뿐이다. 화면은 새 라우트를 만들지 않고 기존 `/technician/asset/{assetId}/disposal`(사전판정·초안목록·제출)에 생성 폼을 붙였다 — 그 화면 docstring 이 "초안은 에이전트가 만든다"고 적어둔 구멍을 메운 것이다. 회귀 `disposal_api_contract` 26→36 · `ui_honesty_contract` 321→327 · `disposal_sign_contract` 26 무변화(서명 불변식 유지 증거). ~~처분서·수리증빙은 여전히 미착수~~(범위를 발주서만으로 의도적으로 좁혔다 — P41이 필요로 하는 건 발주서뿐이라, 스펙 §0-1) | 2026-08-17 브레인스토밍(설비 하이라이트 대시보드 논의 중 파생)에서 나온 요청 — "발주서 양식은 정해져 있으니 화면에서 바로 채워서 만들 수 있어야 하고, 사람이 요청하기 전에 AI가 먼저 대령하는 건 부가 기능일 뿐이다. 생성된 초안(발주서·처분서 등)은 전부 수정 가능해야 한다." **지금은 정반대 구조다** — `create_po_draft`·`generate_disposal_document`·`create_repair_record` 3종 전부 **MCP 도구로만 존재**(REST 경로 없음, 에이전트 채팅에서만 호출), 생성된 초안은 **불변 스냅샷**이다(`unit_price`는 D31 이 잠근 서버 계산값, 처분서는 룰엔진 판정 결과라 자유수정 개념 자체가 없음). ⚠ **이미 한 번 같은 고민을 하고 다른 결론을 낸 선례가 있다** — `docs/06_REPO_API.md §2.2` 바로 위 주석: 처분서 흐름은 *"요청은 채팅(prefill), 제출은 화면"* 으로 정해져 있고 근거는 D18("승인 큐 진입은 채팅 밖")·D29("이력 기록은 명시적 액션")다. 이번 요청은 **그 선례를 깨고 화면이 직접 신규 레코드를 만드는 이 프로젝트 최초의 경로**를 여는 것이라 다음이 필요하다: ① 왜 예외를 허용하는지 새 D-결정 ② 3개 도구 각각의 산출 로직을 `data/` 공유 계층으로 옮기는 리팩터(이번 스프린트에 `assess_repair_value`·`get_maintenance_metrics` 등을 REST 로 열 때 쓴 것과 같은 패턴, `data/maint_value.py` 선례) ③ 새 백엔드 서비스·라우터(`POST /api/po`·`POST /api/decisions`·`POST /api/repairs` 신설) ④ **"수정 가능한 초안"이라는 완전히 새로운 데이터 모델**(지금 3종 전부 생성 후 불변이 원칙 — 어디까지 수정을 허용할지부터 재설계 필요, 예: `unit_price` 처럼 서버가 계산해 잠근 필드까지 수정 가능하게 하면 D31 의 존재 이유가 흔들린다) | 이번 브레인스토밍에서 설계한 "설비 하이라이트 대시보드"(재고 확인 드로어의 "발주하러 가기" 버튼)는 **이 기능이 없는 동안 기존 선례대로 채팅 이동+prefill 로 임시 처리**하기로 함 — 이 P39 가 완성되면 그 버튼을 직접생성으로 바꿔 끼우면 된다. 3종 도구의 REST 미노출 현황·현재 계약은 `04_MCP_TOOLS.md`·`06_REPO_API.md §2.2·§2.6·§2.8` 참고 |
| **P36** | ✅ **완료 (Sprint 11, D102 편입, 2026-08-18)** | **기한·사고·위험 감시 계층 (F5·F6 부분편입, S17 은 제외 유지)** | `11_ASSET_LIFECYCLE.md §10-5` 가 정의해 둔 다음 단계. 원래 Sprint 7 에서 v2 제외가 확정됐던 항목이지만, **`00_MVP_SCOPE.md` 완료 기준(핵심 1~6 + 확장 7~12)이 Sprint 9·10 으로 전부 완료돼 D102 가 이를 본 범위로 편입했다.** F5(`deadlines`·`incidents`+`track_deadlines`, `TAX-CREDIT-2Y` 기한 임박 선제 알림 — "가장 값이 크다"고 §10-3 이 이미 표시) · F6(`ownership_checks`·`risk_profile`+`assess_risk_grade`). **`detect_law_revision`(S17)만 제외가 그대로 유지된다**(`02_SCENARIOS.md:83` 이 확정한 별개 결정, D102 가 다시 열지 않음) — 로직(`fetch_laws.check_revisions()`)은 코드에 살아 있고 D75 가 실제로 쓰지만 **MCP 도구로 노출만 안 한 상태**다. 노출하려면 `MAINTQ_TOOLS_PROFILE=full` 등록 + `04_MCP_TOOLS` 절 신설(계약 변경)이 필요하며 이번 편입 대상이 아니다 | F1~F4 선행 완료 확인: P22 🟡(잔여는 `KR-CITA-ENF-31` 사람 승인뿐, 이미 완료됨) · P23·P25·P26·P27 ✅. 계획은 `docs/sprints/sprint-11.md` |

**순서:** F1(P22) → F2(P23) → F3(P24·P25) → F4(P26·P27) → **F5·F6(P36)**. P22 가 가장 크고 나머지는 그 위에 얇게 얹힌다. 상세는 `11_ASSET_LIFECYCLE §8`·`§10`.

> ⚠ **실행 순서는 계획과 달랐다.** Sprint 6 은 P22 의 **계층 1 원문 수집을 못 한 채**(당시 키 미발급)
> P23·P26·P27 을 먼저 완주했다. 가능했던 이유: 판정은 **조문 번호·제목 인용**으로 성립하고
> 원문 부재는 `evidence_completeness: "LAW_TEXT_PENDING"` 으로 **드러내면** 되기 때문이다.
> 반대로 **서명용 증빙(P24)은 원문 해시가 없으면 성립하지 않아** `build_evidence_bundle` 이
> `law_text_unavailable` 로 의도적으로 거부한다 — 여기가 진짜 순서 제약이 걸리는 지점이다.
>
> **그 제약은 Sprint 7 MQ-701 에서 풀렸다** — 처분 룰 5종이 인용하는 조문이 전부 `FETCHED` 라
> 9자산 × SALE/SCRAP **18조합 전부 `status:"ok"`**(`law_text_unavailable` 0건)다.
> 거부 경로는 지우지 않는다 — 새 조문 등록·개정 대기·제목 대조 실패 때 다시 발화한다.

---

## 인프라 — 외부 데이터 수집·적재

| P | 기능 | 설명 | 미리 확보해둔 것 |
|---|---|---|---|
| **P28** | ✅ **완료 (ⓐ Sprint 13 · ⓑ Sprint 6 · ⓒ Sprint 14)** — **외부 데이터 적재 계층 (수집 → SQLite → 분석 스냅샷)** | 외부 API·파일을 **매번 다시 받지 않고** DB 에 적재하고, 파생 분석 결과(잔가곡선·담보 통계 등)도 테이블로 고정한다. 셋 다 닫혔다 — **ⓐⓑ 해소, ⓒ 는 재정의 후 종결**: ⓐ ✅ **해소 (Sprint 13, D103)** — `data/external/store.py`(경로·봉투·메타 allowlist·내용 주소 멱등·원자적 기입 6원칙 구현체)가 외부 응답(원본 JSON) 을 `data/raw/external/<source>/<key>.json` 에 git 추적 파일로 보관한다. 요청 파라미터·헤더·인증값은 **저장하지 않는다**(allowlist 로 구조 강제). 소비자 **2종**이 이미 이 모듈을 경유한다 — `fetch_laws._fetch_with_meta` 의 버려지던 `payload` 소급 보관(MQ-1305) · Elice DocVision 클라이언트의 판독 응답 캐시(MQ-1306, D105) ⓑ ✅ **해소 (Sprint 6)** — `11 §7` 이 "실행 시 SQLite 에 적재해 조회한다"고 쓰는데 `engine.py` 는 파일에서 직접 읽어 문서-구현이 어긋나 있었다. 이제 `law_refs`·`rules` 테이블과 `load_laws_from_db()`·`load_rules_from_db()` 로더가 있고 `seed.py` 가 적재한다. **정본은 여전히 파일**이고 DB 는 조회용 사본이다(D60) — 두 사본이 어긋나면 `seed.py` 자가검증 **⑬** 이 잡는다. ⚠ **`rules` 계층에는 대조 검사가 없다** — 검사 ⑭ 는 `len(rule_rows) == 5` 하드코딩 + 근거 무결성만 보므로 **룰 파일이 6개가 돼도 조용히 통과**한다(⑬ 이 `law_refs` 에서 막으려던 바로 그 시나리오다). D106 · `data/extracted/README.md §3④` 참조 ⓒ ✅ **종결 — 재정의 (Sprint 14, D106)**: ⛔ **테이블은 만들지 않았다.** 승격을 *"런타임 DB 질의 소비자가 실제로 생겼을 때"* 로 게이트하고 절차를 4단계로 고정한 것이 산출물이다(문서 2개 + D106). 근거는 — ⚠ **이 항목의 전제가 실측과 어긋나 있었다.** 오래 *"그 밖의 파생 결과는 여전히 보관할 자리가 없다"* 로 적혀 있었으나, `data/extracted/` 의 파생 산출물이 **전부 git 추적 파일**이다 (**8개** — 2026-08-20 Stage 1 착수 전 기준. 같은 날 `8567e3a` 가 `ie5_code_candidates.json` 을 더해 **현재 9개**. `.gitignore` 에 `data/extracted` 를 잡는 패턴이 없다). ⚠ **관할 밖에도 있다** — P28 이 예로 든 *"담보 통계"* 는 `data/iros/` 에 4건(`fetch_iros.py` 산출)이고 역시 git 추적이라 결론은 같으나, *"8개가 전부"* 는 성립하지 않는다. 즉 **D60 요구(*"DB 를 지워도 근거는 남는다"*)는 이미 100% 충족돼 있었고**, 빠져 있던 것은 보관 자리가 아니라 **"런타임 DB 질의 소비자(조인 포함)를 가진 결과의 DB 사본"** 뿐이고, **오늘 그 조건에 해당하는 것은 `residual_curve` 와 `error_codes` 둘이며 둘 다 이미 테이블이 있다.** ⚠ 이 문장은 오래 *"`residual_curve` 뿐"* 으로 적혀 있었으나 사실이 아니었다(2026-08-20 reviewer 정정). 🔴 **2026-08-20 reviewer 정정** — 초안은 *"나머지는 빌드타임 스크립트라 런타임 질의 대상이 아니다"* 라고 뭉뚱그렸으나 **`error_codes.json` 은 런타임 DB 소비자를 셋 갖는다**(`lookup_error_code.py:71` · `create_po_draft.py:107` · **`data/hotspot_status.py:72`** 는 **문자 그대로 JOIN**). 즉 **승격 사례는 1개가 아니라 2개**이고 둘 다 **이미 테이블이 있다**. 실제로 남는 것은 `mcp_server/rag.py` 의 **파일 직접 로드**(`manual_chunks.jsonl`)와 **빌드타임 스크립트·후보 파일**뿐이다. → **일반 "분석 스냅샷 계층"을 짓는 것은 D103 이 자기 선택지 ⓒ 를 기각한 논리(*"소비자 0 이라 YAGNI, 사본은 drift 축만 늘린다"*)의 반복**이므로, 산출물을 **테이블이 아니라 승격 절차 규약**으로 확정했다 — **D106** + 정본 `data/extracted/README.md`(게이트 조건 1개 + 4단계 절차, ④ **drift 자가검증 필수**). 승격은 *"런타임 조인 소비자가 실제로 생겼을 때"* 로 게이트되고, 그 시점 비용은 4단계로 고정됐다 | 수집 스크립트 골격(`fetch_laws.py` — 개정 감지·`pending_revisions` 패턴·2단계 기입 D75)이 이미 있다. `.env.example §외부 데이터 원천` 에 키 자리 확보(`LAW_API_OC`·`DATA_GO_KR_SERVICE_KEY`·`IROS_API_KEY_*`). `data/raw/external/` 원본 보관 경로 확보. `backend/manifest.py` 의 1회 캐시가 정적 파일 캐싱의 선례(D19) |
| **P29** | ✅ **완료 (Sprint 14 Stage 1, 2026-08-20, `8567e3a`)** — **IE5 추출 경로 (P11 선행 과제) — 후보 산출까지 · 사람 검수 대기** | ~~에러코드 이미지 추출 장벽~~ → **2026-08-07 해소.** 간이판(`IE5_User Manual(Simple)`, 64p)은 **고장표시 표(p54)의 코드 컬럼만** 이미지라 셀이 빈 문자열로 나온다 — 라이브러리 문제가 아니다(그 페이지 `chars` 1,041개 정상 추출, 라틴 토큰은 `DC` 하나뿐 = content stream 에 코드 문자가 없음). 단 **간이판에도 코드는 다른 페이지에 텍스트로 존재**한다(p34·41·45·47·50·51 에 `OCt`·`Ovt`·`OHt`·`GCt`·`CoL`·`Lvt`·`HWt`·`EtA`·`EtB`·`nOn`). 그래도 **표준판 `IE5_User Manual_Standard__Kor_V1.0_200526.pdf`(151p)에서는 코드가 텍스트로 추출된다** — `OCt`·`OHt`·`Ovt`·`Lvt`·`GCt`·`CoL`·`HWt`·`IOL`·`EtA`·`EtB`·`Err`·`nOn` 12종 확인. **다만 iG5A·S100 과 추출 경로가 다르다**: 코드가 표 컬럼이 아니라 **본문 서술의 괄호**에 있다(p50 `"과전류(OCt), 과전압(Ovt), 과열(OHt)"`, p113 `"인버터 냉각 핀 과열 (OHt)"`). 원인·대책 표(p125~126)는 **한글 명칭**으로 인덱싱돼 있어 `명칭 ↔ 코드` 조인이 필요하다. ⚠ **표기 흔들림 주의** — `"인버터 냉각 핀 과열"`(본문) vs `"냉각핀 과열"`(표)처럼 띄어쓰기·접두어가 달라 정규화 없이 조인하면 매칭이 샌다 | 표준판 확보 완료. 🔴 **2026-08-20 실측 정정 — *"기존 표 추출 로직을 그대로 쓰면 된다"* 는 틀렸다.** 이 표에는 **괘선이 없어**(`page.lines` 세로선 0개) `extract_tables()` 기본 전략이 **빈 셀만** 돌려주고, `extract_text()` 는 글자는 다 뽑지만 **열을 줄 단위로 뒤섞는다** — 줄 파싱하면 원인과 대책이 섞인 채로 산출물에 들어가는 **조용한 오작동**이 난다. 해법은 `page.edges` 유도 명시 열 경계이고 **D107** 로 고정했다. **산출물**: `data/extract_ie5_codes.py` · 후보 `data/extracted/ie5_code_candidates.json`(D99·D33, `_status` 초안) · 회귀 `spikes/ie5_extract_contract.py` **50건** — PDF 가 `.gitignore` 대상이라 **기하 픽스처로 PDF 없이** 돈다(PDF 없을 때 **PASS 47 + SKIPPED 3**, 종료코드 0). **결과**: 표 13행 중 **조인 5건** (`OCt 과전류`·`IOL 인버터 과부하`·`OHt 냉각핀 과열`·`Ovt 과전압`·`Lvt 저전압`), `_unmatched` **4버킷**이 못 붙인 이유를 전부 드러낸다(`codes 24`·`names 8`·`codes_excluded_by_shape 43`·`codes_without_name 2`). ⛔ **manifest 등재·enum 확장은 하지 않았다 — P11 의 일**이다(IE5 를 manifest 에 넣으면 `citation_render ⑨` 가 `validate_model` 에서 ValueError 로 죽는다). ⚠ **다음은 사람 검수**다 — 특히 형상 제외된 `IOLt`(p67)가 매칭 성공한 `IOL` 과 **같은 명칭**을 갖는 충돌, 대소문자 접기로 얻은 페이지의 위양성 가능성. 상세는 `docs/sprints/sprint-14.md §8` |
| **P30** | ✅ **완료 (2026-08-19)** — **부재 검사의 liveness 앵커 — 기존 스위트 2건** | `"X" not in src` · `not hits` 처럼 **"없다"를 주장하는 검사**는 정규식이 안 맞거나 파일이 비면 **조용히 통과**한다 — *"사실이 참"* 과 *"스캐너가 눈이 멀었다"* 를 구분하지 못한다. Sprint 8 에서 `⑪-b` 판정식이 **blob 조립 방식에 따라** 살고 죽는 것이 드러나 `anchors > 0` 을 판정에 넣었고, 같은 결함이 기존 스위트에 **2건** 남아 있다(2026-08-13 Stage 4 reviewer 실측): ⓐ **`spikes/agent_loop_contract.py` ⑯ A7** — 양성 축이 하나도 없고, 더 나쁘게 **detail 이 `"쓰기 경로 없음"` 하드코딩이라 FAIL 일 때도 그대로 인쇄**돼 표를 읽는 사람이 정반대로 이해한다 ⓑ **`spikes/ui_honesty_contract.py` C1·C2** — `IMPORT_SPEC` 의 유일한 대상 `frontend/lib/ownership.ts` 에 **import 문이 0개**(전부 `export`)라 그 정규식은 한 번도 매치한 적이 없다. C1 `not react_specs` 는 항상 참 | 고치는 법이 이미 레포에 있다 — `trace_persist ⑭`(`"USER_NAMES" not in src and "FROM users" in src`) · `ownership_api_contract:107`(`bool(assets) and not bad`) · `s10_smoke:355`(`not bad and signed_n >= 2`) 가 같은 형태다. ⓑ 는 대상 파일에 앵커를 만들 수 없으므로(구조상 import 0개가 정상) **오라클을 스파이크 안에 두는** 메타검사 1건이 맞다 — 같은 파일 `:490~503` L2 뮤턴트 메타검사가 선례. 규약은 CLAUDE.md 회귀 절에 등재됨. ✅ **2026-08-19 해소.** ⓐ `agent_loop_contract ⑯ A7` — 판정을 `not writes_error_history(src) and len(anchors) == 3 and scanner_alive` 로 바꿨다. 양성 축이 **둘**이다: ① 앵커 3종(`async def run_turn(`·`from backend.db import connect`·`TraceWriter`)이 실재해야 하고(= 올바른 파일을 실제로 읽었는가) ② 같은 판정식을 위반 문자열이 섞인 사본에 걸면 반드시 발화해야 한다(스캐너 생존). 하드코딩 detail `"쓰기 경로 없음"` 은 실측값 (`loop.py {len}자 · 앵커 n/3 · 스캐너 생존 {bool}`)으로 교체했다. ⓑ `ui_honesty_contract` — C1~C8 자체는 그대로 두고 **오라클 메타검사 1건**을 신설했다. 4개 문법(from·부수효과·require·동적 import)을 담은 픽스처를 `module_specifiers()` 에 넣어 4건이 그대로 추출되는지 단언한다. **뮤턴트로 둘 다 검증했다** — `module_specifiers` 를 `return []` 로 망가뜨리면 새 오라클만 FAIL 하고 **C1~C8 은 전건 PASS 한다**(= 이 스위트가 지금까지 눈이 멀어 있었다는 직접 증거). A7 도 읽는 파일을 `backend/db.py` 로 바꾸면 `앵커 0/3` 으로 FAIL 한다. **건수 +1** (`ui_honesty_contract` 252→253, 메타 4→5) |
| **P31** | ✅ **불일치 해소 완료 (Sprint 13, 2026-08-19)** — 결측 34건의 성격이 **확정**됐다. ⛔ 다만 **회수는 1건뿐**이라 결측 자체는 33건이 남는다 **PDF 추출 품질 triage + `actions` 결측 회수** | **실측(2026-08-13): `error_codes.json` 65건 중 `actions` 가 37건 결측**(S100 26 / iG5A 11). `causes` 는 0건 결측이라 표는 읽혔는데 **조치 칼럼만 샜다.** 원인은 이미 `data/analysis/manual_eda.md` 에 있다 — `:97` *"원인/조치 불릿 분해 — 셀 내 줄바꿈이 **문장 중간에서** 발생"* · `:100` *"iG5A 표준본 12.1 과 **트러블슈팅 문서**의 항목 불일치 — 트러블슈팅이 원인/조치는 더 상세"*. **결측 37건은 성격이 둘로 갈린다** — ⓐ **iG5A 11건은 유료 OCR 이 필요 없다.** 조치가 `data/raw/iG5A_Troubleshooting_Rev1.0_150415.pdf`(p.22~29)에 있는데 **표준본에서만 뽑았을 뿐**이라 **소스를 추가**하면 된다 ⓑ S100 26건은 셀 내 줄바꿈 분해 실패라 **재추출 후보**다. ⚠ **선행은 triage** — 지금은 추출 품질을 재는 단계가 없어서 이 결측을 **우연히** 발견했고, 파서를 먼저 바꾸면 **좋아졌는지 잴 방법이 없다** ⚠ **2026-08-18 실측 정정 — 이 칸은 오래 "ⓐⓑ 회수 완료" 로 적혀 있었으나 사실이 아니다.** 정본 `data/extracted/error_codes.json` 65건을 다시 세면 **`actions` 결측 34건**(S100 25 / iG5A 9)이다 — 출발점 37건에서 **3건만 줄었다**. 후보 파일 `error_codes_actions.candidate.json` 의 `entries` 도 **3건**(iG5A `RERR`·`ETB` + S100 `FANW`)이고 **`_pending_review` 가 35건**이다. `data/analysis/actions_review.md` 스스로 *"명세 문서는 후보 10건을 기대했으나 실측은 3건"* 이라고 적어 뒀다. **⚠ 이건 실패가 아니라 정직한 거부다** — 사유가 ⓘ 조치문이 여러 항목과 페이지를 공유해 자동 매칭 보류(ambiguous) ⓘⓘ 일람표에 명칭은 있으나 대응 페이지가 `-`(트러블슈팅본에 조치 내용 자체가 없음) ⓘⓘⓘ S100 9.2 표에 항목이 아예 없음 — 셋 다 **지어내지 않기 위해 멈춘 것**이다(절대규칙 3·D99). 따라서 **ⓐ(iG5A, 소스 추가로 풀린다)는 부분 해소에 그쳤고 ⓑ(S100 재추출)는 미착수**다. 정본 병합 경로(MQ-919)와 사람 승인(2026-08-17)이 끝난 것은 맞으나, **그것은 회수된 3건에 대한 것**이다. | **InsuQ 가 같은 문제를 이미 풀었고 실물이 있다**(`InsuQ/ai-engine/insuq_ai/ingest/`): `quality_triage.py` → `elice_replace.py` → `elice_docvision.py` 3단. 핵심은 **전면 재추출이 아니라 선별 재추출**이다 — triage 모듈 독스트링이 *"유료 OCR(Elice, **45원/p**)로 **다시 읽어야 할 페이지**를 고른다"* 이고 **네트워크 호출이 없다**(무엇을 살지 고르는 것까지). 실측 결과 616청크 중 **7페이지 → 315원**. 신호도 실측으로 걸러냈다 — 문자 깨짐 계열은 그 코퍼스에서 **전부 0건**이었고 유효한 건 **길이 이상치**와 **표 구조 붕괴** 둘. 오탐 사례까지 기록돼 있다(`ㆍ` 아래아가 *"전화ㆍ우편ㆍ인터넷"* 처럼 정상 나열 구분자인데 고립 자모로 잡혀 **전 코퍼스 오탐**). MaintQ 에 그대로 옮길 수 있는 건 **모델이 아니라 이 3단 구조**다 — 특히 ⓐ 처럼 **소스 추가로 풀리는 것을 유료 OCR 로 태우지 않게** 막아 준다. 🎯 **2026-08-19 판독 결과 (Sprint 13, 1,530원 집행)** — 저장소 안에서 서로 충돌하던 **세 진단이 판가름났다**: **`CONFIRMED_ABSENT` 24 · `DISAGREE` 6 · `STILL_AMBIGUOUS` 3 · `RECOVERABLE` 1 · `INCONCLUSIVE` 0**. ✅ **`_pending_review`(MQ-911)의 *"매뉴얼에 원래 없음"* 이 맞았다** — 28건 주장 중 24건 확정. ❌ **`extract_triage` 의 *"S100 25건 = `CELL_SPLIT`, 파서 수정으로 회수"* 는 틀렸다**. ❌ **이 칸이 적었던 *"ⓑ S100 재추출 후보"* 도 틀렸다.** → **유료 OCR 로 데이터를 늘리려던 기대는 성립하지 않았다.** 회수 가능은 `iG5A NTC` 1건뿐이고 D99 재승인 대기다. 대신 **"없다"를 근거를 갖고 말할 수 있게 됐다** — 설계 스펙 §1 이 *"회수는 목표가 아니라 결과다"* 라고 못박은 그대로다. ⚠ **`DISAGREE` 6건 중 4건은 알려진 위양성**(설명문의 `교체` 가 조치 표지어에 걸림 · `LCW`/`LOR` 의 `error_name` 이 둘 다 `Lost Command` 라 앵커 충돌). 판독기가 **조치문을 과하게 인정하는 편향**이 있는데도 24건이 부재로 확정됐다는 점이 그 24건의 신뢰도를 높인다 — 위양성은 `DISAGREE` 쪽으로 밀지 `CONFIRMED_ABSENT` 쪽으로 밀지 않는다. 검수 자료: `data/analysis/actions_absence_verification.md`. 🔴 **2026-08-19 위임 검수 결과 — 회수 가능은 0건이다.** 기계 판정의 `RECOVERABLE 1`(`iG5A NTC`)은 **보류(반려)** 됐다: 근거가 표 행이 아니라 `text_window` 폴백이고 **귀속행 0**이며, 무엇보다 `_pending_review` 의 공유 항목 목록에 **`'NTC 이상'` 이 명시적으로 들어 있어** HWT·EEP·ERR·COM 이 `STILL_AMBIGUOUS` 로 남은 것과 **같은 공유 셀**이다 — 회수하면 공유 조치문을 한 항목에 귀속시키는 것이고 절대규칙 3 위반 방향이다. `DISAGREE` 중 실판단 대상이던 `EEP`·`HWT` 도 근거가 각각 **설명문**과 **`하드웨어오류(Fatal)` 8자 라벨**이라 정본에 넣을 것이 없다. ⚠ **파생 발견**: 판정 매트릭스가 `NOT_FOUND_ON_PAGE × ACTION_FOUND` 에는 귀속 조건을 안 걸고 `AMBIGUOUS × ACTION_FOUND` 에만 걸어, **같은 공유 셀인데 파서 분류 차이만으로** 결론이 갈렸다 — 매트릭스 갭이며 다음 작업 후보다. ⚠ 위임 판정이지 **사람 최종 승인은 별도**다 (`related_parts` 2026-08-05 위임 → 08-12 승인 선례) |
| **P32** | **부품 품번(카탈로그) 확보 — 지표를 움직이는 유일한 축** | **부품 특정 정확률 40.0%**(목표 ≥90%. ⚠ **초안의 `42.2%` 는 4차 기준선 값이고 현재 코드 기준선은 `20260812-060312` 의 **40.0%** 다 — 둘의 차이 −2.2pt 는 흔들림이라 판정 불가)의 원인은 추출 충실도가 아니다. `data/related_parts.seed.json` 이 스스로 적어놨다 — *"**추출 파이프라인은 이 값을 만들어낼 수 없다 — 매뉴얼 표에 부품 품번이 없기 때문.**"* 매뉴얼은 *"무엇이 고장났나"* 까지 알려주고 멈추는데 MaintQ 의 서사는 *"그래서 무슨 부품을 발주하나"* 까지 간다. **그 사이를 잇는 게 부품 품번**이고, **유일하게 비어 있으면서 구할 수 있는 실제 데이터**다. ⛔ PDF 추출을 아무리 개선해도 이 지표는 안 올라간다 ⛔ **2026-08-14 실측: 데이터 축은 전부 닫혔다. 자동 수집으로는 못 푼다** — 전문 [`data/analysis/part_number_sources.md`](../data/analysis/part_number_sources.md) · 요약 `data/data_list.md §6-4`. 4개 축 모두 **완제품 ✅ / 소모 교체품 ❌** 로 같은 경계를 보인다: ⓐ **조달청**(08-12) 부품 8종 전수 0건, 대조군 케이블 958·전동기 21 정상 검출 ⓑ **LS 매뉴얼 1,035청크 전수 스캔** — 품번 토큰 34종이 **제동유닛 8 · EMC필터 7 · MCCB 13** 세 계열뿐. **냉각/팬 0 · 제어보드 0 · 키패드 0 · 흡기필터 0**(같은 스캐너가 제동유닛을 잡으므로 **양성 축 살아 있음** = 스캐너 실명이 아님) ⓒ **국내 유통**(나비엠알오 `K18993201` 등·미스미) 완제품 SKU 만 ⓓ **inverterdrive.com** 만 부품 단위로 판다 — `SV-iG5A I/OPCBASSY`(제어보드+로컬 키패드) · `SV-iG5ACAB2/3`(원격 키패드) · `LV0110/0150S100-FAN` · `LV0185/0450S100-FAN`. Cloudflare 봇 차단으로 Claude 는 못 열지만 **사람이 LS 부품 목록(1페이지)을 전수 확인했다(2026-08-14)**: **`parts` 40종에 대응하는 공개 실품번은 `SV-iG5A I/OPCBASSY` 1종뿐**이다 — `Part number:` 명시 · 적용 **`0.4~7.5KW-2/4`** 로 **MaintQ 자산 용량대(2.2·4.0kW)를 덮는다**. ⛔ **iG5A 냉각팬은 부재 확정** — 같은 목록에 팬이 4종 있는데(S100 11~15 · S100 18.5~45 · iS7 30~45 · **iS7 5.5kW**) **iG5A 팬만 0건**이다. **팬 축·iG5A 축이 각각 살아 있고 교차만 비었으며**, iS7 5.5kW 가 있으니 *"소용량은 원래 안 판다"* 도 아니다. ⚠ 판매점 주문번호(`Order code: 32155`)·완제품 형명(`SV220iG5A-4`·`LSLV0004G100-2EONN`)은 **품번이 아니다** — 단 완제품 소매가는 `assess_repair_value` 의 **"교체" 선택지 비용**(지금 목업, D74 가 막아 둔 자리)으로 쓸모가 있다(⚠ GBP 영국가 · `G100` 은 기종 enum 밖 D6·D13). **근본 원인은 유통 정책이다** — 매뉴얼이 *"FAN교체는 구입처나 LS산전 고객센터에 문의하십시오"* 라고 **명시**한다(팬은 교체 절차 3.1.5·경보 `Pr.87`·누적시간 `CNF.75` 까지 다 있는데 **품번만 없다**). **→ 검색 도구를 바꿔도(tavily/serp) 없는 것이 생기지 않는다.** 남은 **유일한** 경로는 **LS 고객센터·대리점 문의**(사람) → `TODO_직접할일.md §데이터 확보`. 붙일 수 있는 건 **`SV-iG5A I/OPCBASSY` 1종**뿐이라 **지표(42.2%)를 직접 못 움직인다** — 케이스 맵 주인공 `FAN-IG5-01`(S1)이 정확히 품번 미공개 구간. ⚠ **상태 서술 주의**: *"품번이 전부 없다"*(제어보드는 있다) · *"자료를 못 찾았다"*(찾은 결과 **공개돼 있지 않은 것**이다) 둘 다 틀리며, 백로그에서 전혀 다른 액션으로 이어진다(더 뒤진다 vs 사람이 전화한다). 채택 시 방식도 미결: `part_no` 는 PK 라 케이스 맵·평가셋·회귀가 묶여 있으므로 **`parts.mfr_part_no` nullable 컬럼 신설**(합성 PK 유지 + 실품번은 부가정보, 없으면 NULL = "미공개"를 데이터로 정직하게 표현)이 후보이며 `05_DB_SCHEMA §7` 변경이라 **D 등재 대상** |

---

## UI · 결재 워크플로우 (2026-08-20 추가)

| P | 기능 | 설명 | 미리 확보해둔 것 |
|---|---|---|---|
| **P40** | **UI 라이브러리 비교판 — MUI + animata.design 으로 같은 화면을 v2 로 만들어 대조** | 기존 화면을 **바꾸지 않고** 같은 화면을 라이브러리로 다시 만들어 **나란히 비교만** 한다(요청 원문: *"v2 에 같은 화면 만들어서 기존 화면이랑 비교만 해보고 싶어"*). 🔴 **실측 제약 — 지금 프론트에는 CSS 프레임워크가 하나도 없다.** `frontend/package.json` 의 런타임 의존성은 `next`·`react`·`react-dom` **3개뿐**이고, 스타일은 `frontend/app/globals.css` **한 파일**로 손수 짠 것이다. 그래서 이 작업은 "라이브러리 교체"가 아니라 **스타일 시스템 신규 도입 2건**이다: ⓐ **MUI 는 emotion(CSS-in-JS)** — Next 14 App Router 에서 RSC 와 맞지 않아 `'use client'` 경계 + emotion cache provider 설정이 선행된다 ⓑ **animata.design 은 Tailwind + framer-motion 전제의 복붙 컴포넌트** — 즉 **Tailwind 도입**이 딸려 온다. 둘을 같이 넣으면 `globals.css` + emotion + Tailwind **3중 스타일 시스템**이 공존한다. **비교가 목적이라면 그 자체는 감수할 수 있으나 격리가 조건**이다. 🔴 **결정이 필요한 지점 — 비교판을 어디에 두느냐가 회귀를 가른다**: `app/(console)/v2/…` 에 두면 `spikes/ui_honesty_contract.py` 의 L2 글롭 `app/(console)/**/*.tsx` 이 **자동으로 잡아** 파일당 6건씩 검사가 붙고 **D87(UI 정직성 규약)을 지켜야 한다.** `app/v2/…` 로 빼면 글롭 밖이라 안 잡히지만 **정직성 규약이 안 걸린 화면**이 생긴다 — **권고는 전자**다(이 프로젝트의 주장이 "화면이 거짓말하지 않는다"인데 비교판만 예외를 두면 비교의 의미가 없다). ⚠ 프론트 라우트 **기준선 18개**가 늘어나므로 `CLAUDE.md` 기준선 갱신이 따라온다 | `08_DESIGN_BRIEF.md` 에 투입 프롬프트 + 검수 체크리스트가 이미 있다. D87 이 상태→표시 매핑을 **전역 total 맵 1곳**으로 고정해 둬서, 라이브러리를 바꿔도 **매핑 계층은 재사용**된다(`frontend/lib/queueState.ts`·`mappers.tsx`). `ui_honesty_contract` 253건이 회귀 그물로 이미 깔려 있다 |
| **P41** | **실제 서류 양식 기반 발주 결재 + 부서·권한 분리 (재무부 계정)** | 요청 원문: 정비사가 **실제 양식**에 맞춰 발주요청서를 만들고 → 확인·승인하면 → **10분 뒤 발송**(그 사이 취소 가능) → **같은 회사 재무부 담당자** 계정 이력에 도착. 드롭다운에 `즉시 요청` · `10분 뒤 요청(기본)` · `시간 예약 요청`. **목적은 부서 분리·권한 분리**다. 네 조각으로 갈린다: **① 양식 확보** — 실제 발주서 양식을 찾아 그 서식대로 생성·채움. ⚠ **출처·저작권 확인이 선행**(공정위 표준양식 등 공개 출처 우선). 외부에서 받아 오면 **D103 규약 적용 대상**(원본 보관 · 요청 파라미터·인증값 미저장). **② 화면에서 직접 생성·수정** — **이건 P39 그 자체다.** ✅ **발주서 한정으로 완료 (D111, 2026-08-23)** — `POST /api/po`·`PATCH /api/po/{po_id}`·`/technician/po/new`·`/technician/po/[poId]`. P41 나머지(①③④)의 선결과제로서는 ②가 이걸로 닫힌다. P39 가 정리해 둔 선결 4건(새 D-결정 · 3도구 산출 로직을 `data/` 공유 계층으로 이관 · `POST /api/po` 등 라우터 신설 · **"수정 가능한 초안" 데이터 모델**)이 **그대로 P41 의 선결과제**다 — **P41 ⊃ P39**. **③ 부서·권한 분리** — 🔴 **역할이 2종으로 하드코딩돼 있다**: `backend/deps.py:15` `Role = Literal["technician","manager"]` + `VALID_ROLES`, 그리고 **DDL CHECK** `data/seed.py:89` `CHECK (role IN ('technician','manager'))`. 재무부 담당자를 넣으려면 **DDL 변경 → `05_DB_SCHEMA` 변경 → D 등재 대상**이고 `spikes/api_contract.py`(권한·전이 28건)가 함께 움직인다. ⚠ **설계 갈림길**: `role`(권한)과 `department`(소속)를 **한 컬럼에 뭉개지 말 것** — 재무부 담당자도 승인자이므로 `manager` 권한 + `finance` 부서인지, 별도 role 인지부터 정해야 한다. D52 가 *"role 은 OAuth 가 아니라 `users` 테이블이 정한다"* 로 이미 서 있어 **자리는 있다**. **④ 지연·예약 발송** — 🔴 **스케줄러가 없다.** FastAPI + uvicorn 단일 프로세스에 백그라운드 잡 인프라가 없고 배포도 단일 인스턴스 전제다(`13_DEPLOYMENT §4`). 사용자가 *"복잡하면 패스, UI 상 보여지기만"* 이라고 정했다. ⚠ **그런데 그 타협이 D87 과 정면 충돌한다** — 화면이 *"10분 뒤 발송됩니다"* 라고 말하는데 실제로 즉시 발송되면 **화면이 거짓말을 한다.** 정직한 처리 2안: ⓐ 드롭다운에 항목은 두되 **`disabled` + "미구현" 라벨** ⓑ `send_after` 컬럼만 두고 **실제 동작대로 "즉시 발송"이라고 표시**. **ⓐⓑ 중 택1 이 착수 조건**이다 | `users` 테이블이 이미 `role`·`email`·`active`·`auth_provider` 를 갖고 있다(D41·D52). 상태 전이가 `ALLOWED_FROM` **한 곳**을 지나므로(D38) 승인 단계를 늘릴 자리가 있다 — P9(예산/승인 한도 차등)가 같은 자리를 노린다. 승인 큐는 이미 `kind` 통합(D85)이라 재무부 큐를 얹기 쉽다. `requested_by`·`decided_by`·`decision_note` 가 남아 **부서별 이력**이 그대로 성립한다. 인접 항목: **P39**(전제) · **P6**(발주서 PDF 내보내기) · **P9**(승인 한도) · **P16**(다건 품목) · **P21**(인증·IdP) |

> ⚠ **P41 은 단독 착수가 불가능하다** — ②가 P39 이고, P39 는 *"채팅이 아니라 화면이 신규 레코드를 만드는 이 프로젝트 최초의 경로"* 라 **새 D-결정부터** 필요하다(D18·D29 선례를 깨는 일). 순서는 **P39 → P41** 이고, ③(부서 분리)만 떼어 먼저 하는 것은 가능하다.

### P41 ③ 부서 분리 — ✅ **완료 (2026-08-20, D108)**

산출물: `users.department` 컬럼(nullable, CHECK) · `backend/deps.py`(`Caller.department`,
`_department_of()` DB 조회) · `GET /api/whoami`(신규) · `data/seed.py`(`mgr-02` 재무 담당자
시드 + 자가검증 ⑨·⑨-b) · `docs/05_DB_SCHEMA.md`·`docs/06_REPO_API.md` 갱신 · **D108**.
🔴 **`/manager/expenditure` 페이지에 "재무부 소관" 배지를 달았으나 `/api/whoami` 를 부르지
않는다** — 프론트가 아직 `mgr-01`(정비 소속)로만 로그인해서(D108 시드, 세션 전환 경로 없음),
whoami 를 붙이면 "재무부 화면인데 정비 소속"이라는 대조가 생긴다. 그래서 배지는 **호출자
신원과 무관한 정적 텍스트**다 — `frontend/app/(console)/manager/expenditure/page.tsx` 주석에
이유가 적혀 있다. `GET /api/whoami` 자체는 살아 있고 D108 이 정한 "department 를 클라이언트가
읽는 유일한 경로"이지만, **지금 이 경로를 부르는 프론트 코드는 0건**이다 — 재무 계정 세션
전환(별도 로그인/라우팅)이 생기면 그때 연결한다. (승인 게이트 아님 — D71 무저장 화면이라
원래 역할 게이트가 없다.) 아래는 착수 시 확정한 스펙 그대로다.

### P41 ③ 부서 분리 — 착수 스펙 **확정** (2026-08-20, 사용자 결정)

**나머지 ①②④ 와 분리해 이것만 먼저 한다.** 역할 enum 을 건드리지 않아 `spikes/api_contract.py`(권한·전이 28건)가 흔들리지 않는 것이 분리 착수가 싼 이유다.

| 항목 | 확정 내용 |
|---|---|
| 원칙 | **부서 ⊥ 역할.** `users.role` = **권한**, `users.department` = **소속**(신설, nullable) |
| 🔴 권한 판정 | **`require()` 는 `role` 만 본다.** `department` 를 권한 판정에 **넣지 않는다** — 재무부 소속이어도 `role` 이 없으면 승인 못 한다 |
| 🔴 신뢰 경계 | **`department` 를 헤더로 받지 않는다** (`X-Dept` 금지 — 클라이언트가 자기 부서를 참칭할 수 있다). 서버가 `users` 테이블에서 `user_id` 로 조회해 주입한다 — D52 의 태도(*"OAuth 가 아니라 `users` 테이블이 정한다"*) 그대로 |
| 재무부 담당자 | `role: "manager"` + `department: "finance"` |
| **채택 ⓐ** | 승인 큐는 **부서로 필터링만** 하고 **권한은 동일**하게 둔다. ⚠ **정비팀장과 재무부 담당자가 서로의 건을 승인할 수 있다는 것을 알고 수용한다.** 근거: 역할이 2종뿐이라는 현 전제와 일관되고, 나중에 P9(승인 단계 차등)에서 `role` 을 늘리면 자연스럽게 ⓑ(부서별 승인 제한)로 간다 — **그때 판정에 들어가는 것은 `department` 가 아니라 `role`** 이라 이 원칙이 깨지지 않는다 |
| 기각 ⓑ | 승인 대상을 부서로 제한 → `department` 가 판정에 들어가 **"부서 ⊥ 역할"이 깨진다.** 하려면 `role` 을 늘리는 것이 맞다(`finance_manager`) |
| 변경면 | `data/seed.py`(DDL `department` 컬럼 + 시드) · `backend/deps.py`(`Caller` 에 department 주입) · `05_DB_SCHEMA` · 프론트 소속 표시. **역할 enum 무변경** |
| 새 D-결정 후보 | **"부서는 권한이 아니다"** — 판정 함수가 `department` 를 참조하지 않는다는 것을 회귀로 잠근다(부재 검사이므로 **liveness 앵커 필수**) |

**첫 적용 대상 권고 — 발주 승인이 아니라 지출 분류 화면.**
`classify_expenditure`(`POST /api/expenditure/classify` · 화면 `/manager/expenditure`)는 정비 판단이 아니라 **회계 판단**(자본적/수익적 지출)이라 실무에서 원래 재무·회계팀 소관이다. **새 상태 머신도 새 전이도 필요 없고 화면 소속만 옮기면 된다.** ⚠ 단 그 API 는 무저장이라 **역할 게이트가 없다**(D71 패턴) — 옮기는 것은 권한이 아니라 **화면의 소속 표시**다.

⚠ **실무 흐름과의 차이를 알고 간다.** 전형적 실무는 `현장 요청 → 부서장 결재 → 구매 집행 → 재무 지급` 이고 **재무의 승인은 보통 "발주 승인"이 아니라 지급·예산 승인**이다. 중소 제조사는 구매팀이 없어 재무가 겸하는 일이 흔해 이 설정 자체는 현실적이지만, **팀장 결재를 건너뛰지 않는 것**이 조건이다 → 발주 **2단계 결재**는 **P9** 자리이며 이 스펙 범위 밖이다.

---

## 크로스 프로젝트 (Q 시리즈) — A2A 경계

> ⛔ **MaintQ 는 A2A 스킬을 노출하지 않는다 — 수신 어댑터(`:9003`)는 «미착수»가 아니라 «설계상 없음»이다**
> (2026-09-09 확인). 근거는 표준 계약 자체다 — `A2A_Q/docs/agent_cards/maintq.json` 의 `skills` 가
> **빈 배열**이고 노트에 *"MaintQ는 A2A 스킬을 노출하지 않는다 — 요청을 시작하는 client 역할이 기본이다"*
> 라고 적혀 있다. 같은 디렉터리의 `finallq.json` 은 **7스킬**, `insuq.json` 은 **6스킬**을 노출한다 —
> 이 비대칭은 결함이 아니라 **역할 배정**이다(설비 고장이 나야 돈도 보험도 움직이므로 제조가 시작점이다).
> 카드가 유일하게 언급하는 예외 S15 조차 *"MaintQ 가 응답을 받아 FinAllQ 에 재요청"* 이라 여전히 client 다.
> 📌 이 레포·이력서 문서가 오래 *"수신 어댑터 미착수"* 로 적어 **하지 않기로 한 일을 밀린 일처럼** 보이게
> 했다. P34 의 S6·S15·S16 을 *"미착수가 아니라 데이터 없음"* 으로 닫은 것과 같은 원칙이다.

> 출처: `../A2A_Q/Q시리즈_시나리오맵_S1-S18.html` (기준 2026-08-14 · FinAllQ Sprint 10 완료 반영).
> 이 지도는 **MaintQ · FinAllQ · InsuQ 세 프로젝트의 시나리오를 S1~S23 한 체계로** 잡는다.
> MaintQ 단독 시나리오로 **S1~S4 · S9 · S10 · S17 · S18** 을 인정하고, 경계를 넘는 것이 10개다.

| P | 기능 | 설명 | 미리 확보해둔 것 |
|---|---|---|---|
| **P33** | ✅ **완료 (Sprint 12, 2026-08-18)** | **시나리오 번호 충돌 정정 — MaintQ 의 `S19` → `S29`** | **MaintQ 가 로컬로 붙인 `S19`(수리 증빙 서명, `02_SCENARIOS.md:82`)가 Q 시리즈 전사 지도의 `S19`(FinAllQ **기업 고객 온보딩** — 등록→앵커→초대, 구현 완료)와 정면 충돌했다.** 지도는 MaintQ 몫으로 S1~S4·S9·S10·S17·S18 을 **이미 인정**하고 있어 다른 번호는 어긋나지 않았다 — **어긋난 것은 `S19` 하나뿐**이고, 지도가 *"MaintQ는 S1~S4로 잡혀 있었죠"* 라고 적은 데서 보듯 **MaintQ 가 S19 를 만든 사실을 지도가 몰랐다.** 정정 2안 중 ⓐ **MaintQ 가 번호를 옮긴다 → `S29`** ⓑ **전사 지도를 고쳐** S19 를 MaintQ 에 주고 FinAllQ 를 밀어낸다(FinAllQ 가 이미 구현 완료라 **비용이 훨씬 크다**) 가운데, **채택안 ⓐ**로 결론이 났다. 근거 번호는 `../A2A_Q/11_A2A_SCENARIOS.md:98`(*"FinAllQ 가 S19~S23 을 선점했으므로 InsuQ 는 S24~S28 을 쓴다"*)이 **InsuQ 에 이미 S24~S28 을 배정**해 뒀다는 사실에서 나왔다 — **비어 있는 첫 번째 번호가 `S29`**다. 사람 협의 결과 **`S29` 채택이 승인**돼, Sprint 12(MQ-1201)가 살아있는 문서(`02_SCENARIOS.md`·`12_MAINT_VALUE.md`·`00_MVP_SCOPE.md`·`04_MCP_TOOLS.md`·`06_REPO_API.md`·`07_BACKLOG.md`·`README.md`·`docs/status/*.html`)의 `S19`를 전부 `S29`로 치환하고, 역사 기록(`docs/sprints/sprint-6~11.md`)은 본문을 보존한 채 forward-reference만 추가해 정정을 완료했다 | 충돌 지점이 **`S19` 단 하나**였다. MaintQ 내 `S19` 사용처는 `rg -l "S19" docs/` 로 전수 가능했다(문서 10여 개, 코드 0). **번호는 문서에만 있고 DB·도구 계약·enum 에는 없어** 회귀를 깨지 않고 바꿀 수 있었다 |
| **P34** | 🟡 **부분 재개 (D112, 2026-08-23 → S13·S12 추가 2026-08-30)** — **MaintQ 발신 A2A — 경계 시나리오 8종** | 지도가 세는 **경계 시나리오 10개**(S5·S6·S7·S8·S11~S16, 2026-08-14 스냅샷 번호) 중 **MaintQ 가 발신자**인 것: **S5**(출금 요청→FinAllQ 2단 승인) · **S7**(화재보험 갱신 상담→InsuQ) · **S11**(보험 목적물 변경 통지→InsuQ) · **S12**(매각대금 정산·대출상환→FinAllQ) · **S13**(중고설비 취득→담보심사, 멀티홉) · **S14**(위험등급 변동 통지→InsuQ) · **S16**(설비 취득 자금조달 비교 상담→FinAllQ). S10 에서 **담당자가 서명하는 순간** S11·S12 로 이어지는 것이 지도가 그린 연결점이다. 🔑 **지도의 핵심 관찰**: FinAllQ 는 *"S5 가 도착하면 타야 할 레일(S20 결재 + S21 FDS + 감사 로그)이 **이미 다 깔려 있고**, 빠진 것은 흐름이 아니라 **바깥으로 난 문**(Agent Card · :9001)"* 이다 — 즉 **양쪽 다 문만 없다.** ⛔~~MaintQ 쪽도 같은 상태이며 `README.md` 다음 액션 8 이 *"A2A 호출부는 QMesh 착수 후"* 로 이미 유보해 뒀다 — **이 P 는 그 유보를 백로그 번호로 고정하는 것**이지 착수 신호가 아니다.~~ → **D112(2026-08-23)로 뒤집혔다.** A2A_Q 레포에 실제 어댑터(`adapters/finallq_a2a`·`insuq_a2a`)가 생기면서 "검증할 상대가 없다"는 유보 근거가 무효화됐고, 위 8종 중 **S5(출금 요청)만** `request-withdrawal`로 구현·커밋됐다(나머지 7종은 여전히 미착수). 여기에 구 목록에 없던 **lookup-clause**·**assess-loan**(설비 담보 대출 사전 판정, 2026-08-23 신규)도 함께 구현됐다 — **assess-loan은 개념상 S13(중고설비 취득 담보심사)에 가장 가깝지만 정확히 같지는 않다.** 사용자가 2026-08-23 제시한 최신 A2A_Q 시나리오맵은 이 표의 S5·S13·S11을 각각 **S1·S4·S5**(새 번호)로 부른다 — `S19→S29`(P33) 선례와 같은 종류의 번호 충돌이니 아래 표의 번호는 **2026-08-14 스냅샷 기준임을 인용할 때마다 명시할 것**. **구체 사례(2026-08-17 브레인스토밍에서 추가)**: 설비 하이라이트 대시보드 설계 중 "수리 판정 시 재고가 없으면 자동으로 FinAllQ 에 자금 조달 통신을 보내자"는 아이디어가 나왔다 — 이건 **S5(출금 요청)의 구체적인 발화 조건 한 가지**로, 새 시나리오가 아니라 S5 트리거 목록에 포함시킬 것 | Sprint 8 이 신원 계층을 깔아 뒀다 — `partner_links`(D91·D96) · 자격증명 위치(D93) · `traces.request_chain_id`(D94, **이제 컬럼만이 아니다** — `backend/a2a/trace.py`가 실제로 쓴다, D112). `spikes/a2a_identity_contract.py ⑪-b` 는 이미 뒤집혀 있다  **⏩ 2026-09-09 갱신 — 발신 5종 → 6종.** `notify-asset-change`(S11, InsuQ 부보 목적물 변경 통지)를 구현했다. **S12 와 정반대로 서명 뒤에 온다** — 계약이 *"설비 처분 **확정**에 따른"* 변경이라 못박으므로 미서명 draft 로는 조립하지 않는다(S12 는 담보를 푸는 수단이라 서명보다 앞서야 했다). 부보되지 않은 자산(`insured=false`·`policy_id` NULL)도 조립 단계에서 막는다 — InsuQ 에 고칠 증권이 없는데 빈 값을 실어 보내면 `schema_validation_failed` 가 난다(request-withdrawal 전례). ⛔ **응답으로 MaintQ 상태를 바꾸지 않는다** — 통지는 알리는 것이지 되받는 것이 아니다(S12 만 `lien_released` 를 소비한다). 회귀 14건(payload 9 · 라우터 5). 🟡 **S14(`notify-risk-change`)는 계약에 미정이 있어 멈췄다** — 스키마가 `risk_before`/`risk_after` 를 `number` 로 요구하는데 MaintQ 는 `LOW/MEDIUM/HIGH` 서열 등급이다. 내부 산식에 점수(3~9)가 있긴 하나 **어느 척도를 InsuQ 가 기대하는지 계약에 없고**, 응답의 `margin`(*"임계값까지의 여유, ±10% 이내면 needs_review"*)은 정수 3~9 위에서 의미가 서지 않는다. 척도를 임의로 정해 보내면 assess-loan 때와 같은 계약 드리프트가 된다 — **InsuQ 와 척도를 합의한 뒤 착수한다.** **⏩ 2026-09-16 — 방향 합의됨(그쪽 사용자 승인 대기). 착수는 아직 아니다.** 합의안: 요청의 `risk_before`/`risk_after` 를 **`"LOW"|"MEDIUM"|"HIGH"` 문자열 enum** 으로 바꾸고, 응답 `margin` 은 **단계 차(정수) 또는 `null`**, 판정은 **등급 전이표**로 한다(등급이 안 바뀌면 통지의무도 안 생긴다). 응답 계약은 안 깨진다(`number` 가 정수를 포함하고 `null` 은 이미 계약에 있다) — **바뀌는 건 요청 두 필드의 타입뿐**이다. 🔴 **이 칸이 적어 둔 기각 근거는 기전이 틀렸다** — *"`margin` 이 정수 3~9 위에서 의미가 서지 않는다"* 고 썼는데, `margin` 은 **InsuQ 가 계산해 돌려주는 값**이고 그쪽 ±10% 는 점수의 10% 가 아니라 **상대 변화율**(`ratio = (after-before)/before`, 임계 0.2)이다. 나눗셈이라 절대 단위가 상쇄돼 «9의 10%» 계산은 애초에 맞물리지 않는다. **결론(서열에 비율 산식을 대면 안 된다)은 맞았지만 근거가 달랐다** — 진짜 문제는 *"띠가 아무것도 못 거른다"* 가 아니라 **"띠가 엉뚱한 걸 거른다"** 다. InsuQ 실측: `3→4` ratio 0.333 → `notify_required`(**둘 다 LOW 인데 통지의무 발생**) · `8→9` ratio 0.125 → `deferred`(**둘 다 HIGH, 같은 한 칸인데 판정이 다름**). ⛔ **정규화(0~100)로는 안 풀린다** — 단조변환이라 순서만 유지되고 «간격이 같다»는 가정은 그대로 들어간다. ⛔ **«우리가 임계값을 payload 로 보낸다」(ⓑ)도 기각** — 통지의무 임계값은 보험사가 정할 사안이라 주입받으면 책임이 뒤집힌다. **증권번호 발급 주체 논증과 같은 구조이고 그 논증을 먼저 세운 게 우리**라 일관되게 받았다. 📌 **착수 시 이미 있는 것**: `data/risk_grade.py` 가 `stored_grade`(마지막 저장 = `risk_before`)·`current_grade`(재계산 = `risk_after`)·`changed` 를 **이미 함께 낸다** — 새로 만들 것이 없다. 시드에 **2단계 상승 케이스**도 있다(`BLD-C` stored `LOW` → 재계산 `HIGH`, 자가검증 ㉟ 가 대조하는 의도적 불일치). 나머지 3동은 무변화. 요청해 둔 것: **전이표 9칸을 스펙에 전수 열거**할 것 — *"1단계 이상 상승이면 통지"* 같은 규칙만 두면 **하강·2단계**를 양쪽이 각자 추론하게 되고 그게 assess-loan 드리프트가 난 방식이다.

**⏩ 2026-08-30 갱신 — 발신 3종 → 5종.** `assess-used-equipment-loan`(S13)·`request-settlement`(S12) 발신 트리거를 구현했다. **S12 는 MaintQ 발신 스킬 중 처음으로 응답이 MaintQ 상태를 바꾼다** — `lien_released: true` 가 `assets.lien_consent_ref` 를 채워 LIEN-CONSENT(BLOCKING)를 해소한다. ⛔ **서명하지는 않는다** — 담보만 풀고 서명은 사람이 한다(`disposal_sign_contract` 26/26 유지가 그 독립 증거다). 빈 문자열은 쓰지 않는다(`''` 는 `is_null` 을 False 로 만들어 BLOCKING 룰을 조용히 미발화시킨다, seed 검사 ⑱). 🔵 **나머지 3종은 '미착수'가 아니라 '데이터 없음'으로 닫는다** — 언젠가 할 일과 하지 않기로 한 일은 다르게 적어야 한다: ㉠ `advise-hedge`(S6) — MaintQ 에 통화·외화 데이터가 **0건**이다. 만들려면 공급사에 통화 컬럼을 신설하고 환노출을 지어내야 한다(D62 위반). ㉡ `advise-financing`(S16) — 트리거가 될 도메인 이벤트가 없다. ㉢ `advise-replacement-financing`(S15) — 2차 홉 전용인데 MaintQ 에 `claim-insurance` 발신 흐름 자체가 없어 사실상 두 스킬 작업이라 별도 사이클이다. |
| **P35** | ✅ **완료 (D136, 2026-09-09)** — **나가는 A2A 호출의 차단기(circuit breaker) 경계** | 지도가 FinAllQ 내부 구조를 설명하며 명시한 교훈 — *"코어와 모델을 프로세스 단위로 갈랐다. 같은 프로세스에 태우면 **모델이 죽을 때 이체도 같이 죽는다.** 사이에 **차단기**를 둬 AI 장애가 코어로 번지지 않게 했다 — **A2A 에서 남의 에이전트를 부를 때도 같은 경계가 필요하다.**"* MaintQ 가 P34 를 착수하면 **상대 서버(FinAllQ·InsuQ)의 장애가 MaintQ 의 진단·발주까지 끌고 내려가지 않아야** 한다. 함께 볼 것: FinAllQ 는 감사 로그·AI 전송 페이로드를 **화이트리스트(등재된 키만)** 로 내보낸다 — *"블랙리스트였다면 새 필드가 생길 때마다 빠뜨릴 위험이 생긴다. 계좌번호·금액은 목록에 없어서 **구조적으로** 실릴 수 없다."* MaintQ 의 `tool_payload` 원문 보관도 같은 규약을 따라야 한다 | D15 가 이미 **프로세스 경계**를 갈라 뒀다(backend ↔ mcp_server). 도구 실패를 예외가 아니라 `status` 로 반환하는 규약(D9)과 *"하위 도구 실패를 삼키지 않는다"*(`04 §13`)가 **차단기 반환값의 형태를 이미 정해 준다** |

> ⚠ **P33 은 Sprint 12 에서 해소됐다(S29 확정).** ~~아래는 P34·P35 에만 해당한다. P34·P35 는
> 전부 "지금 하지 않을 것"이다~~ — **P34는 D112(2026-08-23)로 부분 재개됐다**(request-withdrawal·
> lookup-clause·assess-loan 3종만, 구 목록 S5·S7·S11~S16 중 나머지 7종은 여전히 보류).
> ~~P35(차단기 경계)는 `services/po.py:approve()`가 실패를 삼키는 정도로만 부분 달성, 정식 패턴은
> 아직 없어 계속 열어 둔다.~~ → **D136(2026-09-09)으로 해소.** 진단이 한 걸음 모자랐다 —
> 예외를 삼키는 것은 맞았지만 **상대가 죽어 있으면 승인 한 건마다 10초 타임아웃을 그대로 물었다.**
> *실패를 삼키는 것*과 *빨리 실패하는 것*은 다르다. `backend/a2a/circuit.py` 가 파트너 단위로
> 연속 «도달 불가» 3회에 열고 30초 뒤 시험 호출 1건만 통과시킨다. ⛔ **400·422 는 열지 않는다** —
> 상대가 살아 있다는 증거라서, 그걸로 막으면 한 스킬의 계약 오류가 그 파트너의 멀쩡한 다른
> 스킬까지 멈춘다(2026-08-24 assess-loan 드리프트 때 실제로 그런 상황이었다).
> 회귀 `test_circuit.py` 17건 + `test_client.py` 16→22건.
>
> ⚠ **2026-08-24 추가 대기열** — 🔵 **2026-09-16 갱신: 5개 중 2개는 이미 착지했다.**
> `request-settlement`(S12, 2026-08-30 — 응답 `lien_released` 가 MaintQ 상태를 바꾸는 첫 스킬) ·
> `assess-used-equipment-loan`(S13, 2026-08-30 → D140 이 MCP 도구로도 개방)이 완료다.
> **남은 3개**는 `advise-hedge` · `advise-financing` · `advise-replacement-financing` 이고,
> 셋 다 **자문(advise) 계열**이라 «받아서 무엇을 바꾸는가»가 MaintQ 쪽에 정의돼 있지 않다 —
> 착수 전에 그것부터 정할 것. ⚠ 아래 *"지금은 넘어가고 **시연 이후** 착수"* 의 그 시연은
> **2026-08-29 에 끝났다** — 더 이상 대기 사유가 아니다.
> (원문 유지) FinAllQ 세션이 크로스세션 메시지로 나머지 5개 스킬(advise-hedge·
> advise-financing·request-settlement·assess-used-equipment-loan·advise-replacement-financing)의
> 요청/응답 계약과 curl 검증 결과를 선제 공유해 왔다(`docs/sessions/2026-08-24_finallq_conversion.md`
> 는 이 메시지를 포함하지 않는다 — 별도 시각의 메시지). 이번 시연 범위가 S5·S8 두 시나리오로
> 확정돼 있어 **지금은 넘어가고 시연 이후 착수**하기로 FinAllQ 쪽에 회신했다. 착수 시
> `build_request_withdrawal_payload`·`build_assess_loan_payload`와 같은 패턴
> (`backend/a2a/payloads.py`) + `routers/a2a.py` 트리거 추가로 대응 가능 — FinAllQ 쪽 스펙은
> 이미 확보돼 있다. `advise-replacement-financing`은 "InsuQ claim-insurance 이후 2차 홉 전용"
> 이라 MaintQ 쪽에 그 흐름(InsuQ claim-insurance 호출 지점) 자체가 있는지 먼저 확인할 것.

---

- 🟡 `data/pg_isolation.py` `_CLONE_TABLES` 에 `onboarding_*` 5테이블이 없다 — `clone_data=True` 격리 스키마에서 온보딩 데이터가 0행이다
  (MQ-1911 이 화면 검증 때 손으로 복사했다). **그대로 추가하면 안 된다** — `onboarding_contract`(적재기 멱등 ③)·`onboarding_promote_contract` 등이
  「격리 스키마 온보딩 0행」을 전제로 자기 배치를 만든다. 넣으려면 옵트인 인자(`clone_onboarding=True`)로
  (2026-09-25 Stage 4)

- 🟡 **D158 후속(Stage 5 리뷰 경미)** — ⓐ `scripts/migrate_d158_sites.py` 가 **행** 드리프트만 본다: 같은 이름 테이블이 다른 모양으로
  이미 있으면 `CREATE TABLE IF NOT EXISTS` 가 조용히 건너뛴다 → `information_schema.columns` 대조로 스키마 드리프트 보고 ·
  `site_floorplan_contract ⑬` 은 INSERT 경로의 2회 실행 멱등을 자동 검증하지 않는다(수동 실행 출력만)
  ⓑ 설비 「최악 색」 우선순위가 두 벌 — `frontend/lib/floorplan.ts` `COLOR_RANK` 와 `technician/equipment-status/page.tsx` `rankAsset`
  (순서는 같으나 `rankAsset` 은 모르는 색을 정상(tier 3)으로 센다 — 기존 결함) → `rankAsset` 이 `lib/floorplan` 을 쓰게 합친다
  ⓒ `data/pg_isolation._CLONE_TABLES` 에 D158 3테이블 — 공유 DB 에 마이그레이션 전이면 `clone_data=True` 격리 스파이크·pytest 전부가
  UndefinedTable 로 죽는다(시끄러운 실패). **새 환경은 `scripts/migrate_d158_sites.py` → 회귀 순서** (2026-09-25 Stage 5)

## 아이디어 주차장 (미분류)

- 🔵 **외부 연동은 A2A 대신 카카오톡 알림(MCP)으로 (2026-09-25 사용자 방향)** — 이 레포에서 A2A(FinAllQ·InsuQ)는 더 확장하지 않는다
  (구현·회귀는 유지, 데모 시나리오에서는 제외). 외부로 나가는 연동이 필요하면 예: 온보딩 검수 대기·안전 문구 승인 대기·발주 승인 대기를
  팀장에게 카카오톡으로 알림. 착수 시 D 번호 먼저(채널·수신자·보내는 내용의 범위 — 매뉴얼 원문·안전 문구 본문은 보내지 않는다 D144)

- 발주 이력 기반 소모성 부품 자동 재주문 제안 (안전재고 하회 시 선제 알림) — P17과 묶으면 시너지
- 점검 체크리스트 완료 체크 → 정비 리포트 자동 생성 (S3의 `po_card` variant:`hold` 체크리스트가 입구)
- 팀장 화면 주간 요약 (반복 고장 Top3, 발주 지출 합계)
- 반려 사유 템플릿 (예산/사양 불일치/재고 있음/시기 조정) — 자유 입력이면 통계가 안 나옴
- 세션 목록·재개 UI — `traces`에 세션이 쌓이는데 사용자가 과거 대화를 다시 열 경로가 없다
- ✅ **실제 .docx 파일 생성 — 2026-09-04 해소 (D124·D125). pdf 는 미착수.**
  구현: `data/doc_fields.py`(필드맵) → `backend/services/docx_render.py`(템플릿 채우기) →
  `backend/services/document_download.py`(신원 주입) → `GET /api/{po,decisions}/.../documents/{doc}.docx`.
  MCP 읽기 도구 `get_document_facts` 1종 신설(01·02·05·06, 조회만 — D125).
  **경로는 `python-docx` 직접 조립이 아니라 ① 템플릿 채우기다** — 아래 "경로 두 가지" 는
  라이브러리 선택이었고, 그 앞에 전략 갈림길이 하나 더 있었다(착수 시 실측으로 발견).
  ⛔ **pdf 는 안 했다** — 시스템 바이너리(LibreOffice 등)가 필요해 python-docx 를 고른
  이유("순수 pip, 배포 단순")가 사라진다. 필요해지면 별건이다.
  ⛔ **프론트 다운로드 버튼도 안 했다** — 엔드포인트까지만. UI 를 붙이면
  `ui_honesty_contract` 가 파일당 6건 늘고 D87 검토가 따라온다.
  **착수 시 실측 2건이 계획을 바꿨다**:
  ㉠ `render_*_document()`·`render_documents()` 는 **f-string 평문 한 덩어리**를 돌려주지
     템플릿 199자리에 넣을 이름별 값 맵이 아니었다. "문안은 이미 있으니 배선만" 은
     절반만 맞았다 — 필드맵 계층이 추가로 필요했다.
  ㉡ 5종 전부 플레이스홀더가 **단일 `<w:t>` 런** 안에 온전해 치환이 깨끗하다.
     표가 문서당 9~13개라 평문 덤프였으면 전부 뭉개졌다.
  **미리보기 5종은 바이트 동일**하다(골든 `spikes/golden/*.txt` 가 고정) — 리팩터가
  화면에 나가는 문자열을 한 글자도 안 바꿨다.
  회귀: `spikes/docx_contract.py` **63건 신설**(🔴 **2026-09-16 정정** — 오래 **58** 로
  적혀 있었다. 러너 실측이 63 이고 CLAUDE.md 기준선도 63 이라 **이 줄만 어긋나 있었다**.
  구현 도중 값을 적고 마지막에 안 고친 것으로 보인다) · `tools_profile_contract` 20→21종
  (⚠ 지금은 **22종**이다 — D140 이 `assess_used_equipment_loan` 을 더했다. 이 20→21 은
  D124 시점 기록이다) ·
  `write_tool_contract` **30건 그대로**(쓰기 경로 무증가 = D10 무손상의 증거).
  아래는 착수 전 조사 기록 — 경위 참고용으로 남긴다.

- ~~**실제 .docx/.pdf 파일 생성 (2026-08-24 A2A_Q 세션 조사)**~~ — 사용자가 "승인 버튼 누르면
  docx/pdf가 생성된다"고 기억하고 있었으나 실측 결과 **미구현**이었다. `po_documents.py`·
  `generate_disposal_document.py`의 `render_*_document()`는 D86/D118 원칙("저장하지 않고
  조회 시점에 렌더")에 따라 **평문 미리보기 문자열만** 반환하고, `python-docx` 류 바이너리
  생성 라이브러리는 레포 전체(`pyproject.toml`·프론트엔드)에 0건. 신규 구현 시 데이터
  조립·비즈니스 룰은 `render_*_document()`에 이미 완결돼 있어 상대적으로 빠를 것으로 판단.
  경로 두 가지 검토함: ① `python-docx`로 `Document()` 직접 조립(순수 pip, 배포 단순·코드
  더 많음) ② 렌더 함수 출력을 진짜 마크다운으로 바꾼 뒤 `pypandoc`으로 1줄 변환(코드
  적음, 단 `pandoc` 시스템 바이너리 추가 필요 — Docker 배포면 `apt-get install pandoc`
  한 줄). **P6(발주서 내보내기)과 인접** — P6이 "PDF/이메일로 공급사 발송"이라면 이건
  "내부 승인 문서(01~04) 자체를 바이너리로 뽑는" 더 앞단 문제.
  상세는 `A2A_Q/docs/session_log/2026-08-24.md` §8 참고.
  ✅ **2026-09-03 — MaintQ 소유로 확정. A2A_Q(QMesh)는 관여하지 않는다.**
  근거: 문안·템플릿·`facts` 매핑이 전부 MaintQ 안에 있고, QMesh 는 README 상
  **"각 프로젝트 내부 구현을 알지 못하는 블랙박스"** 라 문서 문안을 알 수도 알아서도
  안 되는 자리다. InsuQ·FinAllQ 도 나중에 필요해지면 각자 자기 것을 만든다.
  **D86 은 유지한다 — 다운로드 시점에 생성하고 저장하지 않는다**:
  `승인 → 미리보기(지금대로) → [docx 다운로드] → 그 자리에서 생성·스트림`.
  ⛔ 생성물을 디스크·DB 에 저장하지 말 것 — 그건 D86 폐기라 별도 결정이 필요하다.
  경로 선택(① `python-docx` 직접 조립 / ② md+`pandoc`)은 **MaintQ 판단**이다. ②는 시스템
  바이너리가 필요해 배포가 한 겹 는다.
  준비 상태: 템플릿 6종(01~06) · 문안은 `render_documents()` 보유 · `facts` 17종 기계 대조 완료.
  **남은 것은 `python-docx` 의존성 추가와 배선뿐.**

  🔴 **곁가지 요구 — "MCP 도구로 문서 원본을 수정" 은 거부됐다 (2026-09-03). 근거를 남긴다.**
  docx 착수 논의 중 *"MCP 도구로 `facts` 를 수정할 수 있어야 한다"* 는 요구가 왔고,
  **절대규칙 1(D10)과 정면 충돌**해 그대로 받지 않았다. 다음에 같은 요구가 오면 이 항목을 보라.
  ㉠ **규율이 아니라 물리적 차단이다** — `mcp_server/db.py` 의 `draft_writer()`·
     `decision_writer()`·`repair_writer()` 가 TEMP TRIGGER 로 UPDATE 를 막는다
     (`MCP 도구는 po_drafts 를 수정/삭제할 수 없습니다 (D10, op=UPDATE)`).
     `write_tool_contract` 30건 중 **6건이 이 경계를 검증**한다.
  ㉡ **`facts` 출처가 D10 대상이다** — 01·02·03 은 `po_drafts`, 05·06 은 `assets`
     (MCP 가 `assets` 를 쓰는 경로는 **현재 하나도 없다** — 새 쓰기 권한을 여는 결정이다).
  ㉢ 🔴 **처분은 더 심각하다** — `assets` 를 고치면 `bundle_hash` 가 달라지고 `sign()` 이
     `EvidenceChanged` 로 **서명을 막는다**(D84). 사용자에겐 *"고쳤더니 결재가 안 된다"* 로
     나타난다. 이 점은 요구를 보낸 쪽도 몰랐던 것이고, 그대로 갔으면 그 상태를 만들 뻔했다.

  ✅ **확정 대안 (사용자 결정, 2026-09-03) — 읽기 도구 + 교정은 새 draft.**
  ```
  MCP 읽기 도구 → 현재 facts 조회        (UPDATE 없음)
  교정          → create_po_draft 로 **새 draft INSERT** (INSERT 는 원래 열려 있다)
  사람          → 화면에서 채택 · 또는 PATCH(P39)로 직접 수정
  docx          → 다운로드 시점 렌더 (저장 없음, D86 유지)
  ```
  **D10·D84 무손상.** TEMP TRIGGER 재설계도 회귀 6건 재작성도 없다.
  결정 근거: MCP UPDATE 로 얻는 건 "이미 만든 걸 대화로 고치기" 하나인데, 잃는 건 이
  프로젝트가 내세우는 문장 자체다 — *"AI 가 제안하고 사람이 결정한다"*. **"쓰기 권한의 선을
  DB 트리거로 강제했고 계약 테스트 6건이 그 선을 지킨다"** 가 더 강한 이야기다.
  ⚠️ **요구의 실질은 이미 구현돼 있었다** — "사람이 원본을 고칠 수 있어야 한다"는
  `PATCH /api/po`(D111)·`/api/repairs`·`/api/decisions`(P39, 2026-09-03)로 전부 열렸다.
  화면에서 고치고 다운로드하면 최신값이 렌더된다.

  ✅ **착수 시 판단할 것 2건 — 2026-09-04 결론 (아래가 원문, 결론은 각 항목 끝에)**:
  ㉮ **교정마다 새 draft 가 쌓이는 것을 감당할지.** 감사 관점에선 "3개로 제안했다가 5개로
     바꿨다"는 경과가 남아 **오히려 낫다**. 다만 화면에 draft 가 여러 개 뜨는 게 혼란스러우면
     교정은 화면 PATCH 로만 두고 **읽기 도구만** 넣어도 된다.
  ㉯ **읽기 도구가 노출할 필드** — 기존 도구 7종과 같은 결로. ⛔ 신원·서명 필드는 제외
     (D23 — 도구 스키마에 넣지 않는다는 기존 경계 그대로).

  → **㉮ 결론: 누적을 감수한다.** 감사 관점에서 경과가 남는 게 낫고, 화면이 혼잡해지면
    목록 필터를 손보는 것이 맞지 이 작업의 범위가 아니다. 사람의 직접 수정 경로는
    이미 열려 있다(PATCH 3종).
  → **㉯ 결론: 템플릿 자리 그대로(필드맵)를 준다.** 업무 값 subset 이 아니라 문서 자리와
    1:1 이라, 에이전트가 "어느 칸이 틀렸다" 를 짚어 말할 수 있고 원천이 없는 자리가
    `확인되지 않음` 으로 드러난다. 신원·서명 **16키**는 `WITHHELD_KEYS` 로 제외하되
    "안 준다"(`withheld`)와 "원천이 없다"(`unavailable`)를 **분리**해 싣는다(D62) —
    합치면 에이전트가 "요청자 이름이 시스템에 없다" 는 거짓을 말하게 된다.
  → **추가 결정: 읽기 도구 범위는 01·02·05·06 네 종.** 03 은 제외했다 — 내부통제
    판정(D119)은 `create_po_draft` 로 새 draft 를 넣어도 안 바뀌는 **교정 경로가 없는
    값**이라, 도구가 보여주면 에이전트가 그것을 두고 대화하게 된다.
    (docx 다운로드는 03 포함 5종 전부 지원한다.)

  🔴 **여기 오래 붙어 있던 차단 문구는 사실이 아니었다 — 기록해 둔다.**
  2026-08-29 커밋 `32c67c9` 가 *"QMesh 프로젝트에서 구현 진행 중이므로 이 레포에서 먼저
  착수하지 않는다(경로 선택도 QMesh 쪽 결정을 따른다)"* 라고 적었는데, **셋 다 틀렸다**:
  ㉠ **QMesh 는 별도 프로젝트가 아니라 A2A_Q 자신이다**(`A2A_Q/README.md:1` = `# QMesh`).
     별도 레포도 세션도 없다 — 찾아도 안 나오는 게 당연했다.
  ㉡ **A2A_Q 에서 docx 는 한 줄도 진행된 적이 없다** — `requirements.txt` 에
     `python-docx`·`pypandoc` 없음, grep 0건, 관련 커밋 0건. 유일한 언급은
     `docs/session_log/2026-08-24.md §8` 의 **경로 논의 기록**이고, 그걸 "진행 중"으로 잘못 읽었다.
  ㉢ 애초에 **아키텍처와 맞지 않았다** — 블랙박스인 QMesh 가 남의 문서 문안을 정할 자리가 아니다.
  ⚠️ **이 한 문장이 며칠간 착수를 막았다.** 실제로 2026-09-03 세션에서 "다음 작업으로 docx 를
  하자"고 제안했다가 이 문장을 뒤늦게 읽고 철회한 일이 있다. **검증되지 않은 차단 문구는
  없는 것보다 나쁘다** — 근거 없는 "대기"는 아무도 다시 확인하지 않는다.

### 2026-09-24 NVIDIA 해커톤 논의에서 나온 기능 (미착수 · 해커톤은 별도 레포에서 진행)

> 해커톤 작업은 제출용 새 레포(`~/MaintQ-NVIDIA`, WSL)로 옮겼다. 아래는 **MaintQ 본체에도 가치가 있는** 것만 추렸다.
> 조사 원문·실측 근거: 브랜치 `feat/nvidia-hackathon` 의 `docs/hackathon/day1.md`·`day2-prep.md` (이 브랜치는 master 에 합치지 않는다).
> 🔵 **2026-09-25 — 이 레포에서는 첫 두 항목을 Sprint 19 로 이관했다** (`docs/sprints/sprint-19.md`). 아래 각 항목의 표시 참고.

- **매뉴얼 온보딩 에이전트 — 새 기종 매뉴얼을 읽어 진단 데이터를 제안하고, 사람이 승격해야만 진단에 쓰인다.**
  → 🔵 **Sprint 19 로 이관·구현**(D153~D157, HV600). 아래 「착수 전 결정 필요 ①②」와 RAG 위치는 D146·D157·D148 로 확정됐다
  새 사업장·새 기종 도입 때마다 사람이 표를 옮겨 적던 일(D107·D109 의 IE5 추출이 그 수작업이었다)을 에이전트가 초안까지 한다.
  - 흐름: PDF 구조 파악 → 표 추출(D107 기하 기반 재사용) → 행 검증(코드 형식·중복·누락) → 저신뢰 행 표시 → **스테이징 draft 적재** → 사람 검수·승격
  - 스테이징 테이블: 근거(파일명·페이지) · 추출 신뢰도 · 상태(`staged`/`approved`/`rejected`). 승격은 **사람 전용 API**(D10·D81 과 같은 구조)
  - **온보딩 전용 DB 역할** — 스테이징 INSERT 만. 운영 테이블·결재 한도·조직/권한 테이블은 DB 수준에서 거부(`draft_writer` 패턴)
  - **별도 도구 프로파일** — 진단·발주·결재 도구에 접근 불가(D69·D88 프로파일 분리 확장)
  - **업로드 매뉴얼은 신뢰할 수 없는 입력** — 추출 텍스트 속 문장을 지시로 취급하지 않는다. 주입 문구가 든 테스트 페이지로
    "따르지 않고 의심 행으로 표시" 를 회귀로 고정할 것
  - 새 매뉴얼 후보 조사 완료(공개 PDF 4종, 텍스트 추출 확인): **Yaskawa HV600**(HVAC, 괘선 4열 표, 추천) · Mitsubishi FR-F800 · ABB ACH580 · Danfoss FC 102
  - 🔴 **착수 전 결정 필요 ①: 절대 규칙 4(기종 enum)와 충돌한다.** enum 이 코드 8곳 하드코딩(D109).
    추천안 — 새 기종을 enum 에 미리 넣고 "진단 가능" 은 DB 온보딩 상태로 게이트(승격 전 조회 = `not_found` → S4 흐름).
    대안 — enum 을 DB 에서 동적으로(규칙 4 개정, MCP 스키마 재적재 필요)
  - 🔴 **착수 전 결정 필요 ②: 새 기종 안전 문구** — 절대 규칙 3. 현 `SAFETY_BASELINE` 은 iG5A 근거라
    새 기종 진단 시 안전 게이트가 막을 가능성이 크다. 제안: 온보딩이 안전 문구 후보도 스테이징 → 사람 승인(safety-guardrail 스킬 규칙)
  - 새 매뉴얼 RAG 청크를 어디에 둘지 — 지금 인덱스는 파일(`data/extracted/manual_chunks.jsonl`). 런타임 추가라면 DB(`manual_chunks`, §24) 쪽
- **사업장 → 구역 → 설비(개별 대) → 기종 계층 + 설비 평면도(SVG)** — 온보딩 상태는 **기종 단위**로 관리
  (설비 수백 대라도 기종은 몇 종 — 기종 하나를 승격하면 그 기종 설비 전부가 진단 가능). 평면도는 외부 지도 API 없이 SVG,
  점 색으로 상태 구분, 설비 클릭 → 진단 콘솔. 목업 사업장은 실제 회사명을 쓰지 않고 목업임을 표시
  → 🔵 **Sprint 19 MQ-1914(선택, Stage 5)로 이관** — 시간이 남을 때만
  - ⚠ 설비 테이블에 컬럼을 더해도 **A2A 발신 페이로드·QMesh 계약은 바뀌면 안 된다**
- **NeMo Guardrails 입력 검사** — 업로드 문서·OCR 텍스트 같은 신뢰할 수 없는 입력에 `self check input`
  (메인 LLM 하나로 동작, 추가 모델 불필요). `nemoguardrails` 0.24.1 · Python 3.10~3.13. 휴리스틱 jailbreak 탐지는 영어 최적화라 한국어엔 약함
- **스킬 공급망 게이트 — SkillSpector** — 개발용 스킬(`.claude/skills/`)을 설치·수정할 때 NVIDIA SkillSpector 로 스캔.
  첫 스캔 결과는 아래 「알려진 결함」 참고. ⚠ Windows 에서는 긴 경로 문제로 `uv` 설치가 실패해 공식 Docker 이미지로 돌려야 했다
- **LLM 샌드박스 실행(OpenShell)** — D143 이 해커톤 브랜치에만 있다. 키는 게이트웨이에만, egress 기본 차단, 폴백 불가 명시.
  본체로 가져올지는 별건(브랜치 `feat/nvidia-hackathon` 의 `5e5e962`)

## 알려진 결함 — 테스트 격리·회귀 표기

- 🟡 **웹 콘솔 안전 가드가 부품 이름의 위험 키워드에 걸린다** (2026-09-28, 데모 장면 6 녹화 중 실측 — 고치지 않음).
  `backend/agent/loop.py::flush()` 는 문장마다 `prompts.needs_safety_block()`(키워드 텍스트 매칭)을 부르고, 그 턴에
  매뉴얼 근거(`st.pages`)가 없으면 문장을 「근거 문서를 확인하지 못해 작업 절차를 안내할 수 없습니다.」로 **치환**한다.
  S1 주인공 부품 FAN-IG5-01 의 이름이 「냉각팬 (iG5A 표준)」 이고 `냉각팬` 이 `DANGER_KEYWORDS` 에 있어서, 매뉴얼을 조회하지
  않는 **발주 초안 턴**에서 LLM 이 "냉각팬 2개 …" 라고 쓰면 그 문장이 잘린다(녹화 3회 중 2회 — 품번만 쓴 1회는 통과).
  ✅ 안전 쪽 오탐이다(경고 누락이 아니라 과잉). 발주 카드 block 은 정상으로 나온다. 고칠 때는 **게이트를 좁히지 말고**
  절차 서술(동사·작업 맥락)과 부품 명칭을 가르는 판정을 더할 것 — 키워드 삭제는 C-5 누락(2026-07-27)의 재발이다.
  프롬프트로 "품번만 쓰라" 고 하는 우회는 확률만 낮춘다. `SUBMISSION.md` §6 「안전 가드 오탐」

- 🟡 **A2A 클라이언트가 "중간 프록시의 응답" 을 "상대의 응답" 으로 오인한다** (2026-09-24 실측, 해커톤 샌드박스에서 발견).
  `backend/a2a/client.py::call_skill()` 은 HTTP 응답이 **오기만 하면** 차단기를 닫는다(D139 — "응답이 있었으면 상대는 살아 있다").
  그런데 egress 프록시가 연결을 막고 **자기가 403 을 돌려주면**, 상대(FinAllQ)에는 닿지도 않았는데 trace 는
  `status=error · A2A request failed with status 403` 이 되고 **차단기는 FinAllQ 를 "살아 있음" 으로 회계**한다 — 사실과 반대다.
  ✅ 업무 자체는 안 깨진다 — `finance-approve` 는 200 · `finance_approved` 로 끝났다(발신 실패를 라우터가 삼킨다).
  기업 프록시 뒤에 배포하면 같은 일이 난다. 고칠 때는 "응답 출처" 를 가를 근거가 필요하다(프록시 응답 헤더·본문 형태 등 — 미조사)
- 🟡 **A2A 이벤트 발신이 설정 누락 시 흔적 없이 끝난다** (2026-09-24 실측).
  `services/po.py::dispatch_a2a_withdrawal_request()` 는 `MAINTQ_A2A_FINALLQ_BASE_URL` 이 없거나 회사 연결이 없으면
  **trace 없이 `None` 을 반환**한다. 재무 승인은 됐는데 출금 요청이 왜 안 나갔는지 이력 화면에서 알 수 없다(D62 "모른다를 말한다" 와 어긋남)
- 🟡 **개발용 스킬 3종이 SkillSpector 에 걸린다** (2026-09-24, NVIDIA SkillSpector 정적 스캔 `--no-llm`).
  `run-eval` **PE3 HIGH** — `SKILL.md:16` 에서 `.env` 를 직접 `grep`(자격증명 파일 접근) · `done` **AS1 HIGH** —
  `SKILL.md:50` 에서 `.claude/` 를 `grep`(에이전트 설정 디렉터리 접근) · `stage` **RP1 MEDIUM ×2** — `SKILL.md:73` 버전 미고정 `npx`.
  나머지 5종 0점. `run-eval` 은 실제로 고칠 가치가 있다(비밀 파일을 셸로 읽는 관행)

- 🟡 **온보딩 적재기의 멱등 검사가 쓰기 트랜잭션 밖에 있다** (2026-09-25, Sprint 19 Stage 2 리뷰 발견,
  고치지 않음). `mcp_server/onboarding_load.py::_already_loaded()` 는 `read_only()` 커넥션으로
  "이미 적재됐는가" 를 먼저 보고, 그 다음 **별도 트랜잭션**인 `onboarding_writer()` 로 INSERT 한다 —
  이 둘 사이에 경합 창이 있다. 같은 `(manual_id, candidates_sha256)` 후보 파일을 **동시에** 두 프로세스가
  적재하면 둘 다 "아직 없음" 을 보고 둘 다 INSERT 를 시도해, 두 번째는 `onboarding_batches` 의 UNIQUE
  제약을 어겨 `load()` 의 `except Exception` 블록(라인 202)에 걸린다 — 그러면 멱등 종료코드 **3**(이미
  적재됨) 대신 **2**(입력 오류)로 끝난다. 실패가 fail-closed 이므로(아무것도 안 쓰고 종료) 데이터
  무결성 사고는 아니지만, 재시도 스크립트가 종료코드 2 를 "입력이 잘못됐다"로 오해할 수 있다.
  고치려면 `_already_loaded()` 조회와 INSERT 를 한 트랜잭션으로 묶거나 UNIQUE 위반을 3으로 재매핑해야
  한다 — 이번 리뷰 반영 범위 밖이라 코드는 그대로 둔다.

- 🟡 **Sprint 19 Stage 3 설계 리뷰 경미 지적 7건** (2026-09-25, MQ-1908·1909·1910 리뷰, **고치지 않음** —
  경고 4건·부수 2건은 같은 날 커밋 전에 반영했다. 아래는 그 밖의 경미 항목이다):
  - `backend/services/onboarding.py::_integrity_reason()` 가 제약 위반을 **예외 메시지 문자열**(`"manual_chunks" in msg`)로
    분류한다 — Postgres 메시지 문구·로캘이 바뀌면 조용히 422 `integrity` 로 떨어진다. `exc.sqlstate`(23505 등) +
    `diag.constraint_name` 으로 바꿀 것
  - `promote()` 의 `group_incomplete` 판정이 **배치 구분 없이 `(model, code)`** 로 staged 행을 모은다 — 같은 기종
    배치가 2개가 되면(개정판 재적재) 옛 배치의 staged 행까지 "누락" 으로 요구한다. 지금은 HV600 배치 1개라 잠재 결함
  - `check_safety_text()` 는 `\d+\s*분` 만 본다 — `10 minutes`·`600초`·`십 분` 표기는 숫자 검증을 **통과해 버린다**
    (규칙 1·3 의 사각지대). 승인자가 한국어 `N분` 으로 쓰는 것을 전제로 한다
  - `reject_safety()` 는 반려자를 기록하지 않는다 — `onboarding_safety_candidates` 에 `reviewed_by` 류 컬럼이 없다
    (승인은 `approved_by` 가 있다). 스키마 변경이 필요해 보류
  - `deploy/openshell/policy-nat.yaml` 에 스파이크 때 쓴 포트 **8775** 허용이 남아 있다 — 데모 토폴로지는 8766 만 쓴다
  - NAT 실행 stderr 에 매뉴얼 원문(행 `name_en`·`causes_en`)이 찍힌다 — **파일로 리다이렉트하지 말 것**(D144 —
    원문·번역문을 산출물로 남기지 않는다). `onboarding/nat/README.md` 에 경고 1줄을 넣었다
  - `onboarding/nat/README.md` L1 예시가 토큰을 `MAINTQ_NAT_MCP_TOKEN=<토큰> uv run …` 처럼 **셸 env 로 앞에 붙여**
    셸 히스토리에 남긴다 — L0 처럼 `--token-stdin` 을 쓰는 예시로 바꿀 것
- 🟡 **`stage_code_normalization` 의 `state='staged'` 확인과 정규화 INSERT 가 다른 트랜잭션이다**
  (2026-09-25, Sprint 19 Stage 2 리뷰 발견, 고치지 않음). `mcp_server/tools/stage_code_normalization.py`
  는 `read_only()` 로 `onboarding_code_rows.state` 를 확인한 뒤 `onboarding_writer()` 로
  `onboarding_normalizations` 에 INSERT 한다 — 그 사이 사람이 화면에서 그 행을 승인(`state` 전이)해도
  이 도구는 그걸 모르고 정규화 행을 계속 붙일 수 있다. 영향은 낮다 — 승격은 특정 `norm_id` 를
  명시적으로 골라 쓰므로, 승인 후 붙은 "고아" 정규화 행이 있어도 승격 결과에 섞여 들어가지 않는다.
- 🟡 **full 프로필 A2A 도구 3종이 `policy_blocked` 와 `circuit_open` 을 구분하지 못한다**
  (2026-09-25, D149 리뷰 발견 · **Sprint 19 범위 밖, 이월** — MQ-1913 은 문서 동기화만 한다. 샌드박스는 `core`
  프로필이라 이 3종이 노출되지 않아 데모 경로에는 영향이 없다). `assess_equipment_loan`·`assess_used_equipment_loan`·
  `search_insurance_clause` (각 `mcp_server/tools/*.py`) 는 백엔드가 돌려준 503 을 전부
  `reason: "circuit_open"` 으로 매핑한다 — 백엔드가 `A2APolicyBlockedError` 를 잡아 dict 형태
  `{"reason":"policy_blocked", ...}` 를 돌려줘도(`backend/routers/a2a.py`) 이 세 도구는 `detail` 의
  모양을 보지 않고 상태코드만 본다. 그래서 에이전트에게는 "우리가 연속 실패해서 막았다"(차단기)와
  "샌드박스 정책이 애초에 막았다"(policy_blocked, D149)가 똑같이 보인다 — 재시도 안내 문구도
  차단기 쪽 문구를 쓰게 된다. `docs/06_REPO_API.md` §2.9 참고.

- 🟡 **Sprint 19 온보딩의 알려진 한계 3건** (2026-09-25, 계획 단계에서 인지 — 고치지 않음):
  - **BYOC 덤프가 온보딩 역할·GRANT 를 옮기지 않는다** — 웹 콘솔 샌드박스 이미지용 덤프가 `--no-privileges` 라
    `maintq_onboarding` 역할·GRANT 가 빠진다. 샌드박스 안에서는 온보딩을 돌리지 않아 지금은 무관하지만,
    샌드박스 안 온보딩을 하려면 가드 SQL(`scripts/postgres_guards.sql`)을 따로 적용해야 한다(H8)
  - **승격 취소 API 가 없다** — `backend/routers/onboarding.py` 는 승격·행 반려·안전 승인/반려만 있다. 잘못 승격한
    `error_codes`·`manual_chunks` 행을 되돌리는 사람 경로가 없어 지금은 DB 직접 조작뿐이다(수동 절차는 `TODO_직접할일.md` H10)
  - **OpenClaw 경로의 HV600 안전 문구는 모델의 규칙 준수에 기대고 있다** — 백엔드 루프는 `resolve()`(D157) + 안전
    게이트로 강제하지만, OpenClaw 는 `deploy/nemoclaw/workspace/build.py` 가 생성한 워크스페이스 규칙을 모델이
    따르기를 기대할 뿐 런타임 게이트가 없다
- 🟡 **`law_fetch_contract ⓚ` 가 이 레포에서 매번 오탐 FAIL 한다** (2026-09-25, Sprint 19 Stage 1~3 회귀 매번).
  `.env` 의 `LAW_API_OC` 값이 GitHub 아이디와 같아 추적 파일(커밋 저자·URL 등)에서 "인증값 유출" 로 걸린다.
  코드 결함이 아니다 — **값을 실제 발급받은 OC 로 바꾸면 해소된다.** 그 전까지는 이 1건을 기존 오탐으로 보고하되,
  **다른 검사의 FAIL 까지 함께 넘기지 말 것**
- 🟡 **브라우저 검증에서 드러난 기존 UI·문구 이슈 4건** (2026-09-25, Sprint 19 Stage 1~3 브라우저 확인 중 발견 —
  Sprint 19 가 만든 것이 아니다, 고치지 않음):
  - 채팅 본문의 `**굵게**` 마크다운이 렌더되지 않고 별표가 그대로 보인다
  - TracePanel 「근거 문서」·「발주 이력」 탭을 눌러도 내용이 바뀌지 않는다 + `borderBottom` 관련 React 경고
    (콘솔이 가리킨 위치 `frontend/components/trace/TracePanel.tsx:70` — 원인 미조사)
  - Nemotron 응답에 중국어 「参照」가 섞여 폰트에 따라 네모 글자로 보인다(모델 출력 — 프롬프트·후처리 미조치)
  - `backend/routers/onboarding.py` docstring 의 *"`X-User` 기본값 `tech-01` 은 technician"* 은 부정확하다 —
    기본 역할을 정하는 것은 **`X-Role` 기본값**이다(D108). 코드 파일 문구 정정 필요
- 🟡 **요청자 식별자 `finallq_company_id` 가 빌더 5곳에서 `or ""` 로 뭉개진다** (2026-09-16 발견, D142 스코프 밖).
  `get_finallq_company_id()` 는 `link_state != 'LINKED'` 면 `None` 을 돌려주는데, 호출부가
  `or ""` 로 받아 **빈 문자열을 payload 에 싣는다**. 빈 요청자 식별자는 수신부에서
  `schema_validation_failed`(400) 가 된다 — `request-withdrawal` 이 `error_code=None` 으로
  정확히 그 400 을 맞은 전례가 있다.
  ✅ **`notify-asset-change` 는 D142 가 닫았고**, `request-withdrawal` 은 발신 경로
  (`services/po.py:461`)에 dispatch 게이트가 있어 **실제로는 안 나간다.**
  🟡 **남은 것은 `lookup-clause` · `assess-loan` · `assess-used-equipment-loan` ·
  `request-settlement` 4곳**이다 — 이 라우트들은 회사 결 연결을 확인하지 않는다.
  ⚠ **왜 이번에 같이 안 고쳤나**: `test_payloads.py` 40건 중 **26건만** `link_finallq` 를
  쓴다. 빌더에서 일괄 `raise` 로 바꾸면 나머지가 함께 움직여 «가드 1개 추가» 가
  «회귀 14건 재작성» 이 된다. 스코프를 지키려고 분리했다 — 고칠 때는 픽스처부터 정리할 것.



> 🔵 **2026-09-16 전수 대조.** 제목이 오래 *"(2026-08-29 발견, **미수정**)"* 이었는데
> **틀렸다** — 2026-08-29 자 3건(`a2a_identity_contract` 사망 · pytest `DATABASE_URL`
> 전제 누락 · A2A "86건" 표기)은 **전부 같은 날 고쳐졌고**(`be16ff6`·`53342ae`) 백로그만
> 안 닫혔다. 실행으로 확인했다(`a2a_identity_contract` **PASS 19건**).
> **지금 실제로 열려 있는 것은 위 2건뿐이다** — S13 도구 선택 취약성 · T07 인자 JSON 유출.
> ⚠ 둘 다 **우리 코드 쪽 원인이 실측으로 기각된** 상태라 고칠 자리가 특정되지 않았다.

- 🟡 **S13 도구 선택이 발화 표현에 취약하다 — 어림 금액·완곡 청유형이면 안 부르고 되묻는다**
  (2026-09-11 측정, `gpt-oss:120b`). D140 이 만든 `assess_used_equipment_loan` 을 **챗 경로로
  처음 태우면서** 드러났다. 배선은 전부 정상이다(등록 22종 · `EXT_TOOLS` 등재 · 통제군
  `lookup_error_code`·`rag_search_manual` 정상 호출). **호출될 때 인자는 항상 정확했다**
  (`asset_id`·`loan_amount`) — «못 부르는» 것이 아니라 «덜 명시적이면 되묻는» 것이다.
  실측(각 n=8, `/api/chat` 경유):

  | 발화 | 금액 | 요청 동사 | 호출 |
  |---|---|---|---|
  | A | 2천만원 **정도** | 「대출이 **될지** … 좀 **받아봐 줘**」 | **1/8** |
  | C | 2천만원 정도 | 「심사를 **요청해 줘**」 | 4/8 |
  | D | **20000000원** | 「될지 … 좀 받아봐 줘」 | 3/8 |
  | B | 20000000원 | 「심사를 요청해 줘」 | **8/8** |

  두 변수가 각각 기여한다 — 단일 방아쇠가 아니라 **「얼마나 명시적인가」가 연속적으로 작동**한다.
  🔴 **우리 코드 쪽 후보 둘을 실측으로 기각했다 — 추측으로 고치지 말 것.**
  ㉠ **도구 DESCRIPTION 의 `"명시적으로 물을 때만 호출할 것"` 게이트가 아니다.** 그 문장
  **하나만** 빼고 A 발화를 같은 8회로 재니 **2/8**(기준선 1/8)로 유의미한 변화가 없었다.
  고쳤으면 D140 의 남용 방지 경계만 잃고 증상은 그대로였을 것이다.
  ㉡ **MaintQ 시스템 프롬프트가 아니다.** 도구 목록·모델·문장을 고정하고 `system` 만 갈아
  **n=20** 으로 재니 정식 프롬프트 **8/20** · 최소 프롬프트 **8/20** 으로 **완전히 같았다**.
  (⚠ 그 전 n=8 회차는 2/8 대 5/8 이라 «프롬프트가 원인» 으로 보였다 — Fisher p≈0.31 로
  단언할 수 없는 차이였고 20회차에서 사라졌다. **이 레포가 D134·D135 에서 배운 노이즈
  교훈이 그대로 재현된 자리다.**) 프롬프트에 규칙을 더해도 듣지 않을 가능성이 높다는 뜻이라,
  «묻는 지점은 셋뿐이다» 규칙 위반으로 보고 문구를 보강하는 처방은 근거가 없다.
  ⚪ **미측정 축 하나**: 다른 모델에서도 같은지 못 쟀다 — OpenAI 키 **429**(쿼터 소진),
  Gemini `ClientError`. 남은 설명은 «모델의 인자 바인딩 성향» 이지만 **확증은 없다.**
  📌 **촬영 대응은 이미 확보돼 있다** — 「20000000원 … 심사를 요청해 줘」 문형이 8/8 이다.
  대본을 그 문장으로 고정하면 된다(A2A_Q 세션에 전달 완료).

- 🟡 **T07 에서 모델이 도구 인자 JSON 을 응답 본문으로 흘린다** (2026-09-09 발견, 기전 미확인).
  D137 20문항 측정에서 응답이 통째로 `{"model": null, "part_name": null, "part_no": "FAN-S100-01"}`
  으로 나온 회차가 **2/6**(대조군 0/6). 사용자는 아무 답도 못 받고, 채점은 `part_no=None` 으로
  미특정 처리한다. ⚠️ **D137 에 귀속할 수 없다** — 구간이 겹치고(0/6 [0,39] vs 2/6 [9.7,70])
  표본이 작다. 다만 대조군에는 없던 패턴이라 다음 측정에서 재현 여부를 확인할 것.
  원자료 `eval/results/full-d137/`.
  🔵 **2026-09-10 재현 시도 — 나오지 않았다 (0/20).** T07 단독 testset 으로 **각 arm 20회차**
  A/B 를 돌렸다(D137 20 · 대조군 20, 같은 날·같은 모델 `gpt-oss:120b`). **양쪽 모두 JSON 유출
  0건**이고 부품 특정은 **양쪽 20/20**이었다. 실행 실패 0 · 스트림 실패 0 · 폴백 0 · 잘린 턴 0.
  ⚠️ **"없다"로 닫지 않는다.** 0/20 의 95% 상한은 **16.1%** 이고 원 관측 2/6 은 [9.7, 70] 이라
  두 구간이 9.7~16.1 에서 **겹친다** — 말할 수 있는 것은 *"직전 관측만큼 흔하지는 않다"* 까지다
  (Fisher 양측 p≈0.046, 경계선). 게다가 두 표본은 **구성이 다르다** — 직전은 20문항 배치 안의
  T07, 이번은 T07 단독 배치다. 세션은 문항별로 독립이라 컨텍스트는 같지만 제공자 부하·시간대가
  다르다. **D137 귀속 의심은 이번 측정으로 약해졌다**(대조군에도 0, D137 에도 0).
  📌 부수 관측: 같은 20세션에서 D137 arm 의 `tool_result` 가 **213행**, 대조군이 **304행**이다
  (LLM 호출 수는 105 로 동일). 결론을 좁히는 조항이 **조회 자체를 줄인다**는 신호인데, 이 배치는
  그것을 겨냥해 설계하지 않았으므로 주장하지 않고 관측만 남긴다.
  원자료 `eval/results/t07-{d137,control}/`.

- ✅ ~~**부품 특정 40% 는 원천 데이터 부재라 오르지 않는다**~~ (2026-08-14 판단 → **2026-09-09
  정정**). 데이터를 한 줄도 늘리지 않고 같은 테스트셋에서 **88.9%** 가 나왔다. **두 가지를
  하나로 접은 것이 원인**이다: ㉠ *실제 제품* 관점에서 LS 가 소모품 품번을 공개하지 않는 것은
  **여전히 참**이고 P32 실측 그대로다 ㉡ 그러나 *이 지표* 가 채점하는 것은 **시드에 있는 정답
  부품을 고르는가**이고, 기대 품번 6종은 **전부 `parts` 테이블에 있다**(실측). 묶여 있던 것은
  데이터가 아니라 **모델·프롬프트**였다. 📌 *"못 하는 것을 정확히 말한다"* 는 태도는 옳았지만
  **한계가 어느 층에 있는지 가르기 전에 지표의 상한까지 단정한 것**이 성급했다. README §평가 ① 참고.

- ✅ ~~**`bundle_integrity ⑫` 가 FK 하나를 놓쳐 FAIL 한다**~~ (2026-09-03 발견 → **같은 날 해소**).
  `N2 — 판정 직후 자산 행 DELETE → error/asset_disappeared` 가 `DELETE 0행 ·
  reason=db_error` 로 떨어진다. **자산이 안 지워져서** `asset_disappeared` 대신 다른
  실패가 나는 것이다.
  원인: `assets` 를 참조하는 FK 가 **둘**인데(`equipment.asset_id`·**`decisions.asset_id`**)
  스파이크는 `equipment` 만 NULL 로 비운다(`spikes/bundle_integrity.py:505`). 그 사이
  판정이 `decisions` 행을 만들어 두 번째 FK 가 DELETE 를 막는다.
  ⚠️ **Sprint 16 Postgres 포팅 때 절반만 고친 것이다.** CLAUDE.md 가 이 검사를 두고
  *"SQLite 는 `foreign_keys` 기본 OFF 라 자산 행을 그냥 지울 수 있었지만 Postgres 는
  `equipment.asset_id → assets.asset_id` FK 를 강제해 DELETE 전에 비워야 했다"* 고
  적었는데, **`decisions` FK 는 그 목록에 없었다.**
  🔵 **P39 처분서 작업과 무관하다** — 그 변경을 `git stash` 로 걷어낸 상태에서도 동일하게
  재현된다(2026-09-03 실측). 고쳤다: DELETE 전에 `decisions` 행도 지운다(`spikes/bundle_integrity.py:505`).~~
  → **해소.** 26/26 복구. **뮤턴트로 실증했다** — 자산 DELETE 문을 no-op 으로 바꾸면
  정확히 ⑫ 만 FAIL 한다. 즉 이 수정은 검사를 무력화한 것이 아니라 **막혀 있던 전제를
  푼 것**이다(검사는 여전히 "자산이 사라지면 asset_disappeared" 를 판정한다).
  주석에 참조가 **둘**임을 명시했다 — `decisions` 행은 이 스파이크가 직접 만들지 않아도
  **판정 경로가 만들 수 있으므로**, "지금 픽스처에 없으니 괜찮다"가 아니라 항상 끊는다.

- ✅ ~~**`calls` 표기가 화면마다 의미가 다르다**~~ (2026-09-01 발견 → **2026-09-10 해소**).
  `frontend/lib/trace.ts::toTraceSession()` 의 `calls`(:125 `let calls = 0`)는 **받은 이벤트
  묶음 안의 `tool_call` 수**다. 그런데 그 함수를 두 화면이 쓴다:
  ㉠ **정비사 콘솔**(`DiagnosticConsole.tsx`) — **한 턴**의 이벤트만 받아 그리므로
     `4 → 1 → 0` 처럼 **턴마다 리셋**되는 게 정상이다
  ㉡ **매니저 트레이스**(`manager/trace/[sessionId]`) — **세션 전체** 이벤트를 받으므로
     같은 코드가 **누적값**으로 보인다
  ⚠️ **실제로 오독을 낳았다.** 2026-08-31 촬영에서 `calls` 가 `1 → 0 → 1` 로 리셋되는 것을
  보고 "세션 상태가 매 턴 초기화된다"는 가설이 섰고, 그 가설로 다른 세션에 조사가 위임됐다.
  진짜 원인은 이력 절삭(위 항목)이었고 `calls` 는 **정상 동작**이었다. 값 자체는 맞지만
  **같은 이름이 두 뜻**이라 세션 상태 판정에 쓸 수 없다.
  **고쳤다 — 두 번째 안(범위를 인자로)**: `toTraceSession(trace, scope)` 이 `TraceScope`
  (`"turn"` | `"session"`)를 **필수**로 받고, 라벨을 `callsLabel()` 한 곳에서 만든다 —
  `이번 턴 N회` / `누적 N회`. 호출자가 **선언**하게 한 것이 요점이다: 이 함수는 넘겨받은
  이벤트 묶음만 보므로 범위를 **추론할 방법이 없다.**
  ⚠️ **기본값을 두지 않았다.** 기본이 있으면 두 뜻 중 하나가 조용히 선택되고 그 순간 이
  결함이 그대로 돌아온다 — 새 호출자가 생기면 타입 검사가 그 자리에서 멈춰 세운다.
  범위 선언: `lib/chatStream.ts::rebuildTrace()` → `"turn"`(`startTurn()` 이 매 턴
  `traceEvents` 를 비운다) · `manager/trace/[sessionId]` → `"session"`.
  목업(`lib/mock/trace.ts`)·자리표시(`DiagnosticConsole` `EMPTY_TRACE`)도 같은 표기로 맞췄다 —
  **한 화면에 두 표기가 섞이면 고친 의미가 없다.**
  검증: `tsc --noEmit` clean · `next build` 25라우트 · `ui_honesty_contract` **327건 무변화**.

- ✅ ~~**대화 이력 절삭이 사용자의 핵심 사실을 먼저 버린다**~~ (2026-08-31 발견 → **2026-09-01 해소**).
  **증상**: 처분서 초안 하나 만드는 데 4턴이 걸렸고, 매 턴 다른 항목을 다시 물었다 —
  2턴에서 **1턴에 말한 자산 ID(`AST-L3-CONV`)를 잊었다.** 세션 ID 는 같았다.
  **원인은 `SessionStore` 버그가 아니다** — 2턴 재현 테스트에서 맥락은 정확히 유지됐다
  ("담당 설비는 INV-L3-01" → 다음 턴 "INV-L3-01 입니다"). 진짜 기전은 **이력 절삭**이다:
  `backend/agent/loop.py` 는 이력에 **셋**을 쌓는다 — 사용자 메시지(:353) · 어시스턴트
  응답(:457) · **도구 결과(:544, D76)**. `HISTORY_LIMIT = 20` 을 넘으면 `append()` 가
  **앞에서** 잘라낸다(`del h[: len(h) - HISTORY_LIMIT]`). 처분 흐름은 턴마다
  `track_deadlines`·`check_disposal_blockers` 등을 부르므로 **턴당 4~5개**가 쌓이고,
  4턴이면 20 을 넘겨 **1턴의 사용자 메시지가 가장 먼저 사라진다** — 하필 사용자가 처음
  말한 핵심 사실이다.
  ⚠️ **같은 계열 사고가 이미 한 번 있었다.** `HISTORY_MAX_ITEMS` 주석(loop.py:63-65)에
  *"5 였다가 10 으로 올렸다: 견적이 2건인데 이력에 A사만 남으면 다음 턴에 B사 단가가 없어
  발주가 틀어진다"* 고 적혀 있다 — **같은 함정이 한 단계 위(`HISTORY_LIMIT`)에서 재발했다.**
  단순히 20 을 키우는 건 토큰·비용을 밀어올리므로 답이 아니다. 고칠 때 검토할 것:
  ㉠ 절삭을 role 인지적으로(도구 결과를 사용자 메시지보다 먼저 버린다)
  ㉡ 사용자 메시지는 별도 예산으로 보존
  ㉢ 절삭 시 "…앞부분 N건 생략" 표식을 남겨 **조용히 사라지지 않게** 한다
     (`HISTORY_MAX_ITEMS` 가 이미 쓰는 방식)
  🔵 데모에서는 되묻는 장면이 오히려 좋게 보였지만 **대화형 UX 로는 결함**이다.~~
  → **해소.** `SessionStore.append()` 가 상한 초과 시 **역할을 보고 골라 버린다** —
  우선순위 `tool` → `assistant` → `user`(`_EVICT_ORDER`). 근거: **도구 결과는 재호출로
  되살릴 수 있지만 사용자가 한 말은 되살릴 방법이 없다.** 예전 구현은 그 구분 없이 앞에서
  잘라 가장 되살리기 어려운 것을 가장 먼저 버렸다.
  ⛔ **상한(20)은 키우지 않았다** — 위 ㉠~㉢ 중 ㉠을 택했다. 증량은 토큰·비용만 밀어올릴
  뿐 순서가 그대로면 몇 턴 뒤 똑같이 사라진다. 문제는 양이 아니라 **무엇을 먼저 버리느냐**였다.
  ㉢(표식)은 **운영자용 경고**로 넣었다 — 사용자·어시스턴트 메시지까지 버릴 때만
  `logger.warning`(도구 결과만 버린 건 정상 운영이라 경고로 시끄럽게 하지 않는다).
  프롬프트에 합성 마커를 넣는 방식은 택하지 않았다 — 모델이 그것을 사용자 발화로 오인한다.
  회귀는 `agent_loop_contract ②-c`(36→37). 수정 전 실측은 `user 0건 · 자산ID 생존=False`
  였다: 사용자 메시지가 **통째로** 사라지고 있었다.

- 🟢 **`lien_consent_ref` 값에 접두사가 겹친다** (2026-08-31 발견, 기능 영향 없음).
  `backend/routers/a2a.py` 가 `f"A2A-SETTLE-{chain_id}"` 로 조립하는데 `chain_id` 자체가
  `CHAIN-SETTLE-` 로 시작해 실제 값이 `A2A-SETTLE-CHAIN-SETTLE-e1281b75` 가 된다.
  유일성·추적성(`traces` 로 되짚기)은 온전해 **기능상 문제는 없다.** 다만 사람이 읽을 때
  중복이 눈에 띈다. 고칠 때 주의: 이미 저장된 값이 있는 DB 에서 형식을 바꾸면 과거 값과
  새 값이 섞이므로, 되짚기 규약을 먼저 정하고 손댈 것.

- ✅ ~~**본문이 빈 응답이 조용히 정상 종료된다**~~ (2026-08-29 발견 → **2026-08-31 해소**).
  `elice_chunk_delta` 는 `delta.content` 만 읽고 `reasoning`/`reasoning_content` 는
  버린다. 추론 모델이 본문을 안 내면 텍스트 0글자가 되는데, `backend/agent/loop.py` 의
  `if not pending: break` 가 그대로 턴을 끝낸다 — `TRUNCATION_REASONS` 가
  `MAX_TOKENS`/`LENGTH` 만 보므로 `finish_reason=stop` + 빈 본문은 **예외도 경고도 없이**
  지나간다. InsuQ 는 같은 상황에서 `TruncatedResponseError` 로 터졌는데(그래서
  `gpt-oss-120b` 를 기각했다), MaintQ 는 **터지지 않고 빈 응답을 낸다** — 어떤 면에서는
  더 나쁘다. 현재 모델(`openai/gpt-oss-120b`)에서는 발화하지 않았지만(도구 5종 정상 호출)
  모델을 바꾸면 발화할 수 있다. 최소 조치는 "텍스트 0글자 + 도구 호출 0건 + `stop`" 을
  경고로 남기는 것.~~
  → **해소.** `loop.py` 의 `if not pending: break` 앞에 "텍스트도 도구도 없음" 분기를 세워
  WARNING 을 남기고 사용자에게 *"응답을 받지 못했습니다. 다시 시도해 주세요."* 를 말한다
  (09_RUNTIME §3 — 확인하지 못했다를 명시한다). 부분 스트림을 이어 붙이거나 재시도하지는
  않는다(스트림 실패 경로와 같은 태도). 회귀는 `agent_loop_contract ②-b`(35→36건) —
  ② "텍스트 있고 도구 없으면 종료" 의 **음성 쌍**이다. 수정 전 실측은 `token 0건` 이었다:
  사용자에게 **빈 화면이 실제로 나가고 있었다.**
  ⚠ **근본 원인은 그대로 남아 있다** — `elice_chunk_delta` 는 여전히 `delta.content` 만
  읽고 `reasoning`/`reasoning_content` 를 버린다. 이 수정은 "조용히 실패하지 않게" 만든
  것이지 "추론 모델의 본문을 읽게" 만든 것이 아니다. 후자가 필요해지면 별건이다.

NVIDIA provider 전환 작업(`feat/llm-provider-unification`) 중 회귀를 돌리다 드러났다.
**셋 다 그 브랜치와 무관한 기존 문제**이고, 범위를 지키려고 기록만 하고 넘어갔다.
1·2 는 실제로 사람을 멈춰 세우는 종류라 다음에 회귀를 만지는 사람이 먼저 볼 것.

- ✅ ~~**`spikes/a2a_identity_contract.py` 가 D120 이후 죽어 있다**~~ (2026-08-29 발견 →
  **같은 날 해소, `be16ff6`** — 「백로그만 안 닫혔다」. 2026-09-16 실측 확인: 컨테이너를
  올리고 돌려 **PASS 19건**, `client_secret`·`FAKE_SECRET` 단언은 `cred.token`·`FAKE_TOKEN`
  으로 이미 교체돼 있다(`spikes/a2a_identity_contract.py:566`). 따라서 아래 *"기준선
  33스위트/1,075건은 재현 불가능하다"* 는 서술도 **더 이상 사실이 아니다**).
  `AttributeError: 'PartnerCredential' object has no attribute 'client_secret'`
  (`spikes/a2a_identity_contract.py:558`). D120(`ba340a6`)이 파트너 인증을
  Basic(`client_id`/`client_secret`) → Bearer(`token`)로 바꾸면서 `PartnerCredential`
  필드를 `token` 하나로 합쳤는데, **그 커밋은 `spikes/api_contract.py` 만 고치고 이
  스파이크는 안 고쳤다.** 즉 CLAUDE.md 의 기준선 **“33스위트 / 1,075건”은 지금 재현
  불가능하다** — 이 스위트(19건)가 실행 도중 예외로 죽는다. 기준선을 신뢰해 “전수 통과”
  라고 보고하면 사실과 다르다. 고치려면 `run_env()` 의 `client_secret`·`FAKE_SECRET`
  단언을 `token` 기준으로 다시 쓰면 된다(D120 의미는 그대로 검증 가능).

- ✅ ~~**`backend/agent/test_llm_cache.py::test_trace_replay_marks_events_when_cached` 가
  공유 DB 로 샌다.** `TraceWriter(db_path=tmp_path / "t.db")` 로 **`Path` 객체**를 넘기는데
  `backend/db.py:56` 은 `isinstance(db_path, str) and startswith("postgresql://")` 일 때만
  인자를 존중한다 — `Path` 는 조용히 무시되고 `DATABASE_URL` 로 간다. CLAUDE.md 가 Sprint 16
  4차 체크포인트에 적어 둔 **그 버그 계열 그대로**다(“DSN 을 `Path()` 로 감싸면 검사를 벗어나
  실 DB 로 샌다”). 테스트 docstring 은 아직 *“`tmp_path/"t.db"` 는 스키마가 없는 빈 sqlite
  파일이라 `_persist` 가 예외를 삼킨다”* 는 **SQLite 시절 전제**로 적혀 있어, 읽는 사람이
  격리돼 있다고 착각한다. 기준선 워크트리(`e963f9e`)에서도 동일 재현 확인.
  Postgres 가 떠 있으면 그냥 통과해서 **아무도 모르고 지나간다** — 내려가야 드러난다.~~
  → **해소 (2026-08-29, `714b900`).** `TraceWriter.__init__` 에 런타임 가드를 넣어
  DSN 아닌 값은 `TypeError` 로 즉시 실패시키고, 두 테스트를 `data.pg_isolation` 격리
  스키마로 옮겼다. 낡은 docstring 도 정정. 가드 회귀 2건 추가.
  → **일반화 완료 (2026-08-29, `d0ffc96`)**: `connect()` 인자 경로에 같은 가드를 세웠다.
  그 즉시 실제 유출 2건을 더 잡았다(`write_tool_contract` 가 격리 스키마 튜플을
  언패킹 없이 넘겨 **공유 DB 를 stamp** 하고 있었고, `approvals_contract ④` 는 D119
  이후 FAIL 중이었다). 이후 `data/seed.py::verify()` 의 `Path` 유출도 같은 가드가 드러냈다.
  🔵 **`DB_PATH` 전역은 가드하지 않기로 확정한다 (2026-08-31 재검토).** 근거:
  ㉠ `backend/db.py:28` 의 기본값이 **`Path`** 라 전역을 조이면 평상시 호출이 전부 터진다 —
  기본값부터 바꿔야 하고 그건 `disposal.py` 의 잔존 SQLite 분기까지 번진다.
  ㉡ 그런데 그 `Path` 기본값은 **무해하다**: `connect()` 도 `disposal.py` 도
  `isinstance(dbp, str) and startswith("postgresql://")` 로 걸러 `DATABASE_URL` 로 간다.
  ㉢ **실제 사고 4건이 전부 인자 경로였다**(`test_llm_cache`·`write_tool_contract`·
  `seed.py`·Sprint 16 의 `payloads.py`/`trace.py`). 전역으로 들어온 사고는 **0건**이고
  스파이크 8곳은 전부 DSN 을 넣는다.
  → 이미 있는 인자 가드가 실제 발생 지점을 전부 덮는다. 전역 가드는 가설적 위험을 막으려고
  회귀 전체를 한 줄에 인질로 잡는 거래다. **하지 않는다.**

- ✅ **pytest 는 `DATABASE_URL` 없이는 매단다** — **현상은 그대로 유효하고, 「CLAUDE.md 에
  전제가 빠졌다」는 부분만 2026-08-29 `53342ae` 로 해소됐다**(2026-09-16 확인 — 아래 실행
  커맨드가 CLAUDE.md 「회귀 스위트」 절에 실려 있다). ⚠ **함정 자체는 사라지지 않았다** —
  아래 설명은 앞으로도 유효하니 지우지 말 것.
  pytest 실행 경로에는 `load_dotenv` 가 없어
  (`backend/main.py` 에만 있다) `backend/db.py:21` 의 기본값 `postgresql://localhost/maintq`
  = **포트 5432** 로 떨어지는데, `docker-compose.yml` 의 컨테이너는 **5434** 다. 아무도 듣지
  않는 포트라 psycopg 가 타임아웃 없이 멈춘다 — 실패가 아니라 **무한 대기**라 원인 파악이
  오래 걸린다. ⚠ **CLAUDE.md 「회귀 스위트」 절의 pytest 실행 커맨드에 이 전제가 빠져 있다** —
  적힌 대로 복사해 돌리면 그대로 밟는다. 실제 실행은 아래처럼 해야 한다:
  `DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" uv run --with pytest ...`
  ~~(이 정정은 CLAUDE.md 수정이 필요해 **사람 확인 대기 중**이다.)~~
  → **반영 완료 (2026-08-29, `53342ae`).** 대기 중이 아니다.

- ✅ ~~**A2A 8파일군 “86건” 은 러너 출력이 아니다.**~~ (2026-08-29 발견 → **같은 날 해소,
  `53342ae`** — 86→88 정정. 이후 파일군이 **9파일 156건**으로 자라며 CLAUDE.md 가 파일별
  실측을 싣고 *"`N passed` 만 grep 하지 말 것 — 요약 줄 전체를 보거나 `--collect-only` 로
  교차 확인한다"* 는 규칙까지 명문화했다. 2026-09-16 확인.) 원 기록은 아래에 남긴다: `def test_` 개수를 센 값이고 실제
  pytest 출력은 **88** 이다 — `backend/a2a/test_client.py:213` 의
  `@pytest.mark.parametrize("status_code", [502, 503, 504])` 가 함수 1개를 3건으로 편다.
  CLAUDE.md 는 바로 위 문단에서 **“건수는 러너 출력이 기준이다”** 라고 못박고 있어
  자기 규칙과 어긋난다. 이 값을 기준선 대조에 쓰면 **항상 +2 가 남아** 원인을 엉뚱한
  곳에서 찾게 된다.

---

## 백로그에 넣지 않은 것 (경계 메모)

혼동하기 쉬워서 명시한다 — 아래는 **MVP 본체**다 (`00_MVP_SCOPE` 참조).

- 공급사 **비교 제시**는 MVP / 다운타임 비용 기반 **추천**만 P2
- 승인 **워크플로우**는 MVP / 팀장 **알림**만 P3
- `requested_by`·`decided_by`·`reason`·`evidence` **기록**은 MVP / 불변 **감사 로그**만 P5
- 반복 고장 **감지**는 MVP / 예측 **모델**만 P10

그리고 확장 범위 쪽 경계 (D67):

- 진단·발주는 기존 6종 / **처분·취득**은 확장 6종 (P22~P27). 도구로는 **코어 7종 / 확장 13종**이며 노출은 `MAINTQ_TOOLS_PROFILE` 이 가른다 (D69). 확장 8번째는 `generate_disposal_document`(Sprint 7 신설, **두 번째 쓰기 도구**), 9번째는 `create_repair_record`(Sprint 9 신설, **세 번째 쓰기 도구**, D98), 10번째는 `track_deadlines`(Sprint 11 신설, F5, D102), 11번째는 `assess_risk_grade`(Sprint 11 신설, F6, D102)
- 매뉴얼 **근거 페이지** 인용은 기존 / **법령 조문** 인용은 확장
- 반복 고장 감지는 기존 / 그걸 **자산가치 감점 신호로 재사용**하는 건 확장 (P26)
- 팀장 승인 큐는 기존 / 그 큐에 **처분서·수리 증빙을 같이 올리는 것**은 확장 (P24·P25)
