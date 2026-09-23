# NVIDIA 해커톤 Day 1 — Nemotron 교체 + OpenShell 샌드박스 (2026-09-24)

**브랜치**: `feat/nvidia-hackathon` · **마감**: 2026-09-28(월) 23:59
**오늘 목표**: S1(진단→재고→발주 draft)·S4(미지 코드→추측 없이 A/S)가 **Nemotron** 으로,
**OpenShell 샌드박스 안에서** 동작하는지 확인한다. 성능 측정은 하지 않는다.

> ⚠ 이 문서에는 **이번 세션에서 직접 실행해 확인한 것만** 적는다. 문서로만 읽은 것은
> 「미확인」으로 따로 표시한다. 기존 평가 수치(오특정률 등)는 이전 모델 기준이라 **Nemotron 결과로 인용하지 않는다.**

---

## 1. 결과 요약

| 항목 | 상태 | 근거 |
|---|---|---|
| Nemotron 도구 호출 (단독 프로브) | ✅ 동작 | `nemotron-3-super-120b-a12b` 가 `lookup_error_code(model=iG5A, code=OHt)` 를 정확한 인자로 호출, `finish_reason=tool_calls` (2/2) |
| S1 — Nemotron, 로컬 | ✅ 3턴 완주 | 진단 → 재고 → 견적 → **`PO-0121` draft 생성**. 안전 블록 + 인용(p.202) 발행 |
| S4 — Nemotron, 로컬 | ✅ | 기종 되물음 → `lookup_error_code` `not_found` → 원인·조치 생성 없음, A/S 안내 |
| D76(도구 결과를 user 텍스트로) | ✅ 그대로 동작 | 네이티브 `tool` 역할 분기 **불필요** — 다중 도구 체인이 깨지지 않았다 |
| 이미지에 키 없음 | ✅ | 이미지 파일 10,594개 전수 스캔, `.env` 의 비밀값 16종 **0건** (양성 앵커 3종 검출로 스캐너 생존 확인) |
| 샌드박스 모드 명시적 실패 | ✅ | 게이트웨이 없이 띄우면 채팅에 `샌드박스 정책상 폴백 불가 (egress 기본 차단, D143)` 가 그대로 나온다 |
| OpenShell 설치 | ⛔ **막힘** | 설치 스크립트가 `sudo apt-get install openshell_0.0.116` 에서 **WSL sudo 비밀번호**를 기다린다 — 에이전트가 입력할 수 없다. 사람이 설치해야 한다 (§6) |
| OpenShell 샌드박스 실행 · 차단 확인 | ⏳ 미실행 | 설치 후 진행 |

---

## 2. 설계 결정 — D143

**OpenShell 샌드박스 모드(`MAINTQ_SANDBOX=openshell`)** — 전문은 `docs/10_DECISIONS.md` D143.

- 켜지면 LLM 은 `nvidia` 제공자만, `https://inference.local`(OpenShell 추론 라우팅)로만 호출한다
- 샌드박스 안에 `NVIDIA_API_KEY` 가 **보이면 기동을 거부**한다 — "키는 게이트웨이에만" 을 코드가 강제
- 폴백(OpenAI 등)은 조립하지 않는다. primary 실패는 `SandboxFallbackBlocked` →
  사용자 화면에 **"샌드박스 정책상 폴백 불가"** (원인은 타입+상태코드만, 본문 없음 — D40·D131)
- `MAINTQ_SANDBOX` 는 빈 값 또는 `openshell` 만 — 오타가 조용히 "샌드박스 아님" 이 되지 않는다
- 샌드박스 밖은 기존 동작 그대로. 폴백 코드·로컬 설정은 지우지 않았다
- 회귀: `test_llm_fallback.py` 15→**25** (7파일군 128→**138**). 뮤턴트 3종(키 가드 무력화 ·
  래퍼가 실패를 삼킴 · 래퍼가 항상 실패) **전부 검출**

**기존 원칙 무손상**: 쓰기 도구·D10 트리거·읽기 전용 커넥션·신원 주입(D23·D36)·결재 API 는
한 줄도 건드리지 않았다. S1 의 `create_po_draft` 는 draft INSERT 만 했다(`PO-0121`, `state=draft`).

---

## 3. LLM 호출 구조 (Step 0 조사)

