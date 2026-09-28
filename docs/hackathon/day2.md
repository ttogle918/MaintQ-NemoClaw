# NVIDIA 해커톤 Day 2 — NemoClaw 도입과 게이트웨이 통합 (2026-09-24)

> Day 1 결과는 [`day1.md`](day1.md), 착수 전 조사·미결정은 [`day2-prep.md`](day2-prep.md)(§8 에 결정 완료 표).
> 이 문서에도 **이번 세션에서 직접 실행해 확인한 것만** 적는다.

---

## 1. 레포 이관 — `MaintQ-NemoClaw`

- 작업 위치: **WSL Ubuntu `~/MaintQ-NVIDIA`** (Claude Code 도 여기서 돈다)
- 원격: `https://github.com/ttogle918/MaintQ-NemoClaw` — **비공개**, Apache-2.0
- **커밋 해시가 전부 바뀌었다 (두 번 재작성).** ㉠ 작성자 이메일 → GitHub noreply(537커밋)
  ㉡ D144 매뉴얼 추출물 퍼지. 문서가 인용하는 옛 해시는 조회되지 않는다 —
  대조표 `~/maintq-filter-repo-maps-20260924/commit-map`
- 복구 번들(**매뉴얼 실데이터 포함 — 공개 금지**): `~/maintq-backup-20260924.bundle` ·
  `~/maintq-backup-20260924-prepurge.bundle`

## 2. 결정 — D144~D150

| D | 내용 |
|---|---|
| D144 | 매뉴얼 추출물 비공개 — 실데이터 `.gitignore`, **형태는 `data/extracted/samples/`**, 평가 지표는 `eval/SCOREBOARD.md`(33회) |
| D145 | 새 기종 = **Yaskawa HV600** + 온보딩에 **한국어 정규화** 단계 |
| D146 | 기종 enum **선등록** + "진단 가능" 은 DB 온보딩 상태로 게이트 (절대규칙 4 유지) |
| D147 | 새 기종 안전 문구 = **스테이징 → 사람 승인** (절대규칙 3 유지) |
| D148 | 온보딩 청크는 DB 승격, `rag.py` 가 **jsonl ∪ DB** |
| D149 | 샌드박스 A2A 는 **시도 전 `policy_blocked`**, 차단기 회계 제외 |
| D150 | MCP **streamable-http 입구** 추가 (stdio 유지) — NemoClaw 연동 전제 |

## 3. NemoClaw 는 에이전트가 아니다 (원문 확인)

- **에이전트를 OpenShell 샌드박스에서 돌리는 레퍼런스 스택.** 돌릴 수 있는 에이전트는
  **OpenClaw(기본) · Hermes · LangChain Deep Agents Code** 3종 — **Claude Code 는 목록에 없다**
  (day1 §5 의 "OpenShell 공식 지원 에이전트 … Claude Code" 는 OpenShell 쪽 목록이고 서로 다르다)
- 모델 provider 9종 (NVIDIA Endpoints=`build` · OpenRouter · OpenAI · **Anthropic** · Gemini ·
  Ollama · Model Router=`routed` 등). Anthropic 을 고르면 채점 ①(NVIDIA 기술 활용 심도)에서 손해
- **`routed` 는 "게이트웨이 기존 경로 재사용" 이 아니라 Model Router** 다 — 별도 키를 요구한다(실측)

### stdio MCP 를 받지 않는다 → D150 의 계기

> "Stdio-only MCP servers are not supported. NemoClaw does not start, wrap, or translate them."

managed MCP 는 **HTTPS + 서버당 bearer 1개**가 필수다. 우리 MCP 는 stdio(D15)라 그대로는 못 붙는다.

## 4. HTTPS 다리 — `openshell service expose` (실측)

게이트웨이는 **같은 포트에서 평문 HTTP 와 mTLS HTTPS 를 둘 다** 서빙한다:

```
openshell service expose maintq 8000 maintq-api
  → http://default--maintq--maintq-api.openshell.localhost:<port>/     200 (인증 없음)
  → https://(같은 URL)                                                  200 (mTLS 필요)
```

- 인증서: `~/.config/openshell/gateways/<gw>/mtls/{ca.crt,tls.crt,tls.key}` · issuer `CN=openshell-ca`
- 없이 호출하면 TLS 핸드셰이크 중 `certificate required` 로 끊긴다(`-k` 로도 안 된다 — CA 문제가 아니라 **클라이언트 인증서** 문제다)

## 5. NemoClaw 설치가 기존 게이트웨이를 빼앗는다 — 사고와 복구 절차

**증상** (이번 세션에서 **세 번** 겪었다)
- 설치/`onboard` 가 자기 게이트웨이(`nemoclaw`, **8080**)를 systemd 유저 서비스로 띄우고
  **Day 1 게이트웨이(`openshell`, 17670)를 내린다.** 실행 중이던 샌드박스는 **SIGKILL**(`Exited 137`)
- `openshell sandbox list` 가 `No sandboxes found` 로 보이는 건 **활성 게이트웨이가 바뀌었기 때문**이지
  샌드박스가 지워진 게 아니다 — `openshell gateway list` 로 먼저 확인할 것
- `nemoclaw onboard --fresh` 는 **`~/.config/openshell/gateway.env` 를 자기 소유로 되돌린다**
  (`OPENSHELL_DB_URL` 을 자기 DB 로). env 를 고쳐도 다음 onboard 에서 다시 덮인다

**원인**

```
systemd:  openshell-gateway.service
          StateDirectory=openshell/gateway      ← KEK(자격증명 복호화 키)는 여기 고정
          EnvironmentFile=~/.config/openshell/gateway.env
gateway.env:  OPENSHELL_DB_URL=sqlite:~/.local/state/nemoclaw/openshell-docker-gateway/openshell.db
              ↑ NemoClaw 가 소유. 옛 DB(~/.local/state/openshell/gateway/openshell.db)에 provider 가 남아 있다
```

**복구 — 키 재입력 없이 되는 방법** (env 를 고치지 말고 **DB 파일을 옮긴다**)

```bash
systemctl --user stop openshell-gateway.service
cp ~/.local/state/nemoclaw/openshell-docker-gateway/openshell.db ~/nemoclaw-gw.db.bak   # 먼저 백업
cp ~/.local/state/openshell/gateway/openshell.db \
   ~/.local/state/nemoclaw/openshell-docker-gateway/openshell.db                        # 이식
systemctl --user start openshell-gateway.service
openshell provider list && openshell inference get                                      # nvidia-prod · Nemotron 확인
```

KEK 이 `StateDirectory`(위치 불변)에 있어서 **암호화된 자격증명이 그대로 복호화된다.** 이게 요점이다.

**샌드박스 재생성** — `day1.md` §6 의 create 명령 그대로. `Ready` 까지 20~30초.

**백업 목록**: `~/openshell-state-backup-20260924.tgz`(12MB, 설치 전 전체) ·
`~/gateway.env.bak-20260924` · `~/openshell-gw.db.bak-20260924` · `~/nemoclaw-gw.db.bak*-20260924`

## 6. 키 — `NVIDIA_API_KEY` 와 `NVIDIA_INFERENCE_API_KEY` 는 **같은 키다**

`dist/lib/inference/nim.js` 주석: *"explicit arg wins, then `NGC_API_KEY`, then
`NVIDIA_INFERENCE_API_KEY`, then the **legacy `NVIDIA_API_KEY` alias**"* ·
`dist/lib/validation.js` 는 둘을 같은 "NVIDIA API Key" 로 취급한다.
build.nvidia.com 의 `nvapi-` 키 하나이고 **변수 이름만 맥락마다 다르다.**
게이트웨이 저장분도 `Credential keys: NVIDIA_API_KEY` 다. 우리 `.env` 에도 같은 키가 있다(임베딩용, day1 §3).

