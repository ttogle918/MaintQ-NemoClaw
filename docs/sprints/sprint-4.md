# Sprint 4 — M3 마무리: 화면 A 배선 + 표시 규약 정리

**수립**: 2026-07-28 · **선행 상태**: Sprint 3 종료(회귀 241건), D54~D56 확정,
실 Gemini 1턴 스모크(C-5) 관통 완료. `error_codes` 는 여전히 0행(사람 승인 대기).

**목표**: `00_MVP_SCOPE §6`(trace 시각화)·"UI 2종" 중 남은 **화면 A(진단 콘솔)를 실 SSE 로
배선**하고, Sprint 3 이월 표시 결함(N-c·N-b·W-6·error 색 리터럴·replay 표식 표시)을 정리해
**M3 를 종료**한다.

**이번 스프린트의 성격**: **전 태스크가 frontend/ 전용.** 백엔드·MCP·계약(`04_MCP_TOOLS`·
`06_REPO_API`)을 한 줄도 건드리지 않는다 → 회귀 241건(전부 Python)은 구조적으로 계속
통과하고, **신규 D 결정이 필요한 태스크가 없다**. D54·D55·D56 이 필요한 계약을 전부 깔아 놨다.
frontend 변경이 깨뜨릴 수 있는 정적 검사는 `tsc --noEmit`·`next build` 2종뿐이다.

## 블로커 검토

| 블로커 | 이번 스프린트 영향 |
|---|---|
| `error_codes` 사람 승인 대기 (0행) | **막지 않는다** — 화면 A 데모 경로는 `?replay=s1`(D55, LLM·error_codes 불요, chat.py `_replay_s1` 은 하드코딩 이벤트 + traces INSERT 만). 실 루프는 `catalog_not_loaded` 를 정직하게 표시하는 것 자체가 D50 의 올바른 동작 — **라이브 DoD 를 "정직한 실패 확인"으로 한정**해 승인 대기에 스프린트가 막히지 않게 한다 |
| API 키 | **해소됨** (D56, Gemini 스모크 관통). 실 루프 UI 검증은 키 있는 환경의 수동 체크 항목 |
| related_parts 검수 | 무관 (평가 실적 인용은 범위 밖) |
| 임베딩 (D51) | 무관 |

## 범위 밖 (의도적)

- `/api/po/{id}` 에 `print_page` 계약 추가 — W-6 근본 해소. **D 선행 필요**라 이번엔
  계약-무변경 라벨 정직화(MQ-403)까지만
- `tool_result` summary 의 `✗ timeout ·` 접두를 백엔드에서 제거 — traces 저장값 변경
  = D44 개정 + 회귀 수정이라 기각. 표시 측 중복 제거(MQ-401)로 해소
- 환각률 LLM judge · `eval/testset.json` 20문항 · 실 DB 채점 배선(`has_replay` 분모 제외) — M4
- `AnthropicClient` 실 API 검증 — 키 없음, 사람 항목
- `07_BACKLOG` P1~P21 승격 없음 — `VoiceBar`(P8)·(P1)은 자리만 유지, 배선하지 않는다

---

## Sprint 4 최종 실행 계획

| 스테이지 | 태스크 | 병렬 | 예상 결과물 |
|---------|--------|-----|-----------|
| Stage 1 | MQ-401, MQ-402, MQ-403 | ✅ (파일 교집합 없음, 실측 확인) | trace 표시 규약 정리 + replay 배지 · 실 입력 composer · 정직한 인용 라벨 |
| Stage 2 | MQ-404 | — | SSE 리듀서 (`lib/chatStream.ts`, 순수 로직) |
| Stage 3 | MQ-405 | — | 화면 A 라이브 관통 (?replay=s1 데모 + 실 루프) |

선행 관계:

```
MQ-401 ─┬─► MQ-404 ─► MQ-405
MQ-403 ─┘                ▲
MQ-402 ──────────────────┘
```

### 스테이지 구성 근거

- **Stage 1 세 태스크는 파일이 완전히 분리** — 401={trace.ts, types.ts, TraceStep, TracePanel,
  globals.css} / 402={ChatComposer} / 403={citation.ts, CitationChip, mappers.tsx}. 교집합 없음
  (tool-builder 실측). 전부 세션 로그 이월 결함이라 최우선 배치 원칙에 맞고, 사람 승인·키
  어느 쪽에도 막히지 않는다.
- **MQ-404 를 Stage 1 에 못 넣는 이유**: 리듀서가 쓸 스텝 매핑 헬퍼의 export 는 MQ-401 소유,
  `Citation.label` passthrough(+`manual` optional 완화)는 MQ-403 소유. 매핑 로직을 리듀서에
  복제하는 대안은 기각 — 화면 A 와 화면 B 가 같은 이벤트를 다른 스텝으로 그리면 감사 화면의
  신뢰가 깨진다.
