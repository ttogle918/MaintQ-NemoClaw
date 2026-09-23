# NVIDIA 해커톤 Day 2 준비 — 조사 결과와 미결정 사항 (2026-09-24)

> 새 레포(해커톤 제출용)로 옮기기 직전에 남긴 인수인계 문서. Day 1 결과는 [`day1.md`](day1.md).
> 여기 적힌 것은 **이번 세션에서 실측·원문 확인한 것**이고, 확인 못 한 것은 「미확인」으로 표시했다.

---

## 1. 대회 요건 (사용자 전달 원문 요약)

- 교육 미션: **Securing Agents with NemoClaw and OpenShell**
- 개발 방식: **build.nvidia.com 을 통해 Skill API 활용**하여 데모 프로젝트를 직접 개발
- 채점: ① NVIDIA Agent 기술 활용 심도 ② 실용성·산업가치·혁신성 ③ 완성도 ④ 커스터마이징·독창성
- 활용 도구: Nemotron · NIM · NVIDIA (NeMo) Agent Toolkit · Agent Skills · SkillSpector · OpenShell(NemoClaw)
- 전제 조건(필수 아님으로 보임): NeMo Framework 또는 NeMo Microservices 활용
- 제출: **재현 가능한 코드 + 작동하는 데모** → 코드 공개 전제로 **새 레포**에서 진행하기로 함

---

## 2. "Skill" = SKILL.md (Agent Skills 오픈 표준)

- build.nvidia.com/skills 는 **카탈로그**(382종)다. Claude Code·Codex 와 **같은 SKILL.md 형식**
  (frontmatter `name`·`description` 필수). 우리 `.claude/skills/*/SKILL.md` 8종이 이미 이 형식이다
- **HTTP "Skill API" 는 확인되지 않았다** — 공개된 것은 카탈로그 · `npx skills add NVIDIA/skills --skill <name>` CLI ·
  문서 검색용 MCP(`https://docs.nvidia.com/skills/_mcp/server`) 뿐
- NVIDIA 검증 스킬에는 추가로 `skill.oms.sig`(서명) · `skill-card.md` · `evals/` 가 붙는다.
  게시 파이프라인: SkillSpector 스캔 → 평가 → OMS 서명 → skill card
- 설치 위치(`npx skills add … --agent claude-code`): 프로젝트 `.claude/skills/`, 전역 `~/.claude/skills/`

### 카탈로그 실측 (2026-09-24, `npx skills add NVIDIA/skills --list` — 설치 없이 조회)

382종 중 관련: `nemoclaw-user-guide` · `nemotron-policy-generator` · `skill-card-generator` · `rag-eval` ·
`nemo-retriever` · `nemo-retriever-mcp` · `nemotron-voice-agent-builder` · `nemotron-speech`(Day 3 음성) ·
`nvidia-skill-finder`.
⚠ `nemoclaw-user-*` 가 11종 있다는 보고가 있었으나 **카탈로그에는 `nemoclaw-user-guide` 1종뿐**.
Guardrails · OpenShell · NeMo Agent Toolkit 전용 스킬은 카탈로그에 없다
(Guardrails 스킬은 제품 레포 `NVIDIA-NeMo/Guardrails/.agents/skills` 에만 있음).

---

## 3. SkillSpector — 우리 스킬 8종 실측 스캔

- 도구: https://github.com/NVIDIA/SkillSpector (Apache-2.0, Python 3.12+)
- ⚠ **Windows 에서 `uv run` 설치는 실패** — anthropic SDK 의 긴 파일명 + 긴 경로로 MAX_PATH(260) 초과.
  **공식 Dockerfile 로 빌드해서 쓴다**: `docker build -t skillspector:local .` →
  `docker run --rm -v "<skills>:/scan" skillspector:local scan /scan/<name> --no-llm --format json --output /scan/x.json`
- LLM 의미 분석은 `SKILLSPECTOR_PROVIDER=nv_build` + `NVIDIA_INFERENCE_KEY`(build.nvidia.com) 기본 지원 — 이번엔 `--no-llm`(정적)만

| 스킬 | 점수 | 판정 | 발견 |
|---|---|---|---|
| `done` | 27 | MEDIUM / CAUTION | **AS1 HIGH** Agent Config Directory Access — `SKILL.md:50` `grep -rn "D1~D" … .claude/` |
| `run-eval` | 19 | LOW / CAUTION | **PE3 HIGH** Credential Access — `SKILL.md:16` `grep '^DATABASE_URL=' .env` |
| `stage` | 13 | LOW / CAUTION | RP1 MEDIUM ×2 MCP Rug Pull — `SKILL.md:73` 버전 미고정 `npx` |
| `safety-guardrail` | 0 | SAFE | — |
| `eda-manual`·`scenario-smoke`·`seed-db`·`sprint` | 0 | CAUTION | 발견 없음. 참조 파일이 번들에 없어 "partial" 이라 CAUTION |