**게이트웨이 자격증명 재사용은 첫 onboard 에서는 못 쓴다** —
`dist/lib/onboard/build-credential-reuse.js`: *"only the recovered-sandbox path (for example
`onboard --recreate-sandbox`) may rely on the existing gateway credential. Explicit
non-interactive provider selections still require a local key."* 등록된 샌드박스가 생긴 **두 번째부터** 열린다.

## 7. 설치 함정

| 증상 | 원인 | 해결 |
|---|---|---|
| provider 가 `install-ollama` 로 자동 선택 → zstd 없어 중단 | 파이프(`curl \| bash`)면 stdin 이 TTY 가 아니라 **자동 non-interactive** + 키가 env 에 없으면 Ollama 가 기본값 | `NEMOCLAW_PROVIDER=build` + 키를 env 로 |
| `onboard --fresh` 가 exit 0 인데 아무것도 안 됨 | `routed`(Model Router) 선택인데 키가 없어 [3/8]에서 중단 | provider 를 `build` 로, 키를 넘긴다 |
| `Existing OpenShell Docker-driver gateway is stale (executable=/usr/bin/… expected ~/.local/bin/…)` | NemoClaw 는 **자기 바이너리**(`~/.local/bin/openshell-gateway`)로 게이트웨이를 재생성한다 | 불가피 — 재생성 후 샌드박스 다시 만든다 |
| `bash -c` 안에서 `pkill -f <패턴>` 이 exit 15 | 패턴이 자기 자신에 매치 | `pgrep -af … \| grep -v 'bash -c'` 로 거른다 |

## 8. 남은 것

- ~~NemoClaw 가 게이트웨이 자체 CA 를 신뢰하는가~~ → **D151 로 해소** — managed MCP 경로는 불가,
  호스트 loopback + 커스텀 egress 정책으로 연결 완료
- ✅ **OpenClaw 가 우리 `SKILL.md` 를 읽는다** (2026-09-24 실측, 샌드박스 `maintq-agent`)
  - 형식 변경 불필요 — 8종 전부 표준(`name` 소문자·하이픈·디렉터리명 일치, `description` ≤1024자)
  - `nemoclaw maintq-agent skill install .claude/skills/safety-guardrail` → `Validated SKILL.md` →
    `/sandbox/.openclaw/workspace/skills/` 설치, `skill list` 에 `✓ ready · openclaw-workspace` (15→16 ready)
  - 명시 질의: 규칙 1번을 **원문 그대로** 인용
  - 암묵 적용: 스킬 이름 없이 "iG5A 커버 열고 커패시터 점검 안전 주의" → "10분 이상 + 테스터 방전 확인 ·
    5분 등 단축 금지 · iG5A p.4/p.6 · S100 p.2 (D26)" — 전부 `SKILL.md:17-19` 에 있는 값이다
  - 첫 시도는 `FailoverError: The AI service is temporarily overloaded` (무료 티어 과부하 O1) — 재시도로 통과
  - 우리 8종 중 **제품용은 `safety-guardrail` 하나뿐**이다. 나머지 7종은 Claude Code 개발 워크플로
    (`/sprint`·`/stage` 등 — 서브에이전트·레포 명령 전제)라 OpenClaw 에 넣을 대상이 아니다
