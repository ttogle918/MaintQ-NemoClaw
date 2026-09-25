# MaintQ × NVIDIA — 해커톤 제출 문서

> **한 줄**: 영문 매뉴얼만 있는 새 기종 설비를 **OpenShell 샌드박스 안의 NVIDIA 에이전트**(NeMo Agent Toolkit + Nemotron)가
> 한국어로 온보딩하고, **사람이 검수·승격·안전 문구 승인을 해야만** 현장 진단 에이전트(OpenClaw)가 그 기종을 진단한다.

- 교육 미션: **Securing Agents with NemoClaw and OpenShell** (요건 원문 요약: [`day2-prep.md`](day2-prep.md) §1)
- 레포: `ttogle918/MaintQ-NemoClaw` · 라이선스 Apache-2.0(`LICENSE`)
- 이 문서의 모든 주장은 레포 안 파일·결정 번호(D1~D158, [`docs/10_DECISIONS.md`](../10_DECISIONS.md))로 근거를 단다.
  실행해 확인하지 못한 것은 「확인 안 됨」으로 적었다.

## 목차

1. [문제와 해법](#1-문제와-해법)
2. [NVIDIA 기술 사용 현황과 채점 기준 매핑](#2-nvidia-기술-사용-현황과-채점-기준-매핑)
3. [보안 설계 — 에이전트를 어디까지 믿지 않는가](#3-보안-설계--에이전트를-어디까지-믿지-않는가)
4. [데모 영상](#4-데모-영상)
5. [재현 가이드](#5-재현-가이드)
6. [한계·미완](#6-한계미완)
7. [완성도 지표](#7-완성도-지표)

---

## 1. 문제와 해법

**문제.** 설비 보전 현장에 새 기종이 들어오면 매뉴얼은 대개 영문 PDF 하나뿐이다. 현장은 고장 코드를 한국어로
빨리 알아야 하는데, AI 번역을 그대로 믿으면 두 가지 사고가 난다.

- **잘못된 진단** — 번역·추출이 틀린 고장 정의로 엉뚱한 조치를 한다. 모르는 코드를 비슷한 코드로 추측하면 더 위험하다.
- **잘못된 안전 문구** — 방전 대기 시간 같은 숫자가 틀리면 감전 사고로 이어진다. 기존 기종의 값(예: 10분)을 새 기종에 그대로 쓰는 것도 같은 오류다.

**해법.** 역할을 셋으로 나눴다.

| 단계 | 누가 | 무엇을 | 근거 |
|---|---|---|---|
| 추출 | 결정적 코드(LLM 없음) | PDF 고장 표에서 코드·페이지·원문 행을 뽑는다 | `data/extract_hv600_codes.py` · `data/extract_hv600_safety.py` (D153) |
| 한국어 정규화 | **NAT 에이전트 + Nemotron**, OpenShell 샌드박스 안 | 행마다 한국어 초안을 **스테이징 테이블에만** 쓴다 | `onboarding/nat/` · `skills/maintq-manual-onboarding` (D145·D153·D154) |
| 검수·승격·안전 승인 | **사람**(팀장) | 원문과 대조해 코드 그룹 단위로 승격, 안전 문구는 원문 페이지를 보고 직접 입력·승인 | `/manager/onboarding` · `backend/routers/onboarding.py` (D146·D147·D156·D157) |
| 진단 | **OpenClaw(NemoClaw)** + 제품 스킬 | 승격된 코드만 진단한다. 승격 전 코드는 추측 없이 A/S 안내 | `skills/maintq-diagnose` · `deploy/nemoclaw/` (D150~D152) |

같은 질문 "HV600에서 GF 떴어" 가 승격 전에는 「매뉴얼에서 확인되지 않는 코드 → A/S 안내」, 승격 후에는
「정의·원인·조치 + 사람이 승인한 안전 문구」로 바뀐다. 이게 데모의 핵심이다(§4).

MaintQ 본체(이 레포의 바탕)는 인버터 에러코드 진단 → 재고 → 견적 → 발주 초안까지 도구로 잇는 보전 에이전트다(S1~S4,
[`docs/02_SCENARIOS.md`](../02_SCENARIOS.md)). 해커톤에서는 그 위에 **새 기종 온보딩**(Sprint 19,
[`docs/sprints/sprint-19.md`](../sprints/sprint-19.md))과 **NVIDIA 런타임·샌드박스**를 얹었다. 대상 기종은
Yaskawa HV600(HVAC 팬·펌프용 인버터)이다(D145). 특정 공장이 이 기종을 쓴다고 주장하지 않는다.

---

## 2. NVIDIA 기술 사용 현황과 채점 기준 매핑

### 2.1 기술별 사용 현황

| 기술 | 사용 | 어디에 | 근거(파일·결정·실측 기록) |
|---|---|---|---|
| **Nemotron** | ✅ | 진단(웹 콘솔·OpenClaw)과 온보딩 정규화의 추론 모델 `nvidia/nemotron-3-super-120b-a12b` | [`day1.md`](day1.md) §1·§3(모델 ID 실측 — 목록에 있어도 404 인 ID 가 있었다) · `onboarding/nat/workflow.yml` |
| **NIM** (build.nvidia.com 호스팅 엔드포인트) | ✅ | 샌드박스 안은 `https://inference.local` → 게이트웨이가 키를 넣어 build.nvidia.com 으로 라우팅. 호스트에서는 임베딩 `nvidia/nemotron-3-embed-1b` | D143 · `backend/agent/llm.py` · NAT `llms._type: nim` · `data/external/nvidia_embed.py` · [`day2.md`](day2.md) §9 ⓘⓘ |
| **NeMo Agent Toolkit (NAT)** | ✅ | 온보딩 에이전트 런타임 — `tool_calling_agent` + `mcp_client`(streamable-http, 헤더 주입) + 가드 함수 | D153 · `onboarding/nat/`(`workflow.yml`·`maintq_nat/guarded_stage.py`·`run_normalize.py`) · 스파이크 [`day2.md`](day2.md) §9 |
| **Agent Skills** (SKILL.md) | ✅ | 제품 스킬 2종 `skills/maintq-diagnose`(OpenClaw 진단) · `skills/maintq-manual-onboarding`(정규화 규칙의 단일 원천) + 안전 규칙 스킬 `.claude/skills/safety-guardrail`. 개발용으로 NVIDIA 카탈로그 스킬 2종(`skill-card-generator`·`nemoclaw-user-guide`) 설치 | [`day2.md`](day2.md) §8 · `skills/maintq-diagnose/skill-card.md`(NVIDIA `skill-card-generator` 로 생성) · `evals/evals.json` 양쪽 |
| **SkillSpector** | ✅ | 스킬 공급망 게이트 — NVIDIA 카탈로그 스킬도 **설치 전** 스캔, 우리 스킬은 발견 사항을 고치거나 사람이 수용 판정 | [`day2-prep.md`](day2-prep.md) §3 · [`day2.md`](day2.md) §8 · 결과는 §3.8 |
| **OpenShell** | ✅ | 샌드박스 3개 — `maintq`(웹 콘솔 백엔드, BYOC) · `maintq-nat`(온보딩 NAT, BYOC) · `maintq-agent`(NemoClaw/OpenClaw) | `deploy/openshell/`(`Dockerfile.sandbox`·`Dockerfile.nat`·`policy.yaml`·`policy-nat.yaml`·`start.sh`) · [`day1.md`](day1.md) §5~§6 |
| **NemoClaw / OpenClaw** | ✅ | 현장 진단 에이전트. MaintQ MCP(core 7종)에 붙어 스킬 `maintq-diagnose` 로 진단 | D150·D151·D152 · `deploy/nemoclaw/presets/maintq-mcp.yaml` · `deploy/nemoclaw/workspace/build.py` · [`day2.md`](day2.md) §3~§8 |
| **MCP streamable-http** | ✅ | 같은 FastMCP 인스턴스에 두 번째 입구(stdio 유지). OpenClaw·NAT 가 bearer + `X-User` 로 붙는다 | D150~D152 · `mcp_server/http_entry.py` · `spikes/mcp_http_contract.py`(17건) |
| NeMo Guardrails | ❌ 사용 안 함 | 조사만 했다. 주입 판정은 Guardrails 대신 **서버 결정적 가드**로 했다(§3.6) | [`day2-prep.md`](day2-prep.md) §4 |
| NeMo Framework · NeMo Microservices | ❌ 사용 안 함 | 학습·파인튜닝·마이크로서비스 배포를 하지 않았다 | — |
| NIM 셀프호스팅 컨테이너 | ❌ 사용 안 함 | 호스팅 엔드포인트(build.nvidia.com)만 썼다 | — |
| build.nvidia.com 「Skill API」(HTTP) | ❓ 확인 안 됨 | 공개된 것은 카탈로그·`npx skills` CLI·문서 검색 MCP 뿐이었다. 우리는 SKILL.md 표준 형식으로 해석했다 | [`day2-prep.md`](day2-prep.md) §2 |
| NemoClaw managed MCP | ❌ 불가(실측) | 공인 DNS 엔드포인트를 요구해 로컬 데모에 맞지 않았다 → 커스텀 egress 프리셋으로 대체 | D151 |
| 스킬 OMS 서명 | ❌ 안 함 | NVIDIA 검증 스킬의 게시 파이프라인(서명) 단계는 하지 않았다 | [`day2-prep.md`](day2-prep.md) §2 |

### 2.2 채점 기준 ↔ 근거

| 채점 기준 | 우리가 보이는 것 | 근거 |
|---|---|---|
| **① NVIDIA Agent 기술 활용 심도** | 런타임 둘을 각자 자리에 뒀다 — **진단 = OpenClaw(NemoClaw)**, **온보딩 = NAT**. 둘 다 Nemotron 을 OpenShell 게이트웨이(`inference.local`)로만 부르고 샌드박스 안에 키가 없다. 두 런타임이 같은 MaintQ MCP 에 streamable-http 로 붙고, 스킬은 SKILL.md 표준으로 쓰고 SkillSpector 로 거른다 | D143·D150·D151·D153 · [`day2.md`](day2.md) §8·§9 · `onboarding/nat/workflow.yml` · `skills/` |
| **② 실용성·산업가치·혁신성** | 새 기종 도입 시 「영문 매뉴얼 → 한국어 진단 가능」 까지를 AI 초안 + 사람 승인 파이프라인으로 만든다. 안전 수치는 기종마다 매뉴얼 값을 쓴다(HV600 은 p.29 의 5분, 기존 iG5A·S100 은 10분) | D145~D147·D157 · [`../memo/2026-09-25-hv600-onboarding-demo.md`](../memo/2026-09-25-hv600-onboarding-demo.md) §2~§3 |
| **③ 완성도** | 실데이터(HV600 249행) 전량 정규화 · 8코드 승격 · 안전 문구 1건 승인 · 승격 전/후 데모 녹화. 회귀 스위트 spikes 41종 1,387건 · pytest 406건 등(§7) | [`sprint-19.md`](../sprints/sprint-19.md) 실행 기록 · `CLAUDE.md` 회귀 기준선 |
| **④ 커스터마이징·독창성** | OpenShell 공식 지원 에이전트가 아닌 자체 백엔드를 BYOC 로 넣고 Postgres 까지 샌드박스 안에 넣었다(외부 허용 0건) · 온보딩 전용 DB 역할과 도구 프로필 · 서버가 판정하는 주입 가드 · 안전 문구 fail-closed 게이트 · OpenClaw 워크스페이스를 정본 코드와 DB 승인 상태에서 생성(`--check` 드리프트 검사) | [`day1.md`](day1.md) §5 · D154·D157 · `deploy/nemoclaw/workspace/build.py` |

---

## 3. 보안 설계 — 에이전트를 어디까지 믿지 않는가

전제: 에이전트(LLM)는 틀릴 수 있고, 업로드된 매뉴얼은 믿을 수 없는 입력이다. 그래서 막는 일을 에이전트의
판단이 아니라 **샌드박스 정책·DB 권한·서버 코드**에 맡겼다. 아래는 전부 실측 기록이 있는 항목이다.

| # | 장치 | 실측 결과 | 근거 |
|---|---|---|---|
| 3.1 | **샌드박스 안에 키 없음** | `NVIDIA_API_KEY in env: False` 인데 `inference.local` 로 Nemotron 도구 호출 성공. 키는 게이트웨이에만 있다. 샌드박스 안에 키가 보이면 기동을 거부한다. 최종 이미지 파일 17,833개 전수 스캔에서 `.env` 비밀값 0건 | D143 · [`day1.md`](day1.md) §1 |
| 3.2 | **egress 허용 목록** | 웹 콘솔 샌드박스는 외부 허용 **0건**(`network_policies: {}`). `api.openai.com`·`integrate.api.nvidia.com`(직접)·`ollama.com`·`example.com` 전부 403 + OCSF 로그에 실행 파일·목적지. NVIDIA 로 가는 길은 게이트웨이 하나뿐 | `deploy/openshell/policy.yaml` · [`day1.md`](day1.md) §5.1·§5.3 |
| 3.3 | **binary·method·path 단위 허용** | OpenClaw 샌드박스는 `host.openshell.internal:8765` 의 `/mcp` 만, 실행 파일 `/usr/local/bin/node` 만 허용. 같은 주소를 `curl` 로 부르면 `binary not allowed in policy` 로 거부. NAT 샌드박스는 온보딩 프로필(8766)만 열고 진단·발주 도구(8765)는 열지 않는다 | `deploy/nemoclaw/presets/maintq-mcp.yaml` · `deploy/openshell/policy-nat.yaml` · D151 |
| 3.4 | **파일시스템(Landlock)** | `/app` 쓰기 → `PermissionError 13`. 쓰기는 `/tmp` 뿐, uid 1000 | [`day1.md`](day1.md) §1·§5.1 |
| 3.5 | **D10 쓰기 가드** | AI 도구는 발주·처분·수리에 **draft INSERT 만**. 샌드박스 안에서도 `UPDATE po_drafts` 는 트리거가, 읽기 전용 커넥션의 INSERT 는 DB 가 거부. 온보딩 쓰기 도구는 전용 역할 `maintq_onboarding` 으로 스테이징 4테이블 INSERT 만 GRANT(나머지는 기본 거부). 승격·상태 전이는 사람 전용 API | D10·D154 · [`day1.md`](day1.md) §1 · `spikes/onboarding_contract.py` |
| 3.6 | **주입 판정은 서버가 한다** | 매뉴얼 행의 주입 의심은 도구 서버가 결정적으로 판정하고, 에이전트가 `confidence=high` 를 보내도 서버가 `low`+플래그로 덮는다. NAT 쪽 가드 함수가 페이지 밖 행·중복 저장·행당 반복을 거부한다. 합성 주입 픽스처 회귀 5/5 | D154 · `mcp_server/onboarding_guard.py` · `onboarding/nat/maintq_nat/guarded_stage.py` · `onboarding/nat/run_injection_check.py` · [`day2.md`](day2.md) §10 ⑦ |
| 3.7 | **안전 문구 fail-closed** | 새 기종 안전 문구는 사람이 원문 페이지와 대조해 승인한 DB 행에서만 온다. 승인 전에는 안전 블록도 절차 문장도 내지 않고, 원문에 없는 숫자는 API 가 거부(`number_not_in_source`), 같은 종류 승인 행이 2건이면 차단(웹 콘솔 경로) | D147·D157 · `backend/agent/safety_source.py` · `spikes/onboarding_safety_gate.py`(22건) |
| 3.8 | **SkillSpector 게이트** | NVIDIA 카탈로그 2종을 설치 전 스캔하고 발견 사항을 사람이 읽고 수용. 우리 스킬: `run-eval` 15→0(셸로 `.env` 를 읽던 줄 제거) · `stage` 10→0(버전 미고정 `npx` 제거) · `done` 21 수용 · `maintq-diagnose` **0점·커버리지 100%** · `maintq-manual-onboarding` HIGH 1(evals 의 합성 주입 문장 — 판정 대기, H6) | [`day2.md`](day2.md) §8 · [`sprint-19.md`](../sprints/sprint-19.md) Stage 3 |
| 3.9 | **A2A 사전 차단** | 샌드박스 모드에서는 외부 파트너 호출을 시도하기 **전에** `policy_blocked` 로 분류하고 차단기 회계에서 뺀다(원래는 프록시 403 을 상대 응답으로 오인했다). 데모 녹화에서는 제외 | D149 · [`day2-prep.md`](day2-prep.md) §6 · [`day2.md`](day2.md) §10 ⑥ |
| 3.10 | **요청자 신원은 서버가 읽는다** | MCP-HTTP 쓰기의 요청자는 LLM 이 채우는 파라미터가 아니라 `X-User` 헤더에서 서버가 읽는다. 없거나 모르는 사용자면 초안을 만들지 않는다 | D152 · `mcp_server/identity.py` |

---

## 4. 데모 영상

**영상 링크**: (링크: 사람이 기입)

녹화 2026-09-25. 장면 설명과 녹화 시점 DB 실측은 [`../memo/2026-09-25-hv600-onboarding-demo.md`](../memo/2026-09-25-hv600-onboarding-demo.md).

| 장면 | 화면 | 보여 주는 것 |
|---|---|---|
| ① 승격 전 | OpenClaw 웹 대화창(샌드박스 `maintq-agent`) | "HV600에서 GF 떴어" → 매뉴얼에서 확인되지 않는 코드라 원인·조치를 추정하지 않고 표시부 재확인·제조사 A/S 로 안내. 유사 코드 추측 0 |
| ② NAT 정규화 | (녹화 대신 설명) | HV600 249행을 샌드박스 `maintq-nat` 안에서 Nemotron 이 한국어로 정규화. 전량 2,588초라 결과만 보인다 |
| ③ 사람 검수·승격 | MaintQ 웹 `/manager/onboarding`(팀장) | 「AI 초안 — 사람 승인 전」 라벨 · 원문 전체 보기(영문 ↔ 한국어, 인용은 원문 쪽에만) · GF 그룹 **승격**(되돌릴 수 없는 동작) |
| ④ 승격 후 | OpenClaw 웹 대화창(**새 세션**) | 같은 질문 → GF 정의·원인·권장 조치·최근 이력 + **사람이 승인한 HV600 안전 문구**(최소 5분, 근거 p.29) |

녹화하지 않은 것: 안전 문구 승인 장면과 헤더 뱃지 전환(온보딩 중 → 진단 가능)은 녹화 전에 지나갔다. 발표에서 말로 보충한다.
A2A 차단 장면(⑥)은 사용자 결정으로 데모에서 뺐다.

녹화 시점 상태(메모 §2): 원문 249행 · 정규화 261(재정규화 12 포함, 최신 기준 high 248 · low 1) · 승격 8코드
(CE·GF·OC·OV·UV1·OH·CPF06·EF1) · 반려 1행(추출 섞임) · `error_codes` HV600 8 · 승격 RAG 청크 33 · 안전 문구 승인 1건.

---

## 5. 재현 가이드

세부 명령은 링크한 문서가 정본이다. 여기서는 **순서와 함정**만 적는다.

### 5.0 사전 요건

- **WSL2 Ubuntu** — 실측 환경: RAM 15Gi · vCPU 8 · Node v22.23.1 · docker 29.3.1 · openshell 0.0.116 ([`day2-prep.md`](day2-prep.md) §11).
  NemoClaw 공식 최소 사양은 RAM 8GB · 4 vCPU · 디스크 20GB · Node 22.19+
- Docker, [uv](https://docs.astral.sh/uv/)(Python 3.13 — `.python-version`), Node.js
- **build.nvidia.com API 키** — 호스트 `.env`(임베딩·L1 실행용)와 OpenShell 게이트웨이 provider 에만 넣는다. 샌드박스에는 넣지 않는다
- **매뉴얼 PDF** — 매뉴얼 본문·추출물은 레포에 없다(D144, 형태 견본만 `data/extracted/samples/`). 공식 PDF 를 받아 `data/raw/` 에 두면
  `data/raw/manifest.json` 의 sha256 으로 판본을 대조한다(다르면 멈춘다, D19). HV600 PDF 출처는 [`day2-prep.md`](day2-prep.md) §7

### 5.1 순서

| # | 단계 | 명령·정본 문서 |
|---|---|---|
| 1 | Postgres 기동 · 환경 | `docker compose up -d postgres` (포트 5434 — 컨테이너 이름 `maintq_postgres` 고정. 같은 이름 컨테이너가 이미 다른 compose 프로젝트로 떠 있으면 그 프로젝트명으로 `-p <이름>` 을 붙여야 같은 볼륨을 이어 쓴다) · `cp .env.example .env` 후 `DATABASE_URL`·`MAINTQ_LLM_PROVIDER=nvidia`·`MAINTQ_LLM_MODEL=nvidia/nemotron-3-super-120b-a12b`·`NVIDIA_API_KEY` · `uv sync` |
| 2 | 매뉴얼 추출 | [`data/extracted/samples/README.md`](../../data/extracted/samples/README.md) 「실데이터를 만드는 법」 + HV600 후보 `uv run python data/extract_hv600_codes.py` · `uv run python data/extract_hv600_safety.py` |
| 3 | 시드 | `DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env \| cut -d= -f2-)" uv run python data/seed.py --with-error-codes` → `SELECT count(*) FROM error_codes` 가 **70** 인지 확인. `--today` 금지 |
| 4 | **D158 마이그레이션** | `DATABASE_URL=… uv run python scripts/migrate_d158_sites.py` (`--dry-run` 가능, 멱등 — 두 번째 실행은 0행). **D158 이전에 시드한 DB 는 회귀를 돌리기 전에** 반드시 실행 — 안 하면 격리 스키마 스파이크·pytest 가 `UndefinedTable` 로 죽는다(`docs/07_BACKLOG.md`). 새로 시드한 DB 에는 D158 테이블이 시드에 포함된다(seed ㊸) |
| 5 | 온보딩 적재 | `DATABASE_URL=… uv run python -m mcp_server.onboarding_load --codes data/extracted/hv600_code_candidates.json --safety data/extracted/hv600_safety_candidates.json` (멱등 — 두 번째는 종료코드 3) |
| 6 | NAT 한국어 정규화 | [`onboarding/nat/README.md`](../../onboarding/nat/README.md) — MCP-HTTP #2(onboarding 프로필, 8766) 기동 → 샌드박스 `maintq-nat` 생성(L0) → `run_normalize.py`. 데모 코드만: `--codes GF,OC,OV,UV1,OH,CPF06,EF1,CE`. 스파이크 재현은 `onboarding/nat/spike/README.md` |
| 7 | 백엔드·프론트 | [`../memo/2026-09-25-hv600-onboarding-demo.md`](../memo/2026-09-25-hv600-onboarding-demo.md) §4 (백엔드 127.0.0.1:8010 · 프론트 3000) |
| 8 | 검수·승격·안전 승인 | `http://localhost:3000` → 정비팀장 → 「기종 온보딩 검수 →」(`/manager/onboarding`). 승격·반려·안전 승인은 **되돌릴 수 없다**(승격 취소 API 없음, H10) |
| 9 | OpenClaw 진단 | MCP-HTTP #1(core, `MAINTQ_MCP_TOKEN=… uv run python -m mcp_server.http_entry`, 127.0.0.1:8765) → 프리셋 `deploy/nemoclaw/presets/maintq-mcp.yaml` · `openclaw mcp add … --header 'Authorization=Bearer …'` + `X-User` 헤더(D151·D152) → `deploy/nemoclaw/workspace/build.py`(생성) · `--check`(드리프트) → 업로드 · `skills/maintq-diagnose` 설치 → `nemoclaw maintq-agent agent --session-id <새 ID> -m "HV600에서 GF 떴어"` |
| (선택) | 웹 콘솔 샌드박스 | [`day1.md`](day1.md) §6 — 이미지 빌드 · DB 덤프 · `openshell sandbox create`. HV600 을 보이려면 덤프·재빌드가 필요(H8) |

### 5.2 순서 함정

- ⛔ **시드는 온보딩을 지운다(H9)** — `data/seed.py` 는 `DROP SCHEMA public CASCADE` 다. 5단계 적재는 다시 돌릴 수 있지만
  **NAT 정규화(전량 약 43분)·승격·안전 승인은 복구되지 않는다.** 3단계는 한 번만, 온보딩 전에
- `seed.py` 에도 `DATABASE_URL` 을 실어야 한다(안 실으면 다른 경로로 새다 죽는다). pytest 도 같다(`CLAUDE.md` 회귀 스위트)
- **NemoClaw 설치가 기존 OpenShell 게이트웨이를 빼앗고 실행 중 샌드박스를 종료한다** — 키 재입력 없는 복구 절차는 [`day2.md`](day2.md) §5
- 안전 문구를 승인하면 `build.py --check` 가 stale 을 낸다 — 워크스페이스를 재생성·재업로드해야 OpenClaw 에 반영된다
- OpenClaw 는 **새 세션**으로 물어야 승격 전/후 차이가 보인다(같은 세션 재사용 시 이전 답을 재활용한 기록이 있다 — 스킬에 「매번 lookup 재호출」을 넣었다)
- `openshell sandbox exec` 는 이미지 `ENV` 를 넘기지 않는다 → `--env` 명시, 이름은 `-n` ([`day1.md`](day1.md) §6 · `onboarding/nat/README.md`)
- 스파이크용 MCP 서버를 끌 때 `pkill -f` 금지 — 운영 서버와 모듈 이름이 같다. PID 로만 끈다([`day2.md`](day2.md) §9)
- NVIDIA 무료 티어 과부하(`Service temporarily overloaded`)가 간헐적으로 난다 — 재시도로 통과. 라이브보다 녹화를 권장

---

## 6. 한계·미완

| 항목 | 내용 | 근거 |
|---|---|---|
| HV600 절차 근거 | 승격된 HV600 RAG 청크는 **고장 표**뿐이다. 부품 교체 같은 절차를 물으면 근거가 없어 「근거 확인 못 함 → 제조사 문의」로 답한다 — 결함이 아니라 의도된 동작 | [`sprint-19.md`](../sprints/sprint-19.md) Stage 5 발견 ② · 후속 |
| 평가 수치 | README 의 평가 기준선은 이전 모델(`gpt-oss:120b`) 기준이다. Nemotron 으로는 성능을 측정하지 않았고, 이후 시스템 프롬프트가 바뀌어 **이전 결과·LLM 카세트와 비교할 수 없다** — 재평가 필요 | D88 · [`day1.md`](day1.md) 머리말 · 커밋 `e9005f0`·`4614b79`·`1cf93e8` 본문 |
| OpenClaw 안전 게이트 | 웹 콘솔은 `loop.py` 가 안전 블록을 시스템으로 붙이고 막지만, **OpenClaw 경로에는 그 계층이 없다** — HV600 안전 문구는 모델이 워크스페이스·스킬 규칙을 지키는지에 달려 있다 | `docs/07_BACKLOG.md` 「Sprint 19 온보딩의 알려진 한계」 · [`day2.md`](day2.md) §10 ⑤ |
| 웹 콘솔 샌드박스 | 샌드박스 `maintq` 는 빌드 시점 DB 스냅샷이라 **HV600 승격분이 없다**. 반영하려면 덤프 → 재빌드 → 재생성(H8). 그 덤프는 온보딩 역할·GRANT 를 옮기지 않는다 | `TODO_직접할일.md` H8 · `docs/07_BACKLOG.md` |
| 승격 취소 | 승격을 되돌리는 API 가 없다. 잘못 승격하면 DB 를 사람이 직접 되돌린다 | H10 · `docs/07_BACKLOG.md` |
| 샌드박스 안 dense 검색 | 게이트웨이는 모델 1개만 라우팅해 임베딩을 같이 쓸 수 없다 → 샌드박스 안 검색은 키워드 전용 | [`day1.md`](day1.md) §5.2 |
| MCP 토큰·신원 | OpenClaw 등록 토큰과 `X-User` 헤더가 샌드박스 안 설정 파일에 평문으로 있다. 파일 쓰기 도구를 가진 에이전트가 신원을 바꿔 쓸 수 있다 — 토큰↔사용자 바인딩은 후속 | D151·D152 한계 |
| NAT 와 SKILL.md | NAT 1.9 는 SKILL.md 를 런타임에 읽지 않는다 → `build_prompt.py` 가 SKILL.md 본문으로 시스템 프롬프트를 생성해 대체(`--check` 드리프트 검사) | D153 · [`day2.md`](day2.md) §9 ⓘⓘⓘ |
| 모델 출력 품질 | Nemotron 응답에 다른 언어 토큰(중국어 「参照」, 노르웨이어 등)이 섞인 기록이 있다. 웹 콘솔은 한국어 전용 규칙을 추가했지만 모델 준수는 실호출로만 확인된다 | [`day1.md`](day1.md) §4 O3 · `docs/07_BACKLOG.md` |
| 수량 확인 | OpenClaw 가 부품 수량을 묻지 않고 1개로 가정해 견적을 낸 실행이 있었다 | [`day2.md`](day2.md) §8 |
| OpenClaw 구성 절차 | NemoClaw 설치·샌드박스 생성·프리셋 적용의 전체 명령은 레포 문서에 한 곳으로 정리돼 있지 않다(흩어진 기록: [`day2.md`](day2.md) §3~§8, D151, `build.py` 머리 주석) | — |
| 플랫폼 | OpenShell 은 alpha, WSL2 지원은 experimental — 버전이 바뀌면 절차가 깨질 수 있다 | [`day1.md`](day1.md) §7 |

---

## 7. 완성도 지표

`CLAUDE.md` 회귀 기준선(2026-09-25 실측):

- spikes **41스위트 / 1,387건** — `law_fetch_contract ⓚ` 기존 오탐 1건(`.env` 값 문제, 코드 결함 아님) 외 FAIL 0
- pytest **406건**(23파일) · seed 자가검증 **44건** · 프론트 라우트 **27개**(`next build`) · 설계 결정 **D1~D158**
- 온보딩 전용 스파이크: `model_enum_contract` · `onboarding_contract` · `onboarding_rag_contract` · `onboarding_safety_gate` ·
  `onboarding_promote_contract` · `mcp_http_contract` · `site_floorplan_contract`
- 회귀 실행 커맨드와 함정(`DATABASE_URL` 필수 등)은 `CLAUDE.md` 「회귀 스위트」 절
