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
| Nemotron 도구 호출 (단독 프로브) | ✅ | `nemotron-3-super-120b-a12b` 가 `lookup_error_code(model=iG5A, code=OHt)` 를 정확한 인자로 호출, `finish_reason=tool_calls` (2/2) |
| S1 — Nemotron, 로컬 | ✅ 3턴 완주 | 진단 → 재고 → 견적 → **`PO-0121` draft**. 안전 블록 + 인용(p.202) |
| S4 — Nemotron, 로컬 | ✅ | 기종 되물음 → `not_found` → 원인·조치 생성 없음, A/S 안내 |
| D76(도구 결과를 user 텍스트로) | ✅ 그대로 동작 | 네이티브 `tool` 역할 분기 **불필요** |
| **S4 — 샌드박스 안** | ✅ | `not_found` → 추측 없이 A/S 안내 |
| **S1 — 샌드박스 안** | ✅ 3턴 완주 | 진단·RAG·재고 → 견적 → **`PO-0122` draft**. 안전 블록 + 인용 |
| **샌드박스 안에 키 없음** | ✅ | `NVIDIA_API_KEY in env: False` 인데 `inference.local` 로 Nemotron 도구 호출 성공 — 게이트웨이 로그 `openshell_router: routing proxy inference request` |
| **허용 안 된 호스트 차단** | ✅ | `api.openai.com` · `integrate.api.nvidia.com`(직접) · `ollama.com` · `example.com` 전부 `403 Forbidden`, 로그에 실행 파일·목적지·이유 (§5.3) |
| **D10 가드 — 샌드박스 안** | ✅ | `draft_writer` 로 `UPDATE po_drafts` → `mcp_block_write()` 트리거가 거부 · `read_only` 로 INSERT → `read-only transaction` 거부 · 상태 `draft` 유지 |
| **파일시스템** | ✅ | `/app` 쓰기 → `PermissionError 13` (Landlock) |
| 이미지에 키 없음 | ✅ | 최종 이미지 파일 17,833개(DB 템플릿 포함) 전수 스캔, `.env` 비밀값 16종 **0건** (양성 앵커 4종 검출로 스캐너 생존 확인) |
| 샌드박스 모드 명시적 실패 | ✅ (일반 Docker) | 게이트웨이 없이 띄우면 채팅에 `샌드박스 정책상 폴백 불가 (egress 기본 차단, D143)` |
| DB 방식 | **B** | 방식 A(호스트 Postgres 허용)는 Docker Desktop 에서 불가 — §5 |

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
한 줄도 건드리지 않았다. S1 의 `create_po_draft` 는 draft INSERT 만 했다(`PO-0121`·`PO-0122`, `state=draft`).

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
| O1 | NVIDIA `Service temporarily overloaded` — 로컬 S1 첫 시도는 1회차, 두 번째는 5회차 LLM 호출에서 스트림 실패. 이후 전부 정상(샌드박스 포함) | 외부(무료 티어 과부하) | 기록만. 사용자에게는 실패 문구가 보인다(조용한 종료 아님). **데모 리스크** |
| O2 | `create_po_draft` 1차 호출에서 `evidence` 를 **JSON 문자열**로 넘겨 스키마 검증 실패 → 모델이 **스스로 객체로 고쳐 재호출**, 성공. 샌드박스 실행에서는 처음부터 객체로 넘김 | 인자 포맷 | 기록만. 자가 복구됨 |
| O3 | 응답 본문에 `안전 først` — 노르웨이어 토큰 혼입 | 모델 출력 품질 | 기록만 |
| O4 | 로컬 S1 한 실행이 도구 2개만 부르고 재고 조회 없이 끝남 — 다른 실행은 3~5개 | 도구 선택 편차 | 기록만(성능 측정 안 함) |
| O5 | 응답 끝에 `(시스템이 자동으로 안전 경고 블록과 인용 칩을 생성합니다.)` — 시스템 프롬프트 내용 노출 | 프롬프트 누출 | 기록만 |
| O6 | S1 3턴 응답 한가운데 `근거 문서를 확인하지 못해 작업 절차를 안내할 수 없습니다.` 가 끼어듦 | **안전 게이트 정상 발동**(`loop.py:435`, 절대규칙 3) — 인용 없는 턴에 "전원 차단 10분" 문구가 나와 걸렸다 | 게이트는 **끄지 않는다.** 문구 위치가 어색한 UX 문제만 남음 |
| O7 | `rag_search_manual` 이 한 턴에 2번 호출되는 경우 있음 | 루프 | 정상 범위(상한 내) |

