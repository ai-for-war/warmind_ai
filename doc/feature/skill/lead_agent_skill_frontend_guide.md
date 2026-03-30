# Tài Liệu Tích Hợp Frontend Cho Lead Agent Skill API

## 1. Mục tiêu tài liệu

Tài liệu này mô tả chính xác backend hiện đang cung cấp gì cho nhóm API skill
của `lead-agent`.

Trọng tâm của tài liệu là:

- frontend cần gửi gì lên backend
- backend trả về gì
- ý nghĩa của các field quan trọng
- semantics về scope, enablement, version, validation và pagination

Tài liệu này không hướng dẫn cách viết code frontend.

Guide này chỉ nói về HTTP API để quản lý skill do user tự tạo. Luồng chat
conversation của lead-agent là capability khác.

## 2. Nguồn sự thật

Nếu có khác biệt giữa tài liệu này và tài liệu cũ hơn trong repo, thứ tự ưu tiên là:

1. Code runtime backend
2. Tài liệu này

Các file chính cho capability này:

- `app/api/v1/ai/lead_agent.py`
- `app/services/ai/lead_agent_skill_service.py`
- `app/domain/schemas/lead_agent.py`
- `app/agents/implementations/lead_agent/tool_catalog.py`
- `app/common/exceptions/ai_exceptions.py`
- `app/main.py`

## 3. Backend đang cung cấp gì

Backend hiện cung cấp 8 endpoint HTTP dưới prefix:

```text
/api/v1/lead-agent
```

Nhóm endpoint này cho phép frontend:

- lấy danh sách tool selectable hiện đang available
- list skill của current user trong organization hiện tại
- tạo skill mới
- lấy detail một skill
- cập nhật skill
- xóa skill
- bật một skill trong organization hiện tại
- tắt một skill trong organization hiện tại

Capability này không cung cấp:

- bulk create/update/delete skill
- endpoint reorder skill
- endpoint duplicate skill
- endpoint publish/share skill cho user khác

## 4. Điều kiện để gọi API thành công

Mọi endpoint trong nhóm này đều yêu cầu:

- `Authorization: Bearer <token>`
- header `X-Organization-ID: <organization_id>`

Scope truy cập thực tế là:

- dữ liệu luôn bị giới hạn theo `current authenticated user`
- dữ liệu luôn bị giới hạn theo `organization` hiện tại từ header

Semantics authorization hiện tại:

- thiếu `Authorization` hoặc token không hợp lệ -> backend reject request
- thiếu `X-Organization-ID` hoặc organization không hợp lệ -> backend reject request
- skill nằm ngoài user scope hoặc ngoài organization scope -> backend trả như resource không tồn tại

## 5. Semantics chung mà frontend cần hiểu

### 5.1 `skill_id` do backend sinh, frontend không gửi khi create

Khi tạo skill, frontend chỉ gửi metadata của skill. Backend tự sinh `skill_id`
từ `name`.

Semantics hiện tại:

- `skill_id` là slug lowercase, URL-safe
- ký tự không hợp lệ bị loại bỏ
- nếu trùng trong cùng scope user + organization, backend tự thêm suffix như `-2`, `-3`
- frontend nên coi `skill_id` là durable identifier để gọi các endpoint detail/update/delete/enable/disable

Ví dụ:

- `Sales Research` có thể thành `sales-research`
- nếu đã tồn tại, backend có thể sinh `sales-research-2`

### 5.2 `is_enabled` là trạng thái theo organization hiện tại

`is_enabled` không phải metadata tĩnh của skill, mà là trạng thái enablement
theo scope:

- current user
- current organization

Điều này có nghĩa:

- cùng một skill khi đọc ở organization khác không được assume có cùng trạng thái enable
- sau khi create, skill mới luôn trả về `is_enabled: false`
- `enable` và `disable` chỉ đổi trạng thái enablement, không sửa nội dung skill

### 5.3 `version` do backend tự quản lý

Backend trả `version` trong mọi response skill.

Semantics hiện tại:

- khi create: `version = "1.0.0"`
- mỗi lần update thành công: backend tự tăng patch version
- frontend không gửi `version` trong request create/update

Ví dụ:

- create -> `1.0.0`
- update lần 1 -> `1.0.1`
- update lần 2 -> `1.0.2`

### 5.4 `allowed_tool_names` là danh sách tool selectable

`allowed_tool_names` là danh sách tool mà skill được phép sử dụng trong nhóm
tool selectable.

Semantics hiện tại:

- FE nên lấy source of truth từ `GET /api/v1/lead-agent/tools`
- backend sẽ trim value, loại bỏ phần tử rỗng và loại trùng, đồng thời giữ thứ tự đầu tiên
- nếu có tool name không nằm trong catalog hiện tại, backend trả `400`
- có thể gửi mảng rỗng `[]`

Frontend không nên hardcode danh sách tool selectable.

### 5.5 `allowed_tool_names` khi update: `null` khác `[]`

Với `PATCH /skills/{skill_id}`:

- không gửi field `allowed_tool_names` hoặc gửi `null` -> backend giữ nguyên giá trị cũ
- gửi `[]` -> backend clear toàn bộ tool selectable của skill
- gửi mảng có phần tử -> backend thay thế toàn bộ danh sách hiện tại bằng danh sách mới sau normalize

### 5.6 Pagination dùng envelope cố định

Backend trả list skill theo format:

```json
{
  "items": [],
  "total": 0,
  "skip": 0,
  "limit": 20
}
```

Ý nghĩa:

- `items`: slice hiện tại
- `total`: tổng số record match scope hiện tại trước khi cắt trang
- `skip`: offset FE đã gửi
- `limit`: limit FE đã gửi hoặc default backend áp vào

## 6. Shape dữ liệu chung

### 6.1 Tool object

```json
{
  "tool_name": "search",
  "display_name": "Web Search",
  "description": "Search the web with DuckDuckGo for current external information.",
  "category": "research"
}
```

Ý nghĩa:

- `tool_name`: identifier stable để FE gửi vào `allowed_tool_names`
- `display_name`: label hiển thị
- `description`: mô tả ngắn về tool
- `category`: nhóm tool để FE có thể group/filter nếu cần

### 6.2 Skill object

```json
{
  "skill_id": "sales-research",
  "name": "Sales Research",
  "description": "Research external market context for sales questions.",
  "activation_prompt": "When the user asks about market context, gather current external information first.",
  "allowed_tool_names": [
    "search",
    "fetch_content"
  ],
  "version": "1.0.1",
  "is_enabled": true,
  "created_at": "2026-03-30T02:10:00Z",
  "updated_at": "2026-03-30T03:05:00Z"
}
```

Ý nghĩa:

- `skill_id`: id do backend sinh, dùng cho mọi endpoint theo path param
- `name`: tên hiển thị của skill
- `description`: mô tả ngắn cho người dùng
- `activation_prompt`: prompt đầy đủ mà backend lưu cho skill
- `allowed_tool_names`: danh sách tool selectable mà skill được phép dùng
- `version`: semantic version do backend quản lý
- `is_enabled`: trạng thái enablement trong organization hiện tại
- `created_at`: thời điểm tạo
- `updated_at`: thời điểm cập nhật gần nhất

## 7. `GET /api/v1/lead-agent/tools`

## 7.1 Mục đích

Trả về catalog các tool selectable hiện đang available ở runtime.

## 7.2 FE cần gửi gì

Header:

```http
Authorization: Bearer <token>
X-Organization-ID: org_123
```

Không có query param và không có request body.

## 7.3 Backend trả gì

```json
{
  "items": [
    {
      "tool_name": "search",
      "display_name": "Web Search",
      "description": "Search the web with DuckDuckGo for current external information.",
      "category": "research"
    },
    {
      "tool_name": "fetch_content",
      "display_name": "Fetch Web Content",
      "description": "Fetch and extract content from a specific web page URL.",
      "category": "research"
    }
  ]
}
```

## 7.4 Điều FE nên assume

- response chỉ chứa tool currently available ở runtime
- danh sách này có thể thay đổi theo môi trường hoặc runtime capability
- `tool_name` là giá trị duy nhất FE được dùng để gửi lên `allowed_tool_names`

## 8. `GET /api/v1/lead-agent/skills`

## 8.1 Mục đích

List các skill do current user sở hữu trong organization hiện tại.

## 8.2 FE cần gửi gì

Header:

```http
Authorization: Bearer <token>
X-Organization-ID: org_123
```

Query params:

- `skip`: optional, integer, mặc định `0`, tối thiểu `0`
- `limit`: optional, integer, mặc định `20`, tối thiểu `1`, tối đa `100`

Ví dụ:

```http
GET /api/v1/lead-agent/skills?skip=0&limit=20
```

## 8.3 Backend trả gì

```json
{
  "items": [
    {
      "skill_id": "sales-research",
      "name": "Sales Research",
      "description": "Research external market context for sales questions.",
      "activation_prompt": "When the user asks about market context, gather current external information first.",
      "allowed_tool_names": [
        "search"
      ],
      "version": "1.0.0",
      "is_enabled": false,
      "created_at": "2026-03-30T02:10:00Z",
      "updated_at": "2026-03-30T02:10:00Z"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 20
}
```

