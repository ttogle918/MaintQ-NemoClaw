# Sprint 15 — 백로그 P11: IE5 표준판을 model enum에 편입

**상태**: **계획 확정** (PM 초안 → tool-builder 현실성 평가 → 지적 반영, 2026-08-20) · **작성일**: 2026-08-20
**작성 방식**: pm·tool-builder 에이전트 위임 → 코디네이터가 평가 결과 반영해 확정
**착수 트리거**: 사용자가 2026-08-20 세션 중 백로그(`docs/07_BACKLOG.md`)에서 다음 작업으로 **P11**을 명시 선택.
`TODO_직접할일.md` Sprint 14절의 *"검수 후 P11 착수 여부 — 오늘 세션 범위 밖, 미결정"* 메모는
**그 시점 이후의 명시적 사용자 선택으로 해소**됐다 — 별도 조치 불필요, 기록만 남긴다.

---

## 0. 배경 (실측 — pm 에이전트 조사)

Sprint 14(2026-08-20)가 IE5 추출 경로(P29)를 완성하고, 같은 날 IE5 후보 파일(`data/extracted/ie5_code_candidates.json`)
사람 검수 5건이 전부 완료됐다(`TODO_직접할일.md` Sprint 14절). 조인 5건(`OCt 과전류`·`IOL 인버터 과부하`·
`OHt 냉각핀 과열`·`Ovt 과전압`·`Lvt 저전압`) 전부 원문 대조로 정확성이 확인됐고 `IOL` 채택도 확정됐다.
**즉 IE5 5개 에러코드를 정본에 병합할 준비는 이미 끝나 있다.**

### 0-1. 🔴 백로그 P11의 "enum 확장 지점 4곳"은 부정확하다 — 실제로는 그보다 많다

`docs/07_BACKLOG.md` P11: *"enum 확장 지점 4곳: `mcp_server/tools/*.VALID_MODELS`, DB
`CHECK(model IN ...)`, `manifest.json`, 프론트 타입"* — 이건 백로그 작성 당시 추정이다. PM·tool-builder
가 각각 실측한 결과:

- **"DB CHECK(model IN ...)"는 `error_codes` 테이블에 없다.** 실제로 그 CHECK는 `equipment`(물리
  설비) 테이블(`data/seed.py:139`)에 있다. `error_codes`는 `PRIMARY KEY (model, code)`만 있고 model
  값 자체를 제한하는 CHECK가 없다 — **IE5 코드 5건 추가에 DDL 변경이 필요 없다.**
- **"프론트 타입"이라는 4번째 지점은 존재하지 않는다.** `frontend/lib/citation.ts`의 `Citation.manual`
  은 free-form string이고 model을 제한하는 TS enum/union이 실제로 없다. **프론트 코드 변경 불필요.**
- **실제 값·검사 지점은 최소 8곳**이다 — `mcp_server/tools/lookup_error_code.py MODELS` ·
  `mcp_server/rag.py MODELS` · `backend/manifest.py MODELS` · `mcp_server/tools/create_po_draft.py
  VALID_MODELS` · `mcp_server/tools/create_repair_record.py VALID_MODELS` · `data/inventory.py
  VALID_MODELS` · `backend/agent/prompts.py MODELS` · `backend/agent/loop.py:517`(하드코딩 튜플).
- ⚠ **이 "8곳"도 완전하지 않다** — tool-builder 재검토에서 하드코딩된 **에러 메시지 문자열** 3건이
  추가로 드러났다(§0-3). 게다가 sprint-14 §0-5는 *"iG5A·S100 쌍을 언급하는 파일이 28개"* 라고
  이미 적어 뒀다 — 언급(참조)과 정의(enum 검사 로직) 개수가 다르다는 점을 다시 한번 확인한다.
  **DDL(`equipment.model` CHECK)은 이번 스프린트가 의도적으로 건드리지 않는다** — IE5 실물 설비를
  시드하지 않으므로 당장 안 깨지지만, "완전 동등 3기종"은 아직 아니라는 사실을 정직하게 남긴다.