---

## 5. OpenShell 샌드박스 설계

**MaintQ 는 OpenShell 공식 지원 에이전트(Claude Code·OpenCode·Codex·Copilot CLI·OpenClaw·Hermes)가 아니다.**
그래서 **자체 이미지(BYOC) 방식**으로 OpenShell 을 직접 쓴다 — `openshell sandbox create --from <image>`.
NemoClaw 는 설치하지 않았다(RAM 7GB · WSL Node v18). 대신 NemoClaw 가 OpenShell 위에서 쓰는
**정책(기본 차단 + 선언된 binary→endpoint 허용)과 추론 라우팅(inference.local, 키는 게이트웨이에만)**
접근을 그대로 참고했다.

- 이미지: 루트 `Dockerfile`(백엔드 + MCP stdio 자식, 한 컨테이너) 위에 `deploy/openshell/Dockerfile.sandbox`
  — OpenShell 요구 도구(`iproute2`·`nftables`) + Postgres 17/pgvector + **uid 1000** + 샌드박스 env. 키 없음
- 추론: `inference.local` → 게이트웨이가 키 주입 · model 재작성
- 임베딩: §5.2
- DB: ~~방식 A — 샌드박스 밖 Postgres 를 `host.docker.internal:5434` 로 허용~~ → **기각, 방식 B 로 전환**.
  - 실측: 이름은 `/etc/hosts` 로 `192.168.65.254` 에 풀리는데 연결은 `Network is unreachable`,
    슈퍼바이저 로그 `DENIED host.docker.internal:53 [reason:policy_dns_trusted_gateway_unavailable]`
  - Docker Desktop 에서는 호스트 IP 가 OpenShell 게이트웨이(`host.openshell.internal`)와 **같은 주소**라
    슈퍼바이저가 SSRF 보호로 막는다(기동 로그 `host.openshell.internal maps to a non-link-local IP;
    trusted-gateway SSRF exemption disabled`). 정책 DNS(127.0.0.1:15053)에 직접 물어도 허용·차단 호스트 모두 `REFUSED`
- **방식 B**: Postgres 를 이미지 안에 넣고, 빌드 때 공유 DB 덤프(`pg_dump`, 임베딩 데이터 제외)를
  `/app/pgdata-template` 에 복원 → 기동 때 `/tmp/pgdata` 로 복사해 uid 1000 으로 loopback 에만 띄운다
  (`deploy/openshell/start.sh`). 복원 검증: `error_codes=70` · 사용자 트리거 **12개(원본과 동일)** —
  D10 가드는 DB 역할이 아니라 세션 설정(`default_transaction_read_only`) + 스키마 트리거라 덤프로 그대로 옮겨진다
  - ⚠ 샌드박스는 매번 **빌드 시점 스냅샷**에서 시작하고, 안에서 만든 draft 는 샌드박스를 지우면 사라진다 —
    데모 격리로는 오히려 장점(공유 DB 오염 없음)
  - 덤프 파일은 `deploy/openshell/build/`(gitignore) — 커밋하지 않는다

### 5.1 정책 YAML — `deploy/openshell/policy.yaml` (최종)

```yaml
version: 1
filesystem_policy:
  include_workdir: false
  read_only: [/usr, /lib, /etc, /proc, /dev/urandom, /app]
  read_write: [/tmp, /dev/null]
landlock:
  compatibility: best_effort
process:
  run_as_user: "1000"
  run_as_group: "1000"
network_policies: {}
```

