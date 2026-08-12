# 등기정보광장(IROS) Open API 명세 — 동산·채권담보등기 4종

> **이 문서는 기관 명세를 옮겨 둔 것이고, 아직 실호출로 검증되지 않았다.**
> 판단 근거(왜 받았나·한계·인용 금지선)와 서비스 ID 매핑은 `data/data_list.md §A6` 가 정본이다.
> 여기는 **요청 예시·에러코드 전문**을 두는 자리다.
>
> ⚠ 응답 필드가 4개 서비스에 걸쳐 `resDate·srprsCls·tot` 로 동일하게 적혀 있는데,
> 채권최고액별·누적채권액 서비스에는 금액 관련 필드가 있어야 한다 — **복붙 정황이므로
> 실호출 응답으로 확정한다.** 확정 결과는 이 문서 말미에 `## 실호출 확인` 으로 덧붙인다.

---
# 동산·채권담보등기 누적채권액 현황 Open API 명세서

## 1. 개요

* **서비스명**: 동산·채권담보등기 누적채권액 현황(담보권설정자 유형별)
* **설명**: 동산·채권담보등기 누적채권액을 매월 말일 기준으로 동산·채권 구분 및 담보권설정자 유형(법인, 외국법인, 미등기 외국법인 등)별로 제공
* **분류체계**: 동산·채권담보등기 > 등기기록
* **갱신주기**: 월
* **요청 제한**: 일 최대 1,000회 (1회 요청당 최대 1,000건 제공)

---

## 2. API 요청 정보

* **요청 URL**: `https://data.iros.go.kr/openapi/cr/rs/selectCrRsRgsCsOpenApi.rest`
* **요청 방식**: `GET` 또는 `POST`

---

## 3. 요청 파라미터 (Request Parameters)

### 기본 인자

| 변수명 | 필수 여부 | 타입 | 설명 |
| --- | --- | --- | --- |
| `id` | **Y** | STRING | Open API 서비스 ID (`0000000242`) |
| `key` | **Y** | STRING | 발급받은 인증키 |
| `reqtype` | **Y** | STRING | 응답 형식 (`xml`, `json` / 기본값: `xml`) |

### 요청 인자 (검색 조건)

| 변수명 | 필수 여부 | 타입 | 설명 및 예시 |
| --- | --- | --- | --- |
| `search_type_api` | **Y** | STRING | 검색기간 구분 (`02` - 월별 검색) |
| `search_start_date_api` | **Y** | STRING | 검색 시작년월 (예: `202401`) |
| `search_end_date_api` | **Y** | STRING | 검색 종료년월 (예: `202412`) |

> **주의사항**
> * 최근 **3년** 이내의 데이터만 제공하므로, `search_start_date_api` 설정 시 기간을 확인해야 합니다.
> * 조회 기간이 너무 길 경우 데이터 초과 오류가 발생할 수 있습니다.
> 
> 

---

## 4. 응답 데이터 (Response Fields)

| 변수명 | 타입 | 설명 |
| --- | --- | --- |
| `resDate` | STRING | 결과 일자 |
| `srprsCls` | STRING | 담보권설정자 구분 |
| `tot` | STRING | 결과 건수 |

---

## 5. 요청 예시 (Example)

### HTTP Request (JSON)

```http
GET https://data.iros.go.kr/openapi/cr/rs/selectCrRsRgsCsOpenApi.rest?id=0000000242&key=YOUR_AUTH_KEY&reqtype=json&search_type_api=02&search_start_date_api=202601&search_end_date_api=202606

```

---

## 6. 주요 에러 및 응답 코드

