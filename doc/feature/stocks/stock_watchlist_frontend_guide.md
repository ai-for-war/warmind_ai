# Tài Liệu Tích Hợp Frontend Cho Stock Watchlist API

## 1. Mục tiêu tài liệu

Tài liệu này mô tả contract backend cho tính năng stock watchlist.

Phạm vi tài liệu chỉ gồm:

- frontend cần truyền gì khi gọi API
- endpoint nào đang có
- request schema của từng endpoint
- response schema của từng endpoint
- nullable semantics và error semantics

Tài liệu này không hướng dẫn frontend cách code.

## 2. Base path

Tất cả watchlist endpoints dùng base path:

```text
/api/v1/stocks/watchlists
```

Danh sách endpoint:

- `POST /api/v1/stocks/watchlists`
- `GET /api/v1/stocks/watchlists`
- `PATCH /api/v1/stocks/watchlists/{watchlist_id}`
- `DELETE /api/v1/stocks/watchlists/{watchlist_id}`
- `GET /api/v1/stocks/watchlists/{watchlist_id}/items`
- `POST /api/v1/stocks/watchlists/{watchlist_id}/items`
- `DELETE /api/v1/stocks/watchlists/{watchlist_id}/items/{symbol}`

## 3. Điều kiện để gọi API thành công

Tất cả watchlist endpoints đều cần:

```http
Authorization: Bearer <token>
X-Organization-ID: <organization_id>
```

Semantics:

- watchlist được scope theo `user + organization`
- cùng 1 user nhưng organization khác nhau sẽ có tập watchlist khác nhau
- nếu thiếu `X-Organization-ID`, backend sẽ reject request
- nếu user không thuộc organization được gửi lên, backend sẽ reject request

## 4. Định danh và normalization frontend cần hiểu

### 4.1 `watchlist_id`

- là string id của watchlist
- frontend chỉ cần gửi lại đúng giá trị đã nhận từ backend

### 4.2 `symbol`

- frontend có thể gửi `fpt`, `FPT`, ` FPT `
- backend sẽ normalize về uppercase trước khi xử lý
- response luôn trả `symbol` ở dạng uppercase

### 4.3 `name`

- backend trim khoảng trắng 2 đầu
- blank string là không hợp lệ
- tên watchlist phải unique trong cùng `user + organization`

## 5. Request schema của từng endpoint

## 5.1 Tạo watchlist

Endpoint:

```text
POST /api/v1/stocks/watchlists
```

Headers bắt buộc:

```http
Authorization: Bearer <token>
X-Organization-ID: <organization_id>
Content-Type: application/json
```

Request body:

```json
{
  "name": "Tech"
}
```

Schema:

```ts
type CreateStockWatchlistRequest = {
  name: string; // required, min length 1, max length 255
}
```

## 5.2 Lấy danh sách watchlist

Endpoint:

```text
GET /api/v1/stocks/watchlists
```

Không có query param trong v1.

## 5.3 Đổi tên watchlist

Endpoint:

```text
PATCH /api/v1/stocks/watchlists/{watchlist_id}
```

Request body:

```json
{
  "name": "Growth"
}
```

Schema:

```ts
type RenameStockWatchlistRequest = {
  name: string; // required, min length 1, max length 255
}
```

## 5.4 Xóa watchlist

Endpoint:

```text
DELETE /api/v1/stocks/watchlists/{watchlist_id}
```

Không có request body.

## 5.5 Lấy items của watchlist

Endpoint:

```text
GET /api/v1/stocks/watchlists/{watchlist_id}/items
```

Không có query param trong v1.

## 5.6 Thêm symbol vào watchlist

Endpoint:

```text
POST /api/v1/stocks/watchlists/{watchlist_id}/items
```

Request body:

```json
{
  "symbol": "FPT"
}
```

Schema:

```ts
type AddStockWatchlistItemRequest = {
  symbol: string; // required, min length 1, max length 32
}
```

## 5.7 Xóa symbol khỏi watchlist

Endpoint:

```text
DELETE /api/v1/stocks/watchlists/{watchlist_id}/items/{symbol}
```

Không có request body.

`symbol` được gửi trên path param.

## 6. Response schema chung

