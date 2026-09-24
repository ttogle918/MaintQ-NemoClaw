# NVIDIA 해커톤 Day 2 — NemoClaw 도입과 게이트웨이 통합 (2026-09-24)

> Day 1 결과는 [`day1.md`](day1.md), 착수 전 조사·미결정은 [`day2-prep.md`](day2-prep.md)(§8 에 결정 완료 표).
> ⚠ 이 문서에도 **이번 세션에서 직접 실행해 확인한 것만** 적는다.

---

## 1. 레포 이관 — `MaintQ-NemoClaw`

- 작업 위치: **WSL Ubuntu `~/MaintQ-NVIDIA`** (Claude Code 도 여기서 돈다)
- 원격: `https://github.com/ttogle918/MaintQ-NemoClaw` — **비공개**, Apache-2.0
- 🔴 **커밋 해시가 전부 바뀌었다 (두 번 재작성).** ㉠ 작성자 이메일 → GitHub noreply(537커밋)
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
- ⚠ **`routed` 는 "게이트웨이 기존 경로 재사용" 이 아니라 Model Router** 다 — 별도 키를 요구한다(실측)

### 🔴 stdio MCP 를 받지 않는다 → D150 의 계기

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

## 5. 🔴 NemoClaw 설치가 기존 게이트웨이를 빼앗는다 — 사고와 복구 절차

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

⚠ **게이트웨이 자격증명 재사용은 첫 onboard 에서는 못 쓴다** —
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
  - ⚠ 첫 시도는 `FailoverError: The AI service is temporarily overloaded` (무료 티어 과부하 O1) — 재시도로 통과
  - ⚠ 우리 8종 중 **제품용은 `safety-guardrail` 하나뿐**이다. 나머지 7종은 Claude Code 개발 워크플로
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
  - ⚠ 재스캔 판정을 한 번 잘못 읽었다 — 결과 키는 `findings` 가 아니라 **`issues`** 다. 빈 키를 읽어
    "3종 모두 0건" 이 나왔다(부재 검사 + liveness 앵커 규칙이 여기에도 적용된다)
- ✅ **OpenClaw workspace + 제품 스킬 `maintq-diagnose` (2026-09-24, 샌드박스 `maintq-agent`)**
  - `deploy/nemoclaw/workspace/build.py` 가 `AGENTS.md`·`TOOLS.md`·`IDENTITY.md` 를 생성한다 — 안전 확정 문구·
    근거 페이지는 `prompts.py` 의 `SAFETY_BASELINE`·`QUALIFIED_WORKER_NOTE` 에서 읽는다(복사 금지, `--check` 로 드리프트 검사).
    **백엔드와 다른 점**: 웹 콘솔은 안전 블록·인용 칩을 시스템(`loop.py`)이 붙이지만 OpenClaw 에는 그 계층이 없어
    에이전트가 확정 문구를 그대로 붙이도록 규칙을 옮겨 적었다. 원본 기본 파일은 배포 전 백업
  - `skills/maintq-diagnose/`: 흐름 A~D(S1·S2·S3·S4) + `evals/evals.json` 4건 + `skill-card.md`(NVIDIA `skill-card-generator`).
    SkillSpector **0점 · 커버리지 100%** — ⚠ 처음엔 0점이었지만 `permissions` 를 맵으로 써서 `manifest_parse_error`
    (커버리지 50%, MCP 분석기 미실행)였다. 표준 `allowed-tools` 리스트로 바꿔 전 분석기가 돈 뒤의 0점이다
  - 도구는 OpenClaw 에서 `maintq__<이름>` 으로 보인다(코어 7종 + prompts/resources 4종)
  - 실행 결과(세션 JSONL 로 도구 호출 확인): S1 1턴 lookup→history→rag→inventory→quotes, 발주 없음, 페이지 202/43/205 전부
    도구 결과에 존재, 안전 문구 원문 그대로 · S1 2턴 `PO-0122` `state=draft` (DB 확인) · S4 `not_found` 전달, 추측 0 ·
    기종 누락 → 도구 호출 전 되물음 · **S2 미실행**
  - 약점: S1 1턴에서 수량을 묻지 않고 1개로 가정해 견적을 냈다(규칙상 수량은 묻는 자리) · `requested_by` 가 NULL —
    MCP-HTTP 경로엔 사람 신원이 없다(데모 전 결정 필요)
  - 스킬 카드 `validate_submission.py` 는 **소유자 VERIFY 표시 1건**으로 FAIL — 사람이 확인하고 지울 항목이라 남겨 둠
- 온보딩 에이전트 런타임 선택(NAT / LangGraph / `loop.py` 확장) — **미결정**
