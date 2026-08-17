# 재고 드로어 (A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 수리가치판단 화면(`RepairValuePanel`)에서 판정이 나오면 해당 부품의 재고를 자동 조회해 표시하고, 우측 드로어(`InventoryDrawer`)로 상세(재고 수량·공급사 비교)를 보여준다. "발주하러 가기" 버튼은 기존 채팅 prefill 경로로 이동한다(새 쓰기 경로 없음).

**Architecture:** 기존 MCP 도구 `search_inventory`의 로직을 `data/inventory.py`(공유 계층)로 옮기고, MCP 도구는 얇은 위임으로 축소한다(Stage 2 `data/maint_value.py` 선례와 동일 패턴, D101·D73). 새 `backend/services/inventory.py` + `backend/routers/inventory.py`가 그 공유 로직을 호출해 REST로 노출한다(`core` 프로파일에서도 동작, D73). 프론트는 `CriticalityDrawer.tsx`와 동일한 오버레이 패턴으로 `InventoryDrawer.tsx`를 만든다.

**Tech Stack:** Python 3.11 / FastAPI / SQLite (백엔드) · Next.js 14 (App Router) / React / TypeScript, 인라인 스타일(`sx()` 헬퍼) (프론트)

## Global Constraints

- MCP 도구는 예외를 던지지 않고 `status` 필드로 실패 반환한다 (D9)
- `data/` 모듈은 `mcp_server`를 import하지 않는다 (D15) — 커넥션은 호출자가 `mode=ro`로 열어 넘긴다
- REST 오류 매핑은 도구 `status`/`reason`을 재포장하지 않고 그대로 싣는다 (`06_REPO_API.md §2.6` 규약)
- 신규 REST 경로는 역할 게이트(`require()`)를 두지 않는다 — 읽기 판정이라 403이 나오지 않는다(기존 `maint_value.py` 5경로와 같은 이유)
- 프론트 컴포넌트는 `frontend/lib/mappers.tsx`의 전역 매퍼만 어휘·색을 정한다 — 컴포넌트 파일 안에서 상태 문자열을 직접 비교하지 않는다 (D87)
- `null`/빈 재고를 `0`이나 "충분"으로 접지 않는다 (D62)
- 커밋 메시지는 한국어, 실제로 `uv run ruff check` / `npx tsc --noEmit` / `npm run build`를 실행해서 결과를 확인한 뒤에만 "통과" 표현을 쓴다

---

## Task 1: `search_inventory` 로직을 `data/inventory.py`로 추출

**Files:**
- Create: `data/inventory.py`
- Modify: `mcp_server/tools/search_inventory.py`

**Interfaces:**
- Produces: `data.inventory.search(con: sqlite3.Connection, *, part_no: str | None = None, part_name: str | None = None, model: str | None = None) -> dict` — 이후 Task 2(백엔드)가 이 함수를 그대로 호출한다.

- [ ] **Step 1: `data/inventory.py` 작성**

기존 `mcp_server/tools/search_inventory.py`(전체 내용은 아래 "현재 코드" 참고)의 SQL·검증 로직을 그대로 옮긴다. 커넥션은 호출자가 연다(`data/maint_value.py`와 같은 규약 — `read_only()`를 import하지 않는다).

