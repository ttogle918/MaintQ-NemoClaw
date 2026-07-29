# 데모 영상 촬영 큐시트 (MQ-506)

산출물 목표: `docs/01_OVERVIEW.md` §10 이 요구하는 "데모 영상(S1→S2→S3→S4 순)" — 화면 A(정비사
진단 콘솔)에서 S1~S4를 순서대로, 화면 B(팀장 승인 큐)에서 근거 검토·승인·human-in-the-loop
증명(403)까지 이어서 촬영한다.

> 이 문서는 큐시트다. 러닝타임은 **촬영 후 실측치**로 채운다 — 추정치를 미리 적지 않는다
> (표의 "러닝타임" 칸은 전부 `TBD — 촬영 후 실측 기입`).

---

## 0. 사전 준비 체크리스트

촬영 시작 **전** 순서대로 확인한다. 하나라도 실패하면 다음 단계로 넘어가지 않는다.

1. **DB가 `--with-error-codes`로 적재돼 있는지 확인**
   - 재적재(권장 — 데모 상태를 항상 알려진 초기값으로 되돌린다. `seed_po_drafts`가
     `PO-0117`을 `state:"pending"`으로 다시 심어 두므로 컷2를 리허설로 이미 소진했어도
     복구된다):
     ```bash
     uv run python data/seed.py --with-error-codes
     ```
   - 출력에서 `[error_codes] 65건 적재 · related_parts 임시 매핑 N건`과 "시드 케이스 맵 검증"
     표가 전부 통과(✓)인지 육안 확인. `[error_codes] 적재 건너뜀`이 나오면 관련 승인이 안
     끝난 것이므로 **촬영 중단** — `TODO_직접할일.md`의 related_parts/승인 항목부터 처리한다.
   - 개수만 별도 확인하려면:
     ```bash
     uv run python -c "import sqlite3; c=sqlite3.connect('data/maintq.db'); print(c.execute('SELECT count(*) FROM error_codes').fetchone())"
     ```
     `(65,)` 가 아니면 촬영 중단.

2. **`GEMINI_API_KEY` 환경변수 확인** (라이브 컷 1·3·5는 실 LLM 호출이 필요하다)
   ```bash
   echo $GEMINI_API_KEY   # 또는 GOOGLE_API_KEY — 둘 중 하나만 있으면 됨 (.env.example 참조)
   ```
   비어 있으면 `.env`에 채우거나 OS 환경변수로 export 후 재확인. `MAINTQ_LLM_MODEL`도 함께
   비어 있지 않은지 확인(예: `gemini-2.5-flash`) — 기본값이 없어 비어 있으면 `get_client()`가
   즉시 실패한다(D40).

3. **백엔드 기동**
   ```bash
   uv run uvicorn backend.main:app --port 8000
   ```
   기동 후 헬스체크로 MCP 연결까지 확인 (`ready=False`면 도구 호출이 전부
   `mcp_unavailable`로 실패한다 — 09_RUNTIME §3):
   ```bash
   curl http://localhost:8000/health
   # {"status":"ok","mcp":true}  ← mcp:true 아니면 촬영 중단, MCP 서버 로그 확인
   ```

4. **프론트 기동 + API_BASE 정합성 확인 (실측으로 발견한 함정)**
   - `frontend/package.json`의 `dev` 스크립트는 `next dev -p 3003` → 실제 프론트 URL은
     `http://localhost:3003`이다(`frontend/README.md`의 "3000"·"3002" 서술은 낡은 문서 —
     `package.json` 이 실제 소스).
   - `frontend/lib/api.ts`의 `API_BASE` 기본값은 **`http://localhost:8003`**이다. 위 3번에서
     백엔드를 `--port 8000`으로 띄웠다면 이 기본값과 어긋난다. 아래 둘 중 하나로 맞춘다
     (둘 다 실재하는 해결책, 임의로 지어낸 것 아님):
     - (권장) 프론트 기동 전 `frontend/.env.local`에 `NEXT_PUBLIC_API_BASE=http://localhost:8000`
       추가, 또는
     - 백엔드를 `--port 8003`으로 기동해 기본값에 맞춘다.
   - CORS는 `localhost`/`127.0.0.1`의 3000~3005 포트를 범위로 허용하므로(`backend/main.py`)
     3003은 별도 설정 없이 통과한다.
   - 기동:
     ```bash
     cd frontend && npm run dev
     ```
   - 브라우저에서 `http://localhost:3003/technician` 접속 → 상단 장비 선택기가
     "장비 선택…" 플레이스홀더로 뜨는지 확인(= `GET /api/equipment` 연동 확인).

