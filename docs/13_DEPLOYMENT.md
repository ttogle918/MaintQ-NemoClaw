# 13. 배포 설계 (Deployment)

> **상태: DB·벡터 인프라는 결정 완료(D116·D117) — 배포 플랫폼도 확정(GCP Cloud Run + Supabase).**
> 미결정은 §6의 2건(인증·LLM 비용 방어)뿐이다. 배포 실행 스크립트·IaC 는 아직 없다 (백로그 **P14**).
> 이 문서는 2026-08-24 전면 개정됐다 — 이전 버전은 "SQLite 유지·벡터 DB 없음"을 전제로 했는데
> Sprint 16(D116)·D117이 그 전제를 둘 다 뒤집었다. 옛 버전을 인용하지 말 것.
>
> **이 문서가 다루지 않는 것**: 인증·계정(백로그 **P21**) · 감사 로그 불변성(**P5**) ·
> 오토스케일 세부 튜닝. 셋 다 배포와 맞물리지만 각자 별도 항목이다.

---

## 1. 무엇을 올리는가 — 런타임 3조각

| 조각 | 실체 | 상태 | 비고 |
|---|---|---|---|
| 프론트 | Next.js App Router, 라우트 **22개**(`npx next build` 기준 — `find frontend/app -name page.tsx`로 세면 21로 하나 적다, 자동 생성되는 `/_not-found` 차이) | 정적 빌드 + 클라이언트 fetch | `NEXT_PUBLIC_API_BASE` 로 백엔드 **직접 호출** (`frontend/lib/api.ts:15`) |
| 백엔드 | FastAPI + uvicorn (기본 `:8000`, 로컬 개발은 `:8003`) | **상태 없음(stateless)** — 쓰기는 전부 컨테이너 밖 Postgres로 나간다 | CORS 는 `MAINTQ_CORS_ORIGINS` |
| MCP 서버 | `mcp_server/` **별도 프로세스** (D15) | 백엔드가 **자식 프로세스로 spawn**, 백엔드와 **같은 컨테이너** 안에서만 | stdio 트랜스포트 (`MAINTQ_MCP_AUTOSTART=1`) |

데이터 실체:

| 데이터 | 경로/위치 | 성격 |
|---|---|---|
| RDB | **Supabase(관리형 Postgres) — 컨테이너 밖** | **읽기+쓰기** — 발주·처분·수리 상태 전이·자산·에러코드 등 24개+ 테이블 (§3) |
| 매뉴얼 검색 인덱스(키워드) | `data/extracted/manual_chunks.jsonl` | **읽기 전용**, 이미지에 COPY로 포함 — RAG 키워드 스코어러가 로컬 파일로 읽는다 |
| 매뉴얼 검색 인덱스(dense) | Postgres `manual_chunks.embedding`(pgvector) | **읽기 전용**(런타임 기준) — dense 스코어러가 질의마다 조회한다 (§2) |
| 파생 산출물·룰·법령 | `data/extracted/*.json` · `data/rules/` | 수백 KB, **읽기 전용**, git 추적 (D60), 이미지에 COPY |

⛔ **`data/raw/` 의 매뉴얼 PDF 는 런타임에 필요 없다.** 청킹·추출은 빌드타임(M1)에 끝났고
백엔드가 참조하는 것은 `data/raw/manifest.json`(오프셋 원천, D19) 하나뿐이다 —
`backend/manifest.py:4`. **PDF 를 이미지에 넣지 말 것** (저작권 + 용량, `.dockerignore` 가 이미
`data/raw`·`data/cache`·`*.db` 를 제외한다).

---

## 2. RAG 하이브리드 검색 — 키워드는 로컬 파일, dense는 Postgres pgvector (D117)

이전 버전이 "벡터 DB는 존재하지 않는다"고 못박았던 절이다 — **더 이상 사실이 아니다.**
D117(2026-08-24)이 D51을 해소하며 dense 스코어러를 켰다.

- `mcp_server/rag.py`의 하이브리드 인터페이스(`search(model, query, top_k, dense=None)`, D47)는
  그대로다 — `rag.py` 자신은 여전히 어떤 임베딩도 import하지 않는다(원 설계 유지).
- `mcp_server/tools/rag_search_manual.py`가 `mcp_server/dense_scorer.py`를 주입 지점에 꽂았다
  (`dense=dense_scorer.score`).
