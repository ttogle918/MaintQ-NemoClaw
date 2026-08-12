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
- [x] **`related_parts` 수작업 매핑 검수** — ✅ **2026-08-12 사용자 최종 승인 완료 (D12 게이트 해제)** — 파일: `data/related_parts.seed.json`.
  **2026-08-05 Claude 위임 판정 완료(8코드)** — 사용자가 이 건에 한해 위임. 매뉴얼 조치문
  (iG5A p.202~204 · S100 §9.2 p.420~421)을 직접 대조해 판정했고, 각 항목에
  `reviewed_by: "claude (사용자 위임, 2026-08-05)"` 와 `verdict` 를 남겼다.
  주요 변경: iG5A OCT 에서 모터 제거 · iG5A GFT 에 모터 추가 · **S100 OCT 반려(빈 목록)** ·
  S100 GFT 신규. 근거는 `docs/sessions/2026-08-05.md` §2.
  - [x] **사람 최종 승인 — 2026-08-12 완료.** 사용자가 내용을 확인하고 승인했다.
    위임 이력은 지우지 않고 두 단계를 모두 남긴다(`_승인_이력`) — 누가 무엇을 판단했는지가 지워지면 승인의 의미가 사라진다.
  - ✅ 이제 부품 특정 정확률을 **실적으로 인용할 수 있다**. 첫 실적: **40.0%**(목표 ≥90%, `20260812-075303` 3회차)
- [ ] 두 기종 간 동일 표기 코드 목록 확인 (OL, OC 계열) — "같은 코드, 다른 의미" 실증 자료
- [ ] 시드 데이터의 부품명/가격이 현실적인지 감수 (냉각팬 3만원대 등)
- [ ] **`parts.part_class` 40종 감수** (신규, Sprint 6 Stage 2) — 파일: `data/seed.py` 의 `PARTS` 상수.
  `CONSUMABLE` 14 / `CRITICAL` 26 으로 분류돼 있고 **`assess_repair_value` 의 수리/교체/매각 3지 판단에 직접 영향**한다.
  `related_parts` 와 같은 성격(D12) — 미검수 상태로도 코드는 돌고, 시드가 매 실행 `part_class_caveat()` 경고를 찍는다.
  - 특히 볼 것: 명세 열거 밖이라 **추측으로 분류한 9종**(히트싱크·키패드·센서 3종·접촉기·SPD·커플링·제동저항·케이블)
  - `FAN-IG5-01` = `CRITICAL` 은 S1 주인공이라 3지 판단 데모가 성립해야 해서 그렇게 뒀다 — 동의 여부 확인

## Sprint 7 사람 판단 대기 (지금 가장 급한 것)

> **외부 블로커는 해소됐다.** `LAW_API_OC` 발급·조문 실수집이 끝나 스프린트를 막는 항목은 없다.
> 남은 것은 전부 **사람의 값 판단**이며, 미해결 상태로도 코드는 돈다(그 사실이 출력에 드러난다).
>
> 📌 **확인 시점: 스프린트 종료 후 일괄** (2026-08-10 사용자 결정). 스테이지마다 멈추지 않고
> 여기에 누적한다. Stage 별 자동 파이프라인은 이 항목들에 막히지 않고 계속 진행한다.

### 🔐 Stage 1 — 보안 (push 전 반드시 결정)

- [ ] **로컬 커밋 2개에 법제처 인증값 평문이 남아 있다** — `c3a46c8`·`4dc6448`
  - 작업 트리·인덱스는 정리 완료(`git grep` 0건) + 재발 방지 회귀 `law_fetch_contract ⓚ` 추가
  - **두 커밋 모두 원격에 없다** (`origin/master` 는 그보다 앞선 `c118074`) → **지금 push 하면 유출된다**
  - 선택지 ⓐ 그대로 두고 push 안 함 ⓑ 히스토리 재작성 후 push
    ⚠ `4dc6448` 은 병렬 세션의 코드 커밋이라 재작성하면 **이후 커밋이 전부 리베이스**된다
  - 값 자체는 공개 GitHub 사용자명과 동일해 민감도는 낮다 — 판단 재료로 참고

### 📄 Stage 1 — 조문 정정 승인

- [ ] **`KR-CITA-ENF-31` 제목 정정** — 등록 `즉시상각의제` vs API `즉시상각의 의제`
  - 계층 1의 **마지막 `PENDING` 1건**. 처분 룰이 인용하지 않아 S9/S10 은 막지 않는다
  - 승인 시: `data/rules/laws/KR-CITA-ENF-31.json` 제목 수정 → `fetch_laws.py --fetch-all` → 재시드
- [ ] **`KR-STTC-146` 정정 확인** (`세액공제액의 추징` → `감면세액의 추징`, 2026-08-09 승인분)
  - BLOCKING 룰 `TAX-CREDIT-2Y` 의 **근거 조문 정체성 키**를 바꾼 변경이라 눈으로 한 번 더 볼 값

### 📊 Stage 1 — 3차 평가 결과 판단

