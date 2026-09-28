# NAT 스파이크 재현 절차 (MQ-1901, D153 미확인 3건)

결과 서술·판정표는 `docs/hackathon/day2.md §9`. 이 문서는 **재현 명령만** 적는다.

## 0. 준비 — 별도 uv 프로젝트

```bash
cd onboarding/nat
uv sync
uv run nat --version   # 1.9.0 이어야 한다
```

레포 본 프로젝트(`pyproject.toml`/`uv.lock`)와 완전히 분리된 프로젝트다 — 여기서 만든
`.venv`/`uv.lock` 은 `onboarding/nat/` 안에만 있다.

## ⓘ 헤더 도달 — echo 서버

```bash
# 터미널 A
uv run python spike/header_echo.py 8799

# 터미널 B
uv run python spike/mcp_client_check.py echo http://127.0.0.1:8799/mcp
```

터미널 A 로그에 `authorization: Bearer nat-spike-token` · `x-user: nat-onboarding` 이
둘 다 찍히면 확인. (echo 서버는 진짜 MCP 응답을 못 주므로 클라이언트 쪽은 타임아웃하는
게 정상 — `mcp_client_check.py` 가 15초 타임아웃으로 잡아 종료코드 0 을 낸다.)

## ⓘ 헤더 도달 — 실제 MCP 왕복 (`lookup_error_code`)

호스트에서 **스파이크 전용 포트·토큰**으로 core 프로필 MCP 를 띄운다(운영 중인
127.0.0.1:8765 는 건드리지 않는다):

```bash
cd /path/to/MaintQ-NVIDIA   # 레포 루트
DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" \
  MAINTQ_MCP_TOKEN=<스파이크 전용 토큰> MAINTQ_MCP_HTTP_PORT=8775 MAINTQ_TOOLS_PROFILE=core \
  uv run python -m mcp_server.http_entry
```

```bash
cd onboarding/nat
uv run python spike/mcp_client_check.py real http://127.0.0.1:8775/mcp <스파이크 전용 토큰>
```

`[도구 호출 결과] lookup_error_code -> '{"status": "ok", ..., "manual_page": 202, ...}'`
가 나오면 확인(D151 과 같은 기대값).

`nat mcp client tool call` **CLI 는 쓰지 않았다** — `--bearer-token` 만 있고
`custom_headers`(X-User 등 임의 헤더)를 받지 않는다. 대신 `nvidia-nat-mcp` 가 워크플로
YAML 을 해석할 때 내부적으로 호출하는 것과 **같은 코드 경로**
(`WorkflowBuilder.add_function_group()` → `MCPClientConfig` → `MCPStreamableHTTPClient`)
를 `mcp_client_check.py` 에서 코드로 직접 구성해 썼다 — LLM 에이전트 단계 없이 연결성만
검증한다. `spike/config_http.yml` 은 같은 스키마를 **워크플로 YAML 형태**로 문서화한
것이다(`nat validate --config_file spike/config_http.yml` 로 스키마 자체는 검증됨,
`workflow:` 항목은 별도 에이전트 패키지가 없어 주석 처리).

## ⓘⓘ 샌드박스 추론 (OpenShell BYOC)

```bash
# 레포 루트에서 이미지 빌드
docker build -f deploy/openshell/Dockerfile.nat -t maintq-nat:spike .

# 샌드박스 생성 (이름 maintq-nat — 기존 maintq/maintq-agent 는 그대로 둔다)
openshell sandbox create --name maintq-nat --from maintq-nat:spike \
  --policy deploy/openshell/policy-nat.yaml --detach -- /usr/bin/sleep infinity

# 스파이크 스크립트는 /app 이 read-only 라 /tmp 에 올린다
openshell sandbox upload maintq-nat spike /tmp/spike

# 추론 (키 없이 — 게이트웨이가 주입)
openshell sandbox exec -n maintq-nat -- /app/onboarding/nat/.venv/bin/python -c \
  "import httpx; r = httpx.post('https://inference.local/v1/chat/completions', json={'model':'nvidia/nemotron-3-super-120b-a12b','messages':[{'role':'user','content':'ping'}],'max_tokens':10}, headers={'Authorization':'Bearer dummy'}, timeout=30, verify=False); print(r.status_code, r.text[:200])"

# MCP (호스트 8775 스파이크 서버로 — policy-nat.yaml 이 이 포트만 연다)
openshell sandbox exec -n maintq-nat -- /app/onboarding/nat/.venv/bin/python \
  /tmp/spike/mcp_client_check.py real http://host.openshell.internal:8775/mcp <토큰>

openshell logs maintq-nat --source sandbox   # ALLOWED inference.local:443 / HTTP:POST ALLOWED 확인

# 정리
openshell sandbox delete maintq-nat
```

## ⓘⓘⓘ SKILL.md 로딩

```bash
grep -rn "SKILL.md" onboarding/nat/.venv/lib/python3.13/site-packages/nat*
```

0건이면 「불가」— NAT 는 자체 `SKILL.md` 로더가 없다(OpenClaw 와 달리 NVIDIA 스킬 규격을
런타임에 읽는 코드가 패키지 안에 없음, 504개 `.py` 파일 스캔 기준).