**근거**
- **`network_policies: {}` — 외부 허용 0건.** 백엔드·MCP·Postgres 가 전부 샌드박스 안 loopback 이라
  밖으로 나갈 항목이 없다. 유일한 외부 경로는 게이트웨이가 가로채는 `inference.local` 이다
- **NVIDIA 를 network_policies 에 적지 않는다** — `integrate.api.nvidia.com` 을 직접 열면 샌드박스 안에 키가
  있어야 하고 D143 과 충돌한다
- **폴백 호스트(OpenAI·Ollama)를 열지 않는다** — 열면 "샌드박스 정책상 폴백 불가" 가 거짓이 된다
- **`include_workdir: false` + `/app` 읽기 전용** — `true` 면 작업 디렉터리(`/app`)가 **쓰기 목록에 자동 추가**된다
  (첫 기동 로그 `rw:3`). 앱 코드·매뉴얼 청크·DB 템플릿을 에이전트가 고쳐 쓸 수 없게 껐다. 쓰기는 `/tmp` 만
- **uid 1000** — process 정책이 root 를 거부한다. Postgres 도 uid 1000 으로 돈다
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
- 대안 ⓑ 데모 질의 임베딩을 미리 캐시해 이미지에 동봉 — `data/cache` 는 `.dockerignore` 대상이고, 질의가 조금만 달라도 캐시 미스라 취약
- 대안 ⓒ 샌드박스에 키를 넣고 임베딩 호스트만 허용 — D143 의 핵심을 버린다. **기각**
- ⚠ 지금은 dense 가 꺼진 것이 **warning 로그 없이** 조용하다(키 미설정 분기가 `return zeros`).
  데모에서 "검색이 키워드 전용" 임을 보여 주려면 Day 2 에 표시를 검토

### 5.3 차단 실측 (최종 정책)

샌드박스 안에서 python 으로 HTTPS 요청 — 전부 프록시가 `Tunnel connection failed: 403 Forbidden` 으로 끊었다.
슈퍼바이저 로그(OCSF):

```
NET:OPEN [INFO] ALLOWED inference.local:443
openshell_router: routing proxy inference request (streaming)
NET:OPEN [MED] DENIED /usr/local/bin/python3.13(198) -> api.openai.com:443 [policy:- engine:opa] [reason:network connections not allowed by policy]
NET:OPEN [MED] DENIED /usr/local/bin/python3.13(198) -> integrate.api.nvidia.com:443 [policy:- engine:opa] [reason:network connections not allowed by policy]
NET:OPEN [MED] DENIED /usr/local/bin/python3.13(198) -> ollama.com:443 [policy:- engine:opa] [reason:network connections not allowed by policy]
```

- `integrate.api.nvidia.com` **직접 호출도 막힌다** — NVIDIA 로 가는 길은 게이트웨이 경유 하나뿐이다
- 폴백 호스트(OpenAI·Ollama)가 막히는 것이 D143 "샌드박스 정책상 폴백 불가" 의 실체다
- 샌드박스는 `HTTP(S)_PROXY=http://10.200.0.1:3128` 을 주입한다 — openai SDK(httpx)는 이를 따라 inference.local 에 닿는다.
  허용 안 된 이름은 **DNS 조회부터 실패**한다(`api.openai.com` → `Temporary failure in name resolution`)

---

## 6. 설치·기동 기록 (재현 절차)

**사람이 한 일** (WSL Ubuntu 터미널 — 2026-09-24): 설치 스크립트가 `sudo apt-get install openshell_0.0.116`
에서 비밀번호를 요구해 에이전트가 진행할 수 없었다.
```bash
curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh
export NVIDIA_API_KEY=...        # 직접 입력 — 파일에 쓰지 않는다
openshell provider create --name nvidia-prod --type nvidia --from-existing
openshell inference set --provider nvidia-prod --model nvidia/nemotron-3-super-120b-a12b
unset NVIDIA_API_KEY
```

