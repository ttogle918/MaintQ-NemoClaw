---
name: seed-db
description: 목업 DB를 (재)생성하고 시드 케이스 맵을 검증한다. 사용자가 /seed-db를 호출하거나, 스키마·시드 변경 후 DB 재생성이 필요할 때 사용.
---

# 목업 DB 시드 & 검증

## 절차

1. `data/seed.py --with-error-codes` 실행 → `data/maintq.db` 생성 (기존 DB는 백업 후 덮어쓰기).
   iG5A 매핑이 승인 완료(2026-07-28)라 이 플래그가 기본 — 빼면 error_codes 가 0행으로 돌아간다.
   (승인 전 상태를 일부러 재현하려면 플래그 없이 실행)
2. `docs/05_DB_SCHEMA.md`의 **시드 케이스 맵 7종**이 전부 재현되는지 SQL로 검증:

| 검증 쿼리 | 기대 결과 |
|---|---|
| FAN-IG5-01 재고 | qty=1 < safety_stock=3 |
| PCB-S100-CTRL | qty=0, discontinued=1, 대체품 R2 confirmed=true 존재 |
| 대체품 없는 전원모듈 | qty=0, part_alternatives 0건 |
| 냉각팬 공급사 | SUP-A(3일/38000/moq1), SUP-B(14일/29000/moq10) 2건 |
| INV-L3-01 OCt 이력 | 최근 30일 내 정확히 3건, action_taken 전부 '리셋' |
| compat_confirmed=false | 정확히 1건 존재 |
| 규모 | parts≈40, equipment≈10, suppliers=4, error_history≈200 |

3. 검증 결과를 통과/실패 표로 보고. 실패 시 seed.py 수정 후 재실행 (최대 3회, 이후 사람에게 보고)

## 주의

- error_codes 테이블은 시드가 아니라 `data/extracted/error_codes.json`에서 적재 — 이 파일이 없으면 "M1 추출 미완료"라고 보고하고 목업 코드로 채우지 말 것
- 반복 고장 케이스의 날짜는 실행일 기준 상대 날짜로 생성 (하드코딩 금지 — 데모 날짜가 밀려도 S3가 트리거되도록)
