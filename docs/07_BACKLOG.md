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
| P9 | 예산/승인 한도 체크 | 금액 구간별 승인 단계 차등 (팀장→부장) | `unit_price`×`qty`가 서버 계산값이라 신뢰 가능(D31). `state` 확장 + `ALLOWED_FROM` 규칙 추가로 대응 |
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
| **P39** | **화면 직접 초안 생성 + 수정 가능한 초안 (발주서·처분서·수리증빙 3종)** ✅ **발주서(D111, 2026-08-23)·수리증빙(2026-09-03) 완료 — 3종 중 2종** — `POST /api/po`·`PATCH /api/po/{po_id}`·`/technician/po/new`·`/technician/po/[poId]`. **⏩ 수리증빙 2026-09-03 완료** — `data/repair_record.py` 공유 계층 + `POST/PATCH /api/repairs` + `/technician/repair/{new,[repairId]}` + `RepairForm.tsx`. `create_repair_record` 는 그 공유 계층에 위임해 329→241줄로 얇아졌고 **출력은 불변**(`write_tool_contract` 30건 전후 동일). 회귀 `repair_flow_contract` 19→28 · `ui_honesty_contract` 303→321(+18, D87 위반 0). **처분서만 남았다** — 처분은 룰엔진 판정·`evidence_bundle`·`bundle_hash`(D84)가 얽혀 입력 수정이 **재판정**을 부른다(발주·수리에는 없는 문제). 그 재판정 규약을 먼저 정해야 하므로 별건이다. ~~처분서·수리증빙은 여전히 미착수~~(범위를 발주서만으로 의도적으로 좁혔다 — P41이 필요로 하는 건 발주서뿐이라, 스펙 §0-1) | 2026-08-17 브레인스토밍(설비 하이라이트 대시보드 논의 중 파생)에서 나온 요청 — "발주서 양식은 정해져 있으니 화면에서 바로 채워서 만들 수 있어야 하고, 사람이 요청하기 전에 AI가 먼저 대령하는 건 부가 기능일 뿐이다. 생성된 초안(발주서·처분서 등)은 전부 수정 가능해야 한다." **지금은 정반대 구조다** — `create_po_draft`·`generate_disposal_document`·`create_repair_record` 3종 전부 **MCP 도구로만 존재**(REST 경로 없음, 에이전트 채팅에서만 호출), 생성된 초안은 **불변 스냅샷**이다(`unit_price`는 D31 이 잠근 서버 계산값, 처분서는 룰엔진 판정 결과라 자유수정 개념 자체가 없음). ⚠ **이미 한 번 같은 고민을 하고 다른 결론을 낸 선례가 있다** — `docs/06_REPO_API.md §2.2` 바로 위 주석: 처분서 흐름은 *"요청은 채팅(prefill), 제출은 화면"* 으로 정해져 있고 근거는 D18("승인 큐 진입은 채팅 밖")·D29("이력 기록은 명시적 액션")다. 이번 요청은 **그 선례를 깨고 화면이 직접 신규 레코드를 만드는 이 프로젝트 최초의 경로**를 여는 것이라 다음이 필요하다: ① 왜 예외를 허용하는지 새 D-결정 ② 3개 도구 각각의 산출 로직을 `data/` 공유 계층으로 옮기는 리팩터(이번 스프린트에 `assess_repair_value`·`get_maintenance_metrics` 등을 REST 로 열 때 쓴 것과 같은 패턴, `data/maint_value.py` 선례) ③ 새 백엔드 서비스·라우터(`POST /api/po`·`POST /api/decisions`·`POST /api/repairs` 신설) ④ **"수정 가능한 초안"이라는 완전히 새로운 데이터 모델**(지금 3종 전부 생성 후 불변이 원칙 — 어디까지 수정을 허용할지부터 재설계 필요, 예: `unit_price` 처럼 서버가 계산해 잠근 필드까지 수정 가능하게 하면 D31 의 존재 이유가 흔들린다) | 이번 브레인스토밍에서 설계한 "설비 하이라이트 대시보드"(재고 확인 드로어의 "발주하러 가기" 버튼)는 **이 기능이 없는 동안 기존 선례대로 채팅 이동+prefill 로 임시 처리**하기로 함 — 이 P39 가 완성되면 그 버튼을 직접생성으로 바꿔 끼우면 된다. 3종 도구의 REST 미노출 현황·현재 계약은 `04_MCP_TOOLS.md`·`06_REPO_API.md §2.2·§2.6·§2.8` 참고 |
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

