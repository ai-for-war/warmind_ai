# Tài Liệu Tích Hợp Frontend Cho Stock Company API

## 1. Mục tiêu tài liệu

Tài liệu này mô tả backend hiện đang cung cấp gì cho tính năng company
information của một mã chứng khoán.

Phạm vi tài liệu gồm:

- frontend cần truyền gì khi gọi API
- backend trả về schema gì
- ý nghĩa của từng endpoint
- ý nghĩa của các field trong response
- các semantics frontend cần hiểu khi tích hợp

Tài liệu này không hướng dẫn frontend cách code.

## 2. Phạm vi endpoint

Backend hiện cung cấp nhóm endpoint company info dưới base path:

```text
/api/v1/stocks/{symbol}/company/*
```

Danh sách endpoint:

- `GET /api/v1/stocks/{symbol}/company/overview`
- `GET /api/v1/stocks/{symbol}/company/shareholders`
- `GET /api/v1/stocks/{symbol}/company/officers`
- `GET /api/v1/stocks/{symbol}/company/subsidiaries`
- `GET /api/v1/stocks/{symbol}/company/affiliate`
- `GET /api/v1/stocks/{symbol}/company/events`
- `GET /api/v1/stocks/{symbol}/company/news`
- `GET /api/v1/stocks/{symbol}/company/reports`
- `GET /api/v1/stocks/{symbol}/company/ratio-summary`
- `GET /api/v1/stocks/{symbol}/company/trading-stats`

Ý nghĩa:

- mỗi endpoint trả về đúng dữ liệu của 1 tab
- backend không trả một payload aggregate gồm tất cả tab
- source hiện tại của company info là cố định `VCI`

## 3. Điều kiện để gọi API thành công

Tất cả company endpoints đều cần:

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

Tất cả endpoint company info đều dùng:

- `symbol`: mã chứng khoán cần lấy thông tin

Semantics:

- frontend có thể gửi `fpt`, `FPT`, `Fpt`
- backend sẽ normalize thành uppercase trước khi xử lý
- nếu `symbol` không tồn tại trong stock catalog của backend, request sẽ bị reject

## 4.2 Query params

Phần lớn endpoint không cần query param.

Chỉ có 2 endpoint có query param trong v1:

### `GET /api/v1/stocks/{symbol}/company/officers`

Query param:

- `filter_by`: optional

Giá trị hợp lệ:

- `working`
- `resigned`
- `all`

Mặc định:

- `working`

### `GET /api/v1/stocks/{symbol}/company/subsidiaries`

Query param:

- `filter_by`: optional

Giá trị hợp lệ:

- `all`
- `subsidiary`

Mặc định:

- `all`

## 5. Response envelope chung

Mỗi endpoint company info đều trả về envelope metadata giống nhau:

```json
{
  "symbol": "FPT",
  "source": "VCI",
  "fetched_at": "2026-04-13T03:00:00Z",
  "cache_hit": false,
  "item": {}
}
```

hoặc:

```json
{
  "symbol": "FPT",
  "source": "VCI",
  "fetched_at": "2026-04-13T03:00:00Z",
  "cache_hit": true,
  "items": []
}
```

Schema chung:

```ts
type StockCompanyResponseBase = {
  symbol: string;      // always uppercase
  source: "VCI";
  fetched_at: string;  // ISO datetime
  cache_hit: boolean;
}
```

Ý nghĩa các field:

- `symbol`: mã chứng khoán đã được backend normalize sang uppercase
- `source`: nguồn dữ liệu company info. V1 cố định là `VCI`
- `fetched_at`: thời điểm backend tạo response payload này
- `cache_hit`: `true` nếu response được đọc từ cache, `false` nếu vừa fetch và normalize mới

Lưu ý:

- `cache_hit` là metadata để frontend hiểu tính chất response, không phải error flag
- frontend không nên dùng `cache_hit` để thay đổi business logic

## 6. Phân loại response

Có 2 nhóm response:

- snapshot endpoint: trả về `item`
- list endpoint: trả về `items`