### 0-2. manifest 등재와 enum 확장은 분리 불가능하다 (sprint-14 §7-1 실증)

`spikes/citation_render.py ⑨`가 "manifest 등재 + enum 미확장" 조합에서 `validate_model()` →
`ValueError`로 **예외로 죽는 것**이 sprint-14에서 실증됐다. 이번 스프린트는 둘을 **같은 스테이지**
(Stage 2)에서 함께 진행한다.

### 0-3. 🔴 tool-builder 현실성 평가가 드러낸 추가 결함 3건 (전부 이 계획에 흡수)

| # | 결함 | 근거(실측) | 이 계획의 대응 |
|---|---|---|---|
| ① | 하드코딩 에러 메시지 3곳이 8개 지점 목록에서 빠짐 | `mcp_server/tools/rag_search_manual.py:37`(`MODELS`를 import는 하지만 메시지는 자체 하드코딩) · `create_po_draft.py:86` · `data/inventory.py:37` — 전부 `f"model 은 iG5A|S100 이어야 합니다"` 리터럴 | MQ-1504·MQ-1505 범위에 각각 추가 (§1 Stage 2) |
| ② | `null_count==62` 하드코딩이 **두 곳**에 있는데 계획은 한 곳만 고침 | `data/seed.py`(㉚)뿐 아니라 `spikes/lookup_contract.py:288`(검사 ⑭)도 같은 값을 독립적으로 단언 | MQ-1508 범위에 `spikes/lookup_contract.py:288` 갱신 추가 |
| ③ | 🔴 **안전 회귀** — `prompt_rules ⑭`가 `MODELS`와 `SAFETY_BASELINE` 키 집합의 **완전 일치**를 검사 | `spikes/prompt_rules.py:185-200` `baseline_quoted == set(MODELS)`. MQ-1501이 `SAFETY_BASELINE`에 IE5를 추가하지 않기로 결정(안전 문구 근거 미검증, 절대규칙 3)했으므로 `MODELS`가 3-tuple이 되는 순간 이 등식이 깨진다 | MQ-1509 범위에 이 검사 갱신 추가 — `baseline_quoted <= set(MODELS)`(부분집합)로 완화하고, "IE5는 SAFETY_BASELINE 근거가 아직 없다"를 판정식 주석에 명시 |

> ⚠ 이 표는 "누가 틀렸다"가 아니라 **다음 사람이 같은 구멍을 다시 뚫지 않기 위한 기록**이다.
> tool-builder는 fresh agent로 PM의 요약 명세만 받았고, 코디네이터가 프롬프트를 압축하는 과정에서
> PM 원안의 세부(예: `severity` 매핑)가 일부 누락돼 tool-builder가 "명세 불충분"으로 오판한 항목도
> 있었다 — MQ-1507의 `severity` 매핑은 PM 원안에 **이미 있었다**(§2 참조). 재확인 과정에서
> 정정했다.

### 0-4. 이번 스프린트 산출물 범위

**"IE5를 iG5A·S100과 동급의 3번째 기종으로 완전히 편입"이 아니라 "IE5의 정의 조회(`lookup_error_code`)
경로를 완전히 편입하고, RAG·세이프티·물리설비는 명시적으로 후속 과제로 남긴다."**

명시적으로 **범위 밖**:
- `SAFETY_BASELINE["pages"]`에 IE5 추가 안 함 — 안전지침 페이지 사람 검증 전(절대규칙 3)
- RAG 청킹 안 함 — IE5 매뉴얼이 `manual_chunks.jsonl`에 없어 `rag_search_manual(model="IE5")`은
  `index_not_built`을 정직하게 반환(환각 아님, 정상 동작)
- `equipment`/`assets` 물리 설비 시드 안 함 — IE5 실물 자산·related_parts 매핑 데이터가 없다