> 출처: `../A2A_Q/Q시리즈_시나리오맵_S1-S18.html` (기준 2026-08-14 · FinAllQ Sprint 10 완료 반영).
> 이 지도는 **MaintQ · FinAllQ · InsuQ 세 프로젝트의 시나리오를 S1~S23 한 체계로** 잡는다.
> MaintQ 단독 시나리오로 **S1~S4 · S9 · S10 · S17 · S18** 을 인정하고, 경계를 넘는 것이 10개다.

| P | 기능 | 설명 | 미리 확보해둔 것 |
|---|---|---|---|
| **P33** | ✅ **완료 (Sprint 12, 2026-08-18)** | **시나리오 번호 충돌 정정 — MaintQ 의 `S19` → `S29`** | **MaintQ 가 로컬로 붙인 `S19`(수리 증빙 서명, `02_SCENARIOS.md:82`)가 Q 시리즈 전사 지도의 `S19`(FinAllQ **기업 고객 온보딩** — 등록→앵커→초대, 구현 완료)와 정면 충돌했다.** 지도는 MaintQ 몫으로 S1~S4·S9·S10·S17·S18 을 **이미 인정**하고 있어 다른 번호는 어긋나지 않았다 — **어긋난 것은 `S19` 하나뿐**이고, 지도가 *"MaintQ는 S1~S4로 잡혀 있었죠"* 라고 적은 데서 보듯 **MaintQ 가 S19 를 만든 사실을 지도가 몰랐다.** 정정 2안 중 ⓐ **MaintQ 가 번호를 옮긴다 → `S29`** ⓑ **전사 지도를 고쳐** S19 를 MaintQ 에 주고 FinAllQ 를 밀어낸다(FinAllQ 가 이미 구현 완료라 **비용이 훨씬 크다**) 가운데, **채택안 ⓐ**로 결론이 났다. 근거 번호는 `../A2A_Q/11_A2A_SCENARIOS.md:98`(*"FinAllQ 가 S19~S23 을 선점했으므로 InsuQ 는 S24~S28 을 쓴다"*)이 **InsuQ 에 이미 S24~S28 을 배정**해 뒀다는 사실에서 나왔다 — **비어 있는 첫 번째 번호가 `S29`**다. 사람 협의 결과 **`S29` 채택이 승인**돼, Sprint 12(MQ-1201)가 살아있는 문서(`02_SCENARIOS.md`·`12_MAINT_VALUE.md`·`00_MVP_SCOPE.md`·`04_MCP_TOOLS.md`·`06_REPO_API.md`·`07_BACKLOG.md`·`README.md`·`docs/status/*.html`)의 `S19`를 전부 `S29`로 치환하고, 역사 기록(`docs/sprints/sprint-6~11.md`)은 본문을 보존한 채 forward-reference만 추가해 정정을 완료했다 | 충돌 지점이 **`S19` 단 하나**였다. MaintQ 내 `S19` 사용처는 `rg -l "S19" docs/` 로 전수 가능했다(문서 10여 개, 코드 0). **번호는 문서에만 있고 DB·도구 계약·enum 에는 없어** 회귀를 깨지 않고 바꿀 수 있었다 |
| **P34** | 🟡 **부분 재개 (D112, 2026-08-23 → S13·S12 추가 2026-08-30)** — **MaintQ 발신 A2A — 경계 시나리오 8종** | 지도가 세는 **경계 시나리오 10개**(S5·S6·S7·S8·S11~S16, 2026-08-14 스냅샷 번호) 중 **MaintQ 가 발신자**인 것: **S5**(출금 요청→FinAllQ 2단 승인) · **S7**(화재보험 갱신 상담→InsuQ) · **S11**(보험 목적물 변경 통지→InsuQ) · **S12**(매각대금 정산·대출상환→FinAllQ) · **S13**(중고설비 취득→담보심사, 멀티홉) · **S14**(위험등급 변동 통지→InsuQ) · **S16**(설비 취득 자금조달 비교 상담→FinAllQ). S10 에서 **담당자가 서명하는 순간** S11·S12 로 이어지는 것이 지도가 그린 연결점이다. 🔑 **지도의 핵심 관찰**: FinAllQ 는 *"S5 가 도착하면 타야 할 레일(S20 결재 + S21 FDS + 감사 로그)이 **이미 다 깔려 있고**, 빠진 것은 흐름이 아니라 **바깥으로 난 문**(Agent Card · :9001)"* 이다 — 즉 **양쪽 다 문만 없다.** ⛔~~MaintQ 쪽도 같은 상태이며 `README.md` 다음 액션 8 이 *"A2A 호출부는 QMesh 착수 후"* 로 이미 유보해 뒀다 — **이 P 는 그 유보를 백로그 번호로 고정하는 것**이지 착수 신호가 아니다.~~ → **D112(2026-08-23)로 뒤집혔다.** A2A_Q 레포에 실제 어댑터(`adapters/finallq_a2a`·`insuq_a2a`)가 생기면서 "검증할 상대가 없다"는 유보 근거가 무효화됐고, 위 8종 중 **S5(출금 요청)만** `request-withdrawal`로 구현·커밋됐다(나머지 7종은 여전히 미착수). 여기에 구 목록에 없던 **lookup-clause**·**assess-loan**(설비 담보 대출 사전 판정, 2026-08-23 신규)도 함께 구현됐다 — **assess-loan은 개념상 S13(중고설비 취득 담보심사)에 가장 가깝지만 정확히 같지는 않다.** 사용자가 2026-08-23 제시한 최신 A2A_Q 시나리오맵은 이 표의 S5·S13·S11을 각각 **S1·S4·S5**(새 번호)로 부른다 — `S19→S29`(P33) 선례와 같은 종류의 번호 충돌이니 아래 표의 번호는 **2026-08-14 스냅샷 기준임을 인용할 때마다 명시할 것**. **구체 사례(2026-08-17 브레인스토밍에서 추가)**: 설비 하이라이트 대시보드 설계 중 "수리 판정 시 재고가 없으면 자동으로 FinAllQ 에 자금 조달 통신을 보내자"는 아이디어가 나왔다 — 이건 **S5(출금 요청)의 구체적인 발화 조건 한 가지**로, 새 시나리오가 아니라 S5 트리거 목록에 포함시킬 것 | Sprint 8 이 신원 계층을 깔아 뒀다 — `partner_links`(D91·D96) · 자격증명 위치(D93) · `traces.request_chain_id`(D94, **이제 컬럼만이 아니다** — `backend/a2a/trace.py`가 실제로 쓴다, D112). `spikes/a2a_identity_contract.py ⑪-b` 는 이미 뒤집혀 있다  **⏩ 2026-08-30 갱신 — 발신 3종 → 5종.** `assess-used-equipment-loan`(S13)·`request-settlement`(S12) 발신 트리거를 구현했다. **S12 는 MaintQ 발신 스킬 중 처음으로 응답이 MaintQ 상태를 바꾼다** — `lien_released: true` 가 `assets.lien_consent_ref` 를 채워 LIEN-CONSENT(BLOCKING)를 해소한다. ⛔ **서명하지는 않는다** — 담보만 풀고 서명은 사람이 한다(`disposal_sign_contract` 26/26 유지가 그 독립 증거다). 빈 문자열은 쓰지 않는다(`''` 는 `is_null` 을 False 로 만들어 BLOCKING 룰을 조용히 미발화시킨다, seed 검사 ⑱). 🔵 **나머지 3종은 '미착수'가 아니라 '데이터 없음'으로 닫는다** — 언젠가 할 일과 하지 않기로 한 일은 다르게 적어야 한다: ㉠ `advise-hedge`(S6) — MaintQ 에 통화·외화 데이터가 **0건**이다. 만들려면 공급사에 통화 컬럼을 신설하고 환노출을 지어내야 한다(D62 위반). ㉡ `advise-financing`(S16) — 트리거가 될 도메인 이벤트가 없다. ㉢ `advise-replacement-financing`(S15) — 2차 홉 전용인데 MaintQ 에 `claim-insurance` 발신 흐름 자체가 없어 사실상 두 스킬 작업이라 별도 사이클이다. |
| **P35** | **나가는 A2A 호출의 차단기(circuit breaker) 경계** | 지도가 FinAllQ 내부 구조를 설명하며 명시한 교훈 — *"코어와 모델을 프로세스 단위로 갈랐다. 같은 프로세스에 태우면 **모델이 죽을 때 이체도 같이 죽는다.** 사이에 **차단기**를 둬 AI 장애가 코어로 번지지 않게 했다 — **A2A 에서 남의 에이전트를 부를 때도 같은 경계가 필요하다.**"* MaintQ 가 P34 를 착수하면 **상대 서버(FinAllQ·InsuQ)의 장애가 MaintQ 의 진단·발주까지 끌고 내려가지 않아야** 한다. 함께 볼 것: FinAllQ 는 감사 로그·AI 전송 페이로드를 **화이트리스트(등재된 키만)** 로 내보낸다 — *"블랙리스트였다면 새 필드가 생길 때마다 빠뜨릴 위험이 생긴다. 계좌번호·금액은 목록에 없어서 **구조적으로** 실릴 수 없다."* MaintQ 의 `tool_payload` 원문 보관도 같은 규약을 따라야 한다 | D15 가 이미 **프로세스 경계**를 갈라 뒀다(backend ↔ mcp_server). 도구 실패를 예외가 아니라 `status` 로 반환하는 규약(D9)과 *"하위 도구 실패를 삼키지 않는다"*(`04 §13`)가 **차단기 반환값의 형태를 이미 정해 준다** |

