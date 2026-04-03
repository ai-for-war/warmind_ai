# Tài Liệu Tích Hợp Frontend Cho Lead Agent Catalog API

## 1. Mục tiêu tài liệu

Tài liệu này mô tả backend hiện đang cung cấp gì cho endpoint lấy catalog cấu
hình runtime của `lead-agent`.

Phạm vi của tài liệu chỉ gồm:

- frontend cần truyền gì khi gọi API
- frontend nên dùng dữ liệu này như thế nào trong luồng sử dụng
- backend trả về gì
- ý nghĩa của các field trong response

Tài liệu này không hướng dẫn frontend cách code.

## 2. Endpoint

Backend hiện cung cấp endpoint:

```text
GET /api/v1/lead-agent/catalog
```

Mục đích của endpoint này là để frontend lấy danh sách:

- provider được backend support
- model được support theo từng provider
- reasoning option được support theo từng model
- giá trị mặc định backend đang chọn

Frontend nên xem đây là source of truth để build các lựa chọn runtime khi user
gửi message cho `lead-agent`.

## 3. Điều kiện để gọi API thành công

Request cần có:

- `Authorization: Bearer <token>`
- `X-Organization-ID: <organization_id>`

Endpoint này không nhận:

- path param
- query param
- request body

Nếu thiếu thông tin xác thực hoặc organization context không hợp lệ, backend sẽ
reject request.

## 4. Frontend cần truyền gì

Frontend chỉ cần gọi `GET` và truyền header xác thực như trên.

Ví dụ HTTP:

```http
GET /api/v1/lead-agent/catalog HTTP/1.1
Authorization: Bearer <token>
X-Organization-ID: <organization_id>
```

Không cần gửi thêm field nào khác.

## 5. Frontend nên dùng dữ liệu này khi nào

Frontend nên gọi endpoint này trước hoặc trong lúc khởi tạo màn hình có cho phép
user chọn runtime của `lead-agent`.

Dữ liệu từ catalog phù hợp cho các nhu cầu:

- hiển thị danh sách provider
- hiển thị danh sách model theo provider đã chọn
- hiển thị danh sách reasoning option theo model đã chọn
- prefill giá trị mặc định từ backend
- validate phía giao diện rằng chỉ cho user chọn các tổ hợp mà backend support

Semantics FE cần hiểu:

- không phải model nào cũng có `reasoning_options`
- nếu `reasoning_options` là mảng rỗng thì model đó không có lựa chọn reasoning
- `default_provider`, `default_model`, `default_reasoning` là giá trị mặc định backend đang expose
- `is_default` ở provider/model giúp FE đánh dấu lựa chọn mặc định trong từng cấp dữ liệu

## 6. Response backend trả về gì

Response thành công có shape:

```json
{
  "default_provider": "openai",
  "default_model": "gpt-5.2",
  "default_reasoning": "medium",
  "providers": [
    {
      "provider": "openai",
      "display_name": "OpenAI",
      "is_default": true,
      "models": [
        {
          "model": "gpt-5.2",
          "reasoning_options": ["low", "medium", "high"],
          "default_reasoning": "medium",
          "is_default": true
        },
        {
          "model": "gpt-4.1",
          "reasoning_options": [],
          "default_reasoning": null,
          "is_default": false
        }
      ]
    }
  ]
}
```

Lưu ý:

- nội dung thực tế của `providers` và `models` phụ thuộc cấu hình backend tại thời điểm gọi
- ví dụ trên chỉ minh họa shape response

## 7. Ý nghĩa từng field

### 7.1 Root response

- `default_provider`: provider mặc định backend chọn cho lead-agent
- `default_model`: model mặc định backend chọn
- `default_reasoning`: reasoning mặc định backend chọn; có thể là `null`
- `providers`: danh sách provider hiện đang available

### 7.2 Provider object

```json
{
  "provider": "openai",
  "display_name": "OpenAI",
  "is_default": true,
  "models": []
}
```

- `provider`: định danh ổn định để frontend gửi lại cho backend ở API gửi message
- `display_name`: nhãn hiển thị
- `is_default`: provider mặc định trong catalog hiện tại
- `models`: danh sách model thuộc provider này

### 7.3 Model object

```json
{
  "model": "gpt-5.2",
  "reasoning_options": ["low", "medium", "high"],
  "default_reasoning": "medium",
  "is_default": true
}
```

- `model`: định danh model để frontend gửi lại cho backend ở API gửi message
- `reasoning_options`: danh sách reasoning backend cho phép dùng với model này
- `default_reasoning`: reasoning mặc định của model; có thể là `null`
- `is_default`: model mặc định trong provider hiện tại

## 8. Semantics FE cần lưu ý

- FE không nên hardcode provider, model hoặc reasoning option.
- FE nên luôn lấy catalog từ backend trước khi cho user chọn runtime.
- FE chỉ nên gửi `reasoning` cho model có `reasoning_options`.
- Khi `default_reasoning = null`, frontend nên hiểu là backend không yêu cầu giá trị reasoning mặc định cho model đó.
- Thứ tự dữ liệu trong `providers` và `models` có thể được dùng làm thứ tự hiển thị nếu FE không có quy tắc riêng.

## 9. Quan hệ với API gửi message

Catalog này là dữ liệu đầu vào để frontend gọi endpoint gửi message của
`lead-agent`.

Các field FE sẽ map từ catalog sang request gửi message:

- `provider` lấy từ `providers[].provider`
- `model` lấy từ `providers[].models[].model`
- `reasoning` lấy từ `providers[].models[].reasoning_options[]` hoặc giá trị mặc định tương ứng

Frontend không nên tự tạo giá trị ngoài catalog khi gọi API gửi message.