### Snapshot endpoints

- `overview`
- `ratio-summary`
- `trading-stats`

Shape:

```ts
type SnapshotResponse<T> = StockCompanyResponseBase & {
  item: T;
}
```

### List endpoints

- `shareholders`
- `officers`
- `subsidiaries`
- `affiliate`
- `events`
- `news`
- `reports`

Shape:

```ts
type ListResponse<T> = StockCompanyResponseBase & {
  items: T[];
}
```

Lưu ý:

- `items` luôn tồn tại với list endpoint
- `items` có thể là mảng rỗng
- backend chưa hỗ trợ pagination cho `news`, `events`, `reports` trong v1

## 7. Schema từng endpoint

## 7.1 Overview

Endpoint:

```text
GET /api/v1/stocks/{symbol}/company/overview
```

Ý nghĩa:

- trả về thông tin tổng quan doanh nghiệp
- phù hợp để render tab overview của company detail

Response schema:

```ts
type StockCompanyOverviewResponse = StockCompanyResponseBase & {
  item: {
    symbol: string;
    id: number | null;
    issue_share: number | null;
    history: string | null;
    company_profile: string | null;
    icb_name2: string | null;
    icb_name3: string | null;
    icb_name4: string | null;
    charter_capital: number | null;
    financial_ratio_issue_share: number | null;
  };
}
```

Ý nghĩa field chính:

- `company_profile`: mô tả công ty
- `history`: lịch sử doanh nghiệp
- `issue_share`: tổng số cổ phiếu lưu hành theo dữ liệu VCI
- `charter_capital`: vốn điều lệ
- `icb_name2`, `icb_name3`, `icb_name4`: nhóm/ngành theo cấp độ ICB

## 7.2 Shareholders

Endpoint:

```text
GET /api/v1/stocks/{symbol}/company/shareholders
```

Ý nghĩa:

- trả về danh sách cổ đông lớn

Response schema:

```ts
type StockCompanyShareholdersResponse = StockCompanyResponseBase & {
  items: Array<{
    id: number | null;
    share_holder: string | null;
    quantity: number | null;
    share_own_percent: number | null;
    update_date: string | null;
  }>;
}
```

Ý nghĩa field chính:

- `share_holder`: tên cổ đông
- `quantity`: số lượng cổ phiếu nắm giữ
- `share_own_percent`: tỷ lệ sở hữu
- `update_date`: thời điểm upstream ghi nhận dòng dữ liệu này

## 7.3 Officers

Endpoint:

```text
GET /api/v1/stocks/{symbol}/company/officers
```

Ví dụ:

```text
GET /api/v1/stocks/FPT/company/officers?filter_by=working
```

Ý nghĩa:

- trả về danh sách lãnh đạo/nhân sự quản lý theo filter

Response schema:

```ts
type StockCompanyOfficersResponse = StockCompanyResponseBase & {
  items: Array<{
    id: number | null;
    officer_name: string | null;
    officer_position: string | null;
    position_short_name: string | null;
    update_date: string | null;
    officer_own_percent: number | null;
    quantity: number | null;
    type: string | null;
  }>;
}
```

Ý nghĩa field chính:

- `officer_name`: tên lãnh đạo
- `officer_position`: chức danh đầy đủ
- `position_short_name`: chức danh ngắn
- `officer_own_percent`: tỷ lệ sở hữu của officer nếu có
- `quantity`: số lượng cổ phiếu nắm giữ nếu có
- `type`: nhóm/trạng thái upstream trả về

## 7.4 Subsidiaries

Endpoint:

```text
GET /api/v1/stocks/{symbol}/company/subsidiaries
```

Ví dụ:

```text
GET /api/v1/stocks/FPT/company/subsidiaries?filter_by=subsidiary
```

Ý nghĩa:

- trả về danh sách công ty con theo filter của VCI

Response schema:

```ts
type StockCompanySubsidiariesResponse = StockCompanyResponseBase & {
  items: Array<{
    id: number | null;
    sub_organ_code: string | null;
    organ_name: string | null;
    ownership_percent: number | null;
    type: string | null;
  }>;
}
```