## 6.1 Watchlist summary

Schema:

```ts
type StockWatchlistSummary = {
  id: string;
  user_id: string;
  organization_id: string;
  name: string;
  created_at: string; // ISO datetime
  updated_at: string; // ISO datetime
}
```

Semantics:

- `id`: watchlist id
- `user_id`: user owner của watchlist
- `organization_id`: organization owner của watchlist
- `name`: tên watchlist đã được backend trim
- `created_at`: thời điểm tạo watchlist
- `updated_at`: thời điểm update gần nhất của watchlist

## 6.2 Stock metadata block trên watchlist item

Schema:

```ts
type StockWatchlistStockMetadata = {
  symbol: string;
  organ_name: string | null;
  exchange: string | null;
  groups: string[];
  industry_code: number | null;
  industry_name: string | null;
  source: string;
  snapshot_at: string; // ISO datetime
  updated_at: string;  // ISO datetime
}
```

Nullable semantics:

- `organ_name`: nullable
- `exchange`: nullable
- `groups`: không null, có thể là `[]`
- `industry_code`: nullable
- `industry_name`: nullable
- `source`: non-null
- `snapshot_at`: non-null
- `updated_at`: non-null

## 6.3 Watchlist item response

Schema:

```ts
type StockWatchlistItemResponse = {
  id: string;
  watchlist_id: string;
  user_id: string;
  organization_id: string;
  symbol: string;
  saved_at: string;   // ISO datetime
  updated_at: string; // ISO datetime
  stock: StockWatchlistStockMetadata | null;
}
```

Semantics:

- `stock` là dữ liệu stock catalog mới nhất được merge ở thời điểm read
- `stock` có thể là `null` nếu item vẫn tồn tại nhưng symbol không còn xuất hiện trong active stock catalog

## 7. Response schema của từng endpoint

## 7.1 Tạo watchlist

Status code thành công:

- `201 Created`

Response body:

```json
{
  "id": "6800f0b7f3fd5843f1f347f1",
  "user_id": "user-1",
  "organization_id": "org-1",
  "name": "Tech",
  "created_at": "2026-04-17T00:00:00Z",
  "updated_at": "2026-04-17T00:00:00Z"
}
```

Schema:

```ts
type CreateStockWatchlistResponse = StockWatchlistSummary
```

## 7.2 Lấy danh sách watchlist

Status code thành công:

- `200 OK`

Response body:

```json
{
  "items": [
    {
      "id": "6800f0b7f3fd5843f1f347f1",
      "user_id": "user-1",
      "organization_id": "org-1",
      "name": "Tech",
      "created_at": "2026-04-17T00:00:00Z",
      "updated_at": "2026-04-17T00:10:00Z"
    }
  ]
}
```

Schema:

```ts
type ListStockWatchlistsResponse = {
  items: StockWatchlistSummary[];
}
```

Semantics:

- `items` luôn tồn tại
- `items` có thể là mảng rỗng

## 7.3 Đổi tên watchlist

Status code thành công:

- `200 OK`

Response schema:

```ts
type RenameStockWatchlistResponse = StockWatchlistSummary
```

## 7.4 Xóa watchlist

Status code thành công:

- `200 OK`

Response body:

```json
{
  "id": "6800f0b7f3fd5843f1f347f1",
  "deleted": true
}
```

Schema:

```ts
type DeleteStockWatchlistResponse = {
  id: string;
  deleted: boolean; // current success value is always true
}
```

## 7.5 Lấy items của watchlist

Status code thành công:

- `200 OK`

Response body:

```json
{
  "watchlist": {
    "id": "6800f0b7f3fd5843f1f347f1",
    "user_id": "user-1",
    "organization_id": "org-1",
    "name": "Tech",
    "created_at": "2026-04-17T00:00:00Z",
    "updated_at": "2026-04-17T00:10:00Z"
  },
  "items": [
    {
      "id": "6800f11bf3fd5843f1f347f2",
      "watchlist_id": "6800f0b7f3fd5843f1f347f1",
      "user_id": "user-1",
      "organization_id": "org-1",
      "symbol": "FPT",
      "saved_at": "2026-04-17T00:15:00Z",
      "updated_at": "2026-04-17T00:15:00Z",
      "stock": {
        "symbol": "FPT",
        "organ_name": "Cong ty Co phan FPT",
        "exchange": "HOSE",
        "groups": ["VN30", "VN100"],
        "industry_code": 8300,
        "industry_name": "Cong nghe",
        "source": "VCI",
        "snapshot_at": "2026-04-18T01:00:00Z",
        "updated_at": "2026-04-18T01:00:00Z"
      }
    }
  ]
}
```