---

## 1. 스테이지 계획

### Stage 1 — D109 결정 초안 (🛑 사용자 확인 게이트)

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1501 | D109 결정 등재 — model enum 3종 확장, 범위 경계 명시 | `docs/10_DECISIONS.md` | — |

> 🛑 **Stage 2는 사용자가 D109를 확인하기 전에는 착수하지 않는다.** `model` enum은 CLAUDE.md 절대규칙
> 4(D6·D13)가 보호하는 값이고, "설계와 다른 구현을 하려면 먼저 D를 추가하고 진행"이 이 저장소의
> 규칙이다. Stage 1을 단독으로 둔 이유 — 이후 모든 코드 변경이 D109의 범위 경계(§0-4)를 따라야
> 하므로, 결정문 확정 전에 코드를 건드리면 문서·코드가 어긋나는 드리프트가 재발한다.

### Stage 2 — 병렬 enum 확장 (D109 승인 후)

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1502 | IE5 후보 파일 `_status` "승인 완료"로 갱신 | `data/extracted/ie5_code_candidates.json` | Stage 1 |
| MQ-1503 | `manifest.json`에 IE5 표준판 등재 | `data/raw/manifest.json`, `data/raw/INDEX.md` | Stage 1 |
| MQ-1504 | 조회 경로 enum 확장 | `mcp_server/tools/lookup_error_code.py`, `mcp_server/rag.py`, `backend/manifest.py`, **`mcp_server/tools/rag_search_manual.py:37`(하드코딩 메시지, §0-3①)** | Stage 1 |
| MQ-1505 | 쓰기 도구 + 재고 조회 enum 확장 | `mcp_server/tools/create_po_draft.py`(**`:86` 메시지 동적화 포함**), `mcp_server/tools/create_repair_record.py`, `data/inventory.py`(**`:37` 메시지 동적화 포함**) | Stage 1 |
| MQ-1506 | 에이전트 프롬프트·루프 enum 확장 | `backend/agent/prompts.py`, `backend/agent/loop.py` | Stage 1 |

### Stage 3 — 정본 병합 (직렬, 같은 데이터 계보)

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1507 | IE5 5건 정본 병합 스크립트 신설 + 실행 | `data/merge_ie5_codes.py`(신규), `data/extracted/error_codes.json`(데이터), `data/extracted/ie5_code_candidates.json`(데이터) | MQ-1502, MQ-1503 |
| MQ-1508 | 회귀 하드코딩 값 갱신 + IE5 적재 검사 신설 | `data/seed.py`, **`spikes/lookup_contract.py:288`(§0-3②)** | MQ-1507 |

> ⚠ **직렬 필수** — MQ-1508의 정확한 값(65→70 등)은 MQ-1507이 실제로 만든 개수를 실측해서 넣는다
> (추정치 하드코딩 금지, CLAUDE.md 실측 우선 원칙).

### Stage 4 — 회귀 갱신 (병렬)

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1509 | `prompt_rules` 하드코딩 갱신 | `spikes/prompt_rules.py`(**check ⑤ `:121` + check ⑭ `:185-200`, §0-3③ — 안전 회귀**) | MQ-1506 |
| MQ-1510 | `citation_render`에 IE5 왕복 케이스 추가 | `spikes/citation_render.py` | MQ-1503, MQ-1504 |

### Stage 5 — 문서 동기화

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1511 | 정본 문서 65→70 갱신 + P11 상태 갱신 | `CLAUDE.md`, `docs/05_DB_SCHEMA.md`, `docs/07_BACKLOG.md`, `docs/04_MCP_TOOLS.md` (**`docs/00_MVP_SCOPE.md`·`02_SCENARIOS.md`·`06_REPO_API.md`·`01_OVERVIEW.md`·`README.md`는 iG5A·S100 조합을 언급하지만 이번 스프린트에서 의도적으로 갱신하지 않는다 — 이유를 커밋에 명시**) | Stage 1~4 전부 |

