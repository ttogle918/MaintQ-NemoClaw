# .docx 생성 배선 + facts 읽기 MCP 도구 — 설계

- 날짜: 2026-09-03
- 브랜치: `feat/docx-render-and-facts-tool`
- 출처: `docs/07_BACKLOG.md` 「아이디어 주차장」 — "실제 .docx/.pdf 파일 생성"
  (2026-09-03 MaintQ 소유 확정 · "MCP 로 원본 수정" 요구 거부 경위 포함)

---

## 0. 무엇을 만드는가

1. **docx 배선** — 결재 문서 5종(01·02·03·05·06)을 **다운로드 시점에** 생성해 스트림한다.
   디스크·DB 에 저장하지 않는다 (D86 유지).
2. **facts 읽기 MCP 도구 1종** — `get_document_facts`. 조회만 한다. 신원·서명 필드는 제외 (D23).
3. **교정 경로** — UPDATE 가 아니라 `create_po_draft` 새 draft INSERT. **코드 변경 없음**,
   도구 응답의 안내와 문서만 추가한다.

### 대상 문서 5종

| 번호 | 문서 | 값 원천 | 플레이스홀더 수 |
|---|---|---|---|
| 01 | 설비이상진단보고서 | `po_drafts` + `error_codes` 정본 | 46 |
| 02 | 정비부품발주요청서 | `po_drafts` + 견적·재고·대체품 | 55 |
| 03 | 자금집행요청서 | 02 + 내부통제(D119) · A2A · 수취인 | 41 |
| 05 | 설비처분승인서 | `decisions` + evidence bundle | 30 |
| 06 | 진술및보장서 | 같음 | 27 |

⛔ **04(담보대출심사회신서)는 대상이 아니다** — D118 이 MaintQ 구현 대상에서 제외했다(FinAllQ 소관).

### 착수 전 실측 (이 설계의 근거)

| 확인한 것 | 결과 |
|---|---|
| 플레이스홀더가 여러 `<w:t>` 런으로 쪼개졌는가 | **5종 전부 0건** — python-docx 치환이 깨끗하다 |
| 표(`<w:tbl>`) 수 | 9~13개/문서 — 평문 덤프로는 전부 사라진다 |
| `python-docx` 설치 여부 | `pyproject.toml` 에 없음 (신규 의존성) |
| backend → mcp_server import | **0건** — D15 경계가 실제로 지켜지고 있다 |
| 현재 최대 결정 번호 | D123 |

---

## 1. 확정한 세 갈림길

### ① docx 생성 전략 → **템플릿 채우기 + 필드맵 추출**

`data/templates/*.docx` 를 python-docx 로 열어 `{{PLACEHOLDER}}` 를 치환한다.

기각한 대안:
- **평문을 docx 문단으로** — 리팩터 0이지만 표 9~13개가 전부 들여쓰기 평문으로 뭉개진다.
  `data/templates/README.md` 가 선언한 "양식의 정본" 지위가 영원히 실현되지 않는다.
- **템플릿 없이 python-docx 직접 조립** — 배치 정본이 docx 파일과 코드로 이원화된다.
  둘이 어긋나도 아무도 모른다 (D90 이 이미 겪은 실패 유형).

라이브러리는 `python-docx` (순수 pip). `md + pandoc` 은 시스템 바이너리가 필요해 배포가 한 겹 는다.

### ② 읽기 도구 노출 필드 → **템플릿 자리 그대로 (필드맵)**

docx 가 채우는 것과 **같은 dict** 를 돌려준다. 에이전트가 "문서에 실제로 뭐라고 찍힐지"를
그대로 보고, 원천이 없는 자리는 `확인되지 않음` 으로 드러난다.

기각한 대안:
- **업무 값만(subset)** — 문서 자리와 이름이 달라 "어느 칸이 틀렸다"를 집어 말할 수 없고,
  필드맵과 별개 계층이라 둘이 어긋나도 모른다.
- **필드맵 + 미리보기 평문** — 한 호출에 문서 3개 × 2~3KB 가 이력에 쌓인다.
  `HISTORY_LIMIT` 절삭 사고가 이미 한 번 있었다(`docs/07_BACKLOG.md` 「알려진 결함」).

### ③ 읽기 도구 범위 → **01·02·05·06 네 종. 03 제외**

03 의 핵심 필드는 예산 한도·1일 누적 한도·FDS·SoD **내부통제 판정**(D119)이고,
`create_po_draft` 로 새 draft 를 넣어도 달라지지 않는다 — **교정 경로가 없는 값**이다.
도구가 "고칠 수 없는 값"을 보여주면 에이전트가 그것을 두고 대화하게 된다.