- **코퍼스(passage) 임베딩**은 Postgres `manual_chunks` 테이블(pgvector, `scripts/postgres_schema.sql`
  §24)에 저장돼 있다 — `nvidia/nemotron-3-embed-1b`, 2,048차원. 채우는 건 사람이 명시 실행하는
  `scripts/migrate_vectors.py`(컨테이너가 자동으로 하지 않는다, §5 배포 순서 참고).
- **질의(query) 임베딩**은 검색마다 NVIDIA API를 호출하고, `data/external/nvidia_embed.py`가
  텍스트 해시로 로컬 캐시(`data/cache/embeddings/`, git 미추적)해 재과금을 막는다 — 이 캐시는
  인스턴스별 로컬이라 다중 인스턴스에서 각자 따로 쌓인다(정합성 문제 아님, 재과금 방지 최적화일
  뿐이라 인스턴스마다 캐시가 비어 있어도 정상 동작한다).
- `NVIDIA_API_KEY`·`NVIDIA_EMBED_MODEL` 미설정이거나 호출 실패 시 **예외 없이 전부 0.0을
  반환**해 키워드 전용(D47의 `dense=None`과 동등)으로 조용히 물러난다 — 배포 시 이 두 변수를
  빠뜨려도 서비스가 죽지 않는다, 다만 검색 품질이 키워드만으로 낮아진다.

**결론**: 별도 벡터 DB 서비스(Qdrant·Pinecone 등)는 여전히 필요 없다 — Supabase의 Postgres에
pgvector 확장만 켜면 된다(Supabase는 기본 제공). 프로비저닝 대상은 "Postgres 하나"로 그대로다.

---

## 3. DB — SQLite→Postgres 마이그레이션 완료 (D116), Supabase로 관리형 호스팅

이전 버전은 "SQLite를 Postgres로 옮기면 절대규칙 1이 깨진다"며 마이그레이션 자체를 만류했다.
**Sprint 16(D116, 2026-08-23)이 그 마이그레이션을 실제로 완성했다** — 지금 `backend/db.py`·
`mcp_server/db.py`는 **Postgres 전용**이고 SQLite 코드 경로는 남아 있지 않다.

### D10(절대규칙 1)은 어떻게 다시 강제되는가

SQLite판은 커넥션마다 `CREATE TEMP TRIGGER`(세션 범위)로 막았다. Postgres에는 세션 트리거가
없어서 **영구 트리거 + 세션 GUC**로 재구현했다(`scripts/postgres_guards.sql`):

- `po_drafts`·`decisions`·`repair_records` 세 테이블에 `BEFORE UPDATE OR DELETE` 트리거가
  **영구히** 붙어 있다.
- 트리거 함수(`mcp_block_write()`)는 세션 GUC `maintq.mcp_write_guard`가 `'on'`일 때만
  거부한다.
- `mcp_server/db.py`의 `draft_writer()`/`decision_writer()`/`repair_writer()`만 이 GUC를
  켠다 — `backend/db.py`(사람 전용 REST 커넥션)는 절대 켜지 않으므로 기존 UPDATE 경로는
  그대로 동작한다.
- 가드가 꺼져 있을 때 `RETURN NULL`을 내면 모든 UPDATE/DELETE가 조용히 무효화되는 버그가
  초기 구현에 있었다(실측으로 잡음) — 지금은 `RETURN NEW`/`RETURN OLD`를 정확히 낸다.

회귀 `spikes/write_tool_contract.py`(30건)가 이 성질을 검증한다.

### 읽기 전용 강제도 물리적으로 바뀌었다

SQLite는 `mode=ro` URI로 물리적 읽기전용을 걸었다. Postgres는 DSN의
`options=-c default_transaction_read_only=on`으로 세션 자체를 읽기전용 트랜잭션으로 고정한다
(`backend/db.py`의 `read_only()`).

### Supabase 커넥션 풀링 — 배포 전 확정 필요 (§6 신규 미결정 후보)

Supabase는 **Session pooler**(포트 5432, 세션 고정)와 **Transaction pooler**(포트 6543)를
둘 다 제공한다. 위 D10 가드는 `SET`(세션 범위) GUC에 의존하므로:

- **Session pooler 또는 직접 연결**: 세션이 커넥션과 1:1로 고정돼 GUC가 요청 내내 유지된다 — 안전.
- **Transaction pooler**: 트랜잭션마다 물리 커넥션이 바뀔 수 있다. `mcp_server/db.py`가
  `SET LOCAL`(트랜잭션 범위)로 이미 방어해 뒀다고 확인은 됐지만(Sprint 16 4차 체크포인트),
  **실제 프로덕션 트래픽으로 검증된 적은 없다** — 커넥션 수 제한이 문제되기 전까지는
  Session pooler/직접 연결을 기본으로 쓸 것을 권한다.

`Dockerfile`(15~22번째 줄 주석)이 이미 이 권고를 담고 있다.

---

## 3-B. 인덱스 — **지금 추가하지 않는다** (실측 근거, 2026-09-04)

24테이블에 `CREATE INDEX` 가 2개뿐이고 **FK 컬럼 29개가 인덱스 없이** 있다. 리뷰에서
"성능 위험"으로 지목됐지만, **실측 결과 지금 추가하면 손해다.** 근거를 남긴다 —
같은 지적이 반복될 자리이기 때문이다.

### 실측 ① 데이터가 작다

| 테이블 | 행 수 | | 테이블 | 행 수 |
|---|---|---|---|---|
| `error_history` | 200 | | `error_codes` | 70 |
| `supplier_parts` | 80 | | `residual_curve` | 42 |
| `inventory` · `parts` | 40 | | `repair_records` | 12 |
| `assets` · `equipment` | 9 · 10 | | `po_drafts` · `decisions` | 8 · 4 |

### 실측 ② 플래너가 인덱스를 **거부한다**

`EXPLAIN (ANALYZE)` 로 핫 쿼리 5종을 재보면 전부 **0.03~0.8ms**이고, `error_history` 는
인덱스(`idx_history_eq_code`)가 **있는데도** Seq Scan 을 고른다 — 200행에서는 그게 실제로
더 싸기 때문이다.

| 쿼리 | 플랜 | 실행 시간 |
|---|---|---|
| `list_pos(state)` 승인 큐 | Sort + Seq Scan | **0.81 ms** |
| 자금집행 1일 누적(D121) | Aggregate | **0.05 ms** |
| `error_history` 반복 고장 | **Seq Scan**(인덱스 무시) | **0.04 ms** |
| `supplier_parts` 견적 | Seq Scan | **0.03 ms** |
| `repair_records` 설비별 | Seq Scan | **0.09 ms** |

### 실측 ③ 진짜 비용은 다른 데 있다

같은 세션에서 **커넥션 1개 여는 데 ~16ms** 가 든다(풀링 없음). `GET /api/po/{id}` 는
커넥션을 **2개** 열고, 상태 전이는 **3개** 연다.

> **쿼리 0.03~0.8ms vs 커넥션 16ms — 20~500배 차이다.**
> 인덱스를 29개 달아도 응답 시간은 측정 가능한 수준으로 바뀌지 않는다. 줄여야 할 것은
> 커넥션 수이지 스캔 비용이 아니다.

> ✅ **후속 조치 완료 (D127, 2026-09-04)** — 커넥션 풀을 도입했다.
> `list_pos` 23.1→**7.4ms**(3.1배) · `get_po` 31.0→**16.8ms**(1.8배).
> 위 "커넥션이 진짜 비용"이라는 진단이 그대로 확인된 셈이다.
> 남은 항목: `get_po()` 가 커넥션을 2개 여는 것(`a2a_history` 조회가 별도 커넥션)을
> 하나로 합치는 것 — 풀 도입으로 비용이 16ms→~1ms 로 줄어 **우선순위는 내려갔다**.

### 그래서 언제 다는가 — 임계값

인덱스는 **쓰기 비용과 유지보수 표면**을 늘린다. 근거 없이 미리 달지 않는다(D65·D74 가
잔가곡선에 대해 취한 태도와 같다 — 추정치를 사실처럼 굳히지 않는다). 아래 조건이
**실제로 관측되면** 그때 단다.