Ý nghĩa field chính:

- `sub_organ_code`: mã tổ chức liên quan
- `organ_name`: tên công ty con
- `ownership_percent`: tỷ lệ sở hữu
- `type`: loại quan hệ upstream trả về

## 7.5 Affiliate

Endpoint:

```text
GET /api/v1/stocks/{symbol}/company/affiliate
```

Ý nghĩa:

- trả về danh sách công ty liên kết

Response schema:

```ts
type StockCompanyAffiliateResponse = StockCompanyResponseBase & {
  items: Array<{
    id: number | null;
    sub_organ_code: string | null;
    organ_name: string | null;
    ownership_percent: number | null;
  }>;
}
```

## 7.6 Events

Endpoint:

```text
GET /api/v1/stocks/{symbol}/company/events
```

Ý nghĩa:

- trả về sự kiện doanh nghiệp

Response schema:

```ts
type StockCompanyEventsResponse = StockCompanyResponseBase & {
  items: Array<{
    id: number | null;
    event_title: string | null;
    public_date: string | null;
    issue_date: string | null;
    source_url: string | null;
    event_list_code: string | null;
    ratio: number | null;
    value: number | null;
    record_date: string | null;
    exright_date: string | null;
    event_list_name: string | null;
  }>;
}
```

Ý nghĩa field chính:

- `event_title`: tiêu đề sự kiện
- `event_list_code`: mã loại sự kiện
- `record_date`: ngày chốt danh sách
- `exright_date`: ngày giao dịch không hưởng quyền
- `source_url`: link nguồn nếu frontend muốn deep-link

## 7.7 News

Endpoint:

```text
GET /api/v1/stocks/{symbol}/company/news
```

Ý nghĩa:

- trả về tin tức liên quan đến công ty

Response schema:

```ts
type StockCompanyNewsResponse = StockCompanyResponseBase & {
  items: Array<{
    id: number | null;
    news_title: string | null;
    news_sub_title: string | null;
    friendly_sub_title: string | null;
    news_image_url: string | null;
    news_source_link: string | null;
    created_at: string | null;
    public_date: string | null;
    updated_at: string | null;
    lang_code: string | null;
    news_id: number | null;
    news_short_content: string | null;
    news_full_content: string | null;
    close_price: number | null;
    ref_price: number | null;
    floor: number | null;
    ceiling: number | null;
    price_change_pct: number | null;
  }>;
}
```

Lưu ý semantics:

- backend đã normalize các timestamp runtime của VCI thành string datetime
- frontend nên treat `news_full_content` và `news_short_content` là nullable
- `news_source_link` là field phù hợp nếu cần mở bài viết gốc

## 7.8 Reports

Endpoint:

```text
GET /api/v1/stocks/{symbol}/company/reports
```

Ý nghĩa:

- trả về danh sách báo cáo phân tích

Response schema:

```ts
type StockCompanyReportsResponse = StockCompanyResponseBase & {
  items: Array<{
    date: string | null;
    description: string | null;
    link: string | null;
    name: string | null;
  }>;
}
```

Ý nghĩa field chính:

- `name`: tên báo cáo
- `description`: mô tả ngắn
- `link`: URL tải/mở báo cáo
- `date`: ngày của báo cáo

## 7.9 Ratio Summary

Endpoint:

```text
GET /api/v1/stocks/{symbol}/company/ratio-summary
```

Ý nghĩa:

- trả về snapshot các chỉ số tài chính tổng hợp

Response schema:

```ts
type StockCompanyRatioSummaryResponse = StockCompanyResponseBase & {
  item: {
    symbol: string;
    year_report: number | null;
    length_report: number | null;
    update_date: string | null;
    revenue: number | null;
    revenue_growth: number | null;
    net_profit: number | null;
    net_profit_growth: number | null;
    roe: number | null;
    roa: number | null;
    pe: number | null;
    pb: number | null;
    eps: number | null;
    issue_share: number | null;
    charter_capital: number | null;
    dividend: number | null;
    de: number | null;
  };
}
```

