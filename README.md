# MaintQ

> 설비 진단부터 부품 발주까지 — 제조 현장 AI 보전 에이전트

**Q 시리즈 3번째 프로젝트** (FinAllQ · InsuQ · MaintQ)
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
- MCP 도구 총 7종 = 읽기 6종: `lookup_error_code` `rag_search_manual` `get_error_history` `search_inventory` `find_alternative_parts` `get_supplier_quotes` + 쓰기 전용 1종: `create_po_draft`(draft INSERT만 가능 — 승인/반려는 `backend/routers/po.py`의 사람 전용 API, D10)

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

| 지표 | 목표 | 결과 |
|---|---|---|
| 부품 특정 정확률 | ≥90% | TBD (run_eval 실행 후 채움) |
| 근거 페이지 인용률 | 100% | TBD (run_eval 실행 후 채움) |
| 안전 경고 누락 | 0건 | TBD (run_eval 실행 후 채움) |
| 미지 코드 환각률 | 0% | TBD (run_eval 실행 후 채움) |
| 권한 위반 403 차단 | 100% | TBD (run_eval 실행 후 채움) |

> ⚠ **위 표는 아직 채우지 않았다.** 실 20문항 평가는 2026-08-05 에 2회 완주했고 리포트는
> `eval/results/` 에 있으나, 그 이후 들어간 수정(프롬프트 되묻기 제거·다건 부품 순서·
> D66 판정 확장)이 **미측정**이라 확정 수치가 아니다. 측정 이력과 남은 갭은
> `docs/sessions/2026-08-05.md` §검증 상태 참조.
>
> ⚠ `related_parts.seed.json` 은 Claude 위임 판정(2026-08-05)이고 **사람 최종 승인 전**이다
> (D12) — 부품 특정 정확률을 인용할 때 이 사실을 함께 밝힐 것.

## 문서

문서 지도(전체 목록·언제 열어보는지·진행 상태 요약)는 **[docs/README.md](docs/README.md)** 에 위임한다(이중 관리 방지). 자주 찾는 문서만 아래 요약:

| | |
|---|---|
| [00 MVP_SCOPE](docs/00_MVP_SCOPE.md) | 반드시 구현할 기능 6종 + 인프라 + 완료 기준 |
| [02 SCENARIOS](docs/02_SCENARIOS.md) | S1~S4 상세 |
| [04 MCP_TOOLS](docs/04_MCP_TOOLS.md) | 도구 7종(읽기 6+쓰기 1) 입출력·설계 원칙 (계약 임의 변경 금지) |
| [06 REPO_API](docs/06_REPO_API.md) | 모노레포 구조·REST/SSE 설계·평가셋 스키마 |
| [09 RUNTIME](docs/09_RUNTIME.md) | 시퀀스·루프 정책·장애 모드 |
| [10 DECISIONS](docs/10_DECISIONS.md) | 설계 결정 D1~ 과 이유 — "왜 이렇게 했나" 여기서 확인 |

## 데이터 출처 · 저작권 고지

- LS일렉트릭 공식 다운로드 센터에서 받은 공개 자료 — SV-iG5A, S100 사용설명서. **저작권은 LS ELECTRIC에 있으며**, 본 프로젝트는 비상업적 학습·포트폴리오 목적으로만 이를 참조한다.
- 매뉴얼 원본 PDF는 이 저장소에 **포함하지 않는다**(`data/raw/`는 git 제외 — 읽기 전용, 재배포 없음). 출처·버전·해시는 `data/raw/manifest.json`으로만 추적한다(D19).
- AI허브 「기계시설물 고장 예지 센서」 고장 유형 분포 참고 (에러 이력 시드 생성)
- 재고·공급사·발주 데이터는 전부 목업

## 상태

M1~M3 완료 · M4(평가 파이프라인·데모·문서 정리) 진행 중 — 상세 진행 상태는 [docs/README.md](docs/README.md) 참조
