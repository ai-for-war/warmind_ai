# Tài Liệu Tích Hợp Frontend Cho AI Meeting Summary

## 1. Mục tiêu tài liệu

Tài liệu này mô tả chính xác backend hiện đang cung cấp gì cho tính năng
`AI meeting summary`.

Trong code hiện tại, tên implementation đúng hơn là:

- `live meeting transcription`
- `incremental AI meeting notes`

Tức là backend không tạo một bản summary cuối duy nhất ngay khi meeting kết
thúc. Thay vào đó, backend:

- stream transcript realtime cho meeting
- đóng các utterance canonical theo sequence
- xử lý note AI ở background
- emit note chunks tăng dần trong lúc meeting đang chạy hoặc ngay sau khi
  meeting đã kết thúc

Tài liệu này chỉ tập trung vào:

- flow runtime
- socket events
- payload contract
- timing và ordering semantics
- những dữ liệu frontend có thể kỳ vọng nhận được
- những gì backend chưa cung cấp

Tài liệu này không hướng dẫn cách viết code frontend.

## 2. Nguồn sự thật

Nếu có khác biệt giữa tài liệu này và tài liệu cũ hơn trong repo, thứ tự ưu
tiên là:

1. Code runtime backend
2. OpenSpec hiện tại
3. Tài liệu này

Các file chính cho feature:

- `app/socket_gateway/server.py`
- `app/common/event_socket.py`
- `app/domain/schemas/meeting.py`
- `app/services/meeting/meeting_service.py`
- `app/services/meeting/session.py`
- `app/services/meeting/session_manager.py`
- `app/services/meeting/note_state_store.py`
- `app/services/meeting/note_processing_service.py`
- `app/services/meeting/note_generation_service.py`
- `app/workers/meeting_note_worker.py`
- `app/common/service.py`

Spec liên quan:

- `openspec/specs/live-meeting-transcription/spec.md`
- `openspec/specs/meeting-incremental-ai-notes/spec.md`

## 3. Backend đang làm gì

Feature hiện tại có 2 lớp hành vi nối tiếp nhau:

### 3.1 Live meeting transcription

Frontend gửi audio meeting realtime qua Socket.IO.

Backend:

- tạo một `meeting` record durable
- mở Deepgram live transcription cho audio mono
- emit `meeting:final` cho các final transcript fragment
- emit `meeting:utterance_closed` khi một utterance canonical được đóng

### 3.2 Incremental AI meeting notes

Mỗi `meeting:utterance_closed` sẽ được đưa vào queue background.

Worker:

- persist utterance vào MongoDB
- stage utterance chưa summarize vào Redis
- chỉ summarize khi có đủ `7` utterance liên tiếp, hoặc khi meeting đã
  `completed` / `interrupted` và cần flush phần tail còn lại
- persist note chunk
- emit `meeting:note:created`

## 4. Tổng quan flow end-to-end

```text
Browser meeting audio capture
  -> Socket.IO authenticated connection
  -> meeting:start
  -> meeting:audio(metadata, binary PCM16)
  -> Backend MeetingSession
  -> Deepgram live transcription
  -> meeting:final
  -> meeting:utterance_closed
  -> Redis queue: meeting_note_tasks
  -> Meeting note worker
  -> MongoDB persist utterance
  -> Redis hot state for pending note input
  -> LLM summarize contiguous batch
  -> MongoDB persist meeting_note_chunk
  -> meeting:note:created
```

## 5. Điều kiện tiên quyết để frontend support được feature

Frontend chỉ có thể dùng flow này khi đáp ứng đủ các điều kiện sau:

- Socket.IO connection đã authenticate thành công.
- User có active membership trong `organization_id` được gửi lên khi start
  meeting.
- Audio gửi lên đúng contract `PCM16`, `16kHz`, `1-channel`.
- Mỗi socket chỉ có tối đa 1 meeting session active cùng lúc.
- Socket gửi audio/control phải là chính socket đã tạo meeting session đó.

Ngoài ra, session live của meeting là process-local. Nếu hệ thống scale ngang,
traffic Socket.IO inbound cần sticky session để toàn bộ audio/control của một
meeting luôn đi vào cùng app instance đang giữ `MeetingSession`.

## 6. Delivery model mà frontend cần hiểu

### 6.1 Event không phát theo meeting room

Backend không emit theo room riêng cho từng meeting.

Outbound events được gửi theo user room:

- room dạng `user:{user_id}`

Điều đó có nghĩa:

- cùng một user có thể nhận event ở nhiều tab/socket khác nhau
- frontend không nên chỉ dựa vào "đang mở socket nào"
- frontend phải lọc event theo `organization_id`, `meeting_id`, `stream_id`

### 6.2 `organization_id` được thêm ở top-level payload

