# Dashboard Visualization Template

Template thiết kế các visualizations cho dữ liệu sync từ Google Sheets. Mỗi sheet type sẽ có dashboard riêng với các charts phù hợp.

---

## Sheet Types

| Type | Description | Has Time Filter |
|------|-------------|-----------------|
| `orders` | Đơn hàng | ✅ (order_date) |
| `order_items` | Chi tiết sản phẩm trong đơn | ❌ |
| `customers` | Khách hàng | ❌ |
| `products` | Sản phẩm | ❌ |

---

## 1. Orders Dashboard

### 1.1 Summary Cards

| Card | Metric | API Field | Format |
|------|--------|-----------|--------|
| Tổng đơn hàng | Count of orders | `total_count` | Number (1,234) |
| Tổng doanh thu | Sum of total_amount | `total_amount` | Currency (50.5M đ) |
| Giá trị đơn TB | Avg of total_amount | `avg_amount` | Currency (40.9K đ) |

**API Endpoint:** `GET /api/v1/analytics/{connection_id}/summary`

**Query Parameters:**
- `date_from` (optional): ISO date string
- `date_to` (optional): ISO date string

**Response:**
```json
{
  "total_count": 1234,
  "total_amount": 50500000,
  "avg_amount": 40939
}
```

---

### 1.2 Time Series Charts

#### 1.2.1 Doanh thu theo thời gian (Line/Area Chart)

| Axis | Data |
|------|------|
| X-axis | Date (grouped by granularity) |
| Y-axis | Total Amount |

#### 1.2.2 Số đơn theo thời gian (Bar Chart)

| Axis | Data |
|------|------|
| X-axis | Date (grouped by granularity) |
| Y-axis | Order Count |

**API Endpoint:** `GET /api/v1/analytics/{connection_id}/time-series`

**Query Parameters:**
- `date_from` (required): ISO date string
- `date_to` (required): ISO date string
- `granularity`: `day` | `week` | `month` | `year` (default: `day`)
- `metrics`: `count` | `amount` | `both` (default: `both`)

**Response:**
```json
{
  "granularity": "day",
  "data": [
    {
      "date": "2025-01-01",
      "count": 50,
      "total_amount": 2000000
    },
    {
      "date": "2025-01-02",
      "count": 45,
      "total_amount": 1800000
    }
  ]
}
```

---

### 1.3 Distribution Charts

#### 1.3.1 Đơn hàng theo Platform (Pie/Donut Chart)

| Segment | Data |
|---------|------|
| Label | Platform name (Shopee, Lazada, Tiki, etc.) |
| Value | Count or Percentage |

#### 1.3.2 Trạng thái đơn hàng (Pie Chart)

| Segment | Data |
|---------|------|
| Label | Order status (pending, paid, shipped, delivered, cancelled, returned) |
| Value | Count or Percentage |

**API Endpoint:** `GET /api/v1/analytics/{connection_id}/distribution/{field}`

**Path Parameters:**
- `field`: `platform` | `order_status`

**Query Parameters:**
- `date_from` (optional): ISO date string
- `date_to` (optional): ISO date string

**Response:**
```json
{
  "field": "platform",
  "data": [
    {
      "value": "Shopee",
      "count": 500,
      "percentage": 45.0
    },
    {
      "value": "Lazada",
      "count": 350,
      "percentage": 31.5
    },
    {
      "value": "Tiki",
      "count": 260,
      "percentage": 23.5
    }
  ]
}
```

---

### 1.4 Top N Charts

#### Top Platforms theo doanh thu (Horizontal Bar Chart)

| Axis | Data |
|------|------|
| Y-axis | Platform name |
| X-axis | Total Amount |

**API Endpoint:** `GET /api/v1/analytics/{connection_id}/top/{field}`

**Path Parameters:**
- `field`: `platform`

**Query Parameters:**
- `date_from` (optional): ISO date string
- `date_to` (optional): ISO date string
- `limit`: Number (default: 10, max: 50)
- `metric`: `count` | `amount` (default: `amount`)

