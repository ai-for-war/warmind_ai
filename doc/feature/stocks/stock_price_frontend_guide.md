# Tài Liệu Tích Hợp Frontend Cho Stock Price API

## 1. Mục tiêu tài liệu

Tài liệu này mô tả backend hiện đang cung cấp gì cho tính năng price
timeseries của một mã chứng khoán.

Phạm vi tài liệu gồm:

- frontend cần truyền gì khi gọi API
- backend trả về schema gì
- ý nghĩa của từng endpoint
- ý nghĩa của các field trong response
- các semantics frontend cần hiểu khi tích hợp

Tài liệu này không hướng dẫn frontend cách code.

## 2. Phạm vi endpoint

Backend hiện cung cấp nhóm endpoint price dưới base path:

```text
/api/v1/stocks/{symbol}/prices/*
```

Danh sách endpoint:

- `GET /api/v1/stocks/{symbol}/prices/history`
- `GET /api/v1/stocks/{symbol}/prices/intraday`

Ý nghĩa:

- `history`: trả về historical OHLCV timeseries
- `intraday`: trả về intraday trade timeseries
- source hiện tại của price data là cố định `VCI`
- v1 chỉ trả raw timeseries, không trả analytics hay summary metrics

## 3. Điều kiện để gọi API thành công

Tất cả price endpoints đều cần:

```http
Authorization: Bearer <token>
X-Organization-ID: <organization_id>
```

Semantics:

- dữ liệu thị trường là shared dataset, không tách theo organization
- nhưng request vẫn phải đi qua auth và organization context của hệ thống
- nếu thiếu `X-Organization-ID`, backend sẽ reject request

## 4. Frontend cần truyền gì

## 4.1 Path param chung

Tất cả endpoint price đều dùng:

- `symbol`: mã chứng khoán cần lấy dữ liệu giá

Semantics:

- frontend có thể gửi `fpt`, `FPT`, `Fpt`
- backend sẽ normalize thành uppercase trước khi xử lý
- nếu `symbol` không tồn tại trong stock catalog của backend, request sẽ bị reject
- v1 chỉ support symbol có trong stock catalog hiện tại của backend

## 4.2 `GET /api/v1/stocks/{symbol}/prices/history`

Method:

```text
GET /api/v1/stocks/{symbol}/prices/history
```

Headers bắt buộc:

```http
Authorization: Bearer <token>
X-Organization-ID: <organization_id>
```

Query params hỗ trợ:

- `start`: optional string
- `end`: optional string
- `interval`: optional string, mặc định `1D`
- `length`: optional number hoặc string

Giá trị hợp lệ của `interval`:

- `1m`
- `5m`
- `15m`
- `30m`
- `1H`
- `1D`
- `1W`
- `1M`

Rule bắt buộc của request:

- phải truyền đúng một trong `start` hoặc `length`
- không được truyền đồng thời cả `start` và `length`
- nếu truyền `end` thì bắt buộc phải có `start`

Semantics:

- mode 1: explicit range dùng `start` và optional `end`
- mode 2: lookback dùng `length`
- `interval` được backend normalize theo contract VCI hiện tại

Ví dụ hợp lệ:

```http
GET /api/v1/stocks/FPT/prices/history?start=2026-04-01&interval=1D
```

```http
GET /api/v1/stocks/FPT/prices/history?start=2026-04-01&end=2026-04-15&interval=1D
```

```http
GET /api/v1/stocks/FPT/prices/history?length=30&interval=1D
```

Ví dụ không hợp lệ:

```http
GET /api/v1/stocks/FPT/prices/history?interval=1D
```

```http
GET /api/v1/stocks/FPT/prices/history?start=2026-04-01&length=30&interval=1D
```

## 4.3 `GET /api/v1/stocks/{symbol}/prices/intraday`

Method:

```text
GET /api/v1/stocks/{symbol}/prices/intraday
```

Headers bắt buộc:

```http
Authorization: Bearer <token>
X-Organization-ID: <organization_id>
```

