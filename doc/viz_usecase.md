# Sheet Analytics API - Frontend Integration Guide

## Overview

API Analytics cung cấp các endpoint để lấy dữ liệu từ Google Sheets đã sync, phục vụ cho việc hiển thị dashboard và visualizations.

**Base URL:** `/api/v1/analytics/{connection_id}`

**Authentication:** Tất cả endpoints yêu cầu Bearer token trong header:
```
Authorization: Bearer <access_token>
```

## Sheet Types

Hệ thống tự động detect sheet type dựa trên `sheet_name` (case-insensitive):

| Sheet Name | Type | Features |
|------------|------|----------|
| `Orders` | orders | Summary, Time Series, Distribution, Top, Data |
| `Order_Items` | order_items | Summary, Top, Data |
| `Customers` | customers | Summary, Data |
| `Products` | products | Summary, Data |

---

## 1. Summary Endpoint

Lấy các metrics tổng hợp cho dashboard cards.

### Request
```
GET /api/v1/analytics/{connection_id}/summary
```

### Query Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date_from` | date | No | Filter từ ngày (YYYY-MM-DD), chỉ áp dụng cho orders |
| `date_to` | date | No | Filter đến ngày (YYYY-MM-DD), chỉ áp dụng cho orders |

### Response theo Sheet Type

**Orders:**
```json
{
  "total_count": 1250,
  "total_amount": 125000000.0,
  "avg_amount": 100000.0
}
```

**Order Items:**
```json
{
  "total_quantity": 5000,
  "total_line_total": 250000000.0,
  "unique_products": 150
}
```

**Customers / Products:**
```json
{
  "total_count": 500
}
```