**Response:**
```json
{
  "field": "platform",
  "metric": "amount",
  "data": [
    {
      "value": "Shopee",
      "count": 500,
      "total_amount": 25000000
    },
    {
      "value": "Lazada",
      "count": 350,
      "total_amount": 18000000
    }
  ]
}
```

---

### 1.5 Data Table

| Column | Source Field | Sortable | Searchable |
|--------|--------------|----------|------------|
| Order ID | order_id | ✅ | ✅ |
| Platform | platform | ✅ | ✅ |
| Status | order_status | ✅ | ✅ |
| Customer ID | customer_id | ❌ | ✅ |
| Order Date | order_date | ✅ | ❌ |
| Subtotal | subtotal | ✅ | ❌ |
| Total Amount | total_amount | ✅ | ❌ |

**API Endpoint:** `GET /api/v1/analytics/{connection_id}/data`

**Query Parameters:**
- `page`: Number (default: 1)
- `page_size`: Number (default: 20, max: 100)
- `date_from` (optional): ISO date string
- `date_to` (optional): ISO date string
- `search` (optional): Search string (searches in order_id, platform, order_status, customer_id)
- `sort_by` (optional): Field name
- `sort_order`: `asc` | `desc` (default: `desc`)
- `filters` (optional): JSON object for field-specific filters

**Response:**
```json
{
  "data": [
    {
      "row_number": 1,
      "order_id": "ORD001",
      "platform": "Shopee",
      "order_status": "delivered",
      "customer_id": "C001",
      "order_date": "2025-01-10T10:30:00",
      "subtotal": 450000,
      "total_amount": 500000
    }
  ],
  "total": 1234,
  "page": 1,
  "page_size": 20,
  "total_pages": 62
}
```

---

### 1.6 Orders Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│  📅 Date Range: [2025-01-01] → [2025-01-31]  [Day ▼] [Apply]           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐            │
│  │    1,234       │  │   50.5M đ      │  │   40.9K đ      │            │
│  │   Đơn hàng     │  │   Doanh thu    │  │   TB/đơn       │            │
│  │   ↑ 12%        │  │   ↑ 8%         │  │   ↓ 3%         │            │
│  └────────────────┘  └────────────────┘  └────────────────┘            │
│                                                                          │
│  ┌──────────────────────────────────────────┐  ┌──────────────────────┐│
│  │  📈 Doanh thu theo thời gian             │  │  🥧 Platform         ││
│  │                                           │  │                      ││
│  │     ╭─────────────────────╮              │  │    ┌────┐            ││
│  │    ╱                       ╲             │  │   ╱ 45% ╲ Shopee     ││
│  │   ╱                         ╲            │  │  │ 31%   │ Lazada    ││
│  │  ╱                           ╲           │  │   ╲ 24% ╱ Tiki       ││
│  │ ╱─────────────────────────────╲          │  │    └────┘            ││
│  │ Jan    Feb    Mar    Apr    May          │  │                      ││
│  └──────────────────────────────────────────┘  └──────────────────────┘│
│                                                                          │
│  ┌──────────────────────────────────────────┐  ┌──────────────────────┐│
│  │  📊 Số đơn theo thời gian                │  │  🥧 Trạng thái       ││
│  │                                           │  │                      ││
│  │  ▁▂▃▅▆▇█▇▆▅▃▂▁▂▃▅▆▇█▇▆▅▃▂▁              │  │  ■ Delivered  65%    ││
│  │                                           │  │  ■ Shipped    20%    ││
│  │ Jan    Feb    Mar    Apr    May          │  │  ■ Pending    10%    ││
│  └──────────────────────────────────────────┘  │  ■ Cancelled   5%    ││
│                                                 └──────────────────────┘│
│  ┌──────────────────────────────────────────────────────────────────────┐
│  │  📋 Danh sách đơn hàng                    🔍 [Search...]            │
│  │  ────────────────────────────────────────────────────────────────── │
│  │  Order ID │ Platform │ Status    │ Customer │ Date       │ Amount  │
│  │  ─────────┼──────────┼───────────┼──────────┼────────────┼──────── │
│  │  ORD001   │ Shopee   │ ✅ Done   │ C001     │ 2025-01-10 │ 500K    │
│  │  ORD002   │ Lazada   │ 🚚 Ship   │ C002     │ 2025-01-10 │ 320K    │
│  │  ORD003   │ Tiki     │ ⏳ Pend   │ C003     │ 2025-01-09 │ 180K    │
│  │  ─────────────────────────────────────────────────────────────────  │
│  │  [< Prev]  Page 1 of 62  [Next >]                                   │
│  └──────────────────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Order Items Dashboard