- **MQ-405 분리 이유**: 404 는 React 없는 순수 로직(타입·코드 리뷰로 검증), 405 는 훅·라우트·
  브라우저 육안 검증 — 검증 단위가 다르다.
- **Stage 2·3 단일 태스크는 의도** — 임계 경로가 401/403 → 404 → 405 한 줄이고, 억지 병렬
  상대를 만들면 DiagnosticConsole 충돌이나 백로그 승격뿐이다.
- 매 스테이지 검증: `tsc --noEmit`·`next build` + 회귀 241건(백엔드 무변경 확인 겸용).
  Stage 1 은 화면 B 육안, Stage 3 은 `?replay=s1` 관통 육안 추가.

---

## 태스크별 상세 구현 명세

> 표시가 붙은 항목은 tool-builder 현실성 평가에서 보강된 것 — 구현 시 누락 금지.

### MQ-401 — trace 표시 규약 정리 + replay 배지

- **복무 시나리오**: S1·S3 (trace 패널은 전 시나리오의 판정·감사 표면)
- **변경 파일**: `frontend/lib/trace.ts` · `frontend/lib/types.ts`(TraceSession 필드 1개 추가만)
  · `frontend/components/trace/TraceStep.tsx` · `frontend/components/trace/TracePanel.tsx`
  · `frontend/app/globals.css`(토큰 추가만)
- **인터페이스**:
  - `types.ts`: `TraceSession` 에 `replay?: boolean` 추가 (기존 필드 의미·이름 변경 금지 —
    mock 데이터가 그대로 컴파일돼야 한다)
  - `trace.ts` 신규 export 3종 (MQ-404 의 입력 계약):
    - `stepFromCall(tool: string, input: unknown): TraceStepData` — 현행 tool_call 분기 본문 추출
    - `stepPatchFromResult(data: Record<string, unknown>): { summary: string; status: TraceStatus }`
      — 현행 `formatSummary`+`stepStatus` 묶음
    - `isHoldCard` 기존 함수 export 승격, `HOLD_STEP` 도 export
  - `toTraceSession` 시그니처 불변, 내부를 위 함수로 재조립
- **핵심 로직**:
  1. **N-c (이중 `✗` 제거)**: **범위 한정 — status 가 `error` 인 행의 summary 선두 `"✗ "`
     접두를 표시용으로만 제거한다. 요약 문자열 재작성 금지.** 붉은 점 글리프 `✗` 는 유지
     (09_RUNTIME §3). traces 저장값·백엔드 불변 — 저장값 자기설명성(D44)은 그대로이고
     렌더에서 같은 정보의 중복만 지우는 것이라 D 불요. docstring 에 이 근거를 남길 것
  2. **replay 감지 (D55)**: `toTraceSession` 이 `ev.data.replay === true` 를 세어 1건 이상이면
     `session.replay = true`
  3. **N-b (elapsed 두 의미 분리)**: **전 이벤트가 replay** 면 meta `"{calls} calls · 재생"`
     (합성 elapsed 를 실측인 양 합산 표시하지 않는다). 혼재면 `"{elapsed}s · {calls} calls"`
     유지 + 배지로 구분. 전부 실 행이면 기존 그대로
  4. **TracePanel 배지**: `session.replay` 참이면 세션 헤더 label 옆 모노 배지 `재생 데이터`.
     색은 `var(--dim2)` 계열 회색 테두리 — 오렌지는 안전·긴급 전용, 파랑은 정상 실행.
     화면 A·B 가 같은 TracePanel 을 쓰므로 두 화면 동시 적용 (D55 채택 사유의 마지막 조각)
  5. **error 색 토큰화**: `globals.css` 4테마(`.app-root` dark / `dgray` / `gray` / `light`)에
     `--error-dot:#C0392B; --error-tx:#D64545;` 추가(4테마 동일값). `TraceStep.tsx` 의
     `ERROR_DOT`/`ERROR_TX` 리터럴을 `var()` 로 교체, 리터럴 상수·주석 제거.
     라이트 2테마(gray·light)용은 **신규 선정값**이므로 4테마 육안 확인이 DoD
- **엣지 케이스**: `data.replay` 가 boolean `true` 아닌 truthy → false 취급 (계약은 boolean,
  D55 — 지어서 넓히지 않는다). summary 가 `"✗"` 한 글자 → strip 후 비면 status 문자열 폴백.
  mock 데이터는 replay 필드 없음 → 배지 없음, 기존 화면 무변화
- **지켜야 할 결정**: D44(5종 상태 의미·색 변경 금지) · D46(reason 판별 시도 금지) ·
  D55(표식 읽기 전용) · D21·D30(저장값 무변경)
- **DoD**: `tsc`·`next build` 통과 · 회귀 241건 통과 · 육안: 재생 세션 trace 에서
  ① `재생 데이터` 배지 ② meta `4 calls · 재생` ③ 타임아웃 행 `✗` 1회만
  ④ error 색 **4테마 전부** 가독

### MQ-402 — ChatComposer 실 입력 활성화