- ✅ **스킬 공급망 게이트 — SkillSpector (2026-09-24, `skillspector:local`, `--no-llm`)**
  - NVIDIA 카탈로그 2종을 **설치 전** 스캔: `skill-card-generator` AE1 HIGH ×5 — 전부 "번들 스크립트 실행"
    서술. 스크립트 3개를 직접 읽음: 네트워크 0 · subprocess 는 `git describe/log/remote`(읽기) 뿐 ·
    `.env`·키 파일은 명시적 제외 목록 → **수용**. `nemoclaw-user-guide` EA2 MEDIUM ×1 — "비밀값을
    요청하지 말라" 는 **방어 문구**에 걸린 오탐 → **수용**. 사람이 `.claude/skills/` 에 설치
    (NVIDIA 서명 스킬도 정적 스캔은 HIGH 를 낸다 — 판정은 사람이 근거를 읽고 한다)
  - 우리 스킬 3건: `run-eval` 15→**0** (스킬이 셸로 비밀 파일을 읽던 줄 제거 — `run_eval.py:94` 가
    backend import 전에 `load_dotenv(override=False)` 로 이미 읽는다) · `stage` 10→**0**
    (`npx tsc` → `./node_modules/.bin/tsc`. 이 WSL 클론엔 `node_modules` 가 없어 옛 명령은 **실제로**
    npm 의 동명 `tsc` 패키지를 받아 올 상태였다) · `done` 21 그대로 — AS1 은 `reviewer.md` 의 D 범위를
    읽는 정당한 접근이라 **수용된 위험**
  - 재스캔 판정을 한 번 잘못 읽었다 — 결과 키는 `findings` 가 아니라 **`issues`** 다. 빈 키를 읽어
    "3종 모두 0건" 이 나왔다(부재 검사 + liveness 앵커 규칙이 여기에도 적용된다)
- ✅ **OpenClaw workspace + 제품 스킬 `maintq-diagnose` (2026-09-24, 샌드박스 `maintq-agent`)**
  - `deploy/nemoclaw/workspace/build.py` 가 `AGENTS.md`·`TOOLS.md`·`IDENTITY.md` 를 생성한다 — 안전 확정 문구·
    근거 페이지는 `prompts.py` 의 `SAFETY_BASELINE`·`QUALIFIED_WORKER_NOTE` 에서 읽는다(복사 금지, `--check` 로 드리프트 검사).
    **백엔드와 다른 점**: 웹 콘솔은 안전 블록·인용 칩을 시스템(`loop.py`)이 붙이지만 OpenClaw 에는 그 계층이 없어
    에이전트가 확정 문구를 그대로 붙이도록 규칙을 옮겨 적었다. 원본 기본 파일은 배포 전 백업
  - `skills/maintq-diagnose/`: 흐름 A~D(S1·S2·S3·S4) + `evals/evals.json` 4건 + `skill-card.md`(NVIDIA `skill-card-generator`).
    SkillSpector **0점 · 커버리지 100%** — 처음엔 0점이었지만 `permissions` 를 맵으로 써서 `manifest_parse_error`
    (커버리지 50%, MCP 분석기 미실행)였다. 표준 `allowed-tools` 리스트로 바꿔 전 분석기가 돈 뒤의 0점이다
  - 도구는 OpenClaw 에서 `maintq__<이름>` 으로 보인다(코어 7종 + prompts/resources 4종)
  - 실행 결과(세션 JSONL 로 도구 호출 확인): S1 1턴 lookup→history→rag→inventory→quotes, 발주 없음, 페이지 202/43/205 전부
    도구 결과에 존재, 안전 문구 원문 그대로 · S1 2턴 `PO-0122` `state=draft` (DB 확인) · S4 `not_found` 전달, 추측 0 ·
    기종 누락 → 도구 호출 전 되물음 · **S2 미실행**
  - 약점: S1 1턴에서 수량을 묻지 않고 1개로 가정해 견적을 냈다(규칙상 수량은 묻는 자리) · `requested_by` 가 NULL —
    MCP-HTTP 경로엔 사람 신원이 없다(데모 전 결정 필요)
  - 스킬 카드 `validate_submission.py` 는 **소유자 VERIFY 표시 1건**으로 FAIL — 사람이 확인하고 지울 항목이라 남겨 둠
- 온보딩 에이전트 런타임 선택(NAT / LangGraph / `loop.py` 확장) — **미결정** →
  **D153 으로 NAT 결정, 미확인 3건은 아래 §9 에서 확인 완료**

## 9. NAT 스파이크 결과 (2026-09-24, MQ-1901 — D153 미확인 3건)

