# 13. 배포 설계 (Deployment)

> **상태: 초안 — 미결정 3건이 열려 있다 (§6).** 이 문서는 *"어디에 어떻게 올릴 것인가"*의
> 설계 근거를 모은다. 배포 실행 스크립트·IaC 는 아직 없다 (백로그 **P14**).
>
> **이 문서가 다루지 않는 것**: 인증·계정(백로그 **P21**) · 감사 로그 불변성(**P5**) ·
> 오토스케일. 셋 다 배포와 맞물리지만 각자 별도 항목이다.

---

## 1. 무엇을 올리는가 — 런타임 3조각

| 조각 | 실체 | 상태 | 비고 |
|---|---|---|---|
| 프론트 | Next.js App Router, 라우트 **18개** | 정적 빌드 + 클라이언트 fetch | `NEXT_PUBLIC_API_BASE` 로 백엔드 **직접 호출** (`frontend/lib/api.ts:15`) |
| 백엔드 | FastAPI + uvicorn (기본 `:8003`) | 상태 있음 (SQLite 쓰기) | CORS 는 `MAINTQ_CORS_ORIGINS` |
| MCP 서버 | `mcp_server/` **별도 프로세스** (D15) | 백엔드가 **자식 프로세스로 spawn** | stdio 트랜스포트 (`MAINTQ_MCP_AUTOSTART=1`) |

데이터 실체는 셋뿐이고 **전부 작다**:

| 데이터 | 경로 | 크기 | 성격 |
|---|---|---|---|
| 목업 DB | `data/maintq.db` | **311 KB** | **읽기+쓰기** — 발주·처분·수리 상태 전이가 여기 쌓인다 |
| 매뉴얼 검색 인덱스 | `data/extracted/manual_chunks.jsonl` | **1.2 MB** | **읽기 전용** — 이미지에 그대로 포함 |
| 파생 산출물·룰·법령 | `data/extracted/*.json` · `data/rules/` | 수백 KB | **읽기 전용**, git 추적 (D60) |

⛔ **`data/raw/` 의 매뉴얼 PDF 는 런타임에 필요 없다.** 청킹·추출은 빌드타임(M1)에 끝났고
백엔드가 참조하는 것은 `data/raw/manifest.json`(오프셋 원천, D19) 하나뿐이다 —
`backend/manifest.py:4`. **PDF 를 이미지에 넣지 말 것** (저작권 + 용량).

---

## 2. 🔴 벡터 DB 는 존재하지 않는다 — 프로비저닝 대상이 아니다

배포 논의에서 가장 흔히 잘못 잡히는 항목이라 먼저 못 박는다.

`mcp_server/rag.py` 는 **키워드 + IDF 스코어러**다. 하이브리드 **인터페이스만** 고정돼 있고
(`search(model, query, top_k, dense=None)`, **D47**), dense scorer 는 **주입 지점이 비어 있다**.
임베딩 모델·벡터스토어·융합 가중치는 **D51 이 "실측 보고 정한다"로 미뤄 둔 미결정**이다.

실측 확인:

- `backend/` 전체에 `dense`·`scorer` 문자열 **0건** — `backend/rag/` 디렉터리 자체가 없다 (D48)
- `mcp_server/rag.py` 는 어떤 임베딩 모델도 import 하지 않는다 (모듈 docstring 이 명시)
- 인덱스 = `manual_chunks.jsonl` **1.2 MB 텍스트 파일**, 프로세스 안에서 읽기 전용 로드

**결론**: 벡터 DB 서비스도, 그 인덱스를 담을 볼륨도 **필요 없다.** 다른 벡터 DB 로
바꿀지 비교할 대상 자체가 없다. D51 이 풀리면 그때 이 절을 다시 연다.

---

## 3. 🔴 SQLite 를 Postgres(Neon 등)로 옮기면 **절대규칙 1 이 깨진다**

Neon 은 서버리스 **Postgres** 다 — SQLite 파일을 올려두는 곳이 아니다. 옮긴다면 그것은
호스팅 변경이 아니라 **DB 엔진 마이그레이션**이고, 이 저장소에서는 단순 방언 변환이 아니다.

`mcp_server/db.py` 는 **TEMP TRIGGER 로 MCP 도구의 UPDATE/DELETE 를 물리적으로 차단**하고,
커넥션을 `draft_writer()` / `decision_writer()` / `repair_writer()` 로 갈라 둔다 (**D99**).
이것이 CLAUDE.md **절대규칙 1**(*"MCP 도구는 draft INSERT 만 가능"*)을 프롬프트가 아니라
**DB 권한 구조로** 강제하는 장치다. 실제로 걸려 있는 자리:

```
mcp_server/db.py
mcp_server/tools/create_repair_record.py
mcp_server/tools/generate_disposal_document.py
backend/services/decisions.py
```