- 호출 지점: `backend/agent/llm.py::get_client()` **한 곳** — 사용처 `backend/routers/chat.py`(에이전트) ·
  `eval/judge.py`(평가). 스트림 소비는 `backend/agent/loop.py`
- SDK: OpenAI 호환 제공자(nvidia·ollama·openai·elice)는 전부 `openai.AsyncOpenAI` 하나(`EliceClient`)
- 도구 호출: OpenAI `tools`(function) 형식, MCP `input_schema` 를 그대로 넘긴다
- `nvidia` 제공자는 **이미 있었다**(D123) — 전환은 env 2줄(`MAINTQ_LLM_PROVIDER=nvidia`,
  `MAINTQ_LLM_MODEL=nvidia/nemotron-3-super-120b-a12b`). 코드 변경은 샌드박스 모드(D143)뿐
- 임베딩은 이미 NVIDIA(`nvidia/nemotron-3-embed-1b`, `data/external/nvidia_embed.py`) — 키를 **직접** 쓴다

### 모델 ID (2026-09-24, `GET /v1/models` 실측 — 82종)

| ID | 결과 |
|---|---|
| `nvidia/nemotron-3-super-120b-a12b` | ✅ 호출·도구 호출 확인 — **메인** |
| `nvidia/nemotron-3-ultra-550b-a55b` | ✅ 도구 호출 확인(6.7s, 느림) |
| `nvidia/nemotron-nano-3-30b-a3b` | ⛔ **목록에는 있는데 호출하면 404** |
| `openai/gpt-oss-120b` | 목록에 없음 — 9-05 의 410 EOL 을 목록으로도 확인 |

⚠ OpenShell 문서 예시의 `nvidia/nemotron-3-nano-30b-a3b` 는 **목록에 없는 ID** 다(실제 목록은 `nemotron-nano-3-…`).
**목록에 있다 ≠ 호출된다** — 모델을 바꿀 때는 반드시 1회 호출로 확인할 것.

---

## 4. Step 2 관찰 기록 (고치지 않고 기록만)

| # | 관찰 | 분류 | 조치 |
|---|---|---|---|
| O1 | NVIDIA `Service temporarily overloaded` — S1 첫 시도는 1회차, 두 번째는 5회차 LLM 호출에서 스트림 실패. 이후 2회는 정상 | 외부(무료 티어 과부하) | 기록만. 사용자에게는 기존 문구로 실패가 보인다(조용한 종료 아님). **데모 리스크** — Day 2 이후 재시도 정책 검토 |
| O2 | `create_po_draft` 1차 호출에서 `evidence` 를 **JSON 문자열**로 넘겨 스키마 검증 실패 → 모델이 **스스로 객체로 고쳐 재호출**, 성공 | 인자 포맷 | 기록만. 자가 복구됨 |
| O3 | 응답 본문에 `안전 først` — 노르웨이어 토큰 혼입 | 모델 출력 품질 | 기록만 |
| O4 | S1 한 실행(run c)이 도구 2개만 부르고 재고 조회 없이 끝남 — 다른 실행은 5개 | 도구 선택 편차 | 기록만(성능 측정 안 함) |
| O5 | 응답 끝에 `(시스템이 자동으로 안전 경고 블록과 인용 칩을 생성합니다.)` — 시스템 프롬프트 내용 노출 | 프롬프트 누출 | 기록만 |
| O6 | S1 3턴 응답 한가운데 `근거 문서를 확인하지 못해 작업 절차를 안내할 수 없습니다.` 가 끼어듦 | **안전 게이트 정상 발동**(`loop.py:435`, 절대규칙 3) — 인용 없는 턴에 "전원 차단 10분" 문구가 나와 걸렸다 | 게이트는 **끄지 않는다.** 문구 위치가 어색한 UX 문제만 남음 |
| O7 | `rag_search_manual` 이 한 턴에 2번 호출되는 경우 있음 | 루프 | 정상 범위(상한 내) |

---

## 5. OpenShell 샌드박스 설계 (방식 A)

**MaintQ 는 OpenShell 공식 지원 에이전트(Claude Code·OpenCode·Codex·Copilot CLI·OpenClaw·Hermes)가 아니다.**
그래서 **자체 이미지(BYOC) 방식**으로 OpenShell 을 직접 쓴다 — `openshell sandbox create --from <image>`.
NemoClaw 는 설치하지 않는다(RAM 7GB · WSL Node v18). 대신 NemoClaw 가 OpenShell 위에서 쓰는
**정책(기본 차단 + 선언된 binary→endpoint 허용)과 추론 라우팅(inference.local, 키는 게이트웨이에만)**
접근을 그대로 참고했다.

