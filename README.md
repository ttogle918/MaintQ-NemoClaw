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

## 아키텍처

```
[정비사 UI]──┐
[팀장 UI]  ──┤→ [FastAPI 백엔드] → [Agent Loop] → [MCP 서버] → [SQLite 목업 DB]
             │        └ SSE (token / tool_call / tool_result / block)   └ [벡터스토어 (매뉴얼)]
```

- MCP 서버·백엔드 프로세스 분리 → 목업 DB를 실제 ERP로 교체 시 MCP 서버만 갈아끼우면 됨
- MCP 도구 총 7종 = 읽기 6종: `lookup_error_code` `rag_search_manual` `get_error_history` `search_inventory` `find_alternative_parts` `get_supplier_quotes` + 쓰기 전용 1종: `create_po_draft`

## 빠른 시작

요구사항: Python 3.13+, [uv](https://docs.astral.sh/uv/) (D27 — Docker는 MVP 제외, 백로그 P14)

```bash
git clone https://github.com/<YOUR_ID>/MaintQ.git && cd MaintQ
uv sync                              # .venv 생성 + uv.lock 기준 의존성 설치
cp .env.example .env                 # ANTHROPIC_API_KEY 입력

uv run python data/seed.py           # 목업 DB 생성 (시드 케이스 맵 7종)

# 프로세스 2개를 각각 띄운다 (D15: MCP 서버·백엔드 분리)
uv run python mcp_server/server.py                        # 터미널 1 — MCP 서버
uv run uvicorn backend.main:app --reload --port 8000      # 터미널 2 — FastAPI 백엔드
```

> 현재 M1(데이터 준비) 단계 — `seed.py`·`mcp_server`·`backend`는 M2에서 구현 예정이라 위 명령 중 일부는 아직 동작하지 않는다. 데이터 파이프라인은 지금도 실행 가능: `uv run python data/extract_error_codes.py`

## 시나리오 (도구 오케스트레이션 패턴 4종)

| # | 시나리오 | 증명하는 패턴 |
|---|---|---|
| S1 | 진단→재고→발주 풀 파이프라인 | 순차 도구 실행 |
| S2 | 재고 0 → 호환 대체품 → 비교 제시 | 조건 분기 |
| S3 | 반복 고장 감지 → 근본원인 모드 + 안전 경고 | 이력 기반 판단 + 가드레일 |
| S4 | 미지 에러코드 → 추측 없이 한계 인정 → A/S 안내 | 실패 처리 (환각 방지) |

## 평가

에러코드 20개 테스트셋 자동 실행 (`eval/run_eval.py`)

- 부품 특정 정확률 ≥ 90%
- 근거 페이지 인용률 100%
- 안전 경고 누락 0건
- 미지 코드 환각률 0%
- 권한 위반(정비사 approve 호출) 403 차단 100%

## 문서

| | |
|---|---|
| [00 INDEX](docs/00_INDEX.md) | 문서 지도 + 3줄 요약 |
| [01 OVERVIEW](docs/01_OVERVIEW.md) | 문제정의·페르소나·As-Is·KPI·Out of Scope·리스크·마일스톤 |
| [02 SCENARIOS](docs/02_SCENARIOS.md) | S1~S4 상세 |
| [03 WIREFRAME](docs/03_WIREFRAME.html) | 화면 A(진단 콘솔)·B(승인 큐) + 주석 |
| [04 MCP_TOOLS](docs/04_MCP_TOOLS.md) | 도구 7종(읽기 6+쓰기 1) 입출력·설계 원칙 |
| [05 DB_SCHEMA](docs/05_DB_SCHEMA.md) | 테이블 9종 + 시드 케이스 맵 |
| [06 REPO_API](docs/06_REPO_API.md) | 모노레포 구조·REST/SSE 설계 |
| [07 BACKLOG](docs/07_BACKLOG.md) | v2 이후 기능 |
| [08 DESIGN_BRIEF](docs/08_DESIGN_BRIEF.md) | Claude Design 투입 프롬프트 |
| [09 RUNTIME](docs/09_RUNTIME.md) | 시퀀스·루프 정책·장애 모드 |
| [10 DECISIONS](docs/10_DECISIONS.md) | 설계 결정 D1~D23과 이유 |

## 데이터 출처

- LS일렉트릭 공식 다운로드 센터 — SV-iG5A, S100 사용설명서 (비상업적 학습·포트폴리오 목적, 저작권은 LS ELECTRIC에 있음)
- AI허브 「기계시설물 고장 예지 센서」 고장 유형 분포 참고 (에러 이력 시드 생성)
- 재고·공급사·발주 데이터는 전부 목업

## 상태

🚧 설계 완료 · M1(데이터 준비) 진행 중
