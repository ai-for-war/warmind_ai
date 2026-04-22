# Tài Liệu Tích Hợp Frontend Cho Stock Research Report API

## 1. Mục tiêu tài liệu

Tài liệu này mô tả contract backend cho tính năng stock research report.

Phạm vi tài liệu chỉ gồm:

- frontend cần truyền gì khi gọi API
- endpoint nào hiện có
- request schema của từng endpoint
- response schema của từng endpoint
- lifecycle state, nullable semantics, và error semantics

Tài liệu này không hướng dẫn frontend cách code.

## 2. Base path

Tất cả stock research endpoints dùng base path:

```text
/api/v1/stock-research/reports
```

Danh sách endpoint hiện có:

- `GET /api/v1/stock-research/reports/catalog`
- `POST /api/v1/stock-research/reports`
- `GET /api/v1/stock-research/reports`
- `GET /api/v1/stock-research/reports/{report_id}`

## 3. Điều kiện để gọi API thành công

Tất cả endpoints đều cần:

```http
Authorization: Bearer <token>
X-Organization-ID: <organization_id>
```

Semantics:

- report được scope theo `current_user + organization`
- cùng một user nhưng organization khác nhau sẽ thấy danh sách report khác nhau
- nếu thiếu `X-Organization-ID`, backend sẽ reject request
- nếu user không thuộc organization được gửi lên, backend sẽ reject request

## 4. Tổng quan luồng tích hợp FE

Luồng backend hiện tại:

1. FE có thể gọi catalog endpoint để lấy danh sách provider/model/reasoning được support.
2. FE gọi `POST /api/v1/stock-research/reports` để tạo một report request.
3. Backend trả `202 Accepted` ngay, kèm summary của report vừa tạo.
4. Backend xử lý report ở background.
5. FE poll `GET /api/v1/stock-research/reports/{report_id}` để lấy trạng thái mới nhất.
6. FE có thể gọi `GET /api/v1/stock-research/reports` để hiển thị lịch sử report.

## 5. Định danh và normalization frontend cần hiểu

### 5.1 `report_id`

- là string id của report
- frontend chỉ cần gửi lại đúng giá trị đã nhận từ backend

### 5.2 `symbol`

- frontend có thể gửi `fpt`, `FPT`, ` FPT `
- backend sẽ normalize về uppercase trước khi xử lý
- response luôn trả `symbol` ở dạng uppercase

### 5.3 `runtime_config`

- là optional object trong create request
- nếu không truyền, backend sẽ dùng runtime mặc định server-side
- nếu có truyền, frontend chỉ nên dùng giá trị lấy từ catalog endpoint

## 6. Request schema của từng endpoint

## 6.1 Lấy catalog runtime

Endpoint:

```text
GET /api/v1/stock-research/reports/catalog
```

Không có:

- path param
- query param
- request body

## 6.2 Tạo stock research report

Endpoint:

```text
POST /api/v1/stock-research/reports
```

Headers bắt buộc:

```http
Authorization: Bearer <token>
X-Organization-ID: <organization_id>
Content-Type: application/json
```

Request body tối thiểu:

```json
{
  "symbol": "FPT"
}
```

Request body có runtime override:

```json
{
  "symbol": "FPT",
  "runtime_config": {
    "provider": "zai",
    "model": "glm-5.1",
    "reasoning": null
  }
}
```

Schema:

```ts
type StockResearchReportCreateRequest = {
  symbol: string;
  runtime_config?: {
    provider: string;
    model: string;
    reasoning?: string | null;
  } | null;
}
```

Validation semantics:

- `symbol`: required, min length `1`, max length `32`
- `runtime_config`: optional
- nếu `runtime_config` có mặt thì:
  - `provider`: required
  - `model`: required
  - `reasoning`: optional, có thể `null`

## 6.3 Lấy một report theo id

Endpoint:

```text
GET /api/v1/stock-research/reports/{report_id}
```

Không có request body.

## 6.4 Lấy lịch sử report

Endpoint:

```text
GET /api/v1/stock-research/reports
```

Query params:

- `symbol`: optional, min length `1`, max length `32`

Ví dụ:

```http
GET /api/v1/stock-research/reports
```

```http
GET /api/v1/stock-research/reports?symbol=FPT
```

Semantics:

- nếu có `symbol`, backend sẽ normalize uppercase trước khi filter
- list hiện tại là history của current user trong current organization

## 7. Response schema chung

## 7.1 Runtime catalog model

```ts
type StockResearchCatalogModelResponse = {
  model: string;
  reasoning_options: string[];
  default_reasoning: string | null;
  is_default: boolean;
}
```

## 7.2 Runtime catalog provider

```ts
type StockResearchCatalogProviderResponse = {
  provider: string;
  display_name: string;
  is_default: boolean;
  models: StockResearchCatalogModelResponse[];
}
```

## 7.3 Runtime catalog root