> ⚠ **P33 은 Sprint 12 에서 해소됐다(S29 확정).** ~~아래는 P34·P35 에만 해당한다. P34·P35 는
> 전부 "지금 하지 않을 것"이다~~ — **P34는 D112(2026-08-23)로 부분 재개됐다**(request-withdrawal·
> lookup-clause·assess-loan 3종만, 구 목록 S5·S7·S11~S16 중 나머지 7종은 여전히 보류).
> P35(차단기 경계)는 `services/po.py:approve()`가 실패를 삼키는 정도로만 부분 달성, 정식 패턴은
> 아직 없어 계속 열어 둔다.
>
> ⚠ **2026-08-24 추가 대기열**: FinAllQ 세션이 크로스세션 메시지로 나머지 5개 스킬(advise-hedge·
> advise-financing·request-settlement·assess-used-equipment-loan·advise-replacement-financing)의
> 요청/응답 계약과 curl 검증 결과를 선제 공유해 왔다(`docs/sessions/2026-08-24_finallq_conversion.md`
> 는 이 메시지를 포함하지 않는다 — 별도 시각의 메시지). 이번 시연 범위가 S5·S8 두 시나리오로
> 확정돼 있어 **지금은 넘어가고 시연 이후 착수**하기로 FinAllQ 쪽에 회신했다. 착수 시
> `build_request_withdrawal_payload`·`build_assess_loan_payload`와 같은 패턴
> (`backend/a2a/payloads.py`) + `routers/a2a.py` 트리거 추가로 대응 가능 — FinAllQ 쪽 스펙은
> 이미 확보돼 있다. `advise-replacement-financing`은 "InsuQ claim-insurance 이후 2차 홉 전용"
> 이라 MaintQ 쪽에 그 흐름(InsuQ claim-insurance 호출 지점) 자체가 있는지 먼저 확인할 것.