### 2.1 Summary Cards

| Card | Metric | API Field | Format |
|------|--------|-----------|--------|
| Tổng SP đã bán | Sum of quantity | `total_quantity` | Number (5,678) |
| Tổng doanh thu SP | Sum of line_total | `total_line_total` | Currency (45.2M đ) |
| Số SP unique | Count distinct product_id | `unique_products` | Number (234) |

**API Endpoint:** `GET /api/v1/analytics/{connection_id}/summary`

**Response:**
```json
{
  "total_quantity": 5678,
  "total_line_total": 45200000,
  "unique_products": 234
}
```

---

### 2.2 Top N Charts

#### 2.2.1 Top 10 SP bán chạy (Horizontal Bar Chart)

| Axis | Data |
|------|------|
| Y-axis | Product name |
| X-axis | Quantity sold |

#### 2.2.2 Top 10 SP theo doanh thu (Horizontal Bar Chart)

| Axis | Data |
|------|------|
| Y-axis | Product name |
| X-axis | Total line_total |

**API Endpoint:** `GET /api/v1/analytics/{connection_id}/top/{field}`

**Path Parameters:**
- `field`: `product_name`

**Query Parameters:**
- `limit`: Number (default: 10, max: 50)
- `metric`: `quantity` | `amount` (default: `quantity`)

**Response:**
```json
{
  "field": "product_name",
  "metric": "quantity",
  "data": [
    {
      "value": "Áo thun nam basic",
      "quantity": 500,
      "total_line_total": 100000000
    },
    {
      "value": "Quần jean slim fit",
      "quantity": 420,
      "total_line_total": 126000000
    }
  ]
}
```

---

### 2.3 Data Table

| Column | Source Field | Sortable | Searchable |
|--------|--------------|----------|------------|
| Order Item ID | order_item_id | ✅ | ✅ |
| Order ID | order_id | ✅ | ✅ |
| Product ID | product_id | ✅ | ✅ |
| Product Name | product_name | ✅ | ✅ |
| Quantity | quantity | ✅ | ❌ |
| Unit Price | unit_price | ✅ | ❌ |
| Final Price | final_price | ✅ | ❌ |
| Line Total | line_total | ✅ | ❌ |

**API Endpoint:** `GET /api/v1/analytics/{connection_id}/data`

**Query Parameters:**
- `page`, `page_size`, `search`, `sort_by`, `sort_order`, `filters`

---