Socket payload outbound được enrich thêm `organization_id` ở top-level.

Điều này áp dụng cả cho:

- live transcript events
- worker-emitted note events

Frontend nên coi `organization_id` là field chuẩn để filter theo context hiện
tại.

### 6.3 Chỉ user tạo meeting mới nhận note chunks

`meeting:note:created` chỉ được emit cho user đã tạo meeting.

Backend hiện không broadcast note chunks cho cả organization.

## 7. Audio contract

Meeting phase hiện tại khóa cứng audio như sau:

- `encoding = "linear16"`
- `sample_rate = 16000`
- `channels = 1`
- payload audio là raw PCM16 binary

Backend không nhận:

- partial transcript do frontend gửi
- audio URL
- uploaded audio file
- multi-channel meeting audio

## 8. Inbound Socket Events Từ Frontend

## 8.1 `meeting:start`

Dùng để tạo live meeting session mới.

Payload:

```json
{
  "organization_id": "org_123",
  "stream_id": "meeting_stream_001",
  "title": "Weekly product sync",
  "language": "en",
  "encoding": "linear16",
  "sample_rate": 16000,
  "channels": 1
}
```

Field:

- `organization_id`: bắt buộc
- `stream_id`: bắt buộc, FE tự tạo
- `title`: optional
- `language`: optional, backend normalize lowercase, mặc định `en`
- `encoding`: phải là `"linear16"`
- `sample_rate`: phải là `16000`
- `channels`: phải là `1`

Lưu ý về `source`:

- frontend không cần coi đây là field quan trọng của flow
- đây chỉ là metadata tùy chọn, backend không rẽ nhánh xử lý theo field này
- nếu có gửi, backend chỉ normalize và persist lại vào meeting record
- nếu không gửi, backend vẫn dùng default `google_meet`

Nếu hợp lệ, backend tạo durable meeting record rồi emit `meeting:started`.

## 8.2 `meeting:audio`

Event này có 2 phần:

1. metadata payload
2. binary audio payload

Metadata:

```json
{
  "stream_id": "meeting_stream_001",
  "encoding": "linear16",
  "sample_rate": 16000,
  "channels": 1,
  "sequence": 42,
  "timestamp_ms": 1760000000000
}
```

Binary payload:

- raw PCM16 bytes
- không phải base64 string

Field:

- `stream_id`: bắt buộc
- `encoding`: phải là `"linear16"`
- `sample_rate`: phải là `16000`
- `channels`: phải là `1`
- `sequence`: số frame phía client, backend chưa dùng để reorder nhưng vẫn nhận
  như metadata
- `timestamp_ms`: optional

## 8.3 `meeting:finalize`

Payload:

```json
{
  "stream_id": "meeting_stream_001"
}
```

Ý nghĩa:

- yêu cầu backend finalize provider-side stream
- flush transcript còn pending
- để meeting đi vào đường kết thúc sạch

Đây là đường kết thúc chuẩn khi user chủ động end meeting bình thường.

## 8.4 `meeting:stop`

Payload:

```json
{
  "stream_id": "meeting_stream_001"
}
```

Trong implementation hiện tại, `stop` đi cùng clean flush path tương tự
`finalize`.

Về mặt contract FE có thể xem:

- `finalize` = kết thúc bình thường
- `stop` = kết thúc chủ động cùng clean shutdown path

## 9. Outbound Socket Events Từ Backend

## 9.1 `meeting:started`

Emit khi session được tạo thành công.

Payload mẫu:

```json
{
  "stream_id": "meeting_stream_001",
  "meeting_id": "meeting_abc123",
  "language": "en",
  "encoding": "linear16",
  "sample_rate": 16000,
  "channels": 1,
  "status": "streaming",
  "organization_id": "org_123"
}
```

Frontend có thể dùng event này để bind `stream_id -> meeting_id`.

## 9.2 `meeting:final`

Emit cho từng final transcript fragment realtime.

Payload mẫu:

```json
{
  "stream_id": "meeting_stream_001",
  "meeting_id": "meeting_abc123",
  "utterance_id": "utt_001",
  "messages": [
    {
      "speaker_index": 0,
      "speaker_label": "speaker_1",
      "text": "Let's review the timeline."
    }
  ],
  "is_final": true,
  "organization_id": "org_123"
}
```

Semantics quan trọng:

- đây là fragment final realtime
- đây chưa phải durable canonical utterance cuối cùng
- một `utterance_id` có thể nhận nhiều `meeting:final` trước khi utterance đó
  đóng
- backend không emit partial transcript cho meetings

## 9.3 `meeting:utterance_closed`

Emit khi backend coi một utterance là canonical và đã đóng sequence.

Payload mẫu:

```json
{
  "stream_id": "meeting_stream_001",
  "meeting_id": "meeting_abc123",
  "utterance_id": "utt_001",
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
  "created_at": "2026-03-22T12:00:05.000000Z",
  "organization_id": "org_123"
}
```

Semantics:

- `sequence` là ordering key chính trong một meeting
- `messages[]` là bản canonical theo speaker grouping
- event này là đầu vào của background note pipeline
- event này có thể đến sau nhiều `meeting:final` cùng `utterance_id`

## 9.4 `meeting:note:created`

Emit từ worker khi một note chunk mới được tạo thành công.

Payload mẫu:

```json
{
  "id": "note_chunk_001",
  "meeting_id": "meeting_abc123",
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
  "created_at": "2026-03-22T12:01:20.000000Z",
  "organization_id": "org_123"
}
```

Semantics:

- đây là event additive
- backend chỉ emit chunk mới tạo, không emit merged snapshot
- FE phải tự merge note timeline phía client nếu muốn render aggregate view
- range authoritative của chunk là `from_sequence -> to_sequence`

## 9.5 `meeting:completed`

Emit khi meeting kết thúc cleanly.

Payload mẫu:

```json
{
  "stream_id": "meeting_stream_001",
  "meeting_id": "meeting_abc123",
  "status": "completed",
  "organization_id": "org_123"
}
```

Semantics:

- live session đã hoàn tất ở realtime path
- event này không đảm bảo background note worker đã drain xong toàn bộ tail

## 9.6 `meeting:interrupted`

Emit khi socket disconnect trong lúc meeting còn active và backend kết thúc
meeting ở trạng thái interrupted.

Payload mẫu:

```json
{
  "stream_id": "meeting_stream_001",
  "meeting_id": "meeting_abc123",
  "status": "interrupted",
  "organization_id": "org_123"
}
```

Semantics:

- disconnect được xem là terminal state của meeting
- background note pipeline vẫn có thể tiếp tục chạy sau event này

## 9.7 `meeting:error`

Payload mẫu:

```json
{
  "stream_id": "meeting_stream_001",
  "meeting_id": "meeting_abc123",
  "error_code": "meeting_request_error",
  "error_message": "Invalid meeting payload",
  "retryable": false,
  "organization_id": "org_123"
}
```

Hoặc:

```json
{
  "stream_id": "meeting_stream_001",
  "meeting_id": "meeting_abc123",
  "error_code": "meeting_background_enqueue_failed",
  "error_message": "Failed to enqueue meeting background task 'utterance_closed'",
  "retryable": false,
  "organization_id": "org_123"
}
```

Frontend nên coi `meeting:error` là normalized failure signal của feature.

## 10. Semantics quan trọng nhất cho frontend

## 10.1 Không có `meeting:partial`

Khác với STT interview, meeting capability không emit transcript partial.

Frontend chỉ nhận:

- `meeting:final`
- `meeting:utterance_closed`

## 10.2 `meeting:final` và `meeting:utterance_closed` không cùng nghĩa

`meeting:final`:

- là final fragment realtime
- có thể xảy ra nhiều lần trong một utterance
- có thể thay đổi cảm nhận realtime của UI

`meeting:utterance_closed`:

- là mốc canonical cuối cùng cho một utterance
- có `sequence`
- là nguồn authoritative cho thứ tự transcript của meeting

Nếu cần bản transcript ổn định để gắn với note chunks, event authoritative là
`meeting:utterance_closed`.

## 10.3 `speaker_label` không phải identity thật

`messages[].speaker_label` hiện có dạng:

- `speaker_1`
- `speaker_2`
- ...

Đây chỉ là label frontend-friendly từ diarization index.

Backend hiện không map các speaker này sang participant identity thật của Google
Meet.

## 10.4 Note AI là asynchronous và eventual

`meeting:note:created` không nằm trên critical realtime path.

Điều đó kéo theo:

- note có thể tới chậm hơn transcript
- note có thể tới sau khi `meeting:completed`
- note có thể tới sau khi `meeting:interrupted`
- FE không nên giả định meeting terminal event là "đã có note cuối cùng"

## 10.5 Không phải mọi batch đều tạo ra note chunk

Nếu một batch bị AI đánh giá là không note-worthy:

- backend vẫn consume batch đó
- backend không persist note chunk
- backend không emit `meeting:note:created`

Tức là frontend không thể suy từ số lượng utterance sang số lượng note chunks.

## 11. Luật batching cho AI notes

Backend chỉ tạo note chunk từ các utterance đóng liên tiếp, chưa summarize.

Rule hiện tại:

- khi có ít nhất `7` utterance contiguous sau `last_summarized_sequence` thì
  summarize đúng `7` utterance tiếp theo
- nếu meeting vẫn đang `streaming` mà chưa đủ `7` contiguous utterance thì chưa
  summarize