5. **브라우저 확대율·캐시 정리**
   - 확대율 100%(또는 촬영 해상도에 맞춘 고정값) — 브라우저마다 배율이 남아있으면 컷 사이
     레이아웃이 흔들린다.
   - 캐시·로컬스토리지 정리(시크릿/프라이빗 창 사용 권장) — 이전 리허설의 세션 잔상이
     화면에 남지 않게 한다. `?replay=` 계열 쿼리는 별도 세션 ID를 매번 새로 발급하므로
     캐시와 무관하지만, 리허설 중 열어둔 탭의 낡은 trace 패널 상태는 새로고침으로 지운다.

---

## 1. 촬영 순서 7컷

두 화면 모두 실제 라우트다 (`frontend/app/(console)/technician/page.tsx`,
`frontend/app/(console)/manager/**`, `Glob`으로 실재 확인). 입력 문구는 `docs/02_SCENARIOS.md`
원문 그대로이거나(컷1·3·4·5) 그와 합치하는 다음 턴 발화(컷2)다.

| 컷 | 화면 | URL | 입력/액션 | 보여줄 것 | 러닝타임 |
|---|---|---|---|---|---|
| 1 | 화면A 라이브 | `http://localhost:3003/technician` | 장비 선택기에서 iG5A 장비(예: `INV-L1-01 · iG5A`) 선택 → 채팅에 "iG5A 인버터에 OHt 에러 떴어" 입력 (S1 원문, `02_SCENARIOS.md`) | trace 패널에 도구 4스텝(`lookup_error_code`→`rag_search_manual`→`search_inventory`→`get_supplier_quotes`)이 순차로 뜨는 것(A1 — 호출 직전에 뜸)·`SAFETY` block이 위험 서술 문단보다 먼저/함께 도착(D22, token에 안 섞임)·응답 내 인용 칩(citation block, PDF p.202)·마지막에 발주 초안 카드(`po_card` variant `draft`, "팀장 승인 요청" 버튼만 있고 "확정" 버튼 없음 — D10·D18) | TBD — 촬영 후 실측 기입 |
| 2 | 화면A (컷1과 같은 세션, 다음 턴) | 동일 URL(세션 유지) | "A사로 진행해줘" (A2 — 공급사 선택 발화가 있는 **다음 턴**에서만 `create_po_draft` 호출) | `create_po_draft` 호출이 trace에 새로 추가되는 것·발주 카드가 "승인 요청" 버튼(라벨 실측: `팀장 승인 요청`, `PoDraftCard.tsx`)만 노출하고 확정 버튼이 없는 것(D10·D18 — 사람 승인 전 상태 전이가 없음을 시각적으로 증명) | TBD — 촬영 후 실측 기입 |
| 3 | 화면A 라이브(새 세션 또는 새 탭) | `http://localhost:3003/technician` | **장비 미선택 상태로** "S100 인버터 제어보드 교체해야 해" 입력(S2 원문 — 진단 없이 중간 진입하는 의도적 엔트리 포인트) | `search_inventory` 결과 `qty:0`+단종(`PCB-S100-CTRL`)·`find_alternative_parts`가 호환 확정 대체품(`PCB-S100-CTRL-R2`, `compat_confirmed:true`) 제시·원부품 대신 대체품 리드타임·단가 비교(공급사 SUP-A vs SUP-C) 후 사용자 선택 유도 | TBD — 촬영 후 실측 기입 |
| 4 | 화면A — **라이브/목업 중 드라이런 후 확정**(아래 §2 참조) | 라이브: `http://localhost:3003/technician` (장비 `INV-L3-01` 선택) · 목업: `http://localhost:3003/technician?scenario=s3` | "3번 라인 인버터 또 OCt 떴어" (S3 원문) | 반복 감지 배너(`repeat_banner`/`RepeatFaultBanner` — "30일 내 3회")·안전 경고(방전 대기 "10분 이상", 활선 측정 금지, 매뉴얼 근거 표기)·발주 카드 자리에 **발주 보류 블록**(`po_card` variant `hold` — 발주 카드가 아님을 명시, D35·A8) | TBD — 촬영 후 실측 기입 |
| 5 | 화면A 라이브(새 세션) | `http://localhost:3003/technician` | "XY9 에러가 떴는데" (S4 원문 — iG5A 매뉴얼 65건에 부재 실측 확인됨, `sprint-5.md` 사전조사) | `lookup_error_code` → `status:"not_found"` 이후 유사 코드 추측 없이 "매뉴얼에서 확인되지 않는 코드" 명시 + A/S 안내(원인·조치 서술 없음 — 환각 0% 시연) | TBD — 촬영 후 실측 기입 |
| 6 | 화면B | `http://localhost:3003/manager/po/PO-0117` | 페이지 로드만(딥링크 접속) — 큐 목록에서 `PO-0117`이 선택된 상태로 바로 뜸 | 근거 요약 카드(`EvidenceCard` — SYMPTOMS·DIAGNOSIS(인용 칩 포함)·INVENTORY·NOTES 행, 대화 전체를 안 읽어도 판단 가능함을 시연, D18)·`TRACE` 행의 "에이전트 실행 로그 전체 보기 →" 링크 클릭 → `/manager/trace/{session_id}`로 이동해 timeline 확인·승인/반려 버튼(`승인 — 발주서 확정` / `반려 (사유 입력)`) | TBD — 촬영 후 실측 기입 |
| 7 | 화면B(정비사 역할로 강제 호출) | 터미널(curl) — UI에는 해당 버튼이 없음(아래 참고) | ```curl -i -X POST http://localhost:8000/api/po/PO-0117/approve -H "X-Role: technician" -H "X-User: tech-01"``` | HTTP 403 응답 (`backend/deps.py`의 `require()`가 반환하는 메시지: `발주 승인 은(는) manager 만 수행할 수 있습니다 (요청자 역할: technician)`) — human-in-the-loop이 UI가 아니라 **서버가 강제**함을 증명(06_REPO_API §2.2 403 규칙) | TBD — 촬영 후 실측 기입 |