### Frontend Usage
```typescript
// Summary cards component
const fetchSummary = async (connectionId: string, dateFrom?: string, dateTo?: string) => {
  const params = new URLSearchParams();
  if (dateFrom) params.append('date_from', dateFrom);
  if (dateTo) params.append('date_to', dateTo);
  
  const response = await fetch(
    `/api/v1/analytics/${connectionId}/summary?${params}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  return response.json();
};
```

---

## 2. Time Series Endpoint

Lấy dữ liệu theo thời gian cho line/bar charts. **Chỉ hỗ trợ Orders sheet.**

### Request
```
GET /api/v1/analytics/{connection_id}/time-series
```

### Query Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `date_from` | date | **Yes** | - | Ngày bắt đầu (YYYY-MM-DD) |
| `date_to` | date | **Yes** | - | Ngày kết thúc (YYYY-MM-DD) |
| `granularity` | enum | No | `day` | `day`, `week`, `month`, `year` |
| `metrics` | enum | No | `both` | `count`, `amount`, `both` |

### Response
```json
{
  "granularity": "day",
  "data": [
    {
      "date": "2024-01-01",
      "count": 45,
      "total_amount": 4500000.0
    },
    {
      "date": "2024-01-02",
      "count": 52,
      "total_amount": 5200000.0
    }
  ]
}
```

### Frontend Usage - Line Chart
```typescript
// Recharts example
const fetchTimeSeries = async (
  connectionId: string,
  dateFrom: string,
  dateTo: string,
  granularity: 'day' | 'week' | 'month' | 'year' = 'day'
) => {
  const params = new URLSearchParams({
    date_from: dateFrom,
    date_to: dateTo,
    granularity,
    metrics: 'both'
  });
  
  const response = await fetch(
    `/api/v1/analytics/${connectionId}/time-series?${params}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  return response.json();
};

// Usage with Recharts
<LineChart data={timeSeriesData.data}>
  <XAxis dataKey="date" />
  <YAxis yAxisId="left" />
  <YAxis yAxisId="right" orientation="right" />
  <Line yAxisId="left" dataKey="count" stroke="#8884d8" name="Số đơn" />
  <Line yAxisId="right" dataKey="total_amount" stroke="#82ca9d" name="Doanh thu" />
</LineChart>
```

---

## 3. Distribution Endpoint

Lấy phân bố dữ liệu cho pie/donut charts. **Chỉ hỗ trợ Orders sheet.**

### Request
```
GET /api/v1/analytics/{connection_id}/distribution/{field}
```

### Path Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `field` | string | `platform` hoặc `order_status` |

### Query Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date_from` | date | No | Filter từ ngày |
| `date_to` | date | No | Filter đến ngày |

### Response
```json
{
  "field": "platform",
  "data": [
    {
      "value": "Shopee",
      "count": 450,
      "percentage": 36.0
    },
    {
      "value": "Lazada",
      "count": 350,
      "percentage": 28.0
    },
    {
      "value": "Tiki",
      "count": 250,
      "percentage": 20.0
    },
    {
      "value": "Website",
      "count": 200,
      "percentage": 16.0
    }
  ]
}
```

### Frontend Usage - Pie Chart
```typescript
// Recharts Pie Chart
const fetchDistribution = async (connectionId: string, field: 'platform' | 'order_status') => {
  const response = await fetch(
    `/api/v1/analytics/${connectionId}/distribution/${field}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  return response.json();
};

// Usage
<PieChart>
  <Pie
    data={distributionData.data}
    dataKey="count"
    nameKey="value"
    label={({ value, percentage }) => `${value}: ${percentage}%`}
  />
  <Tooltip formatter={(value, name, props) => [`${value} (${props.payload.percentage}%)`, name]} />
</PieChart>
```

---

## 4. Top N Endpoint

Lấy top items cho bar charts. **Hỗ trợ Orders và Order Items.**

### Request
```
GET /api/v1/analytics/{connection_id}/top/{field}
```

### Path Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `field` | string | Orders: `platform` / Order Items: `product_name` |

### Query Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | int | No | 10 | Số lượng items (1-50) |
| `metric` | enum | No | `amount` | `count`, `amount`, `quantity` |
| `date_from` | date | No | - | Filter từ ngày |
| `date_to` | date | No | - | Filter đến ngày |

### Response
```json
{
  "field": "product_name",
  "metric": "quantity",
  "data": [
    {
      "value": "Áo thun nam",
      "count": 150,
      "total_amount": 15000000.0,
      "total_quantity": 500
    },
    {
      "value": "Quần jean nữ",
      "count": 120,
      "total_amount": 24000000.0,
      "total_quantity": 400
    }
  ]
}
```

### Frontend Usage - Horizontal Bar Chart
```typescript
const fetchTop = async (
  connectionId: string,
  field: string,
  limit: number = 10,
  metric: 'count' | 'amount' | 'quantity' = 'amount'
) => {
  const params = new URLSearchParams({
    limit: limit.toString(),
    metric
  });
  
  const response = await fetch(
    `/api/v1/analytics/${connectionId}/top/${field}?${params}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  return response.json();
};

// Horizontal Bar Chart
<BarChart data={topData.data} layout="vertical">
  <XAxis type="number" />
  <YAxis dataKey="value" type="category" width={150} />
  <Bar dataKey="total_amount" fill="#8884d8" name="Doanh thu" />
</BarChart>
```

---

## 5. Data Endpoint

Lấy dữ liệu chi tiết với search, filter, sort và pagination cho data tables.

### Request
```
GET /api/v1/analytics/{connection_id}/data
```

### Query Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | int | No | 1 | Trang hiện tại (1-indexed) |
| `page_size` | int | No | 20 | Số records/trang (1-100) |
| `search` | string | No | - | Tìm kiếm text |
| `sort_by` | string | No | - | Field để sort |
| `sort_order` | enum | No | `desc` | `asc` hoặc `desc` |
| `date_from` | date | No | - | Filter từ ngày (orders only) |
| `date_to` | date | No | - | Filter đến ngày (orders only) |

### Searchable Fields theo Sheet Type
| Sheet Type | Searchable Fields |
|------------|-------------------|
| Orders | `order_id`, `platform`, `order_status`, `customer_id` |
| Order Items | `order_item_id`, `order_id`, `product_id`, `product_name` |
| Customers | `customer_id`, `customer_name`, `phone` |
| Products | `product_id`, `product_name` |

### Response
```json
{
  "data": [
    {
      "_id": "65abc123...",
      "connection_id": "conn_123",
      "row_number": 2,
      "data": {
        "order_id": "ORD001",
        "platform": "Shopee",
        "order_status": "completed",
        "order_date": "2024-01-15",
        "total_amount": "150000"
      }
    }
  ],
  "total": 1250,
  "page": 1,
  "page_size": 20,
  "total_pages": 63
}
```

### Frontend Usage - Data Table
```typescript
interface DataParams {
  page?: number;
  pageSize?: number;
  search?: string;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
  dateFrom?: string;
  dateTo?: string;
}

const fetchData = async (connectionId: string, params: DataParams = {}) => {
  const searchParams = new URLSearchParams();
  if (params.page) searchParams.append('page', params.page.toString());
  if (params.pageSize) searchParams.append('page_size', params.pageSize.toString());
  if (params.search) searchParams.append('search', params.search);
  if (params.sortBy) searchParams.append('sort_by', params.sortBy);
  if (params.sortOrder) searchParams.append('sort_order', params.sortOrder);
  if (params.dateFrom) searchParams.append('date_from', params.dateFrom);
  if (params.dateTo) searchParams.append('date_to', params.dateTo);
  
  const response = await fetch(
    `/api/v1/analytics/${connectionId}/data?${searchParams}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  return response.json();
};

// React Table example
const [data, setData] = useState([]);
const [pagination, setPagination] = useState({ page: 1, pageSize: 20, total: 0 });

useEffect(() => {
  fetchData(connectionId, { page: pagination.page, pageSize: pagination.pageSize })
    .then(res => {
      setData(res.data);
      setPagination(prev => ({ ...prev, total: res.total }));
    });
}, [pagination.page]);
```

---

## Error Handling

### Common Error Responses

**400 Bad Request:**
```json
{
  "detail": "Invalid date range: date_from must be before date_to"
}
```

```json
{
  "detail": "Time series not supported for sheet type 'customers'"
}
```

```json
{
  "detail": "Field 'invalid_field' not supported for sheet type 'orders'"
}
```

**404 Not Found:**
```json
{
  "detail": "Connection not found"
}
```

**422 Validation Error:**
```json
{
  "detail": [
    {
      "loc": ["query", "limit"],
      "msg": "ensure this value is less than or equal to 50",
      "type": "value_error.number.not_le"
    }
  ]
}
```

### Frontend Error Handling
```typescript
const handleApiError = (error: any) => {
  if (error.status === 400) {
    // Show user-friendly message
    toast.error(error.detail);
  } else if (error.status === 404) {
    // Redirect or show not found
    router.push('/connections');
  } else if (error.status === 422) {
    // Validation error - show field errors
    error.detail.forEach(err => {
      toast.error(`${err.loc.join('.')}: ${err.msg}`);
    });
  }
};
```

---

## Caching

- Tất cả analytics responses được cache 5 phút
- Cache tự động invalidate khi sync sheet hoàn thành
- Frontend có thể implement local caching để giảm API calls

---

## Complete Dashboard Example

```typescript
// Dashboard component với tất cả visualizations
const Dashboard = ({ connectionId }: { connectionId: string }) => {
  const [dateRange, setDateRange] = useState({ from: '2024-01-01', to: '2024-12-31' });
  const [summary, setSummary] = useState(null);
  const [timeSeries, setTimeSeries] = useState(null);
  const [platformDist, setPlatformDist] = useState(null);
  const [topProducts, setTopProducts] = useState(null);

  useEffect(() => {
    // Fetch all data in parallel
    Promise.all([
      fetchSummary(connectionId, dateRange.from, dateRange.to),
      fetchTimeSeries(connectionId, dateRange.from, dateRange.to, 'month'),
      fetchDistribution(connectionId, 'platform'),
      fetchTop(connectionId, 'product_name', 10, 'quantity')
    ]).then(([sum, ts, dist, top]) => {
      setSummary(sum);
      setTimeSeries(ts);
      setPlatformDist(dist);
      setTopProducts(top);
    });
  }, [connectionId, dateRange]);

  return (
    <div className="dashboard">
      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-4">
        <Card title="Tổng đơn hàng" value={summary?.total_count} />
        <Card title="Doanh thu" value={formatCurrency(summary?.total_amount)} />
        <Card title="Trung bình/đơn" value={formatCurrency(summary?.avg_amount)} />
      </div>

      {/* Time Series Chart */}
      <LineChart data={timeSeries?.data} />

      {/* Distribution Pie Chart */}
      <PieChart data={platformDist?.data} />

      {/* Top Products Bar Chart */}
      <BarChart data={topProducts?.data} />
    </div>
  );
};
```