- 이미지: 루트 `Dockerfile`(백엔드 + MCP stdio 자식, 한 컨테이너) 위에 `deploy/openshell/Dockerfile.sandbox`
  — **uid 1000**(process 정책이 root 거부) + 샌드박스 env. 키 없음
- DB: Postgres 는 샌드박스 **밖**(compose), 정책으로 `host.docker.internal:5434` 만 허용.
  막히면 방식 B(Postgres 를 이미지 안에서 비root 로 함께 기동)로 전환
- 추론: `inference.local` → 게이트웨이가 키 주입 · model 재작성
- 임베딩: §5.2

### 5.1 정책 YAML — `deploy/openshell/policy.yaml`

```yaml
version: 1
filesystem_policy:
  include_workdir: true
  read_only: [/usr, /lib, /etc, /proc, /dev/urandom, /app]
  read_write: [/tmp, /dev/null]
landlock:
  compatibility: best_effort
process:
  run_as_user: "1000"
  run_as_group: "1000"
network_policies:
  maintq_postgres:
    name: maintq-postgres
    endpoints:
      - {host: host.docker.internal, port: 5434, protocol: tcp, enforcement: enforce}
    binaries:
      - path: /app/.venv/bin/python*
      - path: /usr/local/bin/python3*
```

**근거**
- **기본 차단** — 스키마상 선언되지 않은 binary·endpoint 조합은 전부 거부된다. 우리가 여는 것은 DB 하나다
- **`/app` 읽기 전용** — 앱 코드·매뉴얼 청크를 에이전트가 고쳐 쓸 수 없다. 쓰기는 `/tmp` 만
- **NVIDIA 를 network_policies 에 적지 않는다** — `integrate.api.nvidia.com` 을 직접 열면 샌드박스 안에 키가
  있어야 하고 D143 과 충돌한다. 추론은 게이트웨이의 `inference.local` 경유만
- **폴백 호스트(OpenAI·Ollama)를 열지 않는다** — 열면 "샌드박스 정책상 폴백 불가" 가 거짓이 된다
- **MCP 서버는 네트워크 정책이 필요 없다** — 백엔드의 stdio 자식이라 같은 샌드박스 안 프로세스 간 통신이다.
  core 7종 도구는 외부 HTTP 를 부르지 않는다(외부를 부르는 A2A 도구는 `full` 프로필 전용)

### 5.2 임베딩 — inference.local 불가 (원문 확인)