재현 명령: `onboarding/nat/spike/README.md`. `cd onboarding/nat && uv run nat --version` →
`nat, version 1.9.0`(nvidia-nat==1.9.0 + nvidia-nat-mcp==1.9.0, 레포 본 프로젝트와 분리된
uv 프로젝트).

| 항목 | 판정 | 근거 |
|---|---|---|
| ⓘ 헤더(`Authorization`·`X-User`) 도달 | **확인** | echo 서버(127.0.0.1:8799) 로그에 `authorization: Bearer nat-spike-token` · `x-user: nat-onboarding` 둘 다 기록. 실 MCP(스파이크 전용 127.0.0.1:8775, core 프로필) 왕복: `lookup_error_code(model=iG5A, code=OHt)` → `manual_page=202`·`error_name=냉각핀 과열`(D151 과 동일 기대값, 환각 아님) |
| ⓘⓘ 샌드박스 추론 — 키 없이 `inference.local` | **확인** | 샌드박스 `maintq-nat`(BYOC, `deploy/openshell/Dockerfile.nat` 빌드) 안에서 더미 키로 `https://inference.local/v1/chat/completions` 호출 — 로그 `ALLOWED inference.local:443` + `routing proxy inference request … endpoint=https://integrate.api.nvidia.com/v1`. 1회차 `503 Service temporarily overloaded`(day2 §8 의 O1 과 같은 무료 티어 과부하) → 재시도 3회 전부 `200`(재시도로 통과 사실 기록) |
| ⓘⓘ 샌드박스 추론 — MCP(`host.openshell.internal`) | **확인** | 같은 샌드박스에서 `mcp_client_check.py real http://host.openshell.internal:8775/mcp <토큰>` → `lookup_error_code` 정상 응답(위와 동일 payload). 정책 로그 `HTTP:POST … ALLOWED … [policy:maintq_mcp_spike engine:l7]` + `engine:opa` 둘 다 통과 |
| ⓘⓘⓘ NAT 가 `SKILL.md` 를 런타임에 읽는가 | **불가** | `grep -rln "SKILL.md" onboarding/nat/.venv/lib/python3.13/site-packages/nat*` → 0건(스캔 대상 504개 `.py` 파일, liveness 앵커로 스캐너 생존 확인). NAT 패키지 안에 NVIDIA 스킬 규격(`SKILL.md`) 로더가 없다 — OpenClaw 와 다른 지점 |

**채택 레벨: L0 (샌드박스 안 NAT + streamable-http 헤더 + `inference.local`, 목표 그대로).**
ⓘ·ⓘⓘ 가 둘 다 확인돼 폴백(L1/L2)으로 물러날 필요가 없었다. ⓘⓘⓘ 만 「불가」이고, 이는
애초에 폴백 사다리가 아니라 별도 분기(SKILL.md 생성 방식, MQ-1908 이 이어받음)로 처리하게
설계돼 있었다 — L0 채택에 영향 없음.

**엔지니어링 메모 (재현 시 참고)**:
- `nat mcp client tool call` CLI 는 `custom_headers`(X-User 등)를 지원하지 않는다
  (`--bearer-token` 만) — 그래서 `WorkflowBuilder.add_function_group()` 을 코드로 직접
  호출해 `MCPClientConfig`(streamable-http + `custom_headers`)를 검증했다. 이것이
  워크플로 YAML 이 내부적으로 거치는 것과 같은 코드 경로다.
- `mcp_client` 는 `functions:` 가 아니라 **`function_groups:`** 최상위 키에 둔다
  (`nat/data_models/config.py:281` — `register_function_group()` 으로 등록된 컴포넌트).
- 함수 그룹의 도구를 전역 함수 레지스트리에 편입해 다른 컴포넌트가 참조하려면
  `include: [<tool_name>]` 를 명시해야 한다(`get_included_functions()` 는 `include` 가
  비어 있으면 빈 dict 를 돌려준다 — 실측으로 드러남).