레포를 WSL 에 다시 받을 필요는 없다 — `/mnt/c/Users/ttogl/workspace/MaintQ` 로 그대로 보이고,
Docker Desktop 은 Windows·WSL 이 같은 이미지 저장소를 쓴다.

이미지 빌드 (레포 루트 — `Dockerfile.sandbox` 머리 주석에 전 절차):
```bash
docker build -t maintq:hackathon-day1 .
docker exec maintq_postgres pg_dump -U postgres -d maintq -Fc --no-owner --no-privileges \
    --exclude-table-data=manual_chunks -f /tmp/maintq.dump
docker cp maintq_postgres:/tmp/maintq.dump deploy/openshell/build/maintq.dump
docker build -f deploy/openshell/Dockerfile.sandbox -t maintq-sandbox:day1 .
```

샌드박스 기동 (WSL, 레포 루트):
```bash
openshell sandbox create --name maintq --from maintq-sandbox:day1 \
  --policy deploy/openshell/policy.yaml \
  --env MAINTQ_SANDBOX=openshell --env MAINTQ_LLM_PROVIDER=nvidia \
  --env MAINTQ_LLM_MODEL=nvidia/nemotron-3-super-120b-a12b \
  --env DATABASE_URL=postgresql://postgres@127.0.0.1:5432/maintq --env PYTHONUNBUFFERED=1 \
  --forward 8000 --detach -- /app/start.sh
curl -s 127.0.0.1:8000/health            # Windows 쪽 localhost:8000 에서도 닿는다
openshell sandbox exec -n maintq --no-tty -- /app/.venv/bin/python -c "..."   # 이름은 -n 으로
openshell logs maintq --source sandbox    # OCSF 이벤트(ALLOWED/DENIED)
```

**기동까지 부딪힌 것 (전부 실측)**

| 증상 | 원인 | 해결 |
|---|---|---|
| `protocol tcp does not support L7-only fields: enforcement` | tcp 엔드포인트에 L7 필드 | 제거 (방식 B 에선 항목 자체가 사라짐) |
| `trusted ip helper not found` → 컨테이너 종료 | slim 이미지에 `ip` 없음 | `iproute2` 설치 |
| `trusted nft helper not found` | `nft` 없음 | `nftables` 설치 |
| `failed to spawn sandbox entrypoint process: No such file or directory` | 샌드박스가 이미지의 `ENV PATH` 를 쓰지 않는다 | 절대경로(`/app/start.sh`) + env 는 `--env` 로 명시 |
| Postgres `Network is unreachable` | Docker Desktop 호스트 IP = 게이트웨이 주소 → SSRF 보호 | 방식 B |
| `openshell sandbox exec maintq -- …` 가 멈춤 | 이름은 위치 인자가 아니라 `-n` | `-n maintq` |
| `sandbox create --forward … --detach` 명령이 반환하지 않음 | 포워드 프로세스가 셸에 붙어 있다 | 상태는 `openshell sandbox list` · `openshell forward list` 로 따로 확인 |

---

## 7. 확인·미확인 정리

**실측으로 확인됨**
- `inference.local` 은 network_policies 에 적지 않아도 게이트웨이가 가로챈다 (`ALLOWED inference.local:443`)
- 차단 형태: HTTPS 는 프록시 `403 Forbidden`. 로그는 **해석된 실행 파일 경로**(`/usr/local/bin/python3.13` —
  venv 심링크가 아니라 실체)로 찍힌다. 정책 binary 를 쓸 때는 **실체 경로**로 적어야 한다
- `openshell provider create --from-existing` 은 셸 env 의 `NVIDIA_API_KEY` 를 읽었다(provider 에 자격증명 1개 등록 확인)
- 샌드박스 안 S1 최장 턴 22.7s — 추론 라우팅 기본 타임아웃 60s 안이다(로컬에선 48s 턴도 있었다 — 여유가 크지 않다)