### 스테이지 구성 근거

- Stage 1: 절대규칙을 바꾸는 결정은 코드보다 먼저, 단독으로.
- Stage 2: 5태스크가 서로 다른 파일만 건드려 병렬 안전(tool-builder가 grep으로 전수 확인).
- Stage 3: `merge_ie5_codes.py`는 후보 파일 `_status`="승인 완료"에 의존(MQ-1502), `seed.py`의
  정확한 카운트 갱신은 병합 후 실측이 필요해 직렬.
- Stage 4: 대상 코드가 Stage 2에서 존재해야 검증 가능.
- Stage 5: 최종 숫자가 전부 확정된 뒤에만 정확하게 쓸 수 있어 마지막.
- 이월 태스크 없음 — 신규 착수.

---

## 2. 태스크별 핵심 명세 (전체 상세는 pm 에이전트 산출물 참조, 여기는 요지 + 정정분만)

### MQ-1501 — D109 결정 등재

**결정문 골자**: `model` enum을 `("iG5A", "S100", "IE5")` 3종으로 확장한다. 확장 대상은 §0-1이
실측한 8개 코드 지점 + §0-3①의 하드코딩 메시지 3건. 범위 밖(§0-4)을 명시.

**기각 대안**: ① 백로그 원안대로 4곳만 확장(실측상 불충분) ② 세이프티·RAG까지 완전 동등화(절대규칙
3 위반·스코프 폭발) ③ enum 미확장 상태로 데이터만 추가(sprint-14 §7-1이 "뒷문"으로 이미 기각).

**엣지 케이스**: 착수 시 D108이 여전히 마지막 결정인지 재확인(선점 시 D110으로 밀림).

**DoD**: `docs/10_DECISIONS.md`에 D109 행 추가 + **사용자 명시 승인**. 승인 전 Stage 2 착수 금지.

### MQ-1502 — 후보 파일 `_status` 갱신

`_status`를 `"승인 완료 (2026-08-20). ⛔ 이 파일은 여전히 DB 에 적재되지 않는다 — 정본 병합은
MQ-1507 이 별도로 한다"`로 갱신(`data/merge_approved_actions.py` 선례 형식). `_status` 외 키는
건드리지 않는다.

### MQ-1503 — manifest.json에 IE5 등재

`id: "ie5-standard"`(후보 파일 `_source.manual_id` 재사용) · `role: "primary"` · `sha256`은 후보
파일의 `_source.sha256`과 반드시 일치 · `print_page_offset`은 실측 가능하면 정수, 불가능하면 `0` +
caveat(추측 금지, D9). `data/raw/INDEX.md`에도 동일 원칙으로 등재.

### MQ-1504 — 조회 경로 enum 확장

`lookup_error_code.py MODELS`·`rag.py MODELS`·`manifest.py MODELS` 3-tuple화 + 하드코딩 에러
메시지를 `f"model은 {'|'.join(MODELS)} 이어야 합니다"` 식으로 동적화. **`rag_search_manual.py:37`도
같은 방식으로 동적화**(§0-3①). `rag_search_manual.py`는 `MODELS` import 자체는 이미 하고 있어 재수출
관련 변경 불필요.

### MQ-1505 — 쓰기 도구 + 재고 조회 enum 확장

`create_po_draft.py VALID_MODELS`·`create_repair_record.py VALID_MODELS`·`data/inventory.py
VALID_MODELS` 3-tuple화. **`create_po_draft.py:86`·`data/inventory.py:37`의 하드코딩 메시지도
동적화**(§0-3①, `create_repair_record.py:198`은 이미 동적이라 변경 불필요).

### MQ-1506 — 에이전트 프롬프트·루프 enum 확장