## 8.4 Điều FE nên assume

- chỉ list skill của current user trong organization hiện tại
- `is_enabled` đã phản ánh trạng thái enablement của từng skill trong organization hiện tại
- hiện tại không có server-side search/filter/sort param cho skill list

## 9. `POST /api/v1/lead-agent/skills`

## 9.1 Mục đích

Tạo một skill mới thuộc current user trong organization hiện tại.

## 9.2 FE cần gửi gì

Header:

```http
Authorization: Bearer <token>
X-Organization-ID: org_123
Content-Type: application/json
```

Request body:

```json
{
  "name": "Sales Research",
  "description": "Research external market context for sales questions.",
  "activation_prompt": "When the user asks about market context, gather current external information first.",
  "allowed_tool_names": [
    "search",
    "fetch_content"
  ]
}
```

Field rules:

- `name`: bắt buộc, string, độ dài `1..200`
- `description`: bắt buộc, string, độ dài `1..2000`
- `activation_prompt`: bắt buộc, string, độ dài `1..20000`
- `allowed_tool_names`: optional, array string, nếu không gửi thì backend dùng `[]`

## 9.3 Backend trả gì

Status code:

- `201 Created`

Response body:

```json
{
  "skill_id": "sales-research",
  "name": "Sales Research",
  "description": "Research external market context for sales questions.",
  "activation_prompt": "When the user asks about market context, gather current external information first.",
  "allowed_tool_names": [
    "search",
    "fetch_content"
  ],
  "version": "1.0.0",
  "is_enabled": false,
  "created_at": "2026-03-30T02:10:00Z",
  "updated_at": "2026-03-30T02:10:00Z"
}
```

## 9.4 Điều FE nên assume

- không thể tự chỉ định `skill_id`
- ngay sau khi create, skill chưa được enable
- nếu `allowed_tool_names` có giá trị không hợp lệ, request fail toàn bộ

## 10. `GET /api/v1/lead-agent/skills/{skill_id}`

## 10.1 Mục đích

Lấy detail của một skill thuộc current user trong organization hiện tại.

## 10.2 FE cần gửi gì

Header:

```http
Authorization: Bearer <token>
X-Organization-ID: org_123
```

Path param:

- `skill_id`: bắt buộc, string, chính là `skill_id` backend đã trả trước đó

Ví dụ:

```http
GET /api/v1/lead-agent/skills/sales-research
```

## 10.3 Backend trả gì

Response body là một `Skill object`.

Ví dụ:

```json
{
  "skill_id": "sales-research",
  "name": "Sales Research",
  "description": "Research external market context for sales questions.",
  "activation_prompt": "When the user asks about market context, gather current external information first.",
  "allowed_tool_names": [
    "search"
  ],
  "version": "1.0.1",
  "is_enabled": true,
  "created_at": "2026-03-30T02:10:00Z",
  "updated_at": "2026-03-30T03:05:00Z"
}
```

## 11. `PATCH /api/v1/lead-agent/skills/{skill_id}`

## 11.1 Mục đích

Cập nhật một skill thuộc current user trong organization hiện tại.

## 11.2 FE cần gửi gì

Header:

```http
Authorization: Bearer <token>
X-Organization-ID: org_123
Content-Type: application/json
```

Path param:

- `skill_id`: bắt buộc

Request body là partial update. Có thể gửi 1 hoặc nhiều field:

```json
{
  "name": "Sales Research Pro",
  "description": "Research external market context and summarize findings.",
  "activation_prompt": "When the user asks about market context, gather current external information first and summarize it clearly.",
  "allowed_tool_names": [
    "search"
  ]
}
```

Field rules:

- `name`: optional, nếu gửi thì string, độ dài `1..200`
- `description`: optional, nếu gửi thì string, độ dài `1..2000`
- `activation_prompt`: optional, nếu gửi thì string, độ dài `1..20000`
- `allowed_tool_names`: optional

Semantics quan trọng:

- phải có ít nhất 1 field thực sự được gửi để update
- field không gửi hoặc gửi `null` sẽ không thay đổi giá trị cũ
- riêng `allowed_tool_names: []` nghĩa là clear toàn bộ tool

## 11.3 Backend trả gì

Response body là `Skill object` sau khi update.

Ví dụ:

```json
{
  "skill_id": "sales-research",
  "name": "Sales Research Pro",
  "description": "Research external market context and summarize findings.",
  "activation_prompt": "When the user asks about market context, gather current external information first and summarize it clearly.",
  "allowed_tool_names": [
    "search"
  ],
  "version": "1.0.1",
  "is_enabled": true,
  "created_at": "2026-03-30T02:10:00Z",
  "updated_at": "2026-03-30T03:05:00Z"
}
```

