# Tài Liệu Tích Hợp Frontend Cho Backtest API

## 1. Mục tiêu tài liệu

Tài liệu này mô tả contract backend hiện tại cho tính năng backtest cổ phiếu.

Phạm vi tài liệu gồm:

- frontend cần gọi endpoint nào
- frontend cần truyền schema gì
- backend trả về schema gì
- ý nghĩa của từng field trong request và response
- các semantics frontend cần hiểu khi render dữ liệu

Tài liệu này không hướng dẫn frontend cách code.

## 2. Phạm vi endpoint

Backend hiện cung cấp nhóm endpoint backtest dưới base path:

```text
/api/v1/backtests/*
```

Danh sách endpoint:

- `GET /api/v1/backtests/templates`
- `POST /api/v1/backtests/run`

Ý nghĩa:

- `templates`: trả về catalog các template backtest mà backend đang support
- `run`: chạy một lần backtest đồng bộ và trả về toàn bộ kết quả

## 3. Điều kiện để gọi API thành công

Tất cả backtest endpoints đều cần:

```http
Authorization: Bearer <token>
X-Organization-ID: <organization_id>
```

Semantics:

- nếu thiếu `X-Organization-ID`, backend sẽ reject request
- user phải có quyền truy cập organization tương ứng
- backend hiện tự cố định các execution assumptions của v1, frontend không cần truyền thêm

## 4. Các assumptions backend đang cố định

Frontend không truyền các field sau trong request body:

- `timeframe`
- `direction`
- `position_sizing`
- `execution_model`

Backend hiện cố định:

- `timeframe = "1D"`
- `direction = "long_only"`
- `position_sizing = "all_in"`
- `execution_model = "next_open"`

Các giá trị này luôn được trả lại trong block `assumptions` của response `POST /run`.

## 5. `GET /api/v1/backtests/templates`

### 5.1 Mục đích

Endpoint này dùng để FE lấy danh sách template hiện đang được support và schema parameter của từng template.

FE nên dùng endpoint này để:

- render template picker
- render form parameter theo template
- đọc default value và min value cho từng parameter

### 5.2 Request

Method:

```text
GET /api/v1/backtests/templates
```

Headers bắt buộc:

```http
Authorization: Bearer <token>
X-Organization-ID: <organization_id>
```

Request này không có query param và không có request body.

### 5.3 Response schema

Shape:

```json
{
  "items": [
    {
      "template_id": "buy_and_hold",
      "display_name": "Buy and Hold",
      "description": "Buy once at the first eligible entry and hold until the end of the backtest window.",
      "parameters": []
    }
  ]
}
```

Schema:

```ts
type BacktestTemplateCatalogResponse = {
  items: BacktestTemplateItem[];
};

type BacktestTemplateItem = {
  template_id: "buy_and_hold" | "sma_crossover" | "ichimoku_cloud";
  display_name: string;
  description: string;
  parameters: BacktestTemplateParameter[];
};

type BacktestTemplateParameter = {
  name: string;
  type: "integer";
  required: boolean;
  default: number | null;
  min: number | null;
  description: string | null;
};
```

### 5.4 Semantics frontend cần hiểu

- `parameters` có thể là mảng rỗng với template không cần config
- `default` là default value backend khuyến nghị để FE prefill form
- `min` là min bound để FE validate input cơ bản
- `description` là text giải thích ngắn về từng parameter
- FE không nên hardcode danh sách template nếu có thể đọc từ endpoint này

### 5.5 Catalog hiện tại

#### `buy_and_hold`

- `template_id = "buy_and_hold"`
- không có parameter

#### `sma_crossover`

Parameters:

- `fast_window`: integer, required
- `slow_window`: integer, required

Rule validation:

- `fast_window < slow_window`

#### `ichimoku_cloud`

Parameters:

- `tenkan_window`: integer, required
- `kijun_window`: integer, required
- `senkou_b_window`: integer, required
- `displacement`: integer, required
- `warmup_bars`: integer, required

