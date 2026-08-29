# 2026-08-24 — spikes 33스위트 전수 실행 (Postgres 전환 후 실측 기준선 증거)

**성격: 실행 증거 파일.** 본문 대부분은 `uv run python spikes/*.py` 33회의 **원본 콘솔 출력**이다.
세션 로그의 통상 목적(결과가 아니라 맥락 — `docs/sessions/README.md`)과 성격이 다르지만,
CLAUDE.md 의 "실측 기준선" 이 근거로 삼는 **SQLite→Postgres 전환 후 유일한 전수 실행 기록**이라
버리지 않는다. 요약을 앞에 두고 원본은 부록으로 내렸다.

- **실행일** 2026-08-24 (파일 mtime 10:49)
- **대상** 공식 33스위트 전건. `ls spikes/*.py` 가 반환하는 37개 중 공식 목록 밖 4개
  (`a2a_outbound_contract` · `a2a_e2e_integration_spike` · `demo_recommendation_1_and_2` ·
  `test_elice_stream`)는 실행하지 않았다 — CLAUDE.md "스코프 밖 발견" 항목과 일치
- **결과** **FAIL 0 · 합계 1,052건** · 소켓 고갈(`WinError 10014`) 재시도 0회 · `ie5_extract_contract`
  는 IE5 PDF 가 실재해 E축 3건까지 실행(SKIPPED 0)
- **정리·커밋** 2026-08-29 — 5일간 미추적으로 남아 있던 것을 다른 세션(A2A_Q)의 알림으로 발견해
  헤더를 붙이고 커밋했다

## 스위트별 실측 (이 파일에서 기계 추출)

| 스위트 | 건수 |
|---|---|
| `sp2_mcp_roundtrip` | 20 |
| `write_tool_contract` | 30 |
| `api_contract` | 41 |
| `sp3_sse_events` | 22 |
| `trace_persist` | 17 |
| `mcp_client_contract` | 15 |
| `prompt_rules` | 24 |
| `lookup_contract` | 14 |
| `citation_render` | 19 |
| `db_concurrency` | 7 |
| `rag_contract` | 13 |
| `agent_loop_contract` | 35 |
| `eval_score_contract` | 36 |
| `s4_smoke` | 10 |
| `llm_provider_contract` | 23 |
| `eval_replay_guard` | 16 |
| `law_fetch_contract` | 28 |
| `rules_db_load` | 25 |
| `disposal_api_contract` | 26 |
| `asset_tools_contract` | 49 |
| `tools_profile_contract` | 7 |
| `bundle_integrity` | 26 |
| `approvals_contract` | 26 |
| `ownership_api_contract` | 10 |
| `disposal_sign_contract` | 26 |
| `s10_smoke` | 17 |
| `ui_honesty_contract` | 291 |
| `a2a_identity_contract` | 19 |
| `repair_flow_contract` | 19 |
| `deadline_risk_contract` | 18 |
| `external_store_contract` | 47 |
| `ie5_extract_contract` | 54 |
| `a2a_partner_tools_contract` | 22 |

**합계 1,052건 · FAIL 0.**

## CLAUDE.md 기준선과의 대조 (2026-08-29 검증)

합계 1,052 는 CLAUDE.md 가 "Sprint 16 4차 체크포인트" 시점으로 적는 값과 **정확히 일치**한다.
현재 헤드라인 **1,075** 와의 차이 23건은 전부 이 실행 **이후** 반영분이다 —
`api_contract` 41→52(+11, Sprint 17 D119 재무부 승인·doc3 계약) ·
`ui_honesty_contract` 291→303(+12, Sprint 18 대시보드 신규 파일 2건×6).
즉 이 덤프는 낡은 것이 아니라 **1,075 직전 상태의 정상 스냅샷**이고 두 문서는 어긋나 있지 않다.

⚠ 세는 함정 둘 (다음에 이 파일을 기계로 집계할 사람을 위해):

- `s4_smoke` 요약줄은 `통과 (S4判定 9건 + DB 안전 게이트 1건)` 로 **갈라 인쇄**한다 —
  `통과 (N건)` 만 긁으면 9 로 세어 표(10)와 어긋나 보인다. 실제 PASS 줄은 10개다.
- `ui_honesty_contract` 는 `통과 (N건)` 자체가 없다 — `신규 계약 검사 268건` + `제약 게이트 10 ·
  뮤턴트 8 · 메타 5 = 23` 두 줄로 나뉘어 합이 291 이다.

---

## 부록 — 원본 실행 출력 (33스위트, 무편집)

PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/sp2_mcp_roundtrip.py
SP2 — MCP 서버 ↔ 클라이언트 왕복 (stdio, 프로세스 분리)

[격리] 실 DB(before) mtime_ns=1787533322088414500 size=319488
[격리] MAINTQ_DB = C:\Users\ttogl\AppData\Local\Temp\tmpikq8w01u\sp2.db

[격리] mcp_server.db.DB_PATH = None
읽기 연결 오류: cannot execute UPDATE in a read-only transaction
쓰기 연결 오류: MCP 도구는 po_drafts 를 수정/삭제할 수 없습니다 (D10, op=UPDATE)
CONTEXT:  PL/pgSQL function mcp_block_write() line 4 at RAISE
[격리] 실 DB(after)  mtime_ns=1787533322088414500 size=319488