→ 새 레포에서 3건을 고치고 재스캔 결과를 데모·README 에 싣는다. `run-eval` 의 `.env` 직접 읽기는 실제로 고칠 가치가 있다.

---

## 4. NeMo Guardrails · NemoClaw · NeMo Agent Toolkit (원문 확인)

- **NeMo Guardrails** `nemoguardrails` 0.24.1 · Python 3.10~3.13 · Apache-2.0
  - `self check input` — 메인 LLM 하나로 판정 → **OpenShell 게이트웨이의 단일 모델(inference.local)로 가능**
  - `content safety`(`nvidia/llama-3.1-nemotron-safety-guard-8b-v3`) — **두 번째 모델 경로가 필요** → 현 구조로는 불가(미확인)
  - 휴리스틱 jailbreak 탐지는 gpt2-large 필요 · 영어 최적화 → 한국어 문서 텍스트엔 약함
- **NemoClaw** 공식 최소 사양 **RAM 8GB**(권장 16GB) · 4 vCPU · 디스크 20GB · Node 22.19+.
  🔵 **2026-09-24 갱신 — WSL Ubuntu 로 옮기며 전부 충족됐다**(RAM 15Gi · 8 vCPU · 936G · Node v22.23.1, §11).
  아래 "RAM 7GB 미달" 은 Windows 시절 실측이다.
  현 PC 는 **RAM 7GB → 최소 미달.** OpenShell 직접 사용(BYOC) 유지, 근거는 `day1.md` §5.
  원리상 OpenClaw 는 SKILL.md 와 stdio MCP(`mcp.servers`)를 둘 다 로드할 수 있다(미실행)
- **NeMo Agent Toolkit** `nvidia-nat` 1.9.0 · Python 3.11~3.13 · `nvidia-nat[mcp]` 로
  **기존 stdio MCP 서버를 그대로 붙일 수 있다**(`_type: mcp_client`, `transport: stdio`).
  NAT 가 SKILL.md 를 런타임에 읽는지는 미확인

---

## 5. 제안된 "NVIDIA 완전 포장" 안 (사용자 방향 동의 — 세부는 새 레포에서 확정)

- **개발 방식**: NVIDIA 카탈로그 스킬을 Claude Code 에 설치해 개발에 쓴다. **모든 스킬은 설치 전 SkillSpector 게이트**(NVIDIA 것 포함)
- **제품 스킬**: `maintq-manual-onboarding`(Day 2) · `maintq-diagnose`(S1) 를 SKILL.md 로 패키징 +
  `skill-card-generator` 로 카드 + `evals/` + SkillSpector 결과
- **런타임**: 온보딩 에이전트 = NeMo Agent Toolkit 워크플로 + MaintQ MCP · 업로드 텍스트 = NeMo Guardrails `self check input` ·
  추론 = Nemotron(NIM) · 실행 = OpenShell
- **보안 서사**: 스킬 검증(SkillSpector) → 입력 검증(Guardrails) → DB 권한(스테이징 INSERT 만) → 샌드박스(외부 0건) → 사람 승격

---

## 6. Day 2 사전 확인 결과 (샌드박스 실측)

- ✅ **샌드박스 안 추론 실패 → 명시적 에러**: 게이트웨이 모델을 없는 ID 로 바꾸고(`openshell inference set … --no-verify`,
  검증 없이는 거부됨) 채팅 → `LLM 호출 실패 — nvidia 원인 NotFoundError 404. 샌드박스 정책상 폴백 불가 (egress 기본 차단, D143).`
  게이트웨이 로그 `API:INFERENCE Failure … 92ms`. 모델 원복 확인
- **A2A 이벤트 발신 차단** — 자동 발화는 `POST /api/po/{id}/finance-approve` → FinAllQ `request-withdrawal` **한 곳**
  (정산·처분 통지는 사람이 누르는 별도 API)
  - ✅ 샌드박스 안 `PO-0114` 재무 승인(mgr-02) → **HTTP 200, `finance_approved`** — 업무는 안 깨진다
  - ✅ 발신은 정책이 차단: `DENIED python3.13 -> POST http://host.docker.internal:9101/a2a/skills/request-withdrawal`
  - ❌ **trace 에는 `status=error` · `A2A request failed with status 403`** — 샌드박스 프록시의 403 을 FinAllQ 의 응답으로 오인
  - ❌ 같은 이유로 **차단기가 FinAllQ 를 "살아 있음"으로 회계**한다(D139 규칙) — 사실과 반대
  - 제안(미적용): 샌드박스 모드(D143)에서 A2A 실패를 `policy_blocked` 로 분류, 차단기 회계 제외. 페이로드·QMesh 계약 무변경
  - ⚠ 샌드박스에 `MAINTQ_A2A_FINALLQ_BASE_URL` 이 **없으면** 발신 함수가 **아무 기록 없이 조용히 반환**한다