Rule validation:

- `tenkan_window < kijun_window < senkou_b_window`
- `warmup_bars >= senkou_b_window + displacement`

## 6. `POST /api/v1/backtests/run`

### 6.1 Mục đích

Endpoint này dùng để FE gửi một request backtest và nhận kết quả hoàn chỉnh của một lần chạy.

### 6.2 Request

Method:

```text
POST /api/v1/backtests/run
```

Headers bắt buộc:

```http
Authorization: Bearer <token>
X-Organization-ID: <organization_id>
Content-Type: application/json
```

Request body schema:

```ts
type BacktestRunRequest = {
  symbol: string;
  date_from: string;
  date_to: string;
  template_id: "buy_and_hold" | "sma_crossover" | "ichimoku_cloud";
  template_params?: BacktestTemplateParams;
  initial_capital?: number;
};

type BacktestTemplateParams =
  | Record<string, never>
  | SmaCrossoverTemplateParams
  | IchimokuCloudTemplateParams;

type SmaCrossoverTemplateParams = {
  fast_window: number;
  slow_window: number;
};

type IchimokuCloudTemplateParams = {
  tenkan_window: number;
  kijun_window: number;
  senkou_b_window: number;
  displacement: number;
  warmup_bars: number;
};
```

Ý nghĩa field:

- `symbol`: mã cổ phiếu
- `date_from`: ngày bắt đầu cửa sổ backtest, format `YYYY-MM-DD`
- `date_to`: ngày kết thúc cửa sổ backtest, format `YYYY-MM-DD`
- `template_id`: template chiến lược cần chạy
- `template_params`: object parameter đúng với template đã chọn
- `initial_capital`: vốn ban đầu; nếu bỏ qua backend dùng mặc định `100000000`

Normalization semantics:

- backend normalize `symbol` sang uppercase
- backend normalize `template_id` sang lowercase

Validation semantics:

- `date_to` phải lớn hơn hoặc bằng `date_from`
- `template_params` phải khớp đúng với `template_id`
- frontend không nên gửi thêm field ngoài contract, backend đang để `extra="forbid"`

### 6.3 Rule cho `template_params`

#### Khi `template_id = "buy_and_hold"`

`template_params` có thể:

- bỏ qua hoàn toàn
- hoặc gửi `{}` nếu FE muốn đồng nhất shape

Ví dụ hợp lệ:

```json
{
  "symbol": "FPT",
  "date_from": "2025-01-01",
  "date_to": "2025-12-31",
  "template_id": "buy_and_hold"
}
```

#### Khi `template_id = "sma_crossover"`

`template_params` bắt buộc có:

- `fast_window`
- `slow_window`

Ví dụ hợp lệ:

```json
{
  "symbol": "FPT",
  "date_from": "2025-01-01",
  "date_to": "2025-12-31",
  "template_id": "sma_crossover",
  "template_params": {
    "fast_window": 20,
    "slow_window": 50
  }
}
```

#### Khi `template_id = "ichimoku_cloud"`

`template_params` bắt buộc có đủ:

- `tenkan_window`
- `kijun_window`
- `senkou_b_window`
- `displacement`
- `warmup_bars`

Ví dụ hợp lệ:

```json
{
  "symbol": "VIC",
  "date_from": "2025-01-18",
  "date_to": "2026-12-31",
  "template_id": "ichimoku_cloud",
  "template_params": {
    "tenkan_window": 9,
    "kijun_window": 26,
    "senkou_b_window": 52,
    "displacement": 26,
    "warmup_bars": 100
  },
  "initial_capital": 100000000
}
```

## 7. Response của `POST /api/v1/backtests/run`

### 7.1 Response envelope

Shape:

```json
{
  "result": {
    "summary_metrics": {
      "symbol": "FPT",
      "template_id": "sma_crossover",
      "timeframe": "1D",
      "date_from": "2025-01-01",
      "date_to": "2025-12-31",
      "initial_capital": 100000000,
      "ending_equity": 120000000,
      "total_trades": 1
    },
    "performance_metrics": {
      "total_return_pct": 20.0,
      "annualized_return_pct": 20.0,
      "max_drawdown_pct": 5.0,
      "win_rate_pct": 100.0,
      "profit_factor": 20000000.0,
      "avg_win_pct": 20.0,
      "avg_loss_pct": 0.0,
      "expectancy": 20.0
    },
    "trade_log": [
      {
        "entry_time": "2024-01-02",
        "entry_price": 100.0,
        "exit_time": "2024-12-31",
        "exit_price": 120.0,
        "shares": 1000000,
        "invested_capital": 100000000.0,
        "pnl": 20000000.0,
        "pnl_pct": 20.0,
        "exit_reason": "end_of_window"
      }
    ],
    "equity_curve": [
      {
        "time": "2024-12-31",
        "cash": 120000000.0,
        "market_value": 0.0,
        "equity": 120000000.0,
        "drawdown_pct": 0.0,
        "position_size": 0
      }
    ]
  },
  "assumptions": {
    "timeframe": "1D",
    "direction": "long_only",
    "position_sizing": "all_in",
    "execution_model": "next_open",
    "initial_capital": 100000000
  }
}
```

Schema:

```ts
type BacktestRunResponse = {
  result: BacktestResult;
  assumptions: BacktestRunAssumptions;
};

type BacktestRunAssumptions = {
  timeframe: "1D";
  direction: "long_only";
  position_sizing: "all_in";
  execution_model: "next_open";
  initial_capital: number;
};

type BacktestResult = {
  summary_metrics: BacktestSummaryMetrics;
  performance_metrics: BacktestPerformanceMetrics;
  trade_log: BacktestTradeLogEntry[];
  equity_curve: BacktestEquityCurvePoint[];
};

type BacktestSummaryMetrics = {
  symbol: string;
  template_id: "buy_and_hold" | "sma_crossover" | "ichimoku_cloud";
  timeframe: "1D";
  date_from: string;
  date_to: string;
  initial_capital: number;
  ending_equity: number;
  total_trades: number;
};

type BacktestPerformanceMetrics = {
  total_return_pct: number;
  annualized_return_pct: number;
  max_drawdown_pct: number;
  win_rate_pct: number;
  profit_factor: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  expectancy: number;
};

type BacktestTradeLogEntry = {
  entry_time: string;
  entry_price: number;
  exit_time: string;
  exit_price: number;
  shares: number;
  invested_capital: number;
  pnl: number;
  pnl_pct: number;
  exit_reason: string;
};

type BacktestEquityCurvePoint = {
  time: string;
  cash: number;
  market_value: number;
  equity: number;
  drawdown_pct: number;
  position_size: number;
};
```

## 8. Ý nghĩa các block trong response

### 8.1 `result.summary_metrics`

Block này là metadata tổng quan của lần chạy:

- `symbol`: symbol đã được backend normalize sang uppercase
- `template_id`: template đã chạy
- `timeframe`: hiện luôn là `1D`
- `date_from`: mốc đầu cửa sổ backtest
- `date_to`: mốc cuối cửa sổ backtest
- `initial_capital`: vốn đầu kỳ
- `ending_equity`: equity cuối kỳ
- `total_trades`: số trade đã đóng

### 8.2 `result.performance_metrics`

Block này là các chỉ số hiệu suất đã được backend tính sẵn:

- `total_return_pct`: tổng lợi nhuận phần trăm
- `annualized_return_pct`: lợi nhuận quy đổi theo năm
- `max_drawdown_pct`: drawdown lớn nhất
- `win_rate_pct`: tỷ lệ trade thắng
- `profit_factor`: tổng lãi chia tổng lỗ
- `avg_win_pct`: trung bình phần trăm của trade thắng
- `avg_loss_pct`: trung bình phần trăm của trade thua
- `expectancy`: kỳ vọng trung bình mỗi trade