- khi meeting thành `completed` hoặc `interrupted`, nếu còn contiguous tail thì
  summarize nốt tail đó, kể cả tail ngắn hơn `7`

Ví dụ:

- Có sequence `1..7` -> tạo chunk `1..7`
- Có tiếp `8..14` -> tạo chunk `8..14`
- Meeting kết thúc khi mới có `15..18` -> tạo chunk cuối `15..18`

Batch chỉ hợp lệ khi sequence liền nhau. Nếu Redis đang có lỗ hổng sequence,
worker sẽ chờ contiguous range đầy đủ.

## 12. Ý nghĩa của từng nhóm dữ liệu FE nhận được

## 12.1 Transcript layer

Nguồn:

- `meeting:final`
- `meeting:utterance_closed`

Mục đích:

- hiển thị transcript realtime
- commit transcript ổn định theo sequence

Field quan trọng:

- `meeting_id`
- `stream_id`
- `utterance_id`
- `messages[]`
- `sequence` chỉ có ở `meeting:utterance_closed`

## 12.2 Note layer

Nguồn:

- `meeting:note:created`

Mục đích:

- render note chunks tăng dần
- build timeline note của meeting

Field quan trọng:

- `meeting_id`
- `from_sequence`
- `to_sequence`
- `key_points`
- `decisions`
- `action_items`

## 12.3 Terminal lifecycle layer

Nguồn:

- `meeting:completed`
- `meeting:interrupted`
- `meeting:error`

Mục đích:

- đóng vòng đời live session
- báo terminal state cho UI
- nhưng không đồng nghĩa background note work đã hoàn tất

## 13. Luồng runtime điển hình

## 13.1 Flow bình thường trong lúc meeting đang chạy

```text
meeting:start
-> meeting:started
-> meeting:final
-> meeting:final
-> meeting:utterance_closed(sequence=1)
-> meeting:final
-> meeting:utterance_closed(sequence=2)
-> ...
-> khi đủ sequence 1..7
-> meeting:note:created(from=1,to=7)
```

## 13.2 Flow kết thúc bình thường

```text
meeting:finalize
-> backend finalize Deepgram
-> flush final transcript còn lại
-> meeting:utterance_closed(last sequence)
-> meeting:completed
-> background worker tiếp tục xử lý
-> nếu còn tail chưa đủ 7
-> meeting:note:created(from=tail_start,to=tail_end) có thể tới sau completed
```

## 13.3 Flow disconnect

```text
socket disconnect
-> backend cố finalize provider
-> flush transcript còn lại nếu có
-> meeting:interrupted
-> worker vẫn có thể persist utterance/note sau đó
-> note tail cuối vẫn có thể emit muộn
```

## 13.4 Flow batch rỗng

```text
sequence 1..7 đã đủ
-> worker gọi AI
-> AI trả empty lists
-> backend không emit meeting:note:created
-> watermark vẫn advance qua 7 utterances đó
```

## 14. Những gì frontend không có từ backend ở thời điểm hiện tại

Hiện tại backend chưa cung cấp:

- REST API để list meetings
- REST API để lấy lại transcript của một meeting
- REST API để lấy lại note chunks của một meeting
- merged note snapshot do server tạo sẵn
- explicit event kiểu `meeting:note:processing_completed`
- participant identity mapping cho `speaker_1`, `speaker_2`
- replay event khi frontend reconnect
- resume live meeting session sau reconnect

Hệ quả thực tế:

- nếu frontend reload giữa meeting, state live cũ không được replay từ server
- nếu frontend muốn hiển thị history sau reload, hiện chưa có API source chính
  thức trong runtime này để lấy lại transcript hoặc notes
- terminal event không phải tín hiệu "đã chắc chắn xong note"

## 15. Các assumption FE nên giữ nguyên

- `meeting_id` là identity durable của meeting
- `stream_id` là identity của live stream hiện tại
- `sequence` là ordering key của utterance trong meeting
- `from_sequence/to_sequence` là ordering key của note chunk
- `organization_id` là context filter top-level cho mọi outbound business event
- `meeting:note:created` là additive, không phải snapshot thay thế toàn bộ note

## 16. Tóm tắt ngắn

Frontend support feature này nếu hiểu đúng 4 ý sau:

1. Transcript realtime và AI notes là hai lớp dữ liệu khác nhau.
2. `meeting:utterance_closed` là mốc transcript canonical; `meeting:note:created`
   là mốc note asynchronous ở background.
3. Note chỉ xuất hiện theo batch contiguous `7` utterances, hoặc tail cuối khi
   meeting đã terminal.
4. `meeting:completed` / `meeting:interrupted` không đảm bảo note pipeline đã
   drain xong; note chunks cuối vẫn có thể đến sau đó.
