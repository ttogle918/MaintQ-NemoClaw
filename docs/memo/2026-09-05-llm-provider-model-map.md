# LLM 제공자·모델 실측 지도

**측정: 2026-09-05** · 외부 서비스 카탈로그라 **빠르게 낡는다.** 아래 §5 의 커맨드로 다시 잴 것.

---

## 0. 이 문서가 생긴 계기

평가를 돌렸더니 **20문항이 전부 빈 응답**이었다. 지표가 `0.0%` 로 찍히고 리포트는
`part 53.3% → 0.0% (-53.3pt)` 라는 회귀를 인쇄했다. **회귀가 아니라 장애였다.**

```
HTTP 410 {"title":"Gone",
          "detail":"The model 'openai/gpt-oss-120b' has reached its end of life
                    on 2026-09-03T08:00:00Z and is no longer available."}
```

NVIDIA 가 우리 기본 모델을 **이틀 전에 EOL** 시켰고, 폴백인 OpenAI 는 크레딧이 소진돼
있었다. 로그에는 `원인 APIStatusError` 한 줄뿐이라 원인을 알 수 없었다(→ D131 로 상태코드까지
남기게 고쳤다).

**교훈: 모델 id 는 우리가 통제하지 못하는 외부 자원이다.** 어느 날 사라진다.

---

## 1. 무료로 쓸 수 있는 모델 (2026-09-05)

두 제공자 모두 **OpenAI 호환**이라 `EliceClient` 를 그대로 재사용한다.

### Ollama Cloud (`MAINTQ_LLM_PROVIDER=ollama`)

카탈로그 19종 중 **6종만 무료**다. 나머지 13종은 `HTTP 402` +
`"this model requires a subscription or extra usage"` 를 낸다.

| 모델 | 파라미터 | 아키텍처 | ctx | 도구호출 | 지연(1콜) |
|---|---|---|---|---|---|
| `gpt-oss:20b` | 20.9B | gptoss (MoE) | 131K | ✅ | **1.8s** |
| `gpt-oss:120b` | 116.8B | gptoss (MoE) | 131K | ✅ | **3.1s** |
| `nemotron-3-super` | 120B | nemotron_h_moe | 262K | ✅ | 4.9s |
| `gemma4:31b` | 32.7B | gemma4 | 262K | ✅ | 5.3s |
| `nemotron-3-ultra` | 550B | MoE | 262K | ✅ | 19.8s |
| `nemotron-3-nano:30b` | 32B | nemotron-3-nano | 262K | ✅ | 21.6s |

**구독 필요(402)** — 이름이 카탈로그에 보인다고 쓸 수 있는 게 아니다:
`qwen3.5:397b` · `kimi-k3` · `kimi-k2.6` · `kimi-k2.7-code` ·
`glm-5.1` / `5.2` / `5.3` / `5.3-flash` · `deepseek-v4-pro` / `deepseek-v4-flash` ·
`minimax-m2.7` / `m3` · `mistral-large-3:675b`

> `GET /v1/models` 는 **인증 없이도 200** 이고 유료 모델까지 전부 나열한다.
> 목록에 있다 ≠ 쓸 수 있다. **호출해 봐야 안다.**

### NVIDIA NIM (`MAINTQ_LLM_PROVIDER=nvidia`)

카탈로그 81종. 계열별 유무만 적는다(전수는 §5 로 다시 잴 것).

| | |
|---|---|
| 있음 | `openai/gpt-oss-20b` · `moonshotai/kimi-k2.6` · `kimi-k3` · `nvidia/nemotron-3-*` · `google/gemma-*` · `mistralai/*` · `deepseek-ai/*` |
| **없음** | **Qwen 계열 0건** · GLM 0건 · llama-4 0건 |
| EOL | `openai/gpt-oss-120b` (2026-09-03) — **Ollama Cloud 에는 아직 살아 있다** |

> 임베딩도 같은 카탈로그에서 고른다 — D117 이 `nvidia/nemotron-3-embed-1b` 를 쓴다.
> 그때도 원래 Qwen 임베딩을 원했으나 **카탈로그에 0건**이라 대체했다. 같은 제약이 반복된다.

