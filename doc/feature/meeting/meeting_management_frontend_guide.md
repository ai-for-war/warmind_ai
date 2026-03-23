# Tài Liệu Tích Hợp Frontend Cho Meeting Management API

## 1. Mục tiêu tài liệu

Tài liệu này mô tả chính xác backend hiện đang cung cấp gì cho nhóm API
`meeting management`.

Trọng tâm của tài liệu là:

- frontend cần gửi gì lên backend
- backend trả về gì
- ý nghĩa của từng field quan trọng
- semantics về scope, ownership, archive, pagination và ordering

Tài liệu này không hướng dẫn cách viết code frontend.

Guide này chỉ nói về HTTP API cho dữ liệu meeting đã được persist. Luồng realtime
meeting transcription và AI note runtime vẫn được mô tả ở:

- `doc/feature/meeting/frontend_integration_guide.md`

## 2. Nguồn sự thật

Nếu có khác biệt giữa tài liệu này và tài liệu cũ hơn trong repo, thứ tự ưu tiên là:

1. Code runtime backend
2. OpenSpec hiện tại
3. Tài liệu này

Các file chính cho capability này:

- `app/api/v1/meetings/router.py`
- `app/services/meeting/meeting_management_service.py`
- `app/domain/schemas/meeting.py`
- `app/repo/meeting_repo.py`
- `app/repo/meeting_utterance_repo.py`
- `app/repo/meeting_note_chunk_repo.py`
- `openspec/specs/meeting-management/spec.md`

## 3. Backend đang cung cấp gì

Backend hiện cung cấp 4 endpoint HTTP dưới prefix:

```text
/api/v1/meetings
```

Capability này cho phép frontend:

- list các meeting do chính current user tạo trong organization hiện tại
- filter theo archive scope, lifecycle status, thời gian bắt đầu và title search
- update `title`, `source`, trạng thái archive của một meeting
- đọc lại canonical utterances đã persist của một meeting
- đọc lại raw note chunks đã persist của một meeting

Capability này không cung cấp:

- endpoint `GET /meetings/{meeting_id}` cho detail summary riêng
- delete meeting
- organization-wide meeting browsing
- merged note snapshot do backend dựng sẵn

## 4. Điều kiện để gọi API thành công

Mọi endpoint trong nhóm này đều yêu cầu:

- `Authorization: Bearer <token>`
- header `X-Organization-ID: <organization_id>`

Scope truy cập thực tế là:

- chỉ meeting có `organization_id` đúng với header
- chỉ meeting có `created_by` đúng với current authenticated user

Semantics authorization hiện tại:

- thiếu `X-Organization-ID` -> backend reject request
- user không có active membership trong organization đó -> backend reject request
- meeting nằm ngoài creator scope hoặc organization scope -> backend trả như resource không tồn tại

## 5. Semantics chung mà frontend cần hiểu

### 5.1 `status` và `archived` là hai khái niệm khác nhau

`status` là lifecycle của meeting realtime:

- `streaming`
- `finalizing`
- `completed`
- `interrupted`
- `failed`

`archived` không nằm trong field riêng, mà được suy ra từ:

- `archived_at != null` -> meeting đang archived
- `archived_at == null` -> meeting đang active

Điều này có nghĩa:

- một meeting có thể `completed` và đồng thời `archived`
- archive không làm thay đổi lifecycle status

### 5.2 Mọi list endpoint đều dùng pagination envelope chung

Backend trả list theo format:

```json
{
  "items": [],
  "total": 0,
  "skip": 0,
  "limit": 20,
  "has_more": false
}
```

Ý nghĩa:

- `items`: slice hiện tại
- `total`: tổng số record match filter trước khi cắt trang
- `skip`: offset FE đã gửi
- `limit`: limit FE đã gửi hoặc default backend áp vào
- `has_more`: còn trang tiếp theo hay không

### 5.3 Ordering mặc định là deterministic

Backend cố định ordering như sau:

- meeting list: `started_at desc`, sau đó `id desc`
- utterances: `sequence asc`
- note chunks: `from_sequence asc`, sau đó `to_sequence asc`

Frontend không cần gửi sort param ở phase hiện tại.

## 6. `GET /api/v1/meetings`