| 코드 | 구분 | 설명 |
| --- | --- | --- |
| `APIINFO-0001` | 정상 | 정상 처리되었습니다. |
| `APIINFO-0003` | 정상 | 해당하는 데이터가 없습니다. |
| `APIERROR-0001` | 에러 | 파라미터 값이 누락되었거나 유효하지 않습니다. |
| `APIERROR-0003` | 에러 | 일별 트래픽 제한(1,000회) 초과 |
| `APIERROR-0005` | 에러 | 인증키 값이 누락되었습니다. |
| `APIERROR-0010` | 에러 | 출력 데이터가 너무 많으므로 검색기간을 줄여주세요. |
| `APIERROR-0014` | 에러 | 최근 3년의 데이터만 제공합니다. 검색시작기간을 확인하세요. |
| `APIERROR-0016` | 에러 | OpenAPI 서비스 시간이 아닙니다. |

---

# 동산·채권담보등기 신청사건 현황 Open API 명세서

## 1. 개요

* **서비스명**: 동산·채권담보등기 신청사건 현황
* **설명**: 동산·채권담보 등기신청 건수를 동산·채권 구분, 담보권설정자 구분(법인, 외국법인, 미등기 외국법인 등), 기간(일/월/년)별로 제공
* **분류체계**: 동산·채권담보등기 > 신청정보
* **갱신주기**: 일
* **요청 제한**: 일 최대 1,000회 (1회 요청당 최대 1,000건 제공)

---

## 2. API 요청 정보

* **요청 URL**: `https://data.iros.go.kr/openapi/cr/rs/selectCrRsRgsCsOpenApi.rest`
* **서비스 ID**: `0000000212`

---

## 3. 요청 파라미터 (Request Parameters)

### 기본 인자

| 변수명 | 필수 여부 | 타입 | 설명 |
| --- | --- | --- | --- |
| `id` | **Y** | STRING | Open API 서비스 ID (`0000000212`) |
| `key` | **Y** | STRING | 발급받은 인증키 |
| `reqtype` | **Y** | STRING | 응답 형식 (`xml`, `json` / 기본값: `xml`) |

### 요청 인자 (검색 조건)

| 변수명 | 필수 여부 | 타입 | 설명 및 입력 Format |
| --- | --- | --- | --- |
| `search_type_api` | **Y** | STRING | 검색기간 구분 (`01`: 년별, `02`: 월별, `03`: 일별) |
| `search_start_date_api` | **Y** | STRING | 검색 시작기간 (예: 년별 `2024`, 월별 `202401`, 일별 `20240101`) |
| `search_end_date_api` | **Y** | STRING | 검색 종료기간 (예: 년별 `2025`, 월별 `202512`, 일별 `20251231`) |

---

## 4. 응답 데이터 (Response Fields)

| 변수명 | 타입 | 설명 |
| --- | --- | --- |
| `resDate` | STRING | 결과 일자 (기간 구분에 따라 년/월/일 형식으로 출력) |
| `srprsCls` | STRING | 담보권설정자 구분 |
| `tot` | STRING | 결과 건수 |

---

## 5. 요청 예시 (Example)

### HTTP Request (JSON - 월별 검색 예시)

```http
GET https://data.iros.go.kr/openapi/cr/rs/selectCrRsRgsCsOpenApi.rest?id=0000000212&key=YOUR_AUTH_KEY&reqtype=json&search_type_api=02&search_start_date_api=202601&search_end_date_api=202606

```

---

## 6. 주요 에러 및 응답 코드

| 코드 | 구분 | 설명 |
| --- | --- | --- |
| `APIINFO-0001` | 정상 | 정상 처리되었습니다. |
| `APIINFO-0003` | 정상 | 해당하는 데이터가 없습니다. |
| `APIERROR-0001` | 에러 | 파라미터 값이 누락 혹은 유효하지 않습니다. |
| `APIERROR-0003` | 에러 | 일별 트래픽 제한(1,000회) 초과 |
| `APIERROR-0005` | 에러 | 인증키 값이 누락되었습니다. |
| `APIERROR-0010` | 에러 | 출력데이터가 너무 많습니다. 검색기간을 줄여주세요. |
| `APIERROR-0014` | 에러 | 최근 3년의 데이터만 제공합니다. 검색시작기간을 확인하세요. |
| `APIERROR-0016` | 에러 | OpenAPI 서비스 시간이 아닙니다. |