또 실무적 이유가 하나 더 있다: 03 의 controls·a2a·payee 조립은
`backend.services.a2a_history` · `data.expenditure_limits` 를 쓰는 backend 로직이라
MCP 가 재사용할 수 없다 (D15). 이관하려면 D121(`po_id != ?` 자기중복 방지)을 포함한
재무 한도 판정을 통째로 옮겨야 하는데, 이번 작업(docx 배선)과 무관한 리팩터가 섞인다.

**docx 다운로드는 03 을 포함해 5종 전부 지원한다** — 제외는 읽기 도구 범위에만 적용된다.

---

## 2. 아키텍처

```
data/doc_fields.py                        ← 신설. 순수 계층
  WITHHELD_KEYS: frozenset[str]           ← 신원·서명 (D23)
  po_context(con, po_id)   -> dict | None ← get_po() 의 SELECT+조인 이관
  fields_01(ctx)           -> dict[str,str]
  fields_02(ctx)           -> dict[str,str]
  fields_03(ctx, controls, a2a_info, payee) -> dict[str,str]   ← backend 만 호출
  fields_05(bundle, *, verdict, bundle_hash, reason, decision_id) -> dict[str,str]
  fields_06(...)           -> dict[str,str]

backend/services/po_documents.py          ← render_*_document() 가 fields_* 를 소비. 출력 불변
mcp_server/tools/generate_disposal_document.py ← render_documents() 도 동일. 출력 불변
backend/services/docx_render.py           ← 신설. fill_template(name, fields) -> bytes
mcp_server/tools/get_document_facts.py    ← 신설. 읽기 전용 확장 도구
backend/routers/po.py · decisions.py      ← 다운로드 엔드포인트 2개
```

### `data/doc_fields.py` 가 `data/` 에 있는 이유

`data/po_draft.py` 의 선례 그대로다 — 그 파일 상단이 이미 규약을 못박고 있다:

> ⛔ 이 모듈은 `mcp_server` 도 `backend` 도 import 하지 않는다 (D15 — 두 런타임 프로세스의
> 상호 import 금지). 커넥션은 호출자가 열어서 넘긴다.

MCP 도구와 backend 가 **같은 필드맵**을 봐야 하는데, 어느 한쪽에 두면 반대쪽이 import 할 수
없다. 실측으로 backend → mcp_server import 가 0건임을 확인했다 — 이 경계는 지금 살아 있고,
이번 작업이 그것을 깨는 첫 사례가 되어서는 안 된다.

### 신원 필드는 공유 계층에 넣지 않는다

`{{REQUESTER_NAME}}` · `{{REQUESTER_DEPT}}` · `{{APPROVER_NAME}}` · `{{SIGNED_BY}}` ·
`{{SIGNED_AT}}` · `{{OVERRIDE}}` · `{{OVERRIDE_REASON}}` · `{{SIGNATURE_HASH}}` 은
`data/doc_fields.py` 가 **만들지 않는다.** 다운로드 엔드포인트(backend)가 DB 에서 읽어
마지막에 얹는다.

근거는 D23·D37 의 결 그대로다 — 신원은 서버가 stamp 한 값이고 도구 경로에는 흐르지 않는다.
공유 계층에 두면 읽기 도구가 그것을 빼는 일이 **규율**이 되지만, 애초에 만들지 않으면
**구조**가 된다. `write_tool_contract` 가 UPDATE 를 규율이 아니라 TEMP TRIGGER 로 막은 것과
같은 태도다.

---

## 3. 출력 불변 — 이 작업 최대의 리스크

`render_*_document()` 를 필드맵 소비 형태로 재작성하면 미리보기 문자열이 미묘하게 바뀔 수
있다. 그 문자열은 `spikes/api_contract.py` 52건과 화면(`DocumentPreview.tsx`)이 함께 본다.

**골든 스냅샷으로 막는다.**

1. 리팩터 **전에** 현재 출력을 파일로 뜬다 (시드 DB 의 PO 3건 × 문서 3종 + decision 2건 × 2종)
2. 골든 대조 검사를 먼저 쓴다 → 이 시점엔 자명하게 PASS
3. `fields_*()` 신설 + `render_*()` 재작성 → 골든 대조가 계속 PASS 여야 한다

### ⚠ 이건 부재검사 계열이다 — liveness 앵커를 함께 건다

"차이가 없다"를 주장하는 검사는 *사실이 참* 과 *스캐너가 눈이 멀었다* 를 구분하지 못한다.
골든 파일이 비거나 경로가 바뀌면 **조용히 통과**한다. CLAUDE.md 가 못박은 규칙을 따른다:

- 판정식에 **양성 축**을 넣는다 — `골든 개수 > 0 and 전건 바이트 일치`
- detail 에 **결론이 아니라 실측값**을 찍는다 — `"골든 5/5 일치 · 총 8,431바이트"`
  (`"출력 불변 확인"` 같은 하드코딩 문구는 FAIL 일 때도 그대로 인쇄된다)