| 트리거 | 추가할 인덱스 | 근거 쿼리 |
|---|---|---|
| `error_history` > **10,000행** | `(equipment_id, code, occurred_at)` — **이미 있다.** 그때부터 실제로 쓰인다 | `get_error_history` 반복 고장 판정 |
| `po_drafts` > **5,000행** | `(state, created_at DESC)` | `list_pos(state)` 승인 큐 정렬 |
| `decisions`·`repair_records` > **5,000행** | 각 `(state)` | 승인 큐 3종(D85) |
| `traces` > **100,000행** | `(session_id, seq)` — **이미 있다** | `GET /api/chat/{id}/trace`(D43) |
| `repair_records` 설비별 조회가 느려지면 | `(equipment_id)` | 보전지표 산출(D101) |
| 자산 **삭제/이관**을 실제로 쓰기 시작하면 | FK 컬럼 `asset_id` 5종(`equipment`·`decisions`·`flags`·`incidents`·`ownership_checks`·`deadlines`) | Postgres 는 FK 컬럼을 자동 인덱싱하지 않는다 — 부모 행 DELETE 시 자식 전체를 스캔한다 |

**마지막 줄만 성격이 다르다.** 나머지는 조회 속도지만 이건 **삭제 시 잠금 시간**이라,
행 수가 아니라 *"그 기능을 쓰는가"* 가 트리거다. 현재 자산 삭제 경로는 없다.

### 재측정 방법

```bash
DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)"   uv run python -c "import os,psycopg; con=psycopg.connect(os.environ['DATABASE_URL']);   [print(r[0]) for r in con.execute('EXPLAIN (ANALYZE) <쿼리>').fetchall()]"
```

Seq Scan 의 `actual time` 이 **10ms 를 넘기 시작하면** 위 표의 임계값을 앞당겨 볼 것.

---

## 4. 인스턴스 제약 — Postgres 전환으로 대부분 해소됐다

이전 버전은 "SQLite 쓰기 + MCP stdio + RAG 인덱스" 세 가지가 겹쳐 **단일 인스턴스 강제**라고
결론 냈다. Postgres 전환 이후 재평가하면:

| 요소 | 이전(SQLite) | 지금(Postgres) |
|---|---|---|
| DB 쓰기 | 로컬 파일, 인스턴스 2개면 승인 큐가 요청마다 다르게 보임 | **Supabase가 중앙에서 관리 — 다중 인스턴스가 같은 상태를 본다.** 해소됨 |
| WAL/네트워크 파일시스템 | NFS·FUSE에서 깨짐 — Cloud Run 배포 자체를 막던 근본 이유 | **해당 없음** — 컨테이너에 DB 파일 자체가 없다(Dockerfile 74번째 줄 주석) |
| MCP stdio | 백엔드와 같은 컨테이너 필요 (D15) | **여전히 유지** — 단, 이건 "인스턴스 1개"가 아니라 "인스턴스마다 자기 MCP 자식 프로세스"를 뜻한다. Cloud Run이 인스턴스를 N개로 늘리면 MCP 자식도 N개, 문제 없음 |
| RAG 인덱스 | 프로세스 메모리 로드, 인스턴스마다 중복 | 키워드 인덱스(`manual_chunks.jsonl`)는 여전히 인스턴스마다 로드(가벼움, 1.4MB). dense 코퍼스 임베딩은 **Postgres에서 질의마다 조회**라 중복 없음 |

**결론**: **Cloud Run을 min/max 인스턴스 1로 고정해야 할 기술적 이유가 이제 없다.** 다만
지금 배포 초기 단계라 §6에 "복제본 수·오토스케일 정책"을 신규 미결정으로 남겨 둔다(아직
동시 요청 부하 실측이 없어 안전하게 1~2로 시작하는 걸 권한다).

---

## 5. 권고 구성 (확정)

| 층 | 결정 | 근거 |
|---|---|---|
| 프론트 | **Vercel 또는 Netlify** | 프론트는 `API_BASE`로 백엔드를 직접 호출하고 SSE를 Next 라우트로 프록시하지 않는다 → 플랫폼별 스트리밍 버퍼링 함정을 애초에 피해 있다. 아래 ⚠ 유지 |
| 백엔드+AI+MCP | **GCP Cloud Run**(사용자 결정, 2026-08-24) | 컨테이너가 이제 상태 없음(stateless) — DB가 컨테이너 밖 Supabase라 Cloud Run의 "요청 없으면 스케일 0" 모델과 궁합이 좋다. 기존 `Dockerfile`을 그대로 쓸 수 있다(§4) |
| RDB + 벡터 | **Supabase(관리형 Postgres + pgvector)**(사용자 결정, 2026-08-24) | §2·§3. 별도 벡터 DB 불필요 |
| MCP | **stdio 유지, 백엔드와 같은 컨테이너** | D15 프로세스 분리는 stdio로도 성립, §4 |