회귀 `spikes/write_tool_contract.py`(30건)가 이 성질을 검증한다. **Postgres 에는 TEMP TRIGGER
시맨틱이 없으므로 이 안전장치를 처음부터 다시 설계**해야 한다 — 배포하려다 프로젝트의
핵심 설계 주장(*"AI 는 근거를 조립하고 사람이 서명한다"*)을 떠받치는 구조를 흔드는 셈이다.

**DB 는 311 KB 다. 옮길 이유가 없다.** (굳이 "클라우드 SQLite"를 원한다면 Turso/libSQL 이나
Litestream 이지만, 다중 커넥션 + TEMP TRIGGER 구조와 궁합이 나쁘고 얻는 것이 없다.)

---

## 4. 진짜 제약은 플랫폼이 아니라 **인스턴스 1개**

이 앱은 **단일 인스턴스 전제**로 짜여 있다. 세 요소가 동시에 그것을 요구한다.

| 요소 | 왜 |
|---|---|
| **SQLite 쓰기** | 발주·처분·수리 상태 전이가 로컬 파일에 쌓인다. 인스턴스 2개면 **승인 큐가 요청마다 다르게 보인다** |
| **MCP stdio** | 백엔드가 자식 프로세스로 spawn — 백엔드와 **같은 컨테이너**에 있어야 한다 |
| **RAG 인덱스** | 프로세스 메모리 로드 (동작 문제는 아니나 인스턴스마다 중복) |

### 4-1. WAL 저널 — 네트워크 파일시스템에 DB 를 두면 안 된다

두 커넥션 모듈이 **모두 WAL 을 켠다** (`backend/db.py:36`, `mcp_server/db.py:41`).
그리고 `backend/db.py:37` 의 주석이 이미 그 위험을 적어 두었다 — *"네트워크 FS 등에서 실패 가능"*.
WAL 은 공유 메모리(`-shm`)와 파일 락에 의존해 **NFS·FUSE 계열에서 깨진다.** 코드는 실패해도
죽지 않고 기본 저널로 폴백하지만, 그건 *"조용히 느려지고 락 시맨틱이 달라진다"*는 뜻이지
안전하다는 뜻이 아니다.

| 저장 위치 | 판정 |
|---|---|
| 컨테이너에 직접 마운트한 **블록 볼륨** (Northflank 등) | ✅ 로컬 블록 디바이스 — WAL 정상 |
| 컨테이너 내부 디스크 + 부팅 시 재시드 | ✅ 동작 — 단 **재시작 시 데이터 휘발** |
| Cloud Run + **GCS FUSE** | ⛔ **금지** — 파일 락 없음, WAL 깨짐 |
| Cloud Run + Filestore(NFS) | ⚠ 비권장 + 비쌈 |

→ **Cloud Run 에서 SQLite 를 안전하게 영속시킬 방법이 없다.** GCP 로 간다면 그것은 선택이
아니라 *"DB 휘발을 받아들인다"*는 **강제 조건**이다 (§6 미결정 ①).

---

## 5. 권고 구성

| 층 | 권고 | 근거 |
|---|---|---|
| 프론트 | **Vercel 또는 Netlify — 기술적으로 거의 동등** | 프론트는 `API_BASE` 로 백엔드를 직접 호출하고 SSE 를 Next 라우트로 프록시하지 않는다 → 플랫폼별 스트리밍 버퍼링 함정을 애초에 피해 있다. Vercel 이 App Router 무설정, Netlify 는 어댑터 필요. **배우고 싶은 쪽으로 고르면 된다** |
| 백엔드+AI+MCP | **1 컨테이너 · replica 고정 1 · 블록 볼륨에 `maintq.db`** (Northflank 적합) | §4 |
| 벡터 DB | **없음 — 항목 삭제** | §2 |
| RDB | **SQLite 유지** | §3 |
| MCP | **stdio 유지** | D15 프로세스 분리는 stdio 로도 성립 |

> ⚠ **SSE 를 Next.js 라우트로 프록시하지 말 것.** 지금 구조(브라우저 → 백엔드 직접)를
> 유지하면 플랫폼 선택이 자유롭다. 프록시를 넣는 순간 서버리스 응답 버퍼링이
> `token`/`tool_call`/`tool_result`/`block` 스트림(D14·D22)을 뭉개기 시작한다.

### 5-1. 백로그 **P14 문구 정정 필요**

P14 는 *"docker-compose (backend + mcp-server **2서비스**)"* 로 적혀 있으나, **stdio 는
부모-자식 프로세스라 컨테이너 2개로 쪼갤 수 없다.** 둘 중 하나를 골라야 한다:

- ⓐ **P14 를 "1컨테이너 안 2프로세스"로 정정** — D15 프로세스 분리는 그대로 성립. 권장
- ⓑ **MCP 트랜스포트를 HTTP/SSE 로 전환** — 컨테이너 경계 = 프로세스 경계라는 어필은
  살아나지만 **새 D-결정 사안**이고 `backend/agent/mcp_client.py` 재작성이 따른다

---

## 6. 미결정 — 사람이 정해야 한다