```python
# -*- coding: utf-8 -*-
"""재고 조회 — 공유 데이터 계층 (D101·D73).

`mcp_server/tools/search_inventory.py`(MCP 도구)와 `backend/services/inventory.py`
(REST) 둘 다 이 모듈을 부른다 — 산식이 두 벌 존재하는 것을 막는다(Stage 2
`data/maint_value.py` 선례와 같은 이유).

커넥션은 호출자가 `mode=ro`로 열어 넘긴다 — 이 모듈은 `mcp_server`를 import하지
않는다(D15).
"""

from __future__ import annotations

import json
import sqlite3

VALID_MODELS = ("iG5A", "S100")


def search(
    con: sqlite3.Connection,
    *,
    part_no: str | None = None,
    part_name: str | None = None,
    model: str | None = None,
) -> dict:
    if not part_no and not part_name:
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": "part_no 또는 part_name 중 하나는 필요합니다",
        }
    if model is not None and model not in VALID_MODELS:
        return {
            "status": "error",
            "reason": "invalid_model",
            "message": f"model은 iG5A|S100 이어야 합니다: {model!r}",
        }

    sql = [
        "SELECT p.part_no, p.name, p.compatible_models, p.discontinued,",
        "       i.qty, i.safety_stock, i.location",
        "FROM parts p JOIN inventory i ON i.part_no = p.part_no",
        "WHERE 1=1",
    ]
    args: list[object] = []
    if part_no:
        sql.append("AND p.part_no = ?")
        args.append(part_no)
    if part_name:
        # 양쪽의 공백을 지우고 비교한다 — search_inventory.py 원본 주석 그대로 유지
        sql.append("AND REPLACE(p.name, ' ', '') LIKE ?")
        args.append(f"%{part_name.replace(' ', '')}%")

    try:
        rows = con.execute(" ".join(sql), args).fetchall()
    except sqlite3.Error as e:
        return {"status": "error", "reason": "db_error", "message": str(e)}

    items = []
    for r in rows:
        models = json.loads(r["compatible_models"])
        if model and model not in models:
            continue
        items.append(
            {
                "part_no": r["part_no"],
                "name": r["name"],
                "qty": r["qty"],
                "safety_stock": r["safety_stock"],
                "location": r["location"],
                "compatible_models": models,
                "discontinued": bool(r["discontinued"]),
            }
        )

    if not items:
        return {"status": "not_found", "items": []}
    return {"status": "ok", "items": items}
```

- [ ] **Step 2: `mcp_server/tools/search_inventory.py`를 얇은 위임으로 축소**

`DESCRIPTION` 상수는 도구 파일에 그대로 남긴다(정본 위치, `04_MCP_TOOLS.md §설계원칙 3`). 출력 dict를 한 글자도 바꾸지 않는다 — 원본과 완전히 동일해야 한다.

```python
# -*- coding: utf-8 -*-
"""search_inventory — 재고 조회 (docs/04_MCP_TOOLS.md §4).

산출 로직은 `data/inventory.py`(D101) — 이 파일은 얇은 위임이다.
실패는 예외가 아니라 status 로 반환한다 (D9) — 에이전트가 S2 분기를 판단해야 하므로.
"""

from __future__ import annotations

from data import inventory as data_inventory

from ..db import read_only

DESCRIPTION = (
    "부품의 재고·안전재고·단종 여부를 조회한다. part_no를 알면 part_no로, 사용자가 부품을 "
    "이름으로만 말했으면 part_name으로 조회할 것. part_name으로 조회할 때는 model을 반드시 "
    "함께 지정할 것 — 지정하지 않으면 다른 기종 부품이 섞여 나온다."
)


def search_inventory(
    part_no: str | None = None,
    part_name: str | None = None,
    model: str | None = None,
) -> dict:
    try:
        with read_only() as con:
            return data_inventory.search(con, part_no=part_no, part_name=part_name, model=model)
    except FileNotFoundError as e:
        return {"status": "error", "reason": "db_missing", "message": str(e)}
```

- [ ] **Step 3: 회귀로 동일 동작 확인**

```bash
uv run python spikes/asset_tools_contract.py
uv run ruff check data mcp_server
```

Expected: `asset_tools_contract.py`가 **49건 전건 통과**(이 스위트가 `search_inventory`를 포함한 코어 도구 계약을 검사한다 — 정확한 대상 여부를 스위트 출력에서 직접 확인할 것. `search_inventory`를 직접 검사하는 별도 스위트가 없다면, 실제 도구 호출로 원본과 동일 출력이 나오는지 아래 수동 확인을 추가로 할 것):

