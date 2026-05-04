# Tài Liệu Tích Hợp Frontend Cho Stock Financial Report API

## 1. Mục tiêu tài liệu

Tài liệu này mô tả contract backend cho tính năng lấy báo cáo tài chính của một mã chứng khoán.

Phạm vi chỉ gồm:

- frontend cần truyền gì khi gọi API
- backend trả về schema gì
- ý nghĩa các field trong request/response
- nullable semantics và error semantics

Tài liệu này không hướng dẫn frontend cách code.

## 2. Endpoint

Backend hiện cung cấp endpoint:

```text
GET /api/v1/stocks/{symbol}/financial-reports/{report_type}
```

Endpoint này trả về một bảng báo cáo tài chính cho một mã chứng khoán, lấy từ nguồn KBS thông qua vnstock.

Không có endpoint aggregate trong v1:

```text
GET /api/v1/stocks/{symbol}/financial-reports
```

Request phía trên không được support trong contract hiện tại.

## 3. Điều kiện để gọi API thành công

Request cần có:

```http
Authorization: Bearer <token>
X-Organization-ID: <organization_id>
```

Semantics:

- dữ liệu báo cáo tài chính là shared market dataset, không tách theo organization
- request vẫn phải đi qua auth và organization context của hệ thống
- nếu thiếu `X-Organization-ID`, backend reject request
- nếu user không thuộc organization được gửi lên, backend reject request

## 4. Frontend cần truyền gì

### 4.1 Path params

```text
GET /api/v1/stocks/{symbol}/financial-reports/{report_type}
```

Path params:

- `symbol`: mã chứng khoán cần lấy báo cáo
- `report_type`: loại báo cáo cần lấy

`symbol` semantics:

- frontend có thể gửi `fpt`, `FPT`, ` FPT `
- backend normalize `symbol` thành uppercase trong response
- nếu `symbol` không tồn tại trong stock catalog của backend, request trả `404`

`report_type` hợp lệ:

- `income-statement`: báo cáo kết quả kinh doanh
- `balance-sheet`: bảng cân đối kế toán
- `cash-flow`: báo cáo lưu chuyển tiền tệ
- `ratio`: chỉ số tài chính

Ví dụ:

```http
GET /api/v1/stocks/FPT/financial-reports/income-statement
```

```http
GET /api/v1/stocks/FPT/financial-reports/balance-sheet
```

```http
GET /api/v1/stocks/FPT/financial-reports/cash-flow
```

```http
GET /api/v1/stocks/FPT/financial-reports/ratio
```

### 4.2 Query params

Query params hiện tại:

- `period`: optional

Giá trị hợp lệ của `period`:

- `quarter`
- `year`

Mặc định:

- nếu không truyền `period`, backend dùng `quarter`
- nếu truyền blank string, backend cũng normalize về `quarter`

Ví dụ:

```http
GET /api/v1/stocks/FPT/financial-reports/income-statement?period=quarter
```

```http
GET /api/v1/stocks/FPT/financial-reports/income-statement?period=year
```

### 4.3 Option chưa support trong v1

Endpoint hiện tại chưa support các query option sau:

- `limit`
- `source`
- `include_metadata`
- `display_mode`

Contract v1 cố định:

- source luôn là `KBS`
- mỗi request chỉ lấy đúng một `report_type`
- response không trả metadata phân cấp của KBS như `item_en`, `unit`, `levels`, `row_number`

## 5. Response schema chung

Tất cả `report_type` dùng cùng một envelope response.

```ts
type StockFinancialReportResponse = {
  symbol: string;
  source: "KBS";
  report_type: StockFinancialReportType;
  period: StockFinancialReportPeriod;
  periods: string[];
  items: StockFinancialReportItem[];
}

type StockFinancialReportType =
  | "income-statement"
  | "balance-sheet"
  | "cash-flow"
  | "ratio";

type StockFinancialReportPeriod = "quarter" | "year";

type StockFinancialReportCellValue = number | string | null;

type StockFinancialReportItem = {
  item: string;
  item_id: string | number | null;
  values: Record<string, StockFinancialReportCellValue>;
}
```

Ý nghĩa root fields:

- `symbol`: mã chứng khoán đã được backend normalize uppercase
- `source`: nguồn dữ liệu, v1 cố định là `KBS`
- `report_type`: loại báo cáo của response
- `period`: kỳ báo cáo backend dùng cho response
- `periods`: danh sách kỳ báo cáo theo đúng thứ tự cột backend nhận từ KBS
- `items`: các dòng trong bảng báo cáo

Ý nghĩa item fields:

- `item`: tên dòng báo cáo tài chính
- `item_id`: identifier của dòng nếu KBS có trả; có thể là string, number, hoặc `null`
- `values`: object chứa giá trị của từng kỳ báo cáo, key là label trong `periods`

## 6. Period/value semantics

`periods` là source of truth cho thứ tự cột khi frontend render bảng.

Ví dụ:

```json
{
  "periods": ["2025-Q4", "2025-Q3"],
  "items": [
    {
      "item": "Doanh thu thuần",
      "item_id": "revenue",
      "values": {
        "2025-Q4": 1000,
        "2025-Q3": 900
      }
    }
  ]
}
```

Semantics:

- mỗi key trong `values` tương ứng với một phần tử trong `periods`
- frontend nên dùng `periods` để quyết định thứ tự hiển thị cột
- `values` có thể chứa `null` khi upstream không có dữ liệu cho cell đó
- giá trị cell có thể là number, string, hoặc `null`
- backend không guarantee mọi dòng đều có đủ dữ liệu khác `null` ở mọi kỳ