──────────────────────────────────────────────────────────────────────────────────────
  PASS  ① 서버 initialize                           stdio 핸드셰이크 성공
  PASS  ② 도구 등록                                   7종: create_po_draft, find_alternative_parts, get_error_history, get_supplier_quotes, lookup_error_code, rag_search_manual, search_inventory
  PASS  ③ description 존재 (오케스트레이션의 절반)            전부 있음
  PASS  ④ search_inventory (S1 재고 미달)             status=ok, qty=1, safety=3
  PASS  ⑤ D28 model 필터                            필터 없음 4건 → S100 지정 2건
  PASS  ⑤-b part_name 공백 무관 매칭                    '냉각 팬' → ok ['FAN-IG5-01', 'FAN-GEN-40', 'FAN-IG5-02']
  PASS  ⑤-c part_name 공백 무관 매칭 (전원모듈)             '전원 모듈' → ok ['PWR-S100-MOD']
  PASS  ⑤-d line_id 라인 이름 → status:error (예외 아님)  status=error, reason=invalid_line_id
  PASS  ⑤-e line_id 숫자 문자열은 정상 조회                 status=ok, count=4
  PASS  ⑥ S2 분기 근거 (qty 0 + 단종)                   qty=0, discontinued=True
  PASS  ⑦ 대체품 조회                                  status=ok, 1건
  PASS  ⑧ D9 status:empty (예외 아님)                 status=empty
  PASS  ⑨ 견적 트레이드오프 + MOQ                         A사 3일/₩38,000, B사 14일/MOQ 10
  PASS  ⑩ S3 repeated 판정 (D25 대소문자 무관)            count=3, repeated=True (입력 'OCt' → 저장 'OCT')
  PASS  ⑪ not_found 반환                            status=not_found
  PASS  ⑫ 인자 누락 → status:error                    status=error, msg=part_no 또는 part_name 중 하나는 필요합니다
  PASS  ⑬ model enum 강제 (iS7 거부)                  status=error, msg=model은 iG5A | S100 | IE5 이어야 합니다: 'i
  PASS  ⑭ 읽기 커넥션 쓰기 차단                            DatabaseError
  PASS  ⑮ 도구의 po_drafts UPDATE 차단 (D10)           MCP 도구는 po_drafts 를 수정/삭제할 수 없습니다 (D10, op=U
  PASS  ⑳ 격리 · 실 data/maintq.db mtime·size 불변     변경=False
──────────────────────────────────────────────────────────────────────────────────────

SP2 통과 (20건) — 도구 등록·호출·status 왕복 확인
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/write_tool_contract.py
쓰기 도구 3종 계약 검증 — create_po_draft · generate_disposal_document · create_repair_record (임시 DB 사본)

[스키마] decisions.reason 이 이미 스키마에 있음 (MQ-707 착지 완료)

쓰기 연결 오류: MCP 도구는 decisions 를 수정/삭제할 수 없습니다 (D10, op=UPDATE)
CONTEXT:  PL/pgSQL function mcp_block_write() line 4 at RAISE
쓰기 연결 오류: MCP 도구는 decisions 를 수정/삭제할 수 없습니다 (D10, op=DELETE)
CONTEXT:  PL/pgSQL function mcp_block_write() line 4 at RAISE
쓰기 연결 오류: MCP 도구는 repair_records 를 수정/삭제할 수 없습니다 (D10, op=UPDATE)
CONTEXT:  PL/pgSQL function mcp_block_write() line 4 at RAISE
쓰기 연결 오류: MCP 도구는 repair_records 를 수정/삭제할 수 없습니다 (D10, op=DELETE)
CONTEXT:  PL/pgSQL function mcp_block_write() line 4 at RAISE
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① 신원·단가·state 가 스키마에 없음 (D23·D31·D37)                                                      노출 파라미터: ['error_code', 'evidence', 'model', 'part_no', 'qty', 'reason', 'supplier_id', 'urgency']
  PASS  ② 정상 발주 → draft 생성                                                                         po_id=PO-0118, state=draft
  PASS  ③ D31 단가 스냅샷 (입력 아님)                                                                       unit_price=38000, total=76000
  PASS  ④ D31 MOQ 미달 거부 (자동 상향 안 함)                                                                reason=moq_not_met, moq=10
  PASS  ⑤ D33 미지 코드 거부 (환각이 발주까지 못 감)                                                              reason=unknown_error_code
  PASS  ⑥ D33 model/code 짝 강제                                                                      reason=model_code_pair
  PASS  ⑦ D5 reason 필수                                                                             reason=reason_required
  PASS  ⑧ 견적 없는 공급사 → not_found                                                                    status=not_found, reason=no_quote
  PASS  ⑮ D81 스키마에 override·override_reason·reviewed_by 키 없음 (+D23 신원·상태 없음)                       노출 파라미터=['asset_id', 'disposal_date', 'disposal_mode', 'equipment_id', 'reason'] · required=['reason']
  PASS  ⑯ reason 공백 → reason_required · 행 수 불변                                                     reason=reason_required · decisions=0→0
  PASS  ⑰ 처분 초안 생성 → state=draft · override=false · 미검수 고지 · 문서 2종                                 decision_id=DEC-0001 verdict_at_signing=CONDITIONAL · 문서=['approval', 'representation_warranty']
  PASS  ⑱ D63 BLOCKED 자산도 draft 생성 (막지 않고 기록한다) · override 는 여전히 false                             verdict_at_signing=BLOCKED decision_id=DEC-0002
  PASS  ⑲ law_text_unavailable 전파 → draft 미생성 (decisions 행 수 불변)                                   reason=law_text_unavailable · missing=['KR-VAT-32'] · decisions=2→2
  PASS  ㉔ D98 서명·신원·state 가 create_repair_record 스키마에 없음                                           노출 파라미터: ['cost', 'downtime_hours', 'equipment_id', 'error_code', 'model', 'note', 'parts', 'repair_scope', 'work_type']
  PASS  ㉕ 정상 수리 증빙 → draft 생성                                                                      repair_id=RPR-2413, state=draft
  PASS  ㉖ ⓒ 미존재 부품 → not_found/unknown_part · repair_records 행 수 불변                                status=not_found reason=unknown_part · repair_records=13→13
  PASS  ⑨ D10 state 는 draft 고정                                                                     state=draft
  PASS  ⑩ D23 신원은 도구가 못 채움 (INSERT 시 NULL)                                                         requested_by=None, session_id=None
  PASS  ⑪ D34 evidence 저장                                                                          keys=['basis', 'notes', 'symptoms']
  PASS  ⑫ D25 코드는 대문자 canonical 저장 ('OHt'→'OHT')                                                   model=iG5A, error_code=OHT
  PASS  ⑬ D37 백엔드 stamp (1회만, 덮어쓰기 불가)                                                             1차=True, 2차=False, requested_by=tech-01
  PASS  ⑭ D36 표시명은 서버 매핑                                                                           tech-01 → 김OO
  PASS  ⑳ D10·D81 저장 계약 — state='draft' · override=0 · override_reason/reviewed_by/signed_at NULL  DEC-0001: state=draft override=False verdict_at_signing=CONDITIONAL reason=노후 리프터 매각 — 대체…
  PASS  ㉑ D84 저장된 evidence_bundle 재파싱 → bundle_hash 일치 · 정준 직렬화 바이트 동일                             재산출=sha256:4ba30331afa9663c4… 저장=sha256:4ba30331afa9663c4… · 재직렬화 동일=True
  PASS  ㉒ D10 decisions UPDATE 시도 → TEMP TRIGGER ABORT · 행 그대로                                     MCP 도구는 decisions 를 수정/삭제할 수 없습니다 (D10, op=UPDATE)
CONTEXT:  PL/pgSQL function mcp_block_write() line 4 at RAISE · 행 상태=draft
  PASS  ㉓ D10 decisions DELETE 시도 → TEMP TRIGGER ABORT · 행 그대로                                     MCP 도구는 decisions 를 수정/삭제할 수 없습니다 (D10, op=DELETE)
CONTEXT:  PL/pgSQL function mcp_block_write() line 4 at RAISE · 행 상태=draft
  PASS  ㉗ D10·D98 저장 계약 — state='draft' · 서명·신원 필드 전부 NULL                                         RPR-2413: state=draft equipment_id=INV-L3-01
  PASS  ㉘ ⓓ expenditure_class — 도구 응답값이 repair_records 저장값과 일치                                     응답=HOLD · DB=HOLD
  PASS  ㉙ ⓐ D10 repair_records UPDATE 시도 → TEMP TRIGGER ABORT · 행 그대로                              MCP 도구는 repair_records 를 수정/삭제할 수 없습니다 (D10, op=UPDATE)
CONTEXT:  PL/pgSQL function mcp_block_write() line 4 at RAISE · 행 상태=draft
  PASS  ㉚ ⓐ D10 repair_records DELETE 시도 → TEMP TRIGGER ABORT · 행 그대로                              MCP 도구는 repair_records 를 수정/삭제할 수 없습니다 (D10, op=DELETE)
CONTEXT:  PL/pgSQL function mcp_block_write() line 4 at RAISE · 행 상태=draft
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (30건) — 쓰기 도구 3종이 D10·D23·D31·D33·D34·D37·D63·D80·D81·D84·D98 경계를 지킨다
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/api_contract.py
REST API 계약 검증 — 상태 전이 = 권한 (임시 DB 사본)

────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① 승인 큐 조회 (긴급 우선 정렬) + 항목 키집합 불변 (D85)                                    3건, 첫 항목 PO-0117(urgent), 키차이=없음
  PASS  ② 상세 — evidence·재고·견적·trace 링크 + 키집합 불변 (D85)                             quotes=2, 재고=1, trace=/api/chat/S1/trace, 키차이=없음
  PASS  ②-b D57 — model 확정(iG5A, 2026-07-28 승인 후) → print_page 실측 202(offset 0)   model=iG5A, basis=[{'tool': 'lookup_error_code', 'code': 'OHT', 'manual_page': 202, 'print_page': 202}, {'tool': 'search_inventory', 'part_no': 'FAN-IG5-01', 'qty': 1, 'safety_stock': 3}]
  PASS  ③ D36 표시명은 서버가 매핑                                                         tech-01 → 김OO
  PASS  ④ 정비사 approve → 403 (평가 지표)                                               403 발주 승인 은(는) manager 만 수행할 수 있습니다 (요청자 역할:
  PASS  ⑤ 정비사 reject → 403                                                        403
  PASS  ⑥ 팀장 submit → 403 (역할 분리는 양방향)                                            403
  PASS  ⑦ pending 을 다시 submit → 409 (403 과 구분)                                    409 PO-0117 는 지금 'pending' 상태라 'pending' 로 전이할 수 없
  PASS  ⑧ 팀장 approve → approved + decided_by stamp                                state=approved, decided_by=mgr-01
  PASS  ⑨ 이미 승인된 건 재승인 → 409                                                      409
  PASS  ⑩ D38 사유 없는 반려 → 422                                                      422
  PASS  ⑪ 반려 → rejected + 사유 저장                                                   state=rejected, note='예산 초과'
  PASS  ⑫ 없는 발주 → 404                                                             404
  PASS  ⑬ 장비 목록                                                                   10대
  PASS  ⑭ 이력 조회 (30일 OCT 3건)                                                      OCT 3건
  PASS  ⑮ D29 이력 기록 (정비사) + D25 대문자 저장                                            201, code=OCT
  PASS  ⑯ 기록이 반복 감지 모수에 반영                                                        3 → 4건
  PASS  ⑰ 팀장은 이력 기록 불가 → 403                                                      403
  PASS  ⑱ 없는 설비에 기록 → 404                                                         404
  PASS  ⑲ ASCII 사용자 ID 는 통과                                                       200
  PASS  ⑳ trace_url 을 그대로 GET → 200 + D43 스키마                                     200 /api/chat/S1/trace keys=['count', 'events', 'session_id']
  PASS  ㉑ 없는 세션 → 404 가 아니라 200 + count 0 (D43)                                   200, count=0
  PASS  ㉒ 무작위 순서 INSERT → seq 오름차순 · data 는 dict · ts 는 ...Z (D39)                seq=[1, 2, 3, 4, 5], ts=2026-07-23T04:05:06Z
  PASS  ㉓ 역할 제한 없음 — technician 헤더로도 200 (D43)                                    200, count=5
  PASS  ㉔ GET /api/whoami — department 는 user_id 별로 DB 값 그대로 (D108)               mgr-01='maintenance' mgr-02='finance' tech-01='maintenance'
  PASS  ㉕ X-Dept 헤더 스푸핑 무시 — mgr-01(maintenance)에 X-Dept:finance 를 실어도 무시 (D108)  department='maintenance' (기대: 'maintenance', 헤더값 'finance' 는 무시돼야 함)
  PASS  ㉖ 미등록 user_id → department:None, 400 아님 (D108)                            {'role': 'manager', 'user_id': 'ghost-99', 'department': None}
  PASS  ㉗ 부품 견적 사전 조회 (발주 화면이 공급사를 고르기 전)                                         200, 3건
  PASS  ㉘ 정비사 화면 직접 생성 → 200 + draft + requested_by 즉시 stamp                      200, state=draft, requested_by=tech-01, 키차이=없음
  PASS  ㉙ 팀장이 화면 생성 호출 → 403                                                      403
  PASS  ㉚ 없는 공급사 → 404(no_quote)                                                  404
  PASS  ㉛ MOQ 미달 → 422(moq_not_met)                                               422, reason=moq_not_met
  PASS  ㉜ draft 수정 → 200 + qty·reason 반영                                          200, qty=2, reason='수량 정정'
  PASS  ㉝ 팀장이 PATCH 호출 → 403                                                      403
  PASS  ㉞ 제출(submit) 성공 — 이후 PATCH 는 409 여야 한다                                    200
  PASS  ㉟ pending 상태를 PATCH → 409(draft 아님)                                       409
  PASS  ㊱ 없는 발주 PATCH → 404                                                       404
  PASS  ㉗ D57 print_page — iG5A(offset 0): 202 → 202                              {'tool': 'lookup_error_code', 'manual_page': 202, 'print_page': 202}
  PASS  ㉘ D57 print_page — S100(offset 16): 202 → 186 (★ 음성: 202 면 오프셋 미적용)       {'tool': 'lookup_error_code', 'manual_page': 202, 'print_page': 186}
  PASS  ㉙ D57 print_page — model 없음 → 필드 없음                                       {'tool': 'lookup_error_code', 'manual_page': 202}
  PASS  ㉚ D57 print_page — manual_page 없는 basis 항목은 무영향                           {'tool': 'search_inventory', 'part_no': 'FAN-IG5-01'}
────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (41건) — 권한 403·전이 409·D29 기록·GET /trace(D43)·department 는 헤더 스푸핑 불가·DB 조회만(D108) 확인
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/sp3_sse_events.py
SP3 — FastAPI SSE 이벤트 4종 + block 중간 삽입 (실제 uvicorn 프로세스)

────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① 200 + text/event-stream                           200 text/event-stream; charset=utf-8
  PASS  ② 이벤트 수신                                            20개 프레임
  PASS  ③ 4종 전부 구분 수신 (D14·D22)                             {'tool_call': 4, 'tool_result': 4, 'token': 9, 'block': 3}
  PASS  ④ 4종 외 이벤트 없음 (고정 규격)                               수신 종류: ['block', 'token', 'tool_call', 'tool_result']
  PASS  ⑤ A1 tool_call 이 tool_result 보다 먼저                  모든 쌍에서 성립
  PASS  ⑥ block 이 token 중간에 삽입 (D22 핵심)                     token 4~14 사이에 block [10, 11]
  PASS  ⑦ 안전 경고가 위험 절차 서술보다 먼저                              safety=11, 위험 서술 시작=12
  PASS  ⑦-b 안전 문구 인용이 승인된 매뉴얼 페이지 (절대규칙 3)                  citation={'page': 4, 'print_page': 4, 'label': 'iG5A 매뉴얼 p.4'} (기대 page=4)
  PASS  ⑧ 점진 전송 (버퍼링 아님)                                    프레임 분산 0.84s, 간격>5ms 17/19
  PASS  ⑨ block 타입 (safety·citation·po_card)                ['citation', 'po_card', 'safety']
  PASS  ⑩ D35 po_card variant                               variant='draft'
  PASS  ⑪ D32 citation payload                              {'page': 202, 'print_page': 202, 'label': 'iG5A 매뉴얼 p.202'}
  PASS  ⑫ A1 강화 — 도구 실행 전에 tool_call 이 이미 나갔다 (몰아쓰기 아님)     4쌍, 최소 간격 0.086s ≥ 0.030s
  PASS  ⑬ A5 replay 가 traces 에 저장 (payload == SSE data)     traces 11행 ['block', 'tool_call', 'tool_result'] · SSE 비-token 11건
  PASS  ㉑ D55 재생 표식 — 저장된 재생 이벤트 전부 replay:true             11행 중 표식 누락 0건 []
  PASS  ⑭ 같은 session_id 두 번째 호출 → seq 이어짐                   1턴 11행 → 2턴 누적 22행, seq 1~22
  PASS  ⑮ D36 — X-User 에 한글 → 400 (DB 로 새지 않는다)             400 X-User 는 ASCII 사용자 ID 여야 합니다 (D36)
  PASS  ⑯ D36 위반 요청은 traces 에 한 행도 남기지 않는다                  count=0
  PASS  ⑰ 조기 종료 직후 재요청도 200 + 정상 이벤트                        끊기 전 2청크 수신 → 재요청 20프레임
  PASS  ⑲ MCP ready=False → 도구 없이 진단하지 않는다 (09_RUNTIME §3)  200 · 첫 토큰 '도구 서버에 연결할 수 없습니다. 재시도하거나 관리자에게 문의하세요.'
  PASS  ⑳ 그 턴은 도구 이벤트를 한 건도 남기지 않는다                         traces=0행, tool_call 프레임 0건
  PASS  ⑱ 서버 로그에 cancel scope 예외 없음 (조기 종료 후)               깨끗함
────────────────────────────────────────────────────────────────────────────────────────────────

SP3 통과 (22건) — 이벤트 4종 · block 중간 삽입 · A5 저장 · D36/D42 회귀
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/trace_persist.py
trace 영속화 계약 검증 — A5·D41 (임시 DB 전용)

DB 연결 오류: duplicate key value violates unique constraint "traces_session_id_seq_key"
DETAIL:  Key (session_id, seq)=(S-TRACE, 5) already exists.
traces seq 충돌 (session=S-TRACE seq=5 event=block 시도=1): duplicate key value violates unique constraint "traces_session_id_seq_key"
DETAIL:  Key (session_id, seq)=(S-TRACE, 5) already exists.
DB 연결 오류: connection timeout expired
traces INSERT 실패 (session=S-BROKEN event=tool_call): connection timeout expired
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① tool_call 발행 = traces INSERT (A5)                                         이벤트=tool_call, 저장=1행 (1, 'tool_call', 'lookup_error_code')
  PASS  ② payload == SSE data (바이트 동일, D30)                                         payload={"tool": "lookup_error_code", "input": {"model": "iG...
  PASS  ③ seq 는 MAX(seq)+1 로 이어쓴다 (턴이 바뀌어도)                                         seq=[1, 2, 3, 4]
  PASS  ④ TraceWriter 에 token 메서드 없음 + emit(token) 거부 (D41)                         hasattr(token)=False, emit(token) 거부=True
  PASS  ⑤ traces 에 token 직접 INSERT → CHECK 거부                                       new row for relation "traces" violates check constraint "traces_event_
  PASS  ⑥ 같은 (session_id, seq) 중복 INSERT → 거부 (D41)                                 duplicate key value violates unique constraint "traces_session_id_seq_
  PASS  ⑦ seq 충돌 → 1회 재시도로 이어씀 (persist_errors 0)                                   seq=[1, 2, 3, 4, 5, 6], persist_errors=0
  PASS  ⑧ DB 쓰기 실패 → 이벤트는 정상, persist_errors 증가                                     event=tool_call, persist_errors=1
  PASS  ⑨ read_trace = D43 스키마 {session_id,count,events[{seq,event,tool,data,ts}]}  count=6, event keys=['data', 'event', 'seq', 'tool', 'ts']
  PASS  ⑩ 저장된 data 가 SSE data 와 같은 객체로 복원 (D30)                                     data={'tool': 'lookup_error_code', 'input': {'model': 'iG5A', 'code':
  PASS  ⑪ 없는 세션 → count 0 (404 아님, D43)                                             {'session_id': 'NO-SUCH-SESSION', 'count': 0, 'events': []}
  PASS  ⑫-b D76-2 tool_payload 에 도구 원본 JSON 저장 · tool_call 행은 NULL                  tool_call=None, tool_result={"manual_page": 202, "related_parts": ["FA
  PASS  ⑫-c D30 유지 — tool_payload 가 payload/SSE data 로 새지 않는다 (바이트 동일)              payload={"tool": "lookup_error_code", "status": "ok", "summary": "과열",
  PASS  ⑫-d read_trace(D43) 에는 tool_payload 가 실리지 않는다                               keys=['data', 'event', 'seq', 'tool', 'ts']
  PASS  ⑫ ts 는 UTC 'Z' 표기 · block 의 tool 은 NULL (D39)                               event ts=2026-08-24T01:33:27.967Z, row ts=2026-08-24T01:33:28Z, tool=N
  PASS  ⑬ data/maintq.db 불변 (mtime)                                                 1787533322088414500 == 1787533322088414500
  PASS  ⑭ po.py 에 하드코딩 USER_NAMES 없음 · users 조회 (D41)                               USER_NAMES=False, users 조회=True
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (17건) — 발행=저장이 한 몸, seq 충돌은 재시도, 실패해도 스트림은 산다
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/mcp_client_contract.py
MQ-302 — MCP 클라이언트(lifespan 워커) 계약 (D42·D46·D9·D15)

[격리] 실 DB(before, 공유 Postgres) po_drafts=5행
[격리] DATABASE_URL = postgresql://postgres:postgres@127.0.0.1:5434/maintq?options=-c%20search_path%3Dmcp_client_1787535216_nzbtgx%2Cpublic

MCP 도구 타임아웃: search_inventory (0.0s)
MCP 워커 종료 — ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
MCP 클라이언트 기동 실패 — ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)

[격리] 실 DB(after, 공유 Postgres) po_drafts=5행

───────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① start() → 세션 준비 (lifespan 소유)                    ready=True
  PASS  ② 도구 목록 (부분집합 비교)                                  7종 · 누락 없음
  PASS  ③ call() 정상 왕복                                     status=ok, qty=1
  PASS  ④ D9 인자 누락 → 예외 아닌 status:error                    status=error, msg=part_no 또는 part_name 중 하나는 필요합니다
  PASS  ⑤ D46 타임아웃 → status:error + reason:timeout         status=error, reason=timeout
  PASS  ⑥ 타임아웃 후에도 세션 생존                                   status=ok, 공급사 2곳
  PASS  ⑦ 동시 호출 5건 직렬 소비                                   ok 5/5
  PASS  ⑧ 취소 안전성 (취소 직후 재호출 · cancel scope 예외 없음)          재호출 status=ok, cancel scope 예외 0건
  PASS  ⑨-a create_po_draft 왕복 (쓰기 도구)                     status=ok, po_id=PO-0118
  PASS  ⑩ summarize_result 한 줄 요약                          search_inventory: FAN-IG5-01 재고 1/안전 3 · 안전재고 미달 / get_supplier_quotes: 공급사 2곳 · 최단 3일 · 최저 ₩29,000 / create_po_draft: P
  PASS  ⑪ stop() 후 호출 → status:error + reason:unavailable  status=error, reason=unavailable
  PASS  ⑫ 기동 실패해도 예외 없이 status:error (앱은 산다)               start=False, reason=unavailable
  PASS  ⑨-b env 격리 · 임시 DB 에만 행 증가                         임시 DB 5 → 6
  PASS  ⑨-c 실 DB(공유 Postgres) row count 불변                 rows 5→5
  PASS  ⑬ D15 프로세스 분리 (mcp_server 를 import 하지 않음)          sys.modules 에 없음
───────────────────────────────────────────────────────────────────────────────────────────────

통과 (15건) — 워커 소유·shield 취소 안전·env 격리 확인
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/prompt_rules.py
MQ-303 — 시스템 프롬프트·안전 상수 정적 검사 (LLM 호출 없음)

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① 규칙 11개 + 결정 태그 전건 존재                                                  RULES=11, 누락 태그=없음
  PASS  ② 기준값 '10분 이상' 포함 · '5분' 미포함                                            10분이상=True, 5분부재=True
  PASS  ③ pages = 물리 페이지 (iG5A 4 / S100 2)                                      {'iG5A': 4, 'S100': 2}
  PASS  ④ SAFETY_BASELINE 에 print_page 키 없음                                     중첩 포함 재귀 검사
  PASS  ⑤ build_system_prompt('iS7') → ValueError, enum 3종은 통과                  ValueError=True, MODELS=('iG5A', 'S100', 'IE5')
  PASS  ⑥ 미지 코드 추측 금지 + not_found/catalog_not_loaded 구분                         추측 금지 · 미적재는 별도 안내
  PASS  ⑦ A2 '다음 턴' 발주 규칙                                                       견적 제시 턴 자동 호출 금지
  PASS  ⑧ MOQ 미달 시 임의 상향 금지                                                     도구 거부 후 사용자 재확인
  PASS  ⑨ 신원(requested_by)·단가(unit_price) 지어내기 금지                               서버 주입 — LLM 위조 경로 차단
  PASS  ⑩ 타임아웃/실패는 '확인하지 못했다'로 명시                                               09_RUNTIME §3 원칙
  PASS  ⑪ 안전 문구 창작 금지 · 페이지 인용은 시스템이 생성                                         safety-guardrail 규칙 1 · D32
  PASS  ⑫ D1 경계: 정의는 lookup, 절차는 rag_search_manual                              경계를 흐리는 문구 없음
  PASS  ⑬ S2 compat_confirmed 분기 · S3 hold 보류 블록                                보류는 po_card variant
  PASS  ⑭ SAFETY_SOURCES 에 매뉴얼 원문·페이지 기록 (IE5 는 근거 미확보로 의도적 제외 — D109)          SAFETY_SOURCES 모델=['S100', 'iG5A'], MODELS=['iG5A', 'S100', 'IE5'], MODELS-SAFETY_SOURCES 차집합=['IE5'], 4건, 기준값 원문 보유=['S100', 'iG5A'], 필수 보유 대상=['S100', 'iG5A'], 누락=없음
  PASS  ⑮ needs_safety_block — 위험 키워드 감지 (내부 작업 확장 + 띄어쓰기 정규화)                  키워드 19종
  PASS  ⑯ model=None → '미확정' + 확인 질문 지시                                         폴백으로 한쪽 기종을 고르지 않음
  PASS  ⑰ env 미설정 상태에서 RULES 11개 · EXT_RULES 8개 고정 (D69·D102·D112)              RULES=11 EXT_RULES=8 CORE=7 EXT=13 · env 미설정
  PASS  ⑱ tool_names=코어7 → EXT 규칙·확장 도구명 부재 (없는 도구 사용법 지시 금지)                   규칙 누출=없음 · 도구명 누출=없음
  PASS  ⑲ tool_names=전체20 → EXT 규칙 8개 + D 태그 전건 · 규칙 번호 12~19                   규칙 누락=없음 · 태그 누락=없음 · 번호=True
  PASS  ⑳ MAINTQ_TOOLS_PROFILE=full 로 재임포트해도 프롬프트 불변 (env 를 읽지 않는다)             소스에 env 참조 없음=True · 출력 동일=True · 누출=없음
  PASS  ㉑ 확장 도구 일부만 등록 → 해당 규칙만 · 번호 밀림 없음                                      규칙 존재={12: False, 13: True, 14: True, 15: False, 16: False, 17: False, 18: False, 19: False} · 헤더 13개=True
  PASS  ㉒ tool_names=코어7 → generate_disposal_document·규칙 15 문구 0건 누출 (D69 게이트)  누출=없음 · 코어 규칙 헤더 11개=True
  PASS  ㉓ 규칙 15 — 초안 한정 · override 는 권한 아님 · 사유 대필 금지 · 미생성 사실 명시 (D81·D63)     규칙 15 누락 문구=없음
  PASS  ㉔ prompts.EXT_TOOLS == server.py full 블록 실등록 도구명 (자기참조 위장통과 방지)         prompts.EXT_TOOLS=13 · server 실등록=13 · prompts 누락(서버엔 있는데 프롬프트에 없음)=없음 · server 누락(프롬프트엔 있는데 서버에 없음)=없음
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (24건) — 규칙 11개 · '10분 이상' 기준값 · 물리 페이지 유지 확인
PS C:\Users\ttogl\workspace\MaintQ>
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/lookup_contract.py
lookup_error_code 계약 검증 — 임시 DB + 합성 픽스처 3행 (실 DB 는 ⑭ 한 곳만 읽기 전용으로 구조만 본다)

읽기 연결 오류: connection timeout expired
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① model enum 강제 (iS7 거부)                                                              status=error, msg=model은 iG5A|S100|IE5 이어야 합니다: 'iS7
  PASS  ② 정상 조회 + D20 related_parts                                                           name=인버터 과열, related=['FAN-IG5-01']
  PASS  ③ D25 case-insensitive + canonical/display 분리                                         'oht'·' OHT '·'OhT' → code=OHT / display_code=OHt (입력 반향 아님)
  PASS  ④ D13 복합키 (같은 코드 다른 의미)                                                               iG5A=인버터 과열 / S100=방열판 과열(S100 정의)
  PASS  ⑤ D26 manual_page 무가공 (환산 금지)                                                         iG5A p.202, S100 p.30 (픽스처 값 그대로)
  PASS  ⑥ D50 0행 → error/catalog_not_loaded                                                   status=error, reason=catalog_not_loaded
  PASS  ⑦ D9 DB 없음 → 예외 아닌 status:error                                                       status=error, reason=db_error
  PASS  ⑧ code 누락 → status:error                                                              status=error, reason=code_required
  PASS  ⑨ 적재 후 미지 코드 → not_found (유사 코드 추측 없음)                                                status=not_found, 추측 노출=없음
  PASS  ⑩ ok 응답 키가 계약과 동일                                                                     초과=없음, 누락=없음
  PASS  ⑪ 결정론 (같은 질의 2회 동일)                                                                   동일 dict
  PASS  ⑬ D100 actions_source 키가 픽스처 전 3행 응답에 존재 · 값은 null (합성 DB)                            키 존재=[True, True, True] · 값=[None, None, None]
  PASS  ⑭ D100 실 DB — actions_source(actions_manual_id) 실측 대조 (정본 병합 MQ-919 완료 — 승인 3건만 채워짐)  [양성] 채워짐=[('S100', 'FANW'), ('iG5A', 'ETB'), ('iG5A', 'RERR')](기대 [('S100', 'FANW'), ('iG5A', 'ETB'), ('iG5A', 'RERR')]) · [음성] null=67건(기대 67) · rows=70(기대 70)
  PASS  ⑫ 실 DB(공유 Postgres) error_codes 행수 불변 — ⑭ 는 SELECT 만                                  불변
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (14건) — D13·D20·D25·D26·D50 준수. iG5A 매핑 승인 완료(2026-07-28) — 실데이터는 계속 합성 픽스처로 격리 검증(승인 결과가 회귀 기준값이 되는 걸 막기 위해, MQ-310 원칙과 동일)
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/citation_render.py
MQ-312 — manifest 로더 + 인쇄 페이지 환산 (D19·D26·D32·D49)

─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① iG5A p.202 → 'iG5A 매뉴얼 p.202'                                          'iG5A 매뉴얼 p.202' page=202 print_page=202
  PASS  ② S100 p.416 → 'S100 매뉴얼 p.400 (PDF p.416)'                              'S100 매뉴얼 p.400 (PDF p.416)' page=416 print_page=400
  PASS  ③ S100 p.2 → 음수 없음, print_page==2 (D49)                                  'S100 매뉴얼 p.2' print_page=2
  PASS  ④ payload page 는 항상 PDF 물리 원본 (D26)                                      {'iG5A p.4': 4, 'iG5A p.202': 202, 'S100 p.2': 2, 'S100 p.16': 16, 'S100 p.17': 17, 'S100 p.416': 416, 'IE5 p.125': 125}
  PASS  ⑤ model='iS7' → ValueError (D6·D13)                                      ValueError 4/4
  PASS  ⑥ 기존 citation_block 직접 호출 유지 (하위 호환)                                     signature=['manual', 'page', 'print_page', 'section']
  PASS  ⑦ payload 키 = {page, print_page, label} (D32)                            ['label', 'page', 'print_page']
  PASS  ⑧ D49 경계: S100 p.16→16(미적용) / p.17→1                                     p.16→16, p.17→1
  PASS  ⑨ 오프셋 원천은 manifest.json — primary+supplement 전건 (D19)                    대조 7건(model 3 + id 4) supplement 1/1=['ig5a-troubleshooting'] / 파일={'ig5a-manual': 0, 'ig5a-troubleshooting': 1, 's100-manual': 16, 'ie5-standard': 0} / 코드={'ig5a-manual': 0, 'ig5a-troubleshooting': 1, 's100-manual': 16, 'ie5-standard': 0} / model축={'iG5A': 0, 'S100': 16, 'IE5': 0} / 불일치=[]
  PASS  ⑩ section 은 라벨에만 반영                                                      'S100 매뉴얼 p.400 (PDF p.416) · 8.2 보호 기능'
  PASS  ⑪ manifest 부재/모델 미등록 → offset 0 폴백 + warning                             부재=True/warn=True, 미등록=True
  PASS  ⑫ load_manifest 1회 캐시                                                    동일 객체, manuals=4건
  PASS  ⑬ page < 1 은 ValueError                                                  0·-3 모두 거부
  PASS  ⑭ ig5a-troubleshooting offset=1 · 물리 20/22/24/28 → 19/21/23/27 (PDF 실측)  entry=있음 offset=1 환산={20: 19, 22: 21, 24: 23, 28: 27}
  PASS  ⑮ model 키(primary 우선)와 manual_id 키의 분리 유지                                {"print_page_offset('iG5A')": 0, "manual_offset('ig5a-manual')": 0, "manual_offset('ig5a-troubleshooting')": 1, "print_page_offset('S100')": 16, "manual_offset('s100-manual')": 16}
  PASS  ⑯ D49 경계 (manual_id 경로): tsg p.1→1 / s100 p.16→16 · p.17→1               {'ig5a-troubleshooting p.1': 1, 's100-manual p.16': 16, 's100-manual p.17': 1}
  PASS  ⑯-b IE5 p.1/20/125/126 → 동일(offset=0, D109)                              offset=0 환산={1: 1, 20: 20, 125: 125, 126: 126}
  PASS  ⑰ 미등록 manual_id → offset 0 폴백 + 경고 1회 (예외 없음)                            offset=0 page 202→202 경고=1건
  PASS  ⑱ manual_id 경로 입력 검증 (page<1·bool·빈 id)                                  ValueError 4/4
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

MQ-312 통과 (19건) — 오프셋 산술은 to_print_page 1함수(SSE·REST 공유, D57), page 는 물리 원본
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/db_concurrency.py
동시성 검증 (MQ-313) — WAL+busy_timeout(SQLite) / MVCC(Postgres)

쓰기 연결 오류: MCP 도구는 po_drafts 를 수정/삭제할 수 없습니다 (D10, op=UPDATE)
CONTEXT:  PL/pgSQL function mcp_block_write() line 4 at RAISE
쓰기 연결 오류: MCP 도구는 po_drafts 를 수정/삭제할 수 없습니다 (D10, op=DELETE)
CONTEXT:  PL/pgSQL function mcp_block_write() line 4 at RAISE
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ①②③⑤⑥⑧⑨ WAL/busy_timeout — 대상 없음 (Postgres 는 MVCC, 파일 잠금 개념이 없다)        backend/db.py·mcp_server/db.py 의 Postgres 버전에 journal_mode/_enable_wal 코드 자체가 없다
  PASS  ④' MVCC — traces 쓰기 트랜잭션이 열린 동안 po_drafts INSERT 가 대기 없이 성공             대기 0.03s (다른 트랜잭션 보유 0.6s)
  PASS  ⑦ D10 회귀: read_only() 는 쓰기 거부 (물리적 강제 — default_transaction_read_only)  INSERT/UPDATE 거부=[True, True]
  PASS  ⑩ draft_writer UPDATE 차단 트리거 유지 (D10 · 트리거 문구까지 대조)                     MCP 도구는 po_drafts 를 수정/삭제할 수 없습니다 (D10, op=UPDATE)
CONTEXT:  PL/pgSQL function mcp_block_write() line 4 at RAISE / state pending→pending
  PASS  ⑪ draft_writer DELETE 차단 트리거 유지 (D10)                                   MCP 도구는 po_drafts 를 수정/삭제할 수 없습니다 (D10, op=DELETE)
CONTEXT:  PL/pgSQL function mcp_block_write() line 4 at RAISE / 잔존=1
  PASS  ⑫ D15: backend/db.py ↔ mcp_server/db.py 코드 비공유                          backend=['__future__', 'collections.abc', 'contextlib', 'data.dbcompat', 'logging', 'os', 'pathlib', 'psycopg', 'sqlite3'] / mcp=['__future__', 'collections.abc', 'contextlib', 'data.dbcompat', 'logging', 'os', 'psycopg', 'sqlite3', 'urllib.parse']
  PASS  ⑬ 공유 Postgres po_drafts 행 수 불변 (격리 스키마만 썼다는 증거)                         5 → 5행
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (7건) — 동시 쓰기가 잠기지 않고 D10·D15 경계는 그대로다
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/rag_contract.py
rag_search_manual 계약 검증 (합성 인덱스)

dense 스코어러 비활성 — 질의 임베딩 실패: NVIDIA_EMBED_MODEL 이 설정되지 않았습니다 — .env 에 실제 카탈로그 모델 ID를 넣으세요 (기본값을 두지 않는 이유: 임의 모델로 과금되는 사고를 막기 위해, MAINTQ_LLM_MODEL 과 같은 관례)
dense 스코어러 비활성 — 질의 임베딩 실패: NVIDIA_EMBED_MODEL 이 설정되지 않았습니다 — .env 에 실제 카탈로그 모델 ID를 넣으세요 (기본값을 두지 않는 이유: 임의 모델로 과금되는 사고를 막기 위해, MAINTQ_LLM_MODEL 과 같은 관례)
dense 스코어러 비활성 — 질의 임베딩 실패: NVIDIA_EMBED_MODEL 이 설정되지 않았습니다 — .env 에 실제 카탈로그 모델 ID를 넣으세요 (기본값을 두지 않는 이유: 임의 모델로 과금되는 사고를 막기 위해, MAINTQ_LLM_MODEL 과 같은 관례)
dense 스코어러 비활성 — 질의 임베딩 실패: NVIDIA_EMBED_MODEL 이 설정되지 않았습니다 — .env 에 실제 카탈로그 모델 ID를 넣으세요 (기본값을 두지 않는 이유: 임의 모델로 과금되는 사고를 막기 위해, MAINTQ_LLM_MODEL 과 같은 관례)
dense 스코어러 비활성 — 질의 임베딩 실패: NVIDIA_EMBED_MODEL 이 설정되지 않았습니다 — .env 에 실제 카탈로그 모델 ID를 넣으세요 (기본값을 두지 않는 이유: 임의 모델로 과금되는 사고를 막기 위해, MAINTQ_LLM_MODEL 과 같은 관례)
dense 스코어러 비활성 — 질의 임베딩 실패: NVIDIA_EMBED_MODEL 이 설정되지 않았습니다 — .env 에 실제 카탈로그 모델 ID를 넣으세요 (기본값을 두지 않는 이유: 임의 모델로 과금되는 사고를 막기 위해, MAINTQ_LLM_MODEL 과 같은 관례)
────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① model 필터 — iG5A 질의에 S100 청크 없음              status=ok, pages=[204, 202]
  PASS  ② 같은 질의 2회 → 동일 결과                            완전 일치
  PASS  ③ 청크 키가 text/page/section 뿐 (score 없음)        ['page', 'section', 'text']
  PASS  ④ D53 text 무절단 (원본과 완전 동일)                    888자 · 원본 888자 · 동일=True
  PASS  ⑤ D26 page 는 물리 페이지 정수 무가공                    pages=[204, 202]
  PASS  ⑥ 매칭 없음 → empty (error 아님)                    status=empty
  PASS  ⑦ model enum 강제                               reason=invalid_model
  PASS  ⑧ query 필수                                    reason=query_required
  PASS  ⑨ 인덱스 미구축 → error/index_not_built (empty 아님)  status=error, reason=index_not_built
  PASS  ⑩ 빈 인덱스 → error (empty 와 구분)                  reason=index_not_built
  PASS  ⑪ top_k 과대 입력도 안전                             status=ok, 2건
  PASS  ⑫ 실 인덱스 검색 + 파일 불변                            status=ok, 3건, pages=[37, 146, 38]
  PASS  ⑬ D110 IE5 실 인덱스 검색 + 파일 불변                   status=ok, 3건, pages=[134, 125, 122]
────────────────────────────────────────────────────────────────────────────────────────

통과 (13건) — D53 무절단 · D26 page 무가공 · 미구축≠empty · D110 IE5 실 인덱스 검색 확인
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/agent_loop_contract.py
에이전트 루프 계약 검증 (ScriptedClient — API 키 불필요)

───────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① A1 tool_call → tool_result 순서                              ['tool_call', 'tool_result', 'token', 'block']
  PASS  ② 도구 없는 응답 → 턴 종료                                            calls=[]
  PASS  ③ 루프 탈출 — 동일 호출 반복 차단                                        실행 1회
  PASS  ④ 턴당 도구 호출 상한 8                                              8회
  PASS  ⑤ 안전 블록이 위험 서술보다 먼저                                          safety=2, 위험=3
  PASS  ⑥ 안전 문구는 SAFETY_BASELINE 상수 (LLM 생성 아님)                      상수 일치 + '10분 이상'
  PASS  ⑥-b ★ 안전 블록 인용이 SAFETY_BASELINE 페이지 (도구 페이지 아님)              page=4 (기대 4, 도구는 204)
  PASS  ⑥-c 안전 블록 인용이 계약 형태 {page,print_page,label}                  {'page': 4, 'print_page': 4, 'label': 'iG5A 매뉴얼 p.4'}
  PASS  ⑦ 근거 없으면 안전 블록·위험 서술 둘 다 안 냄                                 safety=0건
  PASS  ⑦-b 전제: 이 문장은 키워드 트리거에 안 걸린다 (안 그러면 ⑦-c 가 공회전)               '해당 부품을 교체하시면 됩니다.'
  PASS  ⑦-b ⓑ 트리거 — 근거 O + 부품 조회 O 면 키워드 없이도 안전 블록 발행                safety=1건 · 본문 유지=True
  PASS  ⑦-c ★ 안전핀: 근거 없으면 ⓑ 미발동 — 블록도 없고 **본문도 안 잘린다**               safety=0건 · 본문 유지=True
  PASS  ⑧ D30 citation.page == lookup 결과 page                        page=202 (도구 202)
  PASS  ⑨ A8·D45 repeated → po_card variant:hold                     keys=['checklist', 'reason', 'repeated', 'variant']
  PASS  ⑩ hold checklist 의 citation 은 rag page 에서만                   [204, 206]
  PASS  ⑩-b hold checklist citation 도 계약 형태 · label 중복 없음            ['iG5A 매뉴얼 p.204 · 12.2 고장 대책', 'iG5A 매뉴얼 p.206 · 12.3 절연 점검']
  PASS  ⑨-b N-1 window_days 가 호출에 쓴 days 를 따른다 (30 하드코딩 아님)          window_days=7 (호출 days=7)
  PASS  ⑩-c ★ S100 안전 인용에 음수 페이지가 안 뜬다 (D49 경계)                      {'page': 2, 'print_page': 2, 'label': 'S100 매뉴얼 p.2'}
  PASS  ⑪ draft po_card 에 part_name·supplier_name·lead_days          {'part_name': '냉각팬 (iG5A 표준)', 'supplier_name': '에이스산전', 'lead_days': 3}
  PASS  ⑫ D37 신원 stamp (requested_by 채워짐)                            requested_by=tech-01, session=T9
  PASS  ⑬ A5 발행 이벤트가 전부 traces 에 저장                                  traces=3, 발행=3, types=['block', 'tool_call', 'tool_result']
  PASS  ⑭ 도구 실패 시 status:error 가 trace 에 그대로                         status=error, citation=0건
  PASS  ⑭-b D54 tool_result.pages — ok 는 근거 page, 실패는 빈 리스트          ok=[[202], [204, 205, 206]], error=[]
  PASS  ⑮ A2 발주 식별 필드가 구조 그대로 보존 (다건)                                suppliers=[{'supplier_id': 'SUP-A', 'lead_days': 3, 'unit_price': 38000, 'moq': 1}, {'supplier_id': 'SUP-B', 'lead_days': 14, 'unit_price': 29000, 'moq': 10}]
  PASS  ⑮-b D12 related_parts 품번이 이력에 보존됨                            리스트 원형 유지
  PASS  ⑮-c related_parts 다건 전부 보존                                   2건 유지
  PASS  ⑮-d 목록에 없던 필드도 보존 (블랙리스트 뒤집기)                                meaning=과열 actions=['냉각팬을 교체하십시오'] 제조사=LS
  PASS  ⑮-e rag 본문만 절삭 · page·section 은 보존 · 절삭 사실 명시                text=409자 tail=가가가…(총 900자)
  PASS  ⑮-f 리스트 상한 초과분은 생략 표식을 남김                                    11개 · 마지막=…외 3건 생략
  PASS  ⑮-g Gemini 는 functionResponse 파트로 변환 (평문 아님)                 name=lookup_error_code keys=['_summary', 'actions', 'code', 'error_name']
  PASS  ⑮-h Anthropic 은 JSON 텍스트로 변환 (tool_use 짝 없음 — 주석 참조)         [도구 결과 lookup_error_code]
{"_summary": "OHT 냉각핀 과열 (fault) ·
  PASS  ⑯-a D76-2 도구 원본이 traces.tool_payload 에 저장 (SSE 는 요약본 그대로)    tool_payload keys=['actions', 'causes', 'code', 'display_code', 'error_name', 'manual_page', 'related_parts', 'severity', 'status'], sse keys=['elapsed', 'pages', 'parts', 'status', 'summary', 'tool']
  PASS  ⑯-b ★ end 델타의 stop reason 기록 (★ 음성: STOP → truncated=0)      잘림=['[LLM_END] session=TEND1 call=1 reason=MAX_TOKENS truncated=1'], 정상=['[LLM_END] session=TEND2 call=1 reason=STOP truncated=0']
  PASS  ⑯-c 제공자별 표기가 같은 판정으로 정규화 (Gemini enum · Anthropic · length)  MAX_TOKENS/max_tokens/length → True · STOP/end_turn/tool_use/None → False
  PASS  ⑯ A7 ★ 루프가 error_history 에 쓰지 않음 (★ 양성: 앵커 실재 + 스캐너 생존)      위반 적발 0건 · loop.py 25581자 · 앵커 3/3 ['async def run_turn(', 'from backend.db import connect', 'TraceWriter'] · 스캐너 생존 True
───────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (35건) — A1·A2·A5·A7·A8 · D30·D37·D45 확인
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/eval_score_contract.py
eval/score.py 계약 검증 (합성 traces — DB·API 불필요)

[중단] D88 프로파일 가드 — 평가는 core 프로파일에서만 유효합니다.
  - 위반: tools_profile='full' — 기대 'core' (backend env 에코, main.py:111)
  왜 막는가: 확장 9종(04 §8~§16)이 등록된 상태의 점수는 core 기준 지표와 분모가 달라 이전 회차와 비교할 수 없습니다. 사후에는 어느 프로파일로 돌았는지 복원할 수 없어 결과 전체가 무효가 됩니다.
  어떻게 푸는가: ① MAINTQ_TOOLS_PROFILE 을 unset 하거나 'core' 로 두고 다시 실행 — 이 값은 자식 MCP 서버로 상속되므로 셸 세션 전체에서 지워야 합니다. ② 의도한 full 실행이면 --allow-full-profile 을 명시하십시오.
[중단] D88 프로파일 가드 — 평가는 core 프로파일에서만 유효합니다.
  - 위반: tools=14 — 기대 ≤7 (list_tools() 실측, main.py:110)
  왜 막는가: 확장 9종(04 §8~§16)이 등록된 상태의 점수는 core 기준 지표와 분모가 달라 이전 회차와 비교할 수 없습니다. 사후에는 어느 프로파일로 돌았는지 복원할 수 없어 결과 전체가 무효가 됩니다.
  어떻게 푸는가: ① MAINTQ_TOOLS_PROFILE 을 unset 하거나 'core' 로 두고 다시 실행 — 이 값은 자식 MCP 서버로 상속되므로 셸 세션 전체에서 지워야 합니다. ② 의도한 full 실행이면 --allow-full-profile 을 명시하십시오.
[중단] D88 프로파일 가드 — 평가는 core 프로파일에서만 유효합니다.
  - 위반: tools_profile='full' — 기대 'core' (backend env 에코, main.py:111)
  - 위반: tools=14 — 기대 ≤7 (list_tools() 실측, main.py:110)
  왜 막는가: 확장 9종(04 §8~§16)이 등록된 상태의 점수는 core 기준 지표와 분모가 달라 이전 회차와 비교할 수 없습니다. 사후에는 어느 프로파일로 돌았는지 복원할 수 없어 결과 전체가 무효가 됩니다.
  어떻게 푸는가: ① MAINTQ_TOOLS_PROFILE 을 unset 하거나 'core' 로 두고 다시 실행 — 이 값은 자식 MCP 서버로 상속되므로 셸 세션 전체에서 지워야 합니다. ② 의도한 full 실행이면 --allow-full-profile 을 명시하십시오.
[중단] D88 프로파일 가드 — 평가는 core 프로파일에서만 유효합니다.
  - 위반: tools_profile=None — 기대 'core' (backend env 에코, main.py:111)
  왜 막는가: 확장 9종(04 §8~§16)이 등록된 상태의 점수는 core 기준 지표와 분모가 달라 이전 회차와 비교할 수 없습니다. 사후에는 어느 프로파일로 돌았는지 복원할 수 없어 결과 전체가 무효가 됩니다.
  어떻게 푸는가: ① MAINTQ_TOOLS_PROFILE 을 unset 하거나 'core' 로 두고 다시 실행 — 이 값은 자식 MCP 서버로 상속되므로 셸 세션 전체에서 지워야 합니다. ② 의도한 full 실행이면 --allow-full-profile 을 명시하십시오.
[--allow-full-profile] D88 가드를 명시적으로 우회합니다:
  - tools_profile='full' — 기대 'core' (backend env 에코, main.py:111)
  - tools=14 — 기대 ≤7 (list_tools() 실측, main.py:110)
  ⚠ 이 실행의 지표는 core 프로파일 기준 결과와 **같은 축에 놓을 수 없습니다** (D69) — 결과 MD 의 meta 로 구분하십시오.
  [경고] 권한 403 점검 실패: ConnectError: All connection attempts failed
───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① 정상 S1 — 4지표 전부 pass                                                        part:P; citation:P; safety:P; sequence:P
  PASS  ② citation page 불일치 → fail [합성 rich payload 한정] (★ 음성: 202→pass, 999→fail)   999:False / 202:True
  PASS  ③ safety 기준값 완화('5분') → fail (★ 음성: 10분→pass, 5분→fail)                       5분:False / 10분:True
  PASS  ④ S3 에서 create_po_draft → sequence fail (★ 음성: 미호출→pass, 호출→fail)            호출:False / 미호출:True
  PASS  ⑤ catalog_not_loaded 를 S4 로 → citation fail 이고 분모 포함 (D50)                   passed=False, applicable=True
  PASS  ⑥ S4 정답(not_found) → citation applicable=False (★ 음성: catalog→fail/포함)       not_found.applicable=False / catalog.applicable=True
  PASS  ⑦ S4 정답 → 인용 분모 제외로 인용률 불변 (통과 1 / 분모 1 = 100%)                              통과 1 / 분모 1
  PASS  ⑧ 부품 특정 불일치 → part fail (★ 음성: 정답→pass, 오답→fail)                             오답:False / 정답:True
  PASS  ⑧-b D66 대체품 결과로 부품 특정 인정 (원부품 아닌 대체품)                                        특정 part_no=PCB-S100-CTRL-R2 (기대 PCB-S100-CTRL-R2)
  PASS  ⑧-c D66 결과 다건이면 특정 실패 (★ 첫 항목을 정답으로 세지 않음)                                   특정 part_no=None (기대 FAN-IG5-01)
  PASS  ⑧-d 인자 part_no 가 결과보다 우선 (기존 판정 경로 불변)                                       특정 part_no=FAN-IG5-01 (기대 FAN-IG5-01)
  PASS  ⑨ 안전 블록에 근거 page 없음 → safety fail                                            안전 블록에 인용 근거 page 없음
  PASS  ⑩ citation 블록 미발행 → fail                                                     인용 블록 없음 (진단 응답인데 근거 미발행)
  PASS  ⑪ tool_result 요약본(page 없음) → 발행=근거로 citation pass (degraded)                 인용 발행 [202]; 도구 요약에 근거 page 없어 발행=근거로 인정 (degraded)
  PASS  ⑫ create_po_draft 없으면 search_inventory 인자로 부품 특정                             특정 part_no=FAN-IG5-01 (기대 FAN-IG5-01)
  PASS  ⑬ safety_required 아님 → applicable=False (분모 제외)                              applicable=False
  PASS  ⑭ score_session → [part, citation, safety, sequence] 4지표 고정                  ['part', 'citation', 'safety', 'sequence']
  PASS  ⑮ D54 pages 로 strict — 근거 안 pass / 밖 fail (★ 음성: 202→pass, 999→fail)         202:True / 999:False
  PASS  ⑯ D54 pages=[] (생산자 존재·근거 없음) → fail (★ 음성: 키 없으면 ⑪ degraded pass)           인용 발행 [202] 이나 tool_result.pages 근거가 빈 집합 (지어낸 페이지, D54)
  PASS  ⑰ D55 has_replay — replay:true 섞인 세션 감지 (★ 음성: 없으면 False)                    replay=True / live=False
  PASS  ⑱ D88 이중 게이트 — 에코만 full·실측만 14·둘 다·health 불명 → 전부 exit 2 (★ 음성: core/7 → 0)  에코만:2 / 실측만:2 / 둘다:2 / 불명:2 / core:0
  PASS  ⑲ D88 --allow-full-profile → 우회해 exit 0 (★ 위반 사유 자체는 2건 그대로 보고)              exit=0 / 사유 2건: ["tools_profile='full' — 기대 'core' (backend env 에코, main.py:111)", 'tools=14 — 기대 ≤7 (list_tools() 실측, main.py:110)']
  PASS  ⑳ D88 확장 — meta.llm_model 은 env 그대로, 없으면 null (★ 음성: 빈 값도 null)              설정='gemini-2.5-flash' / 빈값=None / 미설정=None / meta키=['llm_cache', 'llm_model', 'llm_provider', 'tools', 'tools_profile']
  PASS  ㉑ [LLM_END] 생산자(loop) → 소비자(run_eval) 라운드트립 · 잡음 줄 무시                        파싱 4줄 · 잘림 2 · {'MAX_TOKENS': 2, 'STOP': 1, 'STREAM_ERROR': 1}
  PASS  ㉑-b ★ 음성: 정상 종료만 → 잘림 0건 (measured=True 는 유지)                                measured=True / 잘림=0
  PASS  ㉒ 미계측(마커 0건)과 잘림 0건을 다른 문장으로 보고                                              미계측=- 잘린 턴: **계측 실패** — `[LLM_END]` 마커 0건 (서버 stderr 미회수… / 0건=- 잘린 턴: **0건** / LLM 호출 2회 (종료 사유: STOP×2)…
  PASS  ㉓ 3회차 — 뒤집힌 문항만 flipped, 나머지는 안정 통과/안정 실패                                    flipped=['T02'] · part={'stable_pass': 1, 'stable_fail': 1, 'flipped': 1, 'undetermined': 0}
  PASS  ㉓-b ★ 음성: 3회 동일 판정 → 흔들림 0칸                                                  flipped=0 · part={'stable_pass': 1, 'stable_fail': 0, 'flipped': 0, 'undetermined': 0}
  PASS  ㉔ 1회차 — measurable=False 이고 MD 가 '측정 불가'라고 쓴다(0건이 아니다)                       measurable=False / md=## 회차 간 흔들림  - **측정 불가** — 실행 회차 1회. 뒤집힘은 2회차 이상에서만 정의된다(`--…
  PASS  ㉕ 실행 실패 회차는 분모 제외 — 통과 2/측정 2 로 '안정 통과'(흔들림 아님)                              T05={'passed': 2, 'measured': 2, 'state': 'stable_pass'}
  PASS  ㉖ 측정 회차 <2 인 칸은 undetermined (안정으로 읽지 않는다)                                   T06={'passed': 1, 'measured': 1, 'state': 'undetermined'}
  PASS  ㉗ hallucination 은 통과 축으로 정규화(hallucinated=True → passed=False)               clean=True / bad=False / T07={'passed': 2, 'measured': 3, 'state': 'flipped'}
  PASS  ㉙ 403 점검이 죽어도 실행은 계속 — 결과를 반환하고 사유를 싣는다 (N문항 폐기 금지)                          perm=(False, '점검 실패 — ConnectError')
  PASS  ㉚ 자식 서버 stderr 를 PIPE 로 두지 않는다 (읽지 않는 파이프 = 이벤트 루프 정지)                       PIPE 미사용
  PASS  ㉚-b ★ 뮤턴트: 읽지 않는 PIPE 로는 자식이 멈추고, 파일로는 완주한다                                  PIPE 차단=True · 파일 완주=True(300000바이트)
  PASS  ㉘ --repeat 비용 추정이 회차를 곱한다 (200 → 600회)                                       1회차=문항 20개 × 최대 10회 LLM 호출(MAX_LLM_CALLS_PER_TURN) = 최대 200회. 실측… / 3회차=문항 20개 × 3회차 × 최대 10회 LLM 호출(MAX_LLM_CALLS_PER_TURN) = 최대 600회. …
───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

data/maintq.db mtime 불변: True (before=1787533322088414500, after=1787533322088414500)

통과 (36건) — 4지표 · D30 분모 · D50 S4 · 발행=근거 폴백 · D88 프로파일 가드 확인
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/s4_smoke.py
MQ-311 — S4 관통 스모크 (run_turn in-process · ScriptedClient · 실 MCP)

공유 Postgres error_codes(before) = 70행

[격리] DATABASE_URL(loaded) = postgresql://postgres:postgres@127.0.0.1:5434/maintq?options=-c%20search_path%3Ds4_loaded_1787535302_femcmg%2Cpublic
[격리] DATABASE_URL(empty)  = postgresql://postgres:postgres@127.0.0.1:5434/maintq?options=-c%20search_path%3Ds4_empty_1787535303_buxwdr%2Cpublic


공유 Postgres error_codes(after) = 70행
───────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① 미지 코드 lookup 이 실제 1회 호출                                  lookup 1회 · 전체 tool_call 1건
  PASS  ② lookup 결과 status == not_found                            status=not_found
  PASS  ③ 최종 응답에 '확인되지 않' 포함                                       요청하신 코드 E999 는 iG5A 매뉴얼에서 확인되지 않는 코드입니다. 정확한 코드를 다시 확인하시거나 제
  PASS  ④ citation 블록 0건                                           citation 0건
  PASS  ⑤ create_po_draft 미호출                                      create_po_draft 0회
  PASS  ⑥ traces 에 tool_call·tool_result 행 존재 (A5)                 count=2, types=['tool_call', 'tool_result']
  PASS  ⑦ 재조회 없음 — traces 의 lookup tool_call 정확히 1건                lookup tool_call 1건
  PASS  ⑧ 정상 코드 OHt 조회는 status == ok                               status=ok
  PASS  ⑨ D50 — 0행 DB 는 not_found 가 아니라 error(catalog_not_loaded)  status=error, summary='에러코드 표가 아직 적재되지 않았습니다 — 조회 결과 없음이 아니라 데이'
  PASS  DB 안전 · 공유 DB 불변                                           변경=False
───────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (S4判定 9건 + DB 안전 게이트 1건) — 루프가 not_found 를 왜곡 없이 흘림
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/llm_provider_contract.py
LLM 제공자 계약 검증 (D40 · D56 — SDK 호출·네트워크 없음)

───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① gemini_schema — title/additionalProperties/$schema 제거, 계약 키 보존             keys=['properties', 'required', 'type']
  PASS  ② gemini_schema — items/properties 재귀 (중첩 title·default 제거)                  {'type': 'array', 'items': {'type': 'object', 'properties': {'qty': {'type': 'integer'}}}}
  PASS  ③ gemini_declarations — 이름·설명 보존, 무인자 도구는 parameters 없음                      [['description', 'name', 'parameters'], ['description', 'name']]
  PASS  ④ gemini_contents — assistant→model, 평문 user 유지                              roles=['user', 'model', 'user']
  PASS  ⑤ gemini_chunk_deltas — text part 정규화
  PASS  ⑥ function_call → ToolUse, id 합성(fc-N)                                       [('tool_use', ToolUse(id='fc-1', name='lookup_error_code', input={'model': 'iG5A', 'code': 'OHt'}))]
  PASS  ⑦ args=None → {}, SDK id 보존                                                  [('tool_use', ToolUse(id='srv-9', name='ping', input={}))]
  PASS  ⑧ provider 오타 → RuntimeError                                                 MAINTQ_LLM_PROVIDER 는 ('gemini', 'anthropic', 'elice', 'open
  PASS  ⑨ 기본 gemini — 키 없으면 실패 (GEMINI_API_KEY 안내, 폴백 없음)                            환경변수(또는 .env)에 GEMINI_API_KEY(또는 GOOGLE_API_KEY) 이(가) 없습니다 (provider=gemini). 테스
  PASS  ⑩ GOOGLE_API_KEY 인정 → GeminiClient                                           GeminiClient
  PASS  ⑪ anthropic — 키 없으면 실패 (ANTHROPIC_API_KEY 안내)                                환경변수(또는 .env)에 ANTHROPIC_API_KEY 이(가) 없습니다 (provider=anthrop
  PASS  ⑬ D56 — 빈 문자열 provider → 기본 gemini 적용 (★ 음성: .get 패턴이면 RuntimeError)         GeminiClient
  PASS  ⑭ D56 — 빈 MAINTQ_CORS_ORIGINS → 기본 dev 범위 유지 (브라우저 검증 실측 결함)                 origins=12개
  PASS  ⑫ D56 — OS env 우선 (main.py override=False + dotenv 실측)                       src=True, os유지·빈곳채움=True
  PASS  ⑮ elice_tools — type:function 래핑, name·description·parameters 보존             [{'type': 'function', 'function': {'name': 'lookup_error_code', 'description': '코드 조회', 'parameters': {'type': 'object', 'properties': {'code': {'type': 'string'}}}}}]
  PASS  ⑯ elice_messages — tool 결과를 JSON 텍스트로 평탄화한 user 메시지로 (thought_signature 회피)  roles=['user', 'assistant', 'user']
  PASS  ⑰ elice_chunk_delta — 텍스트 델타 정규화                                             '안녕',[],None
  PASS  ⑱ elice_chunk_delta — tool_call 조각 추출(부분 arguments 포함)                       [{'index': 0, 'id': 'call_abc', 'name': 'lookup_error_code', 'arguments': '{"model":'}]
  PASS  ⑲ elice_chunk_delta — finish_reason 정규화                                      tool_calls
  PASS  ⑳ elice_finalize_tool_calls — index 오름차순, 조각난 JSON arguments 병합·파싱           [ToolUse(id='call_1', name='lookup_error_code', input={'model': 'iG5A'}), ToolUse(id='call_2', name='search_insurance_clause', input={'question': 'q'})]
  PASS  ㉑ elice — 키 없으면 실패 (ELICE_API_KEY 안내)                                        환경변수(또는 .env)에 ELICE_API_KEY · ELICE_LLM_URL 이(가) 없습니다 (provider=elice). 테스트용 스크
  PASS  ㉒ elice — ELICE_LLM_URL 없으면 실패                                               환경변수(또는 .env)에 ELICE_LLM_URL 이(가) 없습니다 (provider=elice). 테스트용 스크립트 응답으로 자동 대체하지
  PASS  ㉓ elice — 키·URL 모두 있으면 EliceClient                                           EliceClient
───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (23건) — 변환 순수함수 · provider 분기 · OS env 우선 확인
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/eval_replay_guard.py
eval/run_eval.py aggregate() 분모 제외 배선 회귀 (합성 ItemResult — API·서버·DB 불필요)

─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  사전 A — 적용 가능한 지표 전부 pass (설계 의도 확인)                                                    part:P/True; citation:P/True; safety:P/False; sequence:P/False
  PASS  사전 B — 일부러 fail 조합인가 (분모에 잘못 섞이면 rate 가 떨어져야 함)                                        part:F/True; citation:F/True; safety:P/False; sequence:P/False
  PASS  ① aggregate([A,B(first)]) 의 metrics == aggregate([A]) (B 완전 배제)                        AB={'part': {'passed': 1, 'total': 1, 'rate': 1.0}, 'citation': {'passed': 1, 'total': 1, 'rate': 1.0}, 'safety': {'passed': 0, 'total': 0, 'rate': None}, 'sequence': {'passed': 0, 'total': 0, 'rate': None}, 'hallucination': {'hallucinated': 0, 'total': 0, 'rate': None}} / A={'part': {'passed': 1, 'total': 1, 'rate': 1.0}, 'citation': {'passed': 1, 'total': 1, 'rate': 1.0}, 'safety': {'passed': 0, 'total': 0, 'rate': None}, 'sequence': {'passed': 0, 'total': 0, 'rate': None}, 'hallucination': {'hallucinated': 0, 'total': 0, 'rate': None}}
  PASS  ① excluded_replay == 1 (B 하나만 재생 오염)                                                   AB.excluded_replay=1 / A.excluded_replay=0
  PASS  ① n_kept == 1 (A 만 kept, B 제외)                                                         n_kept=1, n_items=2
  PASS  ② has_replay — 표식이 리스트 마지막이어도 True                                                     events[0]=None, events[-1]=True
  PASS  ② aggregate([A,B(last)]) 도 aggregate([A]) 와 지표 동일 (위치 무관)                              metrics 동일=True, excluded_replay=1
  PASS  ③ aggregate([]) 이 ZeroDivisionError 없이 반환                                              정상 반환
  PASS  ③ aggregate([]) 의 모든 지표 total==0, rate=None                                            {'part': {'passed': 0, 'total': 0, 'rate': None}, 'citation': {'passed': 0, 'total': 0, 'rate': None}, 'safety': {'passed': 0, 'total': 0, 'rate': None}, 'sequence': {'passed': 0, 'total': 0, 'rate': None}, 'hallucination': {'hallucinated': 0, 'total': 0, 'rate': None}}
  PASS  ③ aggregate([]) 의 n_items/n_kept/excluded_* 전부 0, failed_items 빈 리스트                   {'n_items': 0, 'n_kept': 0, 'excluded_replay': 0, 'excluded_failed': 0, 'metrics': {'part': {'passed': 0, 'total': 0, 'rate': None}, 'citation': {'passed': 0, 'total': 0, 'rate': None}, 'safety': {'passed': 0, 'total': 0, 'rate': None}, 'sequence': {'passed': 0, 'total': 0, 'rate': None}, 'hallucination': {'hallucinated': 0, 'total': 0, 'rate': None}}, 'failed_items': []}
  PASS  사전 D — sequence 가 공허하게 PASS (create_po_draft 미호출, applicable=True)                     passed=True, applicable=True, detail=S3 보류 — create_po_draft 미호출
  PASS  ④ aggregate([A,D]) 의 metrics == aggregate([A]) (D 완전 배제, Stage 2 회귀)                   AD={'part': {'passed': 1, 'total': 1, 'rate': 1.0}, 'citation': {'passed': 1, 'total': 1, 'rate': 1.0}, 'safety': {'passed': 0, 'total': 0, 'rate': None}, 'sequence': {'passed': 0, 'total': 0, 'rate': None}, 'hallucination': {'hallucinated': 0, 'total': 0, 'rate': None}} / A={'part': {'passed': 1, 'total': 1, 'rate': 1.0}, 'citation': {'passed': 1, 'total': 1, 'rate': 1.0}, 'safety': {'passed': 0, 'total': 0, 'rate': None}, 'sequence': {'passed': 0, 'total': 0, 'rate': None}, 'hallucination': {'hallucinated': 0, 'total': 0, 'rate': None}}
  PASS  ④ excluded_failed == 1 (D 하나만 실행 실패, excluded_replay 는 0)                              excluded_failed=1, excluded_replay=0
  PASS  ④ D 의 공허한 sequence PASS 가 sequence 분모에 안 들어감                                           AD.sequence.total=0, A.sequence.total=0
  PASS  ④ failed_items 에 D1 이 기록됨(집계에서는 빠지되 실패 사실은 노출)                                         ['D1']
  PASS  ⑤ aggregate([A,B,D]) 도 aggregate([A]) 와 지표 동일 + excluded_replay=1 · excluded_failed=1  metrics 동일=True, excluded_replay=1, excluded_failed=1, n_kept=1
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (16건) — replay/실행실패 분모 제외 · 0분모 방어 · 표식 위치 무관 확인
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/law_fetch_contract.py
법령 수집·적용 계약 검증 — tmp 사본 + 합성 픽스처 (네트워크·정본 파일 미사용)

──────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ⓪ laws/ 8건 · FETCHED 는 원문+해시 일치 · PENDING 은 원문 없음           8건 · FETCHED 8건 · PENDING 없음 · 해시 불일치 없음 · 원문 있는 PENDING 없음
  PASS  ⓐ 최초 수집 → FILLED · text_hash 기입                             FILLED, hash=sha256:52f59a198893b…, retrieved_at 有
  PASS  ⓐ-2 키 집합 보존 (필드 추가·누락 없음)                                   초과=없음, 누락=없음
  PASS  ⓑ 조문번호 불일치 → 중단 · 파일 바이트 불변                                 LawMismatchError / 바이트 동일=True
  PASS  ⓑ-2 제목 불일치 → 중단 · 파일 바이트 불변 · 개정 기록도 없음                     LawMismatchError / 바이트 동일=True / pending 0건
  PASS  ⓑ-W5-a article 키 누락 → 중단 · 파일 바이트 불변                        LawMismatchError / 바이트 동일=True / msg에 'article' 포함
  PASS  ⓑ-W5-b title 빈 문자열 → 중단 · 파일 바이트 불변                         LawMismatchError / 바이트 동일=True / 누락 키만 지목
  PASS  ⓑ-W5-c 선택적 필드 없어도 통과 (정체성 키만 필수)                            FILLED / effective_from·promulgation_no 는 null 유지 (지어내지 않음)
  PASS  ⓑ-3 미등록 law_ref_id 거부 (D61)                                 KeyError / 파일 생성 안 됨
  PASS  ⓒ FETCHED + 해시 상이 → REVISION_PENDING · 원본 불변                REVISION_PENDING, pending 1건, 원본 바이트 동일=True
  PASS  ⓒ-2 재감지 시 기록 누적 (append-only, D60)                          1건 → 2건, 기존 파일 불변
  PASS  ⓒ-3 동일 원문 → UNCHANGED · 무기록                                 UNCHANGED, pending 증가 없음
  PASS  ⓒ-4 force → FILLED · 직전 스냅샷 보존 · confirmed 승격               FILLED, pending 3건 / confirmed 1건에 구 원문 보존
  PASS  ⓒ-5 기입 실패 → intent 로 남음 (거짓 '적용됨' 기록 없음)                    OSError / 법령파일 불변 / intent 1건 (requires_signature=true → 사람이 대조)
  PASS  ⓒ-6 intent→confirmed 전이가 payload 를 바꾸지 않음                   old/new text·hash·detected_at 동일 — 상태 3필드만 전이. 원 기록 불변
  PASS  ⓒ-7 서명 큐 필터 = requires_signature (confirmed 만 제외)           전체 4건 중 미처리 3건 (applied=None 2 + intent 1)
  PASS  ⓓ 전각/공백 변형 해시 동치 (NFKC + 공백 축약)                             3변형 → 해시 1종: sha256:d3067b7736f9ac89d…
  PASS  ⓓ-2 text_hash 재구현 없음 (engine 함수 동일 객체)                      engine 함수 그대로 · 자체 해시 흔적=없음
  PASS  ⓓ-3 파일 기입 해시 == engine.text_hash(원문)                        sha256:e395ee2169f48c714…
  PASS  ⓔ 빈 원문 거부 · 파일 바이트 불변                                       ValueError / 바이트 동일=True
  PASS  ⓕ 키 미설정 → RuntimeError (호출 전 차단)                            RuntimeError: LAW_API_OC 미설정. law.go.kr에서 OPEN API 이용 …
  PASS  ⓕ-2 JO 6자리(조4+가지2) · display=100 · search=1 — 실호출 확정 형식 고정  JO 4종 일치=True · 항 지정 차단=True · 검색 파라미터=True
  PASS  ⓘ 제목만 담긴 응답 → 적용 거부 (본문 1줄만 있어도 통과)                         LawFetchError · 본문 있으면 text 36자 (제목 15자)
  PASS  ⓙ '전문'(절 제목) 섞인 응답에서 '조문' 만 선택 · 항·호까지 평탄화                  text 65자 · '제4절' 배제 · effective_from=2026-06-01 (YYYYMMDD→ISO) · promulgation_no=21374 (기본정보 유래)
  PASS  ⓖ D59 벡터 인덱싱 흔적 없음                                          금지어 검출=없음
  PASS  ⓚ 인증값(OC) 이 추적 파일에 없다 (.env.example·세션 로그 평문 유출 재발 방지)      추적 파일 0건
  PASS  ⓗ 정본 laws/ 불변 (내용 해시)                                       sha256[:16]=b1f87cf9285ed59b (7파일 전부 그대로)
  PASS  ⓗ-2 정본 pending_revisions/ 생성 안 됨                            존재=False (실행 전과 동일)
──────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (28건) — D59·D60·D61·D75 준수. 실수집은 MQ-701 이 완료했으나 **이 스위트는 법제처를 호출하지 않는다** — 응답 정규화를 순수 함수로 분리해 합성 응답으로 덮는다. 키·네트워크·법령 개정에 좌우되는 검사는 회귀가 아니다.
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/rules_db_load.py
근거계층 DB 로더 · build_facts 계약 검증 — 임시 DB (실 DB 미사용)

─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① LawRef 파일 == DB (D60)                                                  파일 8건 / DB 8건
  PASS  ② Rule 파일 == DB (dataclass 동치)                                           파일 5종 / DB 5종
  PASS  ③ rule_version 이 사본에도 실린다 (D60 복합 PK)                                    {'INSURANCE-NOTIFY': 3, 'LIEN-CONSENT': 2, 'SAFETY-INSPECTION': 4, 'TAX-CREDIT-2Y': 1, 'VAT-INVOICE': 2}
  PASS  ④ 근거 없는 룰 행 → RuleIntegrityError (D61)                                   BAD-NO-EVIDENCE: 근거 참조 없음
  PASS  ⑤ 미등록 법령 참조 행 → RuleIntegrityError                                       BAD-UNKNOWN-LAW: 미등록 법령 참조 KR-NOT-REGISTERED-999
  PASS  ⑥ 깨진 JSON INSERT → 스키마 CHECK 거부                                          CHECK constraint failed: json_valid(law_refs) AND json_valid(contract_refs) AND json_valid(trigger)
  PASS  ⑦ CHECK 없는 사본에서도 로더가 거부 (조용한 기본값 금지)                                     BAD-JSON: trigger JSON 파싱 실패 — Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
  PASS  ⑦-2 trigger = NULL → 로드 단계에서 RuleIntegrityError                          BAD-NULL-TRIGGER: 필수 컬럼 trigger 이 NULL
  PASS  ⑧ 개정본 공존 시 최신 rule_version 만 로드 (D60)                                    VAT-INVOICE 행 2개 → 로드 v3
  PASS  ⑨ NULL 컬럼이 facts 키에서 빠진다 (D62)                                           facts 키 ['asset_id', 'disposal_mode', 'status', 'vat_invoice_issued']
  PASS  ⑩ facts 에 None 값 키가 없다                                                   None 값 키 0건
  PASS  ⑪ False·0 은 값이므로 남는다                                                     tax_credit_applied=False, has_lien=False, lien_creditor=''
  PASS  ⑫ 파생 필드는 원천이 둘 다 있을 때만 (months)                                          disposal_date 有 → 17개월 / 無 → 키 없음
  PASS  ⑬ vat_invoice_issued 는 채우고 거래 사실은 안 채운다 (D77)                            precheck = 거래 성립 전 → 미발행이 확정 사실 · 매각가액/매수인은 원천 없음
  PASS  ⑭ risk_* 는 키 자체가 없다 (F6 원천 부재)                                           억지로 CLEAR 를 만들지 않는다
  PASS  ⑮ risk_score_delta_pct 키 부재 → 경계 검사 건너뜀 (예외·오탐 HOLD 없음)                  verdict=TRIGGERED
  PASS  ⑯ 사실 전부 NULL → INSUFFICIENT_FACTS (≠ CLEAR, ≠ HOLD) [D79]                verdict=INSUFFICIENT_FACTS · insufficient=['INSURANCE-NOTIFY', 'LIEN-CONSENT', 'SAFETY-INSPECTION', 'TAX-CREDIT-2Y'] · blockers=0
  PASS  ⑰ 반환 키가 asset_id 다 (D68 — equipment_id 아님)                               asset_id='AST-NULL' · 키 ['asset_id', 'blockers', 'disclaimer', 'evaluated_at']…
  PASS  ⑱ insured=0 은 '모름'이 아니라 '확인된 미부보' (D78)                                  insured=False → SCRAP verdict=CLEAR
  PASS  ⑲ 같은 자산도 SALE 이면 CONDITIONAL (매각 = 최소 CONDITIONAL, D78 부수)               SALE=CONDITIONAL preconds=['VAT-INVOICE'] / SCRAP=CLEAR
  PASS  ㉑ 주입 시 파일 로더 미호출 · 미주입은 현행대로 (D82 하위호환)                                  주입 중 로더 호출 0건 · 패치 유효=True · 주입 판정=CONDITIONAL / 파일 판정=CONDITIONAL
  PASS  ㉒ 주입 카탈로그가 판정을 지배 · 미등록 참조는 주입 경로에서도 거부 (D61 불변식 2)                      원본=CONDITIONAL → disposal_type 상향 시 BLOCKED · 게이트: VAT-INVOICE: 미등록 법령 참조 KR-NOT-REGISTERED-999
  PASS  ㉓ facts_used 는 입력의 얕은 사본 · laws_used 는 CLEAR 자산에서도 비지 않는다 (W7)           facts_used 13키 · CLEAR 자산 laws_used=['KR-CIVIL-388', 'KR-KCC-652', 'KR-OSHA-93', 'KR-OSHA-ENR-126', 'KR-STTC-146', 'KR-STTC-24', 'KR-VAT-32']
  PASS  ㉔ laws_all_fetched — 빈 dict False · 전 건 FETCHED True · 1건 PENDING False  빈=False · 전건=True · KR-CITA-ENF-31 PENDING=False
  PASS  ㉕ 실 DB 불변 (mtime)                                                        data/maintq.db 를 열지도 않았다
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (25건) — D60(파일이 정본)·D61(사본도 게이트 통과)·D62(NULL 은 CLEAR 가 아니다)·D77 준수
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/disposal_api_contract.py
S9 REST 계약 검증 — D71 HTTP 매핑 · 무저장 · 역할 게이트 없음 (임시 DB 사본)

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① 자산 목록 9건 (line 오름차순)                                                                                        9건 AST-L1-CONV
  PASS  ② line_id 필터                                                                                                  ['AST-L3-CONV', 'AST-L3-EXFAN', 'AST-L3-LIFT']
  PASS  ③ status 필터                                                                                                   IN_USE=9, DISPOSED=0
  PASS  ④ 상세 + 하위 equipment (D68)                                                                                     equipment=['INV-L3-01']
  PASS  ⑤ 없는 자산 상세 → 404                                                                                              404
  PASS  ⑥ AST-L3-CONV(세액공제+무동의담보) → 409 BLOCKED · blockers 2건                                                         409 BLOCKED blockers=['LIEN-CONSENT', 'TAX-CREDIT-2Y']
  PASS  ⑦ 409 본문 = 200 형태 + detail · 근거·해소경로가 함께 온다 (S9: 거부하되 이유와 경로를)                                                detail=법정 차단 사유 2건으로 처분할 수 없습니다: LIEN-CON… resolve=7건
  PASS  ⑧ AST-L4-WRAP(경계 22~26개월) → 409 HOLD (★ 200 이면 D62 붕괴)                                                        409 HOLD holds=['TAX-CREDIT-2Y']
  PASS  ⑨ AST-L4-DUST(tax_credit_applied NULL) → 409 INSUFFICIENT_FACTS (HOLD 로 흡수 안 함, D79)                          409 INSUFFICIENT_FACTS missing=['tax_credit_applied']
  PASS  ⑩ AST-L2-SPDL → 200 CONDITIONAL · checklist 비어있지 않고 **전 항목에 citations**                                       200 CONDITIONAL checklist=5항목
  PASS  ⑪ AST-L3-LIFT + SCRAP → 200 CLEAR                                                                             200 CLEAR checklist=0
  PASS  ⑫ 같은 자산·같은 날짜 + SALE → 200 CONDITIONAL (VAT-INVOICE — mode 로 판정이 갈린다)                                         200 CONDITIONAL preconditions=['VAT-INVOICE']
  PASS  ⑬ 없는 자산 precheck → 404                                                                                        404
  PASS  ⑭ disposal_mode 'GIFT' → 422 (enum 은 engine.DISPOSAL_MODES 단일 출처)                                             422
  PASS  ⑮ 판독 불가 disposal_date → 422 (조용히 무시하지 않는다)                                                                    422
  PASS  ⑯ disposal_date 생략 → 409, TAX-CREDIT-2Y 는 insufficient (CLEAR 로 조용히 통과 금지)                                    409 BLOCKED insufficient=['TAX-CREDIT-2Y']
  PASS  ⑰ technician·manager 모두 409/200/200 — **403 없음** (D38 지표 오염 방지)                                               {'technician': (409, 200, 200), 'manager': (409, 200, 200)}
  PASS  ⑱ generated_at 은 UTC ISO-8601(...Z) · evaluated_at 은 판정 기준일                                                   generated_at=2026-08-24T01:35:51Z, evaluated_at=2026-08-24
  PASS  ⑲ precheck 12회 호출 후에도 decisions·flags 행 수 불변 + assets 지문 불변                                                   before={'decisions': 0, 'flags': 0, 'assets': 9, 'rules': 5, 'law_refs': 8, 'assets_fingerprint': 1985131923} / after={'decisions': 0, 'flags': 0, 'assets': 9, 'rules': 5, 'law_refs': 8, 'assets_fingerprint': 1985131923}
  PASS  ⑳ REST(DB 사본) == 파일 정본 — verdict **+ 버킷별 rule_id 집합 + law_ref_id 집합** (verdict 만 보면 disposal_type 뮤턴트가 통과한다)  5자산 · 3축(verdict·버킷 4종·인용 조문) 전부 일치
  PASS  ㉑ GET /api/equipment 에 asset_id 가산 · INV-L1-01(분전반)은 null · 나머지 9대는 non-null                                  10대, INV-L1-01=None, INV-L3-01='AST-L3-CONV'
  PASS  ㉒ 기존 키 5종은 그대로 (가산이므로 기존 소비자 무영향)                                                                             keys=['asset_id', 'equipment_id', 'installed_at', 'line_id', 'location', 'model']
  PASS  ㉓ rules 0행 → 503 rule_catalog_not_loaded (500 아님)                                                             503 {'reason': 'rule_catalog_not_loaded', 'message': 'rules 테이블이 비어 있습니다 — data/seed.py 로 근거 계층을 적재하세요'}
  PASS  ㉔ D71 매핑 키 == engine.VERDICTS 5종 · 409 는 정확히 BLOCKED·HOLD·INSUFFICIENT_FACTS                                  {'BLOCKED': 409, 'HOLD': 409, 'INSUFFICIENT_FACTS': 409, 'CONDITIONAL': 200, 'CLEAR': 200}
  PASS  ㉕ not_considered 가 engine.NOT_CONSIDERED 와 동일 · backend 소스에 문구 리터럴 0건 (W2)                                    REST=['생산 계획·대체 설비 확보 여부', '시장 상황 및 매각 타이밍', '개별 계약의 특약 조항'] · 소스 복제=0건
  PASS  ㉖ disclaimer 가 engine.DISCLAIMER 와 동일 · backend 소스에 문구 리터럴 0건 (W2)                                            일치=True · 소스 복제=False
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (26건) — 409(BLOCKED·HOLD·INSUFFICIENT_FACTS)·200·404·422·503 · 무저장 확인
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/asset_tools_contract.py
[기대값 파생] build_evidence_bundle 정상 케이스 — 인용 조문 3건 전부 수집됨 → 번들 성공이 정상

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① check_disposal_blockers — 정상                                                                  status=ok reason=-
  PASS  ② check_disposal_blockers — 잘못된 입력                                                              status=error reason=invalid_input
  PASS  ③ check_disposal_blockers — 없는 대상                                                               status=not_found reason=unknown_asset
  PASS  ④ verify_ownership — 정상                                                                         status=ok reason=-
  PASS  ⑤ verify_ownership — 잘못된 입력                                                                     status=error reason=invalid_input
  PASS  ⑥ verify_ownership — 없는 대상                                                                      status=not_found reason=unknown_asset
  PASS  ⑦ classify_part_criticality — 정상                                                                status=ok reason=-
  PASS  ⑧ classify_part_criticality — 잘못된 입력                                                            status=error reason=invalid_input
  PASS  ⑨ classify_part_criticality — 없는 대상                                                             status=not_found reason=unknown_part
  PASS  ⑩ get_maintenance_metrics — 정상                                                                  status=ok reason=-
  PASS  ⑪ get_maintenance_metrics — 잘못된 입력                                                              status=error reason=invalid_input
  PASS  ⑫ get_maintenance_metrics — 없는 대상                                                               status=not_found reason=unknown_asset
  PASS  ⑬ classify_expenditure — 정상                                                                     status=ok reason=-
  PASS  ⑭ classify_expenditure — 잘못된 입력                                                                 status=error reason=invalid_input
  PASS  ⑮ classify_expenditure — 없는 대상                                                                  status=not_found reason=unknown_asset
  PASS  ⑯ assess_repair_value — 정상                                                                      status=ok reason=-
  PASS  ⑰ assess_repair_value — 잘못된 입력                                                                  status=error reason=invalid_input
  PASS  ⑱ assess_repair_value — 없는 대상                                                                   status=not_found reason=unknown_equipment
  PASS  ⑲ build_evidence_bundle — 정상                                                                    status=ok reason=-
  PASS  ⑳ build_evidence_bundle — 잘못된 입력                                                                status=error reason=invalid_input
  PASS  ㉑ build_evidence_bundle — 없는 대상                                                                 status=not_found reason=unknown_asset
  PASS  ㉒ verify_ownership — 시드 9자산 전부 PARTIAL 이하                                                       ['PARTIAL']
  PASS  ㉓ verify_ownership — FIXED_UNVERIFIED 카테고리 집합·항목 총량 핀 고정                                        카테고리 8종(기대 8) · 항목 26개(기대 ≥26)
  PASS  ㉔ verify_ownership — 상수를 비워도 무조건 UNVERIFIED 인 동적 항목이 남는다 (+ 갈아끼우기가 실제로 먹었음을 함께 단언 — 공허한 통과 차단)  VERIFIED 누출 [] · 항목 342→108 · 잔존 동적 미확인 ['감가상각 명세', '동일 기종 거래가', '매도인 세액공제', '반복 고장 패턴']
  PASS  ㉕ verify_ownership — 9카테고리·전 항목 state·UNVERIFIED limit                                          결함 0건 []
  PASS  ㉖ B-1 — last_overhaul_at 값이 있는 자산은 오버홀 VERIFIED                                                 대상 ['AST-L2-SPDL', 'AST-L4-WRAP'] · 어긋남 []
  PASS  ㉗ B-1 — 값이 없는 자산만 오버홀 UNVERIFIED(빈 값을 '실시함'으로 읽지 않는다)                                           대상 7자산 · 어긋남 []
  PASS  ㉘ B-1 — 오버홀 기록이 있는 자산의 residual_risk 에 '오버홀 미확인'이 없다                                            잔존 []
  PASS  ㉙ verify_ownership — insured=0(확인된 미부보)과 =1 이 다르게 표시                                            LIFT=확인된 미부보 (assets.insured=… / SPDL=부보 확인 (assets.insured=1)…
  PASS  ㉚ 처분 판정 — AST-L3-CONV/SALE → BLOCKED                                                            verdict=BLOCKED blockers=2(기대 2)
  PASS  ㉛ 처분 판정 — AST-L4-WRAP/SALE → HOLD                                                               verdict=HOLD
  PASS  ㉜ 처분 판정 — AST-L4-DUST/SALE → INSUFFICIENT_FACTS                                                 verdict=INSUFFICIENT_FACTS
  PASS  ㉝ 처분 판정 — AST-L2-SPDL/SALE → CONDITIONAL                                                        verdict=CONDITIONAL
  PASS  ㉞ 처분 판정 — AST-L3-LIFT/SALE → CONDITIONAL                                                        verdict=CONDITIONAL
  PASS  ㉟ 처분 판정 — AST-L3-LIFT/SCRAP → CLEAR                                                             verdict=CLEAR
  PASS  ㊱ check_disposal_blockers — 출력 키집합이 04 §8 과 정확히 일치 (초과 키 = 계약 드리프트)                             초과=없음 누락=없음
  PASS  ㊲ get_maintenance_metrics — 출력에 oee 키 부재 (D64)                                                  검출 []
  PASS  ㊳ classify_part_criticality — FAN-IG5-01 CRITICAL · reviewed 필드 존재                              part_class=CRITICAL reviewed=False
  PASS  ㊴ classify_expenditure — CAPITAL/REVENUE/HOLD 판정                                                ['CAPITAL', 'REVENUE', 'HOLD'] (기대 ['CAPITAL', 'REVENUE', 'HOLD'])
  PASS  ㊵ assess_repair_value — estimates[] 에 시장가·회복액이 나열된다 (D65 추정치 고지)                                verdict=REPAIR_RECOMMENDED estimates=['market_value_before', 'market_value_after', 'value_recovery', 'recovery_ratio']
  PASS  ㊶ assess_repair_value — ROOT_CAUSE_FIRST 는 수리/교체/매각 선택지를 내지 않는다 (규칙 14)                         verdict=ROOT_CAUSE_FIRST alternatives=[] estimates=[]
  PASS  ㊷ build_evidence_bundle — 원문이 있으면 해시 산출 · 같은 사실이면 2회 동일 (built_at 은 해시 밖)                       status=ok hash=sha256:678f7f7186afa9ba6… 동일=True 번들키=['contracts', 'evaluated', 'facts', 'laws', 'rules']
  PASS  ㊸ build_evidence_bundle — CLEAR 자산은 laws·rules 가 비어도 evaluated[] 는 비지 않는다 (W7)                  verdict=CLEAR evaluated=5건 hash=sha256:4a49bdff84971de7a…
  PASS  ㊹ MCP(파일 정본) verdict == REST(DB 사본) verdict — 같은 프로브 6조합 직접 대조                                  6조합 일치
  PASS  ㊺ 방어선 생존 — DB 룰 1행을 어긋나게 하면 MCP↔REST 대조가 **실제로 FAIL** 한다                                        변경 1행 · 검출된 불일치 3건 ['AST-L2-SPDL/SALE: MCP=CONDITIONAL vs REST=INSUFFICIENT_FACTS', 'AST-L3-LIFT/SALE: MCP=CONDITIONAL vs REST=INSUFFICIENT_FACTS']
  PASS  ㊻ REST 가 복제한 not_considered·disclaimer 가 엔진과 동일 (W2 드리프트 감시)                                    not_considered 일치=True disclaimer 일치=True
  PASS  ㊼ 예외 무누출 — 도구 7종 × 타입 오류 입력(optional 파라미터 포함)                                                   호출 207회 · 누출 0건 []
  PASS  ㊽ verify_ownership — facts 접근자: 목록 밖 거부 · 사실 키/파생 키 허용 (B-1 구조 방어)                              밖 거부=True · 파생 허용=True · 안 정상=True
  PASS  ㊾ 실 DB(공유 Postgres) 불변 (assets 행수) — 읽기 전용 커넥션만 (D10)                                           assets=9
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (49건) — 도구 7종 · D9·D46(status 반환)·D62(모른다≠통과)·D64(OEE 금지)·D65·D78·D79 준수 · B-1 회귀 · MCP↔REST 대조와 그 방어선 생존 확인 포함
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/tools_profile_contract.py
도구 프로파일 계약 — D69 게이트 · D80 required · D9 타입 폭 (임시 DB 사본)

───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① full 프로파일 → 도구 20종 (코어 7 + 확장 13, 집합 동일)                                               20종 · 누락=없음 · 초과=없음
  PASS  ② D80 — 필수 파라미터가 스키마 required 로 노출 (기본값을 두면 optional 이 된다)                               classify_expenditure 3종 · assess_repair_value 3종 · generate_disposal_document reason 일치
  PASS  ③ D81·D23 — override·override_reason·reviewed_by·requested_by·session_id 가 전 도구 스키마에 부재  누출=없음 · 검사 대상 20종
  PASS  ④ D9 — 숫자 파라미터가 int|str 유니온으로 남아 있다 (좁히면 status 를 못 돌려준다)                                amount·repair_cost·window_months·cost·downtime_hours 전부 유니온
  PASS  ⑤ 확장 13종 description 존재 · disposal_date 파라미터에 유도 문구 (S9·S10 데모 방어)                       빈 description=없음 · disposal_date 설명={'check_disposal_blockers': True, 'build_evidence_bundle': True, 'generate_disposal_document': True}
  PASS  ⑥ core 프로파일 → 정확히 7종 · 확장 도구 0종 누출 (기본값이 core 인 이유 = 평가 오염 방지)                           7종 · 누출=없음
  PASS  ⑦ enum 밖 프로파일 → exit code ≠ 0 (폴백 금지 · 어느 프로파일로 돌았는지 모르는 상태를 만들지 않는다)                    exit=1 · 메시지에 키 이름 포함=True
───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (7건) — D69 프로파일 게이트 양방향 · D80 required · D9 타입 폭 확인
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/bundle_integrity.py
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① 같은 입력 2회 → bundle_hash 동일 (멱등)                                                                    status=ok/ok hash=sha256:680ee9a0a0b1232…
  PASS  ② built_at 만 다른 두 응답 → bundle_hash 동일 (built_at 은 번들 밖)                                             built_at 2020-01-01T00:00:00Z vs 2031-12-31T23:59:59Z · hash 동일=True
  PASS  ③ W6 — 룰 본문 1글자 변경(rule_version 동일) → rule_hash·bundle_hash 변경                                      변경 1행 · v2 sha256:9d2502eb62a… → sha256:b4a13cabfd2…
  PASS  ④ W6 — 메타(revision_note·authored_by·reviewed_at) 변경은 rule_hash 불변 · 본문은 변경                          메타 불변=True · 본문 변경=True
  PASS  ⑤ W7 — CLEAR 자산(laws·rules 빈 배열)도 evaluated[] 가 비지 않는다                                              verdict=CLEAR laws=0 rules=0 evaluated=5(룰 5종)
  PASS  ⑥ 계약 근거 — contracts[] 전 항목이 hash_fixed:false · text_hash:null · note 동반                             ['근저당권설정계약서', '여신거래기본약관']
  PASS  ⑦ 계약 근거 — 조문 0건 수집 상태에서도 contract_refs 만으로 번들 성공 (검사 대상 아님)                                         status=ok reason=- contracts=['A약관', 'Z약관']
  PASS  ⑧ 리스트 4종 명시 정렬 (laws→law_ref_id · rules·evaluated→(rule_id,rule_version) · contracts→contract_ref)  laws 3 rules 3 evaluated 5 contracts 2 (전부 ≥2 여야 검사가 유효)
  PASS  ⑨ W5 — 번들의 text_hash 가 판정에 **주입된 laws 객체**에서 나온다 (재로드 아님)                                           status=ok text_hash=['sha256:5e14e1KR-CIVI', 'sha256:5e14e1KR-KCC-', 'sha256:5e14e1KR-VAT-']
  PASS  ⑩ N1 — 전각/연속 공백 변형은 바이트가 달라도 같은 해시 (hash_spec 이 뜻하는 바)                                              직렬화 다름=True · 해시 동일=True
  PASS  ⑪ N2 — 판정 직후 자산 행 UPDATE → error/asset_modified (스냅샷을 조용히 서명하지 않는다)                                 UPDATE [1]행 · status=error reason=asset_modified
  PASS  ⑫ N2 — 판정 직후 자산 행 DELETE → error/asset_disappeared                                                  DELETE [1]행 · status=error reason=asset_disappeared
  PASS  ⑬ N1·D83 — hash_spec 은 번들 밖 · evidence_bundle 은 정확히 5키 · 해시 대상은 번들뿐                                 hash_spec=sha256/nfkc-ws/canonical-json-v1 번들키=['contracts', 'evaluated', 'facts', 'laws', 'rules']
  PASS  ⑭ D10 — decisions 행 수 불변 (이 도구에는 쓰기 커넥션이 없다)                                                        0 → 0행
  PASS  ⑮ D83 — evaluated[] 항목은 {rule_id,rule_version,verdict,law_refs} 뿐 (text_hash 없음)                    키집합=[['law_refs', 'rule_id', 'rule_version', 'verdict']]
  PASS  ⑯ 실 DB — KR-CITA-ENF-31 미수집 상태에서도 AST-L2-SPDL SALE 번들 성공 (인용 없음)                                    실 DB status=ok(KR-CITA-ENF-31=FETCHED) · 강제 미수집 사본 status=ok
  PASS  ⑰ 미수집 조문 인용 → error/law_text_unavailable + missing_law_refs (경로 생존)                                 reason=law_text_unavailable missing=['KR-VAT-32']
  PASS  ⑱ W5 — 번들 facts 가 판정의 facts_used 와 **같은 객체** (값만 같은 재조립본이 아니다)                                      동일 객체=True · facts 키 14개
  PASS  ⑲ W5 회귀 차단 — build_evidence_bundle 이 check_disposal_blockers 도구를 import 하지 않는다                      import 문 없음 · 자식 프로세스 sys.modules=CLEAN
  PASS  ⑳ 두 도구의 status·reason 어휘 일치 — 자산 해석·입력 검증 8케이스 직접 대조                                                8케이스 일치
  PASS  ㉑ 실패 응답도 계약 밖 키를 늘리지 않는다 (공용 err(**extra) 우회 차단)                                                    8케이스 × 2도구 초과 키 0건
  PASS  ㉒ 엔진 예외 어휘 일치 — KeyError·TypeError·ValueError 3종이 두 도구 모두 internal_error                            3종 × 2도구 전부 error/internal_error (engine_error 는 계약 위반 전용)
  PASS  ㉓ 두 도구의 성공 경로 verdict 일치 — 파일 정본 판정 == DB 사본 판정 (10조합)                                              10조합 일치
  PASS  ㉔ 실 DB 사본 == 파일 정본 (본문·해시까지 · 재시드 누락 감지) — 서명이 폐지 원문에 걸리는 것을 막는다                                    laws 불일치=없음 rules 불일치=없음 (파일 8·5 / DB 8·5)
  PASS  ㉕ 실 DB(public) decisions 행수 불변 — 픽스처는 전부 격리 스키마 사본이었다 (D10)                                         decisions 0→0행
  PASS  ㉖ 격리 스키마 잔존 확인 — 이 실행이 만든 스키마 전부 drop_isolated_schema 로 정리됨                                         생성 7개 · 잔존 없음
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (26건) — W5(원천 일원화·주입)·W6(rule_hash)·W7(evaluated)·계약 근거·N1(hash_spec)·N2(asset_modified) · D9·D10·D62·D82·D83 준수
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/approvals_contract.py
통합 승인 큐 · 처분 서명 REST 계약 (임시 DB 사본)

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① /api/approvals?state=pending 이 po·disposal 양쪽을 담는다                                    200 · 8건 · kind 분포={'disposal': 5, 'po': 3}
  PASS  ② kind 필터 동작 (po / disposal)                                                            po=5건 · disposal=6건
  PASS  ③ kind=repair → 200·REST 건수 == repair_records 실측 건수 (양성 축) · kind 밖 값 → 422 (음성 축)      repair=12(분포={'draft': 1, 'signed': 11}) · REST=12건 · kinds=3 · kind=nope→422
  PASS  ④ state 가 원 어휘 그대로 (approved ≠ signed, 정규화 금지)                                          po=['approved', 'pending', 'rejected'] · disposal=['draft', 'pending']
  PASS  ⑤ urgency 가 처분서에서 null · verdict 가 발주에서 null (지어내지 않는다)                                 disposal.urgency=None/verdict='BLOCKED' · po.verdict=None/requires_override=None
  PASS  ⑥ 모든 detail_path 가 실제 200                                                               23개 경로 · 비200=없음
  PASS  ⑦ 정비사 submit → 200 · draft→pending · requested_by stamp (D23·D37)                       200 state=pending requested_by=tech-01
  PASS  ⑧ 403 대칭 — 팀장 submit → 403 · 정비사 sign → 403                                             manager submit=403 · technician sign=403
  PASS  ⑨ 팀장 sign → 200 · signed · verdict_at_signing 이 재산출 값                                   200 state=signed verdict=CLEAR
  PASS  ⑩ 재서명 → 409 · 없는 decision_id → 404 · pending 재submit → 409                              재서명=409(invalid_transition) · 404=404 · 재submit=409
  PASS  ⑪ 반려 — 사유 없으면 422 · 사유 있으면 rejected + 사유 저장                                             사유없음=422 · 반려=200 note='매각 시점 재검토'
  PASS  ⑫ 정비사 reject → 403                                                                      403 처분 반려 은(는) manager 만 수행할 수 있습니다 (요청자 역할:
  PASS  ⑬ BLOCKED + override 없음 → 409 override_required + blockers·resolve_options              409 override_required verdict=BLOCKED blockers=['LIEN-CONSENT'] resolve=5건
  PASS  ⑭ override=true + 사유 공백/누락 → 422 (D63)                                                  공백=422 · 누락=422
  PASS  ⑮ 자산 UPDATE 주입 → 409 evidence_changed · **순서 잠금**(근거변경+BLOCKED → override_required 아님)  ⓐ policy_id 변경=409/evidence_changed · ⓑ 담보 주입(CLEAR→BLOCKED)=409/evidence_changed · ⓑ+override=409/evidence_changed
  PASS  ⑯ 서명 후 signed_at·reviewed_by non-null · override 서명은 사유와 함께 기록                          override 서명=200 · DEC-S001(signed_at=True, override=False) · DEC-B001(override=True, reason='법무 검토 완료 — 담보권자 동의 별', verdict=BLOCKED)
  PASS  ⑰ 상세에 missing_sections·hash_fixed:false · 증빙 3종 · 서명분만 (D86·12 §11)                     hash_fixed=False · missing=['감가상각 명세 — 상각 스케줄 원천 없음'] · 이력 2건(미서명 누출 0) · 각주 3건 · 핵심부품 1건
  PASS  ⑱ /api/po 응답 키집합 불변 — 통합 큐 도입 무회귀 (D85)                                                 목록 5건 · 키 어긋난 항목=없음 · 상세 키차이=없음
  PASS  ⑲ backend 번들 재산출 == MCP 도구 산출 (해시·본문 동일 — 규약 드리프트 방어)                                   도구=sha256:837eebf2f85db6e53 · backend=sha256:837eebf2f85db6e53 · verdict=BLOCKED
  PASS  ⑳ 증빙 패키지 보전지표 == get_maintenance_metrics (숫자 11 + excluded·disclaimer)                  대조 13필드 · 불일치=없음 · mtbf=5.5일/calendar_days, mttr=4.75h · excluded 2건
  PASS  ㉑ evidence_package.metrics 에 disclaimer·excluded 가 실려 나간다 (D65·D86)                     disclaimer='MTBF 는 가동시간이 아니라 달력 기준 평균 고장 간격이다('… · excluded=2건
  PASS  ㉒ occurred_at 파싱 실패가 excluded 에 고지된다 (조용히 버리지 않는다 — D65)                                N/A — Postgres occurred_at 은 진짜 TIMESTAMP 라 이 값 자체가 INSERT 시점에 거부된다(SQLite 는 타입 강제가 없어 저장된 뒤 앱이 방어했다 — 더 강한 보장으로 대체)
  PASS  ㉓ 직접 SQL 뚫기 2건 → CHECK 거부 · **CHECK 제거 뮤턴트에서는 통과**(방어선 실증)                              ⓐ signed_at 없이 signed: 거부(new row for relation "decisions" violates check constraint ") · ⓑ BLOCKED 를 override=0 으로 signed: 거부(new row for relation "decisions" violates check constraint ") · 뮤턴트 통과=['ⓐ', 'ⓑ']
  PASS  ㉔ 인용 룰 소실 → **409** cited_rule_missing (503 `rule_catalog_invalid` 와 어휘까지 구분)           409 reason=cited_rule_missing missing_rules=['RULE-GHOST-999 v1']
  PASS  ㉕ 룰 카탈로그 0행 → **503** rule_catalog_not_loaded (적재 미완은 재시도 대상)                           503 reason=rule_catalog_not_loaded · rules 복원=5행
  PASS  ㉖ 실 DB(공유 Postgres) decisions 행 수 불변 (사본만 썼다는 증거)                                       (0,) → (0,)
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (26건) — BLOCKING 우회 0건·서명 없는 확정 0건이 REST 순서(D84)와 DB CHECK 양쪽에서 막힌다
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/ownership_api_contract.py
S18 REST 계약 검증 — /ownership · PARTIAL≠409 · REST==MCP · 역할 게이트 없음

────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① 시드 9자산 전부 200 · verdict=PARTIAL                                   9자산 전부 200/PARTIAL
  PASS  ② 카테고리 9종 — 개수·순서가 CATEGORIES 와 동일 (빠진 카테고리 0)                      9종 ('물리적 상태', '가동 이력', '정비 이력')…
  PASS  ③ 항목 총량 38개 — 전 자산 동일 (조용한 축소 감시)                                   [38] · 자산별 [('AST-L1-CONV', 38), ('AST-L2-CLNT', 38)]…
  PASS  ④ VERIFIED→evidence · UNVERIFIED→limit (반대편은 null) — 이유 없는 미확인 0건   결함 0건 []
  PASS  ⑤ REST 응답 == MCP verify_ownership 출력 (9자산 · json sort_keys 동일)      대조 9자산 전부 동일 (판정 원천 1벌 — data/ownership.py)
  PASS  ⑥ 없는 자산 → 404 · reason=unknown_asset (본문에 사유)                       404 unknown_asset AST-NOPE
  PASS  ⑦ INV-L1-01(호스트 자산 없음) → 404 no_host_asset · 본문에 사유 — '문제 없음'이 아니다  404 no_host_asset · message=INV-L1-01 에 연결된 호스트 자산이 없습니다 — 실사 대상이 …
  PASS  ⑧ ★ PARTIAL 이 409 가 아니다 — 실사 미확인은 '해소할 상태'가 아니라 정상 결과 (11 §6)       9자산 상태코드 [200] · 매핑 {'ok': 200, 'not_found': 404, 'error': 500}
  PASS  ⑨ X-Role 무관 — technician·manager·헤더없음이 같은 상태코드·같은 본문 (403 없음, D38)  {'technician': (200, 404, 404), 'manager': (200, 404, 404), '헤더없음': (200, 404, 404)} · 본문 동일=True
  PASS  ⑩ 판정 20+회 호출 후 DB 행 수·assets 지문 불변 (mode=ro 커넥션만)                   before={'assets': 9, 'equipment': 10, 'repair_records': 12, 'error_history': 200, 'decisions': 0, 'assets_fingerprint': 'a77f988dcd1e'} / after={'assets': 9, 'equipment': 10, 'repair_records': 12, 'error_history': 200, 'decisions': 0, 'assets_fingerprint': 'a77f988dcd1e'}
────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (10건) — 200/404 · PARTIAL≠409 · REST==MCP 바이트 대조 · no_host_asset 사유 · 403 없음 · 무저장
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/disposal_sign_contract.py
MQ-708 — BLOCKING 우회 0건 · 서명 없는 확정 0건 전수 회귀 (임시 DB 사본)

[격리] Postgres 격리 스키마 DATABASE_URL = postgresql://postgres:postgres@127.0.0.1:5434/maintq?options=-c%20search_path%3Ddisposal_sign_1787535393_hawpoe%2Cpublic
[격리] 처분 예정일 고정 = 2026-09-01


── 전수 매트릭스 (9자산 × 3모드 = 27조합) ─────────────────────────────
  자산            SALE                                SCRAP                               TRANSFER
  AST-L1-CONV   CONDITIONAL        서명성공             CONDITIONAL        서명성공             CONDITIONAL        서명성공
  AST-L2-CLNT   CONDITIONAL        서명성공             CONDITIONAL        서명성공             CONDITIONAL        서명성공
  AST-L2-SPDL   CONDITIONAL        서명성공             CONDITIONAL        서명성공             CONDITIONAL        서명성공
  AST-L3-CONV   BLOCKED            서명거부             BLOCKED            서명거부             BLOCKED            서명거부
  AST-L3-EXFAN  CONDITIONAL        서명성공             CONDITIONAL        서명성공             CONDITIONAL        서명성공
  AST-L3-LIFT   CONDITIONAL        서명성공             CLEAR              서명성공             CLEAR              서명성공
  AST-L4-CONV   CONDITIONAL        서명성공             CONDITIONAL        서명성공             CONDITIONAL        서명성공
  AST-L4-DUST   INSUFFICIENT_FACTS 서명거부             INSUFFICIENT_FACTS 서명거부             INSUFFICIENT_FACTS 서명거부
  AST-L4-WRAP   CONDITIONAL        서명성공             CONDITIONAL        서명성공             CONDITIONAL        서명성공

  [서명거부 6] [번들불가 0] [서명성공 21]  (미분류 0)  합계 27 / 대상 27조합

HTTP Request: POST http://testserver/api/decisions/DEC-0029/sign "HTTP/1.1 409 Conflict"
HTTP Request: POST http://testserver/api/decisions/DEC-NOPE/sign "HTTP/1.1 404 Not Found"
HTTP Request: POST http://testserver/api/decisions/DEC-0029/sign "HTTP/1.1 403 Forbidden"
HTTP Request: POST http://testserver/api/decisions/DEC-0029/submit "HTTP/1.1 403 Forbidden"
HTTP Request: POST http://testserver/api/decisions/DEC-0001/sign "HTTP/1.1 409 Conflict"
HTTP Request: POST http://testserver/api/decisions/DEC-0001/reject "HTTP/1.1 409 Conflict"
HTTP Request: POST http://testserver/api/decisions/DEC-0030/submit "HTTP/1.1 200 OK"
HTTP Request: POST http://testserver/api/decisions/DEC-0030/sign "HTTP/1.1 422 Unprocessable Content"
HTTP Request: POST http://testserver/api/decisions/DEC-0030/sign "HTTP/1.1 422 Unprocessable Content"
DB 연결 오류: new row for relation "decisions" violates check constraint "decisions_check2"
DETAIL:  Failing row contains (DEC-0030, AST-L3-CONV, DISPOSAL, {"contracts":[{"contract_ref":"근저당권설정계약서","has..., sha256:7c72e50a1df3084c38a0540da738097d55de122e81ed77a401147cbb0..., BLOCKED, f, null, mgr-01, 2026-08-24 01:36:52, signed, AST-L3-CONV/SCRAP 층별 프로브 (MQ-708), tech-01, null, null, 2026-08-24 01:36:52.632854).
HTTP Request: POST http://testserver/api/decisions/DEC-0031/submit "HTTP/1.1 200 OK"
HTTP Request: POST http://testserver/api/decisions/DEC-0031/sign "HTTP/1.1 409 Conflict"
HTTP Request: POST http://testserver/api/decisions/DEC-0031/sign "HTTP/1.1 409 Conflict"
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① 전수 매트릭스 3열 분리 — [서명거부 N][번들불가 M][서명성공 K] · N+M+K == 27                                   N=6 · M=0 · K=21 · 미분류=0 · 대상=27조합
  PASS  ② BLOCKING 우회 0건 — 차단 판정 조합 전부 override 없는 서명이 409 override_required                       차단 조합 6건(['BLOCKED', 'INSUFFICIENT_FACTS']) · 우회 성공 0건 · 층③ 이상 0건 · 409 를 못 받은 조합 0건 (전부 0건)
  PASS  ③ 차단 어휘 3종이 **전부 런타임으로** 차단됐다 (매트릭스는 고정 처분일이라 HOLD 를 못 낸다 — 별도 프로브로 채운다. 기대치는 엔진에서 독립 파생)  기대 차단 어휘 ['BLOCKED', 'HOLD', 'INSUFFICIENT_FACTS'] · 매트릭스 커버 ['BLOCKED', 'INSUFFICIENT_FACTS'] · 미커버 ['HOLD'] → HOLD(AST-L1-CONV/SALE/2023-02-12): 409 → override 200 OK
  PASS  ④ 차단 조합 override 서명 → 200 · override=1 · 사유 저장 (D63 — 막지 않고 기록한다)                          override 서명 7건 / 기대 7건(차단 조합 6 + 커버리지 프로브 1) · 실패=없음
  PASS  ⑤ 위양성 방지 — 비차단 조합은 override 없이 200 (전부 막는 검사가 아님)                                          K=21건 · 실패=없음
  PASS  ⑥ 모든 조합의 draft 가 override=0 · state='draft' 로 생성 (D81 — 도구는 예외를 만들 수 없다)                   위반=없음 · 생성된 decisions 28건
  PASS  ⑦ D63 — 차단 판정 조합도 draft 가 전부 생성된다 (시스템은 막지 않고 기록한다)                                        차단 조합 6건 중 draft 생성 6건 (['AST-L3-CONV/SALE', 'AST-L3-CONV/SCRAP', 'AST-L3-CONV/TRANSFER', 'AST-L4-DUST/SALE', 'AST-L4-DUST/SCRAP', 'AST-L4-DUST/TRANSFER'])
  PASS  ⑧ 서명 전후 bundle_hash 불변 — 서명이 근거를 갈아치우지 않는다 (D84)                                           해시 변동 0건 · 대조한 조합 27건
  PASS  ⑨ 층② 전제 — 도구가 decision_writer 로 쓴다 (draft_writer 재사용 = 잠금 없는 쓰기)                           with decision_writer()=True · with draft_writer(=False
  PASS  ⑩ 번들불가 M 이 인용 조문 수집 상태와 정합 (미수집 0건 ⇒ M==0 · 단방향)                                           M=0 · 최신 버전 룰이 인용한 조문 7건 중 미수집=없음
  PASS  ⑪ 층① 도구 스키마·함수 시그니처 어디에도 override/override_reason/reviewed_by 없음 (D81)                     도구 등록=True · 스키마 키=['asset_id', 'disposal_date', 'disposal_mode', 'equipment_id', 'reason'] · 시그니처=['asset_id', 'disposal_date', 'disposal_mode', 'equipment_id', 'reason'] · 금지 키 노출=없음
  PASS  ⑫ 층② decision_writer 의 UPDATE·DELETE 가 TRIGGER 로 ABORT — **문구까지 대조** (D10)                 UPDATE(state='pending'): 거부(MCP 도구는 decisions 를 수정/삭제할 수 없습니다 (D10, op=UPDATE) C) · DELETE: 거부(MCP 도구는 decisions 를 수정/삭제할 수 없습니다 (D10, op=DELETE) C)
  PASS  ⑬ 층② 대조군 — 같은 UPDATE 가 일반 커넥션에서는 **성공** (거부 원인이 트리거임을 실증)                                  일반 커넥션: 통과 — 트리거가 유일한 차단자
  PASS  ⑭ 층② INSERT 는 통과 — 커넥션이 통째로 막힌 게 아니라 UPDATE/DELETE 만 잠겼다                                   DEC-0029 존재 · decisions 총 29행
  PASS  ⑮ 층③ draft 서명 → 409 invalid_transition · 없는 id → 404 · 403 양방향 (D38)                       draft sign=409(invalid_transition) · 404=404 · technician sign=403 · manager submit=403
  PASS  ⑯ 층③ 서명된 건 재서명·반려 → 409 (확정 이후 상태를 되돌리지 않는다)                                               재서명=409(invalid_transition) · 반려=409(invalid_transition)
  PASS  ⑰ 층③ override=true + 사유 공백/누락 → 422 (409 가 아니다 — D38 이 나눈 코드)                              공백=422 · 누락=422 · 행 상태=pending
  PASS  ⑱ **층 독립성** — 층③ 게이트를 죽여도 층④ CHECK 가 BLOCKED 서명을 막는다                                       예외=IntegrityError · 메시지=new row for relation "decisions" violates check constraint "decisions_ · 서명 후 상태=pending
  PASS  ⑲ 순서 잠금 (D84) — 근거 변경 + BLOCKED 는 override=true 로도 409 evidence_changed                    override 없음=409/evidence_changed · override=true=409/evidence_changed
  PASS  ⑳ 층④ 직접 SQL 3건 전부 CHECK 거부 — **어느 CHECK 인지 제약식 문구로 확인**                                    ⓐ 서명 요소 없이 signed: 거부/문구일치 · ⓑ BLOCKED 를 override=0 으로 signed: 거부/문구일치 · ⓒ 사유 없는 override: 거부/문구일치
  PASS  ㉑ 층④ 대조군 — CHECK 를 벗긴 뮤턴트 테이블에서는 **같은 SQL 3건이 전부 통과**                                      CHECK 제거 확인=True · 뮤턴트에서 통과한 SQL=3/3
  PASS  ㉒ 불변식 — state='signed' 전 행에 signed_at·reviewed_by(users FK)·bundle_hash 존재 (D41)           signed 28행 · 위반 0행
  PASS  ㉓ 불변식 — 차단 판정 서명은 전부 override=1 이고 사유가 비어 있지 않다 (BLOCKING 우회 0건)                           우회 서명 0행 · 사유 없는 override 0행 · override 서명 7행
  PASS  ㉔ 불변식 비공허성 — 27조합 중 서명 완료가 실제로 존재하고 차단·비차단 양쪽이 섞여 있다                                       signed 28행 (차단 override 서명 6 + 비차단 서명 21 이상) · pending 2행
  PASS  ㉕ 캐치올 — 셀·프로브 실패 0건 (분류 문구가 바뀌어도 실패가 새지 않는다)                                               누적 실패 0건
  PASS  ㉖ 실 DB 오염 0 — 공유 Postgres decisions 행 수 불변                                                 decisions 0 → 0행
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (26건) — 27조합 전수에서 BLOCKING 우회 0건 · 서명 없는 확정 0건, 4층이 각각 독립으로 막는다
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/s10_smoke.py
MQ-708 — S9→S10 관통 스모크 (실 uvicorn + 실 MCP stdio · full 프로파일)

[실 DB] public.decisions=0행 (읽기만 한다)
[격리] 자식 DATABASE_URL = postgresql://postgres:postgres@127.0.0.1:5434/maintq?options=-c%20search_path%3Ds10_smoke_1787535415_sucsty%2Cpublic
[격리] MAINTQ_TOOLS_PROFILE = full · 포트 8087

─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① 실 uvicorn 서버 기동 · /health 200 · MCP 세션 ready                                         health={'status': 'ok', 'mcp': True, 'tools': 20, 'tools_profile': 'full'}
  PASS  ② 서버 MCP 가 full 프로파일로 떴다 — 확장 13종 포함 20종 (D69·D98)                                     tools=20 (기대 20) · tools_profile='full'
  PASS  ③ 실 MCP stdio 서버 기동 · generate_disposal_document·check_disposal_blockers 등록            start=True(-) · 도구 20종 · 처분 도구 존재=True
  PASS  ④ [비차단] precheck AST-L3-LIFT/SCRAP → 200 · verdict CLEAR|CONDITIONAL (D71)             200 verdict=CLEAR · 선결 0건
  PASS  ⑤ [비차단] MCP generate_disposal_document → status ok · state=draft · override=false      status=ok/- decision_id=DEC-0001 state=draft override=False
  PASS  ⑥ [비차단] submit(technician) → 200 · state=pending · requested_by stamp                  200 state=pending requested_by=tech-01
  PASS  ⑦ [비차단] /api/approvals?state=pending 에 kind=disposal 로 보이고 detail_path 가 200           큐 4건 · 내 건=있음 kind=disposal · detail=200
  PASS  ⑧ [비차단] GET /api/decisions/{id} — 문서 3종 · missing_sections · hash_fixed:false (D86)    문서 키=['approval', 'evidence_package', 'representation_warranty'] · hash_fixed=False · missing=['감가상각 명세 — 상각 스케줄 원천 없음']
  PASS  ⑨ [비차단] sign(manager) → 200 · state=signed · signed_at·reviewed_by non-null · 해시 불변    200 state=signed signed_at=True reviewed_by=mgr-01 override=False 해시불변=True
  PASS  ⑩ [차단] precheck AST-L3-CONV/SALE → 409 · verdict=BLOCKED · blockers 동봉                 409 verdict=BLOCKED blockers=['LIEN-CONSENT']
  PASS  ⑪ [차단] BLOCKED 여도 draft 는 생성된다 (D63 — 막지 않고 차단 사실을 기록한다) · override=false              status=ok/- decision_id=DEC-0002 verdict=BLOCKED override=False
  PASS  ⑫ [차단] sign(override 없음) → 409 override_required + blockers·resolve_options (D63·D38)  409 reason=override_required verdict=BLOCKED blockers=1건 resolve=5건
  PASS  ⑬ [차단] 403 양방향 — technician sign 403 · manager submit 403 (권한과 상태를 섞지 않는다)             technician sign=403 · manager submit=403
  PASS  ⑭ [차단] sign(override=true + 사유) → 200 · override=1 · 사유·서명자·BLOCKED 판정 기록              200 state=signed override=True verdict=BLOCKED reason='법무 검토 완료 — 담보권자 동의 별건 확보'
  PASS  ⑮ 스모크가 남긴 signed 행 불변식 — 서명 3요소 존재 · 차단 판정은 override=1 (공허하지 않음)                       signed 2행 · 위반 0행
  PASS  ⑯ 서버 로그에 cancel scope·Traceback 없음 (D42 — 조기 종료가 세션을 오염시키지 않는다)                        깨끗함
  PASS  ⑰ 실 DB 오염 0 — public.decisions 행 수 불변 (격리 스키마로 격리, mtime·size 는 Postgres 무관)           decisions 0 → 0행
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (17건) — 실 서버·실 MCP 로 비차단·차단 두 경로를 완주했고, 차단 경로는 override 없이는 확정되지 않았다
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/ui_honesty_contract.py
UI 정직성 회귀 (D87) — 미확인이 확인처럼 보이는 경로가 코드에 없는지

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  IMPORT_SPEC 오라클 — 4개 문법(from·부수효과·require·동적 import)을 실제로 추출한다 (C1~C8 은 부재 검사라 이 오라클이 없으면 정규식이 죽어도 통과한다)              픽스처 추출 4건 ['@/lib/ownership', 'react', 'react-dom', 'react/jsx-runtime'] · 기대 ['@/lib/ownership', 'react', 'react-dom', 'react/jsx-runtime']
  PASS  C1 lib/ownership.ts 가 React 를 들여오지 않는다                                                                                import 대상 0개 (없음) · react 계열 0건
  PASS  C2 lib/ownership.ts 가 `@/` 경로 별칭을 쓰지 않는다 (단독 tsc 컴파일 가능)                                                              별칭 import 0건 · 따옴표 뒤 '@/' 0건 (주석 언급은 세지 않는다)
  PASS  C3 lib/maintValue.ts 가 React 를 들여오지 않는다 (MQ-917)                                                                      import 대상 0개 (없음) · react 계열 0건
  PASS  C4 lib/maintValue.ts 가 `@/` 경로 별칭을 쓰지 않는다 (단독 tsc 컴파일 가능) (MQ-917)                                                    별칭 import 0건 · 따옴표 뒤 '@/' 0건 (주석 언급은 세지 않는다)
  PASS  C5 lib/deadlines.ts 가 React 를 들여오지 않는다 (MQ-1202)                                                                      import 대상 0개 (없음) · react 계열 0건
  PASS  C6 lib/deadlines.ts 가 `@/` 경로 별칭을 쓰지 않는다 (단독 tsc 컴파일 가능) (MQ-1202)                                                    별칭 import 0건 · 따옴표 뒤 '@/' 0건 (주석 언급은 세지 않는다)
  PASS  C7 lib/riskGrade.ts 가 React 를 들여오지 않는다 (MQ-1202)                                                                      import 대상 0개 (없음) · react 계열 0건
  PASS  C8 lib/riskGrade.ts 가 `@/` 경로 별칭을 쓰지 않는다 (단독 tsc 컴파일 가능) (MQ-1202)                                                    별칭 import 0건 · 따옴표 뒤 '@/' 0건 (주석 언급은 세지 않는다)
  PASS  C9 lib/a2a.ts 가 React 를 들여오지 않는다 (MQ-1605)                                                                            import 대상 0개 (없음) · react 계열 0건
  PASS  C10 lib/a2a.ts 가 `@/` 경로 별칭을 쓰지 않는다 (단독 tsc 컴파일 가능) (MQ-1605)                                                         별칭 import 0건 · 따옴표 뒤 '@/' 0건 (주석 언급은 세지 않는다)
  PASS  L1-1 ITEM_VIEW total(2키) · UNVERIFIED.tone !== 'ok'                                                                   keys=[UNVERIFIED,VERIFIED] VERIFIED=ok UNVERIFIED=warn
  PASS  L1-2 itemView 맵 안 값 — VERIFIED='확인됨'/ok · UNVERIFIED='미확인'/warn                                                       VERIFIED={확인됨,ok} UNVERIFIED={미확인,warn}
  PASS  L1-3 itemView 맵 밖 값 6종 — 전용 unknown 톤 + 원문 보존 (초록·정상경고 어느 쪽도 아니다)                                                     검사 6종 · 예: itemView("PENDING")=미확인 (PENDING) tone=unknown
  PASS  L1-4 VERDICT_VIEW.PARTIAL — warn + '안전하다는 뜻이 아닙니다' · 미지 판정은 전용 unknown 톤 + 원문                                         PARTIAL=warn:"확인되지 않은 항목이 남아 있습니다 — 안전하다는 뜻이 아닙니다" · 미지=unknown:"판정 미상 (MOSTLY_VERIFIED) — 확인됐다는 뜻이 아닙니다"
  PASS  L1-5 CATEGORIES — 하드코딩 9종과 개수·순서 동일 (04 §9)                                                                           9종 [물리적 상태, 가동 이력, 정비 이력…]
  PASS  L1-6 toRows — 항목 0건 카테고리도 행을 남긴다 (9카테고리 전부 · 순서 유지)                                                                   카테고리 9종 · 빠짐 0건 · 0건 카테고리 행 1건 (정비 이력/tone=warn)
  PASS  L1-7 미지 state 는 tone='ok' 가 되지 않는다 · summarize 는 'N/M 확인됨' (퍼센트·진행바 없음)                                               미지 state 2건 · 초록 누수 0건 · summary="8/19 확인됨"
  PASS  L1-8 auditRows — 정상 입력은 위반 0건 · 불변식 4종 위반을 각각 잡는다                                                                     정상 위반 0건 · 못 잡은 뮤턴트 0건
  PASS  L1-9 stateView — 맵 밖 (kind,state) 5종이 tone='ok' 로 떨어지지 않는다 (known=false + 원문)                                         검사 5종 전부 warn/known=false · 대조군 po/approved=ok
  PASS  L1-10 showMetric(null) — '0'·''·'양호' 어느 것도 반환하지 않는다 (D62)                                                             text="판단 근거 부족" kind=insufficient
  PASS  L1-11 showTrend('insufficient_data') — kind='insufficient' · null(미산출)과는 다른 kind                                      insufficient_data→text="판단 근거 부족" kind=insufficient · null→kind=unknown
  PASS  L1-12 isHoldVerdict('HOLD')===true · 에러/타 판정 문자열은 HOLD 로 오분류되지 않는다                                                    HOLD=true · 오분류 0건
  PASS  L1-13 estimateNotice — source 있으면 반드시 문자열(고지 누락 불가) · source 없으면 지어내지 않는다                                             source 있음="이 값은 법정 기준내용연수 기반 목업 잔가곡선(D74) 기반 추정치이며 실거래가·실측값이 아닙니다 (D65·D74)." · source 없음=null(정상)
  PASS  L1-14 deadlineStateView — 맵 밖 값 4종은 unknown+원문 · OVERDUE(error) ≠ IN_REVIEW_BAND(warn) 톤                              UPCOMING=warn IN_REVIEW_BAND=warn OVERDUE=error · 맵 밖 4종 전부 unknown+원문
  PASS  L1-15 gradeView(null) — LOW/ok 로 오분류되지 않는다(D62) · 맵 밖 값 4종은 unknown+원문                                                null→{미산출,unknown} LOW→{낮음,ok} · 맵 밖 4종 전부 unknown+원문
  PASS  L1 건수 15건 (줄었으면 단언이 사라진 것이다 — MQ-917 이 maintValue.ts 4건을 더했고, Sprint 12 MQ-1202 가 deadlines.ts·riskGrade.ts 2건을 더했다)  15건 · node exit=0
  PASS  L2 스캔 대상 42개 (하한 42 — 줄면 파일이 빠진 것이다)                                                                                  layout.tsx · page.tsx · page.tsx · page.tsx · page.tsx · page.tsx · page.tsx · page.tsx · page.tsx · page.tsx · page.tsx · page.tsx · page.tsx · page.tsx · page.tsx · page.tsx · page.tsx · page.tsx ·
  PASS  L2-1.1 layout.tsx — "확인됨" 문자열 리터럴 0건                                                                                  적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-1.2 layout.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-1.3 layout.tsx — `--green`·`--ok` 색 토큰 0건                                                                          적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-1.4 layout.tsx — `state ===` 상태 비교 0건                                                                              적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-1.5 layout.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                             적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-1.6 layout.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                           적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-2.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                    적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-2.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                  적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-2.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                            적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-2.4 page.tsx — `state ===` 상태 비교 0건                                                                                적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-2.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                               적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-2.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                             적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-3.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                    적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-3.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                  적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-3.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                            적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-3.4 page.tsx — `state ===` 상태 비교 0건                                                                                적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-3.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                               적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-3.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                             적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-4.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                    적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-4.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                  적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-4.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                            적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-4.4 page.tsx — `state ===` 상태 비교 0건                                                                                적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-4.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                               적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-4.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                             적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-5.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                    적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-5.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                  적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-5.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                            적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-5.4 page.tsx — `state ===` 상태 비교 0건                                                                                적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-5.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                               적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-5.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                             적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-6.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                    적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-6.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                  적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-6.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                            적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-6.4 page.tsx — `state ===` 상태 비교 0건                                                                                적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-6.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                               적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-6.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                             적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-7.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                    적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-7.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                  적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-7.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                            적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-7.4 page.tsx — `state ===` 상태 비교 0건                                                                                적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-7.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                               적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-7.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                             적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-8.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                    적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-8.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                  적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-8.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                            적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-8.4 page.tsx — `state ===` 상태 비교 0건                                                                                적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-8.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                               적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-8.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                             적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-9.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                    적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-9.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                  적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-9.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                            적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-9.4 page.tsx — `state ===` 상태 비교 0건                                                                                적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-9.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                               적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-9.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                             적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-10.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                   적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-10.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                 적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-10.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                           적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-10.4 page.tsx — `state ===` 상태 비교 0건                                                                               적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-10.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                              적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-10.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                            적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-11.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                   적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-11.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                 적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-11.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                           적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-11.4 page.tsx — `state ===` 상태 비교 0건                                                                               적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-11.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                              적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-11.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                            적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-12.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                   적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-12.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                 적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-12.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                           적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-12.4 page.tsx — `state ===` 상태 비교 0건                                                                               적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-12.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                              적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-12.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                            적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-13.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                   적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-13.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                 적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-13.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                           적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-13.4 page.tsx — `state ===` 상태 비교 0건                                                                               적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-13.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                              적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-13.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                            적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-14.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                   적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-14.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                 적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-14.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                           적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-14.4 page.tsx — `state ===` 상태 비교 0건                                                                               적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-14.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                              적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-14.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                            적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-15.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                   적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-15.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                 적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-15.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                           적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-15.4 page.tsx — `state ===` 상태 비교 0건                                                                               적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-15.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                              적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-15.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                            적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-16.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                   적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-16.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                 적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-16.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                           적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-16.4 page.tsx — `state ===` 상태 비교 0건                                                                               적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-16.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                              적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-16.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                            적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-17.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                   적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-17.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                 적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-17.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                           적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-17.4 page.tsx — `state ===` 상태 비교 0건                                                                               적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-17.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                              적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-17.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                            적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-18.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                   적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-18.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                 적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-18.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                           적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-18.4 page.tsx — `state ===` 상태 비교 0건                                                                               적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-18.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                              적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-18.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                            적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-19.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                   적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-19.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                 적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-19.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                           적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-19.4 page.tsx — `state ===` 상태 비교 0건                                                                               적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-19.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                              적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-19.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                            적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-20.1 page.tsx — "확인됨" 문자열 리터럴 0건                                                                                   적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-20.2 page.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                                 적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-20.3 page.tsx — `--green`·`--ok` 색 토큰 0건                                                                           적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-20.4 page.tsx — `state ===` 상태 비교 0건                                                                               적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-20.5 page.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                              적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-20.6 page.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                            적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-21.1 AssetHeader.tsx — "확인됨" 문자열 리터럴 0건                                                                            적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-21.2 AssetHeader.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                          적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-21.3 AssetHeader.tsx — `--green`·`--ok` 색 토큰 0건                                                                    적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-21.4 AssetHeader.tsx — `state ===` 상태 비교 0건                                                                        적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-21.5 AssetHeader.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                       적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-21.6 AssetHeader.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                     적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-22.1 CriticalityDrawer.tsx — "확인됨" 문자열 리터럴 0건                                                                      적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-22.2 CriticalityDrawer.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                    적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-22.3 CriticalityDrawer.tsx — `--green`·`--ok` 색 토큰 0건                                                              적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-22.4 CriticalityDrawer.tsx — `state ===` 상태 비교 0건                                                                  적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-22.5 CriticalityDrawer.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                 적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-22.6 CriticalityDrawer.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                               적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-23.1 DeadlinesPanel.tsx — "확인됨" 문자열 리터럴 0건                                                                         적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-23.2 DeadlinesPanel.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                       적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-23.3 DeadlinesPanel.tsx — `--green`·`--ok` 색 토큰 0건                                                                 적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-23.4 DeadlinesPanel.tsx — `state ===` 상태 비교 0건                                                                     적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-23.5 DeadlinesPanel.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                    적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-23.6 DeadlinesPanel.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                  적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-24.1 DisposalPanel.tsx — "확인됨" 문자열 리터럴 0건                                                                          적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-24.2 DisposalPanel.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                        적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-24.3 DisposalPanel.tsx — `--green`·`--ok` 색 토큰 0건                                                                  적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-24.4 DisposalPanel.tsx — `state ===` 상태 비교 0건                                                                      적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-24.5 DisposalPanel.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                     적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-24.6 DisposalPanel.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                   적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-25.1 EquipmentHotspotDiagram.tsx — "확인됨" 문자열 리터럴 0건                                                                적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-25.2 EquipmentHotspotDiagram.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                              적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-25.3 EquipmentHotspotDiagram.tsx — `--green`·`--ok` 색 토큰 0건                                                        적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-25.4 EquipmentHotspotDiagram.tsx — `state ===` 상태 비교 0건                                                            적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-25.5 EquipmentHotspotDiagram.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                           적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-25.6 EquipmentHotspotDiagram.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                         적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-26.1 EvidenceBundlePanel.tsx — "확인됨" 문자열 리터럴 0건                                                                    적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-26.2 EvidenceBundlePanel.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                  적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-26.3 EvidenceBundlePanel.tsx — `--green`·`--ok` 색 토큰 0건                                                            적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-26.4 EvidenceBundlePanel.tsx — `state ===` 상태 비교 0건                                                                적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-26.5 EvidenceBundlePanel.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                               적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-26.6 EvidenceBundlePanel.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                             적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-27.1 ExpenditureCard.tsx — "확인됨" 문자열 리터럴 0건                                                                        적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-27.2 ExpenditureCard.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                      적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-27.3 ExpenditureCard.tsx — `--green`·`--ok` 색 토큰 0건                                                                적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-27.4 ExpenditureCard.tsx — `state ===` 상태 비교 0건                                                                    적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-27.5 ExpenditureCard.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                   적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-27.6 ExpenditureCard.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                 적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-28.1 ExpenditureForm.tsx — "확인됨" 문자열 리터럴 0건                                                                        적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-28.2 ExpenditureForm.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                      적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-28.3 ExpenditureForm.tsx — `--green`·`--ok` 색 토큰 0건                                                                적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-28.4 ExpenditureForm.tsx — `state ===` 상태 비교 0건                                                                    적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-28.5 ExpenditureForm.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                   적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-28.6 ExpenditureForm.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                 적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-29.1 FindingList.tsx — "확인됨" 문자열 리터럴 0건                                                                            적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-29.2 FindingList.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                          적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-29.3 FindingList.tsx — `--green`·`--ok` 색 토큰 0건                                                                    적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-29.4 FindingList.tsx — `state ===` 상태 비교 0건                                                                        적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-29.5 FindingList.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                       적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-29.6 FindingList.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                     적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-30.1 InventoryDrawer.tsx — "확인됨" 문자열 리터럴 0건                                                                        적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-30.2 InventoryDrawer.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                      적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-30.3 InventoryDrawer.tsx — `--green`·`--ok` 색 토큰 0건                                                                적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-30.4 InventoryDrawer.tsx — `state ===` 상태 비교 0건                                                                    적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-30.5 InventoryDrawer.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                   적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-30.6 InventoryDrawer.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                 적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-31.1 LoanAssessmentHistory.tsx — "확인됨" 문자열 리터럴 0건                                                                  적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-31.2 LoanAssessmentHistory.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-31.3 LoanAssessmentHistory.tsx — `--green`·`--ok` 색 토큰 0건                                                          적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-31.4 LoanAssessmentHistory.tsx — `state ===` 상태 비교 0건                                                              적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-31.5 LoanAssessmentHistory.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                             적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-31.6 LoanAssessmentHistory.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                           적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-32.1 MetricsAside.tsx — "확인됨" 문자열 리터럴 0건                                                                           적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-32.2 MetricsAside.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                         적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-32.3 MetricsAside.tsx — `--green`·`--ok` 색 토큰 0건                                                                   적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-32.4 MetricsAside.tsx — `state ===` 상태 비교 0건                                                                       적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-32.5 MetricsAside.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                      적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-32.6 MetricsAside.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                    적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-33.1 PoForm.tsx — "확인됨" 문자열 리터럴 0건                                                                                 적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-33.2 PoForm.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                               적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-33.3 PoForm.tsx — `--green`·`--ok` 색 토큰 0건                                                                         적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-33.4 PoForm.tsx — `state ===` 상태 비교 0건                                                                             적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-33.5 PoForm.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                            적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-33.6 PoForm.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                          적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-34.1 RepairValuePanel.tsx — "확인됨" 문자열 리터럴 0건                                                                       적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-34.2 RepairValuePanel.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                     적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-34.3 RepairValuePanel.tsx — `--green`·`--ok` 색 토큰 0건                                                               적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-34.4 RepairValuePanel.tsx — `state ===` 상태 비교 0건                                                                   적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-34.5 RepairValuePanel.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                  적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-34.6 RepairValuePanel.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-35.1 ResidualRiskCard.tsx — "확인됨" 문자열 리터럴 0건                                                                       적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-35.2 ResidualRiskCard.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                     적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-35.3 ResidualRiskCard.tsx — `--green`·`--ok` 색 토큰 0건                                                               적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-35.4 ResidualRiskCard.tsx — `state ===` 상태 비교 0건                                                                   적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-35.5 ResidualRiskCard.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                  적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-35.6 ResidualRiskCard.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-36.1 RiskGradeGrid.tsx — "확인됨" 문자열 리터럴 0건                                                                          적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-36.2 RiskGradeGrid.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                        적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-36.3 RiskGradeGrid.tsx — `--green`·`--ok` 색 토큰 0건                                                                  적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-36.4 RiskGradeGrid.tsx — `state ===` 상태 비교 0건                                                                      적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-36.5 RiskGradeGrid.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                     적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-36.6 RiskGradeGrid.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                   적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-37.1 VerificationMatrix.tsx — "확인됨" 문자열 리터럴 0건                                                                     적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-37.2 VerificationMatrix.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                   적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-37.3 VerificationMatrix.tsx — `--green`·`--ok` 색 토큰 0건                                                             적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-37.4 VerificationMatrix.tsx — `state ===` 상태 비교 0건                                                                 적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-37.5 VerificationMatrix.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-37.6 VerificationMatrix.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                              적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-38.1 DecisionBar.tsx — "확인됨" 문자열 리터럴 0건                                                                            적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-38.2 DecisionBar.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                          적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-38.3 DecisionBar.tsx — `--green`·`--ok` 색 토큰 0건                                                                    적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-38.4 DecisionBar.tsx — `state ===` 상태 비교 0건                                                                        적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-38.5 DecisionBar.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                       적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-38.6 DecisionBar.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                     적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-39.1 DecisionDetail.tsx — "확인됨" 문자열 리터럴 0건                                                                         적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-39.2 DecisionDetail.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                       적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-39.3 DecisionDetail.tsx — `--green`·`--ok` 색 토큰 0건                                                                 적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-39.4 DecisionDetail.tsx — `state ===` 상태 비교 0건                                                                     적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-39.5 DecisionDetail.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                    적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-39.6 DecisionDetail.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                  적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-40.1 RepairDetail.tsx — "확인됨" 문자열 리터럴 0건                                                                           적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-40.2 RepairDetail.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                         적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-40.3 RepairDetail.tsx — `--green`·`--ok` 색 토큰 0건                                                                   적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-40.4 RepairDetail.tsx — `state ===` 상태 비교 0건                                                                       적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-40.5 RepairDetail.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                      적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-40.6 RepairDetail.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                    적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-41.1 SignBar.tsx — "확인됨" 문자열 리터럴 0건                                                                                적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-41.2 SignBar.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                              적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-41.3 SignBar.tsx — `--green`·`--ok` 색 토큰 0건                                                                        적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-41.4 SignBar.tsx — `state ===` 상태 비교 0건                                                                            적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-41.5 SignBar.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                                           적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-41.6 SignBar.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                                         적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  L2-42.1 WithdrawalStatusPanel.tsx — "확인됨" 문자열 리터럴 0건                                                                  적발 0건 · 컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다
  PASS  L2-42.2 WithdrawalStatusPanel.tsx — "VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건                                                적발 0건 · 컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)
  PASS  L2-42.3 WithdrawalStatusPanel.tsx — `--green`·`--ok` 색 토큰 0건                                                          적발 0건 · 색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다
  PASS  L2-42.4 WithdrawalStatusPanel.tsx — `state ===` 상태 비교 0건                                                              적발 0건 · 컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다
  PASS  L2-42.5 WithdrawalStatusPanel.tsx — 상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)                                             적발 0건 · 어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다
  PASS  L2-42.6 WithdrawalStatusPanel.tsx — 상태·판정 어휘를 키로 쓰는 지역 맵 0건                                                           적발 0건 · 같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')
  PASS  D64 — `OEE`·`종합효율`·`성능가동률` 0건 + 양성 축(스캔 파일>0 · 다른 지표 문자열 실재)                                                          금지어 적발 0건 · 스캔 파일 42개 · 지표 문자열 적중 17건 (3개 파일: DecisionDetail.tsx, MetricsAside.tsx, RepairValuePanel.tsx)
  PASS  주석 제거기 — 주석만 지우고 문자열·코드는 남긴다 (손으로 적은 픽스처)                                                                             --ok-bd 1건(기대 1) · state=== 1건(기대 1) · URL보존=예 · 길이보존=예
  PASS  ⓐ ITEM_VIEW.UNVERIFIED.tone → 'ok' 로 바꾸면 L1 이 FAIL 한다                                                                 L1 15건 중 FAIL ['L1-1', 'L1-2', 'L1-6', 'L1-8']
  PASS  ⓑ VerificationMatrix 에 `if (row.state === "UNVERIFIED") return <Green/>` 주입 → L2 FAIL                                 주입=성공 · 적발 규칙 3건 ['"VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건', '`state ===` 상태 비교 0건', '상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)']
  PASS  ⓒ toRows 가 항목 0건 카테고리를 스킵하면 L1 이 FAIL 한다                                                                              L1 15건 중 FAIL ['L1-6', 'L1-8']
  PASS  ⓓ DisposalPanel 에 `if (result.verdict === "CLEAR") return <Green/>` 주입 → L2 FAIL                                      주입=성공 · 적발 규칙 1건 ['상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)']
  PASS  ⓓ' 확대 전 규칙 4종으로는 같은 뮤턴트를 **못 잡는다** (확대가 실효한 이유)                                                                       구 규칙 적발 0건 (없음 — 통과해 버린다)
  PASS  ⓔ 스캔 대상 전 파일에 코드 한 줄(`state === "pending"` + `--ok-bd`) 주입 → 전부 적발                                                    대상 42개 · 눈먼 파일 0건 (주석 제거가 코드까지 지웠다면 여기서 드러난다)
  PASS  ⓕ showMetric(null) → '0' 으로 바꾸면 L1 이 FAIL 한다 (MQ-917)                                                                 L1 15건 중 FAIL ['L1-10']
  PASS  ⓖ RepairValuePanel(Stage 7 신규)에 `verdict === "REPAIR_RECOMMENDED"` 직접비교 주입 → L2 FAIL (MQ-917)                         주입=성공 · 적발 규칙 1건 ['상태·판정 어휘와의 직접 비교 0건 (`=== "CLEAR"` 류)']
  PASS  ⓗ estimateNotice 의 고지 문자열을 지우면(source 있어도 항상 null) L1 이 FAIL 한다 (MQ-917 · D65·D74)                                    L1 15건 중 FAIL ['L1-13']
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

신규 계약 검사 268건 (L1 15 · L2 252 · D64 1) — PASS 268 / FAIL 0
제약 게이트 10건 · 뮤턴트 8종 · 메타 5건 — PASS 23 / FAIL 0

⚠ L3(실 데이터 렌더)은 이 스위트가 검증하지 않는다 — 수동 체크리스트가 유일한 확인 수단이다
   이 스위트가 보는 것: 순수 함수의 상태→표시 변환 · 컴포넌트 소스의 우회 수단 유무.
   보지 않는 것: 브라우저 렌더 결과 · 실 자산 9건의 실제 응답 · 색상 대비 · 스크린샷.

통과 — 계약 268건 + 제약 10 + 뮤턴트 8 + 메타 5
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/a2a_identity_contract.py
A2A 신원 식별 기반층 계약 검증 — D91~D96 (임시 DB 전용)

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① partner_links 존재 · 컬럼 6종 · PK 3열 · subject_ref NOT NULL · linked_at DATETIME (D96-ⓑⓓ)       컬럼=['external_ref', 'link_state', 'linked_at', 'partner', 'subject_ref
  PASS  ② 필수 CHECK 2종 존재 · partner·subject_type 엔 CHECK 없음 (D96-ⓒ, 상한 미잠금)                            enum=1, 결합=1, partner/subject_type=0, 총 CHECK=2
  PASS  ③ 결합 CHECK 가 null-safe `link_state IS 'LINKED'` (`=` 되돌림 차단, D96-ⓐ)                           CHECK=external_ref IS NULL OR link_state IS 'LINKED'
  PASS  ④ ('NOT_LINKED','CMP-X') 거부 — 승인 없이 식별자 금지 (D91)                                              CHECK constraint failed: external_ref IS NULL OR link_state IS 'LINKED
  PASS  ⑤ (NULL,'CMP-X') 거부 — SQLite 3값 논리 구멍 (`=` 면 통과한다, D96-ⓐ)                                     CHECK constraint failed: external_ref IS NULL OR link_state IS 'LINKED
  PASS  ⑥ 'linked'·'LINK' 거부 — link_state enum 2종 (오타 차단)                                             'linked'→CHECK constraint failed: link_stat / 'LINK'→CHECK constraint
  PASS  ⑦ (NULL, NULL) 통과 — '모름'을 적을 자리가 살아 있다 (D62·D78)                                              통과
  PASS  ⑧ ('LINKED','CMP-X') 및 ('LINKED', NULL) 통과 — 후자가 §A InsuQ 행 (D95)                             식별자 있음→통과 / 식별자 NULL→통과
  PASS  ⑨ ('finallq','company','') 중복 거부 · subject_ref=NULL 거부 (D96-ⓑ)                                1회차=True, 중복→UNIQUE constraint failed: part, NULL→NOT NULL constraint
  PASS  ⑩ traces.request_chain_id 존재 · nullable · 기본 NULL (D94-ⓐ)                                     notnull=0, dflt=None, 미지정 INSERT 후 값=None
  PASS  ⑪-a TraceWriter 3종 발행 후 전 행 request_chain_id IS NULL (무관한 세션에 값이 새지 않는다)                      [('tool_call', None), ('tool_result', None), ('block', None)]
  PASS  ⑪-b request_chain_id 를 쓰는 쪽이 계측한다 (A2A 호출부 backend/a2a/trace.py 착수)                           86개 파일 스캔(주석·docstring 제외), traces 쓰기문 3건, 히트=['backend/a2a/trace.py']
  PASS  ⑫ traces.event_type CHECK 3종 유지 · 'a2a_call' INSERT 거부 (D94 ① 기각)                             CHECK=['tool_call', 'tool_result', 'block'], a2a_call→new row for rela
  PASS  ⑬ payload == SSE data (바이트 동일) · payload 에 request_chain_id 없음 (D30)                          payload={"tool": "lookup_error_code", "input": {"model": "iG5A",...
  PASS  ⑭ .env.example 에 A2A 4키 · 값 전부 빈칸 · 수집 키 절(외부 데이터 원천) **위** (D93 ③ 기각)                        누락=없음, 실값=없음, 키줄=[75, 76, 77, 78], 수집절=81
  PASS  ⑮ mcp_server/** 에 MAINTQ_A2A_·backend.a2a·partner_links 0건 (D15·D93)                          29개 파일 스캔, 히트=없음
  PASS  ⑯ credentials.load() 상태 4종 (not_configured/incomplete/configured/unknown_partner) · 모듈 캐시 없음  not_configured → incomplete → configured / 미지=unknown_partner, secret_
  PASS  ⑰ repr·str·f-string·status_report 에 secret 원문 없음 · asdict/astuple 소비자 0건                      노출=없음, asdict 는 원문 노출=True(소비자 0건)
  PASS  ⑱ data/maintq.db 불변 (mtime)                                                                   1787533322088414500 == 1787533322088414500
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (19건) — 판정과 식별자는 분리돼 있고, '모름'을 적을 자리는 살아 있으며,
request_chain_id 는 **backend/a2a/trace.py 가 쓴다**(⑪-b — 무관한 세션에는 여전히 새지 않는다)
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/repair_flow_contract.py
수리 증빙 흐름 (MQ-913) — create_repair_record 직접 검증 + MQ-908 5경로(core) + MQ-909 REST 왕복(submit→sign→reject)

─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① create_repair_record 정상 호출 → status=ok · state=draft · expenditure_class 산출  status=ok state=draft expenditure_class=HOLD repair_id=RPR-2413
  PASS  ② repair_records 행 수 +1 (INSERT 만, 기존 12행 안 건드림)                               12건 → 13건
  PASS  ③ DB 행 실측 — state='draft' · 서명·신원 필드 전부 NULL (repair_writer() 는 draft 만 만든다)   row={'state': 'draft', 'performed_by': None, 'verified_by': None, 'signed_at': None, 'record_hash': None, 'requested_by': None, 'session_id': None}
  PASS  ④ expenditure_class — 도구 응답값이 DB 저장값과 일치 (D101)                                응답=HOLD · DB=HOLD
  PASS  ⑤ 채번 — 두 번째 호출이 RPR-%04d 순번을 이어간다                                              RPR-2413 → RPR-2414
  PASS  ⑥ 미존재 부품 → not_found/unknown_part · 행 수 불변 (아무것도 안 씀을 직접 센다)                   status=not_found reason=unknown_part missing=['NOT-A-REAL-PART'] · 14건 → 14건
  PASS  ⑦ MQ-908 5경로 전부 200 — core 프로파일(MAINTQ_TOOLS_PROFILE 미설정)에서도 살아 있다 (D73)       tools_profile env=None · GET /assets/{id}/metrics=200 · POST /equipment/{id}/repair-value=200 · GET /parts/{no}/criticality=200 · POST /expenditure/classify=200 · GET /assets/{id}/evidence-bundle=200
  PASS  ⑧ metrics 응답에 n_repairs_signed·n_repairs_unsigned 존재 (서명분만 반영, 12 §11)         n_repairs_signed=2 n_repairs_unsigned=3
  PASS  ⑨ expenditure/classify 응답 verdict 3종 중 하나 (CAPITAL|REVENUE|HOLD)               verdict=HOLD
  PASS  ⑩ 팀장이 submit → 403                                                             status=403
  PASS  ⑪ 정비사가 submit → 200, state=pending                                             status=200 state=pending
  PASS  ⑫ 정비사가 sign → 403                                                              status=403
  PASS  ⑬ 본인 제출건 본인 서명(self_sign) → 409                                                status=409 reason=self_sign
  PASS  ⑭ 팀장이 sign → 200, state=signed, record_hash=sha256:*, hash_verified=true       status=200 state=signed hash=sha256:dfbcf56f1d0bb61082da1c1e519baf14d38539f9d08db1ce8dcec00da76a735e hash_verified=True
  PASS  ⑮ signed 재서명 → 409 invalid_transition                                          status=409 reason=invalid_transition
  PASS  ⑯ reject 사유 공백 → 422                                                           status=422
  PASS  ⑰ reject 사유 있음 → 200, state=rejected                                           status=200 state=rejected
  PASS  ⑱ 서명 후 get_maintenance_metrics 의 n_repairs_signed +1 (12 §11)                  2 → 3
  PASS  ⑲ 실 DB(공유 Postgres) repair_records 행 수 불변 (사본만 썼다는 증거)                         12 → 12
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (19건) — create_repair_record 는 draft INSERT 만 하고(D10·D98), MQ-908 5경로는 core 프로파일에서도 200 이며(D73), MQ-909 REST 왕복이 403/409/422 경계를 실제로 지킨다
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/deadline_risk_contract.py
deadlines/risk_grade 계약 검증 — DDL 무결성 · track_deadlines 4상태 · assess_risk_grade · 프로파일 게이트 · REST 매핑 (MQ-1106)

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ① DDL — deadlines.type 이 enum(TAX-CREDIT-2Y|SAFETY-INSPECTION) 밖이면 CHECK 거부                                                     asset=AST-L1-CONV type=BOGUS-TYPE → 거부됨
  PASS  ② DDL — incidents.asset_id 가 존재하지 않는 자산이면 FK 거부                                                                                 asset=AST-DOES-NOT-EXIST → 거부됨
  PASS  ③ DDL — ownership_checks either-or CHECK: state=VERIFIED+evidence_ref 성공 · state=VERIFIED+limit_note 거부                         양성(evidence_ref 채움)=성공 · 음성(VERIFIED 인데 limit_note 채움)=거부됨
  PASS  ④ DDL — risk_profile.risk_grade 가 enum(LOW|MEDIUM|HIGH) 밖이면 CHECK 거부                                                            building=BLD-DDL-TEST risk_grade=CRITICAL → 거부됨
  PASS  ⑤ track_deadlines 기본 호출(인자 없음, 실제 오늘 날짜) → 정확히 0건 (D62, MQ-1102 DoD 고정)                                                         status=ok items=0건
  PASS  ⑥ today 주입 — IN_REVIEW_BAND (months_since=24, review_band=[22,26])                                                              status=ok items=[{'asset_id': 'AST-L1-CONV', 'type': 'TAX-CREDIT-2Y', 'law_refs': ['KR-STTC-24', 'KR-STTC-146'], 'due_date': '2026-01-01', 'days_remaining': 0, 'state': 'IN_REVIEW_BAND', 'message': '취득 후 사후관리 기간 미경과. 처분 시 공제세액 추징 대상', 'resolve_options': ['사후관리 기간 경과까지 대기', '추징 감수 결정 (override, 사유 기재 필수)']}]
  PASS  ⑦ today 주입 — UPCOMING (months_since=20 < lo=22, window_days=180)                                                                status=ok items=[{'asset_id': 'AST-L1-CONV', 'type': 'TAX-CREDIT-2Y', 'law_refs': ['KR-STTC-24', 'KR-STTC-146'], 'due_date': '2026-05-01', 'days_remaining': 120, 'state': 'UPCOMING', 'message': '취득 후 사후관리 기간 미경과. 처분 시 공제세액 추징 대상', 'resolve_options': ['사후관리 기간 경과까지 대기', '추징 감수 결정 (override, 사유 기재 필수)']}]
  PASS  ⑧ today 주입 — 제외 (months_since=30 >= hi=26, 항목이 없어야 함)                                                                           status=ok items=0건
  PASS  ⑨ today 주입 — OVERDUE (안전검사 만료, window_days=1 이어도 항상 포함)                                                                         status=ok items=[{'asset_id': 'AST-L1-CONV', 'type': 'SAFETY-INSPECTION', 'law_refs': ['KR-OSHA-93', 'KR-OSHA-ENR-126'], 'due_date': '2025-12-02', 'days_remaining': -30, 'state': 'OVERDUE', 'message': '안전검사 대상 기계. 검사 이력 제공 및 이전 후 재검사 필요 (주기: 설치 후 3년 이내 최초 · 이후 2년마다)', 'resolve_options': ['직전 검사증 사본 첨부', '매수측 재검사 계획 확인']}]
  PASS  ⑩ window_days 경계값 — days_remaining=50 일 때 window_days=50 은 포함(<=) · 49 는 제외                                                     window_days=50→1건 · window_days=49→0건
  PASS  ⑪ assess_risk_grade — BLD-C: changed=true (stored=LOW, 재계산=HIGH, 의도적 불일치 시드)                                                    status=ok changed=True current=HIGH stored=LOW
  PASS  ⑫ assess_risk_grade — BLD-A: changed=false (저장값과 재계산이 일치)                                                                       status=ok changed=False current=LOW stored=LOW
  PASS  ⑬ assess_risk_grade — 미등록 building_id → not_found/unknown_building                                                              status=not_found reason=unknown_building
  PASS  ⑭ 프로파일 게이트 — full 기동 시 track_deadlines·assess_risk_grade 둘 다 등록                                                                 full 도구 20종 · 포함=['assess_risk_grade', 'track_deadlines']
  PASS  ⑮ 프로파일 게이트 — core 기동 시 두 도구 모두 미등록 (D88, 평가는 core 기준)                                                                           core 도구 7종 · 누출=없음
  PASS  ⑯ REST(core) — GET /api/deadlines: 정상 자산 200 · 없는 자산 404 · window_days=-1 422                                                   200/404/422 (asset_id 정상/없음, window_days=-1)
  PASS  ⑰ REST(core) — GET .../risk-grade: building 200 · asset 200 · 없는 building 404 (D73)                                             200/200/404 (BLD-A/AST-L1-CONV/BLD-NOPE)
  PASS  ⑱ liveness 앵커 — mcp_server/tools/*.py 전 파일에 deadlines·incidents·ownership_checks·risk_profile INSERT 코드 부재 (양성 축: 스캔 파일 수 > 0)  스캔 24개 파일 · 위반=없음
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (18건) — DDL 무결성 · track_deadlines 4상태·경계값 · assess_risk_grade · 프로파일 게이트 양방향 · REST 매핑 · liveness 앵커
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/external_store_contract.py
외부 응답 원본 보관·소비자 계약 검증 (D103·D105·D60·D39·D62·D99, P30) — 네트워크·지출 0

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ⓐ 저장 경로 규약: store_path('elice', key) → data/raw/external/elice/<key>.json                                       path=C:\Users\ttogl\workspace\MaintQ\data\raw\external\elice\x_p1_probe_never_written.json · STORE_ROOT=C:\Users\ttogl\workspace\MaintQ\data\raw\external · 파일 미생성=True
  PASS  ⓑ 미등록 source·경로 이탈 key 거부 (4종)                                                                                  {'미등록 source': True, '상위 디렉터리 이탈 ..': True, '경로 구분자 /': True, '숨김파일형 선행 .': True}
  PASS  ⓒ 봉투 round-trip: store_response → load_response → body_of                                                       path=roundtrip_probe_p1.json · body 일치=True · iter_stored 포함=True
  PASS  ⓒ-2 load_response: 미보관 key → None                                                                               반환값=None (type=NoneType)
  PASS  ⓓ 메타 allowlist: params·headers·Authorization·OC 4종 거부                                                           {'params': True, 'headers': True, 'Authorization': True, 'OC': True}
  PASS  ⓔ 멱등: 동일 내용 재저장은 무동작 (경로·mtime 불변)                                                                              path 동일=True · mtime 동일=True
  PASS  ⓔ-2 상이 내용 재저장 거부 (append-only, D60) · 원본 보존                                                                     ExternalStoreError · 원본 보존=True
  PASS  ⓕ 기입 실패 주입 후 .tmp 잔여 0건 (원자적 기입)                                                                                OSError · 잔여 .tmp=0건 (주입 전 0건)
  PASS  ⓚ-4 캐시 미스 + allow_purchase=False → 예외 · 네트워크 0회                                                                 EliceError · _submit_and_wait 호출 0회
  PASS  ⓚ-5 캐시 미스 + allow_purchase=True 인데 키/URL 없음 → 지출 전 예외 · 네트워크 0회                                                 EliceError · _submit_and_wait 호출 0회
  PASS  ⓚ-6 실측 중 실 캐시 디렉터리 미생성 (격리 확인)                                                                                  tmp_cache=ext_store_contract_k9xlpunh (실 캐시 경로 미접촉)
  PASS  ⓖ 평문 자격증명 부재 + 양성 축 (P30) — leaks_real·scanner_alive·scanned_total                                              git_ok=True(rc=0) · leaks_real=False(대상 2종 — 검출파일[]) · scanner_alive=True(합성 픽스처 탐지) · scanned_total=35
  PASS  ⓗ .env.example: 키 이름 3종 존재 · 실값 없음                                                                              누락=없음 · 값 채워짐=없음
  PASS  ⓘ-1 신규 elice 응답 JSON → git 추적 대상 (rc=1)                                                                         state=tracked rc=1
  PASS  ⓘ-2 임시 페이지 PDF 조각 → 제외 (rc=0)                                                                                   state=ignored rc=0
  PASS  ⓘ-3 매뉴얼 PDF 원본 → 제외 (rc=0, 절대규칙 5 유지)                                                                           state=ignored rc=0 · file=S100_Manual_Korean_V4.2.pdf
  PASS  ⓙ-1 소급 보관 지점 순서: _get_json → _store_payload → parse_article_response                                            인덱스 15929 < 15983 < 16032
  PASS  ⓙ-2 _store_payload 본문: params·headers 식별자 0건 · 지연 import                                                        본문확보=True · 금칙식별자=없음 · 지연import=True
  PASS  ⓙ-3 fetch_laws.py 본문에 해시 재구현 흔적 0건 (content_key 는 store.py 단일 소유)                                               검출=없음
  PASS  ⓚ-1 elice_docvision.py: requests import 0건 (httpx 만 지연 import)                                                  requests 참조=없음
  PASS  ⓚ-2 extract_page: 캐시 확인이 _submit_and_wait 호출보다 앞 (문자열 인덱스)                                                      본문확보=True · load_response idx=407 < _submit_and_wait idx=1400
  PASS  ⓚ-3 PRICE_PER_PAGE_WON == 45                                                                                    실측 45
  PASS  ⓛ 판독 계획 산술: 34p / 1530원                                                                                         n_pages=34 · won_per_page=45 · won_total=1530
  PASS  ⓜ-1 NO_ANCHOR 는 어떤 claim 과도 CONFIRMED_ABSENT 가 되지 않는다 (양성 축 사수, P30)                                            ['INCONCLUSIVE', 'INCONCLUSIVE', 'INCONCLUSIVE', 'INCONCLUSIVE', 'INCONCLUSIVE']
  PASS  ⓜ-2 ABSENT_IN_MANUAL × ANCHOR_ONLY → CONFIRMED_ABSENT                                                           CONFIRMED_ABSENT
  PASS  ⓜ-3 AMBIGUOUS × ACTION_FOUND (rowspan 1:1 해소) → RECOVERABLE                                                     RECOVERABLE
  PASS  ⓜ-4 AMBIGUOUS × ACTION_FOUND (rowspan 미해소) → STILL_AMBIGUOUS                                                    STILL_AMBIGUOUS
  PASS  ⓜ-5 reader_blind=True 는 CONFIRMED_ABSENT 를 INCONCLUSIVE 로 강등                                                    INCONCLUSIVE
  PASS  ⓜ-6 ABSENT_IN_MANUAL × ACTION_FOUND → DISAGREE                                                                  DISAGREE
  PASS  ⓜ-7 NOT_FOUND_ON_PAGE × ACTION_FOUND (rowspan 1:1 해소) → RECOVERABLE                                             RECOVERABLE
  PASS  ⓜ-7b NOT_FOUND_ON_PAGE × ACTION_FOUND (rowspan 미해소) → STILL_AMBIGUOUS (NTC 사례)                                  STILL_AMBIGUOUS
  PASS  ⓜ-11 UNCLASSIFIED × ACTION_FOUND: 해소 True→RECOVERABLE / False→STILL_AMBIGUOUS                                   True→RECOVERABLE · False→STILL_AMBIGUOUS
  PASS  ⓜ-12 NO_CLAIM × ACTION_FOUND: 해소 True→RECOVERABLE / False→STILL_AMBIGUOUS                                       True→RECOVERABLE · False→STILL_AMBIGUOUS
  PASS  ⓜ-8 미지 claim·axis → ValueError (순수 오라클, D9 미적용 — MCP 도구가 아니다)                                                   claim=ValueError · axis=ValueError
  PASS  ⓜ-9 ROW_TEXT_ONLY 는 ANCHOR_ONLY 와 같은 판정 (축만 분리, 판정은 동일) · 축 5종                                                  {'ABSENT_IN_MANUAL': 'CONFIRMED_ABSENT', 'AMBIGUOUS': 'DISAGREE', 'NOT_FOUND_ON_PAGE': 'DISAGREE', 'UNCLASSIFIED': 'INCONCLUSIVE', 'NO_CLAIM': 'INCONCLUSIVE'} · ELICE_AXES=['ACTION_FOUND', 'ROW_TEXT_ONLY', 'ANCHOR_ONLY', 'NO_ANCHOR', 'UNREAD']
  PASS  ⓜ-10 unread_in_scope=True 는 CONFIRMED_ABSENT 를 INCONCLUSIVE 로 강등 (D62)                                          unread_in_scope=True → INCONCLUSIVE · False → CONFIRMED_ABSENT
  PASS  ⓝ store.py·verify_actions_absence.py 네트워크 라이브러리 참조 0건(주석 포함)                                                    store.py 검출=없음 · verify_actions_absence.py 검출=없음
  PASS  ⓟ-1 트립표만 심으면 대조군이 자명 충족되지 않는다 → state=blind (READER_BLIND 발화 가능)                                                state=blind · 대조통과=0 · ACTION_FOUND=0 · ROW_TEXT_ONLY=1 · OCT축=ROW_TEXT_ONLY (발견 p=416)
  PASS  ⓟ-2 결측 코드의 자기 설명 셀은 조치문이 아니다 — S100 NMT 가 DISAGREE 로 가지 않는다                                                     NMT 축=ROW_TEXT_ONLY 판정=INCONCLUSIVE blind=True · 전체 DISAGREE=0건 · 근거='인버터 운전 시 모터가 연결되지 않으면 발생합니다. Pr.31 코드를 1'
  PASS  ⓟ-3 픽스처 A: 네트워크 0회 · 판독은 캐시에서만                                                                                  _submit_and_wait 0회 · pages_read=1
  PASS  ⓟ-4 생존 축은 정본 actions 문장 대조다 — OCT 가 조치표(p.420)에서 대조 통과                                                          state=ok · 대조통과=1 · OCT 축=ACTION_FOUND 발견p=420 대조='full' 근거='모터가 정지한 후에 운전하거나 속도 검색 기능(Cn.60)을 사용'
  PASS  ⓟ-5 생존 확인 후에는 결측 코드가 진짜 판정을 받는다 — S100 NMT → CONFIRMED_ABSENT                                                   NMT 축=ROW_TEXT_ONLY 판정=CONFIRMED_ABSENT blind=False unread=False
  PASS  ⓟ-6 rowspan 귀속을 셀 정체성으로 센다 — iG5A COM 은 가짜 1:1 이 아니라 STILL_AMBIGUOUS                                            claim=AMBIGUOUS 축=ACTION_FOUND rowspan=5 covers=4 resolved=False 판정=STILL_AMBIGUOUS
  PASS  ⓟ-7 원인문의 표지어(`교체`)가 조치문으로 오인된다 — iG5A COL 실제 cause → ACTION_FOUND·DISAGREE (안전 방향, C1 계열 위양성을 은폐하지 않고 계약으로 검사)  축=ACTION_FOUND 미판독=['ig5a-manual'] 강등전=DISAGREE 판정=DISAGREE
  PASS  ⓟ-8 픽스처 B: 네트워크 0회 · 5p 캐시 판독 · ig5a-troubleshooting 대조군도 생존                                                    _submit_and_wait 0회 · pages_read=5 · ig5a-troubleshooting 대조통과=2/2 state=ok
  PASS  ⓟ-9 action_text_match: 설명 셀은 불일치 · 조치문 원문은 일치 (음성·양성 양축)                                                        설명셀=(False, '', '') · 조치문=(True, 'full', '모터가 정지한 후에 운전하거나 속도 검색 기능(Cn.60)을 사용하십시오.')
  PASS  ⓞ 정본 불변 (D99) — error_codes.json · candidate 후보 파일 sha256 실행 전후 동일                                              대상=['error_codes.json', 'error_codes_actions.candidate.json'] · sha256 동일=True
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (47건) — D103·D105·D60·D39·D62·D99 준수. 실 Elice·법제처 호출은 하지 않는다 — 캐시는 매 검사마다 tmp 로 격리했다.
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/ie5_extract_contract.py
IE5 추출 경로 계약 — 픽스처 기반 (PDF 비의존, sprint-14 §2 MQ-1405)

────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  A① 픽스처 최상위 키                                  최상위 키 8개 · 누락 없음 · _source.sha256 있음
  PASS  A② 대상 페이지·페이지 키                               페이지 [125, 126] (기대 [125, 126]) · 페이지 키 누락 없음
  PASS  A③ 열 경계 4개 = 3열                               열 경계 개수 {125: 4, 126: 4} (3열 = 경계 4개) · 페이지 2장
  PASS  A④ 열 경계 단조 증가                                 열 경계 {125: '[84.98, 160.98, 314.39, 466.89]↑', 126: '[99.64, 175.38, 332.5, 487.26]↑'}
  PASS  A⑤ 경계가 페이지마다 다르다                              p125↔p126 경계 차 [14.66, 14.4, 18.11, 20.37] (전부 0 이면 하드코딩 의심 · §0-3 '페이지마다 다르다')
  PASS  A⑥ 바깥 경계 글자범위 클램프                             {125: '글자범위[28.32,466.89] 경계[84.98,466.89] 우측일치=True', 126: '글자범위[85.22,487.26] 경계[99.64,487.26] 우측일치=True'}
  PASS  A⑦ 행 경계 ↔ 그리드 행수                              {125: '경계7개↑ 그리드6행', 126: '경계8개↑ 그리드7행'} (그리드 행 = 경계-1)
  PASS  A⑧ 명칭 열 경계 ⊃ 본문 경계                            {125: '본문7 ⊂ 명칭8 추가경계[373.75]', 126: '본문8 ⊂ 명칭9 추가경계[311.57]'} (추가 경계 = 세로 병합 밴드)
  PASS  A⑨ 머리행 3열                                     {125: "['보호 기능', '이상 원인', '대책']✓", 126: "['보호 기능', '이상 원인', '대 책']✓"}
  PASS  A⑩ 모든 행이 3셀                                   행 13개 · 페이지별 셀 폭 {125: [3], 126: [3]}
  PASS  A⑪ 원인·대책 열 혼입 없음                              본문 11행 · 원인 열 존댓말 종결 0건 · 대책 열 존댓말 종결 11건(앵커)
  PASS  A⑫ 불릿 분해                                      원인 셀 11개 → 문장 25건 · 2문장 이상 9행
  PASS  A⑬ 밴드 산술 = table_rows                         기하 유도 {125: 6, 126: 7} 합 13 · expected 13
  PASS  A⑭ 열 경계 재유도 (PDF-free 실행)                     (tol 0.05pt — 픽스처는 소수 2자리 반올림) {125: '재유도 [84.97, 160.98, 314.39, 466.89] vs 저장 [84.98, 160.98, 314.39, 466.89] → 경계일치=True · y범위 [158.3, 516.94] vs [158.3, 516.94] → True', 126: '재유도 [99.64, 175.38, 332.5, 487.26] vs 저장 [99.64, 175.38, 332.5, 487.26] → 경계일치=True · y범위 [92.66, 503.14] vs [92.66, 503.14] → True'}
  PASS  A⑮ 열 경계 실패 경로 = 상태 반환 (D9)                    edge 0개 → None 사유='세로 edge 가 0개 — 이 페이지에는 표 배경 rect 가 없다' · x≈160.98 edge 51개 제거 → None 사유='열 경계가 4개가 아니다 — 3개 [85.0(len 838), 314.4(len 754), 474.4(len' (예외 없이 상태로 반환 = D9)
  PASS  A⑯ 괘선 없음 = page.lines 0개 (D107 전제, §9 이월①)    page.lines 세로선 개수 {125: 0, 126: 0} (기대: 전부 0 — 괘선 없음이 D107 의 전제)
  PASS  B① 괄호 표기 형상 · 두 버킷 서로소                        좁은 형상 94건(코드 40종) · 형상 제외 163건(코드 47종) · 형식 위반 0/0건 · 표기 겹침 []
  PASS  B② 밴드 재구성 (병합 밴드 분할)                          인벤토리 13종 → 행 13개 · 기하 밴드합 13 · 명칭 1:1 소비=True · 미해결 []
  PASS  B③ 조인 재현 — 매칭                                 재현 5건 [('IOL', 'IOL', '과부하'), ('Lvt', 'LVT', '저전압'), ('OCt', 'OCT', '과전류'), ('OHt', 'OHT', '냉각핀 과열'), ('Ovt', 'OVT', '과전압')] · 기대 5건 (일치=True)
  PASS  B④ 조인 재현 — 미매칭 양방향 · 행 폐포                     코드 24/24 · 명칭 8/8 · 행 폐포 5(코드 붙은 행)+8(미매칭 행)=13 vs 전체 13행 → 버려진 행 없음=True (matched 쌍 5건 ≠ 행 수일 수 있다)
  PASS  B⑤ 정규화 ⓐ 공백·괄호 제거                             '냉각 핀 과열'→'냉각핀과열' · '과전압 (Ovt)'→'과전압'
  PASS  B⑥ 정규화 ⓑ 인버터 접두어 (고립 + 관측)                    '인버터과부하'→'과부하' · 고립 입력 매칭 ON ['ZZA'] / OFF [] · 실 픽스처 IOL variant ON '과부하' → OFF '인버터 과부하' (건수는 5로 불변 — 본문에 접두어 포함 표기가 따로 있어 ⓐ 로도 붙는다)
  PASS  B⑦ 명칭 후보 = 접미 어절 · 최소 길이                      '동시 과전류'→['과전류', '동시 과전류'] · '전압'(2자)→[] · MIN_NAME_LEN=3 MAX_NAME_TOKENS=4
  PASS  B⑧ cause·action ↔ 그리드 셀 (병합 복제 포함)            코드 5종 대조 · 불일치 없음 · 병합 밴드 1건[('IOL', ['과부하 트립'])] 셀 일치=True · 원인·대책 둘 다 비지 않은 코드 5/5
  PASS  C① _status 승인·병합 완료 표기 (D33·D99, Sprint 15)   _status='승인 완료 (2026-08-20). ⛔ 이 파일은 여전히 DB 에 적재되지 않는다 — 정본 병합은 별도 스크립트(Sprint 15 MQ-1507)가 한다 · IE5 5건 정본 병합 완료 (2026-08-21, MQ-1507)' · 승인 완료 표기=True · 정본 병합 완료 표기=True · is_draft_status()=False (False 가 정답 — 승인·병합 후 초안 아님)
  PASS  C② _unmatched 3버킷 실재·비공백                      버킷 4종 codes=24 · names=8 · codes_excluded_by_shape=43 · codes_without_name=2 · 비어 있는 버킷 없음 (조인 실패도 형상 제외도 숨기지 않는다)
  PASS  C③ _stats 자기무결성 (행 폐포)                        rows 13 = matched_rows 5 + un 8 · matched 쌍 5 · canonical 29종/원표기 40종 · 위반 없음
  PASS  C④ manual_page = 물리 페이지 (D26)                 codes 5건 · 페이지 [125, 126] · 범위 밖 [] · _source.pages=[125, 126] · citation_basis='PDF 물리 페이지 (D26)'
  PASS  C⑤ codes 필수 키 · model enum 미확장                검사 5건 · 키 누락 [] · model 필드 [] (§0-5 — enum 확장은 P11)
  PASS  C⑥ 후보 ↔ 픽스처 동일 실행 산출물                         동일 실행 대조 {'sha256': True, 'stats': True, 'codes': True, 'uc': True, 'shape': True, 'noname': True} · 불일치 없음
  PASS  C⑦ manifest 등재 표기 (D109, Sprint 15 = P11)     manifest_registered=True · manifest.json 에 IE5 실재=True · manual_id='ie5-standard' (Sprint 15 = P11 완료, D109)
  PASS  C⑧ 리콜 — 확정 12종 전건 등장                          확정 12종 중 미등장 없음 · 산출물 canonical 총 74종 · 이름 지어냄 0건 · 소재 {'COL': ['codes_without_name'], 'ERR': ['_unmatched.codes'], 'ETA': ['_unmatched.codes'], 'ETB': ['_unmatched.codes'], 'GCT': ['_unmatched.codes'], 'HWT': ['_unmatched.codes'], 'IOL': ['codes'], 'LVT': ['codes'], 'NON': ['codes_without_name'], 'OCT': ['codes'], 'OHT': ['codes'], 'OVT': ['codes']}
  PASS  C⑨ 형상 제외 버킷 = 차집합 (블로커 ①)                     형상 제외 43종(원표기 47종) · 파이프라인과 겹침 없음 · 좁은 형상 누수 없음 · 스펙 형상 밖 없음 · 근거(페이지+주변텍스트) 누락 0건 · 예: ['AI', 'AM', 'DC', 'DOWN', 'FUNC', 'FX']
  PASS  C⑩ canonical 접기 + 원표기 보존 (D25)                항목 72종 · canonical 중복 없음 · 대문자 위반 없음 · 원표기 유실 없음 · **접힌 항목 13건**(앵커) [('OVT', ['Ovt', 'OVt']), ('LVT', ['LVt', 'Lvt']), ('CUR', ['Cur', 'CUr']), ('DCL', ['DCL', 'dCL'])] · 원표기 40종 → canonical 29종
  PASS  C⑪ code_pages exact/case_folded 분리 (§8 이월①②)  검사 74건 · exact/case_folded 누락or겹침 없음 · COL.pages_exact에 p117 포함=True(reviewer '위양성 우려' 재검증 — 실측은 정합) · GCT.code_pages_exact에 p117 포함=True(§8 이월① 리콜 복구 앵커)
  PASS  C⑫ IOL↔IOLt 명칭 충돌 상호참조 (§8 이월③)               IOL.name_collision_with=['IOLT'] · IOLT.name_collision_with=['IOL'] (양방향 상호참조=True)
  PASS  D① 정본 error_codes.json 미기록 (D99)              쓰기 호출 6건 대상=['CANDIDATE', 'GEOMETRY_FIXTURE', 'page.extract_text() or ""', 'path', 'path.parent', 's or ""'] · CANONICAL 향함 0건 · CANONICAL 읽기 2건 · 정본 실측 53종 · write_text 보유 함수 ['write_json']
  PASS  D② data/raw/ 미기록 (절대규칙 5)                     쓰기 호출 6건 · RAW 향함 0건 · RAW/PDF_NAME 참조 4회(줄 [80, 84, 978, 978]) · 산출 디렉터리 ['data\\extracted', 'spikes\\fixtures'] · RAW 실재=True
  PASS  D③ 표 파싱 경로에 extract_text 폴백 없음                표 함수 8/8개 스캔 · extract_text 보유 [] · extract_tables 앵커 ['parse_table_page'] · explicit 문자열 ['explicit', 'explicit_horizontal_lines', 'explicit_vertical_lines'] · 양성대조(body_code_names 의 extract_text 탐지)=True
  PASS  D④ _warnings 실패 경로 liveness (§8 이월④)          _warnings 타입=list 실제건수=0 (정상 실행은 0건이 맞다) · 인위적 실패 재현 rows=[] warn='p999: 열 경계 유도 실패 — 세로 edge 가 0개 — 이 페이지에는 표 배경 rect 가 없다 (스킵)' (형식 유효=True)
  PASS  E① PDF sha256 ↔ 픽스처                           sha256 d777626148b4… (픽스처 d777626148b4…) · 151p (픽스처 151p) · 경로 IE5_User Manual(Standard)_Kor_V1.0_200526.pdf
  PASS  E② 재추출 열 경계 == 픽스처                            재추출 [[84.98, 160.98, 314.39, 466.89], [99.64, 175.38, 332.5, 487.26]] · 불일치 없음
  PASS  E③ 재추출 그리드 텍스트 == 픽스처                         재추출 행수 [6, 7] · 셀 텍스트 불일치 없음
  PASS  F① 뮤턴트: 빈 픽스처 → A① 발화                         판정=FAIL(기대) · 최상위 키 0개 · 누락 ['_source', '_generated_by', '_generated_at', 'pages', 'code_name_pairs', 'shape_excluded_pairs', 'expected'] · _source.sha256 없음
  PASS  F② 뮤턴트: pages 제거 → A② 발화                      판정=FAIL(기대) · 페이지 [] (기대 [125, 126]) · 페이지 키 누락 없음
  PASS  F③ 뮤턴트: 열 경계 3개 → A③ 발화                       판정=FAIL(기대) · 열 경계 개수 {125: 3, 126: 4} (3열 = 경계 4개) · 페이지 2장
  PASS  F④ 뮤턴트: 경계 뒤섞음 → A④ 발화                        판정=FAIL(기대) · 열 경계 {125: '[84.98, 160.98, 314.39, 466.89]↑', 126: '[99.64, 332.5, 175.38, 487.26]✗'}
  PASS  F⑤ 뮤턴트: 머리행 훼손 → A⑨ 발화                        판정=FAIL(기대) · {125: "['고장 대책', '', '']✗", 126: "['보호 기능', '이상 원인', '대 책']✓"}
  PASS  F⑥ 뮤턴트: 대책 문장 혼입 → A⑪ 발화                      판정=FAIL(기대) · 본문 11행 · 원인 열 존댓말 종결 1건[(125, '냉각핀 과열', '합니다')] · 대책 열 존댓말 종결 11건(앵커)
  PASS  F⑦ 뮤턴트: table_rows 위조 → A⑬ 발화                 판정=FAIL(기대) · 기하 유도 {125: 6, 126: 7} 합 13 · expected 99
  PASS  F⑧ 뮤턴트: 공백 정규화 차단 → 고립 매칭 붕괴                  고립 입력('냉각 핀 과열' ↔ '인버터 냉각핀 과열') ON ['ZZB'] / OFF [] · 실 픽스처에서는 OFF 여도 5건 유지(본문에 두 표기가 모두 존재 — 이 표본에서 ⓐ 는 중복 경로다)
  PASS  F⑨ 오라클: extract_text 스캐너 생존                   합성 소스(폴백 있음) 탐지=True · 합성 소스(폴백 없음) 오탐=False · 스캔 함수 ['parse_table_page']
  PASS  F⑩ 뮤턴트: codes_without_name 제거 → C⑧ 발화         판정=FAIL(기대) · 확정 12종 중 미등장 ['COL', 'NON'] · 산출물 canonical 총 72종 · 이름 지어냄 0건 · 소재 {'COL': [], 'ERR': ['_unmatched.codes'], 'ETA': ['_unmatched.codes'], 'ETB': ['_unmatched.codes'], 'GCT': ['_unmatched.codes'], 'HWT': ['_unmatched.codes'], 'IOL': ['codes'], 'LVT': ['codes'], 'NON': [], 'OCT': ['codes'], 'OHT': ['codes'], 'OVT': ['codes']}
  PASS  F⑪ 뮤턴트: v_edge 이동 → A⑭ 발화 (추출기 실행)            판정=FAIL(기대) · (tol 0.05pt — 픽스처는 소수 2자리 반올림) {125: '재유도 [84.97, 210.98, 314.39, 466.89] vs 저장 [84.98, 160.98, 314.39, 466.89] → 경계일치=False · y범위 [158.3, 516.94] vs [158.3, 516.94] → True', 126: '재유도 [99.64, 175.38, 332.5, 487.26] vs 저장 [99.64, 175.38, 332.5, 487.26] → 경계일치=True · y범위 [92.66, 503.14] vs [92.66, 503.14] → True'}
────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (전체 54건 = PASS 54 · SKIPPED 0) — D9·D25·D26·D33·D99 · sprint-14 §0-3(괘선 없는 표) 준수.
  · E 축(PDF 대조) 실행됨 — SKIPPED 0건
PS C:\Users\ttogl\workspace\MaintQ> uv run python spikes/a2a_partner_tools_contract.py
MQ-1613 — A2A 파트너 도구 2종 계약 (D15·D93·D69·D88·D9·D30·D114)

[격리] 실 DB(before) mtime_ns=1787533322088414500 size=319488
[격리] 실 DB(after)  mtime_ns=1787533322088414500 size=319488

─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  PASS  ①-search_insurance_clause D15·D93 격리(backend.a2a/MAINTQ_A2A_ 0건) + liveness(httpx/BASE_URL 실사용)  backend.a2a=0건 · MAINTQ_A2A_=0건 · httpx=4건 · MAINTQ_BACKEND_BASE_URL=1건
  PASS  ①-assess_equipment_loan D15·D93 격리(backend.a2a/MAINTQ_A2A_ 0건) + liveness(httpx/BASE_URL 실사용)    backend.a2a=0건 · MAINTQ_A2A_=0건 · httpx=4건 · MAINTQ_BACKEND_BASE_URL=1건
  PASS  ②-a full 프로파일 실기동 → 두 도구 등록                                                                      20종 · 누락=없음
  PASS  ②-b core(기본, MAINTQ_TOOLS_PROFILE 미지정) 실기동 → 두 도구 부재                                             7종 · 누출=없음
  PASS  ③-search_insurance_clause 200/completed → status ok · skill_status completed                     status=ok skill_status=completed
  PASS  ③-search_insurance_clause 200/input-required → status error · reason no_answer                   status=error reason=no_answer skill_status=input-required
  PASS  ③-search_insurance_clause 502 → status error · reason upstream_unavailable                       status=error reason=upstream_unavailable
  PASS  ③-search_insurance_clause timeout → status error · reason timeout                                status=error reason=timeout
  PASS  ③-search_insurance_clause 접속거부 → status error · reason backend_unreachable                       status=error reason=backend_unreachable
  PASS  ③-assess_equipment_loan 200/completed → status ok · skill_status completed                       status=ok skill_status=completed
  PASS  ③-assess_equipment_loan 200/rejected → status error · reason no_answer                           status=error reason=no_answer skill_status=rejected
  PASS  ③-assess_equipment_loan 502 → status error · reason upstream_unavailable                         status=error reason=upstream_unavailable
  PASS  ③-assess_equipment_loan timeout → status error · reason timeout                                  status=error reason=timeout
  PASS  ③-assess_equipment_loan 접속거부 → status error · reason backend_unreachable                         status=error reason=backend_unreachable
  PASS  ④-a 기존 도구 전부 a2a_chain_id=None → 키 집합 {tool,status,summary,elapsed} 바이트 동일                       18종 대상 · 관측된 키집합 [['elapsed', 'status', 'summary', 'tool']]
  PASS  ④-b liveness — a2a_chain_id 값을 주면 실제로 키가 실린다(①-b 형 짝: 부재가 아니라 선택 필드)                             키=['a2a_chain_id', 'elapsed', 'status', 'summary', 'tool']
  PASS  ⑤-a 필터 없음 → 3스킬 전부 회수(MAINTQ_DB 임시 지정 경유)                                                        count=3 skills=['assess-loan', 'lookup-clause', 'request-withdrawal']
  PASS  ⑤-b skill 필터 정확히 걸림                                                                              count=1 chain=['CHAIN-SPIKE-CLAUSE']
  PASS  ⑤-c po_id 필터 정확히 걸림                                                                              count=1 chain=['CHAIN-SPIKE-PO']
  PASS  ⑤-d building_id 필터 정확히 걸림                                                                        count=1 chain=['CHAIN-SPIKE-LOAN']
  PASS  ⑤-e chain_id 정확 매칭(접두어 매칭 아님)                                                                    count=1
  PASS  ⑥ 격리 — 실 data/maintq.db mtime·size 불변                                                            변경=False
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

통과 (22건) — A2A 파트너 도구 2종 격리·프로파일·5경로·SSE·이력 왕복 확인