### 로컬(ollama 데몬)은 이 기계에선 불가

| | |
|---|---|
| GPU | Intel Iris Xe **내장**, VRAM 2GB · `nvidia-smi` 없음 = **CUDA 없음** |
| RAM | 31.6 GB |
| 실측 | `llama3.2:1b` 로 프롬프트 2,332tok + 생성 300tok = **38.2초** (프롬프트 107tok/s · 생성 23tok/s) |

**1B 가 한 턴에 38초다.** 도구 7종 오케스트레이션에 필요한 8B 급은 CPU 추론이 대략 6~8배
느려 한 턴 ~5분 → 20문항 **6~9시간**. 그런데 `ITEM_TIMEOUT_S = 180.0` 이라 **전 문항이
타임아웃**난다. 느린 게 아니라 **측정 자체가 성립하지 않는다.**

> GPU 있는 기계가 생기면 얘기가 다르다 — ollama 는 OpenAI 호환이라
> `PROVIDERS` 에 `base_url="http://localhost:11434"` 한 줄이면 붙는다.
> **Ollama Cloud 는 이 제약과 무관하다** — 남의 GPU 에서 돌기 때문이다.

---

## 2. `.env` 의 유료 폴백 함정

```
MAINTQ_LLM_PROVIDER=ollama
MAINTQ_LLM_MODEL=<무료 모델>
MAINTQ_LLM_FALLBACK_PROVIDER=openai      ← 유료
MAINTQ_LLM_FALLBACK_MODEL=gpt-4.1-mini   ← 유료
```

폴백은 **D123 이 의도한 설계**다 — 무료 primary 가 죽어도 사이트가 조용히 죽지 않게 한다.
서빙에는 옳다. **그런데 평가에는 두 가지로 해롭다.**

1. **돈** — primary 가 402/410 로 죽으면 조용히 유료 경로로 넘어간다.
   실제로 `.env` 에 구독 전용 모델(`qwen3.5:397b`)이 적혀 있던 순간이 있었고,
   그대로 `--repeat 3` 을 돌렸으면 **20문항 × 3회차가 전부 유료**로 나갈 뻔했다.
   (그날 OpenAI 크레딧이 이미 소진돼 있어서 과금은 0이었다 — 운이 좋았던 것이지 방어가 아니다.)
2. **방법론** — 회차 중간에 폴백이 걸리면 1~6번 문항은 모델 A, 7~20번은 모델 B 로 측정되는데
   리포트에는 **모델 하나만** 적힌다. 조용히 섞인 수치가 나온다.

**평가 실행에서는 폴백을 끈다:**

```bash
MAINTQ_LLM_FALLBACK_PROVIDER= MAINTQ_LLM_FALLBACK_MODEL= uv run python eval/run_eval.py --yes
```

빈 문자열이면 `get_client()` 가 `FallbackClient` 로 감싸지 않는다
(`(os.environ.get(...) or "")` 라 빈 값 = 미설정). `load_dotenv(override=False)` 는
**이미 있는 키를 덮지 않으므로** `.env` 값이 되살아나지 않는다 —
`pop()` 으로 지우면 `.env` 가 다시 채운다. **비우되 지우지 말 것.**

확인 방법:
```bash
MAINTQ_LLM_FALLBACK_PROVIDER= MAINTQ_LLM_FALLBACK_MODEL= uv run python -c "
import sys; sys.path.insert(0,'.')
from dotenv import load_dotenv; load_dotenv(override=False)
from backend.agent import llm
print('폴백 래핑?', isinstance(llm.get_client(), llm.FallbackClient))"   # False 여야 한다
```

사후 확인은 서버 로그로:
```bash
grep -c "제공자 폴백" eval/results/<stamp>.server.log      # 0 이어야 전 구간 무료
```

---

## 3. 모델 선택 시 이 코드베이스 고유의 함정

**후보 6종 전부 `thinking` capability 를 갖고 있다.** 그런데 D123 이 기록한 구멍이 있다:

> `elice_chunk_delta` 는 `delta.content` 만 읽고 `reasoning`/`reasoning_content` 는 버린다.
> 모델이 본문을 안 내면 텍스트 0글자가 되는데 `loop.py` 의 `if not pending: break` 가
> 그대로 턴을 끝낸다 — **예외도 경고도 없이 조용히 종료**된다.