```bash
uv run python -c "
from mcp_server.tools.search_inventory import search_inventory
r = search_inventory(part_no='FAN-IG5-01')
print(r)
assert r['status'] == 'ok'
assert r['items'][0]['part_no'] == 'FAN-IG5-01'
print('OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add data/inventory.py mcp_server/tools/search_inventory.py
git commit -m "$(cat <<'EOF'
[M3] search_inventory 로직을 data/inventory.py 로 위임 (D101·D73)

Stage 2 data/maint_value.py 와 같은 패턴 — MCP 도구와 REST 가 같은 함수를
호출하게 하기 위한 선행 리팩터. 출력 dict 무변경(리팩터, 기능 변경 아님).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 백엔드 REST 노출 — `GET /api/inventory`

**Files:**
- Create: `backend/services/inventory.py`
- Create: `backend/routers/inventory.py`
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: `data.inventory.search`(Task 1)
- Produces: `GET /api/inventory?part_no=...` · `GET /api/inventory?part_name=...&model=...` — 이후 Task 3(프론트)이 이 경로를 호출한다. 응답 형태는 `data.inventory.search`의 반환값과 동일(`{"status": "ok", "items": [...]}` 등).

- [ ] **Step 1: `backend/services/inventory.py` 작성**

`backend/services/maint_value.py`(Stage 4 산출물)와 같은 형태 — `data.inventory`를 호출하는 얇은 서비스 계층. `mcp_server`는 import하지 않는다(D15).

```python
# -*- coding: utf-8 -*-
"""재고 조회 서비스 — `data.inventory` 위임 (D101·D73).

`mcp_server` 를 import하지 않는다(D15) — REST 와 MCP 도구가 `data/inventory.py`
하나만 공유한다.
"""

from __future__ import annotations

from data import inventory as data_inventory

from .disposal import read_only


def search(*, part_no: str | None = None, part_name: str | None = None, model: str | None = None) -> dict:
    with read_only() as con:
        return data_inventory.search(con, part_no=part_no, part_name=part_name, model=model)