`prompts.py MODELS` 3-tuple화(`SAFETY_BASELINE`·`QUALIFIED_WORKER_NOTE`는 **불변** — 범위 밖 주석
추가). `loop.py:517`의 하드코딩 튜플을 `prompts.MODELS` 참조로 교체. `_TurnState.safety_page()`는
절대 건드리지 않는다 — `.get()` 유지가 이 스프린트의 안전장치.

### MQ-1507 — IE5 5건 정본 병합

`data/merge_approved_actions.py`를 본뜬 신규 스크립트. 정본이 정확히 65건, 후보 파일 `_status`가
"승인 완료"로 시작해야 진행(D9 — 조건 불충족 시 중단, 예외 아닌 상태 반환). 매핑:

| 정본 필드 | 값 |
|---|---|
| `model` | `"IE5"` |
| `code` | 후보의 `canonical_code`(대문자, D25) |
| `display_code` | 후보의 `display_code`(원표기) |
| `error_name` | 후보의 `name_ko` |
| **`severity`** | **`"fault"`**(iG5A 파서 기존 관행과 동일 — 이 표에 상태 마커가 없다. `error_codes` DDL이 `NOT NULL CHECK IN ('warning','fault','critical')`이므로 반드시 채워야 값이 있어야 KeyError·CHECK 위반 없이 로드된다) |
| `causes` / `actions` | 후보의 `cause` / `action` 리스트 그대로 |
| `related_parts` | `[]`(매핑 데이터 없음, 지어내지 않는다 D12) |
| `manual_page` | 후보의 `manual_page`(125 또는 126) |
| `actions_manual_id` / `actions_page` | `null` / `null`(같은 표에서 원인·조치가 나옴, D100) |
| `source` | `"IE5 표준판 13장 이상 대책 및 점검표(p125-126) + 본문 괄호 코드(D107)"` |

`write_canonical()`은 재사용하지 않는다(그 함수는 "내용 달라지면 안 쓰고 exit1"이 설계 의도라 신규
행 추가와 안 맞음 — `merge_approved_actions.py` 패턴을 따른다). 재실행 시 멱등 종료.

**DoD**: `entries` 65→70, 재실행 시 "변경 없음" 멱등 확인.

### MQ-1508 — 회귀 하드코딩 값 갱신

`data/seed.py` 검사 ㉚ `null_count == 62` → `== 67`(65 IE5 5건 병합 후 actions_manual_id NULL도
5건 늘어남), 검사 ㉘ 설명문자열 65→70. 신규 검사(양성축 IE5 행수==5 + 음성축 causes/actions 빈값
0건, `--with-error-codes` 게이트 조건부). **`spikes/lookup_contract.py:288`의 동일 하드코딩
(`null_count == 62`)도 같은 값으로 갱신**(§0-3② — 놓치면 이 스파이크가 FAIL한다).

### MQ-1509 — prompt_rules 갱신

check ⑤(`:121`) `tuple(MODELS) == ("iG5A", "S100")` → 3-tuple. **check ⑭(`:185-200`)
`baseline_quoted == set(MODELS)`를 `baseline_quoted <= set(MODELS)`(부분집합)로 완화**하고 판정식
주석에 "IE5는 SAFETY_BASELINE 근거 미확보 — 의도적 제외(D109)"를 명시(§0-3③, 안전 회귀 방지).

### MQ-1510 — citation_render IE5 케이스

검사 ④ `cases`에 `("IE5", 125)` 추가. 검사 ⑨(`manifest.MODELS` 순회)는 **코드 변경 없이 자동으로
IE5 편입** — DoD에서 detail 문자열에 `IE5`가 실측값으로 찍히는지 확인. offset 값은 MQ-1503 결과를
그대로 반영(추측 금지).

### MQ-1511 — 문서 동기화

