# HV600 온보딩 데모 — 녹화 영상 설명과 실측 기록

**측정·녹화: 2026-09-25 (KST)** · Sprint 19 (NVIDIA 해커톤 Day 2) · 커밋 `bbd2fc8`~`42b87ec` 이후 상태
· 데모 시나리오 원안은 `docs/hackathon/day2.md` §10, 계획은 `docs/sprints/sprint-19.md`

> DB 시각은 UTC 로 저장된다(D39). 이 문서의 시각은 KST(UTC+9)로 옮겨 적었다.

---

## 0. 한 줄

**영문 매뉴얼만 있는 새 기종(Yaskawa HV600)을 NVIDIA 에이전트(NAT + Nemotron)가 한국어로 온보딩하고,
사람이 검수·승격·안전 문구 승인을 해야만 현장 진단(OpenClaw)에 쓰인다** — 같은 질문
"HV600 에서 GF 떴어" 가 승격 전에는 「모름 → A/S 안내」, 승격 후에는 「정의·원인·조치 + 사람이 승인한 안전 문구」로 바뀐다.

---

## 1. 영상 구성

| 장면 | 화면 | 보여 주는 것 | 비고 |
|---|---|---|---|
| ① 승격 전 | OpenClaw 웹 대화창 (샌드박스 `maintq-agent`) | "HV600에서 GF 떴어" → 「HV600 매뉴얼에서 확인되지 않는 코드 — 원인·조치를 추정하지 않음 → 표시부 재확인·제조사 A/S」 | 유사 코드 추측 0 (절대규칙 6) |
| ② NAT 정규화 | (녹화 대신 설명) | HV600 249행을 샌드박스 `maintq-nat` 안(L0)에서 Nemotron 이 한국어로 정규화 — 전량 2,588초 | 영상에는 결과만. 재현 명령 §4 |
| ③ 사람 검수·승격 | MaintQ 웹 `/manager/onboarding` (팀장 박OO) | GF 그룹: 「AI 초안 — 사람 승인 전」 라벨 · 「원문 전체 보기」(영문 ↔ 한국어, 인용 칩은 원문 쪽에만) · **승격** 클릭 | 되돌릴 수 없는 동작 |
| ④ 승격 후 | OpenClaw 웹 대화창 (**새 세션**) | 같은 질문 → GF 정의(지락)·원인 4건·권장 조치·최근 이력 + **승인된 HV600 안전 문구**(「최소 5분 이상」, 근거 p.29) | ⑤(승인된 안전 문구 동반)를 겸함 |
| ~~⑥~~ | — | 샌드박스 A2A `policy_blocked` | **데모에서 제외**(2026-09-25 사용자 결정 — A2A 는 이 레포에서 더 확장하지 않음) |

**녹화하지 않은 것**: SC-14 안전 문구 승인 장면·헤더 뱃지 전환(온보딩 중 → 진단 가능)은 녹화 전에 이미 지나갔다.
뱃지 전환은 격리 스키마 검증 스크린샷(`.../scratchpad/browser/stage4/09_header_badge_ready.png`, 레포 밖)으로만 남아 있다.

영상 파일 위치: _(사람이 기록)_

---

## 2. 녹화 시점의 실제 상태 (공유 DB, 녹화 후 실측)

