# Sprint 5 — M4 (마지막 마일스톤): 평가셋 실행 · 결과 문서화 · 데모 영상 · README

**수립**: 2026-07-29 · **선행 상태**: M1~M3 전부 완료. `error_codes` 65건 실적재(2026-07-28,
브라우저 실측 완료). Gemini 실 루프·화면 A/B 라이브 배선 전부 검증됨. `eval/score.py` 는
이미 완성(D54·D55 반영, MQ-310) — `eval/testset.json`·`run_eval.py`·`results/` 는 아직 없다.

**이번 스프린트의 성격**: 평가 파이프라인을 처음 만든다. 계약 변경은 없다(`eval/` 신규 코드가
기존 API·MCP 계약을 건드리지 않음) — 단 **문서-구현 정합화 1건**(`expect_hold` 필드가
`eval/score.py` 에는 이미 있는데 `06_REPO_API.md` §3 이 못 따라간 상태)은 있다.

## 사전 조사 핵심 발견 (PM + tool-builder)

- `eval/score.py` 의 `_judge_sequence` 는 이미 `expected.get("expect_hold")` 를 읽는다 —
  `06_REPO_API.md` §3 스키마 예시에 이 필드가 없다. **문서만 뒤늦게 보정**(계약 변경 아님).
- **`POST /api/chat` 은 role 을 게이트하지 않는다** — `backend/deps.py`·`backend/routers/chat.py`
  확인: `require()` 호출은 `backend/routers/po.py:55,62,69`(승인 워크플로우)에만 있다. 20문항
  루프 안에서 role 을 조작해도 403 지표에 아무 영향이 없다 — **403 지표는 문항 루프 밖 별도
  고정 점검**으로 설계해야 한다(PO-0117 승인 시도).
- **시드 데이터 실측 확인 완료**: `INV-L3-01`+`OCT` 가 30일 내 유일한 3회 반복 조합(다른 조합
  없음), `error_codes` 65건에 `XY9`/`QQ1` 부재, `PCB-S100-CTRL-R2`(재고4·공급사2)·
  `PWR-S100-MOD`(재고0·대체품0) 실측 일치, S1 후보 장비 전부 `GET /api/equipment` 존재.
- **`.claude/hooks/guard_writes.py` 가 `eval/testset.json` Write/Edit 을 exit 2 로 하드
  차단한다** (matcher `Edit|Write`, 파일명이 `eval/testset.json` 로 끝나면 무조건 차단 —
  `run-eval` 스킬 규칙 "기대 정답 변경은 사람 승인"을 도구 레벨에서 강제). **Claude 는 이 파일을
  직접 쓸 수 없다** — Bash heredoc 등으로 우회하는 것은 금지(안전장치 무력화). MQ-501 설계를
  이에 맞춰 변경함(아래).
- **`.claude/settings.json` 의 Stop 훅이 매 턴 `pytest eval/ -q` 를 실행한다.** `judge.py`·
  `run_eval.py` 에 `test_*` 로 시작하는 함수/파일명을 두면 안 된다 — 실비용 API 호출이 매 턴
  자동 실행되는 사고로 이어진다.
- **`GeminiClient.stream()`(`backend/agent/llm.py`) 은 `tools=[]` 여도 항상
  `types.Tool(function_declarations=[])` 를 `config.tools` 에 넣는다** — 실 Gemini API 가 빈
  선언 목록의 Tool 을 받아들이는지 이 저장소에서 한 번도 검증된 적이 없다(기존 실 스모크는
  전부 MCP 도구가 채워진 경로). judge.py 가 이 미검증 경로의 첫 소비자가 된다 — 방어적으로
  고친다(아래 MQ-503).
- `spikes/sp3_sse_events.py` 의 subprocess+임시DB 패턴은 `MAINTQ_MCP_AUTOSTART=0` 으로 MCP 를
  **끈 채** 재생 전용으로 쓴다 — MQ-502 는 실 루프가 진짜 도구를 호출해야 하므로 **정반대
  (autostart 기본값 1)** 가 필요하다. 그대로 복사하면 20문항이 "도구 서버 연결 불가"로 조용히
  전부 실패하고 score.py 는 그걸 그냥 fail 로 채점한다(참사가 티가 안 남) — 명시적 방어 필요.

## 범위 밖 (의도적)

- `related_parts.seed.json` 검수 — 사람 전담(D12). testset 의 `part_no` 기대값은 이 파일에서
  파생되므로 **testset 자체도 검수 전까지 초안**이다
- `SAFETY_BASELINE`/`QUALIFIED_WORKER_NOTE` 문안 검수 — 사람 전담
- `docs/07_BACKLOG.md` P1~P21 승격 없음

---

## Sprint 5 최종 실행 계획

| 스테이지 | 태스크 | 병렬 | 예상 결과물 |
|---------|--------|-----|-----------|
| Stage 1 | MQ-501, MQ-503, MQ-506, MQ-507 | ✅ (파일 교집합 없음, tool-builder 실측 확인) | testset 초안 + expect_hold 문서 보정 · 환각 judge · 데모 큐시트 · README 골격 |
| Stage 2 | MQ-502 | — | `eval/run_eval.py` (무비용 `--dry-run` 까지만 DoD) |
| Stage 3 | MQ-504 | — | replay 분모 제외 회귀 (무비용) |
| Stage 4 | MQ-505 | — (사람 비용 승인 게이트) | 실 20문항 1회 실행 + 결과 문서 + README 표 채움 |