---

# 동산·채권담보등기 신청현황(채권최고액별) Open API 명세서

## 1. 개요

* **서비스명**: 동산·채권담보등기 신청현황(채권최고액별)
* **설명**: 동산·채권담보 등기신청 건수를 동산·채권 구분, 담보권설정자 구분(법인, 외국법인, 미등기 외국법인 등), 채권최고액, 기간(일/월/년)별로 제공
* **분류체계**: 동산·채권담보등기 > 신청정보
* **갱신주기**: 일
* **등록일자 / 최종수정일자**: 2020-01-20 / 2026-05-07
* **요청 제한**: 일 최대 1,000회 (1회 요청당 최대 1,000건 제공)

---

## 2. API 요청 정보

* **요청 URL**: `https://data.iros.go.kr/openapi/cr/rs/selectCrRsRgsCsOpenApi.rest`
* **서비스 ID**: `0000000239`
* **요청 방식**: `GET` 또는 `POST`

---

## 3. 요청 파라미터 (Request Parameters)

### 기본 인자

| 변수명 | 필수 여부 | 타입 | 설명 |
| --- | --- | --- | --- |
| `id` | **Y** | STRING | Open API 서비스 ID (`0000000239`) |
| `key` | **Y** | STRING | 발급받은 인증키 |
| `reqtype` | **Y** | STRING | 응답 형식 (`xml`, `json` / 기본값: `xml`) |

### 요청 인자 (검색 조건)

| 변수명 | 필수 여부 | 타입 | 설명 및 입력 Format |
| --- | --- | --- | --- |
| `search_type_api` | **Y** | STRING | 검색기간 구분 (`01`: 년별, `02`: 월별, `03`: 일별) |
| `search_start_date_api` | **Y** | STRING | 검색 시작기간 (예: 년별 `2024`, 월별 `202401`, 일별 `20240101`) |
| `search_end_date_api` | **Y** | STRING | 검색 종료기간 (예: 년별 `2025`, 월별 `202512`, 일별 `20251231`) |

---

## 4. 응답 데이터 (Response Fields)

| 변수명 | 타입 | 설명 |
| --- | --- | --- |
| `resDate` | STRING | 결과 일자 (기간 구분에 따라 년/월/일 형식으로 출력) |
| `srprsCls` | STRING | 담보권설정자 구분 |
| `tot` | STRING | 결과 건수 |

---

## 5. 요청 예시 (Example)

### HTTP Request (JSON - 월별 검색 예시)

```http
GET https://data.iros.go.kr/openapi/cr/rs/selectCrRsRgsCsOpenApi.rest?id=0000000239&key=YOUR_AUTH_KEY&reqtype=json&search_type_api=02&search_start_date_api=202601&search_end_date_api=202606

```

---

## 6. 주요 에러 및 응답 코드

| 코드 | 구분 | 설명 |
| --- | --- | --- |
| `APIINFO-0001` | 정상 | 정상 처리되었습니다. |
| `APIINFO-0003` | 정상 | 해당하는 데이터가 없습니다. |
| `APIERROR-0001` | 에러 | 파라미터 값이 누락 혹은 유효하지 않습니다. |
| `APIERROR-0003` | 에러 | 일별 트래픽 제한을 넘은 호출입니다. 오늘은 더이상 호출할 수 없습니다. |
| `APIERROR-0004` | 에러 | 서비스ID값이 없습니다.요청인자 중 ID를 확인하십시오. |
| `APIERROR-0005` | 에러 | 인증키값이 없습니다.요청인자 중 Key를 확인하십시오. |
| `APIERROR-0010` | 에러 | 출력데이터가 너무 많습니다. 검색기간을 줄여주세요. |
| `APIERROR-0014` | 에러 | 최근 3년의 데이터만 제공합니다. 검색시작기간을 확인하세요. |
| `APIERROR-0016` | 에러 | OpenAPI 서비스 시간이 아닙니다. |



---

