# Tài Liệu Tích Hợp Frontend Cho Stock Research Runtime Metadata

## 1. Mục tiêu tài liệu

Tài liệu này mô tả thay đổi contract cho metadata runtime của stock research report.

Phạm vi chỉ gồm:

- frontend cần gửi gì khi tạo stock research report
- backend persist và trả về metadata runtime nào
- FE nên hiển thị và xử lý `runtime_config` như thế nào
- những điểm thay đổi so với contract cũ

Tài liệu này không hướng dẫn frontend cách code UI.

## 2. Tóm tắt thay đổi

`runtime_config` của stock research report hiện là required khi tạo report.

Trước đây FE có thể không gửi `runtime_config`, khi đó backend dùng runtime mặc định server-side. Contract mới không còn cho phép flow đó.

Backend sẽ:

1. Nhận `runtime_config` từ FE trong request tạo report.
2. Validate provider/model/reasoning theo catalog hiện tại của backend.
3. Persist resolved runtime snapshot vào report.
4. Trả `runtime_config` trong create/list/detail responses để FE hiển thị.
5. Dùng persisted runtime snapshot để chạy background job.

## 3. Endpoint liên quan

Base path:

```text
/api/v1/stock-research/reports
```

Endpoints liên quan:

- `GET /api/v1/stock-research/reports/catalog`
- `POST /api/v1/stock-research/reports`
- `GET /api/v1/stock-research/reports`
- `GET /api/v1/stock-research/reports/{report_id}`

Tất cả endpoints cần:

```http
Authorization: Bearer <token>
X-Organization-ID: <organization_id>
```

## 4. Catalog là source of truth

FE nên lấy catalog trước khi cho user tạo report:

```http
GET /api/v1/stock-research/reports/catalog
```

Catalog response có shape:

```ts
type StockResearchCatalogResponse = {
  default_provider: string;
  default_model: string;
  default_reasoning: string | null;
  providers: StockResearchCatalogProviderResponse[];
}

type StockResearchCatalogProviderResponse = {
  provider: string;
  display_name: string;
  is_default: boolean;
  models: StockResearchCatalogModelResponse[];
}

type StockResearchCatalogModelResponse = {
  model: string;
  reasoning_options: string[];
  default_reasoning: string | null;
  is_default: boolean;
}
```

FE không nên hardcode provider/model/reasoning ngoài catalog.

## 5. Create request mới

Endpoint:

```http
POST /api/v1/stock-research/reports
Content-Type: application/json
```

Request body:

```json
{
  "symbol": "FPT",
  "runtime_config": {
    "provider": "openai",
    "model": "gpt-5.2",
    "reasoning": "high"
  }
}
```

TypeScript contract:

```ts
type StockResearchReportCreateRequest = {
  symbol: string;
  runtime_config: StockResearchRuntimeConfigRequest;
}

type StockResearchRuntimeConfigRequest = {
  provider: string;
  model: string;
  reasoning?: string | null;
}
```

Validation semantics:

- `symbol`: required, min length `1`, max length `32`; backend normalize uppercase.
- `runtime_config`: required.
- `runtime_config.provider`: required.
- `runtime_config.model`: required.
- `runtime_config.reasoning`: optional/null chỉ khi selected model không yêu cầu reasoning.
- Nếu model có `reasoning_options`, FE nên gửi một giá trị nằm trong `reasoning_options`.
- Nếu model có `reasoning_options = []`, FE nên gửi `reasoning: null` hoặc omit `reasoning`.

## 6. Missing runtime_config

Nếu FE tạo report mà không gửi `runtime_config`, backend sẽ reject request ở validation layer.

Example invalid request:

```json
{
  "symbol": "FPT"
}
```

Expected behavior:

```text
422 Unprocessable Entity
```

FE không nên fallback bằng cách ẩn field runtime. Nếu UI chưa load được catalog, nên disable action tạo report hoặc yêu cầu load lại catalog.

## 7. Runtime config response

Backend trả `runtime_config` trong report summary. Field này xuất hiện trong:

- create response
- list response items
- detail response

TypeScript contract:

```ts
type StockResearchRuntimeConfigResponse = {
  provider: string;
  model: string;
  reasoning: string | null;
}

type StockResearchReportSummary = {
  id: string;
  symbol: string;
  status: "queued" | "running" | "completed" | "partial" | "failed";
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
  runtime_config: StockResearchRuntimeConfigResponse | null;
}
```

`runtime_config` có thể `null` với report cũ đã tạo trước khi backend persist metadata này. Report mới tạo theo contract hiện tại sẽ có `runtime_config`.

## 8. Create response example

```json
{
  "id": "6807dd18c5d8d14d4af1d111",
  "symbol": "FPT",
  "status": "queued",
  "created_at": "2026-04-22T08:00:00Z",
  "started_at": null,
  "completed_at": null,
  "updated_at": "2026-04-22T08:00:00Z",
  "runtime_config": {
    "provider": "openai",
    "model": "gpt-5.2",
    "reasoning": "high"
  }
}
```

Semantics:

- `runtime_config` là resolved runtime snapshot backend đã validate.
- FE nên hiển thị response value, không nên hiển thị raw local form state nếu backend đã trả response.
- Background job sẽ chạy bằng runtime snapshot này.

## 9. List response example

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
      "updated_at": "2026-04-22T09:00:41Z",
      "runtime_config": {
        "provider": "zai",
        "model": "glm-5.1",
        "reasoning": null
      }
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

FE có thể dùng `items[].runtime_config` để hiển thị provider/model/reasoning badge trên report history mà không cần gọi detail từng report.

## 10. Detail response example

```json
{
  "id": "6807dd18c5d8d14d4af1d111",
  "symbol": "FPT",
  "status": "completed",
  "created_at": "2026-04-22T08:00:00Z",
  "started_at": "2026-04-22T08:00:05Z",
  "completed_at": "2026-04-22T08:00:42Z",
  "updated_at": "2026-04-22T08:00:42Z",
  "runtime_config": {
    "provider": "openai",
    "model": "gpt-5.2",
    "reasoning": "high"
  },
  "content": "## Current Price Snapshot\n\nCurrent price is around 95,800 VND.",
  "sources": [],
  "error": null
}
```

## 11. UI display recommendation

FE nên hiển thị:

- provider: `runtime_config.provider`
- model: `runtime_config.model`
- reasoning: `runtime_config.reasoning` nếu khác `null`

Nếu `runtime_config = null`, FE nên hiển thị state nhẹ như:

- `Runtime unavailable`
- hoặc ẩn badge runtime đối với report cũ

Không nên hiển thị `reasoning: null` thành text literal `null`.

## 12. Error semantics

Backend có thể reject create request khi:

- thiếu `runtime_config`: `422`
- thiếu `provider` hoặc `model`: `422`
- provider không supported: backend app error
- model không supported với provider: backend app error
- reasoning không supported với model: backend app error
- model yêu cầu reasoning nhưng request không gửi reasoning: backend app error

FE nên ưu tiên validate bằng catalog để tránh các lỗi trên, nhưng backend vẫn là source of truth cuối cùng.

## 13. Những gì FE không nên giả định

- Không nên giả định `runtime_config` của report cũ luôn có giá trị.
- Không nên hardcode danh sách provider/model/reasoning.
- Không nên gửi `reasoning` cho model có `reasoning_options = []` nếu không cần.
- Không nên tự tạo provider/model ngoài catalog.
- Không nên xem raw request payload là metadata cuối cùng; response của backend mới là resolved snapshot.

## 14. Migration checklist cho FE

- Gọi `GET /api/v1/stock-research/reports/catalog` trước khi tạo report.
- Bắt buộc gửi `runtime_config` trong `POST /api/v1/stock-research/reports`.
- Update type create request: `runtime_config` không còn optional.
- Update type report summary: thêm `runtime_config`.
- Update history/detail UI để đọc `runtime_config` từ response.
- Xử lý `runtime_config = null` cho report cũ.

