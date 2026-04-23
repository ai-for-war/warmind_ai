# Tài Liệu Tích Hợp Frontend Cho Notification API

## 1. Mục tiêu tài liệu

Tài liệu này mô tả contract backend cho tính năng in-app notification.

Phạm vi tài liệu chỉ gồm:

- frontend cần truyền gì khi gọi API
- endpoint nào hiện có
- request schema của từng endpoint
- response schema của từng endpoint
- socket event nào backend sẽ bắn về frontend
- nullable semantics, read-state semantics, và error semantics

Tài liệu này không hướng dẫn frontend cách code.

## 2. Base path

Tất cả notification endpoints dùng base path:

```text
/api/v1/notifications
```

Danh sách endpoint hiện có:

- `GET /api/v1/notifications/unread-count`
- `GET /api/v1/notifications`
- `POST /api/v1/notifications/{notification_id}/read`
- `POST /api/v1/notifications/read-all`

Socket event hiện có:

- `notification:created`

## 3. Điều kiện để gọi API thành công

Tất cả notification endpoints đều cần:

```http
Authorization: Bearer <token>
X-Organization-ID: <organization_id>
```

Semantics:

- notification được scope theo `current_user + organization`
- cùng một user nhưng organization khác nhau sẽ thấy inbox khác nhau
- nếu thiếu `X-Organization-ID`, backend sẽ reject request
- nếu user không thuộc organization được gửi lên, backend sẽ reject request

## 4. Tổng quan contract FE

Trong v1, frontend không có endpoint tạo notification.

Notification được tạo từ backend business flow, sau đó frontend:

1. gọi `GET /unread-count` để lấy số unread hiện tại
2. gọi `GET /notifications?page=&page_size=` để lấy danh sách inbox
3. nhận socket event `notification:created` khi có inbox item mới
4. gọi `POST /notifications/{notification_id}/read` để mark một item đã đọc
5. gọi `POST /notifications/read-all` để mark tất cả unread item đã đọc

## 5. Định danh và semantics frontend cần hiểu

### 5.1 `notification_id`

- là string id của notification
- frontend chỉ cần gửi lại đúng giá trị đã nhận từ backend

### 5.2 `type`

- là loại notification
- dùng để phân biệt ý nghĩa nghiệp vụ của thông báo

Ví dụ giá trị hiện có:

- `stock_research_report_completed`
- `stock_research_report_failed`

Lưu ý:

- schema là `string`, frontend không nên hardcode rằng chỉ có 2 giá trị này trong tương lai

### 5.3 `target_type`

- là loại resource đích mà notification trỏ tới
- dùng cùng với `target_id` để xác định object được mở khi user click

Ví dụ giá trị hiện có:

- `stock_research_report`

Lưu ý:

- schema là `string`, frontend không nên hardcode rằng chỉ có 1 giá trị này trong tương lai

### 5.4 `target_id`

- là id của resource đích tương ứng với `target_type`
- frontend chỉ cần dùng lại đúng giá trị đã nhận từ backend

### 5.5 `link`

- là route override optional
- có thể có giá trị khi backend muốn deep-link tới một route cụ thể
- có thể là `null`

### 5.6 `metadata`

- là object optional để frontend đọc thêm context render
- có thể là `null`
- shape bên trong không có schema cố định toàn cục trong v1

Ví dụ metadata cho notification stock research:

```ts
type StockResearchNotificationMetadata = {
  symbol: string;
  report_status: "completed" | "failed";
}
```

## 6. Request schema của từng endpoint

## 6.1 Lấy unread count

Endpoint:

```text
GET /api/v1/notifications/unread-count
```

Không có:

- path param
- query param
- request body

## 6.2 Lấy notification list

Endpoint:

```text
GET /api/v1/notifications
```

Query params:

- `page`: optional, integer, `>= 1`, default `1`
- `page_size`: optional, integer, `>= 1`, `<= 100`, default `20`

Ví dụ:

```http
GET /api/v1/notifications?page=1&page_size=20
```

Không có request body.

## 6.3 Mark một notification đã đọc

Endpoint:

```text
POST /api/v1/notifications/{notification_id}/read
```

Không có request body.

`notification_id` được gửi trên path param.

## 6.4 Mark tất cả notification đã đọc

Endpoint:

```text
POST /api/v1/notifications/read-all
```

Không có request body.

## 7. Response schema chung

## 7.1 Notification summary

Schema:

```ts
type NotificationSummary = {
  id: string;
  user_id: string;
  organization_id: string;
  type: string;
  title: string;
  body: string;
  target_type: string;
  target_id: string;
  link: string | null;
  actor_id: string | null;
  metadata: Record<string, unknown> | null;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}
```

Semantics:

- `created_at`: ISO datetime string
- `read_at`: có thể là `null`
- `link`: có thể là `null`
- `actor_id`: có thể là `null`
- `metadata`: có thể là `null`
- `user_id` và `organization_id` hiện tại được backend trả về trong summary

## 7.2 Unread count response

Schema:

```ts
type NotificationUnreadCountResponse = {
  unread_count: number;
}
```

## 7.3 Notification list response

Schema:

```ts
type NotificationListResponse = {
  items: NotificationSummary[];
  total: number;
  page: number;
  page_size: number;
}
```

Semantics:

- `items` luôn tồn tại
- `items` có thể là mảng rỗng
- `total` là tổng số notification trong current scope
- ordering hiện tại là newest-first theo `created_at desc`

## 7.4 Mark-one-read response

Schema:

```ts
type NotificationMarkReadResponse = {
  id: string;
  is_read: true;
  read_at: string;
}
```

Semantics:

- response thành công hiện tại luôn trả `is_read = true`
- `read_at` luôn non-null nếu request thành công
- nếu notification đã read từ trước, endpoint vẫn idempotent và vẫn trả read state hiện tại

## 7.5 Mark-all-read response

Schema:

```ts
type NotificationMarkAllReadResponse = {
  updated_count: number;
  marked_all_read: true;
  read_at: string;
}
```

Semantics:

- `updated_count` là số unread notification vừa được chuyển sang read trong current scope
- response thành công hiện tại luôn trả `marked_all_read = true`
- `read_at` là timestamp backend dùng cho lần mark-all đó

## 7.6 Socket event payload

Event:

```text
notification:created
```

Payload schema:

```ts
type NotificationCreatedSocketPayload = NotificationSummary
```

Semantics:

- payload socket hiện tại có cùng summary shape với item trong list API
- `organization_id` xuất hiện ở top-level payload
- payload đã được normalize thành JSON-safe primitives trước khi emit
- event được emit vào room `user:{user_id}`

Ví dụ:

```json
{
  "id": "6808a7b4c5d8d14d4af1d441",
  "user_id": "user-1",
  "organization_id": "org-1",
  "type": "stock_research_report_completed",
  "title": "FPT research report is ready",
  "body": "Open the FPT research report to review the completed analysis.",
  "target_type": "stock_research_report",
  "target_id": "6808a7b4c5d8d14d4af1d111",
  "link": "/stock-research/reports/6808a7b4c5d8d14d4af1d111",
  "metadata": {
    "symbol": "FPT",
    "report_status": "completed"
  },
  "is_read": false,
  "read_at": null,
  "created_at": "2026-04-23T09:15:30.123000Z"
}
```

## 8. Response schema của từng endpoint

## 8.1 `GET /api/v1/notifications/unread-count`

Status code thành công:

- `200 OK`

Response body ví dụ:

```json
{
  "unread_count": 3
}
```

## 8.2 `GET /api/v1/notifications`

Status code thành công:

- `200 OK`

Response body ví dụ:

```json
{
  "items": [
    {
      "id": "6808a7b4c5d8d14d4af1d441",
      "user_id": "user-1",
      "organization_id": "org-1",
      "type": "stock_research_report_completed",
      "title": "FPT research report is ready",
      "body": "Open the FPT research report to review the completed analysis.",
      "target_type": "stock_research_report",
      "target_id": "6808a7b4c5d8d14d4af1d111",
      "link": "/stock-research/reports/6808a7b4c5d8d14d4af1d111",
      "actor_id": null,
      "metadata": {
        "symbol": "FPT",
        "report_status": "completed"
      },
      "is_read": false,
      "read_at": null,
      "created_at": "2026-04-23T09:15:30.123000Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

## 8.3 `POST /api/v1/notifications/{notification_id}/read`

Status code thành công:

- `200 OK`

Response body ví dụ:

```json
{
  "id": "6808a7b4c5d8d14d4af1d441",
  "is_read": true,
  "read_at": "2026-04-23T09:20:10.100000Z"
}
```

## 8.4 `POST /api/v1/notifications/read-all`

Status code thành công:

- `200 OK`

Response body ví dụ:

```json
{
  "updated_count": 3,
  "marked_all_read": true,
  "read_at": "2026-04-23T09:22:00.500000Z"
}
```

## 9. Error response shape

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

## 10. Error semantics frontend cần hiểu

Có thể gặp các nhóm lỗi sau:

- `400 Bad Request`
  - thiếu `X-Organization-ID`
  - query param không hợp lệ, ví dụ `page < 1` hoặc `page_size > 100`
- `401 Unauthorized`
  - token không hợp lệ
  - account không active
- `403 Forbidden`
  - user không thuộc organization được gửi lên
  - notification tồn tại nhưng không thuộc current user/current organization khi mark read
- `404 Not Found`
  - organization không tồn tại hoặc không active
  - notification không tồn tại trong scope hợp lệ

## 11. Error detail hiện tại

Những `detail` message FE có thể nhận trong implementation hiện tại:

- `X-Organization-ID header is required`
- `Permission denied`
- `Organization not found`
- `Notification not found`
- `Notification does not belong to the current user`

Frontend không nên hardcode business logic dựa trên text message này. Nếu cần branch logic, nên ưu tiên dựa trên status code.

## 12. Những gì frontend không nên giả định

- không nên giả định frontend có endpoint tạo notification trong v1
- không nên giả định `link` luôn có giá trị
- không nên giả định `actor_id` luôn có giá trị
- không nên giả định `metadata` luôn có giá trị
- không nên giả định `read_at` luôn có giá trị trong list response
- không nên giả định mỗi notification type đều trỏ tới cùng 1 `target_type`
- không nên giả định socket event là nguồn dữ liệu duy nhất; REST API mới là nguồn state đầy đủ
- không nên giả định inbox list không có pagination; contract hiện tại dùng `page` và `page_size`

## 13. Tóm tắt contract

### Headers bắt buộc

- `Authorization: Bearer <token>`
- `X-Organization-ID: <organization_id>`

### Request chính trong v1

- list notifications:
  - `page`
  - `page_size`
- mark one read:
  - `notification_id` trên path
- mark all read:
  - không có body

### Response chính trong v1

- unread count:
  - `unread_count`
- list response:
  - `items`
  - `total`
  - `page`
  - `page_size`
- notification item:
  - `id`
  - `user_id`
  - `organization_id`
  - `type`
  - `title`
  - `body`
  - `target_type`
  - `target_id`
  - `link`
  - `actor_id`
  - `metadata`
  - `is_read`
  - `read_at`
  - `created_at`
- socket created event:
  - cùng shape với `NotificationSummary`