- 뮤턴트로 실증한다 — `render_po_request_document()` 안의 문구 한 글자를 바꾸면
  골든 대조만 FAIL 해야 한다

---

## 4. docx 채우기 — `backend/services/docx_render.py`

```python
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

class TemplateFieldMismatch(Exception): ...

def fill_template(template_filename: str, fields: Mapping[str, str]) -> bytes: ...
```

- `data/templates/{template_filename}` 를 **읽기만** 한다
- 문단 · 표 셀(중첩 표 포함) · 헤더 · 푸터의 모든 run 을 순회해 `{{KEY}}` → `fields[KEY]`
- **양방향 strict** — 어긋나면 `TemplateFieldMismatch`:
  - 템플릿에 있는데 `fields` 에 없는 키 → **결재 서류에 `{{X}}` 가 그대로 인쇄되는 것을
    테스트가 아니라 코드가 막는다**
  - `fields` 에 있는데 템플릿에 없는 키 → 템플릿과 코드가 조용히 갈리는 것을 즉시 잡는다
- 저장 없음: 원본을 `BytesIO` 로 열고 결과도 `BytesIO` 로 받아 `bytes` 를 돌려준다.
  **디스크·DB 기록 0** (D86)

### 런 분할을 다루지 않는 이유

5종 전부 플레이스홀더가 단일 `<w:t>` 안에 온전히 있다(실측). 일반적인 run-merge 로직을
선제적으로 넣지 않는다 — 대신 **분할된 플레이스홀더를 발견하면 명시적으로 실패**시킨다.
조용히 처리하면 나중에 템플릿이 편집돼 분할이 생겼을 때 값이 안 채워진 문서가 나간다.

### 의존성

`pyproject.toml` `[project].dependencies` 에 `python-docx>=1.1` 추가.

---

## 5. 다운로드 엔드포인트

```
GET /api/po/{po_id}/documents/{doc}.docx
      doc ∈ diagnosis | po_request | fund_execution
GET /api/decisions/{decision_id}/documents/{doc}.docx
      doc ∈ approval | representation_warranty
```

- 응답: `Response(content=..., media_type=DOCX_MIME)` +
  `Content-Disposition: attachment; filename="...";  filename*=UTF-8''...`
  (한글 파일명은 RFC 5987 `filename*`, ASCII `filename` 은 구형 클라이언트 폴백)
- **가용성 규칙은 미리보기와 같은 조건을 쓴다** — 두 곳에 다른 조건을 쓰면 화면엔 안 보이는데
  URL 로는 받아지는 문서가 생긴다:
  - `diagnosis` — `error_code_def` 가 없으면 404 (미리보기가 `None` 인 바로 그 조건)
  - `fund_execution` — `state ∉ _FUND_EXECUTION_STATES` 면 404
- 권한: 기존 `caller` 의존성 그대로. 미리보기를 이미 볼 수 있는 사람이면 다운로드도 된다 —
  새 권한 경계를 만들지 않는다
- 신원 필드를 여기서 주입한다 (§2 참고)

🔵 이 엔드포인트는 **backend 쓰기 경로가 아니다** — 순수 GET 이다. D10 대상이 아니며
MCP 도구도 아니다.

---

## 6. facts 읽기 MCP 도구 — `get_document_facts`

```
get_document_facts(doc_type: "po" | "disposal", ref_id: str) -> dict
```

- 필수 2개, **기본값 없음** (D80 — 인자 누락은 MCP 스키마가 앞단에서 막는다)
- `doc_type` 은 enum 강제
- 커넥션은 `read_only()` — **writer 계열을 쓰지 않는다**
- 실패는 예외가 아니라 `status` (D9)
- **`full` 프로파일 전용** (D69) → 확장 13 → **14**, 총 20 → **21**.
  코어 7종은 불변이므로 **D88 의 `tools > 7` 게이트와 평가 실적에 영향이 없다**

### 응답

```json
{
  "status": "ok",
  "doc_type": "po",
  "ref_id": "PO-0117",
  "fields": { "01": { "...": "..." }, "02": { "...": "..." } },
  "withheld": ["REQUESTER_NAME", "APPROVER_NAME", "APPROVER_SIGNED_AT", "SIGNATURE_HASH"],
  "unavailable": { "03": "내부통제 판정(D119)은 재무 승인 경로에서만 산출됩니다" },
  "correction_hint": "이 도구는 조회만 합니다. 값을 고치려면 create_po_draft 로 새 초안을 만들거나 화면에서 수정하세요."
}
```

실패: `{"status": "error", "reason": "not_found" | "invalid_input", "message": "..."}`

### `withheld` 와 `unavailable` 을 분리하는 이유