```ts
type StockResearchCatalogResponse = {
  default_provider: string;
  default_model: string;
  default_reasoning: string | null;
  providers: StockResearchCatalogProviderResponse[];
}
```

Semantics:

- `providers` luôn tồn tại, có thể là mảng rỗng nếu runtime khả dụng bị tắt hoàn toàn
- `reasoning_options` luôn tồn tại, có thể là `[]`
- `default_reasoning` có thể là `null`
- FE không nên hardcode provider/model/reasoning ngoài catalog

## 7.4 Report source

```ts
type StockResearchReportSourceResponse = {
  source_id: string;
  url: string;
  title: string;
}
```

Semantics:

- `source_id` là id citation kiểu `S1`, `S2`, `S3`
- `url` là web source URL
- `title` là nhãn nguồn để hiển thị

## 7.5 Report failure

```ts
type StockResearchReportFailureResponse = {
  code: string;
  message: string;
}
```

Semantics:

- `code` thường là exception type hoặc backend error code
- `message` là thông điệp lỗi ổn định để FE hiển thị

## 7.6 Report summary

```ts
type StockResearchReportSummary = {
  id: string;
  symbol: string;
  status: "queued" | "running" | "completed" | "partial" | "failed";
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
}
```

Semantics:

- tất cả timestamp là ISO datetime string
- `started_at` có thể là `null`
- `completed_at` có thể là `null`

Lưu ý quan trọng:

- enum schema hiện vẫn include `partial`
- nhưng flow service hiện tại đang phát các trạng thái: `queued`, `running`, `completed`, `failed`
- frontend không nên hardcode rằng `partial` sẽ xuất hiện ngay bây giờ
- frontend cũng không nên giả định `partial` sẽ không bao giờ xuất hiện trong tương lai, vì schema vẫn còn giá trị này

## 7.7 Create response

```ts
type StockResearchReportCreateResponse = StockResearchReportSummary
```

## 7.8 Get report response

```ts
type StockResearchReportResponse = StockResearchReportSummary & {
  content: string | null;
  sources: StockResearchReportSourceResponse[];
  error: StockResearchReportFailureResponse | null;
}
```

Nullable semantics:

- `content`: có thể `null` khi report chưa hoàn tất hoặc run thất bại
- `sources`: luôn tồn tại, có thể là `[]`
- `error`: có thể `null`

## 7.9 List response

```ts
type StockResearchReportListResponse = {
  items: StockResearchReportSummary[];
}
```

Semantics:

- `items` luôn tồn tại
- `items` có thể là mảng rỗng

## 8. Response schema của từng endpoint

## 8.1 `GET /catalog`

Status code thành công:

- `200 OK`

Response body ví dụ:

```json
{
  "default_provider": "zai",
  "default_model": "glm-5.1",
  "default_reasoning": null,
  "providers": [
    {
      "provider": "zai",
      "display_name": "Z.AI",
      "is_default": true,
      "models": [
        {
          "model": "glm-5.1",
          "reasoning_options": [],
          "default_reasoning": null,
          "is_default": true
        }
      ]
    }
  ]
}
```

Lưu ý:

- nội dung thực tế của catalog phụ thuộc cấu hình backend tại thời điểm gọi
- ví dụ trên chỉ minh họa shape response

## 8.2 `POST /api/v1/stock-research/reports`

Status code thành công:

- `202 Accepted`

Response body ví dụ:

```json
{
  "id": "6807dd18c5d8d14d4af1d111",
  "symbol": "FPT",
  "status": "queued",
  "created_at": "2026-04-22T08:00:00Z",
  "started_at": null,
  "completed_at": null,
  "updated_at": "2026-04-22T08:00:00Z"
}
```

Semantics:

- `202 Accepted` nghĩa là request đã được accept và background job đã được schedule
- không có guarantee report hoàn tất ngay sau response này
- FE nên dùng `id` từ response để poll endpoint get-by-id

## 8.3 `GET /api/v1/stock-research/reports/{report_id}`

Status code thành công:

- `200 OK`

Response body ví dụ khi report còn đang chạy:

```json
{
  "id": "6807dd18c5d8d14d4af1d111",
  "symbol": "FPT",
  "status": "running",
  "created_at": "2026-04-22T08:00:00Z",
  "started_at": "2026-04-22T08:00:05Z",
  "completed_at": null,
  "updated_at": "2026-04-22T08:00:05Z",
  "content": null,
  "sources": [],
  "error": null
}
```

Response body ví dụ khi report hoàn tất:

```json
{
  "id": "6807dd18c5d8d14d4af1d111",
  "symbol": "FPT",
  "status": "completed",
  "created_at": "2026-04-22T08:00:00Z",
  "started_at": "2026-04-22T08:00:05Z",
  "completed_at": "2026-04-22T08:00:42Z",
  "updated_at": "2026-04-22T08:00:42Z",
  "content": "## Current Price Snapshot\n\nCurrent price is around 95,800 VND.\n\n## Thesis\n\nFPT remains resilient [S1].",
  "sources": [
    {
      "source_id": "S1",
      "url": "https://example.com/fpt",
      "title": "Example Source"
    }
  ],
  "error": null
}
```

