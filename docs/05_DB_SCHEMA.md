# 목업 DB 스키마 v0.2
SQLite 기준 (목업이므로 파일 DB로 충분, 실서비스 가정 시 PostgreSQL 치환 가능)

도구가 읽는 테이블 — 설계하며 6개 → 8개(`error_codes`·`equipment` 추가, D11)
→ 구현 정합화에서 **9개**로 확정: `traces`(실행 로그 영속화, D21) 추가.

> **세는 단위 주의:** 위 숫자는 아래 **절(§) 개수**다. §7이 `suppliers`와 `supplier_parts`
> 두 테이블을 함께 다루므로 실제 `CREATE TABLE` 은 **10개**다 (`data/seed.py` 기준).

---

## ERD 개요

```
equipment ──< error_history >── error_codes
                                    │ (model+code 복합키)
parts ──< inventory
  │
  ├──< part_alternatives (self-ref)
  └──< supplier_parts >── suppliers
  │
  └──< po_drafts >── suppliers
         │ (session_id)
       traces                        ← 세션별 실행 로그 (D21)
```

---

## 1. error_codes — 에러코드 마스터 ★매뉴얼에서 구조화 추출

> `lookup_error_code`의 원천. M1에서 매뉴얼 PDF 표 → 이 테이블로 추출하는 게 최대 작업.

```sql
CREATE TABLE error_codes (
  model        TEXT NOT NULL,          -- 'iG5A' | 'S100'
  code         TEXT NOT NULL,          -- 대문자 canonical: 'OHT', 'OCT' ... (D25, lookup은 case-insensitive)
  display_code TEXT,                   -- 키패드 원표기 보존: 'oht', 'OHt' ... (D25)
  error_name   TEXT NOT NULL,
  severity     TEXT NOT NULL,          -- 'warning' | 'fault' | 'critical'
  causes       TEXT NOT NULL,          -- JSON array
  actions      TEXT NOT NULL,          -- JSON array
  related_parts TEXT,                  -- JSON array of part_no (부품 특정의 연결고리!)
  manual_page  INTEGER NOT NULL,       -- 근거 인용 필수 — PDF 물리 페이지 기준 (D26)
  PRIMARY KEY (model, code),           -- ★ 복합키 = "같은 코드, 다른 의미" 구현
  -- code 형식 제약 (D33): 대문자·숫자·언더스코어 2~4자.
  -- 실측 64건 전부 이 범위 (3자 51 / 4자 12 / 2자 1, 최장 'FLTL'·'RERR' 등 4자)
  CHECK (length(code) BETWEEN 2 AND 4
         AND code = upper(code)
         AND code NOT GLOB '*[^A-Z0-9_]*')
);
```

**설계 포인트:** `related_parts`가 진단→조달을 잇는 다리. 이 컬럼이 없으면 "부품 특정"을 LLM 추측에 맡기게 됨.

## 2. equipment — 설비 마스터

```sql
CREATE TABLE equipment (
  equipment_id TEXT PRIMARY KEY,       -- 'INV-L3-01'
  line_id      INTEGER NOT NULL,       -- 3
  model        TEXT NOT NULL,          -- 'iG5A'
  installed_at DATE,
  location     TEXT                    -- '3번 조립라인 분전반'
);
```

## 3. error_history — 에러 발생 이력 (확정 기능 ①의 원천)

```sql
CREATE TABLE error_history (
  id           INTEGER PRIMARY KEY,
  equipment_id TEXT NOT NULL REFERENCES equipment,
  code         TEXT NOT NULL,
  occurred_at  DATETIME NOT NULL,
  action_taken TEXT,                   -- '리셋', '냉각팬 청소' ...
  part_replaced TEXT,                  -- part_no or NULL
  resolved     BOOLEAN DEFAULT 1
);
```

**시드 전략:** AI허브 「기계시설물 고장 예지 센서」의 고장 유형 4종 분포를 참고해 6개월치 이력 생성. 대부분 단발, **INV-L3-01의 OCt만 30일 내 3건** 심어 S3 트리거.

**쓰기 경로 (D29):** 이 테이블에 INSERT하는 곳은 `POST /api/equipment/{id}/errors` **하나뿐**이며, 정비사가 화면 A에서 명시적으로 기록 액션을 눌렀을 때만 호출된다. MCP 도구에는 쓰기 권한이 없고(D10), 채팅 진입만으로 자동 기록하지 않는다 — 자동 기록하면 `count`가 질문 횟수가 되어 `repeated` 판정이 오염된다.

## 4. parts — 부품 마스터

```sql
CREATE TABLE parts (
  part_no      TEXT PRIMARY KEY,       -- 'FAN-IG5-01'
  name         TEXT NOT NULL,          -- '냉각팬'
  category     TEXT,                   -- '냉각' | '제어' | '전원' ...
  compatible_models TEXT NOT NULL,     -- JSON array ['iG5A']
  discontinued BOOLEAN DEFAULT 0       -- 단종 → 대체품 분기 재료
);
```