### 8.3 `result.trade_log`

Đây là danh sách các trade đã đóng.

Ý nghĩa field:

- `entry_time`: thời điểm vào lệnh
- `entry_price`: giá vào lệnh
- `exit_time`: thời điểm thoát lệnh
- `exit_price`: giá thoát lệnh
- `shares`: số lượng cổ phiếu đã mua
- `invested_capital`: vốn được dùng cho trade đó
- `pnl`: lãi/lỗ tuyệt đối
- `pnl_pct`: lãi/lỗ theo phần trăm
- `exit_reason`: lý do backend dùng để đóng lệnh

Lưu ý:

- `trade_log` có thể là mảng rỗng nếu không có giao dịch nào
- `entry_time` và `exit_time` là string; FE nên treat như timestamp string từ backend, không nên hardcode đúng một format duy nhất

### 8.4 `result.equity_curve`

Đây là chuỗi điểm equity theo thời gian.

Ý nghĩa field:

- `time`: mốc thời gian của snapshot
- `cash`: lượng tiền mặt tại snapshot đó
- `market_value`: giá trị thị trường của vị thế mở
- `equity`: tổng equity = `cash + market_value`
- `drawdown_pct`: drawdown tại snapshot đó
- `position_size`: số lượng cổ phiếu đang nắm giữ

Lưu ý:

- `equity_curve` có thể khá lớn với window backtest dài
- mỗi phần tử phản ánh một snapshot theo bar daily

### 8.5 `assumptions`

Block này mô tả các giả định engine mà backend đã áp dụng cho lần chạy.

Frontend nên dùng block này để hiển thị rõ execution model hiện tại thay vì tự hardcode text riêng.

## 9. Error semantics frontend cần hiểu

Các status chính:

- `400`: thiếu `X-Organization-ID`
- `403`: user không có quyền truy cập organization
- `422`: request body không hợp lệ
- `502`: backend không chạy được backtest vì lỗi upstream/service nội bộ

Ví dụ lỗi `422`:

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "template_params"],
      "msg": "Value error, ichimoku windows must satisfy tenkan_window < kijun_window < senkou_b_window",
      "input": {
        "tenkan_window": 26,
        "kijun_window": 9,
        "senkou_b_window": 52,
        "displacement": 26,
        "warmup_bars": 100
      }
    }
  ]
}
```

Ví dụ lỗi `400`:

```json
{
  "detail": "X-Organization-ID header is required"
}
```

## 10. Những gì frontend không nên giả định

- không nên giả định mọi template luôn có parameter
- không nên giả định `template_params` của mọi template có cùng shape
- không nên gửi thêm các field engine như `timeframe`, `direction`, `position_sizing`, `execution_model`
- không nên giả định `trade_log` luôn có ít nhất một phần tử
- không nên giả định `equity_curve` luôn có cùng độ dài giữa các lần chạy
- không nên hardcode riêng danh sách template nếu đã có thể đọc từ `/backtests/templates`
- không nên hardcode đúng một format duy nhất cho các field thời gian trong response

## 11. Tóm tắt contract

### 11.1 Template catalog

- Endpoint: `GET /api/v1/backtests/templates`
- Auth: `Bearer token` + `X-Organization-ID`
- Request body: không có
- Response:
  - `items[]`
  - `items[].template_id`
  - `items[].display_name`
  - `items[].description`
  - `items[].parameters[]`

### 11.2 Run backtest

- Endpoint: `POST /api/v1/backtests/run`
- Auth: `Bearer token` + `X-Organization-ID`
- Request body:
  - `symbol`
  - `date_from`
  - `date_to`
  - `template_id`
  - `template_params`
  - `initial_capital`
- Response:
  - `result.summary_metrics`
  - `result.performance_metrics`
  - `result.trade_log`
  - `result.equity_curve`
  - `assumptions`