### 2.4 Order Items Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ORDER ITEMS DASHBOARD                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐            │
│  │    5,678       │  │   45.2M đ      │  │     234        │            │
│  │   SP đã bán    │  │   Doanh thu    │  │   SP unique    │            │
│  └────────────────┘  └────────────────┘  └────────────────┘            │
│                                                                          │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────┐  │
│  │  🏆 Top 10 SP bán chạy         │  │  💰 Top 10 SP theo doanh thu │  │
│  │                                 │  │                              │  │
│  │  Áo thun nam    ████████ 500   │  │  Quần jean     ████████ 126M │  │
│  │  Quần jean      ███████ 420    │  │  Áo thun nam   ███████ 100M  │  │
│  │  Váy đầm        █████ 350      │  │  Váy đầm       █████ 87M     │  │
│  │  Áo khoác       ████ 280       │  │  Áo khoác      ████ 70M      │  │
│  │  Giày sneaker   ███ 220        │  │  Giày sneaker  ███ 55M       │  │
│  └─────────────────────────────────┘  └─────────────────────────────┘  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐
│  │  📋 Chi tiết sản phẩm đã bán              🔍 [Search...]            │
│  │  ────────────────────────────────────────────────────────────────── │
│  │  Item ID │ Order ID │ Product      │ Qty │ Price  │ Total          │
│  │  ────────┼──────────┼──────────────┼─────┼────────┼─────────────── │
│  │  ITM001  │ ORD001   │ Áo thun nam  │ 2   │ 200K   │ 400K           │
│  │  ITM002  │ ORD001   │ Quần jean    │ 1   │ 350K   │ 350K           │
│  │  ITM003  │ ORD002   │ Váy đầm      │ 1   │ 450K   │ 450K           │
│  │  ─────────────────────────────────────────────────────────────────  │
│  │  [< Prev]  Page 1 of 284  [Next >]                                  │
│  └──────────────────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Customers Dashboard

### 3.1 Summary Cards

| Card | Metric | API Field | Format |
|------|--------|-----------|--------|
| Tổng khách hàng | Count of customers | `total_count` | Number (892) |

**API Endpoint:** `GET /api/v1/analytics/{connection_id}/summary`

**Response:**
```json
{
  "total_count": 892
}
```

---

### 3.2 Data Table

| Column | Source Field | Sortable | Searchable |
|--------|--------------|----------|------------|
| Customer ID | customer_id | ✅ | ✅ |
| Customer Name | customer_name | ✅ | ✅ |
| Phone | phone | ✅ | ✅ |

**API Endpoint:** `GET /api/v1/analytics/{connection_id}/data`

**Query Parameters:**
- `page`, `page_size`, `search`, `sort_by`, `sort_order`

---

### 3.3 Customers Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CUSTOMERS DASHBOARD                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────┐                                                     │
│  │     892        │                                                     │
│  │   Khách hàng   │                                                     │
│  └────────────────┘                                                     │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐
│  │  📋 Danh sách khách hàng                  🔍 [Search name/phone...]  │
│  │  ────────────────────────────────────────────────────────────────── │
│  │  Customer ID │ Customer Name        │ Phone                         │
│  │  ────────────┼──────────────────────┼────────────────────────────── │
│  │  C001        │ Nguyễn Văn A         │ 0901234567                    │
│  │  C002        │ Trần Thị B           │ 0912345678                    │
│  │  C003        │ Lê Văn C             │ 0923456789                    │
│  │  C004        │ Phạm Thị D           │ 0934567890                    │
│  │  C005        │ Hoàng Văn E          │ 0945678901                    │
│  │  ─────────────────────────────────────────────────────────────────  │
│  │  [< Prev]  Page 1 of 45  [Next >]                                   │
│  └──────────────────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Products Dashboard

### 4.1 Summary Cards

| Card | Metric | API Field | Format |
|------|--------|-----------|--------|
| Tổng sản phẩm | Count of products | `total_count` | Number (156) |

**API Endpoint:** `GET /api/v1/analytics/{connection_id}/summary`

**Response:**
```json
{
  "total_count": 156
}
```

---

### 4.2 Data Table

| Column | Source Field | Sortable | Searchable |
|--------|--------------|----------|------------|
| Product ID | product_id | ✅ | ✅ |
| Product Name | product_name | ✅ | ✅ |

**API Endpoint:** `GET /api/v1/analytics/{connection_id}/data`

**Query Parameters:**
- `page`, `page_size`, `search`, `sort_by`, `sort_order`

---