**아직 미확인**
- OpenShell 은 **alpha**, WSL2 는 README 에 **experimental** — 버전이 바뀌면 위 절차가 깨질 수 있다
- 샌드박스 **안에서** inference 가 실패할 때의 "폴백 불가" 문구 — 일반 Docker 에서만 확인했다(게이트웨이 설정을 일부러 깨 보지는 않았다)
- 컨테이너 헬스체크가 `unhealthy` 로 뜬다 — 베이스 이미지 `HEALTHCHECK` 가 격리된 네트워크 밖에서 도는 것으로 보이며,
  샌드박스 Phase(`Ready`)·실제 `/health` 응답과는 무관하다(원인 미확인)

---

## 8. Day 2(사업장 온보딩 + 지도) 전에 알아야 할 제약

1. **egress 는 기본 차단이다.** 지도 타일·지오코딩 API 등 새 외부 호출은 전부 `network_policies` 에
   binary+host 단위로 추가해야 하고, **추가한 만큼 데모의 보안 서사가 약해진다.** 서버가 부르는 것만 해당 —
   브라우저(프론트)에서 부르는 지도 SDK 는 샌드박스 정책 대상이 아니다(프론트는 샌드박스 밖)
2. **추론 게이트웨이는 모델 1개**다 — 온보딩 에이전트가 다른 모델(예: 음성·VLM)을 쓰려면 같은 게이트웨이에서
   채팅과 공존할 수 없다. 음성 입력(Day 3)도 같은 제약
3. **임베딩은 샌드박스 안에서 꺼진다**(§5.2) — 온보딩 문서 검색을 dense 로 설계하면 샌드박스에서 동작하지 않는다
4. **파일시스템 정책은 생성 시 고정** — 온보딩이 파일 업로드·저장을 한다면 경로를 미리 `read_write` 에 넣고
   샌드박스를 다시 만들어야 한다. 지금 쓰기 가능한 곳은 `/tmp` 뿐이다
5. **NVIDIA 무료 티어 과부하**(O1) — 라이브 데모 중 스트림 실패가 날 수 있다. 녹화 데모 또는 재시도 정책 필요
6. **nano 계열 모델 ID 함정**(§3) — 경량 모델로 바꿀 때 호출로 먼저 확인
7. **MCP 도구를 늘리면** — 도구가 외부 HTTP 를 부르는 순간 정책 항목이 생긴다. 새 쓰기 도구는 여전히 draft INSERT 만(D10)
8. **Docker Desktop 에서는 호스트 서비스에 못 닿는다**(§5) — 외부 서비스가 필요하면 샌드박스 안에 넣거나
   공인 DNS 이름을 가진 엔드포인트여야 한다. 지오코딩을 로컬 컨테이너로 띄우는 설계는 같은 벽에 부딪힌다
9. **DB 는 빌드 시점 스냅샷** — 온보딩 시드(사업장·지도 좌표)를 바꾸면 덤프 → 이미지 재빌드 → 샌드박스 재생성이 필요하다.
   시드는 실행일 기준 상대일이라 **덤프한 날짜에 고정**된다(데모 날 다시 빌드할 것)
10. **샌드박스는 이미지 `ENV`·`PATH` 를 쓰지 않는다** — 새 env 는 `--env` 로 넘기고 실행 파일은 절대경로로
11. **임베딩 데이터를 뺐다** — 샌드박스 DB 의 `manual_chunks` 는 비어 있다(키워드 검색은 jsonl 을 읽어 영향 없음)

---

## 9. 커밋

| 커밋 | 내용 |
|---|---|
| `5e5e962` | D143 — OpenShell 샌드박스 모드 + 회귀 10건 + D 범위 표기 D1~D143 |
| `b2b4ae0` | `deploy/openshell/` 초안 + 이 문서 초판 |
| (이 커밋) | 방식 B(샌드박스 안 Postgres) · 최종 정책(외부 허용 0건) · Step 3 실측 결과 |