- 관찰 O8: `search_inventory` 에 품번을 `part_name` 인자로 넘겨 `not_found` → 대체품 경로로 빠진 실행이 있었다(기록만)

---

## 7. 새 매뉴얼 후보 (4종 모두 PDF 직접 받아 텍스트 추출 확인, 레포 밖 보관)

| 순위 | 기종 | 크기 | 고장 표 | 코드 |
|---|---|---|---|---|
| **1 (추천)** | **Yaskawa HV600** (HVAC 팬·펌프) — TOEPC71061732H<7>-0 | 126쪽 · 24MB | p107~124, **괘선 4열(Code/Name/Causes/Solutions)** | `GF` `Uv` `CPF06` `FAn1` 약 120 · `EF1 to EF7` 범위 펼침 필요 |
| 2 | Mitsubishi FR-F800 (팬·펌프) — IB(NA)-0600547ENG-G | 713쪽 · 17MB | p602~620 카드형, 목록표 코드는 그래픽 | `E.OC1` 약 79 |
| 3 | ABB ACH580 (HVAC) — 3AXD50000027537 Rev J | 764쪽 · 17MB | p245~283 거의 무괘선 | hex `2310` + 보조코드 |
| 예비 | Danfoss FC 102 | 128쪽 | 서술형 | 숫자만 |

HV600 URL: https://www.yaskawa.com/delegate/getAttachment?documentId=TOEPC71061732&cmd=documents&documentName=TOEPC71061732.pdf
특정 팹이 이 기종을 쓴다고 주장하지 않는다.

---

## 8. 미결정 사항 → **전부 결정됨** (2026-09-24, 새 레포에서)

| # | 항목 | 결정 | 근거 |
|---|---|---|---|
| 1 | 새 레포 | `ttogle918/MaintQ-NemoClaw` · **비공개**(제출 직전 공개) · **Apache-2.0** | NVIDIA 생태계 표준 라이선스. NemoClaw 사양은 WSL 이전으로 충족(RAM 7→15GB) |
| 2 | 매뉴얼 추출물 공개 | **비공개 — 실데이터는 `.gitignore`, 형태는 `data/extracted/samples/`** | **D144**. 히스토리까지 재작성(`git filter-repo --invert-paths`) |
| 3 | 매뉴얼 선택 | **Yaskawa HV600** + 온보딩에 **한국어 정규화 단계** | **D145**. 영문 그대로면 샌드박스 키워드 검색이 0히트 |
| 4 | 기종 enum 충돌 | **enum 선등록 + DB 온보딩 상태로 게이트** (절대규칙 4 유지) | **D146**. 정의 지점 **9곳 + DB CHECK 2곳**(문서의 "8곳" 은 실측과 달랐다) |
| 5 | A2A `policy_blocked` | **적용** — 샌드박스에서는 시도 전 분류, 차단기 회계 제외 | **D149** |
| 6 | 새 기종 안전 문구 | **스테이징 → 사람 승인** (절대규칙 3 유지) | **D147**. 승인 전 차단은 결함이 아니라 데모의 핵심 |
| 7 | 새 매뉴얼 RAG | **DB(`manual_chunks`) 승격 + `rag.py` 가 jsonl ∪ DB** | **D148**. `/app` 읽기 전용이라 파일 재생성 경로가 막힌다 |

### 이 과정에서 드러난 실측 정정

- **§7 의 "DB 에 넣는 방향" 은 그대로는 동작하지 않는다.** 키워드 인덱스는 DB 가 아니라 파일
  (`rag.py:44` → `data/extracted/manual_chunks.jsonl`)을 읽고, `manual_chunks` 테이블은 dense 전용인데
  dense 는 샌드박스에서 꺼진다. → `rag.py` 를 **jsonl ∪ DB** 로 넓히는 것이 전제다(D148)