Query params hỗ trợ:

- `page_size`: optional number, mặc định `100`, tối đa `30000`
- `last_time`: optional string
- `last_time_format`: optional string

Semantics:

- nếu không truyền `last_time`, backend đọc slice intraday gần nhất theo `page_size`
- nếu có `last_time`, backend truyền cursor này vào upstream VCI runtime path
- `last_time_format` chỉ có ý nghĩa khi frontend truyền `last_time` theo format string cụ thể

Ví dụ:

```http
GET /api/v1/stocks/FPT/prices/intraday
```

```http
GET /api/v1/stocks/FPT/prices/intraday?page_size=200
```

```http
GET /api/v1/stocks/FPT/prices/intraday?page_size=200&last_time=2026-04-15%2009:15:00&last_time_format=%25Y-%25m-%25d%20%25H:%25M:%25S
```

## 5. Response envelope chung

### 5.1 History response envelope

Shape:

```json
{
  "symbol": "FPT",
  "source": "VCI",
  "cache_hit": false,
  "interval": "1D",
  "items": []
}
```

Schema:

```ts
type StockPriceHistoryResponse = {
  symbol: string;
  source: "VCI";
  cache_hit: boolean;
  interval: "1m" | "5m" | "15m" | "30m" | "1H" | "1D" | "1W" | "1M";
  items: StockPriceHistoryItem[];
}
```

### 5.2 Intraday response envelope

Shape:

```json
{
  "symbol": "FPT",
  "source": "VCI",
  "cache_hit": true,
  "items": []
}
```

Schema:

```ts
type StockPriceIntradayResponse = {
  symbol: string;
  source: "VCI";
  cache_hit: boolean;
  items: StockPriceIntradayItem[];
}
```

Ý nghĩa các field metadata:

- `symbol`: mã chứng khoán đã được backend normalize sang uppercase
- `source`: nguồn dữ liệu giá. V1 cố định là `VCI`
- `cache_hit`: `true` nếu response được đọc từ cache, `false` nếu vừa fetch và normalize mới
- `interval`: chỉ có ở history response, phản ánh interval backend dùng cho response đó

Lưu ý:

- `cache_hit` là metadata để frontend hiểu tính chất response, không phải error flag
- frontend không nên dùng `cache_hit` để thay đổi business logic

## 6. Schema item của từng endpoint

## 6.1 History item

Schema:

```ts
type StockPriceHistoryItem = {
  time: string | null;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}
```

Ý nghĩa field:

- `time`: mốc thời gian của candle
- `open`: giá mở cửa
- `high`: giá cao nhất
- `low`: giá thấp nhất
- `close`: giá đóng cửa
- `volume`: khối lượng

Time semantics:

- `time` luôn là string hoặc `null`
- frontend không nên hardcode chỉ một format duy nhất cho `time`
- với interval dạng ngày/tuần/tháng, `time` thường là date string như `YYYY-MM-DD`
- với interval intraday như `1m`, `5m`, `15m`, `30m`, `1H`, `time` có thể là datetime string như `YYYY-MM-DDTHH:MM:SS`

Ví dụ:

```json
{
  "time": "2026-04-15",
  "open": 100.0,
  "high": 102.0,
  "low": 99.0,
  "close": 101.0,
  "volume": 1000
}
```

## 6.2 Intraday item

Schema:

```ts
type StockPriceIntradayItem = {
  time: string | null;
  price: number | null;
  volume: number | null;
  match_type: string | null;
  id: number | null;
}
```

Ý nghĩa field:

- `time`: mốc thời gian của giao dịch
- `price`: giá khớp
- `volume`: khối lượng khớp
- `match_type`: loại khớp lệnh theo dữ liệu normalize từ VCI runtime
- `id`: identifier của dòng intraday record

Ví dụ:

```json
{
  "time": "2026-04-15T09:15:00",
  "price": 101.2,
  "volume": 50,
  "match_type": "Buy",
  "id": 42
}
```