```

(`backend/services/disposal.py`의 `read_only`를 재사용한다 — `backend/services/maint_value.py`도 이미 같은 임포트를 쓴다. 먼저 `backend/services/disposal.py`를 열어 `read_only`가 실제로 export되는 이름인지 확인할 것.)

- [ ] **Step 2: `backend/routers/inventory.py` 작성**

`backend/routers/maint_value.py`의 `_status_code`/`_respond` 패턴을 그대로 따른다.

```python
# -*- coding: utf-8 -*-
"""재고 조회 REST 노출 (D73).

```
GET /api/inventory?part_no=...                    → search_inventory
GET /api/inventory?part_name=...&model=...         → search_inventory
```

역할 게이트를 두지 않는다 — 읽기 판정이라 403이 나오지 않는다(`maint_value.py` 5경로와
같은 이유). `core` 프로파일에서도 동작한다(MCP 프로세스를 거치지 않는다, D73).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from backend.deps import Caller, caller
from backend.services import inventory as svc

router = APIRouter(prefix="/api", tags=["inventory"])

_REASON_HTTP: dict[str, int] = {
    "invalid_input": 422,
    "invalid_model": 422,
}


def _status_code(result: dict) -> int:
    status = result.get("status")
    if status == "ok":
        return 200
    if status == "not_found":
        return 404
    return _REASON_HTTP.get(result.get("reason"), 500)


@router.get("/inventory")
def get_inventory(
    part_no: str | None = None,
    part_name: str | None = None,
    model: str | None = None,
    c: Caller = Depends(caller),
) -> JSONResponse:
    """재고·안전재고·단종 여부 조회. `part_no` 또는 `part_name`(+선택 `model`) 중 하나 필요."""
    result = svc.search(part_no=part_no, part_name=part_name, model=model)
    return JSONResponse(status_code=_status_code(result), content=result)
```

- [ ] **Step 3: `backend/main.py`에 라우터 등록**

`backend/main.py`를 열어 기존 `app.include_router(maint_value.router)` 줄 바로 아래에 다음을 추가한다(정확한 import 줄 위치는 파일을 열어 기존 import 블록에 맞춰 넣을 것):

```python
from backend.routers import inventory  # 다른 라우터 import 옆에 추가
...
app.include_router(inventory.router)  # 다른 include_router 옆에 추가
```

- [ ] **Step 4: 수동 확인 + 회귀**

```bash
uv run python data/seed.py --with-error-codes
nohup uv run uvicorn backend.main:app --port 8020 > /tmp/inv_test.log 2>&1 &
sleep 3
curl -s "http://127.0.0.1:8020/api/inventory?part_no=FAN-IG5-01"
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8020/api/inventory"
curl -s "http://127.0.0.1:8020/health"
```

Expected: 첫 번째 호출이 `{"status":"ok","items":[...]}` (FAN-IG5-01 포함), 두 번째(파라미터 없음)가 **422**, `/health`가 `tools_profile:"core"`(core 프로파일에서도 동작함을 증명). 확인 후 서버 종료:

```bash
kill %1
uv run python spikes/api_contract.py
uv run ruff check backend
```

Expected: `api_contract.py` **28건 무증감 통과**(이 REST 경로는 새 도구 계약을 안 건드리므로 기존 스위트가 그대로 통과해야 한다).

- [ ] **Step 5: Commit**

```bash
git add backend/services/inventory.py backend/routers/inventory.py backend/main.py
git commit -m "$(cat <<'EOF'
[M3] GET /api/inventory 신설 (D73)

data.inventory.search 위임, core 프로파일에서도 동작. 역할 게이트 없음(읽기 판정).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 프론트 API 배관

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Consumes: `GET /api/inventory`(Task 2)
- Produces: `getInventory(role: Role, params: {part_no?: string; part_name?: string; model?: string}) => Promise<ApiInventory>` · `type ApiInventory` · `type ApiInventoryItem` — 이후 Task 4(`InventoryDrawer`)가 이 함수·타입을 쓴다.

- [ ] **Step 1: `frontend/lib/api.ts`에 타입·함수 추가**

`ApiCriticality`/`getCriticality` 바로 아래(라인 568 부근, `frontend/lib/api.ts:553-571` 참고)에 추가:

```ts
export interface ApiInventoryItem {
  part_no: string;
  name: string;
  qty: number;
  safety_stock: number;
  location: string;
  compatible_models: string[];
  discontinued: boolean;
}

export interface ApiInventory {
  status: string;
  items?: ApiInventoryItem[];
  reason?: string;
  message?: string;
  [k: string]: unknown;
}

export const getInventory = (
  role: Role,
  params: { part_no?: string; part_name?: string; model?: string }
) => {
  const q = new URLSearchParams();
  if (params.part_no) q.set("part_no", params.part_no);
  if (params.part_name) q.set("part_name", params.part_name);
  if (params.model) q.set("model", params.model);
  return apiFetch<ApiInventory>(`/api/inventory?${q.toString()}`, role);
};
```

- [ ] **Step 2: 타입 체크**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 에러 없음(출력 없음).

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "$(cat <<'EOF'
[M3] frontend: GET /api/inventory 배관 (getInventory, ApiInventory)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `InventoryDrawer` 컴포넌트

**Files:**
- Create: `frontend/components/asset/InventoryDrawer.tsx`

**Interfaces:**
- Consumes: `getInventory`·`ApiInventory`·`ApiInventoryItem`(Task 3), `ApiError`·`errorBody`·`extractDetail`(`frontend/lib/api.ts`, 기존)
- Produces: `<InventoryDrawer open partNo equipmentId onClose />` — 이후 Task 5(`RepairValuePanel`)가 이 컴포넌트를 쓴다.

- [ ] **Step 1: `InventoryDrawer.tsx` 작성**

`CriticalityDrawer.tsx`(`frontend/components/asset/CriticalityDrawer.tsx`, 전체 내용은 위에서 이미 확인함)와 **동일한 오버레이 구조**를 그대로 복제하되, 조회 함수와 본문만 바꾼다. "발주하러 가기" 버튼은 `/technician?prefill=...&equipment=...`로 이동한다(새 쓰기 경로 없음 — `frontend/app/(console)/technician/page.tsx`의 기존 `prefill`·`equipment` 쿼리 파라미터 재사용).

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Mono } from "@/components/ui/Mono";
import {
  ApiError,
  errorBody,
  extractDetail,
  getInventory,
  type ApiInventory,
} from "@/lib/api";
import { sx } from "@/lib/sx";

/**
 * 재고 조회 드로어 (`search_inventory`, `04 §4`, Sprint 10 브레인스토밍 A).
 *
 * `CriticalityDrawer` 와 완전히 같은 오버레이 패턴 — `RepairValuePanel` 의 "재고 보기"
 * 칩을 눌렀을 때 옆에서 펼쳐진다. 라우트를 옮기지 않고 `open`/`onClose` 로만 제어된다.
 *
 * ⛔ 발주는 이 컴포넌트가 직접 만들지 않는다 — "발주하러 가기" 는 기존 채팅 prefill
 *   경로(`/technician?prefill=...`)로 이동만 한다. `create_po_draft` 호출은 여전히
 *   에이전트가 채팅에서 한다(P39 완성 전까지의 의도적 설계 — docs/07_BACKLOG.md P39).
 */
export function InventoryDrawer({
  open,
  partNo,
  equipmentId,
  onClose,
}: {
  open: boolean;
  partNo: string | null;
  equipmentId: string | null;
  onClose: () => void;
}) {
  const [data, setData] = useState<ApiInventory | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !partNo) return;
    let alive = true;
    setLoading(true);
    setFailure(null);
    setData(null);
    getInventory("technician", { part_no: partNo })
      .then((res) => {
        if (!alive) return;
        setData(res);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError) {
          const body = errorBody(e);
          const reason = typeof body?.reason === "string" ? body.reason : "";
          const message = extractDetail(e.body);
          setFailure(reason ? `${reason} — ${message}` : message);
        } else {
          setFailure("백엔드에 연결하지 못했습니다 — 조회가 실패한 것이지 재고가 없는 것이 아닙니다.");
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [open, partNo]);

  if (!open || !partNo) return null;

  const item = data?.status === "ok" ? data.items?.[0] : undefined;
  const notFound = data?.status === "not_found";

  const prefillText = `${equipmentId ?? "해당 설비"}의 ${partNo} 재고 부족, 발주해줘`;
  const prefillHref =
    `/technician?prefill=${encodeURIComponent(prefillText)}` +
    (equipmentId ? `&equipment=${encodeURIComponent(equipmentId)}` : "");

  return (
    <>
      <div
        onClick={onClose}
        style={sx(
          "position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:40;cursor:pointer"
        )}
      />
      <aside
        style={sx(
          "position:fixed;top:0;right:0;bottom:0;width:360px;max-width:92vw;z-index:41;" +
            "background:var(--surface);border-left:1px solid var(--line);box-shadow:-8px 0 30px rgba(0,0,0,.35);" +
            "display:flex;flex-direction:column;overflow-y:auto"
        )}
      >
        <div
          style={sx(
            "display:flex;align-items:center;gap:9px;padding:13px 15px;" +
              "border-bottom:1px solid var(--line);background:var(--head)"
          )}
        >
          <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink)")}>재고 조회</span>
          <Mono size={11.5}>{partNo}</Mono>
          <div style={sx("flex:1")} />
          <button
            onClick={onClose}
            aria-label="닫기"
            style={sx(
              "border:1px solid var(--line2);background:transparent;border-radius:6px;" +
                "width:26px;height:26px;cursor:pointer;color:var(--dim);font:14px monospace"
            )}
          >
            ✕
          </button>
        </div>

        <div style={sx("padding:14px 15px;display:flex;flex-direction:column;gap:12px")}>
          {loading && (
            <div style={sx("font:12px 'Pretendard';color:var(--dim)")}>불러오는 중…</div>
          )}

          {failure && !loading && (
            <div
              style={sx(
                "border:1.5px dashed var(--error-tx);border-radius:7px;padding:10px 12px;" +
                  "font:12px/1.7 'Pretendard';color:var(--error-tx)"
              )}
            >
              <b>조회 실패</b>
              <br />
              {failure}
            </div>
          )}

          {notFound && !loading && (
            <div
              style={sx(
                "border:1.5px dashed var(--line2);border-radius:7px;padding:10px 12px;" +
                  "font:12px/1.7 'Pretendard';color:var(--dim)"
              )}
            >
              등록된 재고 정보가 없습니다.
            </div>
          )}

          {item && !loading && (
            <>
              <div
                style={sx(
                  `${item.qty > 0 ? "background:var(--ok-bg);color:var(--ok-tx)" : "background:var(--error-bg);color:var(--error-tx)"};` +
                    "border-radius:8px;padding:11px 13px;display:flex;flex-direction:column;gap:5px"
                )}
              >
                <span style={sx("font:700 14px 'Pretendard'")}>
                  {item.qty > 0 ? `재고 있음 · ${item.qty}개` : "재고 없음"}
                </span>
                <span style={sx("font:11.5px/1.6 'Pretendard'")}>
                  안전재고 {item.safety_stock}개 · 보관위치 {item.location}
                  {item.discontinued ? " · 단종" : ""}
                </span>
              </div>

              {item.qty <= item.safety_stock && (
                <Link
                  href={prefillHref}
                  style={sx(
                    "display:inline-flex;align-items:center;justify-content:center;gap:6px;" +
                      "border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:8px;" +
                      "padding:9px 12px;text-decoration:none;font:700 12.5px 'Pretendard';color:var(--blue-tx)"
                  )}
                >
                  발주하러 가기 →
                </Link>
              )}
            </>
          )}
        </div>
      </aside>
    </>
  );
}
```

- [ ] **Step 2: 타입 체크**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 에러 없음.

- [ ] **Step 3: D87 확인**

```bash
rg -n "qty > 0|qty <= " frontend/components/asset/InventoryDrawer.tsx
```

Expected: 이 두 비교는 **숫자 비교**이지 상태 문자열 비교가 아니므로 D87(어휘·색은 매퍼만) 위반이 아니다 — 참고용 확인. `rg -n "REPAIR|REPLACE|HOLD|CLEAR|CRITICAL" frontend/components/asset/InventoryDrawer.tsx` → 0건이어야 한다(이 파일이 판정 어휘를 갖지 않는지 확인).

- [ ] **Step 4: Commit**

```bash
git add frontend/components/asset/InventoryDrawer.tsx
git commit -m "$(cat <<'EOF'
[M3] InventoryDrawer 신설 — 재고 조회 오른쪽 드로어

CriticalityDrawer 와 같은 오버레이 패턴. "발주하러 가기" 는 /technician?prefill=...
로 이동만 한다 — create_po_draft 직접 호출 없음(P39 완성 전까지 의도적 설계).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `RepairValuePanel`에 연결

**Files:**
- Modify: `frontend/components/asset/RepairValuePanel.tsx`

**Interfaces:**
- Consumes: `InventoryDrawer`(Task 4)

- [ ] **Step 1: import 추가**

`frontend/components/asset/RepairValuePanel.tsx:4` 근처(`import { CriticalityDrawer } ...` 바로 아래)에 추가:

```tsx
import { InventoryDrawer } from "@/components/asset/InventoryDrawer";
```

- [ ] **Step 2: 상태 추가**

`frontend/components/asset/RepairValuePanel.tsx:48`(`const [drawerPartNo, setDrawerPartNo] = useState<string | null>(null);`) 바로 아래에 추가:

```tsx
  const [inventoryPartNo, setInventoryPartNo] = useState<string | null>(null);
```

- [ ] **Step 3: `ResultView` 호출부에 prop 추가**

`frontend/components/asset/RepairValuePanel.tsx:131-136`을 다음으로 교체:

```tsx
      {result && (
        <ResultView
          result={result}
          onOpenPart={(p) => setDrawerPartNo(p)}
          onOpenInventory={(p) => setInventoryPartNo(p)}
        />
      )}
```

- [ ] **Step 4: 드로어 렌더 추가**

`frontend/components/asset/RepairValuePanel.tsx:138-142`(`<CriticalityDrawer .../>`) 바로 아래에 추가:

```tsx
      <InventoryDrawer
        open={inventoryPartNo !== null}
        partNo={inventoryPartNo}
        equipmentId={equipmentId}
        onClose={() => setInventoryPartNo(null)}
      />
```

- [ ] **Step 5: `ResultView` 시그니처에 prop 추가**

`frontend/components/asset/RepairValuePanel.tsx:281-286`(`function ResultView({ result, onOpenPart, }: { result: ...; onOpenPart: (partNo: string) => void; })`)을 다음으로 교체(정확한 기존 시그니처는 파일을 열어 대조할 것 — `result` 타입은 그대로 유지):

```tsx
function ResultView({
  result,
  onOpenPart,
  onOpenInventory,
}: {
  result: ApiRepairValue;
  onOpenPart: (partNo: string) => void;
  onOpenInventory: (partNo: string) => void;
}) {
```

- [ ] **Step 6: "재고 보기" 칩 추가**

`frontend/components/asset/RepairValuePanel.tsx:351-364`("고장 부품" 칩 블록)을 다음으로 교체 — 기존 "등급 보기" 칩 옆에 "재고 보기" 칩을 나란히 놓는다:

```tsx
      {typeof result.failed_part === "string" && (
        <div style={sx("display:flex;align-items:center;gap:8px;flex-wrap:wrap")}>
          <span style={sx("font:11.5px 'Pretendard';color:var(--dim2)")}>고장 부품</span>
          <button
            onClick={() => onOpenPart(result.failed_part as string)}
            style={sx(
              "border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:14px;" +
                "padding:4px 11px;cursor:pointer;font:12px 'JetBrains Mono',monospace;color:var(--blue-tx)"
            )}
          >
            {result.failed_part} <span style={sx("opacity:.7")}>· 등급 보기 →</span>
          </button>
          <button
            onClick={() => onOpenInventory(result.failed_part as string)}
            style={sx(
              "border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:14px;" +
                "padding:4px 11px;cursor:pointer;font:12px 'JetBrains Mono',monospace;color:var(--blue-tx)"
            )}
          >
            재고 보기 →
          </button>
        </div>
      )}
```

- [ ] **Step 7: 타입 체크 + 빌드**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Expected: 에러 없음, **라우트 11개 유지**(이 태스크는 새 라우트를 만들지 않는다).

- [ ] **Step 8: `rg` 확인**

```bash
rg -n "REPAIR|REPLACE|HOLD|CLEAR|CRITICAL" frontend/components/asset/RepairValuePanel.tsx
```

Expected: Task 5 착수 전과 **동일한 건수**(이 태스크가 새로 판정 어휘를 추가하지 않았다는 증명 — 정확한 기존 건수는 `git stash`로 변경 전 상태에서 먼저 확인해 대조할 것, 이전 스테이지 reviewer가 0건임을 이미 확인했으므로 0건이어야 한다).

- [ ] **Step 9: Commit**

```bash
git add frontend/components/asset/RepairValuePanel.tsx
git commit -m "$(cat <<'EOF'
[M3] RepairValuePanel 에 InventoryDrawer 연결 (재고 보기 칩)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 전체 회귀 확인 + 수동 확인

**Files:** (변경 없음 — 검증만)

- [ ] **Step 1: 전체 회귀**

```bash
uv run python data/seed.py --with-error-codes
uv run --with pytest python -m pytest data/rules/test_rules.py -q
for f in spikes/*.py; do
  name=$(basename "$f" .py)
  out=$(uv run python "$f" 2>&1)
  if [ $? -ne 0 ]; then echo "FAIL: $name"; echo "$out" | tail -5; else echo "OK: $name"; fi
done
uv run ruff check data backend mcp_server spikes
cd frontend && npx tsc --noEmit && npm run build
```

Expected: seed 통과, pytest 46건, spikes 전건 통과(감소 0 — 실패 스위트가 있으면 CLAUDE.md 규약대로 단독 재실행해서 Windows 소켓 고갈인지 진짜 회귀인지 구분할 것), ruff 통과, tsc/build 통과 라우트 11개.

- [ ] **Step 2: 브라우저 수동 확인**

`data/seed.py` 재시드 후 백엔드(`uv run uvicorn backend.main:app --port 8020`)와 프론트(`NEXT_PUBLIC_API_BASE=http://localhost:8020 npm run dev`)를 띄우고 `/technician/asset/AST-L3-CONV/value`에서:
- 수리가치판단 실행 → "재고 보기" 칩이 "등급 보기" 옆에 나타나는지
- 클릭 → 드로어가 열리고 재고 수량이 보이는지
- 재고가 안전재고 이하인 부품으로 테스트 → "발주하러 가기" 버튼이 보이는지, 클릭 시 `/technician`으로 이동하며 채팅 입력창에 문장이 채워지는지(자동 전송은 안 되는지)

테스트 후 서버 프로세스 종료, DB 재시드로 원복.

- [ ] **Step 3: 문서 반영**

`docs/06_REPO_API.md`에 `GET /api/inventory` 1줄 추가(§2.5 확장 REST 5종 근처, 정확한 위치는 파일을 열어 기존 표 형식에 맞출 것).

```bash
git add docs/06_REPO_API.md
git commit -m "$(cat <<'EOF'
[M3] docs: GET /api/inventory 06_REPO_API.md 반영

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