### 컷7 보충 설명 — 왜 UI가 아니라 curl인가

`frontend/README.md`·`lib/role.ts` 확인 결과 **역할은 라우트가 결정**한다 — `/manager/*` 라우트는
항상 `X-Role: manager`로 호출하고, `/technician` 화면에는 승인/반려 버튼(`DecisionBar`) 자체가
없다. 즉 "정비사 계정으로 승인 화면에서 버튼을 눌러본다"는 프론트 UI 경로가 실재하지 않는다
(지어낼 수 없음). 403이 **UI 버튼이 없어서가 아니라 서버 권한 검사(`require()`)가 막아서**임을
증명하려면 API를 직접 호출해야 하므로, 화면 녹화 중 터미널 창(또는 브라우저 개발자 도구
Network 탭에서 동일 요청을 수동 전송)을 함께 잡아 curl 응답을 보여주는 방식을 쓴다. 화면 B가
떠 있는 상태에서 나란히 보여주면 "이 화면이 막는 게 아니라 서버가 막는다"는 대비가 산다.

---

## 2. 컷4 라이브 vs 목업 — 드라이런 후 결정 (양쪽 다 실재 경로 확인 완료)

두 경로 모두 코드상 실재한다:

- **라이브**: `frontend/app/(console)/technician/page.tsx`가 쿼리 없이 접속하면
  `DiagnosticConsole mode="live"`를 렌더한다. `INV-L3-01`(iG5A, 3번 조립라인 반송 컨베이어)은
  `data/seed.py`가 실측으로 보장하는 "30일 내 OCT 정확히 3회" 조합이고, `backend/agent/prompts.py`
  191행에 "반복 고장이면 발주 보류 (S3·D35·A8)" 규칙이 시스템 프롬프트에 이미 박혀 있다 —
  즉 배선은 돼 있다. 다만 LLM(Gemini)이 매 실행 매번 이 규칙을 정확히 따라 `po_card
  variant:"hold"` block까지 끝까지 내는지는 결정적이지 않다(비결정적 생성 모델의 한계).