- **복무 시나리오**: S1 (전 시나리오 진입 입력 표면)
- **변경 파일**: `frontend/components/chat/ChatComposer.tsx` 단독
- **인터페이스**: `{ onSend?: (text: string) => void; disabled?: boolean; placeholder?: string }`
  **전부 옵셔널** — DiagnosticConsole 이 Stage 3 전까지 `<ChatComposer />` 로 부른다
- **핵심 로직**: placeholder div → `<input type="text">`(기존 `--field` 토큰 스타일).
  Enter + 전송 버튼 두 경로, 전송 후 입력 비움. **한글 IME 조합 가드 필수**
  (`isComposing`/keyCode 229 시 Enter 무시). `disabled` 면 비활성 + "응답 생성 중…".
  ·는 자리만 유지 (P8·P1 승격 금지)
- **엣지 케이스**: 공백만 → 전송 안 함. `onSend` 미지정(mock) → 무동작이되 입력은 가능
- **DoD**: `tsc`·`next build`. 육안: 한글 조합 중 Enter 이중 전송 없음.
  `?scenario=s1` mock 화면 기존과 동일

### MQ-403 — 인용 라벨 정직화 (W-6 표시측) + SSE label passthrough

- **복무 시나리오**: S1·S2 (화면 B 근거 카드 = 승인 판단 근거, passthrough 는 화면 A 전제)
- **변경 파일**: `frontend/lib/citation.ts` · `frontend/components/ui/CitationChip.tsx`(key 만)
  · `frontend/lib/mappers.tsx`(주석 정합만)
- **인터페이스**: **`Citation.manual` 을 optional 로 완화한다** — SSE 인용 payload 는
  `{page, print_page, label}` **뿐**이라(backend/sse.py `citation_data`, manual·section 필드
  없음) manual 이 required 면 Stage 2 리듀서가 값을 지어내거나 tsc 에러가 난다. 이걸 지금 안
  하면 404 가 Stage 2 에서 403 소유 파일을 재수정하는 순서 위반이 생긴다 (tool-builder 실측):
  ```ts
  export interface Citation {
    manual?: string;      // label 있으면 생략 가능
    page: number;         // PDF 물리 — 불변 (D26)
    printPage?: number;
    section?: string;
    /** 백엔드가 조립한 표시 라벨 (sse.citation_data). 있으면 재조립 금지 (D32) */
    label?: string;
  }
  ```
- **핵심 로직**:
  1. `citationLabel(c)`: `c.label` 있으면 **그대로 반환** — 라벨 조립은 백엔드 렌더 1곳(D32)
  2. label 없고 `printPage` 도 없으면(= `/api/po/{id}` evidence 경로, 인쇄 페이지 미상) →
     **`"{manual} PDF p.{page}"`** 병기 — W-6 의 계약-무변경 해소. 프론트는 offset 을 모르므로
     "PDF" 표기가 유일하게 정직하다
  3. label 없고 `printPage` 있으면 기존 규칙 유지 (`p.{print}` + 다르면 `(PDF p.{page})`)
  4. `CitationRow` key = `${c.label ?? c.manual}-${c.page}`
  5. `mappers.tsx` `firstCitation` docstring 한 줄 갱신 (근본 해소는 D 선행 필요)
- **엣지 케이스**: manual·label 둘 다 없으면 `"매뉴얼 PDF p.{page}"` 폴백 (빈 라벨 금지).
  `printPage === page` 명시 제공 → `p.X` (병기 불요)
- **지켜야 할 결정**: D26 · D32 · W-6 근본 해소는 D 선행이라 범위 밖
- **DoD**: `tsc`·`next build`. 육안: `/manager/po/PO-0117` DIAGNOSIS 칩이
  `"iG5A 매뉴얼 PDF p.202"` 로 **바뀌는 것이 정상** (mappers 가 printPage 를 안 넣으므로 —
  화면 B 체크리스트에 포함). 목업(scenarios·queue)은 printPage 명시라 무영향

### MQ-404 — SSE 스트림 리듀서 (`lib/chatStream.ts` 신규)

- **복무 시나리오**: S1~S4 — 이벤트 4종(D14·D22)→화면 A 렌더 단위 변환의 유일 지점
- **변경 파일**: `frontend/lib/chatStream.ts` 신규. **React import 금지** (순수 로직 + fetch 러너)
- **인터페이스**:
  ```ts
  export interface ChatStreamState {
    items: ChatItem[]; trace: TraceSession; streaming: boolean; error?: string;
  }
  export function initialState(sessionId: string): ChatStreamState;
  export function reduceChatEvent(s: ChatStreamState, e: SseEvent): ChatStreamState; // 순수
  export function runChatTurn(opts: {
    sessionId: string; message: string; equipmentId: string | null;
    replay?: "s1"; signal?: AbortSignal; onState: (s: ChatStreamState) => void;
  }): Promise<void>;
  ```
