# MaintQ

> 설비 진단부터 부품 발주까지 — 제조 현장 AI 보전 에이전트

**설비 진단부터 부품 발주까지 연결하는 B2B 제조 보전 AI 에이전트**
앞선 두 프로젝트가 "검색 깊이"를 다뤘다면, MaintQ는 **도구 오케스트레이션**을 다룬다.

---

## 무엇을 해결하나

중소 제조공장에서 인버터/PLC 에러가 발생하면:
PDF 매뉴얼 뒤지기(10~30분) → 고참 정비사 경험에 의존한 진단 → 자재담당에게 전화로 재고 확인 → 엑셀 발주서 수기 작성 → 팀장 결재. 매체가 계속 바뀌고(PDF→전화→엑셀), 단계마다 대기가 생긴다.

**CMMS는 기록 시스템이고, 매뉴얼은 정적 문서다. MaintQ는 그 사이 — 진단이라는 판단 업무를 자동화하고, 판단 결과를 조달 액션까지 연결한다.**

- 타겟: 중소 제조공장 설비보전팀 (B2B 사내 도구)
- 페르소나: **정비사**(진단·발주 요청) / **보전팀장**(승인·반려)
- 가설 KPI: 고장 발생 → 발주 완료 리드타임 30분+ → 5분

## 핵심 기능

| 기능 | 설명 |
|---|---|
| 에러코드 진단 | LS일렉트릭 공개 매뉴얼(iG5A·S100) 기반. 코드 정의는 **정확 룩업**, 점검 절차는 **RAG** — 문제 성격별 이원화. 모든 답변에 근거 페이지 인용 |
| 부품 특정 → 재고/견적 | MCP 도구로 재고·안전재고·공급사 리드타임/단가 조회. 재고 없으면 호환 대체품 분기 |
| 발주서 초안 + 승인 워크플로우 | AI는 draft만 생성 가능(도구 권한 수준에서 강제). 확정은 팀장 승인 큐에서만 — human-in-the-loop |
| 반복 고장 감지 ★ | 동일 에러 30일 내 3회 → 단순 조치 대신 근본원인 점검 모드로 전환 |
| 안전 가드레일 ★ | 위험 작업(활선 측정, 콘덴서 방전 등) 언급 시 매뉴얼 근거와 함께 안전 경고 필수 삽입 |
| 실행 trace 시각화 | 에이전트가 어떤 도구를 왜 호출했는지 실시간 타임라인 — 이 프로젝트의 시그니처 화면 |

## 데모

<!-- TODO: 촬영 후 삽입 (docs/demo_script.md 큐시트 기준 7컷 GIF/영상) -->

## 아키텍처

```
[정비사 UI]──┐
[팀장 UI]  ──┤→ [FastAPI 백엔드] → [Agent Loop (LLM)] → [MCP 서버] → [SQLite 목업 DB]
             │        │                                      │
             │        └── SSE 스트림 (token/tool_call/       └── [벡터스토어 (매뉴얼 RAG)]
             │             tool_result/block — D14·D22)
```

(도식 원본: `docs/06_REPO_API.md` §0)

- MCP 서버·백엔드 프로세스 분리 (D15) → 목업 DB를 실제 ERP로 교체 시 MCP 서버만 갈아끼우면 됨. 단, 개발/데모 시에는 백엔드 `lifespan`이 MCP 서버를 서브프로세스로 **자동 기동**한다(D42) — 별도 터미널로 띄울 필요 없음
- MCP 도구 **코어 7종 + 확장 11종 = 18종**. 확장분은 `MAINTQ_TOOLS_PROFILE=full` 일 때만 등록된다(**D69** —
  기본 `core`. 도구를 늘린 채 평가를 돌리면 "수정 효과 vs 도구 증가 효과"를 분리할 수 없다.
  **D88** 이 이 기준선을 코드로 잠갔다 — `run_eval.py` 가 `/health` 실측으로 `core` 가 아니면 종료한다)
  확장 11종: `check_disposal_blockers` `verify_ownership` `classify_part_criticality`
  `get_maintenance_metrics` `classify_expenditure` `assess_repair_value` `build_evidence_bundle`
  `generate_disposal_document` `create_repair_record`(Sprint 9, D98)
  **`track_deadlines` `assess_risk_grade`**(Sprint 11, D102)