> ⚠ **SSE를 Next.js 라우트로 프록시하지 말 것.** 지금 구조(브라우저 → 백엔드 직접)를 유지하면
> 플랫폼 선택이 자유롭다. 프록시를 넣는 순간 서버리스 응답 버퍼링이 `token`/`tool_call`/
> `tool_result`/`block` 스트림(D14·D22)을 뭉개기 시작한다.

### 5-0. 실행 경로 (D159, 2026-09-28) — 스크립트가 있다

프론트는 **Netlify**(`netlify.toml`, base=`frontend`)로 확정했다. 순서:

1. Supabase 프로젝트 생성 → **Session pooler(5432)** 연결 문자열 확보
   (직결 `db.<ref>.supabase.co` 는 IPv6 전용이라 Cloud Run 에서 닿지 않는다)
2. `SUPABASE_DATABASE_URL=… deploy/cloudrun/db_to_supabase.sh` — 로컬 DB **통째 이관**
   (재시드는 HV600 승격·정규화를 복구하지 못한다). 대상 public 이 비어 있지 않으면 멈춘다.
   권한은 덤프에서 빼고 `postgres_guards.sql` 을 다시 적용해 D10 트리거·D154 역할을 복원한다
3. `SUPABASE_DATABASE_URL=… MAINTQ_DEMO_TOKEN=… FRONTEND_ORIGIN=https://<site>.netlify.app deploy/cloudrun/deploy.sh`
   — `gcloud run deploy --source .`(Cloud Build). 업로드 목록은 `.gcloudignore`(= .gitignore + .dockerignore)
4. Netlify 사이트 환경변수 `NEXT_PUBLIC_API_BASE=<Cloud Run URL>` 후 빌드
5. 공유 링크: `https://<site>.netlify.app/?demo_token=<토큰>` (한 번 열면 브라우저에 저장된다)

**운영 중 (2026-09-28 첫 배포)**: 프론트 `https://maintq-nvidia.netlify.app` · 백엔드
`https://maintq-backend-97558858623.asia-northeast3.run.app`(GCP `gcp-solana-ai-agentic-hacks-kr`) ·
DB Supabase `MaintQ`(`zccomludbsoivogycrij`, 서울). 비밀(연결 문자열·데모 토큰)은 **`.env.deploy`**(gitignore)에만 있다.

첫 배포에서 드러난 함정 7개 — 각 파일 주석에 근거를 남겼다:
- `.gcloudignore` 가 `.gitignore` 를 포함하면 **git 미추적 런타임 파일**(`manual_chunks.jsonl`)이 이미지에서 빠져
  `rag_search_manual` 이 전부 error 가 된다. 로컬 `docker build` 스모크로는 안 잡힌다 — 배포 후 채팅 1턴으로 확인할 것
- Netlify **업로드 배포**는 Next.js 런타임을 자동으로 붙이지 않는다(`netlify.toml` 에 `@netlify/plugin-nextjs` 명시) — 빠지면 빌드 성공 + 전 경로 404
- Supabase 는 `public` 을 REST 로 노출하고 anon·authenticated 에 GRANT 를 붙인다(이관 직후 462건) — `db_to_supabase.sh` 가 회수한다
- Supabase 풀러(Supavisor)는 접속 문자열의 `options=-c …` 를 **서버로 전달하지 않는다** — `mcp_server/db.py::read_only()`
  세션이 read-write 로 열렸다(SHOW 가 off). 로컬 Docker 에서는 옵션이 먹어 안 보였다. 세션 `SET` + 커밋 + `SHOW` 확인(fail-closed)으로 고쳤다.
  ⚠ 같은 이유로 `options=-c search_path=…`(격리 스키마, `data/pg_isolation.py`)도 Supabase 에서는 안 먹는다 — 스파이크는 로컬 DB 에서만 돌릴 것
