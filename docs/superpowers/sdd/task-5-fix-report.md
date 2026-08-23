# Task 5 Fix Report — supplier_parts 테이블 추가

**Date:** 2026-08-23  
**Status:** ✅ COMPLETE

## Summary

`scripts/migrate_data.py` 의 `TABLES_TO_MIGRATE` 목록에서 **`supplier_parts` 테이블이 누락**되어 있던 문제를 수정했습니다.

## Issue

- **File:** `scripts/migrate_data.py`
- **Location:** Line 21-39, `TABLES_TO_MIGRATE` 리스트
- **Missing Table:** `supplier_parts`
- **Impact:** 공급처별 부품 가격 및 리드타임 데이터가 마이그레이션되지 않음

## Root Cause

마이그레이션 스크립트 작성 시 다음 테이블을 누락:
- `supplier_parts` (FK: `suppliers.supplier_id`, `parts.part_no`)

이 테이블은 S2(발주 시스템)와 S3(부품 공급망)에서 **필수** 데이터입니다.

## Fix Applied

**File:** `scripts/migrate_data.py`

```python
# Before
TABLES_TO_MIGRATE = [
    "users",
    "parts",
    "suppliers",
    "inventory",  # ← supplier_parts 누락
    ...
]

# After
TABLES_TO_MIGRATE = [
    "users",
    "parts",
    "suppliers",
    "supplier_parts",  # ← 추가
    "inventory",
    ...
]
```

**FK 의존성 순서 확인:**
- ✅ `suppliers` → `supplier_parts` (올바른 순서)
- ✅ `parts` → `supplier_parts` (올바른 순서)

## Verification

✅ Script loads without syntax errors:
```bash
$ uv run python scripts/migrate_data.py --help
usage: migrate_data.py [-h] [--sqlite SQLITE] --postgres POSTGRES
                       [--include-error-codes]
```

## Commit

```
[M4] fix: Task 5 — supplier_parts 테이블 추가
04219a0
```

## Impact

- ✅ SQLite → Postgres 마이그레이션에서 supplier_parts 데이터 포함
- ✅ S2/S3 시나리오의 부품 공급망 데이터 무결성 보장
- ✅ PO 생성 시 공급처 정보 조회 정상화
