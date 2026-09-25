# -*- coding: utf-8 -*-
"""사업장 → 구역 → 설비 위치 목업 데이터 (D158, Sprint 19 MQ-1914).

**데이터 정본은 이 파일 하나다.** 두 소비자가 같은 상수를 import 한다:
  - `data/seed.py` — 새 환경(빈 DB)을 만들 때 (공유 DB 에서는 실행하지 않는다 — H9)
  - `scripts/migrate_d158_sites.py` — 이미 사람 작업(HV600 승격·안전 승인·정규화)이 쌓인
    공유 DB 에 **멱등 INSERT … ON CONFLICT DO NOTHING** 으로 반영
값을 두 군데 따로 적으면 새 환경과 공유 DB 의 평면도가 조용히 갈라진다.

⛔ 사업장명에 실제 회사명을 쓰지 않는다 — `is_mock=True` 이고 화면이 「목업」을 표시한다(D158).
좌표계는 SVG 사용자 단위다(지도 좌표 아님 — 외부 지도 API 를 쓰지 않는다, D158 ⓑ).
설비 좌표는 반드시 소속 구역 사각형 **안쪽**이어야 한다 — `seed.py` ㊸ 와
`spikes/site_floorplan_contract.py` 가 같은 규칙을 검사한다.

순수 데이터 모듈이다 — DB·네트워크 import 없음.
"""

from __future__ import annotations

# (site_id, name, is_mock, width, height)
SITES: list[tuple[str, str, bool, int, int]] = [
    ("SITE-01", "목업 제1공장", True, 1000, 600),
]

# (zone_id, site_id, name, kind, x, y, w, h)
# kind 어휘는 스키마 CHECK 와 같다: assembly · machining · packaging · utility
ZONES: list[tuple[str, str, str, str, int, int, int, int]] = [
    ("Z-L1", "SITE-01", "1번 조립라인", "assembly", 40, 40, 420, 150),
    ("Z-L2", "SITE-01", "2번 가공라인", "machining", 500, 40, 460, 150),
    ("Z-L3", "SITE-01", "3번 조립라인", "assembly", 40, 230, 420, 150),
    ("Z-L4", "SITE-01", "4번 포장라인", "packaging", 500, 230, 460, 150),
    ("Z-HVAC", "SITE-01", "공조·유틸리티동", "utility", 40, 420, 920, 140),
]

# HV600 설비 2행 (D158) — `equipment` 테이블에 들어간다. 컬럼 순서는 seed.EQUIPMENT 와 같다:
# (equipment_id, line_id, model, installed_at, location, asset_id)
# ⚠ `asset_id` NULL = 호스트 자산 미등록(D68) — 확장 도구는 `no_host_asset` 을 낸다(정상).
# ⚠ `line_id=5` 는 기존 생산라인 1~4 와 겹치지 않는 **유틸리티동 번호**다 — 라인 필터
#   (`get_error_history(line_id=…)`)가 기존 라인에 HV600 을 섞지 않게 한다.
# ⚠ error_history·inventory·part_lifecycle_mock 등 다른 테이블에는 행을 만들지 않는다 —
#   HV600 부품 재고는 없다(진단 흐름의 재고 조회가 empty 여도 정상).
HV600_EQUIPMENT: list[tuple[str, int, str, str, str, None]] = [
    ("INV-HV-01", 5, "HV600", "2024-03-15", "공조·유틸리티동 공조기 급기팬", None),
    ("INV-HV-02", 5, "HV600", "2024-03-15", "공조·유틸리티동 냉각수 펌프", None),
]

# (equipment_id, zone_id, x, y) — 12대 전부. 라인 설비는 line_id 에 맞는 구역이다.
EQUIPMENT_LOCATIONS: list[tuple[str, str, int, int]] = [
    ("INV-L1-01", "Z-L1", 130, 125),
    ("INV-L1-02", "Z-L1", 330, 125),
    ("INV-L2-01", "Z-L2", 630, 125),
    ("INV-L2-02", "Z-L2", 830, 125),
    ("INV-L3-01", "Z-L3", 110, 315),
    ("INV-L3-02", "Z-L3", 250, 315),
    ("INV-L3-03", "Z-L3", 390, 315),
    ("INV-L4-01", "Z-L4", 580, 315),
    ("INV-L4-02", "Z-L4", 730, 315),
    ("INV-L4-03", "Z-L4", 880, 315),
    ("INV-HV-01", "Z-HVAC", 330, 505),
    ("INV-HV-02", "Z-HVAC", 670, 505),
]


def location_inside_zone(x: int, y: int, zone: tuple) -> bool:
    """설비 점이 구역 사각형 안(경계 제외)에 있는가 — zone 은 ZONES 행 모양."""
    _zid, _sid, _name, _kind, zx, zy, zw, zh = zone
    return zx < x < zx + zw and zy < y < zy + zh