## 7. Response examples

## 7.1 Ví dụ history response

```json
{
  "symbol": "FPT",
  "source": "VCI",
  "cache_hit": false,
  "interval": "1D",
  "items": [
    {
      "time": "2026-04-14",
      "open": 100.0,
      "high": 102.0,
      "low": 99.0,
      "close": 101.0,
      "volume": 1000
    },
    {
      "time": "2026-04-15",
      "open": 101.0,
      "high": 103.0,
      "low": 100.0,
      "close": 102.0,
      "volume": 1200
    }
  ]
}
```

## 7.2 Ví dụ intraday response

```json
{
  "symbol": "FPT",
  "source": "VCI",
  "cache_hit": true,
  "items": [
    {
      "time": "2026-04-15T09:15:00",
      "price": 101.2,
      "volume": 50,
      "match_type": "Buy",
      "id": 42
    },
    {
      "time": "2026-04-15T09:16:00",
      "price": 101.3,
      "volume": 30,
      "match_type": "Sell",
      "id": 43
    }
  ]
}
```

## 8. Error semantics frontend cần hiểu

Các status chính:

- `404`: symbol không tồn tại trong stock catalog của backend
- `422`: query không hợp lệ hoặc provider reject vì input/time range không hợp lệ
- `502`: upstream/provider lỗi và backend không có stale cache cho đúng query variant

Ví dụ response lỗi:

```json
{
  "detail": "Stock symbol not found"
}
```

hoặc:

```json
{
  "detail": "provide exactly one of 'start' or 'length'"
}
```

hoặc:

```json
{
  "detail": "Failed to fetch stock price data from upstream provider"
}
```

## 9. Semantics frontend cần hiểu

### 9.1 History query mode

- `history` không phải endpoint free-form query
- frontend cần chọn rõ 1 mode:
  - range mode: `start` + optional `end`
  - lookback mode: `length`

### 9.2 Cache behavior

- backend cache theo `symbol + endpoint + query variant`
- hai request khác nhau về `interval`, `start`, `end`, `length`, `page_size`, `last_time`, `last_time_format` được xem là 2 variant khác nhau
- frontend không cần truyền thêm cờ nào để bật hoặc tắt cache

### 9.3 Raw timeseries only

- backend chỉ trả raw timeseries item list
- backend không trả summary block như min, max, pct change, average volume, trend, analytics

### 9.4 Nullable fields

- `items` luôn tồn tại
- `items` có thể là mảng rỗng
- từng field bên trong item có thể là `null` nếu upstream không materialize được giá trị đó

## 10. Những gì frontend không nên giả định

- không nên hardcode rằng mọi response luôn có dữ liệu trong `items`
- không nên hardcode rằng `time` luôn cùng một format giữa mọi interval
- không nên giả định `cache_hit=false` nghĩa là dữ liệu mới hơn về business meaning
- không nên giả định mọi symbol hợp lệ trên thị trường đều được backend support; backend chỉ support symbol có trong stock catalog hiện tại
- không nên giả định backend sẽ trả analytics hoặc summary metrics trong v1

## 11. Tóm tắt contract

### 11.1 History

- Endpoint: `GET /api/v1/stocks/{symbol}/prices/history`
- Auth: `Bearer token` + `X-Organization-ID`
- Path param:
  - `symbol`
- Query params:
  - `start`
  - `end`
  - `interval`
  - `length`
- Rule:
  - đúng một trong `start` hoặc `length`
- Response:
  - `symbol`
  - `source`
  - `cache_hit`
  - `interval`
  - `items`

### 11.2 Intraday

- Endpoint: `GET /api/v1/stocks/{symbol}/prices/intraday`
- Auth: `Bearer token` + `X-Organization-ID`
- Path param:
  - `symbol`
- Query params:
  - `page_size`
  - `last_time`
  - `last_time_format`
- Response:
  - `symbol`
  - `source`
  - `cache_hit`
  - `items`