### 4.3 Products Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        PRODUCTS DASHBOARD                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────┐                                                     │
│  │     156        │                                                     │
│  │   Sản phẩm     │                                                     │
│  └────────────────┘                                                     │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐
│  │  📋 Danh sách sản phẩm                    🔍 [Search product...]     │
│  │  ────────────────────────────────────────────────────────────────── │
│  │  Product ID │ Product Name                                          │
│  │  ───────────┼────────────────────────────────────────────────────── │
│  │  P001       │ Áo thun nam basic                                     │
│  │  P002       │ Quần jean slim fit                                    │
│  │  P003       │ Váy đầm công sở                                       │
│  │  P004       │ Áo khoác bomber                                       │
│  │  P005       │ Giày sneaker trắng                                    │
│  │  ─────────────────────────────────────────────────────────────────  │
│  │  [< Prev]  Page 1 of 8  [Next >]                                    │
│  └──────────────────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. API Endpoints Summary

### Base URL: `/api/v1/analytics/{connection_id}`

| Endpoint | Method | Description | Sheet Types |
|----------|--------|-------------|-------------|
| `/summary` | GET | Summary metrics | All |
| `/time-series` | GET | Time-based aggregation | Orders only |
| `/distribution/{field}` | GET | Field value distribution | Orders only |
| `/top/{field}` | GET | Top N by field | Orders, Order Items |
| `/data` | GET | Paginated raw data with search/filter | All |

### Common Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `date_from` | ISO date | Start date filter | None |
| `date_to` | ISO date | End date filter | None |
| `page` | int | Page number | 1 |
| `page_size` | int | Items per page | 20 |
| `search` | string | Search query | None |
| `sort_by` | string | Sort field | None |
| `sort_order` | string | `asc` or `desc` | `desc` |
| `limit` | int | Top N limit | 10 |
| `granularity` | string | `day`/`week`/`month`/`year` | `day` |
| `metric` | string | `count`/`amount`/`quantity` | varies |

---

## 6. Caching Strategy

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CACHING FLOW                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   Request → Redis Cache Check                                           │
│                │                                                         │
│                ├─→ HIT → Return cached response                         │
│                │                                                         │
│                └─→ MISS → Query MongoDB → Compute → Cache → Return      │
│                                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│   Cache Key Pattern:                                                     │
│   analytics:{connection_id}:{endpoint}:{params_hash}                    │
│                                                                          │
│   Examples:                                                              │
│   - analytics:conn123:summary:abc123                                    │
│   - analytics:conn123:time-series:def456                                │
│   - analytics:conn123:distribution:platform:ghi789                      │
│                                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│   Cache TTL: 5 minutes (matches sync interval)                          │
│                                                                          │
│   Cache Invalidation:                                                    │
│   - On sync complete → Delete all cache keys for connection_id          │
│   - Pattern: analytics:{connection_id}:*                                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Error Responses

| Status | Error | Description |
|--------|-------|-------------|
| 400 | Invalid date range | date_from > date_to |
| 400 | Invalid field | Field not supported for this sheet type |
| 400 | Invalid granularity | Must be day/week/month/year |
| 404 | Connection not found | Connection ID doesn't exist |
| 403 | Access denied | User doesn't own this connection |
| 422 | Validation error | Invalid query parameters |

---

## 8. Sheet Type Field Mapping

### Orders Sheet - Required Fields

| System Field | Sheet Column | Data Type |
|--------------|--------------|-----------|
| order_id | A | string |
| platform | C | string |
| order_status | D | string |
| customer_id | E | string |
| order_date | F | datetime |
| subtotal | M | number |
| total_amount | P | number |

### Order Items Sheet - Required Fields

| System Field | Sheet Column | Data Type |
|--------------|--------------|-----------|
| order_item_id | A | string |
| order_id | B | string |
| product_id | C | string |
| product_name | D | string |
| quantity | G | number |
| unit_price | H | number |
| final_price | J | number |
| line_total | K | number |

### Customers Sheet - Required Fields

| System Field | Sheet Column | Data Type |
|--------------|--------------|-----------|
| customer_id | A | string |
| customer_name | B | string |
| phone | C | string |

### Products Sheet - Required Fields

| System Field | Sheet Column | Data Type |
|--------------|--------------|-----------|
| product_id | A | string |
| product_name | B | string |