- **핵심 로직** (payload 계약 = backend/sse.py·chat.py):
  1. `token`: 열린 agent 버블에 이어붙임, 없으면 새 버블. **버퍼링 금지** — block 이 token
     사이에 끼는 순서(D22)가 배열 순서로 보존돼야 안전 경고가 위험 서술보다 먼저 보인다
  2. `tool_call`: `stepFromCall`(MQ-401) 로 pending 스텝 push, calls +1, 열린 버블 닫기
  3. `tool_result`: trace.ts 와 **같은 FIFO 페어링**(같은 tool 의 가장 이른 pending 스텝)으로
     `stepPatchFromResult` 적용. `replay===true` 면 `trace.replay=true` + elapsed 합산 제외
     (meta 규칙 MQ-401 과 동일). `pages` 필드는 표시에 안 쓰지만 파싱을 깨지 말 것
  4. `block safety`: `{kind:"safety", title, body, citation: toCitation(...)}`.
     `toCitation`: `{page, print_page, label}` → `{page, printPage, label}` (스네이크 변환
     명시). **라벨 재조립 금지** (MQ-403 passthrough)
  5. `block citation`: 가장 최근 agent item 의 `citations` 에 부착. 앞에 agent 가 없으면 빈
     agent 를 만들어 부착 — **인용을 조용히 버리지 않는다**
  6. `block po_card draft`: camelCase 매핑 → `{kind:"po_draft"}`. 누락 키는 지어내지 않고
     `0`/`""` (카드 안 깨지게)
  7. `block po_card hold` (D45): `{kind:"po_hold", hold:{reason, checklist(각 citation →
     toCitation)}}`. **`repeat_banner` 는 리듀서 산출물이 아니다** — hold payload 의
     `repeated` 는 hold 카드 안에 렌더될 뿐, 별도 배너를 만들 구조화 소스(도구 결과)가
     스트림에 없다. S3 라이브에서 배너 없이 hold 카드만 뜨는 것이 **의도**임을 주석으로 명시
     (나중에 summary 파싱 같은 우회 금지). **hold 를 po_draft 로 렌더 금지** (D35)
  8. **error_log 액션**: `lookup_error_code` 의 tool_result `status:"ok"` 시 —
     `code` 는 payload 에 없으므로 **FIFO 로 짝지어진 tool_call 의 `input.code` 에서** 꺼낸다.
     `equipmentId` 가 null 이면 **push 하지 않는다(스킵)**. 같은 (equipmentId, code) 중복
     push 금지. push 는 버튼 표시일 뿐, 기록은 사용자 클릭(D29·A7)
  9. `runChatTurn`: POST `/api/chat`(+`?replay=s1`) → `!res.ok` 면 `error:"API {status}"` →
     `readSse` → reduce → `onState` → 완료 시 `streaming:false`
- **엣지 케이스**: JSON 파싱 실패 이벤트 → 무시 + `console.warn` (조용한 유실 금지).
  AbortError → error 아님, `streaming:false` 만. 네트워크 실패 → error + 기존 items 유지.
  block type 3종 밖 → 렌더 안 하고 warn
- **지켜야 할 결정**: D14·D22 · D35·D45 · D29·A7 · D32(라벨 재조립 금지) · D55(읽기 전용) · D9
- **DoD**: `tsc`·`next build`. `reduceChatEvent` 순수성 코드 리뷰. `_replay_s1` 이벤트 시퀀스
  (도구 4쌍 · token · citation · safety · po_card draft — chat.py 가 픽스처 명세)를 주석에
  기대 결과로 명시 → Stage 3 육안 채점표

### MQ-405 — 화면 A 라이브 배선 (replay 데모 + 실 루프)

- **복무 시나리오**: S1~S4 (진단 콘솔 = 정비사 진입점, M4 데모 영상 주 화면)
- **변경 파일**: `frontend/components/screens/DiagnosticConsole.tsx` ·
  `frontend/components/screens/useChatStream.ts` 신규 · `frontend/app/(console)/technician/page.tsx`
- **인터페이스**:
  ```ts
  export function useChatStream(sessionId: string): {
    state: ChatStreamState;
    send: (message: string, equipmentId: string | null, replay?: "s1") => void;
  };  // 내부: AbortController, 언마운트 abort, streaming 중 send 무시
  type ConsoleMode = { mode: "mock"; scenario: Scenario } | { mode: "live"; replay?: "s1" };
  ```