- `openshell sandbox exec` 는 `-n/--name` 플래그가 필요하다(위치 인자 아님) ·
  `sandbox upload` 는 `<NAME> <LOCAL> [DEST]` 위치 인자다(`-n` 플래그 없음) · 정책의
  `filesystem_policy.read_only`(`/app`) 때문에 빌드 후 파일을 얹으려면 `/tmp` 로 올려야
  한다.

**사고 기록 — 운영 중이던 MCP-HTTP(127.0.0.1:8765, `maintq-agent`용) 를 실수로 내렸다
(발견 즉시 오케스트레이터가 복구, pid 40032 → 52442).**
스파이크 서버를 정리하며 `pkill -f "mcp_server.http_entry"` 를 썼는데, 운영 서버와 스파이크
서버(127.0.0.1:8775, 이 스파이크 전용)가 **같은 모듈 문자열**(`mcp_server.http_entry`)로
떠 있어 패턴이 둘 다 잡았다. 이 세션이 정확히 같은 커맨드라인으로 재기동을 시도했으나
샌드박스 권한 정책(auto-mode 분류기)이 "Interfere With Workloads" 로 재기동 자체를 막아
직접 복구하지 못했고, 오케스트레이터가 대신 재기동해 확인했다(새 pid 52442).

재발 방지: 앞으로 스파이크용 MCP 서버는 `pkill -f`(패턴 매치) 대신 **PID 를 직접 기록해
`kill <pid>`** 로 종료할 것 — 운영 프로세스와 모듈 이름이 같은 이상 패턴 매치는 원리적으로
구분하지 못한다. **PID 를 기억하지 못하면 이름으로 죽이지 말고 사람/오케스트레이터에게
넘길 것** — 이번처럼 자기 복구 시도가 권한 게이트에 막히는 경우 공백 시간이 생긴다.

## 10. 데모 시나리오 (MQ-1912 — 초안, 2026-09-25)

> 흐름: HV600 코드를 모름 → NAT 가 한국어로 정규화 → 사람이 검수·승격 → 진단할 수 있게 됨 → 안전 문구도 사람이 승인해야 붙음.
> **아직 실행하지 않은 단계에는 결과를 적지 않는다.** 사람 작업 H2(검수)·H3(승격)·H4(안전 승인)·H5(워크스페이스 재설치)·
> H7(녹화)을 아직 하지 않았다. 이 초안을 쓸 때(2026-09-25) 공유 DB 상태: `error_codes` 70행(HV600 0) · `onboarding_promotions` 0 ·
> 안전 후보 `approved` 0 · HV600 정규화 249/249(최신 기준 high 248 · low 1).
> 매뉴얼 원문·번역문은 여기 옮기지 않는다(D144) — 코드·상태·페이지 번호·건수만 적는다.

**실행 레벨** — `L0`·`L1`·`L2` 는 §9 의 NAT 폴백 사다리다(L0 = 샌드박스 안 NAT + `inference.local` · L1 = 호스트 NAT ·
L2 = 호스트 stdio). NAT 를 거치지 않는 단계는 `—` 로 두고 **어디서 돌렸는지**를 따로 적는다.

| # | 단계 | 실행 레벨 | 상태 | 근거 |
|---|---|---|---|---|
| ① | 승격 전: OpenClaw 에 "HV600 GF 떴어" → `not_found` → 흐름 D(A/S 안내, S4) | — | **도구 단위만 확인** · OpenClaw 대화 **미실행(H5 후)** | 아래 ① |
| ② | NAT 한국어 정규화 | **L0** | 실행 완료 | Stage 3 MQ-1908 |
| ③ | 사람 검수·승격(화면 `/manager/onboarding` 또는 curl) | — | **미실행(H2/H3)** | — |
| ④ | 승격 후 같은 질문 → 한국어 정의 + 원문 페이지 | — | **미실행(H3 후)** | — |
| ⑤ | 위험 절차 질문 → 승인 전 차단 → 안전 승인 → 워크스페이스 재생성 → 안전 문구 동반 | — | 백엔드 게이트는 스파이크로 확인 · 실데이터·OpenClaw **미실행(H4/H5 후)** | 아래 ⑤ |
| ⑥ | ~~샌드박스 A2A 발신 → `policy_blocked` trace~~ **데모 제외(2026-09-25)** | — | 확인됨 (Stage 2) · 녹화 안 함 | 아래 ⑥ |
| ⑦ | 주입 픽스처 회귀 | **L1** | 확인됨 (Stage 3) — 게이트 5/5 | 아래 ⑦ |