## 12. `DELETE /api/v1/lead-agent/skills/{skill_id}`

## 12.1 Mục đích

Xóa một skill thuộc current user trong organization hiện tại.

## 12.2 FE cần gửi gì

Header:

```http
Authorization: Bearer <token>
X-Organization-ID: org_123
```

Path param:

- `skill_id`: bắt buộc

Ví dụ:

```http
DELETE /api/v1/lead-agent/skills/sales-research
```

## 12.3 Backend trả gì

Status code:

- `204 No Content`

Không có response body.

## 12.4 Điều FE nên assume

- nếu skill đang enabled, backend sẽ tự remove skill đó khỏi danh sách enabled
- sau khi delete thành công, `skill_id` đó không còn dùng được nữa trong scope hiện tại

## 13. `PUT /api/v1/lead-agent/skills/{skill_id}/enabled`

## 13.1 Mục đích

Bật một skill trong organization hiện tại.

## 13.2 FE cần gửi gì

Header:

```http
Authorization: Bearer <token>
X-Organization-ID: org_123
```

Path param:

- `skill_id`: bắt buộc

Không có request body.

Ví dụ:

```http
PUT /api/v1/lead-agent/skills/sales-research/enabled
```

## 13.3 Backend trả gì

```json
{
  "skill_id": "sales-research",
  "is_enabled": true
}
```

## 13.4 Điều FE nên assume

- endpoint này idempotent theo hướng enable
- gọi enable nhiều lần vẫn trả `is_enabled: true`

## 14. `DELETE /api/v1/lead-agent/skills/{skill_id}/enabled`

## 14.1 Mục đích

Tắt một skill trong organization hiện tại.

## 14.2 FE cần gửi gì

Header:

```http
Authorization: Bearer <token>
X-Organization-ID: org_123
```

Path param:

- `skill_id`: bắt buộc

Không có request body.

Ví dụ:

```http
DELETE /api/v1/lead-agent/skills/sales-research/enabled
```

## 14.3 Backend trả gì

```json
{
  "skill_id": "sales-research",
  "is_enabled": false
}
```

## 14.4 Điều FE nên assume

- endpoint này idempotent theo hướng disable
- gọi disable nhiều lần vẫn trả `is_enabled: false`

## 15. Error contract FE cần xử lý

### 15.1 Format lỗi application-level

Các lỗi từ `AppException` hiện được backend trả theo format:

```json
{
  "detail": "Error message"
}
```

Frontend nên đọc thông điệp lỗi từ field `detail`.

### 15.2 Các case lỗi quan trọng của nhóm endpoint này

- `400 Bad Request`
  - `allowed_tool_names` chứa tool không hợp lệ
  - `PATCH` không gửi field nào để update
  - `skill_id` path param rỗng sau normalize
- `401 Unauthorized`
  - thiếu token hoặc token không hợp lệ
- `404 Not Found`
  - skill không tồn tại trong scope user + organization hiện tại
- `422 Unprocessable Entity`
  - body sai schema hoặc vi phạm ràng buộc độ dài/type của Pydantic

Ví dụ `400` khi tool không hợp lệ:

```json
{
  "detail": "Unknown or unavailable lead-agent tools: invalid_tool"
}
```

Ví dụ `400` khi update không có field:

```json
{
  "detail": "At least one skill field must be provided for update"
}
```

Ví dụ `404`:

```json
{
  "detail": "Lead-agent skill not found"
}
```

### 15.3 Validation rules để FE align trước khi gửi

- `name`: `1..200`
- `description`: `1..2000`
- `activation_prompt`: `1..20000`
- `skip >= 0`
- `limit` trong `1..100`

Ngoài ra, do schema dùng `str_strip_whitespace=True`, backend sẽ tự trim khoảng
trắng đầu/cuối cho các string field.

## 16. Tóm tắt contract FE nên dùng

1. Luôn gọi `GET /api/v1/lead-agent/tools` để lấy catalog tool selectable hiện tại.
2. Khi create skill, FE chỉ gửi `name`, `description`, `activation_prompt`, `allowed_tool_names`.
3. Dùng `skill_id` do backend trả về cho mọi thao tác tiếp theo.
4. Dùng `is_enabled` từ response như nguồn sự thật cho trạng thái enable trong organization hiện tại.
5. Với update, chỉ gửi field thực sự muốn đổi; nếu muốn clear tool thì gửi `allowed_tool_names: []`.
