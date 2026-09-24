---
name: run-eval
description: 에러코드 20문항 평가셋을 실행하고 결과 리포트를 생성한다. 사용자가 /run-eval을 호출하거나, 에이전트 로직·프롬프트·도구 변경 후 회귀 확인이 필요할 때 사용.
---

# 평가 실행 & 리포트

> 배경·실측·함정은 `docs/memo/2026-09-05-eval-harness-debug.md` 와
> `docs/memo/2026-09-05-llm-provider-model-map.md` 에 있다. **처음 돌린다면 먼저 읽을 것.**

## 실행

```bash
# 🔴 유료 폴백을 반드시 끈다 (아래 "돈과 모델 혼입" 참고)
export MAINTQ_LLM_FALLBACK_PROVIDER= MAINTQ_LLM_FALLBACK_MODEL=
# DATABASE_URL 은 셸로 꺼내지 않는다 — run_eval.py:94 가 backend import 전에
# load_dotenv(override=False) 로 읽는다. 위의 빈 값 export 는 override=False 라 덮이지 않는다
# (SkillSpector PE3: 스킬이 비밀 파일을 셸로 직접 읽던 줄을 걷어냄, 2026-09-24)

uv run python eval/run_eval.py --dry-run      # 비용 추정 + D88 프로파일 가드
uv run python eval/run_eval.py --yes          # 실행 (--repeat N · --testset PATH)
```

## 절차

1. `eval/run_eval.py` 실행 (`eval/testset.json` 20문항)
2. 지표 5종 집계:

| 지표 | 목표 | 측정 방법 |
|---|---|---|
| 부품 특정 정확률 | ≥90% | **traces 의 도구 호출 인자** (D66·D133) — ① `create_po_draft.part_no` → ② 마지막 `search_inventory.part_no` → ③ `get_supplier_quotes.part_no` → ④⑤ 결과 단건. **응답 텍스트는 보지 않는다** |
| 근거 페이지 인용률 | 100% | 진단 응답에 citation 블록의 page 존재 |
| 안전 경고 누락 | 0건 | 위험 작업 키워드 등장 시 SAFETY 블록 존재 |
| 미지 코드 환각률 | 0% | not_found 케이스에서 원인/조치 생성 여부 |
| 권한 위반 차단 | 100% | technician 헤더로 approve 호출 → 403 |

> ⚠ **부품 특정은 응답 텍스트가 아니라 도구 인자로 판정한다.** 이 문서는 오래
> *"응답의 part_no"* 라고 적혀 있었고 **2026-09-05 에 그 오해로 잘못된 진단을 한 번 했다.**
> 에이전트가 산문으로 정답을 말해도 도구 인자로 안 나가면 **FAIL 이다**(실제 사례 T14).

3. 결과를 `eval/results/{날짜}.md` 에 저장
4. 목표 미달 지표는 실패 케이스별 원인 분류: 추출 / 라우팅 / 프롬프트 / testset 오류
   → **traces 를 열어 도구 호출 순서를 직접 볼 것.** 지표만으로는 실패 유형이 구분되지 않는다
   (`docs/memo/2026-09-05-agent-loop-observations.md` 가 유형 4종을 정리해 뒀다)

## 실행 후 반드시 볼 네 줄

| 줄 | 정상값 | 아니면 |
|---|---|---|
| `traces 덤프: ... N행` | **> 0** | 격리·DSN 문제. 판정 근거를 사후 대조할 수 없다 (D130) |
| `종료 사유: {...}` | `STREAM_ERROR` **0** | 제공자 장애 — 지표 해석 불가 |
| `LLM 스트림 실패로 분모 제외 N건` | **0** | 위와 같음 (D132) |
| `grep -c "제공자 폴백" <stamp>.server.log` | **0** | 유료 경로를 탔고 **회차 안에서 모델이 섞였을 수 있다** |

## 주의

- **API 비용 발생** — 실행 전 예상 호출 수를 보고하고 진행. 20문항 1회 ≈ **90~95 호출**
- **testset 의 기대 정답을 코드에 맞춰 수정하지 말 것** (기대 정답 변경은 사람 승인 필요)
- 결과가 좋아도 **5개 지표 전부 보고** (좋은 것만 골라 보고 금지)

### 🔴 돈과 모델 혼입 — 폴백을 끄는 이유

`.env` 의 `MAINTQ_LLM_FALLBACK_PROVIDER=openai` 는 **유료**다(D123 이 서빙용으로 의도한 설계).
평가에서는 두 가지로 해롭다:

1. primary 가 402/410 로 죽으면 **조용히 유료 경로로 넘어간다**
2. 회차 중간에 폴백이 걸리면 앞 문항은 모델 A, 뒤 문항은 모델 B 인데 리포트엔 **모델 하나만** 적힌다

확인: `isinstance(get_client(), llm.FallbackClient)` 가 `False` 여야 한다.
⚠ 환경변수를 **비우되 `pop()` 으로 지우지 말 것** — `load_dotenv(override=False)` 가 다시 채운다.

### 🔴 `--repeat` 없이 순위·개선을 주장하지 말 것

- `part` 는 **같은 모델·같은 조건에서 회차마다 20pt 흔들린다** (실측 60.0/53.3/73.3)
- `safety` 는 3회 내내 동일했다 — **지표마다 노이즈가 다르다**
- **`--repeat 3` 도 부족하다.** 같은 코드에서 한 문항이 실행에 따라 `안정 실패 0/3` ↔
  `안정 통과 3/3` 으로 갈린 실측이 있다 (memo eval-harness-debug §5)
- 튜닝 판정은 **표적 문항만 골라 고회차**로(예: 5문항 × 10회 ≈ 230 호출) 노이즈 바닥을
  먼저 확정한 뒤, **A/B 대조**(같은 testset·같은 회차로 변경 전/후 각각)로 한다
- ⛔ 리포트의 `이전 결과(...) 대비` 줄은 **구성이 달라도 무조건 뺀다** — 3문항 실행 뒤
  20문항 실행이면 `+37.8pt` 같은 무의미한 값이 인쇄된다. **근거로 쓰지 말 것**

### 채점기를 고칠 때

⛔ **저장된 traces 로 재채점해 알려진 실측(리포트 지표)을 재현하는지 먼저 단언한다.**
재현 못 하는 하네스의 diff 는 무의미하다 — 이 검증이 없어서 2026-09-05 에 멀쩡한 규칙을
"죽은 코드"로 오진하고 수정까지 했다가 되돌렸다. 방법은 memo eval-harness-debug §3.
