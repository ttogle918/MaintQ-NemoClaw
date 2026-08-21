# -*- coding: utf-8 -*-
"""요청자 신원 조회 (docs/06_REPO_API.md §2 · D108).

```
GET /api/whoami
```

`Caller` 가 이미 들고 있는 값(`role`·`user_id`·`department`)을 그대로 반환한다 — 새로
판정하지 않는다. 프론트가 소속(`department`) 배지를 그리려면 헤더만으로는 알 수 없다
(D108 — 부서는 헤더로 받지 않고 서버가 DB 조회로 주입한다). 그 값을 클라이언트에
돌려주는 유일한 경로가 이 엔드포인트다.

역할 게이트를 두지 않는다 — 누구든 "나는 누구인가"를 물을 수 있고, 그 답이 권한을
바꾸지 않는다(`hotspot_status.py` 와 같은 이유로 읽기 판정에는 403 이 없다).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.deps import Caller, caller

router = APIRouter(prefix="/api", tags=["session"])


@router.get("/whoami")
def whoami(c: Caller = Depends(caller)) -> dict:
    return {"role": c.role, "user_id": c.user_id, "department": c.department}