| # | 결정할 것 | 선택지 | 걸린 것 |
|---|---|---|---|
| ① | **DB 영속 vs 휘발** | ⓐ 블록 볼륨 영속 ⓑ 부팅 시 `seed.py --with-error-codes` 재시드 | 데모 중 승인한 발주가 재시작 후 남아야 하는가. ⓑ 를 고르면 **플랫폼 자유도가 커지지만** 데모 시연 도중 재시작이 곧 초기화다 |
| ② | **인증** | ⓐ Basic Auth/IP 제한 ⓑ 공개 수용 ⓒ P21 착수 | 지금은 `X-Role`/`X-User` **헤더 시뮬레이션**(P21 미구현)이라 **공개 배포 시 누구나 발주를 승인할 수 있다** |
| ③ | **LLM 비용 방어** | ⓐ 레이트리밋 ⓑ 공개 데모 시간 제한 ⓒ 키 회전 | 기본 provider 가 `gemini`. `MAINTQ_LLM_CACHE`(D104 카세트)는 **평가용이지 런타임 방어가 아니다** |

⚠ ①을 정하기 전에는 플랫폼을 확정하지 말 것 — ①이 ⓑ면 GCP Cloud Run 도 열리고, ⓐ면
사실상 Northflank 계열(블록 볼륨)로 좁혀진다.

---

## 7. 환경변수 (배포 시 주입)

| 변수 | 필수 | 비고 |
|---|---|---|
| `MAINTQ_LLM_PROVIDER` | ✅ | `gemini` \| `anthropic` |
| `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | ✅ (택1) | provider 에 맞춰 |
| `MAINTQ_LLM_MODEL` | — | 미지정 시 기본 |
| `MAINTQ_DB` | ✅ | **볼륨 경로로 지정** (①ⓐ 인 경우) |
| `MAINTQ_CHUNKS` | — | 기본값이 이미지 내 경로라 보통 불필요 |
| `MAINTQ_CORS_ORIGINS` | ✅ | **프론트 배포 도메인**을 반드시 등재 |
| `MAINTQ_MCP_AUTOSTART` | ✅ | `1` 유지 (stdio spawn) |
| `MAINTQ_TOOLS_PROFILE` | — | **기본 `core`**. 확장 11종을 켜려면 `full` (D69·D88 — **평가는 `core` 에서만 인정**) |
| `NEXT_PUBLIC_API_BASE` | ✅ | 프론트 빌드타임 주입 — **백엔드 공개 URL** |
| `LAW_API_OC` · `DATA_GO_KR_SERVICE_KEY` · `IROS_API_KEY_*` · `ELICE_*` | — | **런타임 미호출** (수집 스크립트 전용). 배포 컨테이너에 넣을 필요 없다 |

> 🔴 `data/rules/fetch_laws.py` 의 요청 파라미터에는 `LAW_API_OC` 가 실린다. 2026-08-13 에
> 평문 자격증명이 추적 파일로 흘러 `git filter-repo` 로 **커밋 10개**를 재작성한 사고가 있었다
> (D103). **수집 키를 런타임 컨테이너 환경에 올리지 않는 것**이 노출면을 줄이는 가장 싼 방법이다.

---

## 8. 배포 전 체크리스트

- [ ] §6 미결정 3건 확정
- [ ] 회귀 전수 통과 — spikes **31스위트** · seed **35건** · pytest **83건** (⚠ Windows 소켓 고갈 재시도 규칙은 CLAUDE.md 참조)
- [ ] `MAINTQ_TOOLS_PROFILE` 값 확정 (데모는 `full`, 평가는 `core` — D88)
- [ ] `MAINTQ_CORS_ORIGINS` 에 프론트 도메인 등재 확인
- [ ] 이미지에 `data/raw/*.pdf` 가 **포함되지 않았는지** 확인 (저작권·용량)
- [ ] `manifest.json` 은 포함됐는지 확인 (없으면 인용 페이지 환산이 깨진다 — D19·D32)
- [ ] 인스턴스 수 **1 고정** (max/min 모두)
- [ ] SSE 가 배포 환경에서 끊기지 않는지 실측 (프록시·타임아웃)

---

## 9. 관련 결정·백로그

| 참조 | 내용 |
|---|---|
| **D15** | 백엔드 ↔ MCP 프로세스 분리 (stdio) |
| **D27** | 환경 관리 uv+venv, Docker 는 MVP 제외 → P14 |
| **D47·D48·D51** | RAG 하이브리드 인터페이스 · 구현 위치 · **임베딩 미결정** |
| **D60** | 원본은 파일(git)이 정본, DB 는 조회용 사본 |
| **D99** | 쓰기 커넥션 분리 + TEMP TRIGGER |
| **D103** | 외부 응답 원본 보관 · 자격증명 미저장 |
| **P14** | docker-compose (§5-1 문구 정정 필요) |
| **P21** | 인증·계정 (§6 ②) |