- **핵심 로직**:
  1. 라우트 분기: `?scenario=s1|s3` → mock **보존** (S3 는 error_codes 승인 전 유일한 그림) ·
     `?replay=s1` → live+replay · 없음 → live
  2. 세션 ID: 로드마다 `S-{Date.now().toString(36)}` (ASCII, D36). 재생도 매번 새 세션 —
     같은 세션에 재생을 거듭 흘리면 seq 이어붙어 타임라인이 계속 자란다
  3. live 렌더: `ChatThread` + `TracePanel` 이 같은 state (D14 동기가 그대로 화면).
     `ChatComposer disabled={streaming}`. `error` 는 `StatusBanner tone="error"`
  4. replay 데모: mount 시 1회 자동 send("iG5A 인버터에 OHt 에러가 떴어").
     **StrictMode 이중 mount 가드(ref) 필수** — dev 에서 POST 2회 나가면 같은 세션 seq 에
     타임라인이 2벌 append 된다(TraceWriter MAX(seq)+1 이어쓰기)
  5. 장비 선택기: `getEquipment()` 기반 select (SelectChip 스타일). 조회 실패 시
     `equipment_id: null` 전송 — 에이전트가 모델 확인 질문(06_REPO_API §2.1). 기본값 지어내기 금지
  6. 실 루프 실패는 백엔드 안내 token 을 agent 버블로 그대로 — **mock 폴백 금지** (D40 원칙)
  7. `requestApproval` 409 처리: 재생 데모의 PO-0117 은 DB 상 `pending` 이라 409 가 정상 →
     toast `"이미 요청된 발주입니다 — 재생 데모 데이터"` (403/409 구분은 D38 의미대로)
- **엣지 케이스**: 스트리밍 중 이탈 → abort, 콘솔 에러 0 (백엔드는 D42 라 취소 안전).
  `?replay=S1` 오타 → live 기본 (백엔드 400 을 애초에 유발하지 않음). 스트리밍 중 send → 무시
- **지켜야 할 결정**: D40 · D36 · D23 · D10·D18(카드에 "확정" 버튼 금지) · D55 · D6·D13
- **DoD**: `tsc`·`next build` · 회귀 241건. 육안 체크리스트 (라이브 DoD 는 error_codes
  승인에 **비의존** — 해피패스 육안은 replay 경로 한정):
  1. `/technician?replay=s1` → 도구 4스텝 pending→ok 순차(A1), 안전 블록이 "커버를 열고…"
     **이전**(D22), 인용 칩 `iG5A 매뉴얼 p.202`, PO 카드, meta `4 calls · 재생` + 배지
  2. `/technician` 키 없음 → 안내 문구 agent 버블, 빈 화면·정지 없음
  3. `/technician?scenario=s3` → 기존 목업과 동일
  4. (키 있는 환경 1회) live 1턴 — tool_call/result 실시간 표시, lookup 이
     `catalog_not_loaded`(error·붉은 점)로 **정직하게** 표시
  5. 스트리밍 중 라우트 이동 → 콘솔 에러 없음

---

## tool-builder 현실성 평가 (수립 시점)

명세가 언급한 심볼 전수 실측 — trace.ts 비공개 헬퍼·ChatItem kind 7종·readSse/authHeaders/
getEquipment·replay 주입·PO-0117 pending(409)·replay 무DB 경로 전부 실재 확인.
Stage 1 파일 교집합 없음.

| 스테이지 | TASK | 리스크 | 처리 |
|---------|------|--------|------|
| 1 | MQ-401 | 하 — N-c 범위·라이트 테마 색 신규 선정 | 명세에 반영 (표기) |
| 1 | MQ-402 | 하 — props 옵셔널 필수 | 반영 |
| 1 | MQ-403 | 중 — SSE payload 에 manual 없음 → `Citation.manual` required 면 Stage 2 가 403 파일 재수정 | **manual optional 완화를 Stage 1 로 이동** (반영) |
| 2 | MQ-404 | 중 — error_log 의 code 소스 부재·repeat_banner 소스 부재·스네이크 변환 | 명세에 반영 |
| 3 | MQ-405 | 중 — StrictMode 이중 mount POST 2회·라이브 DoD 가 error_codes 에 막힐 뻔 | ref 가드·DoD 분리 반영 |

**결론**: 구조 그대로, 명세 보강 4건 반영 완료. 계약(D 문서) 변경 불필요.

## 종료 시 상태 (예상)

- **M3 완료**: 화면 A(라이브 SSE + replay 데모) / 화면 B(Sprint 3) / 표시 규약 정리
- 회귀 241건 유지 + `tsc`·`next build`
- 다음(M4) 전 사람 항목: `error_codes` 승인 · `related_parts` 검수 · 안전 문안 검수 ·
  `DANGER_KEYWORDS` 확장 검수 · W-6 근본 해소 D(`/api/po/{id}` print_page) 여부 결정
- M4 후보: `eval/testset.json` 20문항 + 실 DB 채점 배선(`has_replay` 분모 제외) ·
  환각률 LLM judge · 데모 영상 · README

실행: `/stage 1`

---

## Stage 1 완료 (2026-07-28)

**커밋**: `25b0a98` — `[M3] Sprint 4 Stage 1 — trace 표시 규약·replay 배지 · composer 실 입력 · 인용 라벨 정직화`

#### MQ-401
- `frontend/lib/trace.ts` · `lib/types.ts` · `components/trace/TraceStep.tsx` ·
  `components/trace/TracePanel.tsx` · `app/globals.css`