Schema:

```ts
type ListStockWatchlistItemsResponse = {
  watchlist: StockWatchlistSummary;
  items: StockWatchlistItemResponse[];
}
```

Semantics:

- `items` được sort theo `saved_at` giảm dần, item mới save nhất đứng trước
- `watchlist` luôn tồn tại nếu request thành công
- `items` có thể là mảng rỗng

## 7.6 Thêm symbol vào watchlist

Status code thành công:

- `201 Created`

Response schema:

```ts
type AddStockWatchlistItemResponse = StockWatchlistItemResponse
```

## 7.7 Xóa symbol khỏi watchlist

Status code thành công:

- `200 OK`

Response body:

```json
{
  "watchlist_id": "6800f0b7f3fd5843f1f347f1",
  "symbol": "FPT",
  "removed": true
}
```

Schema:

```ts
type RemoveStockWatchlistItemResponse = {
  watchlist_id: string;
  symbol: string;
  removed: boolean; // current success value is always true
}
```

## 8. Error response shape

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

## 9. Error semantics frontend cần hiểu

Có thể gặp các nhóm lỗi sau:

- `400 Bad Request`
  - thiếu `X-Organization-ID`
  - request body không hợp lệ, ví dụ blank `name` hoặc blank `symbol`
- `401 Unauthorized`
  - token không hợp lệ
  - account không active
- `403 Forbidden`
  - user không thuộc organization được gửi lên
- `404 Not Found`
  - organization không tồn tại hoặc không active
  - watchlist không tồn tại hoặc không thuộc user hiện tại trong organization hiện tại
  - watchlist item không tồn tại
  - symbol không tồn tại trong active stock catalog
- `409 Conflict`
  - tên watchlist đã tồn tại trong cùng `user + organization`
  - symbol đã tồn tại trong cùng 1 watchlist

## 10. Error detail hiện tại

Những `detail` message FE có thể nhận trong implementation hiện tại:

- `X-Organization-ID header is required`
- `Permission denied`
- `Organization not found`
- `Stock watchlist not found`
- `Stock watchlist item not found`
- `Stock watchlist name already exists`
- `Stock symbol already exists in this watchlist`
- `Stock symbol not found`

Frontend không nên hardcode business logic dựa trên text message này. Nếu cần branch logic, nên ưu tiên dựa trên status code.

## 11. Những gì frontend không nên giả định

- không nên giả định `stock` luôn có giá trị; field này có thể là `null`
- không nên giả định `groups` luôn có phần tử; field này có thể là `[]`
- không nên giả định watchlist list có pagination trong v1
- không nên giả định watchlist items có pagination trong v1
- không nên giả định `user_id` và `organization_id` sẽ không xuất hiện trong response; hiện tại backend có trả về
- không nên giả định xóa watchlist trả `204`; implementation hiện tại trả `200` và có body
- không nên giả định xóa item trả `204`; implementation hiện tại trả `200` và có body

## 12. Tóm tắt contract

### Headers bắt buộc

- `Authorization: Bearer <token>`
- `X-Organization-ID: <organization_id>`

### Request body trong v1

- create watchlist:
  - `name`
- rename watchlist:
  - `name`
- add item:
  - `symbol`

### Response chính trong v1

- watchlist summary:
  - `id`
  - `user_id`
  - `organization_id`
  - `name`
  - `created_at`
  - `updated_at`
- watchlist item:
  - `id`
  - `watchlist_id`
  - `user_id`
  - `organization_id`
  - `symbol`
  - `saved_at`
  - `updated_at`
  - `stock`

### Ordering semantics

- `GET /api/v1/stocks/watchlists/{watchlist_id}/items` trả về newest-first theo `saved_at desc`
