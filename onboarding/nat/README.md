# MaintQ 온보딩 — NAT 한국어 정규화 (MQ-1908, D153)

결과 서술은 보고·`docs/hackathon/day2.md`(MQ-1912 소유). 이 문서는 **재현 명령만** 적는다.

| 파일 | 역할 |
|---|---|
| `../../skills/maintq-manual-onboarding/SKILL.md` | 정규화 규칙의 **단일 원천** |
| `glossary.json` | 번역어 용어집(기존 `error_codes` 한국어 이름과 맞춤) |
| `build_prompt.py` | SKILL.md 본문 + 용어집 → `out/system_prompt.md`(gitignore) · `--check` 드리프트 검사 |
| `workflow.yml` | NAT 워크플로 — NIM LLM + `mcp_client`(streamable-http, `Authorization`·`X-User`) + `tool_calling_agent` |
| `maintq_nat/guarded_stage.py` | 에이전트에게 주는 `stage_code_normalization` — 페이지 밖 행·중복 저장·행당 3회 이상 거부 |
| `run_normalize.py` | 드라이버 — `list_onboarding_rows` 커서 순회(결정적) + 페이지당 NAT 1회 |
| `run_injection_check.py` · `fixtures/injection_candidates.json` | 주입 회귀(격리 스키마, 합성 픽스처) |

## 준비

```bash
cd onboarding/nat && uv sync && cd -          # nvidia-nat 1.9.0 + nvidia-nat-mcp + nvidia-nat-langchain[nvidia]
uv run python onboarding/nat/build_prompt.py  # out/system_prompt.md 생성 (--check 로 검사)
```

## MCP-HTTP #2 (onboarding 프로필, 데모 토폴로지 §3)

```bash
DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" MAINTQ_TOOLS_PROFILE=onboarding \
  MAINTQ_MCP_HTTP_PORT=8766 MAINTQ_MCP_TOKEN=<#1 과 다른 토큰> MAINTQ_MCP_ALLOWED_HOSTS=host.openshell.internal \
  .venv/bin/python -m mcp_server.http_entry &
echo $!   # 끌 때는 이 PID 로만 kill (패턴 kill 금지 — day2 §9 사고)
```

## L0 — 샌드박스 안 실행

```bash
docker build -f deploy/openshell/Dockerfile.nat -t maintq-nat:mq1908 .
openshell sandbox create --name maintq-nat --from maintq-nat:mq1908 \
  --policy deploy/openshell/policy-nat.yaml --detach -- /usr/bin/sleep infinity
# /app 은 읽기 전용 — 워크플로 묶음을 /tmp 로 올린다(onboarding/nat 의 .venv 제외 + skills/maintq-manual-onboarding)
openshell sandbox upload maintq-nat <묶음 디렉터리 mq> /tmp/mq
printf '%s\n' "$TOKEN" | openshell sandbox exec -n maintq-nat --workdir /tmp/mq/mq --env MAINTQ_SANDBOX=openshell -- \
  /app/onboarding/nat/.venv/bin/python /tmp/mq/mq/onboarding/nat/run_normalize.py --token-stdin \
  --batch-id 1 --codes GF,OC,OV,UV1,OH,CPF06,EF1,CE
```

- 토큰은 **stdin** 으로 넘긴다(`--env`·argv 에 싣지 않는다 — openshell 도 `--env` 에 비밀 금지).
- `openshell sandbox exec` 은 이미지 `ENV` 를 넘기지 않는다 → `--env MAINTQ_SANDBOX=openshell` 필수
  (없으면 드라이버가 호스트(L1)로 판단하고 `.env` 키를 찾다 실패한다).
- 셸에서 stdin 을 주지 않는 `exec` 은 `</dev/null` 을 붙인다(안 붙이면 멈춘 채 기다린다).
- ⚠ 실행 stderr 에 매뉴얼 원문이 찍힌다 — **`2>` 로 파일에 리다이렉트하지 말 것**(D144 — 원문·번역문을 산출물로 남기지 않는다).

## L1 — 호스트 실행

```bash
MAINTQ_NAT_MCP_TOKEN=<토큰> uv run python onboarding/nat/run_normalize.py --batch-id 1
```

LLM 은 build.nvidia.com(`NVIDIA_API_KEY`, env 또는 `.env`), MCP 는 `http://127.0.0.1:8766/mcp`.

## 주입 회귀

```bash
DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" uv run python onboarding/nat/run_injection_check.py [--show]
```
