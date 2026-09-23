# `data/extracted/samples/` — 구조 샘플 (D144)

여기 있는 파일은 **실데이터가 아니다.** 키 구조를 보여 주고, 매뉴얼에서 온 문자열은
40자로 자른 **형태 견본**이다. 사람이 "이 파이프라인이 어떤 모양의 데이터를 다루는가" 를
확인할 수 있게 남긴다.

## 왜 실데이터를 안 올리나

`manual_chunks.jsonl`(본문 1,229청크)·`error_codes.json`(고장 표 70행의 원인·조치 문장)은
원본 매뉴얼의 **표현**이다. 코드·페이지 번호 같은 사실과 달리, 그대로 공개하면 매뉴얼
텍스트 재배포가 된다. 그래서 실데이터는 `.gitignore` 로 빼고 형태만 남겼다 (D144).

## 실데이터를 만드는 법

공식 PDF 를 `data/raw/` 에 두고 (출처·판번호·sha256 은 `data/raw/manifest.json` 에 있다):

```bash
uv run python data/chunk_manual.py          # → manual_chunks.jsonl
uv run python data/extract_error_codes.py   # → error_codes.json + 후보 파일
uv run python data/extract_ie5_codes.py     # → IE5 후보 + spikes 회귀 픽스처
uv run python data/seed.py --with-error-codes
```

manifest 의 sha256 을 실제로 대조하므로, 다른 판본이면 **조용히 재생성하지 않고 멈춘다**(D19).

## 파일 대응

| 샘플 | 원본 | 원본이 하는 일 |
|---|---|---|
| `manual_chunks.sample.jsonl` | `../manual_chunks.jsonl` | RAG 키워드 인덱스 — `mcp_server/rag.py` 가 **파일을 직접** 읽는다 |
| `error_codes.sample.json` | `../error_codes.json` | 정본 고장 표 → `error_codes` 테이블 (`lookup_error_code`) |
| `error_codes_actions.candidate.sample.json` | `../error_codes_actions.candidate.json` | 조치 후보 — 사람 승인 전 격리 (D99) |
| `ie5_code_candidates.sample.json` | `../ie5_code_candidates.json` | IE5 추출 후보 (D107) |
| `ig5a_code_map.sample.json` · `ig5a_action_map.sample.json` | `../ig5a_*_map.json` | 빌드타임 매핑 |
| `actions_absence_verification.sample.json` | `../actions_absence_verification.json` | "조치가 원문에 없음" 검증 리포트 |

추적을 유지하는 두 파일은 매뉴얼 문구가 아니라 우리가 만든 값이다 —
`../residual_curve.json`(D74 잔존가치 목업 공식) · `../extract_triage.json`(추출 트리아지 신호).

재생성: `uv run python scripts/make_data_samples.py`