`error_codes` 65→70건, 회귀 기준선(스위트별 델타 실측), P11 상태를 "✅ 완료 (Sprint 15)"로 갱신 +
이번에 밝혀진 정정(enum 지점 4→8+3곳, DB CHECK는 equipment에 있지 error_codes 아님, 프론트 타입
지점은 애초에 없었음) 기록. **`00_MVP_SCOPE.md`·`02_SCENARIOS.md`·`06_REPO_API.md`·
`01_OVERVIEW.md`·`README.md`는 이번 스프린트에서 갱신하지 않는다** — 범위 밖(§0-4)이지 누락이
아니라는 점을 커밋 메시지에 명시.

---

## 3. 회귀 영향 예측 (tool-builder 실측 재확인)

| 스위트/검사 | 예상 | 근거 |
|---|---|---|
| `spikes/lookup_contract.py`(14건) | **check ⑭만 영향**(§0-3②) | 나머지는 `MODELS` 상수 미참조 |
| `spikes/rag_contract.py`(12건) | 무영향 | `MODELS` 상수 미참조(실측) |
| `spikes/sp2_mcp_roundtrip.py`(20건) | 무영향 | `parts.compatible_models` 부분집합 검사, IE5 미시드 |
| `spikes/api_contract.py`(31건) | 무영향 | iG5A/S100 리터럴 동시 등장 없음 |
| `spikes/write_tool_contract.py`(30건) | 무영향 | 동일 |
| `spikes/prompt_rules.py`(24건) | **건수 불변, ⑤·⑭ 판정 갱신 필수**(§0-3③) | — |
| `spikes/citation_render.py`(18건→18+α) | 건수 소폭 증가 | MQ-1510 |
| `data/seed.py` 자가검증(36→37건) | ㉘·㉚ 값 갱신 + 신규 1건 | MQ-1508 |
| pytest 83건 | 무영향 | model enum·error_codes 비관련 영역 |
| spikes 총 32스위트 | 개수 불변 | 신규 스파이크 파일 없음 |

---

## 4. 사람이 해야 할 일 (`TODO_직접할일.md` 이관 대상)

- [x] ✅ Stage 1 완료 후 D109 결정문 확인·승인 — 2026-08-21 `/stage 2` 트리거로 승인
- [x] ✅ **`print_page_offset` 실측 완료 (2026-08-21).** PDF 직접 확인 결과 물리 p.20→'2-1' ·
      p.50→'5-11' · p.100→'10-13' · p.125→'13-4' — iG5A 표준판과 동일한 장(章)-상대 쪽번호
      표기이고 선형 환산 축이 없어 `offset=0`이 맞는 규약임을 확인(추측 아님, D9). `data/raw/
      manifest.json`의 `page_note` 갱신 완료.
- [ ] (스프린트 밖) IE5 안전지침 페이지 사람 검증 — 완료되면 `SAFETY_BASELINE`에 IE5 추가 근거가 됨
- [ ] (스프린트 밖) IE5 매뉴얼 RAG 청킹 여부 — 별도 스프린트로 판단

---

실행: `/stage 1`

---

## Stage 1 완료 (2026-08-21)

**커밋**: `a3243e7` — `[M4] docs: Sprint 15 Stage 1 — D109 결정 등재 (P11, model enum 3종 확장 전제)`
**reviewer**: 1차 게이트 **PASS**(블로커 0) — 8개 지점·`safety_page()` 방어적 조회·`equipment` CHECK
값을 전부 grep/read로 재확인, 정본 6파일 일관 갱신 확인.

### 산출물

| 파일 | 내용 |
|---|---|
| `docs/10_DECISIONS.md` | **D109** 신규 등재 — model enum 3종 확장 결정 |
| `CLAUDE.md`·`README.md`·`docs/README.md`·`.claude/agents/reviewer.md`·`docs/status/maintq-status.html`·`docs/00_MVP_SCOPE.md` | D1~D108 → D1~D109 갱신 (정본 6파일) |

### 검증

`seed 36` · `sp2 20` · `write_tool 30` · `api 31` · `sp3 22` · `ruff clean` — 문서만 변경이라 코드
회귀 영향은 없으나 고정 스위트 전부 재확인.