### ① 승격 전 `not_found`

- **확인한 것** (2026-09-25, 호스트에서 도구 함수를 직접 호출, 공유 DB): `lookup_error_code(model="HV600", code="GF")` →
  `status=not_found`(`manual_page`·`error_name` 없음). liveness 앵커 — 같은 실행에서 `lookup_error_code(model="iG5A", code="OHt")` →
  `ok` · `manual_page=202` · `냉각핀 과열`(카탈로그가 비어서 not_found 가 난 게 아님). 격리 스키마 회귀는 `spikes/model_enum_contract.py` ⑤
- **확인 안 한 것**: OpenClaw 대화. 샌드박스 `maintq-agent` 의 워크스페이스·스킬이 아직 HV600 이전 판이라(아래 `build.py --check`)
  지금 물으면 옛 규칙 3(기종 3종)으로 답한다
- **녹화 순서 주의**: 표 H5 는 "H3·H4 뒤" 이지만, ①을 OpenClaw 로 녹화하려면 **H3(GF 승격) 전에** 현재 판 워크스페이스·스킬을
  한 번 설치해야 한다. GF 를 승격한 뒤에는 ①을 재현할 수 없다(승격 취소 API 없음, H10). 선택지는 두 가지 — ㉠ H3 전에 한 번 설치하고
  H4 뒤에 한 번 더 설치 ㉡ ①에는 승격 대상이 아닌 코드를 쓴다 → **㉠ 채택(2026-09-25 사용자 결정)** — 같은 GF 로 승격 전·후를 보인다

### ② NAT 정규화 — L0

Stage 3 MQ-1908 에서 샌드박스 안 NAT 로 batch 1 을 **249/249** 정규화했다(2,588초). low 13 중 첫 프롬프트의 주입 과탐 11행과 CPF06 을
`--renormalize-rows` 로 다시 돌려(L0) 12/12 high → 최신 기준 **high 248 · low 1**(oL1 `untranslated_term`).
재현 명령은 `onboarding/nat/README.md`. 데모에서는 녹화본을 쓰거나(전량 43분) `--codes GF,OC,OV,UV1,OH,CPF06,EF1,CE` 로 데모 코드만 돌린다.

### ③·④ 승격과 승격 후 조회 — 미실행

H2(데모 코드 원문 대조) → H3(승격, `flags` 확인 체크 포함)을 사람이 한 뒤에 채운다. ④에서 볼 것:
`lookup_error_code(HV600, GF)` 가 `ok` 이고 인용 페이지가 도구 결과의 `manual_page` 값뿐인지(세션 JSONL 로 도구 호출 확인 — §8 선례).
스킬 평가 문항: `skills/maintq-diagnose/evals/evals.json` 의 `hv600-pre-promotion-001` · `hv600-post-promotion-001`.

### ⑤ 안전 문구 — 백엔드는 확인, OpenClaw 는 미실행

- **웹 콘솔 경로(백엔드 `loop.py`)**: `spikes/onboarding_safety_gate.py`(22건, Stage 3 MQ-1910, 격리 스키마 + 가짜 LLM)가
  승인 전 차단(안전 블록 없음 · 절차 문장 없음 · "근거 문서를 확인하지 못해" 안내 있음) · 승인 후 승인 문안 그대로 블록 ·
  승인 행 2건이면 차단 · iG5A 출력 바이트 동일을 확인했다. **실데이터 HV600 승인은 아직 0건**(H4)