---

## 아이디어 주차장 (미분류)

- 발주 이력 기반 소모성 부품 자동 재주문 제안 (안전재고 하회 시 선제 알림) — P17과 묶으면 시너지
- 점검 체크리스트 완료 체크 → 정비 리포트 자동 생성 (S3의 `po_card` variant:`hold` 체크리스트가 입구)
- 팀장 화면 주간 요약 (반복 고장 Top3, 발주 지출 합계)
- 반려 사유 템플릿 (예산/사양 불일치/재고 있음/시기 조정) — 자유 입력이면 통계가 안 나옴
- 세션 목록·재개 UI — `traces`에 세션이 쌓이는데 사용자가 과거 대화를 다시 열 경로가 없다
- **실제 .docx/.pdf 파일 생성 (2026-08-24 A2A_Q 세션 조사)** — 사용자가 "승인 버튼 누르면
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
  🔵 **2026-08-29 갱신 — QMesh 프로젝트에서 구현 진행 중이다.** MaintQ 는 지시를 받는 쪽이므로
  **이 레포에서 먼저 착수하지 않는다**(경로 선택도 QMesh 쪽 결정을 따른다)

## 알려진 결함 — 테스트 격리·회귀 표기 (2026-08-29 발견, 미수정)

- 🔴 **`bundle_integrity ⑫` 가 FK 하나를 놓쳐 FAIL 한다** (2026-09-03 발견, 미수정).
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
  재현된다(2026-09-03 실측). 고치려면 DELETE 전에 해당 자산의 `decisions` 행도 정리하거나,
  픽스처가 판정 전에 자산을 지우도록 순서를 바꾼다.