- **목업**: `frontend/app/(console)/technician/page.tsx`가 `?scenario=s3`를 받으면
  `DiagnosticConsole mode="mock"`으로 `CHAT_S3`(`frontend/lib/mock/scenarios.tsx`)를 그대로
  렌더한다 — 반복 배너·안전 경고·발주 보류 카드가 **항상 같은 모양**으로 나온다.

**결정 절차**: 촬영 당일, 컷4를 라이브로 먼저 1~2회 드라이런한다.
- 라이브가 매 시도 `po_card variant:"hold"`까지 정확히 도달하면 → **라이브로 촬영**(실제 동작
  증명이라 설득력이 더 크다).
- 라이브가 흔들리면(예: 발주 보류 대신 일반 발주 카드를 내거나, 안전 경고가 누락되는 등) →
  **`?scenario=s3` 목업으로 촬영**하고, 영상 자막/설명에 "S3 흐름의 목업 재현 — 실 배선은
  `backend/agent/prompts.py`·회귀 스위트로 검증됨"을 명시한다. 조용히 목업을 라이브인 것처럼
  보여주지 않는다(`ApprovalQueueScreen`의 "목업 데이터" 배너와 같은 정직성 원칙).

---

## 3. 주의사항 — 라이브 경로 실패 시 대체 방법

- **공통**: 라이브 컷(1·3·4·5)이 그날 Gemini API 상태(요금 한도·타임아웃·모델 변경)에 따라
  실패하면, 같은 컷을 **최대 2회 재시도**한다. 재시도로도 실패하면:
  - 컷1·2(S1)·컷4(S3): `?replay=s1`(컷1·2) 또는 `?scenario=s3`(컷4) 로 대체 촬영하고 자막에
    "재생/목업 데모" 명시.
  - 컷3(S2)·컷5(S4): 현재 이 두 시나리오는 스크립트 확인 시점 기준 목업 데이터가 없다
    (`frontend/lib/mock/scenarios.tsx`의 `Scenario` 타입은 `"s1" | "s3"`뿐). 라이브가 실패하면
    **당일 촬영을 중단하고 API 상태 복구 후 재시도**한다 — 목업으로 대체할 실재 경로가 없다
    (없는 경로를 지어내지 않는다).
- **컷2 특이사항**: `PO-0117`은 시드 재적재 시 항상 `state:"pending"`으로 초기화된다
  (`data/seed.py` `seed_po_drafts`). 컷1→2를 리허설로 이미 한 번 통과시켰다면, 재촬영 전
  `uv run python data/seed.py --with-error-codes`로 상태를 되돌린 뒤 컷1부터 다시 찍는다 —
  이미 `pending`인 PO에 다시 `submit`을 호출하면 409가 뜬다(정상이지만 컷2의 "승인 요청" 연출과
  다른 화면이 나온다).
- **컷6 링크 대상**: `PO-0117`이 이미 `pending` 상태여야 `/manager/po/PO-0117`이 정상적으로
  뜬다(컷2를 라이브로 정상 완주했거나, 시드 기본값을 그대로 뒀다면 자동으로 만족). `approved`/
  `rejected`로 이미 전이됐다면 재적재로 되돌린다.
- **컷7 curl 실패 시**: 백엔드가 살아있는데 403이 아니라 다른 코드가 나오면(예: 404 — `PO-0117`이
  없음) 촬영 전 `GET http://localhost:8000/api/po?state=pending`으로 실제 존재하는 `po_id`를
  먼저 확인하고 그 값으로 치환한다.
- **네트워크/화면 녹화 툴**: curl 대신 브라우저 개발자 도구 Network 탭에서 "Copy as fetch" →
  `X-Role`을 `technician`으로 바꿔 콘솔에서 재전송하는 방식으로도 동일한 403을 보여줄 수 있다
  (터미널 창을 화면에 노출하고 싶지 않을 때의 대안 — 이 문서가 강제하는 방법은 아니다).

---

## 4. 촬영 순서 요약 (문서 §1 표와 동일, 빠른 참조용)

S1(컷1~2) → S2(컷3) → S3(컷4) → S4(컷5) → 화면B 근거·승인(컷6) → 권한 위반 증명(컷7)
— `docs/01_OVERVIEW.md` §10, `docs/02_SCENARIOS.md`가 명시하는 "S1→S2→S3→S4 순"을 그대로 따른다.