Ý nghĩa field chính:

- `year_report`: năm báo cáo
- `length_report`: kỳ báo cáo
- `revenue`, `net_profit`: chỉ số kết quả kinh doanh
- `roe`, `roa`: chỉ số hiệu quả
- `pe`, `pb`, `eps`: chỉ số valuation/thu nhập
- `de`: debt/equity

Lưu ý semantics:

- `update_date` đã được backend normalize thành string datetime
- đây là snapshot, không phải danh sách theo nhiều kỳ

## 7.10 Trading Stats

Endpoint:

```text
GET /api/v1/stocks/{symbol}/company/trading-stats
```

Ý nghĩa:

- trả về snapshot thống kê giao dịch của mã

Response schema:

```ts
type StockCompanyTradingStatsResponse = StockCompanyResponseBase & {
  item: {
    symbol: string;
    exchange: string | null;
    ev: number | null;
    ceiling: number | null;
    floor: number | null;
    ref_price: number | null;
    open: number | null;
    match_price: number | null;
    close_price: number | null;
    price_change: number | null;
    price_change_pct: number | null;
    high: number | null;
    low: number | null;
    total_volume: number | null;
    high_price_1y: number | null;
    low_price_1y: number | null;
    pct_low_change_1y: number | null;
    pct_high_change_1y: number | null;
    foreign_volume: number | null;
    foreign_room: number | null;
    avg_match_volume_2w: number | null;
    foreign_holding_room: number | null;
    current_holding_ratio: number | null;
    max_holding_ratio: number | null;
  };
}
```

Ý nghĩa field chính:

- `match_price`, `close_price`, `ref_price`: thông tin giá
- `high`, `low`: biến động trong phiên
- `total_volume`: tổng khối lượng
- `high_price_1y`, `low_price_1y`: biên giá 1 năm
- `foreign_room`, `foreign_holding_room`: thông tin room nước ngoài

## 8. Error semantics frontend cần hiểu

Backend có thể trả các nhóm lỗi sau:

- `400 Bad Request`
  - thiếu `X-Organization-ID`
  - query param không hợp lệ, ví dụ `filter_by` sai giá trị
- `401 Unauthorized`
  - token không hợp lệ
  - account không active
- `403 Forbidden`
  - user không có quyền trên organization được gửi
- `404 Not Found`
  - `symbol` không tồn tại trong stock catalog của backend
  - organization không tồn tại hoặc không active
- `500 Internal Server Error`
  - upstream lỗi và không có stale cache để fallback

Lưu ý:

- nếu 1 endpoint company bị lỗi, frontend vẫn có thể gọi endpoint khác của cùng `symbol`
- backend có cơ chế section-level isolation, không có concept "một tab lỗi thì các tab còn lại không gọi được"

## 9. Những gì frontend không nên giả định

- không nên giả định mọi field text đều có giá trị
- không nên giả định mọi field số đều có giá trị
- không nên giả định list endpoint luôn có item
- không nên giả định `news`, `events`, `reports` có pagination ở backend
- không nên giả định `cache_hit=false` mới là dữ liệu "đúng" hơn `cache_hit=true`
- không nên giả định source sẽ thay đổi trong v1

## 10. Tóm tắt contract

### Request chung

- Headers bắt buộc:
  - `Authorization: Bearer <token>`
  - `X-Organization-ID: <organization_id>`
- Path param:
  - `symbol`

### Query params đặc biệt

- `officers.filter_by`: `working | resigned | all`
- `subsidiaries.filter_by`: `all | subsidiary`

### Response chung

- `symbol`
- `source`
- `fetched_at`
- `cache_hit`
- `item` hoặc `items`

### Nhóm endpoint snapshot

- `overview`
- `ratio-summary`
- `trading-stats`

### Nhóm endpoint list

- `shareholders`
- `officers`
- `subsidiaries`
- `affiliate`
- `events`
- `news`
- `reports`