- Stage 2 계약 export 확정: `stepFromCall(tool, input)` ·
  `stepPatchFromResult(data) → {summary, status}` · `isHoldCard` · `HOLD_STEP`
- 구현 해석 1건: **혼재 세션 elapsed 합산에서 replay 행 제외** — MQ-404 명세의
  "replay===true 면 elapsed 합산 제외" 문구와 정합을 맞춘 것. 의도와 다르면
  trace.ts 의 `if (ev.data.replay !== true) elapsed +=` 한 줄 되돌리면 됨

#### MQ-402
- `frontend/components/chat/ChatComposer.tsx` 단독
- 구현 해석 1건: `onSend` 미지정 시 "무동작"을 no-op 으로 — 입력 텍스트 유지

#### MQ-403
- `frontend/lib/citation.ts` · `components/ui/CitationChip.tsx` · `lib/mappers.tsx`
- **명세 문면 불일치 기록** (reviewer 참고 1): 명세는 mappers 를 "주석 정합만"이라
  썼으나 실제로는 `firstCitation` 의 `printPage: page` 지정 제거가 필요했다(코드 1줄).
  같은 명세의 DoD 가 "mappers 가 printPage 를 안 넣으므로 라벨이 바뀐다"고 명시해
  문면끼리 모순 — 구현은 DoD·D32(물리를 인쇄인 양 표시 금지) 쪽을 따랐다
- label 우선 시 section 무시 — 백엔드 label 이 section 을 이미 포함(sse.py)하므로
  이중 표기 방지. reviewer 타당 판정

#### 회귀
- 241건(16스위트) + ruff + `tsc --noEmit` + `next build` 전 통과 · reviewer PASS
  (블로커 0 · 경고 0 · 참고 3)