Response body ví dụ khi thất bại:

```json
{
  "id": "6807dd18c5d8d14d4af1d111",
  "symbol": "FPT",
  "status": "failed",
  "created_at": "2026-04-22T08:00:00Z",
  "started_at": "2026-04-22T08:00:05Z",
  "completed_at": "2026-04-22T08:00:18Z",
  "updated_at": "2026-04-22T08:00:18Z",
  "content": null,
  "sources": [],
  "error": {
    "code": "RuntimeError",
    "message": "Stock research report generation failed"
  }
}
```

## 8.4 `GET /api/v1/stock-research/reports`

Status code thành công:

- `200 OK`

Response body ví dụ:

```json
{
  "items": [
    {
      "id": "6807dd18c5d8d14d4af1d112",
      "symbol": "VCB",
      "status": "completed",
      "created_at": "2026-04-22T09:00:00Z",
      "started_at": "2026-04-22T09:00:02Z",
      "completed_at": "2026-04-22T09:00:41Z",
      "updated_at": "2026-04-22T09:00:41Z"
    },
    {
      "id": "6807dd18c5d8d14d4af1d111",
      "symbol": "FPT",
      "status": "running",
      "created_at": "2026-04-22T08:00:00Z",
      "started_at": "2026-04-22T08:00:05Z",
      "completed_at": null,
      "updated_at": "2026-04-22T08:00:05Z"
    }
  ]
}
```

Ordering semantics:

- list hiện tại được trả newest-first theo `created_at desc`

## 9. Semantics FE cần hiểu về `content` và `sources`

- `content` là markdown report body đã persist
- `sources` là danh sách nguồn web dùng cho citation mapping
- citation trong `content` dùng dạng `[S1]`, `[S2]`, `[S3]`
- `source_id` trong `sources[]` map trực tiếp với citation id trong `content`
- current-price text có thể xuất hiện trong `content` mà không cần citation
- frontend không nên giả định mọi câu trong report đều có `[Sx]`

## 10. Error response shape

Khi request lỗi do `AppException` hoặc auth/org dependency, response body có shape:

```json
{
  "detail": "Error message"
}
```

Schema:

```ts
type ErrorResponse = {
  detail: string;
}
```

## 11. Error semantics frontend cần hiểu

Có thể gặp các nhóm lỗi sau:

- `400 Bad Request`
  - thiếu `X-Organization-ID`
  - request body hoặc query param không hợp lệ
- `401 Unauthorized`
  - token không hợp lệ
  - account không active
- `403 Forbidden`
  - user không thuộc organization được gửi lên
- `404 Not Found`
  - organization không tồn tại hoặc không active
  - stock symbol không tồn tại trong active stock catalog
  - report không tồn tại hoặc không thuộc current user/current organization

## 12. Error detail hiện tại

Những `detail` message FE có thể nhận trong implementation hiện tại:

- `X-Organization-ID header is required`
- `Permission denied`
- `Organization not found`
- `Stock symbol not found`
- `Stock research report not found`

Frontend không nên hardcode business logic dựa trên text message này. Nếu cần branch logic, nên ưu tiên dựa trên status code.

## 13. Những gì frontend không nên giả định

- không nên giả định `POST /reports` trả report hoàn chỉnh; endpoint này trả `202 Accepted`
- không nên giả định `content` luôn có giá trị
- không nên giả định `sources` luôn có phần tử; field này có thể là `[]`
- không nên giả định `error` luôn có giá trị khi report chưa hoàn thành
- không nên giả định mọi report thành công đều có current-price citation
- không nên hardcode provider/model/reasoning ngoài catalog endpoint
- không nên giả định `partial` chắc chắn xuất hiện hoặc chắc chắn không xuất hiện; hãy bám schema response

## 14. Tóm tắt contract

### Headers bắt buộc

- `Authorization: Bearer <token>`
- `X-Organization-ID: <organization_id>`

### Request chính trong v1

- create report:
  - `symbol`
  - optional `runtime_config.provider`
  - optional `runtime_config.model`
  - optional `runtime_config.reasoning`
- list reports:
  - optional `symbol`

### Response chính trong v1

- catalog:
  - `default_provider`
  - `default_model`
  - `default_reasoning`
  - `providers`
- create response:
  - `id`
  - `symbol`
  - `status`
  - `created_at`
  - `started_at`
  - `completed_at`
  - `updated_at`
- get response:
  - toàn bộ summary fields
  - `content`
  - `sources`
  - `error`
- list response:
  - `items`

### Polling semantics

- `POST /api/v1/stock-research/reports` trả `202 Accepted`
- FE nên poll `GET /api/v1/stock-research/reports/{report_id}` để lấy trạng thái mới nhất
- terminal states hiện tại của flow service là:
  - `completed`
  - `failed`