원문(https://docs.nvidia.com/openshell/sandboxes/inference-routing):
- `/v1/embeddings` 경로 자체는 지원 목록에 **있다**
- 그러나 *"One provider and one model define sandbox inference for the active gateway"* 이고
  *"the privacy router … rewrites the model before forwarding"* — **임베딩 요청의 model 이 채팅 모델로 재작성된다.**
  채팅과 임베딩을 한 게이트웨이에서 동시에 쓸 수 없다

**채택**: 샌드박스 안에서는 **질의 임베딩을 호출하지 않는다** — 키가 없으므로 `dense_scorer.score()` 가
D47 이 정의한 키워드 전용 경로(전부 0점)로 떨어진다. **코드 변경 0줄.**
코퍼스 임베딩(`manual_chunks.embedding`)은 이미 DB 에 사전 색인돼 있지만 질의 벡터가 없으면 쓰이지 않는다.
- 대안 ⓑ 데모 질의 임베딩을 미리 캐시해 이미지에 동봉 — `data/cache` 는 `.dockerignore` 대상이고, 질의가 조금만 달라도 캐시 미스라 취약
- 대안 ⓒ 샌드박스에 키를 넣고 임베딩 호스트만 허용 — D143 의 핵심을 버린다. **기각**
- ⚠ 지금은 dense 가 꺼진 것이 **warning 로그 없이** 조용하다(키 미설정 분기가 `return zeros`).
  데모에서 "검색이 키워드 전용" 임을 보여 주려면 Day 2 에 표시를 검토

---

## 6. 막힌 것 — OpenShell 설치 (사람 필요)

설치 스크립트(`curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh`)가
`openshell_0.0.116-1_amd64.deb` 를 `sudo apt-get install` 로 설치하려다 **비밀번호 입력을 기다리며 멈췄다.**
에이전트 셸은 비대화식이라 입력할 수 없다. 멈춘 프로세스는 정리했다(잔존 0, 패키지 미설치 확인).

**사람이 할 일** (WSL Ubuntu 터미널에서):
```bash
curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh
openshell --version
# 게이트웨이에 NVIDIA 키 등록 — 키는 이 셸의 환경변수로만, 파일에 쓰지 않는다
export NVIDIA_API_KEY=...        # 직접 입력
openshell provider create --name nvidia-prod --type nvidia --from-existing
openshell inference set --provider nvidia-prod --model nvidia/nemotron-3-super-120b-a12b
unset NVIDIA_API_KEY
```

그 뒤 에이전트가 이어 할 것:
```bash
openshell sandbox create --name maintq --from maintq-sandbox:day1 \
  --policy deploy/openshell/policy.yaml \
  --env DATABASE_URL=postgresql://postgres:postgres@host.docker.internal:5434/maintq \
  --forward 8000 --detach -- uvicorn backend.main:app --host 0.0.0.0 --port 8000
# 차단 확인 — 허용 안 된 호스트
openshell sandbox exec maintq -- python -c "import urllib.request as u; u.urlopen('https://api.openai.com', timeout=5)"
openshell logs maintq --tail --source sandbox
```

---

## 7. 미확인 (문서로만 읽음 — 실측 전)

- `inference.local` 을 network_policies 에 적지 않아도 게이트웨이가 가로채는지
- 샌드박스 안에서 `host.docker.internal` 이 호스트 Postgres 로 풀리는지 (일반 Docker 에서는 됐다)
- 정책 binary 경로 매칭이 python 심링크(`/app/.venv/bin/python` → `/usr/local/bin/python3.13`)를 어느 쪽으로 보는지
- 차단 시 에러 형태 (REST 403 / TCP 연결 종료라는 설명은 요약에서만 봤다)
- `openshell provider create --from-existing` 이 키를 어디서 읽는지 (셸 env 로 가정)
- OpenShell 은 **alpha** — WSL2 지원은 README 에 **experimental** 로 적혀 있다
- 추론 라우팅 기본 타임아웃 **60초** — S1 의 긴 턴(48s 관측)이 여기에 걸릴 수 있다. 필요 시 `--timeout`

---

## 8. Day 2(사업장 온보딩 + 지도) 전에 알아야 할 제약

1. **egress 는 기본 차단이다.** 지도 타일·지오코딩 API 등 새 외부 호출은 전부 `network_policies` 에
   binary+host 단위로 추가해야 하고, **추가한 만큼 데모의 보안 서사가 약해진다.** 서버가 부르는 것만 해당 —
   브라우저(프론트)에서 부르는 지도 SDK 는 샌드박스 정책 대상이 아니다(프론트는 샌드박스 밖)
2. **추론 게이트웨이는 모델 1개**다 — 온보딩 에이전트가 다른 모델(예: 음성·VLM)을 쓰려면 같은 게이트웨이에서
   채팅과 공존할 수 없다. 음성 입력(Day 3)도 같은 제약
3. **임베딩은 샌드박스 안에서 꺼진다**(§5.2) — 온보딩 문서 검색을 dense 로 설계하면 샌드박스에서 동작하지 않는다
4. **파일시스템 정책은 생성 시 고정** — 온보딩이 파일 업로드·저장을 한다면 경로를 미리 `read_write` 에 넣고
   샌드박스를 다시 만들어야 한다
5. **NVIDIA 무료 티어 과부하**(O1) — 라이브 데모 중 스트림 실패가 날 수 있다. 녹화 데모 또는 재시도 정책 필요
6. **nano 계열 모델 ID 함정**(§3) — 경량 모델로 바꿀 때 호출로 먼저 확인
7. **MCP 도구를 늘리면** — 도구가 외부 HTTP 를 부르는 순간 정책 항목이 생긴다. 새 쓰기 도구는 여전히 draft INSERT 만(D10)

---

## 9. 커밋

| 커밋 | 내용 |
|---|---|
| `5e5e962` | D143 — OpenShell 샌드박스 모드 + 회귀 10건 + D 범위 표기 D1~D143 |
| (이 커밋) | `deploy/openshell/`(Dockerfile.sandbox · policy.yaml) + 이 문서 |