- 코어 7종 = 읽기 6종: `lookup_error_code` `rag_search_manual` `get_error_history` `search_inventory` `find_alternative_parts` `get_supplier_quotes` + 쓰기 전용 1종: `create_po_draft`
- **쓰기 도구는 3종**(`create_po_draft` · `generate_disposal_document` · `create_repair_record`) — 셋 다
  **draft INSERT 만** 가능하고 UPDATE 권한이 없다. 승인/반려/서명은 사람 전용 API
  (`backend/routers/po.py` · `backend/routers/decisions.py` · `backend/routers/repairs.py`)만 한다 (D10·D81·D98)

## 빠른 시작

요구사항: Python 3.11+ (개발 고정 버전은 3.13 — `.python-version`), [uv](https://docs.astral.sh/uv/) (D27 — Docker는 MVP 제외, 백로그 P14), Node.js(프론트)

```bash
git clone https://github.com/<YOUR_ID>/MaintQ.git && cd MaintQ
uv sync                              # .venv 생성 + uv.lock 기준 의존성 설치
cp .env.example .env                 # GEMINI_API_KEY, MAINTQ_LLM_MODEL 입력 (기본 제공자: gemini)

uv run python data/seed.py --with-error-codes   # 목업 DB 생성 (시드 케이스 맵 7종 + error_codes)

# 터미널 1 — FastAPI 백엔드 (MCP 서버는 lifespan이 자동 기동, D42)
uv run uvicorn backend.main:app --reload --port 8003

# 터미널 2 — 프론트 (localhost:3003)
npm --prefix frontend install
npm --prefix frontend run dev
```

MCP 도구만 단독으로 점검하려면(디버깅용, 평소엔 불필요): `uv run python mcp_server/server.py`

## 시나리오 (도구 오케스트레이션 패턴 4종)

| # | 시나리오 | 증명하는 패턴 |
|---|---|---|
| S1 | 진단→재고→발주 풀 파이프라인 | 순차 도구 실행 |
| S2 | 재고 0 → 호환 대체품 → 비교 제시 | 조건 분기 |
| S3 | 반복 고장 감지 → 근본원인 모드 + 안전 경고 | 이력 기반 판단 + 가드레일 |
| S4 | 미지 에러코드 → 추측 없이 한계 인정 → A/S 안내 | 실패 처리 (환각 방지) |

## 평가

에러코드 20개 테스트셋 자동 실행 (`eval/run_eval.py`) — 지표 판정 방법 상세는 `docs/06_REPO_API.md` §3 참조.

**측정 조건**: `llm_provider=gemini` · `llm_model=gemini-2.5-flash` · `tools_profile=core`(D88 이 `full`
로 평가하는 것을 코드로 막는다) · `--repeat 3`(20문항 × 3회차 = 60건, 회차 간 흔들림까지 잰 값)

| 지표 | 목표 | 결과 | 판정 |
|---|---|---|---|
| 부품 특정 정확률 | ≥90% | **40.0%** (18/45) | ❌ 미달 — 원인 규명됨, 아래 참조 |
| 근거 페이지 인용률 | 100% | **90.7%** (49/54) | ❌ 미달 |
| 안전 경고 누락 | 0건 | 통과 **70.4%** (38/54, 누락 16건) | ❌ 미달 — 원인 규명됨, 아래 참조 |
| 미지 코드 환각률 | 0% | **0.0%** (0/6) | ✅ 목표 달성 |
| 권한 위반 403 차단 | 100% | **PASS** | ✅ 목표 달성 |

출처: `eval/results/20260817-081049.json`(2026-08-17 실측, 마지막 측정). 권한 위반 403 은 `aggregate`
가 아니라 최상위 `permission_403` 키(`passed: true`, 정비사가 발주 승인을 시도 → 403 차단 확인)의
값이다.

> ⚠ **정직하게 밝힌다 — 목표 미달 2건은 "덜 만들어서"가 아니라 각각 다른 이유로 미달이다.**
>
> **① 부품 특정 정확률 40.0%(목표 ≥90%) — 원인은 추출 파이프라인이 아니라 원천 데이터다.**
> `docs/07_BACKLOG.md` **P32** 가 2026-08-14 실측으로 4개 축(조달청 전수·LS 매뉴얼 1,035청크
> 전수 스캔·국내 유통·해외 판매점)을 전부 확인했다 — **완제품 SKU 는 있지만 소모 교체품(냉각팬·
> 제어보드 등)의 실제 부품 품번은 LS일렉트릭이 아예 공개하지 않는다.** 매뉴얼 자체가
> *"FAN 교체는 구입처나 LS산전 고객센터에 문의하십시오"* 라고 명시한다 — 절차·경보 코드까지
> 다 있는데 품번만 없다. `data/related_parts.seed.json` 도 스스로 *"추출 파이프라인은 이 값을
> 만들어낼 수 없다"* 고 적어 뒀다. **PDF 추출을 개선해도 이 지표는 오르지 않는다** — 없는 데이터를
> 뽑을 수 없기 때문이다. 남은 유일한 경로는 **LS 고객센터 문의(사람, `TODO_직접할일.md`)** 뿐이다.
>
> **② 안전 경고 70.4%(목표 0건 누락) — 이건 "고치면 안 되는" 종류의 실패다.**
> `data/analysis/eval_gap_3rd.md` 군집 B 가 근거다: 부품 교체를 권하는 응답이 `rag_search_manual`
> 을 호출하지 않고 턴을 끝내면, 근거 페이지가 없으니 인용도 안전 문구도 만들 수 없다. 그런데
> **절대 규칙 3 이 "안전 문구는 매뉴얼 근거(페이지) 없이 생성 금지"** 이므로, 이 경우 안전 블록을
> 억지로 찍는 것 자체가 규칙 위반이다 — 즉 지금의 누락은 가드레일이 **정상 작동한 결과**다. 고칠
> 지점은 안전 문구 생성 로직이 아니라 **`rag_search_manual` 미호출**(에이전트가 파이프라인을
> 끝까지 밟지 않고 사용자에게 되묻고 턴을 종료하는 패턴) 쪽이다.
>
> ⚠ 부품 특정 정확률의 근거인 `related_parts.seed.json` 은 **Claude 위임 판정(2026-08-05) →
> 사람 최종 승인(2026-08-12)** 두 단계를 거쳤고 **D12 게이트는 해제**됐다. 즉 위 40.0% 는
> **실적으로 인용 가능한 값**이다. 두 단계를 모두 남기는 것이 이 저장소 규약이다 —
> 누가 무엇을 판단했는지가 지워지면 승인의 의미가 사라진다(`data/related_parts.seed.json`
> 의 `_승인_이력`).

**회귀 현황**(2026-08-20 기준, `CLAUDE.md` 실측 기준선): spikes **32스위트 / 976건** · pytest **83건** ·
seed **36건** · 프론트 라우트 **18개**(`npx next build`).

**재현 방법**:

```bash
uv run python data/seed.py --with-error-codes     # ⛔ --today 금지 (검증 쿼리가 벽시계 기준)
uv run python eval/run_eval.py --dry-run           # D88 프로파일 가드 확인, LLM 호출 0회
uv run python eval/run_eval.py --yes --repeat 3    # 실행 (실비용 발생)
```

## 문서

문서 지도(전체 목록·언제 열어보는지·진행 상태 요약)는 **[docs/README.md](docs/README.md)** 에 위임한다(이중 관리 방지). 자주 찾는 문서만 아래 요약:

| | |
|---|---|
| [00 MVP_SCOPE](docs/00_MVP_SCOPE.md) | 반드시 구현할 기능 6종 + 인프라 + 완료 기준 |
| [02 SCENARIOS](docs/02_SCENARIOS.md) | S1~S4 상세 |
| [04 MCP_TOOLS](docs/04_MCP_TOOLS.md) | 도구 **코어 7 + 확장 11 = 18종** 입출력·설계 원칙 (계약 임의 변경 금지) |
| [06 REPO_API](docs/06_REPO_API.md) | 모노레포 구조·REST/SSE 설계·평가셋 스키마 |
| [09 RUNTIME](docs/09_RUNTIME.md) | 시퀀스·루프 정책·장애 모드 |
| [10 DECISIONS](docs/10_DECISIONS.md) | 설계 결정 **D1~D116** 과 이유 — "왜 이렇게 했나" 여기서 확인 |

## 데이터 출처 · 저작권 고지

- LS일렉트릭 공식 다운로드 센터에서 받은 공개 자료 — SV-iG5A, S100 사용설명서. **저작권은 LS ELECTRIC에 있으며**, 본 프로젝트는 비상업적 학습·포트폴리오 목적으로만 이를 참조한다.
- 매뉴얼 원본 PDF는 이 저장소에 **포함하지 않는다**(`data/raw/`는 git 제외 — 읽기 전용, 재배포 없음). 출처·버전·해시는 `data/raw/manifest.json`으로만 추적한다(D19).
- AI허브 「기계시설물 고장 예지 센서」 고장 유형 분포 참고 (에러 이력 시드 생성)
- 재고·공급사·발주 데이터는 전부 목업

## 상태

M1~M3 완료 · M4(평가 파이프라인·데모·문서 정리) 진행 중 — 상세 진행 상태는 [docs/README.md](docs/README.md) 참조