- **OpenClaw 경로**: `build.py` 가 DB 승인 상태를 AGENTS.md 「온보딩 승인 기종」 절에 쓴다. 지금은 `onboarding_HV600=none` — 승인 후
  재생성·재설치(H5)하기 전까지는 AGENTS.md 에 HV600 안전 문구가 없다
- **한계**: OpenClaw 에는 `loop.py` 의 안전 게이트 계층이 없다. HV600 안전은 **에이전트가 AGENTS.md 규칙을 지키는지에 달려 있다**
  (§8 "백엔드와 다른 점" 과 같은 구조). 시스템이 강제하는 것은 웹 콘솔 경로뿐이다

### ⑥ 샌드박스 A2A `policy_blocked` — Stage 2 확인분

> ⏸ **데모에서 제외(2026-09-25 사용자 결정)** — A2A 는 이 레포에서 더 신경 쓰지 않는다. 구현(D149)과 회귀는 그대로 두고,
> 녹화 시나리오에서는 ⑥을 뺀다. 외부 연동을 보여 줄 필요가 생기면 A2A 대신 **카카오톡 알림 같은 MCP 연동**으로 한다(07_BACKLOG 참고).


- `MAINTQ_SANDBOX` 가 켜져 있으면 A2A 발신을 **시도하기 전에** 막는다(D149) — 라우터 HTTP 503 · `detail.reason="policy_blocked"` ·
  trace `status="policy_blocked"` · 차단기 카운터 불변. 근거: Stage 2 MQ-1907 pytest(`backend/routers/test_a2a.py`·
  `backend/a2a/test_client.py`·`backend/services/test_po_a2a_dispatch.py`, 격리 스키마)
- Stage 2 브라우저 검증에서 `/manager/a2a` 이력에 `policy_blocked` 행이 보였다. 다만 라벨이 없어 원문 그대로 `unknown` 톤으로 나왔다 →
  라벨·톤은 MQ-1911 이 추가한다. 데모 전에 이 화면을 다시 확인할 것
- 이 표에 적은 것은 위 두 가지뿐이다. OpenShell 샌드박스 안의 웹 콘솔에서 실제로 발신해 본 결과는 아니다

### ⑦ 주입 픽스처 — L1, 게이트 5/5

`onboarding/nat/run_injection_check.py`(격리 스키마, **합성** 픽스처 `fixtures/injection_candidates.json`)가 Stage 3 에서 5/5 통과했다.
실데이터 249행에서는 첫 프롬프트가 주입 의심을 11행 과탐했는데, 원문 `source_flags` 는 0이었다. 재정규화 뒤 주입 표시는 0이다(②).
`maintq-manual-onboarding` SkillSpector HIGH 1건(evals 의 합성 주입 문장)을 받아들일지는 사람이 판정한다(H6).

### 이 초안을 쓸 때 실측한 것 (2026-09-25)

- `DATABASE_URL=… uv run python deploy/nemoclaw/workspace/build.py --check` →
  `checked=3 stale=['AGENTS.md'] safety_text_embedded=True onboarding_HV600=none` (exit 1). Stage 3 에서 AGENTS.md 생성 문구(HV600 게이트·
  "10분 이상" 적용 범위)를 고쳤으니 **의도된 드리프트**다. `out/` 재생성과 샌드박스 재설치는 H5(사람)의 일이다.
  재생성 전에 Stage 3 기록의 "적용 범위 문장 변경 — H5 전 사람 확인" 을 먼저 처리한다
- SkillSpector `maintq-diagnose` 재스캔(`skillspector:local`, `--no-llm`, 스킬 사본을 스캔) → `risk_assessment.score=0` · `SAFE` ·
  `issues` 0 · suppressed 0 · 커버리지 100%(3/3 파일). 이전과 같은 0점이다
- 수동 체크리스트 H5~H7: **미수행**