D62 의 결이다 — **"안 준다"와 "없다"는 다른 사실**이다. 하나로 합치면 에이전트가
"요청자 이름이 시스템에 없다"고 말하게 되는데, 그건 거짓이다(있고, 주지 않을 뿐이다).

---

## 7. 교정 경로 — 코드 변경 0

`create_po_draft` 는 이미 INSERT 만 한다. 이 작업이 추가하는 것은 응답의 `correction_hint`
와 `docs/04_MCP_TOOLS.md §21` 의 명시뿐이다.

⛔ **MCP 도구에 UPDATE 를 한 줄도 넣지 않는다** (절대규칙 1 · D10).
`mcp_server/db.py` 의 TEMP TRIGGER 가 물리적으로 막고 `write_tool_contract` 30건 중 6건이
그 경계를 검증한다. **이 스위트가 30건 그대로인 것이 "쓰기 경로가 안 늘었다"의 증거다.**

### 백로그 ㉮ 를 닫는다 — "교정마다 새 draft 가 쌓이는 것"

**감수한다.** 감사 관점에서 "3개로 제안했다가 5개로 바꿨다"는 경과가 남는 것이 오히려 낫다.
사람의 직접 수정 경로는 이미 열려 있다 — `PATCH /api/po`(D111) · `/api/repairs` ·
`/api/decisions`(P39). 화면이 혼잡해지면 그때 목록 필터를 손보는 것이 맞고, 그건 이 작업의
범위가 아니다.

---

## 8. 회귀

| 스위트 | 변화 | 근거 |
|---|---|---|
| `spikes/docx_contract.py` | **신설** | 필드맵 · fill_template 양방향 strict · 다운로드 계약 · 읽기 도구 |
| `spikes/tools_profile_contract.py` | ① 20 → **21**종 | 확장 도구 1종 추가. ⑤ core 7 불변 |
| `spikes/api_contract.py` | 골든 대조 추가 | 미리보기 출력 불변 증명 |
| `spikes/write_tool_contract.py` | **무변경 30건** | 쓰기 경로가 안 늘었다는 증거 |
| 나머지 30 스위트 | 무변경 예상 | |
| `data/seed.py` 41건 | 무변경 | 스키마 변경 없음 |
| pytest 114건 | 무변경 | |
| 프론트 25 라우트 | 무변경 | 버튼은 범위 밖 (§9) |

기준선: **spikes 33/33 · 1,120건**. 작업 후 **34 스위트**가 된다.

⚠ Windows 소켓 고갈로 매번 다른 스위트가 1건 실패할 수 있다. 실패한 스위트는 반드시
단독 재실행해 확인하고, 재시도로 통과하면 그 사실을 보고에 적는다.

---

## 9. 이번 범위에서 뺀 것

- **프론트엔드 다운로드 버튼** — 엔드포인트까지만 만든다. UI 를 붙이면
  `ui_honesty_contract` 가 파일당 6건 늘고 D87(상태→표시 매핑) 검토가 따라온다.
  별건으로 하는 것이 낫다.
- **PDF** — 백로그 항목은 ".docx/.pdf" 지만 pdf 는 별도 변환기(LibreOffice 등 시스템
  바이너리)가 필요해 python-docx 를 고른 이유("순수 pip, 배포 단순")가 사라진다.
- **04 담보대출심사회신서** — D118 (FinAllQ 소관).
- **`data/templates/README.md` 의 "QMesh 진행 중" 문구 정정** — 이미 거짓으로 확정된
  차단 문구가 README ⚠ 절에 남아 있다. 이 작업이 그 문구를 사실로 만들므로 함께 갱신한다.
  (이건 범위 밖이 아니라 **범위 안**이다 — 여기 적어 두는 이유는 빠뜨리기 쉬워서다)

---

## 10. 새 결정 2건

- **D124** — 결재 문서 docx 는 `data/templates/*.docx` 템플릿을 채워 **다운로드 시점에**
  생성하고 저장하지 않는다(D86 유지). 필드맵 산출은 `data/doc_fields.py` 공유 계층에 두어
  MCP·backend 가 같은 값을 본다(D15 준수, `data/po_draft.py` 선례). 신원·서명 필드는 이
  계층이 만들지 않고 backend 엔드포인트가 얹는다(D23·D37).
- **D125** — `get_document_facts` 는 **읽기 전용** 확장 도구다(`full` 전용, 확장 14종·총 21종).
  신원·서명 필드를 `withheld` 로 명시 제외하고(D23), 원천이 없는 것(`unavailable`)과
  구분해 싣는다(D62). 교정은 UPDATE 가 아니라 `create_po_draft` 새 INSERT 로 한다 —
  D10 의 TEMP TRIGGER 와 `write_tool_contract` 6건은 무손상이다.