| 항목 | 값 |
|---|---|
| 온보딩 배치 | batch 1 · HV600 · `hv600-iopm` · 원본 **TOEPC71061732** |
| 원문 행 | 249 (approved 12 · rejected 1 · staged 236) |
| 한국어 정규화 | 261 (= 249 + 과탐 재정규화 12) · 최신 기준 high 248 · low 1(`oL1` untranslated_term) |
| 승격 | **8건** — CE(#5·#141) · GF(#59) · OC(#71) · OV(#110·#190) · UV1(#124) · OH(#99·#184) · CPF06(#40) · EF1(#49·#153) — 06:43~07:00 |
| 반려 | CE row #142 — 이름 "Run at H5-34 (CE Go-To-Freq)" 가 원인(Modbus 통신)과 안 맞음(추출 섞임) |
| `error_codes` HV600 | 8 (전체 78) |
| `manual_chunks` HV600 | 33 (승격이 만든 RAG 청크) |
| 안전 문구 | **SC-14 · p.29 · discharge_wait · 「최소 5분 이상」** 승인(mgr-01, 06:27) · 나머지 27 staged |
| `/api/onboarding/status?model=HV600` | `ready` |
| OpenClaw 워크스페이스 | `build.py --check` → `stale=[] onboarding_HV600=approved` (SC-14 승인 후 재생성·업로드) |

재는 커맨드:
```bash
docker exec maintq_postgres psql -U postgres -d maintq -At \
  -c "select promo_id, code, row_ids from onboarding_promotions order by 1" \
  -c "select state,count(*) from onboarding_code_rows group by 1" \
  -c "select state,count(*) from onboarding_safety_candidates group by 1"
DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" uv run python deploy/nemoclaw/workspace/build.py --check
```

---

## 3. 사람이 한 일 (H0~H7) — 순서대로

1. **H0** D154~D157 확정(09-24)
2. **H4 먼저** — SC-14 안전 문구 승인. 한국어 문안은 Claude 가 원문을 번역한 **초안**을 사람이 p.29 원문과 대조해 확정·입력
   (D147: AI 가 안전 문구를 **화면에서 제안하지 않는다** — 채팅으로 받은 초안을 사람이 판단해 입력한 것)
   · **5분 결정**: HV600 은 매뉴얼 명시값 5분. safety-guardrail 규칙 3 의 「10분 이상」은 iG5A·S100 확정값으로 읽는다
3. 안전 **적용 범위 문장** 승인(`build.py` AGENTS.md · `maintq-diagnose` SKILL.md — 본문 무변경, 적용 기종만)
4. **H5ⓐ** 워크스페이스 재생성·업로드·스킬 설치 → ① 녹화
5. **H2·H3** 검수·승격 (CE #142 반려 후 CE 승격 → GF 승격(녹화) → 나머지 6개)
6. ④ 녹화 — **H5ⓑ 는 필요 없었다**(H4 를 먼저 해서 ⓐ 설치분에 이미 승인 문구가 들어가 있었다)

---

## 4. 재현

```bash
# 백엔드·프론트 (공유 DB — 여기서 누르는 승격·승인은 실제로 반영, 되돌릴 수 없음)
DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" MAINTQ_CORS_ORIGINS=http://localhost:3000 \
  uv run uvicorn backend.main:app --host 127.0.0.1 --port 8010
cd frontend && NEXT_PUBLIC_API_BASE=http://127.0.0.1:8010 npx next dev -p 3000
# → http://localhost:3000 → 정비팀장 박OO → 「기종 온보딩 검수 →」

# OpenClaw 대화
nemoclaw maintq-agent dashboard-url                 # 웹 대화창 URL (토큰 포함 — 녹화·공유 금지)
nemoclaw maintq-agent agent --session-id <새 ID> -m "HV600에서 GF 떴어"

# NAT 정규화 (샌드박스 L0) — onboarding/nat/README.md
```

---

## 5. 관측·함정 (틀렸던 것 포함)

- **같은 세션을 재사용하면 상태 변화를 못 본다.** ① 에 쓴 `--session-id demo1` 로 ④ 를 보냈더니
  "앞서 설명드린 것처럼 … 확인되지 않는 코드" — 에이전트가 `lookup` 을 **다시 부르지 않고** 이전 답을 재활용했다.
  새 세션에서는 정의·안전 문구가 정상으로 나왔다. 데모는 세션을 나눠 찍으면 되지만, 실사용이라면
  "에러코드 질문은 매번 lookup 을 새로 호출" 규칙이 스킬에 필요하다(미반영).
- **NAT 첫 프롬프트가 정상 명령문을 주입으로 오인** — "Make sure…", "Set…" 같은 조치문 11행에 `injection_suspect` 를
  달고 번역을 비웠다(원문 `source_flags` 는 0). 프롬프트 수정 후 `--renormalize-rows` 로 재정규화 → 12/12 high.
- **추출 섞임 1건** — CE row #142. 원인은 #141 과 같은데 이름만 다른 행("Run at H5-34"). 사람 검수에서 반려.
  그룹 단위 승격이라 반려하지 않았으면 같이 들어갔다.
- **서버 토큰 검사가 한글 조사를 몰랐다** — `A1-03을` 의 파라미터 ID 를 `\b`(유니코드)가 못 찾아 `token_dropped` 오판.
  ASCII 경계로 수정(`mcp_server/onboarding_guard.py`).
- **CLI 한 줄에 대해**: `nemoclaw <name> agent` 는 `--session-id` 같은 대상 선택자가 **필수**(없으면 exit 2).
- **개발 도구 쪽**: 서브에이전트 Sonnet 5 주간 한도(09-27 04:00 KST 리셋)에 Stage 3 도중 걸려 Opus 로 재기동 ·
  자동 모드 권한 분류기가 공유 DB 쓰기(가짜 처분서 삭제·재정규화)를 막아 사람이 직접 실행하거나 명시 승인했다.
- **Nemotron 이 답에 중국어 「参照」 를 섞는다**(웹 콘솔에서 네모 글자) — 영상에 걸렸는지 확인할 것.

---

## 6. 남은 것

- H6 SkillSpector 판정(`maintq-diagnose` 0점 · `maintq-manual-onboarding` HIGH 1 — 합성 주입 문장, 리뷰 수용 권고)
- 세션 재사용 문제 → 스킬 규칙 추가 여부 결정
- 발표에서 뱃지 전환·안전 승인 장면은 말로 보충