- **§8 #4 의 "코드 8곳" 은 9곳 + DB CHECK 2곳이다.** 전수: `backend/manifest.py:30` ·
  `agent/prompts.py:41` · `services/po.py:121` · `mcp_server/rag.py:51` · `tools/lookup_error_code.py:31` ·
  `tools/create_po_draft.py:38` · `tools/create_repair_record.py:48` · `data/inventory.py:19` ·
  `data/chunk_manual.py:48` + `data/seed.py:152` · `scripts/postgres_schema.sql`
- **§8 #6 의 "막을 가능성" 은 확정이다.** `loop.py:353 safety_page()` 가 `SAFETY_BASELINE["pages"]`
  (iG5A 4 / S100 2)에 없는 기종이면 `None` → `loop.py:435` 가 턴을 끊는다. IE5 가 이미 그 상태다
- **매뉴얼 문장의 퍼짐이 예상보다 넓었다** — `data/extracted` 뿐 아니라 `eval/results` **190파일**,
  Elice OCR 캐시 34파일, IE5 회귀 픽스처까지 들어 있었다(D144 가 전부 다룬다)

## 9. 공개 전 점검 결과 (현 레포, 2026-09-24)

- 전 브랜치 541 커밋 diff(23.8MB) 전수 — `.env` 실제 비밀값 16종 **0건**, 키 모양 문자열(`nvapi-`·`sk-`·`AIza`·`ghp_`·개인키) **0건**
  (양성 앵커 확인). 추적 파일에 `.env`·키 파일 없음
- ⚠ 541 커밋 전부 작성자 이메일 `ttogle918@naver.com` — 공개 시 노출
- 현 레포: GitHub **비공개**, LICENSE 없음, `.git` 55MB

---

## 10. 새 폴더에서 작업할 때 알아야 할 환경 사실

> 🔴 **이 절의 앞 두 줄은 이제 틀렸다 — §11 참고.** Claude Code 는 WSL Ubuntu 에서 직접 돈다.

- Claude Code 는 **Windows 쪽에서** 켠다. OpenShell 은 WSL Ubuntu 에 설치돼 있고 `wsl -d Ubuntu -- bash -c '…'` 로 조작
- Git Bash 에서 wsl 로 경로를 넘길 때 **`MSYS_NO_PATHCONV=1`** (안 붙이면 `/mnt/c/...` 가 `C:/Program Files/Git/mnt/...` 로 바뀜)
- `bash -c` 안에서 `pkill -f <패턴>` 은 자기 자신도 죽인다(exit 15)
- WSL `sudo` 가 필요한 일은 사람이 한다
- 샌드박스 재현 절차·함정: `day1.md` §6
- 게이트웨이에는 provider `nvidia-prod` · 모델 `nvidia/nemotron-3-super-120b-a12b` 가 설정돼 있다(PC 단위라 새 폴더에서도 그대로)
- 현재 샌드박스 `maintq` 는 A2A 주소 env 를 넣은 상태로 **실행 중**(`localhost:8000`)

---

## 11. 레포 이관 사실 (2026-09-24)

- 작업 위치는 **WSL Ubuntu `~/MaintQ-NVIDIA`** 로 옮겼다. Claude Code 도 여기서 돈다 —
  §10 의 "Windows 에서 켜고 `wsl -d Ubuntu` 로 조작" 은 **더 이상 맞지 않는다**(`MSYS_NO_PATHCONV` 주의사항도 무관)
- 원격: `https://github.com/ttogle918/MaintQ-NemoClaw` (비공개)
- 🔴 **커밋 해시가 전부 바뀌었다 — 두 번 재작성했다.** ㉠ 작성자 이메일 `ttogle918@naver.com` →
  `17754713+ttogle918@users.noreply.github.com`(537커밋) ㉡ D144 퍼지. 그래서 이 레포의 문서가
  인용하는 **옛 해시(`5e5e962`·`5895c2e`·`7ff38b2`·`213b62d`·`390e7a9` 등)는 더 이상 조회되지 않는다.**
  옛→새 대조표는 `~/maintq-filter-repo-maps-20260924/commit-map` 에 있다
- 복구용 번들: `~/maintq-backup-20260924.bundle`(이메일 치환 전) ·
  `~/maintq-backup-20260924-prepurge.bundle`(퍼지 전). **둘 다 매뉴얼 실데이터를 담고 있으니 공개 금지**
- NemoClaw 사양 실측(Ubuntu): RAM **15Gi**(최소 8) · vCPU **8**(4) · 디스크 **936G**(20) ·
  Node **v22.23.1**(22.19+) · docker 29.3.1 · openshell 0.0.116 → **전부 충족**(Windows 시절 RAM 7GB 미달이 해소됐다).
  단 **실제 설치·기동은 아직 안 했다**