- Stage 2 인계 사항: `types.ts:107` 의 repeat_banner 주석이 MQ-404 명세("배너 없음이
  의도")와 표현 불일치 — MQ-404 구현 시 주석 정합 필요 (reviewer 참고 2)

#### 수동 검증 (2026-07-28, Claude in Chrome 브라우저 자동화)

**전부 확인 (✅)**
- `/manager/trace/S1`(재생 세션 주입) — `재생 데이터` 회색 배지 · meta `4 calls · 재생`
  (초 표기 없음) · 도구 4스텝 렌더
- `/manager/trace/SERR`(상태 혼합 주입) — timeout 행 `✗` **글리프 1회만** + summary
  "timeout · …"(접두 제거, N-c 해소) · meta `10.5s · 4 calls` 실측 형식 · 배지 없음 ·
  ok/error/warn/pending 4상태 구분 렌더
- error 색 **4테마 전부 가독** (다크·다크그레이·그레이·라이트 — 라이트 2테마 신규 확인)
- `/manager/po/PO-0117` live — DIAGNOSIS 칩 `매뉴얼 PDF p.202` (**"PDF" 병기 적용**,
  W-6 표시측 해소. "iG5A" 접두가 없는 건 시드의 `model=NULL` 때문 — firstCitation 구현대로)
- `/technician?scenario=s1`·`s3` 목업 — 기존과 동일 (안전 블록·HOLD 카드·held 행 무변화)
- composer — 한글 입력 정상 표시, Enter 후 무동작·텍스트 유지(mock no-op 구현대로), 크래시 없음.
  ※ 실 IME 조합 이중 전송은 자동화로 재현 불가(CDP 는 조합 이벤트를 안 태움) — 사람 확인 항목으로 유지

**검증이 잡은 결함 → 핫픽스 (스테이지 밖 백엔드 수정)**
- **`.env` 의 빈 키가 기본값을 지움 (D56 구현 결함)** — `.env.example` 복사로 생긴
  `MAINTQ_CORS_ORIGINS=`(빈 값)을 dotenv 가 빈 문자열로 로드 → `.get(키, 기본값)` 패턴이
  "설정됨"으로 인식 → CORS 기본 범위(3000~3005)가 전멸해 브라우저 fetch 전부 실패.
  `or` 패턴으로 수정(main.py CORS·MCP_AUTOSTART, llm.py provider — db.py·rag.py 는 원래
  `or` 패턴이라 안전). 음성 검증 ⑬⑭ 를 llm_provider_contract 에 추가 (12→14건, 총 243건)

---

## Stage 2 완료 (2026-07-28)

**커밋**: `14596ee` — `[M3] Sprint 4 Stage 2 — SSE 스트림 리듀서 (lib/chatStream.ts)`

#### MQ-404
- `frontend/lib/chatStream.ts` (신규, 434줄) · `frontend/lib/types.ts`(repeat_banner 주석 1줄)
- **구현 결정 (reviewer 수용 3건)**:
  1. **trace 를 `toTraceSession` 통째 재계산** — 리듀서가 `stepFromCall`/`stepPatchFromResult`
     를 직접 부르는 대신, tool/block 이벤트를 `ApiTraceEvent[]` 로 누적 후 매 이벤트마다
     `toTraceSession()` 재계산. FIFO·replay·N-b meta·HOLD_STEP 로직이 한 곳(MQ-401)에서만
     나와 "화면 A·B 가 같은 스텝"(스테이지 구성 근거)에 **더 정합**. 명세 이탈 아님
  2. **`ChatStreamState._ctx` 내부 필드** — 공개 4필드(items/trace/streaming/error)는 명세대로,
     페어링 상태·equipmentId 는 `_ctx`(readonly, 매 reduce 마다 신규 생성). 순수 2-인자
     리듀서 유지용. 소비자는 4필드만 읽음
  3. **`runChatTurn` 이 user 버블 seed** — 명세 침묵 부분. 사용자 입력 문장이 화면에 남게
     러너가 `{kind:"user"}` 를 심음
- 회귀: 243건(16스위트) + ruff + `tsc --noEmit` + `next build` 전 통과 · reviewer PASS
  (블로커 0 · 경고 0 · 참고 3)

#### Stage 3(MQ-405) 인계 사항 — reviewer 지적
- **★ user 버블 중복 seed 주의**: `runChatTurn`(`seedTurn`)이 user 버블을 **이미 심는다**.
  MQ-405 의 `useChatStream`/`DiagnosticConsole` 이 사용자 버블을 또 append 하면 중복 —
  **재삽입 금지** (명세 §MQ-405 핵심로직 4 "사용자 메시지 버블도 items 맨 앞에"는 러너가
  이미 수행하므로 화면 쪽에서 하지 말 것)
- **`_ctx` 는 내부**: `useChatStream` 소비 측은 공개 4필드만 읽을 것 (계약 불변)
- **D45 `repeated` 정보 손실 (참고 1)**: 백엔드 hold payload 는 `repeated:{count, window_days}`
  를 담지만 `PoHold` 타입(types.ts, MQ-401 소유)에 필드가 없어 `toHold` 가 못 싣는다. S3
  라이브에서 "30일 3회 반복" 맥락이 hold 카드에 안 뜬다 — 목업(`?scenario=s3`)의
  `repeat_banner` 는 mock 전용 데이터라 라이브엔 없음. **PoHold 타입 + PoHoldCard 확장**이
  필요한 후속 과제. MQ-405 에서 다룰지, 백로그로 뺄지 Stage 3 착수 시 판단

---

## Stage 3 완료 (2026-07-28) — **Sprint 4 · M3 종료**

**커밋**: `01f8b77` — `[M3] Sprint 4 Stage 3 — 화면 A 라이브 배선 (M3 종료)`

#### MQ-405
- `frontend/components/screens/useChatStream.ts`(신규) · `DiagnosticConsole.tsx` ·
  `app/(console)/technician/page.tsx` · `lib/chatStream.ts` · `lib/types.ts`
- 라우트 분기: `?scenario=s1|s3`→mock 보존 · `?replay=s1`→live+재생 자동 send ·
  없음→live 실 루프. 세션 `S-{ts36}`(D36), 장비 선택기(getEquipment, 미선택 null)
- 실 루프 실패는 백엔드 안내 token 그대로(mock 폴백 금지, D40) · 409 toast(재생 PO-0117)

#### ★ Stage 2 인계 "D45 repeated" 해소 — **PoHold 확장이 아니라 repeat_banner 산출로**
- Stage 2 는 "PoHold 타입에 repeated 가 없어 못 싣는다"고 봤으나, **더 나은 경로가 있었다**:
  `repeat_banner` 는 이미 `ChatItem` 종류(types.ts)이고 `ChatThread.tsx:41` 이 이미 렌더한다.
  즉 MQ-404 가 "배너 만들 구조화 소스 없음"이라 한 건 **오판** — hold payload 의
  `repeated:{count, window_days}`(D45, `loop.py _hold_block`)가 바로 그 소스다.
- chatStream 리듀서가 hold 블록에서 `count>0` 이면 `repeat_banner` 를 hold 카드 앞에 산출.
  badge `{count}×`, content "반복 고장 감지 — 최근 {window_days}일 {count}회". **개별 날짜는
  payload 에 없어 미생성**(mock 은 "07-01·07-11·07-19"까지 있으나 라이브는 payload 가 주는
  것만 — 환각 방지). PoHold 타입·PoHoldCard 는 **미변경**
- **계약 변경 아님 (D 불요)** — repeat_banner ChatItem·hold repeated 둘 다 이미 D22·D45.
  리듀서가 활용하느냐의 구현 정정. reviewer 확인. types.ts 주석도 정정

#### 구현 결정 (reviewer 수용 3건)
1. **deferred abort** — StrictMode 이중 mount 에서 즉시 abort 하면 재생 POST 가 끊긴 채
   가드에 막히므로 `setTimeout(0)` 으로 미루고 재-mount 가 취소. 프로덕션 동작 동일·누수 없음
2. **replay 데모 equipmentId=null → error_log 스킵** — `_replay_s1` 은 입력 무관이라 정합
   (replay DoD 에 error_log 없음)
3. **repeat_banner 경로** — PoHold 확장 대신 기존 ChatItem 재사용 (위 ★)

#### 회귀
- 243건(16스위트) + ruff + `tsc --noEmit` + `next build`(`/technician` 9.71kB) 전 통과
  · reviewer PASS(블로커 0 · 경고 0 · 참고 2)

#### 수동 검증 (2026-07-28, Claude in Chrome 브라우저 자동화 — Stage 1~3 종합)

**전부 확인 (✅)**
- `/technician?replay=s1` 관통 — 도구 4스텝 A1 순서(pending→ok) · 안전 블록이 위험 서술
  ("커버를 열고 냉각팬 커넥터를…") **앞**(D22) · 인용 `iG5A 매뉴얼 p.202` · PO 카드 ·
  trace 패널 `4 calls · 재생` + `재생 데이터` 배지
- **실 Gemini 1턴 라이브** (`/technician`, 장비 선택 후 진단 메시지) — `lookup_error_code` 가
  `catalog_not_loaded` 로 정직 실패(D50, 붉은 X)하고 에이전트가 환각 없이 그대로 안내.
  실 API·실 MCP 관통 확인
- `/technician?scenario=s1`·`s3` — 목업 기존과 완전히 동일 (안전 블록·HOLD 카드·held 취소선 등)
- 스트리밍 중 라우트 이탈(`?replay=s1` → `/manager`) — 콘솔 에러 0, D42 취소 안전 확인
- Stage 1 항목 재확인 — N-c 단일 `✗`, error 색 4테마, W-6 `PDF p.` 라벨 전부 유지

**검증이 잡은 결함 → 핫픽스 (커밋 `264a113`)**
- **화면 A 라이브 세션 ID 하이드레이션 불일치** — `LiveConsole` 이
  `useState(() => \`S-${Date.now().toString(36)}\`)` 로 세션 ID 를 초기 렌더에서 만들어
  SSR·클라이언트 hydration 패스가 서로 다른 시각을 찍었다. `TracePanel` 의 `SESSION #…`
  텍스트가 갈려 **`/technician` live 모드 접속마다 100% 재현**되는 React hydration mismatch —
  Next dev 오버레이에 "1 error" 뜨고 전체 트리가 클라이언트 재렌더로 강등됨.
  세션 ID 를 `useEffect`(클라이언트 전용, mount 이후)로 미루고 그 전엔 `null` 을 동일하게
  그리도록 `LiveConsole`(게이트)/`LiveConsoleReady`(기존 로직)로 분리. 하드 리로드(진짜
  SSR+hydration) 재검증으로 해소 확인 — 콘솔 에러 0. 회귀 243건 + 정적 3종 재통과

## Sprint 4 종료 상태

- **M3 완료 — 수동 검증까지 마침**: 화면 A(라이브 SSE + replay 데모, 실 Gemini 관통 확인) ·
  화면 B(Sprint 3) · 표시 규약 정리(N-b·N-c·W-6·error 색 토큰·replay 배지·repeat_banner
  라이브 산출) · 하이드레이션 결함 없음
- **W-6 근본 해소 완료 (D57)** — `/api/po/{id}` 에 `print_page` 계약 추가
- **`DANGER_KEYWORDS` 확장 4종 승인 완료**
- **`error_codes` iG5A 매핑 승인 완료 (2026-07-28) — 65건 실적재** — `error_codes.json`
  `_status` 를 D19 원칙대로 하드코딩에서 유도식으로 전환. W-6 이 이제 실제로 인쇄 페이지를
  보여준다(PO-0117 실측: `print_page=202`), 실 MCP `lookup_error_code` 관통 확인.
  회귀 파급(fixture PK 충돌 2건 `INSERT OR REPLACE` 로 수정, `api_contract.py` ②-b 양성
  실측 전환) + 회귀 실행 워크플로우 문서 4곳에 `--with-error-codes` 누락 발견·수정
  (다음 `/stage`·`/done` 에서 조용히 재적재 취소될 뻔함) — 자세한 경위는
  `docs/sessions/2026-07-28.md` 참조
- 회귀 248건 + 정적 3종. 백엔드는 D56 dotenv 핫픽스 + D57 print_page 추가
- **라이브 S3 반복 배너** 육안은 이제 데이터 전제(error_codes)가 갖춰짐 — 반복 이력 있는
  세션으로 실 루프를 돌리면 확인 가능(다음 세션 항목)
- 다음(M4): `eval/testset.json` 20문항 + 실 DB 채점 배선(`has_replay` 분모 제외) ·
  환각률 LLM judge · 데모 영상 · README. 남은 사람 항목: related_parts 검수 ·
  SAFETY_BASELINE/QUALIFIED_WORKER_NOTE 문안 검수