```
MQ-501 ─┬─► [사람: testset.json 반영] ─► MQ-502 ─► MQ-504 ─► MQ-505
MQ-503 ─┘                                              ▲
MQ-507 ──────────────────────────────────────────────────┘ (골격 → 결과표 채움)
MQ-506  (독립, 데모 촬영 준비)
```

### 스테이지 구성 근거

- **Stage 1 네 태스크는 파일이 완전히 분리**(tool-builder 실측: `eval/testset_draft.json`+
  `testset_review_notes.md`+`docs/06_REPO_API.md`(MQ-501) / `eval/judge.py`+
  `eval/prompts/hallucination_judge.md`+`backend/agent/llm.py`(MQ-503, tools=[] 방어 수정
  추가) / `docs/demo_script.md`(MQ-506) / `README.md`(MQ-507) — 교집합 없음.
- **MQ-502 를 Stage 1 에 못 넣는 이유**: testset 문항 내용(MQ-501)과 judge 인터페이스(MQ-503)
  를 소비한다.
- **MQ-504 를 MQ-502 와 같은 스테이지에 못 넣는 이유**: `run_eval.ItemResult`/`aggregate`
  심볼에 의존하는 회귀라 시그니처가 먼저 고정돼야 한다. API 비용은 0(합성 픽스처).
- **MQ-505 를 별도 Stage(4)로 격리하는 이유**: 유일하게 실비용이 발생한다. **추가로 Stage 4
  진입 전에 사람이 할 일이 하나 더 생겼다** — `eval/testset_draft.json`(MQ-501 산출)을 검수해
  `eval/testset.json` 으로 직접 반영하는 것(훅이 Claude 의 직접 반영을 막으므로). 이 스텝
  없이는 `run_eval.py --dry-run` 조차 로드할 파일이 없다.
- 각 스테이지 검증: Stage 1~3 은 회귀 248건 + ruff(신규 파일이 기존 계약 무변경이라 구조적
  통과) + 신규 산출물 자체 검증. Stage 4 는 회귀 재확인 + 5지표 전부 보고.

---

## 태스크별 상세 구현 명세

### MQ-501 — testset 초안 + `expect_hold` 문서 보정

- **복무 시나리오**: S1~S4 전부
- **변경 파일**:
  - `eval/testset_draft.json` (신규 — **`eval/testset.json` 이 아니다**, 훅 미보호 경로)
  - `eval/testset_review_notes.md` (신규 — 사람 검수용 근거 대조표)
  - `docs/06_REPO_API.md` §3 (`expect_hold` 필드 추가, 계약 변경 아님)
- **`eval/testset.json` 자체는 Claude 가 Write/Edit 할 수 없다**(`guard_writes.py` 하드
  차단, exit 2). Bash heredoc 등 우회 시도 금지 — reviewer 게이트에서 이 우회 여부를 확인한다.
  사람이 `testset_draft.json` 을 검수한 뒤 **직접** `eval/testset.json` 으로 옮긴다(그대로
  복사든 수정 후든 사람 손을 거쳐야 함).

- **인터페이스** (`docs/06_REPO_API.md` §3 + `expect_hold` 보정):
  ```json
  {
    "id": "T01",
    "input": "iG5A 인버터에 OHt 에러 떴어",
    "equipment_id": "INV-L1-01",
    "role": "technician",
    "expected": {
      "branch": "s1_pipeline | s2_alternative | s3_root_cause | s4_not_found",
      "part_no": "FAN-IG5-01",
      "safety_required": true,
      "expect_not_found": false,
      "expect_hold": false,
      "safety_page": 4
    }
  }
  ```
  - `expect_hold`: S3 문항만 `true` (`eval/score.py` `_judge_sequence` 소비, D35·A8).
  - `safety_page`: 전부 채운다(iG5A=4, S100=2, `SAFETY_BASELINE["pages"]` 승인값) — 더 엄격한
    판정.
  - `part_no`: S3·S4 문항은 반드시 `null`.
  - `role`: 20문항 전부 `"technician"` — `/api/chat` 은 role 게이트가 없으므로 조작 무의미.

- **핵심 로직 (실행 절차)**:
  1. **데이터 원천**: `data/extracted/error_codes.json`(65건)·`data/related_parts.seed.json`
     (7건, 임시)·`data/seed.py` 상수만 근거로 삼는다. 애매하면 `uv run python -c`로 실
     `data/maintq.db` 를 직접 조회해 실측(추측 금지).
  2. **20문항 배분** (06_REPO_API §3 "부품 특정 15+S3형 3+S4형 2"와 정합):
     - **S1 12문항(T01~T12)** — `related_parts.seed.json` 단일 매핑 4쌍(iG5A: OHT→FAN-IG5-01,
       FAN→FAN-IG5-01, GFT→MTR-CBL-IG5 / S100: OHT→FAN-S100-01, FAN→FAN-S100-01,
       OCT→MTR-CBL-S100 — iG5A OCT 는 2개 부품에 매핑돼 모호하므로 제외)를 서로 다른
       `equipment_id`(실측 확인된 iG5A: INV-L1-01/02·L3-02·L4-03, S100: INV-L2-01/02·L3-03·
       L4-01/02) 조합으로 반복 사용. 전부 `branch:"s1_pipeline"`, `safety_required:true`,
       `expect_hold:false`, `expect_not_found:false`.
     - **S2 3문항(T13~T15)** — `PCB-S100-CTRL`(재고0·단종)→`PCB-S100-CTRL-R2`(재고4, 확정
       대체품) 조합 2문항(다른 equipment_id·문구) + `PWR-S100-MOD`(재고0·대체품 없음, 에스컬
       레이션) 1문항. 전부 `branch:"s2_alternative"`, `safety_required:true`,
       `safety_page:2`.
     - **S3 3문항(T16~T18)** — 시드가 보장하는 유일 반복 조합 `INV-L3-01`+`OCT`(iG5A)를 문구만
       바꿔 3회 사용(추측이 아니라 시드 데이터의 실측 한계). 전부 `equipment_id:"INV-L3-01"`,
       `branch:"s3_root_cause"`, `part_no:null`, **`expect_hold:true`**.
     - **S4 2문항(T19~T20)** — 후보 코드가 65건에 **없음을 스크립트로 실측 확인**한 뒤 확정
       (예: iG5A `XY9`, S100 `QQ1` — 이미 이번 조사에서 부재 확인됨, 충돌 시 대체 후보로 교체
       하고 확인 로그를 남긴다). 전부 `branch:"s4_not_found"`, `part_no:null`,
       `safety_required:false`, `expect_not_found:true`.
  3. **`role` 설계 결정**: `/api/chat` 은 role 을 게이트하지 않으므로 20문항 전부
     `"technician"` 통일. 403 지표는 MQ-502 의 별도 고정 점검이 담당함을 §3 각주에 명시.
  4. **`testset_review_notes.md`**: 문항별 `part_no` 근거 출처 명시(예 "T01 ← related_parts
     OHT 매핑, reviewed:false"). 최상단 경고 배너: "이 표의 `part_no` 는 검수 전(D12) 초안이다
     — `TODO_직접할일.md` 'related_parts 검수' 완료 전까지 이 testset 으로 낸 부품 특정
     정확률을 실적으로 인용하지 말 것. **`eval/testset.json` 반영은 사람이 직접 수행**
     (`.claude/hooks/guard_writes.py` 가 Claude 의 직접 반영을 차단함)."
  5. **§3 문서 보정**: JSON 예시에 `expect_hold` 추가 + 각주 "score.py 가 먼저 구현했고 문서가
     뒤늦게 반영. role 필드는 현재 score.py 가 참조하지 않음 — 403 지표는 run_eval.py 의 별도
     고정 점검 참조."

- **엣지 케이스**: T13/T14 가 같은 부품(PCB-S100-CTRL-R2)을 기대하는 건 의도(시드가 보장하는
  S2 결정론적 케이스가 이것뿐) — review notes 에 한계로 명시. S4 후보 충돌 시 커밋 금지, 대체
  후보로 교체 후 재확인.

- **DoD**:
  - `python -c "import json; d=json.load(open('eval/testset_draft.json',encoding='utf-8')); assert len(d)==20; assert sum(1 for x in d if x['expected']['branch']=='s3_root_cause')==3; assert all(x['expected']['part_no'] is None for x in d if x['expected']['branch'] in ('s3_root_cause','s4_not_found'))"` 통과
  - S4 후보 코드 부재 확인 로그가 `testset_review_notes.md` 에 있음
  - `eval/testset.json` 을 Claude 가 직접 만들거나 수정하지 않았음(reviewer 확인 항목)
  - 회귀 248건 영향 없음

- **관련 결정**: D12·D26·D30·D35·A8

---

### MQ-503 — 환각률 LLM judge (+ GeminiClient 방어 수정)

- **복무 시나리오**: S4
- **변경 파일**: `eval/judge.py`(신규) · `eval/prompts/hallucination_judge.md`(신규) ·
  `backend/agent/llm.py`(수정 — `GeminiClient.stream` 방어)

- **선행 수정 — `backend/agent/llm.py` `GeminiClient.stream`**: `tools` 가 빈 리스트면
  `config` 에 `tools` 키 자체를 넣지 않는다(현재는 `tools=[types.Tool(function_declarations=[])]`
  를 항상 넣어 실 Gemini API 가 빈 선언 Tool 을 받아들이는지 이 저장소에서 검증된 적이 없다 —
  judge.py 가 이 미검증 경로의 첫 소비자가 되므로 방어적으로 없앤다). 기존 실 루프
  경로(`backend/agent/loop.py`)는 MCP 도구 7종을 항상 채워 호출하므로 이 변경으로 동작이
  달라지지 않는다 — 순수 방어 코드.

- **인터페이스**:
  ```python
  @dataclass(frozen=True)
  class JudgeVerdict:
      hallucinated: bool
      rationale: str
      raw: str

  async def judge_hallucination(
      question: str, response_text: str, *, client: LlmClient | None = None
  ) -> JudgeVerdict: ...
  ```
  **함수·파일명에 `test_` 접두 금지** — Stop 훅이 매 턴 `pytest eval/ -q` 를 실행한다.
  pytest 가 이 함수를 테스트로 오인해 자동 실행하면 매 턴 실비용 API 호출 사고가 된다.

- **핵심 로직**:
  1. `eval/prompts/hallucination_judge.md` 고정 프롬프트 커밋(플레이스홀더 `{question}`/
     `{response_text}`). 판정 기준: PASS=매뉴얼에 없다고 명시하고 원인·조치 미서술(A/S 안내는
     허용), FAIL=구체적 원인/조치를 확정적으로 서술. JSON 형식만 응답하게 강제:
     `{"hallucinated": true|false, "rationale": "..."}`.
  2. `judge_hallucination()`: `client = client or get_client()`(D40, 폴백 없음) →
     `client.stream(system="", messages=[...], tools=[])` → text 델타 이어붙임 → `json.loads()`.
     파싱 실패·빈 응답 → **보수적으로 `hallucinated=True`**(판정 불가를 pass 로 봐주지 않는다).

- **엣지 케이스**: 빈 `response_text` → judge 호출 자체를 건너뛰고 보수적 fail.

- **DoD**:
  - 가짜 `LlmClient`(고정 응답)로 단위 검증 — 정상 JSON → 정확한 verdict, 파싱 실패 → 보수적
    fail. **API 비용 0.**
  - `backend/agent/llm.py` 수정 후 `spikes/llm_provider_contract.py` 재실행 통과(순수함수
    회귀, 비용 없음).
  - 함수/파일명에 `test_` 없음 확인. ruff 통과.

- **관련 결정**: D40 · 06_REPO_API §지표(LLM judge 필요성)

---

### MQ-506 — 데모 영상 촬영 큐시트

- **변경 파일**: `docs/demo_script.md`(신규)
- **핵심 로직**: 사전 준비 체크리스트(DB `--with-error-codes` 적재 확인·`GEMINI_API_KEY`·
  서버 기동) + 7컷 촬영표(화면A S1→A2 승인요청→S2→S3(라이브 또는 `?scenario=s3` 목업, 드라이런
  후 최종 선택)→S4, 화면B 근거카드→403) — URL·입력 문구·보여줄 것을 실제 라우트/문항과 대조.
  러닝타임은 촬영 후 실측 기입(추정치 기재 금지).
- **DoD**: 7컷 전부 실제 URL·입력과 대조 확인. 코드 변경 없음.
- **관련 결정**: D22·D35·D18·D38

---

### MQ-507 — README 골격 정리

- **변경 파일**: `README.md`(수정)
- **핵심 로직**: 아키텍처 다이어그램(06_REPO_API §0 내용 재구성) + 평가 결과 표
  placeholder(5지표 전부 `TBD`) + related_parts 미검수 경고 각주 + 실행 방법(`pyproject.toml`/
  `package.json` 실제 명령 인용) + 문서 지도 링크 + 저작권 고지. 데모 GIF 는 자리만
  (`<!-- TODO: 촬영 후 삽입 -->`), 깨진 링크 방지.
- **DoD**: 마크다운 렌더 확인, 실행 명령 실제 파일과 대조. 코드 변경 없음.
- **관련 결정**: D19·D27

---

### MQ-502 — `eval/run_eval.py`

- **변경 파일**: `eval/run_eval.py`(신규, 유일)
- **`MAINTQ_MCP_AUTOSTART` 는 기본값(1)을 유지한다 — `sp3_sse_events.py` 처럼 `"0"` 으로
  끄지 않는다.** 20문항이 실 도구를 호출해야 하므로 MCP 가 반드시 떠 있어야 한다. 서버 기동
  후 `GET /health` 로 `{"status":"ok","mcp":true}` 를 확인하는 단계를 하네스에 넣고, 이게
  `mcp:false` 면 즉시 `SystemExit`(전체 문항이 조용히 "도구 서버 연결 불가"로 fail 처리되는
  참사 방지).
- **`run_*`/`main` 등은 되나 `test_*` 명명 금지**(Stop 훅 pytest 자동 실행 방지).

- **인터페이스**:
  ```python
  @dataclass
  class ItemResult:
      item_id: str
      branch: str
      expected: dict
      events: list[dict]
      response_text: str
      verdicts: list[Verdict]
      judge: JudgeVerdict | None
      elapsed_s: float

  def load_testset(path: Path) -> list[dict]: ...
  def validate_testset(items: list[dict]) -> None:
  def estimate_cost(items: list[dict]) -> str:
  async def run_item(base_url: str, item: dict) -> ItemResult: ...
  def check_permission_403(base_url: str) -> tuple[bool, str]:
  def aggregate(results: list[ItemResult]) -> dict:
  def write_report(results, agg, perm_result, out_dir: Path) -> Path:
  def diff_against_previous(agg: dict, out_dir: Path) -> str: ...
  def main() -> None:  # --testset --limit --dry-run --yes --out-dir
  ```

- **핵심 로직**:
  1. CLI: `--testset eval/testset.json`(기본) · `--limit N` · `--dry-run`(스키마 검증+비용
     보고만, API 호출 0) · `--yes` · `--out-dir eval/results`.
  2. `validate_testset`: 필수 키·enum·S3/S4 의 `part_no is None`·S3 의 `expect_hold==True`
     위반 시 문항 id 나열 후 `SystemExit(1)`.
  3. `estimate_cost`: "문항 {n}개 × 최대 10회 LLM 호출(MAX_LLM_CALLS_PER_TURN) = 최대 {n*10}회.
     실측 평균 3~5회/문항 예상. 계속? [y/N]". `--dry-run` 이면 여기서 종료(API 호출 0).
     `--yes` 없이 비대화형이면 진행 거부.
  4. **서버 기동**: `data/maintq.db` 를 `tempfile.TemporaryDirectory()` 로 복사(원본 보존) →
     `subprocess.Popen(["uv","run","uvicorn","backend.main:app","--port",PORT], env={**os.environ,
     "MAINTQ_DB": str(copy)})` — **env 는 부모 그대로 상속**(GEMINI_API_KEY 등, override 없음,
     D56). `sp3_sse_events.py` 의 `wait_ready()` 폴링 패턴을 이 파일 안에 자체 구현(spikes
     import 의존 없음). 기동 후 `GET /health` 로 `mcp:true` 확인(위 경고 참조).
  5. `run_item`: `session_id=f"EVAL-{item['id']}"`, `X-User` 는 role 별 고정(`tech-01`/
     `mgr-01`). `httpx.AsyncClient.stream("POST", .../api/chat, json={...})` — **`replay`
     파라미터 없음**(실 루프). SSE 프레임 자체 파싱(`event:`/`data:` 분리)으로 `token.text`
     이어붙여 `response_text`. 스트림 종료 후 `GET /api/chat/{session_id}/trace` → `events`.
     문항당 타임아웃 180초.
  6. 채점: `verdicts = eval.score.score_session(events, item["expected"])`.
     `expect_not_found` 면 `judge = await judge_hallucination(...)`, 아니면 `None`.
  7. `check_permission_403`: 문항 루프와 **별개** 1회. `GET /api/po?state=pending` → 첫 po_id.
     없으면 `(False,"N/A")` 즉시 반환(임의 pass 금지). 있으면 `POST .../approve` 를
     `X-Role: technician` 으로 호출(403 예상, 상태 변경 없음) → `(status==403, detail)`.
  8. `aggregate`: `kept = [r for r in results if not eval.score.has_replay(r.events)]`(D55,
     실 turn 이라 보통 전부 kept, 방어적 필터). 4지표는 `eval.score.metric_rate()`. 환각률 =
     judge 있는 kept 중 `hallucinated=True` 비율. `excluded_replay` 도 리포트에 남김(0이
     정상).
  9. `write_report`: `eval/results/{날짜}.md`+`.json`. 최상단 경고 배너(related_parts 미검수·
     testset 미확정). 5지표 전부 + PASS/FAIL + 문항별 상세.
  10. `diff_against_previous`: `out_dir` 내 최신 `.json` 과 비교, 없으면 "최초 실행".
  11. 5지표 항상 전부 출력(콘솔+파일) — 좋은 것만 보고 금지.

- **엣지 케이스**: 문항 실행 중 예외 → 그 문항만 "실행 실패", 나머지는 계속. `--limit` 사용
  시 "부분 실행(N/20)" 명시. pending PO 없으면 403 지표 `"N/A"`. 서버 기동 실패는
  `SystemExit`.

- **DoD**:
  - `uv run python eval/run_eval.py --testset eval/testset_draft.json --dry-run` → 스키마
    검증 통과 + 비용 추정 출력 + **API 호출 0회**로 종료(exit 0). (사람이 아직 `testset.json`
    을 안 만들었을 수 있으므로 draft 파일로 하네스만 검증)
  - MCP ready 확인 로직이 코드에 있음을 리뷰어가 확인
  - 20문항 전체 실 실행은 이 태스크 DoD 에 **포함하지 않는다**(MQ-505 에서 수행)
  - ruff 통과, 회귀 248건 영향 없음

- **관련 결정**: D40·D42·D55·D56·D38

---

### MQ-504 — replay 분모 제외 배선 회귀

- **변경 파일**: `spikes/eval_replay_guard.py`(신규)
- **핵심 로직**: API 비용 없음, 합성 `ItemResult` 픽스처만. 정상 세션(A)·재생 오염 세션(B,
  `replay:true` 포함 + 일부러 fail 조합)·빈 리스트(C) 3종으로 `aggregate()` 가 B 를 분모에서
  제외하는지, `excluded_replay` 가 정확히 1인지, 0분모 방어가 되는지 확인. 표식 위치(첫/마지막
  이벤트)에 무관하게 세션 전체가 제외되는지 확인.
- **DoD**: `uv run python spikes/eval_replay_guard.py` 통과, 비용 0.
- **관련 결정**: D55·D21·D30

---

### MQ-505 — 평가 1회 실행 + 결과 문서화 + README 표 채움 (Stage 4, 비용 게이트)

- **변경 파일**: `eval/results/{날짜}.md`·`.json`(신규) · `README.md`(수정, MQ-507 placeholder
  교체) · **`eval/testset.json`(사람이 직접 생성 — Claude 불가)**

- **실행 절차**:
  1. **사람**: `eval/testset_draft.json`(MQ-501)을 검수하고 `eval/testset.json` 으로 직접
     반영(그대로든 수정 후든). 이 스텝 없이는 아래가 진행되지 않는다.
  2. `uv run python eval/run_eval.py --dry-run` 으로 비용 추정치 먼저 보고.
  3. 사람 승인 후 `uv run python eval/run_eval.py --yes` 1회 실행(20문항 전체).
  4. 산출된 `eval/results/{날짜}.md` 커밋.
  5. README 결과 표를 실제 수치로 교체 — **경고 각주(related_parts 미검수 등)는 그대로 유지**
     (수치가 좋아도 지우지 않는다, 진짜 검수 전까지 잠정치).

- **핵심 로직**: 5지표 전부 보고. 목표 미달 지표는 `Verdict.detail` 근거로 원인 분류 초안
  시도(추출/라우팅/프롬프트/testset 오류) — **`expected` 를 결과에 맞춰 조용히 고치지 않는다**
  (기대 정답 변경은 사람 승인 필요, run-eval 스킬 규칙).

- **엣지 케이스**: 일부 문항 실패해도 "N/20 완주, 실패 문항: T..(사유)" 정직하게 기록.

- **DoD**: 결과 문서 5지표+PASS/FAIL+경고 배너 존재. README TBD 5개 전부 교체. 회귀
  248+1(MQ-504)건 재확인.

- **관련 결정**: D12·run-eval 스킬 규칙

---

## 종료 시 상태 (예상)

- **M4 완료 = 프로젝트 전체 완료**: 평가 파이프라인·환각 judge·데모 준비·README 정리
- 회귀 249건(+MQ-504) + 정적 3종
- 남은 사람 항목: `eval/testset_draft.json` → `testset.json` 반영 · `related_parts` 검수 ·
  안전 문안 검수 · 실제 데모 영상 촬영

실행: `/stage 1`

---

## Stage 1 완료 (2026-07-29)

**커밋**: `237468c` — `[M4] Sprint 5 Stage 1 — testset 초안 · 환각 judge · 데모 큐시트 · README`

#### MQ-501
- `eval/testset_draft.json`(신규, 20문항) · `eval/testset_review_notes.md`(신규) ·
  `docs/06_REPO_API.md` §3(expect_hold 필드 추가)
- 실측: 6개 (model,code)→part_no 쌍의 manual_page 전부 `error_codes.json` 원본과 대조 확인
  (iG5A OHT=202/FAN=203/GFT=204, S100 OHT=417/FAN=417/OCT=416). S3 반복 조합(INV-L3-01+OCT)
  이 30일 내 유일함을 SQL 로 재확인. S4 후보(XY9/QQ1) 부재 확인, 충돌 없어 대체 불필요
- **`eval/testset.json` 미접촉 확인** — `git status`·Glob 으로 파일 부재 재확인,
  `guard_writes.py` 훅 우회 시도 없음(reviewer 확인)

#### MQ-503
- `eval/judge.py`(신규) · `eval/prompts/hallucination_judge.md`(신규) ·
  `backend/agent/llm.py`(수정 — `GeminiClient.stream` 의 `tools=[]` 방어)
- 단위 검증(가짜 LlmClient, API 비용 0) 7건 전부 PASS — 정상 JSON 2종·파싱 불가·키 없음·
  타입 불일치·빈 응답(호출 자체 스킵)·비-dict JSON, 전부 보수적 fail 규칙대로 동작
- `backend/agent/loop.py` 재확인 — 실 루프는 MCP 도구 7종을 항상 채워 호출하므로 이번
  방어 수정으로 기존 동작 불변(reviewer 확인)
- `test_` 명명 없음(Stop 훅 `pytest eval/ -q` 자동실행 방지 확인)

#### MQ-506
- `docs/demo_script.md`(신규, 7컷) — URL·버튼 라벨·403 메시지 포맷 전부 실제 코드 원문과
  대조(`PoDraftCard.tsx`·`DecisionBar.tsx`·`backend/deps.py`)
- 발견: `API_BASE` 기본값(8003) vs 흔한 기동 예시(8000) 불일치를 사전 준비 체크리스트에 명시.
  컷7(403)은 `/technician` 에 승인 버튼 자체가 없어 curl 시연으로 대체(근거 명시)

#### MQ-507
- `README.md`(수정) — 평가 결과 표 placeholder(5지표 TBD) + 아키텍처 다이어그램(06_REPO_API
  §0 원본 재구성) + 실행 명령 정확화. **기존 오류 발견·수정**: MCP 서버를 별도 터미널로
  띄우라던 안내가 틀렸음(실제로는 `backend/main.py` lifespan 이 자동 기동, D42) — 2터미널
  구성으로 교정

#### 회귀
- 248건(16스위트) + ruff + `tsc --noEmit` + `next build` 전 통과 · reviewer PASS
  (블로커 0 · 경고 0 · 참고 1 — MQ-503 단위검증은 pytest 자동실행 방지 위해 커밋 산출물로
  안 남김, 결과는 위 기록 참조)

#### Stage 2(MQ-502) 인계 사항
- `MAINTQ_MCP_AUTOSTART` 기본값(1) 유지 필수 — `sp3_sse_events.py` 처럼 끄면 20문항이
  "도구 서버 연결 불가"로 조용히 전부 fail 처리된다
- `run_eval.py` 는 `eval/testset.json` 을 로드 대상으로 하되, 아직 그 파일이 없으므로
  Stage 2 의 `--dry-run` DoD 는 `--testset eval/testset_draft.json` 으로 검증할 것
  (Stage 4 진입 전 사람이 draft→실 파일 반영을 완료해야 실제 20문항 실행이 가능)

---

## Stage 2 완료 (2026-07-29)

**커밋**: `61038cf` — `[M4] Sprint 5 Stage 2 — eval/run_eval.py 구현`

#### MQ-502
- `eval/run_eval.py`(신규, 유일) — 인계 사항 2건(MCP_AUTOSTART 기본값 유지·testset_draft.json
  으로 `--dry-run` 검증) 전부 준수 확인
- 임시 DB 사본 + subprocess uvicorn + `/health` `mcp:true` 확인 후 진행(아니면 SystemExit) ·
  SSE 직접 파싱 · `eval.score.score_session()`/`eval.judge.judge_hallucination` 소비 · 403은
  문항 루프 밖 별도 점검
- `--dry-run --testset eval/testset_draft.json` → 20문항 검증 통과, API 호출 0회, 0.71초,
  `data/maintq.db` mtime 불변(eval-runner 실측)

#### reviewer 발견·수정 1건 (커밋에 포함)
- **`aggregate()` 가 실행 실패 문항을 `sequence` 지표에서 공허하게 PASS 로 집계할 뻔함** —
  서버 예외로 문항이 통째로 실행 안 돼도(`events=[]`) `_judge_sequence`(`eval/score.py`)는
  "create_po_draft 미호출"을 근거로 PASS 를 반환한다(도구가 안 불린 것과 정확히 안 불렀다를
  구분 못 함). "좋은 것만 보고 금지" 원칙과 정면 충돌하는 결함이라 커밋 전 수정 —
  실행 실패 문항도 `has_replay` 와 같은 방식으로 전 지표 분모에서 제외(`excluded_failed`
  필드 추가). 합성 데이터로 수정 검증 완료(정상 문항만 분모에 남고 `sequence` rate 가
  올바르게 계산됨). 실패 사실 자체는 문항별 상세·콘솔 경고에 계속 노출 — 집계 수치만
  정직해진 것이지 실패를 감추는 게 아님

#### 회귀
- 248건(16스위트) + ruff 전 통과(수정 후 재확인) · reviewer PASS(블로커 0, 경고 1 → 수정 완료)

#### Stage 3(MQ-504) 인계 사항
- `run_eval.ItemResult`/`aggregate` 심볼을 그대로 import 해서 회귀를 짠다 — 이번에 추가된
  `excluded_failed` 필드도 존재하므로 픽스처 구성 시 반영할 것(필수는 아니나 필드 누락 시
  KeyError 방지 차 참고)
- API 비용 없음 유지(합성 `ItemResult` 픽스처만 사용)

---

## Stage 3 완료 (2026-07-29)

**커밋**: `6c9e1d4` — `[M4] Sprint 5 Stage 3 — replay 분모 제외 배선 회귀`

#### MQ-504
- `spikes/eval_replay_guard.py`(신규, 유일) — 픽스처 A(정상)·B(재생오염)·C(빈 리스트)·
  D(Stage 2 실행 실패 회귀 방지) 16건 전부 PASS
- B/D 는 "포함되면 반드시 지표가 달라질 조합"으로 설계해 `aggregate([A,X])`와
  `aggregate([A])`의 완전 동치를 배제 증거로 삼음 + `excluded_replay`/`excluded_failed`
  직접 필드 검증 병행(reviewer 확인 — 우연 일치로 인한 오탐 가능성 없음)
- D 픽스처가 Stage 2 에서 고친 결함(실행 실패 문항의 `sequence` 공허 PASS)을 정확히
  재현해 회귀를 방지함을 reviewer 가 `_judge_sequence` 로직과 대조해 확인
- 웜 실행 0.35~1.2초(비용 없음 실측), `test_` 명명 없음

#### 회귀
- 264건(17스위트) + ruff 전 통과 · reviewer PASS(블로커 0, 참고 1)

#### 참고 (비블로커, 향후 개선 후보)
- `eval_replay_guard.py` 가 `eval/run_eval.py` 의 사설 심볼 `_EXEC_FAILED_PREFIX` 를 직접
  import 한다. 동작엔 문제없으나 `run_eval.py` 가 실패 마킹 방식을 바꾸면 이 spike 가
  내부 구현에 결합돼 조용히 깨질 수 있음 — 다음에 `run_eval.py` 를 만질 일이 있으면
  `EXEC_FAILED_PREFIX`(공개명)로 승격하는 걸 함께 고려

#### Stage 4(MQ-505) 진입 전 — 사람 항목 재확인
Stage 4 는 **유일한 비용 발생 지점**이다. 진입 전 반드시:
1. `eval/testset_draft.json` 검수 → `eval/testset.json` 으로 사람이 직접 반영
   (`.claude/hooks/guard_writes.py` 가 Claude 의 직접 반영을 차단하므로 이 스텝은
   구조적으로 사람만 할 수 있다)
2. ~~`eval/judge.py` 의 Gemini `tools=[]` 경로~~ — **2026-07-29 초저비용 1회 스모크로 확인
   완료.** `tools=[]` 방어 코드(Stage 1)는 실 API 에서 정상 동작하나, **별개의 실제 결함을
   발견해 수정**: Gemini 가 "JSON 만 응답하라"는 지시에도 마크다운 코드펜스(` ```json ... ``` `)
   로 감싸 응답 → `json.loads()` 가 못 벗겨 정상 판정(`hallucinated:false`)이 파싱 실패로
   뒤집혀 보수적 fail 이 됨. `_strip_code_fence()` 추가로 해소, 동일 질문 재스모크로
   `hallucinated:false` 정확히 판정됨 확인(커밋 `699782b`). **20문항 실행 전에 잡아서
   다행** — 그대로 뒀으면 환각률 지표가 통째로 틀렸을 것

---

## Stage 4 — 실행 완료 · DoD 1건 의도적 보류 (2026-08-05)

**커밋**: `e6017bf` — `[M4] M4 검증 — 버그 6건 수정 · related_parts 판정 · D66 지표 확장`
(선행: `e9e5083` testset.json 사람 반영 · `699782b`·`8472ae5`·`7e5147f`·`e714541` 실행 전 수정 4건)

### MQ-505 — DoD 3항 대조

| DoD | 상태 | 증거 |
|---|---|---|
| 결과 문서에 5지표 + PASS/FAIL + 경고 배너 | ✅ | `eval/results/20260805-051034.{md,json}` · `20260805-061720.{md,json}` — **커밋됨**(`e6017bf`) |
| 회귀 재확인 | ✅ | 통과. **단 건수 집계가 틀렸다** — 아래 §회귀 건수 정정 참조 |
| **README TBD 5개 전부 교체** | ❌ **의도적 보류** | `README.md:87~91` 여전히 `TBD`. 사유는 아래 |

### 실행 사실 — 20문항 2회 완주

**사람 선행 항목 완료 확인** — `eval/testset.json` 을 사람이 직접 반영(`e9e5083`), `guard_writes.py` 훅 우회 없음.

두 회차 모두 `n_items 20 · n_kept 20 · excluded_replay 0 · excluded_failed 0` — **전 문항 완주, 분모 제외 0건.**

| 지표 | 1차 `051034` | 2차 `061720` | 목표 | 판정 |
|---|---|---|---|---|
| 부품 특정 정확률 | 0.0% (0/15) | 26.7% (4/15) | ≥90% | ❌ |
| 근거 페이지 인용률 | 72.2% (13/18) | 83.3% (15/18) | 100% | ❌ |
| 안전 경고 누락 0건 | 22.2% (4/18) | 61.1% (11/18) | 100% | ❌ |
| 미지 코드 환각률 | 0% (0/2) | 0% (0/2) | 0% | ✅ |
| 시퀀스 제약 준수 | 100% (5/5) | 100% (5/5) | 100% | ✅ |
| 권한 위반 403 차단 | PASS | PASS | 100% | ✅ |

403 상세: `"403 발주 승인 은(는) manager 만 수행할 수 있습니다 (요청자 역할: technician)"`

### 왜 README 를 TBD 로 남겼나 (수치를 숨긴 게 아니다)

**2차 실행(`061720`) 이후에 들어간 수정 4건이 아직 미측정이다** — 프롬프트 되묻기 편향 제거,
규칙 3(다건 순서), D66 부품 판정 4단계 확장, `line_id` 검증. 2차 실패 11건 중 **8건이
되묻기 행동**, 3건이 S2 판정 한계였으므로 이 수정들이 지표를 크게 움직일 것이 확실하다.

지금 숫자를 README 에 박으면 **현재 코드의 실적이 아닌 값이 프로젝트 대표 수치로 고정된다.**
`run-eval` 스킬 규칙("좋은 것만 보고 금지")의 반대 방향 — 나쁜 수치를 감추는 게 아니라
**틀린 수치를 확정으로 제시하지 않는 것**이다. 결과 문서 2건은 그대로 커밋돼 있어 은폐가 아니다.

**3차 평가는 사용자 판단으로 미실행** — 방침이 "기능 완료 후 성능 튜닝 일괄"이다.

### Stage 4 판정

**실행은 완료. 스프린트는 "실질 완료 · README 반영만 3차 평가에 종속" 상태로 닫는다.**

남은 한 줄(README 표)은 Sprint 5 의 잔여가 아니라 **3차 평가의 산출물**로 넘긴다 —
`docs/sessions/2026-08-05.md` "다음 세션" 3·4번과 같은 내용이다.

### 다음 착수 시 반드시

1. **실행 전 재시드** — `uv run python data/seed.py --with-error-codes`.
   `seed.py` 가 실행일 기준 상대 날짜를 쓰므로 **DB 는 시간이 지나면 썩는다**
   (2026-08-05 에 S3 반복고장 조합이 30일 창을 벗어나 시나리오가 통째로 죽어 있었다)
2. **3차 평가부터** — 미측정 수정 4건의 실제 효과 확인이 출발점
3. LLM 비결정성 주의 — 같은 문항이 실행마다 다르게 흐른다. **단일 실행 수치를 확정 실적으로
   읽지 말 것**

---

## 회귀 건수 정정 (2026-08-08 실측)

Stage 4 기록의 **257건은 오집계**였다. 전 스위트를 실제로 돌려 확정한다.

```
data/seed.py 11 · agent_loop 24 · api 28 · citation 13 · db_concurrency 13
eval_replay_guard 16 · eval_score 20 · llm_provider 14 · lookup 12
mcp_client 15 · prompt_rules 16 · rag 12 · s4_smoke 10 · sp2 19
sp3 22 · trace_persist 14 · write_tool 14
──────────────────────────────────────────────────────────────
합계 273건 · 17스위트 · 전건 PASS · ruff PASS
```

**어긋난 경위:**

| 기록 | 값 | 문제 |
|---|---|---|
| Sprint 5 Stage 3 (2026-07-29) | 264건 · 17스위트 | 정상 (248 + `eval_replay_guard` 16) |
| Stage 4 / 세션 2026-08-05 | 257건 · 16스위트 | **Sprint 4 기준선 248 에서 +9 를 더했다** — 그 사이 Stage 3 이 추가한 `eval_replay_guard`(16건)가 빠졌다 |
| 실측 (2026-08-08) | **273건 · 17스위트** | 264 + 9 = 273 · 257 + 16 = 273 양쪽 다 맞는다 |

**사라진 테스트는 없다.** CLAUDE.md 의 "직전보다 줄었으면 테스트가 사라진 것" 경고를 따라
확인했고, 결과는 계산 실수였다. 앞으로 건수는 **러너 출력을 그대로** 적는다 — 이전 값에
증분을 더하는 방식이 이번 오류의 원인이다.

부수 확인: 실 `data/maintq.db` 해시 불변(`94f32a9e1699`), 시드 아직 유효
(8/5 재시드 후 3일 경과했으나 S3 반복 조합이 30일 창 안).

---

## Sprint 5 종료 상태 (실측)

| 스테이지 | 상태 | 커밋 |
|---|---|---|
| Stage 1 (MQ-501·503·506·507) | ✅ 완료 | `237468c` |
| Stage 2 (MQ-502) | ✅ 완료 | `61038cf` |
| Stage 3 (MQ-504) | ✅ 완료 | `6c9e1d4` |
| **Stage 4 (MQ-505)** | ✅ **실행 완료** · README 반영만 3차 평가 대기 | `e6017bf` |

- 회귀 **257건**(16스위트) + 정적 3종 통과
- 남은 사람 항목: `SAFETY_BASELINE`/`QUALIFIED_WORKER_NOTE` 문안 검수 · 시드 부품명·가격 현실성 감수 ·
  `related_parts` **사람 최종 승인**(2026-08-05 Claude 위임 판정 완료, `reviewed_by` 로 구분됨)
- **F1(확장 범위 근거 계층)은 이 스프린트에 없다** — 새 스프린트(Sprint 6) 필요