- [ ] **`data/analysis/eval_gap_3rd.md` §6 후보 6건의 우선순위 동의 여부**
  - 계측(traces 보존 · 반복 실행)을 프롬프트 수정보다 **앞**에 뒀다 — 지금은 개선과 실행 간 요동을 구분할 수 없기 때문
  - ⚠ S2 안전 경고 누락은 **고치면 안 되는 실패**다. 매뉴얼 근거가 없어 안전 문구를 못 낸 것이며,
    문구를 넣는 방향으로 고치면 절대 규칙 위반이 된다. 고칠 것은 RAG 미호출이다
- [ ] **`docs/status/maintq-data-map.html`** — 법령 원문 배지를 `앞으로 만들 데이터 → 실제 데이터` 로 옮겼다.
  3분류 축 재배치가 의도와 맞는지

- [x] ✅ **law.go.kr OPEN API 활용신청 → `.env` 의 `LAW_API_OC` 기입** — **완료.** 발급·실호출 검증까지 끝났고
  Sprint 7 MQ-701 이 조문을 실수집했다 (`data/analysis/law_fetch.md`)
  - ⚠ **인증값은 API 키가 아니라 "신청 이메일 ID 앞부분"** 이다. 그래서 변수명에 "KEY" 가 들어가지 않고
    **`LAW_API_OC`** 다 (구 변수명 폴백은 `data/rules/fetch_laws.py:41` 한 곳에만 남아 있다)
  - 기입 위치: `.env` (`.env.example §외부 데이터 원천` 참고). ⛔ **값 자체는 저장소·로그·문서 어디에도 적지 않는다**
    — 회귀 `spikes/law_fetch_contract.py ⓚ` 가 추적 파일에 평문이 없음을 단언한다
  - **풀린 것**: 조문 6건 수집 완료 → `build_evidence_bundle` 이 9자산 × SALE/SCRAP **18조합 전부 `ok`**
    (`law_text_unavailable` 0건) → 계층 3 서명·S10 의 하드 선행 조건이 사라졌다

- [ ] 🟡 **`KR-CITA-ENF-31` 등록 제목 정정 승인** ← 계층 1 의 마지막 `PENDING` 1건
  - 등록값 `즉시상각의제` vs 법제처 `조문제목` `즉시상각의 의제` (**공백 1칸 차이**)
  - 수집기는 **자동 정정하지 않고 중단**했다(`LawMismatchError`, D75) — 파일 md5 불변. 조용히 덮어쓰면
    다른 조문을 같은 조문으로 읽는 경로가 열리므로 **중단이 정상 동작**이다
  - 사람이 판단할 것: 등록 제목을 API 값으로 고칠 것인가. 고치면 `data/rules/laws/KR-CITA-ENF-31.json` 의
    `title` 만 정정 → `uv run python data/rules/fetch_laws.py --fetch-all` → `uv run python data/seed.py --with-error-codes`
  - **막히는 것**: `classify_expenditure` 의 `evidence_completeness` 뿐이다. 처분 룰 5종은 이 조문을
    **인용하지 않으므로**(참조 0건) S9·S10 영향은 없다
- [ ] 🔴 **`N = 8`(제조업 기계장치 기준내용연수) 법령 원문 대조** — **잔가곡선 전체가 이 값 하나에 걸려 있다**
  - 근거 문서: `data/analysis/residual_curve.md §2-2` (현재 **미검증** 표시)
  - 대조 대상: 법인세법 시행규칙 **별표5·별표6**(기준내용연수 및 내용연수범위표). 내용연수범위 6~10년의 중앙값 8을 임시로 썼다
  - 값이 바뀌면 `residual_curve` 전 행이 바뀌고 `assess_repair_value` 의 `SELL_AS_IS`/`REPAIR_RECOMMENDED` 경계가 이동한다
  - ⚠ `LAW_API_OC` 는 이제 있으므로 **별표서식 API 로 대조 시도가 가능**하다. 단 별표5·6 은 `data/rules/laws/`
    에 등록된 조문 7건에 **포함되지 않는다**(조문 API 가 아니라 별표서식 API 대상) — **값 채택은 사람 판단**이다
- [ ] **`RESIDUAL_AT_LIFE_END = 0.50` 가정 동의 여부** — N년 시점 잔가율을 50%로 뒀다
  - 세법 잔존가액 `0.05` 를 **그대로 쓰지 않은 이유**는 `residual_curve.md §2-3` 에 있다(세무상 상각 한도이지 시장가가 아니다)
  - 이건 **법령 근거가 없는 순수 가정**이다. 동의하지 않으면 값과 함께 `source` 문구를 고칠 것

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
- [x] ~~평가셋 20문항의 기대 정답(부품·분기) 확정~~ — **2026-07-29 승인 완료.** `eval/testset_draft.json` 그대로 승인, `eval/testset.json` 반영(사람이 직접 cp 실행). D12 경고: 부품 특정 정확률은 `related_parts` 검수 완료 전 실적 인용 금지 유지
- [ ] 데모 영상 촬영 (S1→S2→S3→S4 순서, 화면 A/B 전환 포함)
- [ ] README에 데모 GIF + 평가 결과표 삽입

## 결정 대기 (Claude와 의논)

- [ ] 프론트엔드 스택 (React vs 단순 HTML) — M3 전까지
- [ ] 임베딩 모델/벡터스토어 선택 — M1 EDA에서 매뉴얼 분량 보고
- [ ] 표 추출 전략 (파서 vs 비전 모델) — EDA 결과로 결정