## 7. Response theo từng report_type

### 7.1 Income statement

Endpoint:

```text
GET /api/v1/stocks/{symbol}/financial-reports/income-statement
```

Response:

```ts
type IncomeStatementResponse = StockFinancialReportResponse & {
  report_type: "income-statement";
}
```

Ví dụ shape:

```json
{
  "symbol": "FPT",
  "source": "KBS",
  "report_type": "income-statement",
  "period": "quarter",
  "periods": ["2025-Q4", "2025-Q3"],
  "items": [
    {
      "item": "Doanh thu thuần",
      "item_id": "revenue",
      "values": {
        "2025-Q4": 1000,
        "2025-Q3": 900
      }
    }
  ]
}
```

### 7.2 Balance sheet

Endpoint:

```text
GET /api/v1/stocks/{symbol}/financial-reports/balance-sheet
```

Response:

```ts
type BalanceSheetResponse = StockFinancialReportResponse & {
  report_type: "balance-sheet";
}
```

Ví dụ shape:

```json
{
  "symbol": "FPT",
  "source": "KBS",
  "report_type": "balance-sheet",
  "period": "quarter",
  "periods": ["2025-Q4", "2025-Q3"],
  "items": [
    {
      "item": "Tổng tài sản",
      "item_id": "total_assets",
      "values": {
        "2025-Q4": 5000,
        "2025-Q3": 4800
      }
    }
  ]
}
```

### 7.3 Cash flow

Endpoint:

```text
GET /api/v1/stocks/{symbol}/financial-reports/cash-flow
```

Response:

```ts
type CashFlowResponse = StockFinancialReportResponse & {
  report_type: "cash-flow";
}
```

Ví dụ shape:

```json
{
  "symbol": "FPT",
  "source": "KBS",
  "report_type": "cash-flow",
  "period": "quarter",
  "periods": ["2025-Q4", "2025-Q3"],
  "items": [
    {
      "item": "Lưu chuyển tiền thuần từ hoạt động kinh doanh",
      "item_id": "cash_flow_from_operating_activities",
      "values": {
        "2025-Q4": 700,
        "2025-Q3": null
      }
    }
  ]
}
```

### 7.4 Ratio

Endpoint:

```text
GET /api/v1/stocks/{symbol}/financial-reports/ratio
```

Response:

```ts
type RatioResponse = StockFinancialReportResponse & {
  report_type: "ratio";
}
```

Ví dụ shape:

```json
{
  "symbol": "FPT",
  "source": "KBS",
  "report_type": "ratio",
  "period": "quarter",
  "periods": ["2025-Q4", "2025-Q3"],
  "items": [
    {
      "item": "ROE",
      "item_id": "roe",
      "values": {
        "2025-Q4": 0.24,
        "2025-Q3": 0.23
      }
    }
  ]
}
```

Lưu ý chung cho 4 loại response:

- schema giống nhau, khác nhau ở `report_type` và nội dung `items`
- backend không guarantee danh sách `item` cố định giữa mọi mã chứng khoán
- backend không guarantee `item_id` luôn có giá trị
- ví dụ phía trên chỉ minh họa shape; không phải danh sách dòng cố định từ KBS

## 8. Error response

Khi lỗi, response thường có shape:

```json
{
  "detail": "Error message"
}
```

Các status chính:

- `400 Bad Request`
  - thiếu `X-Organization-ID`
- `401 Unauthorized`
  - token không hợp lệ
  - account không active
- `403 Forbidden`
  - user không có quyền trên organization được gửi
- `404 Not Found`
  - `symbol` không tồn tại trong stock catalog
  - KBS không có dữ liệu báo cáo cho `symbol + report_type + period`
- `422 Unprocessable Entity`
  - `report_type` không hợp lệ
  - `period` không hợp lệ
- `502 Bad Gateway`
  - upstream provider lỗi

Ví dụ:

```json
{
  "detail": "Stock symbol not found"
}
```

```json
{
  "detail": "Financial report data not found"
}
```

```json
{
  "detail": "Failed to fetch stock financial report data from upstream provider"
}
```

Frontend nên ưu tiên branch logic theo HTTP status code, không nên phụ thuộc cứng vào exact text trong `detail`.

## 9. Những gì frontend không nên giả định

- không nên giả định mọi mã chứng khoán đều có đủ cả 4 loại báo cáo
- không nên giả định mọi `period` đều có dữ liệu
- không nên giả định số kỳ trả về luôn là 8; v1 không expose `limit`
- không nên giả định `periods` luôn là quarterly nếu request `period=year`
- không nên tự sort key trong `values`; hãy dùng thứ tự từ `periods`
- không nên giả định `item_id` luôn tồn tại hoặc luôn là string
- không nên giả định giá trị cell luôn là number
- không nên giả định backend trả metadata phân cấp như `levels` hoặc `unit`

## 10. Tóm tắt contract

Request:

- Endpoint: `GET /api/v1/stocks/{symbol}/financial-reports/{report_type}`
- Headers:
  - `Authorization: Bearer <token>`
  - `X-Organization-ID: <organization_id>`
- Path params:
  - `symbol`
  - `report_type = income-statement | balance-sheet | cash-flow | ratio`
- Query params:
  - `period = quarter | year`
- Default:
  - `period = quarter`

Response:

- `symbol`
- `source = "KBS"`
- `report_type`
- `period`
- `periods`
- `items[].item`
- `items[].item_id`
- `items[].values`