InsuQ 가 같은 `gpt-oss-120b` 를 이 이유로 기각했다(도구 없는 최종 턴에서 `reasoning` 에
출력을 다 쏟고 `content` 를 비웠다). **MaintQ 에는 그 패턴이 없어서**(매 회차 `tools` 를 넘긴다)
2026-09-05 실행에서는 발화하지 않았다 — `STREAM_ERROR 0건`.

> 나도 한 번 같은 모양을 봤다: `gpt-oss:20b` 첫 탐침이 `content:null` + `reasoning` 만 찼는데,
> **`max_tokens=10` 을 reasoning 이 다 써서** 그런 것이었다. 토큰을 넉넉히 주면 정상이다.
> 모델 탐침에서 `max_tokens` 를 짜게 주면 **멀쩡한 모델을 불량으로 오판**한다.

`extra_body.chat_template_kwargs.thinking=false` 로 추론을 끄지 말 것 (D123) —
A2A_Q 실측에서 nemotron 계열이 4/4 로 `finish_reason=tool_calls` + 빈 본문을 냈다.

---

## 4. 실측 결과 요약 (참고 — 상세는 세션 로그·리포트)

같은 20문항 · 각 1회 · 채점은 D133 **이전** 기준.

| 지표 | gpt-4.1-mini | gpt-oss:20b | gpt-oss:120b |
|---|---|---|---|
| 부품 특정 | 53.3% | **80.0%** | 60.0% |
| 근거 인용 | 88.9% | 88.9% | **100%** |
| 안전 경고 | 72.2% | 83.3% | 83.3% |
| traces | **0행** (D130 버그) | 176행 | 182행 |

**크기 순위가 성능 순위가 아니다.** 120b 는 부품 특정이 20b 보다 낮은데, 실패를 뜯어 보니
*"후보를 늘어놓고 사용자에게 되묻는"* 경향 때문이었다 — 지표 이름이 "부품 **특정**"이라
헤징이 감점된다. 자세한 것은 [agent-loop-observations](2026-09-05-agent-loop-observations.md).

**각 1회 실행이라 순위를 결론으로 쓰면 안 된다.** 이 레포는 *"2·3차에서 판정이 뒤집힌
문항이 7개"* 였던 기록을 갖고 있다(`data/analysis/eval_gap_3rd.md §4`). `--repeat 3` 필요.

---

## 5. 재는 커맨드

값은 낡아도 **방법은 오래 간다.**

```bash
# ── 카탈로그 (인증 없이도 200. 유료 모델까지 전부 나열된다)
curl -s https://ollama.com/v1/models | python -c "import json,sys; print('\n'.join(sorted(m['id'] for m in json.load(sys.stdin)['data'])))"

K=$(grep -m1 '^NVIDIA_API_KEY=' .env | cut -d= -f2-)
curl -s https://integrate.api.nvidia.com/v1/models -H "Authorization: Bearer $K" | python -c "..."

# ── 제원 (파라미터·컨텍스트·capability)
K=$(grep -m1 '^OLLAMA_API_KEY=' .env | cut -d= -f2-)
curl -s -X POST https://ollama.com/api/show -H "Authorization: Bearer $K" \
     -H "Content-Type: application/json" -d '{"model":"gpt-oss:120b"}'

# ── 실제로 쓸 수 있는가 (402/410 은 여기서만 드러난다)
curl -s -X POST https://ollama.com/v1/chat/completions -H "Authorization: Bearer $K" \
     -H "Content-Type: application/json" \
     -d '{"model":"<모델>","messages":[{"role":"user","content":"hi"}],"max_tokens":50}'
```

**도구 호출 탐침**(이 프로젝트에서 제일 중요한 관문 — 함수 호출이 안 되면 품질과 무관하게 0점):
한글이 섞이면 셸 인코딩에서 깨지므로 **JSON 을 파일로 써서** `--data-binary @file` 로 보낼 것.
`max_tokens` 는 **512 이상**(§3 의 오판 함정).