### 🛑 다음 단계 — 사용자 승인 대기

**Stage 2(실제 enum 코드 확장)는 사용자가 D109 결정문을 확인·승인해야 착수한다.** 결정문 전문은
`docs/10_DECISIONS.md`의 D109 행 참조 — 요지는 §0 그대로:

- `model` enum을 `("iG5A", "S100", "IE5")`로 확장
- 대상 8개 코드 지점 + 하드코딩 메시지 3곳
- 명시적 범위 밖: 안전 문구(`SAFETY_BASELINE`) 미확장 · RAG 청킹 안 함 · `equipment`/`assets` 물리
  설비 미시드 — 즉 "정의 조회 경로만 편입"이지 "완전 동등 3기종"이 아니다

승인되면 `/stage 2`로 Stage 2(MQ-1502~1506, 병렬 5태스크)를 진행한다.

---

## Stage 2 완료 (2026-08-21)

**커밋**: `acd2eee` — `[M2] feat: Sprint 15 Stage 2 — model enum 3종 확장 (D109, P11)`
**reviewer**: 1차 **FAIL**(블로커 1) → 수정 → 2차 **PASS**

### 산출물

| 태스크 | 파일 |
|---|---|
| MQ-1502 | `data/extracted/ie5_code_candidates.json` — `_status` "승인 완료" |
| MQ-1503 | `data/raw/manifest.json`·`data/raw/INDEX.md` — IE5 표준판 등재 |
| MQ-1504 | `lookup_error_code.py`·`rag.py`·`manifest.py`·`rag_search_manual.py` — `MODELS` 3-tuple화 |
| MQ-1505 | `create_po_draft.py`·`create_repair_record.py`·`data/inventory.py` — `VALID_MODELS` 3-tuple화 |
| MQ-1506 | `prompts.py`·`loop.py` — `MODELS` 3-tuple화(`SAFETY_BASELINE` 등은 불변) |

### 🔴 reviewer 1차 FAIL — 계획에 없던 세 번째 하드코딩

`backend/agent/prompts.py`의 `RULES` 규칙 9가 "`model` 파라미터에는 `iG5A` 또는 `S100` 만 쓴다"로
하드코딩돼 있어, 같은 시스템 프롬프트 안에서 `build_system_prompt()`의 장비 컨텍스트 절(`MODELS`
동적 참조, IE5 포함)과 정면 모순됐다. D109가 실측한 "8개 지점 + 하드코딩 메시지 3곳"에도 없던
지점이다 — **결정문 실측이 완전하지 않았다는 증거.** 규칙 9를 `MODELS` 참조 f-string으로 동적화해
해소. 부수로 `mcp_server/server.py:87`의 낡은 docstring도 정리.

### 코디네이터가 회귀 중 발견 — `citation_render.py` 하드코딩 카운트

`⑫ load_manifest 1회 캐시` 검사가 `manuals` 개수를 `3`으로 하드코딩하고 있었는데 MQ-1503이 IE5를
더해 4건이 됨 — `4`로 갱신. MQ-1510(Stage 4)이 담당할 "IE5 왕복 케이스 추가"와는 다른, MQ-1503의
직접 여파라 이번 스테이지에서 즉시 수정했다.

### 알려진 채 남겨둔 회귀 2건 (계획대로, Stage 4 MQ-1509 대상)

`spikes/prompt_rules.py` ⑤(`MODELS` 정확 2종 일치 단언)·⑭(`SAFETY_SOURCES` 키 집합과 `MODELS`
완전 일치 단언) — 둘 다 sprint-15.md §0-3③에 사전 식별된 것으로, IE5 enum 확장과 안전 문구
의도적 미확장의 직접 결과다.

### 회귀

`seed 36` · `sp2 20` · `write_tool 30` · `api 31` · `sp3 22` · `ruff clean` · `lookup_contract 14`
(무영향) · `rag_contract 12`(무영향) · `citation_render 18`(수정 후 재통과)