## 5. part_alternatives — 호환 대체품 (self-reference)

```sql
CREATE TABLE part_alternatives (
  part_no      TEXT REFERENCES parts,
  alt_part_no  TEXT REFERENCES parts,
  compat_confirmed BOOLEAN NOT NULL,   -- false면 도구가 제안 금지
  note         TEXT,
  PRIMARY KEY (part_no, alt_part_no)
);
```

## 6. inventory — 재고

```sql
CREATE TABLE inventory (
  part_no      TEXT PRIMARY KEY REFERENCES parts,
  qty          INTEGER NOT NULL,
  safety_stock INTEGER NOT NULL DEFAULT 0,
  location     TEXT                    -- '자재창고 A-12'
);
```

## 7. suppliers + supplier_parts — 공급사·견적

```sql
CREATE TABLE suppliers (
  supplier_id  TEXT PRIMARY KEY,       -- 'SUP-A'
  name         TEXT NOT NULL,
  contact      TEXT                    -- 에스컬레이션 초안에 사용
);

CREATE TABLE supplier_parts (
  supplier_id  TEXT REFERENCES suppliers,
  part_no      TEXT REFERENCES parts,
  lead_days    INTEGER NOT NULL,
  unit_price   INTEGER NOT NULL,
  moq          INTEGER DEFAULT 1,
  PRIMARY KEY (supplier_id, part_no)
);
```

## 8. po_drafts — 발주서

```sql
CREATE TABLE po_drafts (
  po_id        TEXT PRIMARY KEY,       -- 'PO-0117'
  part_no      TEXT NOT NULL REFERENCES parts,
  qty          INTEGER NOT NULL,
  supplier_id  TEXT NOT NULL REFERENCES suppliers,
  model        TEXT,                   -- 'iG5A' | 'S100' — error_code와 항상 짝 (D33)
  error_code   TEXT,                   -- 이 발주를 유발한 에러코드. 대문자 canonical 2~4자 (D33)
  evidence     TEXT,                   -- JSON. 관찰 현상·판단 근거·비고 (D34)
  unit_price   INTEGER NOT NULL,       -- 발주 시점 단가 스냅샷. create_po_draft가 supplier_parts를 SELECT해 채움 —
                                       --   도구 파라미터가 아니므로 LLM이 가격을 지어낼 경로가 없음 (D31).
                                       --   이후 가격 변동과 무관하게 승인 시점 근거가 보존됨
  reason       TEXT NOT NULL,          -- 진단 근거 (화면 B 근거 카드 소스)
  urgency      TEXT DEFAULT 'normal',
  state        TEXT DEFAULT 'draft',   -- 'draft'|'pending'|'approved'|'rejected'
  requested_by TEXT,                   -- 정비사 — X-User 헤더에서 백엔드가 주입 (D23, 도구 파라미터 아님)
  decided_by   TEXT,                   -- 팀장 (승인/반려 시) — X-User에서 주입
  session_id   TEXT,                   -- 이 발주를 만든 대화 세션 (D21) — 화면 B "실행 로그 보기" 링크의 키
  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,

  -- (model, error_code)는 error_codes 복합키를 참조 — code 단독으로는 "같은 코드, 다른 의미"가
  -- 발주 이력에서 무너짐 (D13). 존재하지 않는 코드는 FK가 튕겨내므로 LLM이 지어낸 코드로
  -- 발주서를 만들 수 없다 (D23·D31과 같은 논리)
  FOREIGN KEY (model, error_code) REFERENCES error_codes(model, code),

  -- code 형식: 대문자 canonical, 2~4자 (실측 64건 전부 이 범위 — 3자 51 / 4자 12 / 2자 1)
  CHECK (error_code IS NULL OR (
           length(error_code) BETWEEN 2 AND 4
           AND error_code = upper(error_code)
           AND error_code NOT GLOB '*[^A-Z0-9_]*')),
  -- 둘 다 있거나 둘 다 없거나 (model만 있고 code가 없는 상태를 막음)
  CHECK ((model IS NULL) = (error_code IS NULL)),
  CHECK (evidence IS NULL OR json_valid(evidence))
);
```

> ⚠️ **`PRAGMA foreign_keys=ON`을 커넥션마다 실행할 것.** SQLite는 FK 검증이 **기본 OFF**다. 이걸 안 켜면 위 복합 FK가 조용히 무시되어 매뉴얼에 없는 코드로도 발주서가 만들어진다 — D33의 보증이 통째로 사라진다. `mcp_server/db.py`의 커넥션 팩토리에서 강제한다.

**검증 완료 (2026-07-23):** 위 DDL을 SQLite에서 실제로 실행해 9개 케이스를 확인했다 — 정상 발주·코드 없는 발주(S2)는 통과, 지어낸 코드(FK)·소문자·5자·특수문자·model만 있는 상태·깨진 JSON·**기종 오배정(S100 코드를 iG5A로)**은 전부 거부.