# 동산·채권담보등기 현황(담보권설정자 유형별) Open API 명세서

## 1. 개요

* **서비스명**: 동산·채권담보등기 현황(담보권설정자 유형별)
* **설명**: 동산·채권담보 등기기록수를 매월 말일 기준으로 동산·채권 구분, 담보권설정자 유형(법인, 외국법인, 미등기 외국법인 등)별로 제공
* **분류체계**: 동산·채권담보등기 > 등기기록
* **갱신주기**: 월
* **등록일자 / 최종수정일자**: 2020-01-20 / 2026-05-07
* **요청 제한**: 일 최대 1,000회 (1회 요청당 최대 1,000건 제공)

---

## 2. API 요청 정보

* **요청 URL**: `https://data.iros.go.kr/openapi/cr/rs/selectCrRsRgsCsOpenApi.rest`
* **서비스 ID**: `0000000213`
* **요청 방식**: `GET` 또는 `POST`

---

## 3. 요청 파라미터 (Request Parameters)

### 기본 인자

| 변수명 | 필수 여부 | 타입 | 설명 |
| --- | --- | --- | --- |
| `id` | **Y** | STRING | Open API 서비스 ID (`0000000213`) |
| `key` | **Y** | STRING | 발급받은 인증키 |
| `reqtype` | **Y** | STRING | 응답 형식 (`xml`, `json` / 기본값: `xml`) |

### 요청 인자 (검색 조건)

| 변수명 | 필수 여부 | 타입 | 설명 및 입력 Format |
| --- | --- | --- | --- |
| `search_type_api` | **Y** | STRING | 검색기간 구분 (`02`: 월별 검색) |
| `search_start_date_api` | **Y** | STRING | 검색 시작년월 (예: `202401`) |
| `search_end_date_api` | **Y** | STRING | 검색 종료년월 (예: `202412`) |

> **주의사항**
> * 해당 API는 **월별 검색(`02`)** 형식으로 지원되며, YYYYMM 형태로 기간을 지정해야 합니다.
> * 최근 **3년** 이내의 데이터만 제공됩니다.
> 
> 

---

## 4. 응답 데이터 (Response Fields)

| 변수명 | 타입 | 설명 |
| --- | --- | --- |
| `resDate` | STRING | 결과 일자 (YYYYMM) |
| `srCls` | STRING | 결과 담보구분 |
| `srprsCls` | STRING | 결과 담보권설정자 |
| `tot` | STRING | 결과 건수 |

---

## 5. 요청 예시 (Example)

### HTTP Request (JSON - 월별 검색 예시)

```http
GET https://data.iros.go.kr/openapi/cr/rs/selectCrRsRgsCsOpenApi.rest?id=0000000213&key=YOUR_AUTH_KEY&reqtype=json&search_type_api=02&search_start_date_api=202601&search_end_date_api=202606

```

---

## 6. 주요 에러 및 응답 코드

| 코드 | 구분 | 설명 |
| --- | --- | --- |
| `APIINFO-0001` | 정상 | 정상 처리되었습니다. |
| `APIINFO-0003` | 정상 | 해당하는 데이터가 없습니다. |
| `APIERROR-0001` | 에러 | 파라미터 값이 누락 혹은 유효하지 않습니다. |
| `APIERROR-0003` | 에러 | 일별 트래픽 제한을 넘은 호출입니다. 오늘은 더이상 호출할 수 없습니다. |
| `APIERROR-0004` | 에러 | 서비스ID값이 없습니다. 요청인자 중 ID를 확인하십시오. |
| `APIERROR-0005` | 에러 | 인증키값이 없습니다. 요청인자 중 Key를 확인하십시오. |
| `APIERROR-0010` | 에러 | 출력데이터가 너무 많습니다. 검색기간을 줄여주세요. |
| `APIERROR-0014` | 에러 | 최근 3년의 데이터만 제공합니다. 검색시작기간을 확인하세요. |
| `APIERROR-0016` | 에러 | OpenAPI 서비스 시간이 아닙니다. |