## 6.1 Mục đích

List các meeting do current user tạo trong organization hiện tại.

## 6.2 FE cần gửi gì

Header bắt buộc:

```http
Authorization: Bearer <token>
X-Organization-ID: org_123
```

Query params hỗ trợ:

- `skip`: optional, integer, mặc định `0`
- `limit`: optional, integer, mặc định `20`, tối đa `100`
- `scope`: optional, một trong `active | archived | all`, mặc định `active`
- `status`: optional, một trong `streaming | finalizing | completed | interrupted | failed`
- `started_at_from`: optional, ISO datetime
- `started_at_to`: optional, ISO datetime
- `q`: optional, title search, trim khoảng trắng; nếu rỗng thì coi như không filter

Ví dụ:

```http
GET /api/v1/meetings?scope=all&status=completed&skip=0&limit=20&q=weekly
```

## 6.3 Backend trả gì

Response:

```json
{
  "items": [
    {
      "id": "meeting_001",
      "title": "Weekly product sync",
      "source": "google_meet",
      "status": "completed",
      "started_at": "2026-03-23T08:00:00Z",
      "ended_at": "2026-03-23T09:00:00Z",
      "archived_at": null,
      "archived_by": null
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 20,
  "has_more": false
}
```

Ý nghĩa từng field của `items[]`:

- `id`: durable meeting id
- `title`: title hiện tại, có thể là `null`
- `source`: metadata nguồn meeting, backend normalize lowercase
- `status`: lifecycle status của meeting
- `started_at`: thời điểm bắt đầu meeting đã persist
- `ended_at`: thời điểm kết thúc nếu đã terminal, có thể là `null`
- `archived_at`: thời điểm archive, `null` nếu chưa archive
- `archived_by`: user id đã archive meeting, `null` nếu chưa archive

## 6.4 Điều FE nên assume

- nếu không gửi `scope`, backend chỉ trả meeting chưa archived
- list này luôn chỉ chứa meeting của current user
- search `q` là match title không phân biệt hoa thường

## 7. `PATCH /api/v1/meetings/{meeting_id}`

## 7.1 Mục đích

Update metadata của một meeting thuộc quyền sở hữu của current user.

## 7.2 FE cần gửi gì

Header:

```http
Authorization: Bearer <token>
X-Organization-ID: org_123
```

Path param:

- `meeting_id`: id của meeting cần update

Body hỗ trợ các field:

- `title`: optional, string không rỗng
- `source`: optional, string không rỗng
- `archived`: optional, boolean

Yêu cầu quan trọng:

- phải có ít nhất một field trong `title`, `source`, `archived`
- field đã gửi lên không được là `null`

Ví dụ rename và archive:

```json
{
  "title": "Weekly sync - Q2",
  "archived": true
}
```

Ví dụ restore:

```json
{
  "archived": false
}
```

## 7.3 Backend trả gì

Response:

```json
{
  "meeting": {
    "id": "meeting_001",
    "title": "Weekly sync - Q2",
    "source": "google_meet",
    "status": "completed",
    "started_at": "2026-03-23T08:00:00Z",
    "ended_at": "2026-03-23T09:00:00Z",
    "archived_at": "2026-03-23T10:30:00Z",
    "archived_by": "user_123"
  }
}
```

Semantics:

- `archived=true` -> backend set archive metadata
- `archived=false` -> backend clear archive metadata
- `source` được normalize lowercase trước khi persist
- response luôn trả summary mới nhất sau update

## 8. `GET /api/v1/meetings/{meeting_id}/utterances`

## 8.1 Mục đích

Đọc lại canonical utterances đã được persist cho một meeting thuộc scope của
current user.

## 8.2 FE cần gửi gì

Header:

```http
Authorization: Bearer <token>
X-Organization-ID: org_123
```

Query params:

- `skip`: optional, mặc định `0`
- `limit`: optional, mặc định `20`, tối đa `100`

## 8.3 Backend trả gì

Response:

```json
{
  "items": [
    {
      "id": "utterance_001",
      "meeting_id": "meeting_001",
      "sequence": 1,
      "messages": [
        {
          "speaker_index": 0,
          "speaker_label": "speaker_1",
          "text": "Let's review the timeline."
        },
        {
          "speaker_index": 1,
          "speaker_label": "speaker_2",
          "text": "We can ship next Friday."
        }
      ],
      "created_at": "2026-03-23T08:05:00Z"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 20,
  "has_more": false
}
```

Semantics:

- `sequence` là ordering key authoritative trong một meeting
- `messages[]` là canonical speaker-grouped transcript đã persist
- đây là persisted history, không phải realtime `meeting:final`
- `speaker_label` hiện chỉ là label dạng `speaker_<n>`, không phải participant identity thật

## 9. `GET /api/v1/meetings/{meeting_id}/note-chunks`

## 9.1 Mục đích

Đọc lại raw persisted note chunks của một meeting thuộc scope của current user.

## 9.2 FE cần gửi gì

Header:

```http
Authorization: Bearer <token>
X-Organization-ID: org_123
```

Query params:

- `skip`: optional, mặc định `0`
- `limit`: optional, mặc định `20`, tối đa `100`

## 9.3 Backend trả gì

Response:

```json
{
  "items": [
    {
      "id": "chunk_001",
      "meeting_id": "meeting_001",
      "from_sequence": 1,
      "to_sequence": 7,
      "key_points": [
        "Team agreed to ship the beta next Friday."
      ],
      "decisions": [
        "Scope of the beta release remains unchanged."
      ],
      "action_items": [
        {
          "text": "Prepare the beta release checklist",
          "owner_text": "Minh",
          "due_text": "next Thursday"
        }
      ],
      "created_at": "2026-03-23T08:15:00Z"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 20,
  "has_more": false
}
```

Semantics:

- đây là raw additive note chunks đúng như backend persist
- backend không merge các chunk thành một snapshot tổng
- `from_sequence` và `to_sequence` là range authoritative của chunk
- FE muốn render combined note view thì phải tự merge hoặc tự build view logic ở phía client

## 10. Error semantics mà FE nên expect

### 10.1 `400 Bad Request`

Thường xảy ra khi:

- thiếu header `X-Organization-ID`
- `started_at_from > started_at_to`
- PATCH body không có field hợp lệ để update
- `title` hoặc `source` là chuỗi rỗng

### 10.2 `401 Unauthorized`

Thường xảy ra khi:

- token không hợp lệ
- user account không active

### 10.3 `403 Forbidden`

Thường xảy ra khi:

- current user không có active membership trong organization từ header

### 10.4 `404 Not Found`

Đối với endpoint có `meeting_id`, backend dùng `404` cho cả hai trường hợp:

- meeting id không tồn tại
- meeting tồn tại nhưng nằm ngoài creator scope hoặc organization scope của current user

Frontend nên coi đây là “meeting không khả dụng trong scope hiện tại”.

### 10.5 `422 Unprocessable Entity`

Có thể xảy ra ở tầng FastAPI/Pydantic khi:

- query param sai kiểu
- body field sai kiểu
- enum value không hợp lệ

## 11. Những gì frontend nên giữ nguyên về mặt semantics

- `meeting_id` là durable identity của meeting history
- list history và subresources đều chỉ phản ánh dữ liệu đã persist
- `status` không nói meeting có archived hay không
- `archived_at` mới là tín hiệu authoritative để biết meeting đang archived
- note chunks là additive raw chunks, không phải merged final note
- utterances được trả theo transcript canonical đã đóng sequence

## 12. Những gì backend chưa cung cấp trong capability này

- `GET /api/v1/meetings/{meeting_id}` cho detail summary riêng
- endpoint xóa meeting
- endpoint merged note snapshot
- organization-wide meeting visibility
- server-side participant identity mapping cho `speaker_1`, `speaker_2`

## 13. Tóm tắt ngắn

Frontend chỉ cần nắm 5 ý chính:

1. Mọi request đều cần `Authorization` và `X-Organization-ID`.
2. Mọi dữ liệu đều bị giới hạn theo current user và organization hiện tại.
3. Meeting list mặc định chỉ trả active meetings, có pagination envelope chung.
4. `status` là lifecycle, còn archive được suy ra từ `archived_at`.
5. Utterances là canonical transcript đã persist; note chunks là raw additive note chunks, không phải merged note.