- 🟢 **`calls` 표기가 화면마다 의미가 다르다** (2026-09-01 발견, 기능 문제 아님 — 오독 유발).
  `frontend/lib/trace.ts::toTraceSession()` 의 `calls`(:104 `let calls = 0`)는 **받은 이벤트
  묶음 안의 `tool_call` 수**다. 그런데 그 함수를 두 화면이 쓴다:
  ㉠ **정비사 콘솔**(`DiagnosticConsole.tsx`) — **한 턴**의 이벤트만 받아 그리므로
     `4 → 1 → 0` 처럼 **턴마다 리셋**되는 게 정상이다
  ㉡ **매니저 트레이스**(`manager/trace/[sessionId]`) — **세션 전체** 이벤트를 받으므로
     같은 코드가 **누적값**으로 보인다
  ⚠️ **실제로 오독을 낳았다.** 2026-08-31 촬영에서 `calls` 가 `1 → 0 → 1` 로 리셋되는 것을
  보고 "세션 상태가 매 턴 초기화된다"는 가설이 섰고, 그 가설로 다른 세션에 조사가 위임됐다.
  진짜 원인은 이력 절삭(위 항목)이었고 `calls` 는 **정상 동작**이었다. 값 자체는 맞지만
  **같은 이름이 두 뜻**이라 세션 상태 판정에 쓸 수 없다.
  고친다면: 두 화면에서 라벨을 구분하거나(`이번 턴 N회` / `누적 N회`), `toTraceSession()` 이
  범위를 인자로 받아 라벨을 만들게 한다.

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

- 🔴 **`spikes/a2a_identity_contract.py` 가 D120 이후 죽어 있다** (2026-08-29 발견).
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

- 🔴 **pytest 는 `DATABASE_URL` 없이는 매단다.** pytest 실행 경로에는 `load_dotenv` 가 없어
  (`backend/main.py` 에만 있다) `backend/db.py:21` 의 기본값 `postgresql://localhost/maintq`
  = **포트 5432** 로 떨어지는데, `docker-compose.yml` 의 컨테이너는 **5434** 다. 아무도 듣지
  않는 포트라 psycopg 가 타임아웃 없이 멈춘다 — 실패가 아니라 **무한 대기**라 원인 파악이
  오래 걸린다. ⚠ **CLAUDE.md 「회귀 스위트」 절의 pytest 실행 커맨드에 이 전제가 빠져 있다** —
  적힌 대로 복사해 돌리면 그대로 밟는다. 실제 실행은 아래처럼 해야 한다:
  `DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" uv run --with pytest ...`
  (이 정정은 CLAUDE.md 수정이 필요해 **사람 확인 대기 중**이다.)

- 🟡 **A2A 8파일군 “86건” 은 러너 출력이 아니다.** `def test_` 개수를 센 값이고 실제
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