**`error_code`가 NULL 허용인 이유 (D33):** S2는 **진단 없이 중간 진입**한다("S100 인버터 제어보드 교체해야 해"). 에러코드 없는 발주가 예외가 아니라 정상 케이스이므로 NOT NULL로 잠그면 S2가 막힌다. 대신 값이 있으면 FK로 실재하는 코드임을 강제한다.

### `evidence` JSON 구조 (D34)

`reason`(한 줄 요약)과 역할이 다르다. **`reason`은 승인자가 3초 안에 읽는 헤드라인**(D5, 화면 B 근거 카드의 제목), **`evidence`는 펼쳐서 확인하는 뒷받침**이다.

```json
{
  "symptoms": ["냉각팬 소음 증가", "3번 라인 2회 정지"],
  "basis": [
    { "tool": "lookup_error_code",  "code": "OHT", "manual_page": 202 },
    { "tool": "get_error_history",  "count": 3, "window_days": 30, "repeated": true },
    { "tool": "search_inventory",   "part_no": "FAN-IG5-01", "qty": 1, "safety_stock": 3 }
  ],
  "notes": "야간조 정비사 육안 확인 — 팬 회전 불량"
}
```

| 키 | 내용 | 출처 |
|---|---|---|
| `symptoms` | **어떤 현상을 보고 고장으로 판단했는지** — 관찰된 증상 | 사용자 발화에서 에이전트가 추출 |
| `basis` | 판단을 뒷받침한 도구 결과 (코드 정의·이력·재고) | 도구 출력 — `traces`와 대조 가능 |
| `notes` | 자유 비고·기타 상황 (구두 보고, 현장 특이사항 등) | 사용자 발화 / 정비사 입력 |

세 키 모두 optional. 승인자가 "왜 이 부품을 지금 사야 하는가"를 대화를 안 읽고 판단할 수 있게 하는 게 목적이다.

**권한 규칙(코드 레벨 강제):** MCP 도구는 `state='draft'`로 INSERT만 가능. `draft→pending`은 정비사 UI("승인 요청"), `pending→approved/rejected`는 팀장 UI만. 도구에 UPDATE 권한 자체를 안 줌.

## 9. traces — 에이전트 실행 로그 (D21)

> SSE로 흘려보낸 trace 이벤트의 영속 사본. `GET /api/chat/{session_id}/trace`(SSE 끊김 폴백),
> 화면 B의 "실행 로그 전체 보기"(po_drafts.session_id 조인), scenario-smoke의 시퀀스 판정이 이 테이블을 읽는다.
> 도구 결과 **원문**도 여기 저장 (세션 이력에는 요약본만 — 09_RUNTIME 참조).

```sql
CREATE TABLE traces (
  id           INTEGER PRIMARY KEY,
  session_id   TEXT NOT NULL,
  seq          INTEGER NOT NULL,       -- 세션 내 이벤트 순번 (시퀀스 판정용)
  event_type   TEXT NOT NULL,          -- 'tool_call' | 'tool_result' | 'block'
  tool         TEXT,                   -- 도구명 (block 이벤트는 NULL 가능)
  payload      TEXT NOT NULL,          -- JSON 원문 (입력/출력/elapsed 등)
  ts           DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_traces_session ON traces(session_id, seq);
```

**테이블로 두지 않는 것:** 제조사 A/S 연락처(S4 안내용)는 데이터가 아니라 **설정(config) 상수** — 공급사(suppliers.contact)와 성격이 다르고 기종당 1개뿐이라 테이블이 과함.

---

## 시드 데이터 전략 — "일부러 꼬아놓은" 케이스 맵

| 케이스 | 시드 | 검증 시나리오 |
|---|---|---|
| 정상 발주 | FAN-IG5-01: qty 1, safety_stock 3 (미달) | S1 |
| 재고 0 + 대체품 有 | PCB-S100-CTRL: qty 0, 단종, 대체품 R2 (confirmed) | S2 |
| 대체품도 없음 | 특정 전원모듈: qty 0, 대체품 無 | S2 서브 (에스컬레이션) |
| 리드타임 트레이드오프 | 냉각팬: A사 3일/₩38,000 vs B사 14일/₩29,000/MOQ 10 | S1·화면 B 비교 |
| 반복 고장 | INV-L3-01 OCt 30일 내 3건 (매번 '리셋'만) | S3 |
| 미확인 호환 | 대체품 1건 compat_confirmed=false | 제안 금지 검증 |
| 규모감 | 부품 ~40종, 설비 ~10대, 공급사 4곳, 이력 ~200건 | 데모 현실감 |

## 다음 단계 (M1 착수 순서)
1. LS 매뉴얼 2종(iG5A, S100) 다운로드 → 에러코드 표 추출 → `error_codes` 적재 (최대 리스크 구간)
2. 시드 생성 스크립트 (`seed.py`) — 위 케이스 맵 그대로
3. MCP 서버 골격 + 도구 7종(읽기 6+쓰기 1) 연결