- Netlify 는 모든 HTML `<head>` 에 홍보 주석+줄바꿈을 끼워 넣는다(끄는 설정 없음). 루트 레이아웃이 `<head>` 를 직접
  쓰면 React 하이드레이션이 매번 깨지고(#418·#423) 약 1/7 은 #329 로 빠져 승인 큐·재무 화면이 목업에 멈췄다.
  `frontend/app/layout.tsx` 가 `<head>` 를 쓰지 않고 폰트 링크를 `<body>` 맨 앞에 둔다 — 로컬에 같은 주석을 주입해
  재현(#418×3+#423) → 수정 후 0건, 배포판 직접 진입 4화면×8회 전부 실데이터 · React 오류 0
- 공유 링크를 첫 화면(`/?demo_token=`)으로 열면 토큰이 저장되지 않았다(첫 화면은 API 를 안 부른다) — `app/page.tsx` 가 직접 저장
- curl 로 API 를 전부 통과해도 위 두 결함은 안 보인다 — **배포 확인은 실제 브라우저(헤드리스 포함)로 한 번 더** 할 것
- Netlify 업로드는 **작업 디렉터리 전체**를 올린다 — 레포 루트에서 실행하면 `.env`·`.env.deploy` 가 함께 간다. 프론트+`netlify.toml` 만 담은 사본에서 실행할 것

⚠ **OpenShell·NemoClaw 샌드박스는 이 경로에 없다** — 로컬 게이트웨이 전제다. 웹 콘솔만 올라간다.
⚠ A2A 파트너(`MAINTQ_A2A_*_BASE_URL`)는 넣지 않았다 — 호출은 차단기(D136)로 실패 표시된다.

### 5-1. 🔴 확인 필요 — `Dockerfile` 헤더 주석이 "Northflank 배포용"이라고 적혀 있다

`Dockerfile` 2번째 줄: `# MaintQ — Northflank 배포용 Dockerfile`. Cloud Run으로 확정됐다면
이 주석은 낡았다(실제 이미지 내용 — Python 3.13-slim, uv sync, uvicorn CMD, HEALTHCHECK —
는 플랫폼 무관하게 그대로 쓸 수 있다. Cloud Run은 HEALTHCHECK 지시문을 직접 쓰진 않지만
무시될 뿐 해가 되지 않는다). **이 문서 갱신 범위 밖이라 코드는 안 건드렸다** — 주석만 고칠지,
Northflank도 동시에 열어 둘지(둘 다 같은 이미지로 배포 가능하니 주석에서 "Northflank 전용"
표현만 빼는 정도로 충분할 수 있다) 사용자가 정할 것.

### 5-2. 배포 순서 (최초 1회, `Dockerfile` 31~35번째 줄과 동일)

```bash
# 1. Supabase 프로젝트 생성 (docs/POSTGRES_SETUP.md "Option A" 참고)
# 2. 스키마 + D10 가드 적용
psql "$DATABASE_URL" -f scripts/postgres_schema.sql
psql "$DATABASE_URL" -f scripts/postgres_guards.sql
# 3. 시드 (데모용 초기 데이터 — 운영 전환 시엔 생략하거나 별도 정본 데이터로 교체)
DATABASE_URL=... uv run python data/seed.py --with-error-codes
# 4. dense 검색용 코퍼스 임베딩 색인 (사람이 명시 실행, D105 식 지출 가드 — §2)
DATABASE_URL=... NVIDIA_API_KEY=... uv run python scripts/migrate_vectors.py
# 5. 이미지 빌드·푸시·배포
docker build -t maintq .
docker tag maintq gcr.io/[PROJECT_ID]/maintq:latest
docker push gcr.io/[PROJECT_ID]/maintq:latest
gcloud run deploy maintq \
    --image gcr.io/[PROJECT_ID]/maintq:latest \
    --region asia-northeast3 \
    --allow-unauthenticated \
    --set-env-vars DATABASE_URL=$DATABASE_URL,MAINTQ_LLM_PROVIDER=...,...
```

리전은 예시(`asia-northeast3`=서울) — 확정 안 됐으면 §6에 추가할 것.

### 5-3. 백로그 **P14 문구 정정 필요** (기존 절, 그대로 유지)

P14는 *"docker-compose (backend + mcp-server **2서비스**)"*로 적혀 있으나, **stdio는
부모-자식 프로세스라 컨테이너 2개로 쪼갤 수 없다.**

- ⓐ **P14를 "1컨테이너 안 2프로세스"로 정정** — D15 프로세스 분리는 그대로 성립. 권장
- ⓑ **MCP 트랜스포트를 HTTP/SSE로 전환** — 새 D-결정 사안이고 `backend/agent/mcp_client.py`
  재작성이 따른다

---

## 6. 미결정 — 사람이 정해야 한다

| # | 결정할 것 | 선택지 | 걸린 것 |
|---|---|---|---|
| ① | ~~DB 영속 vs 휘발~~ | — | **해소됨** — Supabase가 관리형 영속 Postgres다. 재시작·재배포에도 데이터가 남는다 |
| ② | ~~인증~~ | — | **해소됨(D159)** — 데모 토큰 게이트(`MAINTQ_DEMO_TOKEN`). 인증이 아니라 문지기다: 토큰을 아는 사람은 여전히 `X-Role` 로 역할을 바꿀 수 있다(P21 미해소) |
| ③ | **LLM 비용 방어** | ⓐ 레이트리밋 ⓑ 공개 데모 시간 제한 ⓒ 키 회전 | 기본 provider가 `gemini`. `MAINTQ_LLM_CACHE`(D104 카세트)는 **평가용이지 런타임 방어가 아니다** |
| ④ | **신규 — Cloud Run 복제본 수·오토스케일 정책** | ⓐ min=max=1(SQLite 시절 습관 유지) ⓑ min=0(콜드스타트 감수, 비용 최소) ⓒ min=1·max=N(상시 1개+피크 대응) | §4가 다중 인스턴스를 기술적으로 막지 않게 됐지만, **아직 동시 부하 실측이 없다.** MCP 자식 프로세스 기동 비용(콜드스타트 지연) 실측도 안 됐음 |
| ⑤ | **신규 — Supabase 커넥션 풀링 모드** | ⓐ Session pooler(5432) ⓑ 직접 연결 ⓒ Transaction pooler(6543) | §3 — D10 가드가 `SET LOCAL`로 트랜잭션 풀러도 방어된다고 코드는 확인됐지만 실 트래픽 검증 없음. ⓐ/ⓑ 권장 |
| ⑥ | **신규 — `Dockerfile` "Northflank 배포용" 주석** | ⓐ 문구만 정리(범용화) ⓑ Cloud Run 전용 문구로 교체 ⓒ 그대로 두고 Northflank도 배포 대상으로 유지 | §5-1 |

---

## 7. 환경변수 (배포 시 주입)

| 변수 | 필수 | 비고 |
|---|---|---|
| `DATABASE_URL` | ✅ | **Supabase 연결 문자열**(`postgresql://...`). `?sslmode=require` 필요할 수 있음 — Supabase 대시보드가 주는 문자열을 그대로 쓸 것 |
| `MAINTQ_LLM_PROVIDER` | ✅ | 현 기본 `nvidia`(D122 개정 — build.nvidia.com 무료 티어) \| `gemini` \| `anthropic` \| `elice`(D115) |
| `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `ELICE_API_KEY`+`ELICE_LLM_URL` | ✅ (택1) | provider에 맞춰 |
| `MAINTQ_LLM_MODEL` | — | 미지정 시 기본 |
| `NVIDIA_API_KEY` / `NVIDIA_EMBED_MODEL` | — | dense 검색용(D117, §2). 미설정 시 키워드 전용으로 조용히 물러남(서비스 안 죽음) |
| `MAINTQ_CHUNKS` | — | 기본값이 이미지 내 경로라 보통 불필요 |
| `MAINTQ_DEMO_TOKEN` | ✅(공개 배포) | D159 데모 토큰 게이트. 비우면 게이트 무동작 — `deploy/cloudrun/deploy.sh` 는 비어 있으면 배포를 거부한다 |
| `MAINTQ_CORS_ORIGINS` | ✅ | **프론트 배포 도메인**을 반드시 등재 |
| `MAINTQ_MCP_AUTOSTART` | ✅ | `1` 유지 (stdio spawn) |
| `MAINTQ_TOOLS_PROFILE` | — | **기본 `core`**. 확장 도구를 켜려면 `full` (D69·D88 — **평가는 `core`에서만 인정**) |
| `NEXT_PUBLIC_API_BASE` | ✅ | 프론트 빌드타임 주입 — **백엔드 공개 URL**(Cloud Run이 준 URL) |
| `MAINTQ_A2A_FINALLQ_BASE_URL` / `MAINTQ_A2A_INSUQ_BASE_URL` | — | A2A 파트너 어댑터 호출 대상. 로컬 개발은 `localhost:9101`/`9102`, 실 배포는 파트너의 실제 배포 URL로 교체 |
| `MAINTQ_A2A_FINALLQ_CLIENT_ID`/`_SECRET`, `MAINTQ_A2A_INSUQ_CLIENT_ID`/`_SECRET` | — | 파트너 자격증명(D93). 어댑터가 아직 인증을 검사하지 않으면 비워 둬도 라운드트립은 됨 |
| `MAINTQ_DB` | — | **더 이상 읽히지 않는다**(SQLite 시절 변수, `backend/db.py`·`mcp_server/db.py`는 Postgres 전용). `.env`에 남아 있어도 무해하지만 넣을 필요 없음 |
| `LAW_API_OC` · `DATA_GO_KR_SERVICE_KEY` · `IROS_API_KEY_*` | — | **런타임 미호출** (수집 스크립트 전용). 배포 컨테이너에 넣을 필요 없다 |

> 🔴 `data/rules/fetch_laws.py`의 요청 파라미터에는 `LAW_API_OC`가 실린다. 2026-08-13에
> 평문 자격증명이 추적 파일로 흘러 `git filter-repo`로 **커밋 10개**를 재작성한 사고가 있었다
> (D103). **수집 키를 런타임 컨테이너 환경에 올리지 않는 것**이 노출면을 줄이는 가장 싼 방법이다.

---

## 8. 배포 전 체크리스트

- [ ] §6 미결정 5건 확정(①은 해소됨, ②~⑥ 남음)
- [ ] 회귀 전수 통과 — **건수는 CLAUDE.md "회귀 스위트" 절의 최신 실측 기준선을 볼 것**(이
      문서에 하드코딩하지 않는다 — 자주 바뀌고, 옛 숫자를 박아두면 다음 세션이 그대로 믿는
      사고가 반복됐다). 최소 `data/seed.py --with-error-codes` + spikes 전체 + pytest 전체 +
      `ruff check`
- [ ] `MAINTQ_TOOLS_PROFILE` 값 확정 (데모는 `full`, 평가는 `core` — D88)
- [ ] `MAINTQ_CORS_ORIGINS`에 프론트 도메인 등재 확인
- [ ] 이미지에 `data/raw/*.pdf`가 **포함되지 않았는지** 확인 (`.dockerignore` 실측 확인)
- [ ] `manifest.json`은 포함됐는지 확인 (없으면 인용 페이지 환산이 깨진다 — D19·D32)
- [ ] `scripts/postgres_schema.sql`·`postgres_guards.sql`이 대상 Supabase 프로젝트에 **둘 다**
      적용됐는지(가드 빠뜨리면 D10이 조용히 안 지켜진다)
- [ ] `scripts/migrate_vectors.py` 실행 여부 확인(안 돌리면 dense 검색이 전부 0.0으로 조용히
      키워드 전용이 된다 — 서비스는 안 죽지만 품질이 낮다, §2)
- [ ] Supabase 커넥션 풀링 모드 확정(§6 ⑤)
- [ ] SSE가 배포 환경에서 끊기지 않는지 실측 (프록시·타임아웃)
- [ ] Cloud Run 인스턴스 수·오토스케일 정책 확정(§6 ④)

---

## 9. 관련 결정·백로그

| 참조 | 내용 |
|---|---|
| **D15** | 백엔드 ↔ MCP 프로세스 분리 (stdio) |
| **D27** | 환경 관리 uv+venv, Docker는 MVP 제외 → P14 |
| **D47·D48** | RAG 하이브리드 인터페이스 · 구현 위치 |
| **D51** | 임베딩 활성화 여부·모델 미결정 — **D117로 해소됨** |
| **D60** | 원본은 파일(git)이 정본, DB는 조회용 사본 |
| **D99** | 쓰기 커넥션 분리 개념(SQLite 시절) — Postgres판은 D116이 트리거+GUC로 재구현 |
| **D103** | 외부 응답 원본 보관 · 자격증명 미저장 |
| **D116** | SQLite→Postgres 마이그레이션 실제 완성 (§3) |
| **D117** | RAG dense 검색 활성화, NVIDIA 임베딩 + pgvector (§2) |
| **P14** | docker-compose (§5-3 문구 정정 필요) |
| **P21** | 인증·계정 (§6 ②) |
