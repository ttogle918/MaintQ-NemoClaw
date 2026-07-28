# 직접 해야 할 일 (사람 손 필요)

Claude가 대신 못 하는 것들. 순서대로.

## 지금 (M1 시작 전)

- [ ] **LS일렉트릭 매뉴얼 다운로드** ← 최우선, 이거 없으면 M1 시작 불가
  - ls-electric.com/ko/download 또는 sol.ls-electric.com
  - SV-iG5A **완전본** 사용설명서 (간편본 아님 — 보호기능/에러 표가 완전본에 있음)
  - S100 사용설명서
  - 받아서 `data/raw/`에 넣고, Claude 대화에 업로드 → EDA 같이 진행
- [ ] AI허브(aihub.or.kr) 회원가입 + 「기계시설물 고장 예지 센서」 다운로드 **승인 신청** (승인에 시간 걸릴 수 있어 미리)
- [ ] GitHub 레포 생성 (`MaintQ`) + 이 폴더 초기 커밋
  - `.gitignore`에 `data/raw/` 추가 (매뉴얼 원본 PDF는 저작권상 레포 제외, README에 출처 링크만)
- [ ] Anthropic API 키 준비 + 월 비용 상한 설정

## M1 중

- [x] ~~안전 문구 정정 승인: "5분" → "10분 이상"~~ — 승인·전파 완료 (2026-07-18): 02_SCENARIOS·03_WIREFRAME·safety-guardrail 스킬·06 testset 기준에 매뉴얼 근거 페이지와 함께 반영
- [x] ~~추출 전략 승인~~ — D24로 확정 (pdfplumber 텍스트 규칙 파싱)
- [x] ~~**iG5A 매핑 최종 확인**~~ — **2026-07-28 승인 완료.** ② 4건은 180dpi 재렌더링 이미지로
  재확인(COL=입력결상 등 표대로), ③ 2건 결정: `__L` 표기 그대로 채택 + canonical 정책(키패드
  표기 기준, 통신 비트명은 aliases) 제안대로 승인. `ig5a_code_map.json` 갱신 →
  `extract_error_codes.py` 재실행(`_status` 는 이제 맵 파일에서 자동 유도, 하드코딩 아님) →
  `seed.py --with-error-codes` 로 iG5A 24 + S100 41 = **65건 적재 완료**.
  검수표: `data/analysis/ig5a_code_mapping.md` (완료 기록 남김)
- [ ] **`related_parts` 수작업 매핑 검수** — 파일: `data/related_parts.seed.json`. 지금은 S1/S3를 돌려보기 위한 **임시 7건**만 있고 전부 `reviewed: false`. 각 코드의 원인/조치를 매뉴얼에서 읽고 교체 대상 부품이 맞는지 확인 → 맞으면 `reviewed: true`. **검수 전 평가(run_eval) 결과를 실적으로 인용하지 말 것** (부품 특정 정확률의 뿌리, D12)
- [ ] 두 기종 간 동일 표기 코드 목록 확인 (OL, OC 계열) — "같은 코드, 다른 의미" 실증 자료
- [ ] 시드 데이터의 부품명/가격이 현실적인지 감수 (냉각팬 3만원대 등)

## M2~M4 중

- [ ] **시스템 프롬프트의 안전 경고 문구 최종 검수** (안전 관련은 사람이 승인) — safety-guardrail 스킬 규칙 5
  - 파일: `backend/agent/prompts.py` · 검수 대상 상수: **`SAFETY_BASELINE`** (`text` / `pages` / `approved_at`)
    - 같이 볼 것: `SAFETY_SOURCES`(문장별 매뉴얼 원문 근거), `QUALIFIED_WORKER_NOTE`(전문 기술자 원칙, 근거 페이지가 달라 분리), `DANGER_KEYWORDS`(안전 블록 발행 트리거)
  - 확인 포인트 ①: `SAFETY_BASELINE["text"]` 의 방전 대기 기준값이 **"10분 이상"** 인가 (기준값 자체는 2026-07-18 승인 완료 — 축소 표기 금지). 남은 건 **paraphrase 된 문장 표현이 매뉴얼 의미를 넘지 않는가**
  - 확인 포인트 ②: `SAFETY_BASELINE["pages"]` = **iG5A 4 / S100 2 (PDF 물리 페이지, D26)**. 인쇄 페이지로 바꾸지 말 것 — 환산은 `backend/manifest.to_print_page()` 1곳 담당 (D32·D49)
  - 확인 포인트 ③: `SAFETY_SOURCES` 의 원문 인용이 실제 매뉴얼 문장과 일치하는가 (iG5A 표준본 p.4 · S100 p.2 · 보조: iG5A 트러블슈팅 p.6)
  - 검수 전에도 **런타임은 막지 않는다** (게이트하면 안전 블록이 아예 안 나가 더 위험). 회귀: `uv run python spikes/prompt_rules.py`
  - 문안을 고치면 `docs/03_WIREFRAME.html`·`docs/02_SCENARIOS.md`·`docs/06_REPO_API.md §평가` 의 안전 문구 표기와 함께 맞출 것
- [x] ~~**`DANGER_KEYWORDS` 확장 4종 + 공백 정규화 검수** (방열핀·히트싱크·냉각팬·쿨링팬)~~ —
  **2026-07-28 승인 완료.** 네 단어 모두 함체 개방을 전제하는 작업이라 안전 경고 트리거로
  타당하다고 확인. 과잉 경고(진단 서술의 단순 언급까지 걸리는 것)는 안전 쪽으로 완화하는
  방향이라 감수 — 누락보다 낫다. 파일: `backend/agent/prompts.py` `DANGER_KEYWORDS` 끝 4종 ·
  회귀: `spikes/prompt_rules.py` ⑮
- [ ] 평가셋 20문항의 기대 정답(부품·분기) 확정
- [ ] 데모 영상 촬영 (S1→S2→S3→S4 순서, 화면 A/B 전환 포함)
- [ ] README에 데모 GIF + 평가 결과표 삽입

## 결정 대기 (Claude와 의논)

- [ ] 프론트엔드 스택 (React vs 단순 HTML) — M3 전까지
- [ ] 임베딩 모델/벡터스토어 선택 — M1 EDA에서 매뉴얼 분량 보고
- [ ] 표 추출 전략 (파서 vs 비전 모델) — EDA 결과로 결정
