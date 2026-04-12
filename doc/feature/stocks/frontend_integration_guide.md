# Tài Liệu Tích Hợp Frontend Cho Stock Catalog API

## 1. Mục tiêu tài liệu

Tài liệu này mô tả backend hiện đang cung cấp gì cho tính năng:

- lấy danh sách mã chứng khoán
- tìm kiếm mã chứng khoán
- lọc theo sàn
- lọc theo nhóm

Phạm vi tài liệu chỉ gồm:

- frontend cần truyền gì khi gọi API
- backend trả về dữ liệu gì
- ý nghĩa của các field trong response
- các semantics frontend cần hiểu khi dùng API

Tài liệu này không hướng dẫn frontend cách code.

## 2. Endpoint hiện có

Backend hiện cung cấp endpoint:

```text
GET /api/v1/stocks
```

Ý nghĩa:

- `GET /api/v1/stocks`: lấy catalog mã chứng khoán đã được persist trong backend

## 3. Điều kiện để gọi API thành công

### 3.1 `GET /api/v1/stocks`

Request cần có:

- `Authorization: Bearer <token>`
- `X-Organization-ID: <organization_id>`

Read API này dùng org-auth hiện tại của hệ thống. Dữ liệu stock catalog là global shared dataset, nhưng request vẫn phải đi qua auth và organization context.

## 4. Frontend cần truyền gì

## 4.1 `GET /api/v1/stocks`

Method:

```text
GET /api/v1/stocks
```

Headers bắt buộc:

```http
Authorization: Bearer <token>
X-Organization-ID: <organization_id>
```

Query params hỗ trợ:

- `q`: optional, tìm theo mã hoặc tên công ty
- `exchange`: optional, lọc theo sàn
- `group`: optional, lọc theo nhóm
- `page`: optional, mặc định `1`
- `page_size`: optional, mặc định `20`, tối đa `100`

Ví dụ:

```http
GET /api/v1/stocks?page=1&page_size=20
```

```http
GET /api/v1/stocks?q=fpt&page=1&page_size=20
```

```http
GET /api/v1/stocks?exchange=HOSE&group=VN30&page=1&page_size=20
```

Lưu ý semantics:

- nếu không truyền `q`, `exchange`, `group`, backend sẽ đi theo flow default list
- nếu có bất kỳ filter nào trong `q`, `exchange`, `group`, backend xem đó là filtered request
- backend normalize `exchange` và `group` sang uppercase trước khi query
- `q` được trim khoảng trắng; blank string được coi như không truyền

## 5. Backend trả về gì

## 5.1 Response của `GET /api/v1/stocks`

Shape response:

```json
{
  "items": [
    {
      "symbol": "FPT",
      "organ_name": "Công ty Cổ phần FPT",
      "exchange": "HOSE",
      "groups": ["VN30", "VN100"],
      "industry_code": 8300,
      "industry_name": "Công nghệ",
      "source": "VCI",
      "snapshot_at": "2026-04-13T01:00:00Z",
      "updated_at": "2026-04-13T01:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

Schema cụ thể:

```ts
type StockListResponse = {
  items: StockListItem[];   // always present
  total: number;            // always present
  page: number;             // always present
  page_size: number;        // always present
}

type StockListItem = {
  symbol: string;                 // always present
  organ_name: string | null;      // nullable
  exchange: string | null;        // nullable
  groups: string[];               // always present, có thể là []
  industry_code: number | null;   // nullable
  industry_name: string | null;   // nullable
  source: string;                 // always present
  snapshot_at: string;            // always present, ISO datetime
  updated_at: string;             // always present, ISO datetime
}
```

Nullable semantics:

- `symbol`: không null
- `organ_name`: có thể `null`
- `exchange`: có thể `null`
- `groups`: không null, nhưng có thể là mảng rỗng
- `industry_code`: có thể `null`
- `industry_name`: có thể `null`
- `source`: không null
- `snapshot_at`: không null
- `updated_at`: không null

Root response semantics:

- `items`: không null, có thể là mảng rỗng
- `total`: không null
- `page`: không null
- `page_size`: không null

Ý nghĩa root fields:

- `items`: danh sách mã chứng khoán trong page hiện tại
- `total`: tổng số bản ghi match với filter hiện tại
- `page`: page hiện tại
- `page_size`: kích thước page hiện tại

Ý nghĩa từng item:

- `symbol`: mã chứng khoán
- `organ_name`: tên công ty/tổ chức phát hành
- `exchange`: sàn giao dịch, ví dụ `HOSE`, `HNX`, `UPCOM`
- `groups`: danh sách group/index membership mà backend đang persist
- `industry_code`: mã ngành đã normalize từ upstream
- `industry_name`: tên ngành đã normalize từ upstream
- `source`: nguồn dữ liệu hiện tại, v1 là `VCI`
- `snapshot_at`: thời điểm snapshot catalog hiện tại được tạo
- `updated_at`: thời điểm record này được backend persist/update

## 6. Semantics frontend cần hiểu

### 6.1 Search và filter

- `q` match trên symbol hoặc tên công ty đã được normalize trong backend
- `exchange` lọc exact match
- `group` lọc theo membership trong `groups`

### 6.2 Pagination

- API hiện dùng page-based pagination
- `total` là tổng số bản ghi theo filter hiện tại, không phải số item của page hiện tại

### 6.3 Cache behavior

- backend chỉ dùng cache cho default list không filter
- filtered requests không dùng cache
- frontend không cần truyền thêm cờ nào để bật/tắt cache

### 6.4 Freshness

- dữ liệu đọc từ catalog đã persist, không fetch upstream trực tiếp trong `GET /api/v1/stocks`
- frontend có thể dùng `snapshot_at` và `updated_at` để hiển thị độ mới của dữ liệu nếu cần

## 7. Những gì frontend không nên giả định

- không nên hardcode rằng mọi stock luôn có `organ_name`, `exchange`, `industry_code`, `industry_name`
- không nên hardcode rằng `groups` luôn có giá trị
- không nên giả định filtered request sẽ được cache

## 8. Tóm tắt contract

### 8.1 Read catalog

- Endpoint: `GET /api/v1/stocks`
- Auth: `Bearer token` + `X-Organization-ID`
- Query params:
  - `q`
  - `exchange`
  - `group`
  - `page`
  - `page_size`
- Response:
  - `items`
  - `total`
  - `page`
  - `page_size`
