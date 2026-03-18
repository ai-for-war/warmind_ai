# Live Speech-to-Text Streaming - Frontend Integration Guide

## 1. Mục tiêu tài liệu

Tài liệu này mô tả đầy đủ contract backend cho tính năng live speech-to-text (STT) để frontend có thể:

- capture microphone từ browser
- gửi audio realtime qua Socket.IO
- nhận transcript `partial` và `final`
- render UI ổn định
- xử lý lifecycle `start -> streaming -> finalize/stop -> completed/error`

Phạm vi tài liệu bám theo code backend hiện tại, không theo ý tưởng tương lai.

## 2. Tính năng này làm gì

Frontend mở một stream STT trên chính kết nối `Socket.IO` đã authenticated. Sau đó frontend gửi các chunk audio nhị phân từ microphone lên backend. Backend forward audio đó sang Deepgram và emit transcript ngược lại cho chính user đó.

Backend hiện hỗ trợ:

- browser microphone streaming
- transcript realtime dạng `partial`
- transcript commit dạng `final`
- cleanup khi `finalize`, `stop`, hoặc disconnect

Backend hiện chưa hỗ trợ:

- lưu transcript vào database
- trigger workflow/agent sau transcript
- nhiều speaker trong cùng stream
- nhiều stream đồng thời trên cùng một socket
- browser gọi trực tiếp Deepgram
- resume stream sau disconnect

## 3. Kiến trúc FE cần hiểu

Luồng tổng quát:

```text
Browser Mic
  -> AudioWorklet / processor
  -> PCM16 mono 16kHz binary chunks
  -> Socket.IO: stt:start
  -> Socket.IO: stt:audio
  -> Backend STT session
  -> Deepgram
  -> Socket.IO: stt:partial / stt:final / stt:completed / stt:error
  -> FE transcript UI
```

## 4. Điều kiện bắt buộc trước khi gọi STT

Frontend chỉ được dùng STT khi socket đã authenticated thành công.

Backend đọc `user_id` từ session của socket. Nếu socket chưa authenticate thì mọi STT event sẽ fail.

FE cần đảm bảo:

- socket đã connect thành công
- socket đang dùng cùng auth flow với hệ thống hiện tại
- không mở nhiều stream STT trên cùng một socket cùng lúc

## 5. Audio contract bắt buộc

Phase 1 khóa cứng audio format như sau:

- `encoding = linear16`
- `sample_rate = 16000`
- `channels = 1`
- audio payload là binary raw PCM16

Khuyến nghị phía FE:

- capture bằng `AudioWorklet`
- resample về `16kHz`
- convert Float32 PCM sang signed PCM16 little-endian
- gửi frame nhỏ, khoảng `20-40ms`

### 5.1 Kích thước frame khuyến nghị

Với `16kHz`, `mono`, `PCM16`:

- 20ms = `320 samples` = `640 bytes`
- 40ms = `640 samples` = `1280 bytes`

FE nên giữ frame size ổn định để giảm jitter và dễ debug.

## 6. Socket event contract

### 6.1 Inbound events từ frontend lên backend

- `stt:start`
- `stt:audio`
- `stt:finalize`
- `stt:stop`

### 6.2 Outbound events từ backend về frontend

- `stt:started`
- `stt:partial`
- `stt:final`
- `stt:completed`
- `stt:error`

## 7. Payload chi tiết

## 7.1 `stt:start`

Event dùng để tạo session STT mới.

Payload:

```json
{
  "stream_id": "stream-001",
  "language": "en",
  "encoding": "linear16",
  "sample_rate": 16000,
  "channels": 1
}
```

Field:

- `stream_id`: bắt buộc, chuỗi định danh stream do FE tự tạo
- `language`: optional, nếu bỏ qua backend sẽ dùng `en`
- `encoding`: bắt buộc, chỉ chấp nhận `"linear16"`
- `sample_rate`: bắt buộc, chỉ chấp nhận `16000`
- `channels`: bắt buộc, chỉ chấp nhận `1`

Lưu ý:

- `language` sẽ được normalize lowercase ở backend
- nếu gửi sai format audio, backend emit `stt:error`
- nếu socket đã có stream active khác, backend reject stream mới

## 7.2 `stt:audio`

Event gửi audio realtime.

Socket handler nhận 2 phần:

1. metadata payload
2. binary audio payload

Metadata:

```json
{
  "stream_id": "stream-001",
  "sequence": 0,
  "timestamp_ms": 1710000000000
}
```

Binary payload:

- raw PCM16 bytes
- không base64
- truyền trực tiếp như `ArrayBuffer`, `Uint8Array`, hoặc binary tương đương tùy client Socket.IO

Field:

- `stream_id`: bắt buộc
- `sequence`: bắt buộc, số nguyên tăng dần theo từng frame
- `timestamp_ms`: optional, timestamp capture phía client

Lưu ý quan trọng:

- backend hiện yêu cầu audio payload phải là binary thật
- `sequence` hiện là best-effort metadata, chưa reject duplicate/missing frame ở schema layer
- FE vẫn nên giữ `sequence` tăng đơn điệu để debug và mở rộng sau này

## 7.3 `stt:finalize`

Yêu cầu backend flush transcript còn lại từ provider trước khi complete.

Payload:

```json
{
  "stream_id": "stream-001"
}
```

Dùng khi:

- user bấm kết thúc ghi âm bình thường
- FE muốn chờ transcript cuối cùng được commit sạch

Khác với `stop`:

- `finalize` là đường kết thúc đúng chuẩn
- backend chuyển session sang trạng thái finalizing và đợi transcript còn lại

## 7.4 `stt:stop`

Đóng stream và cleanup.

Payload:

```json
{
  "stream_id": "stream-001"
}
```

Dùng khi:

- user cancel
- FE cần dừng ngay
- app unmount hoặc đổi mode

Lưu ý:

- `stop` vẫn có thể nhận một ít event còn pending trước khi listener bị cancel
- nhưng về mặt UX, nên xem `stop` là hành động terminate thay vì đường commit transcript chuẩn

## 7.5 `stt:started`

Ack backend khi stream mở thành công.

Payload:

```json
{
  "stream_id": "stream-001",
  "language": "en",
  "encoding": "linear16",
  "sample_rate": 16000,
  "channels": 1
}
```

FE nên dùng event này để xác nhận stream thực sự active trước khi hiển thị trạng thái "Listening".

## 7.6 `stt:partial`

Transcript tạm thời, chưa commit.

Payload:

```json
{
  "stream_id": "stream-001",
  "transcript": "hello wor",
  "is_final": false
}
```

Ý nghĩa:

- text đang thay đổi trong lúc user còn nói
- không nên append vĩnh viễn vào transcript history
- nên render vào vùng "current live text"

Backend có logic ghép `partial` với final fragments đang buffer để partial nhìn liền mạch hơn.

## 7.7 `stt:final`

Transcript đã commit ổn định cho một segment.

Payload:

```json
{
  "stream_id": "stream-001",
  "transcript": "hello world",
  "is_final": true,
  "confidence": 0.97,
  "start_ms": 0,
  "end_ms": 1140
}
```

Field:

- `transcript`: bắt buộc, đã ổn định cho UI commit
- `is_final`: luôn là `true`
- `confidence`: optional
- `start_ms`: optional
- `end_ms`: optional

FE nên:

- append `transcript` này vào danh sách final segments
- clear vùng partial hiện tại nếu nó tương ứng segment vừa commit

## 7.8 `stt:completed`

Backend báo stream kết thúc sạch.

Payload:

```json
{
  "stream_id": "stream-001",
  "status": "completed"
}
```

FE nên:

- stop recorder/worklet nếu chưa stop
- chuyển UI về idle/completed
- không gửi thêm `stt:audio` cho stream đó nữa

## 7.9 `stt:error`

Payload lỗi chuẩn hóa.

Ví dụ:

```json
{
  "stream_id": "stream-001",
  "error_code": "stt_request_error",
  "error_message": "Invalid STT payload",
  "retryable": false
}
```

Hoặc:

```json
{
  "stream_id": "stream-001",
  "error_code": "stt_session_failed",
  "error_message": "Provider closed before stream finalized",
  "retryable": false
}
```

Field:

- `stream_id`: có thể có hoặc không
- `error_code`: mã lỗi ngắn
- `error_message`: message để log/debug/UI
- `retryable`: hiện backend mặc định `false`

## 8. State machine FE đề xuất

FE nên quản lý state stream tách biệt với transcript state.

### 8.1 Stream state

Đề xuất:

- `idle`
- `starting`
- `streaming`
- `finalizing`
- `completed`
- `error`
- `stopped`

### 8.2 Transcript state

Đề xuất:

- `finalSegments: Array<{ text, confidence?, startMs?, endMs? }>`
- `partialText: string`
- `currentStreamId: string | null`

### 8.3 Chuyển trạng thái khuyến nghị

```text
idle
  -> stt:start sent
  -> starting
  -> stt:started
  -> streaming
  -> stt:partial
  -> streaming
  -> stt:final
  -> streaming
  -> stt:finalize sent
  -> finalizing
  -> stt:final (optional more)
  -> stt:completed
  -> completed
```

Nhánh lỗi:

```text
starting/streaming/finalizing
  -> stt:error
  -> error
```

Nhánh hủy:

```text
streaming
  -> stt:stop sent
  -> stopped
```

## 9. Quy tắc render transcript

Backend tách 2 loại text:

- `partial`: text đang phát sinh, chưa chốt
- `final`: segment đã chốt

Chiến lược render an toàn:

```text
renderedText = finalSegments.join(" ") + " " + partialText
```

Khuyến nghị:

- chỉ lưu vĩnh viễn `stt:final`
- `stt:partial` chỉ để preview
- khi nhận `stt:final`, xóa `partialText` nếu nó thuộc cùng segment

## 10. Lifecycle chuẩn FE nên dùng

## 10.1 Start flow

1. Xin quyền microphone.
2. Tạo `stream_id`.
3. Khởi tạo audio processor.
4. Emit `stt:start`.
5. Bắt đầu gửi `stt:audio`.
6. Chờ `stt:started`.

Lưu ý:

- backend không bắt buộc phải nhận `stt:started` trước mới cho gửi audio
- nhưng FE vẫn nên chờ hoặc ít nhất buffer rất ngắn trước khi stream audio để UX ổn định hơn

## 10.2 Finalize flow

1. Dừng capture audio từ mic.
2. Emit `stt:finalize`.
3. Chờ `stt:final` cuối cùng nếu có.
4. Chờ `stt:completed`.
5. Chuyển UI về trạng thái xong.

Đây là flow nên dùng khi user kết thúc bình thường.

## 10.3 Stop flow

1. Dừng capture audio từ mic.
2. Emit `stt:stop`.
3. Cleanup local state.

Dùng cho cancel hoặc force stop.

## 11. Timeout và keepalive FE cần biết

Backend có chính sách timeout nội bộ:

- stream mở nhưng không nhận audio đủ lâu: timeout
- stream đang chạy mà im lặng quá lâu: backend có thể auto-finalize
- stream ở trạng thái finalizing quá lâu: backend sẽ hard-close

Ý nghĩa với FE:

- không nên mở stream rồi chờ lâu mới bắt đầu gửi audio
- khi user dừng nói và muốn kết thúc, nên chủ động gửi `stt:finalize`
- không nên giữ stream mở vô thời hạn

## 12. Ownership và concurrency rules

Các rule backend đang enforce:

- mỗi socket chỉ có tối đa 1 active stream
- audio/control event phải đến từ đúng socket đã tạo stream
- cùng một account trên 2 socket khác nhau vẫn có thể transcribe độc lập

Hệ quả FE:

- nếu app có nhiều tab dùng chung account, mỗi tab nên có socket riêng
- trong cùng một tab/socket, bắt buộc kết thúc stream cũ trước khi start stream mới

## 13. Error scenarios FE phải xử lý

### 13.1 Gửi sai audio format

Triệu chứng:

- nhận `stt:error`

Nguyên nhân:

- không phải `linear16`
- sample rate không phải `16000`
- channels không phải `1`

### 13.2 Gửi audio không phải binary

Triệu chứng:

- nhận `stt:error`

Nguyên nhân:

- gửi base64 string
- gửi object thay vì `ArrayBuffer`/bytes

### 13.3 Start stream thứ hai trên cùng socket

Triệu chứng:

- stream mới fail
- stream cũ vẫn active

Nguyên nhân:

- backend chỉ cho phép `1 active stream / socket`

### 13.4 Stream ownership mismatch

Triệu chứng:

- `stt:error`

Nguyên nhân:

- gửi `stt:audio`, `stt:finalize`, `stt:stop` với `stream_id` không match session hiện tại

### 13.5 Provider đóng stream trước khi finalize xong

Triệu chứng:

- có thể nhận `stt:error` kiểu `Provider closed before stream finalized`

FE nên:

- dừng UI streaming
- cho phép user retry bằng stream mới

## 14. Checklist tích hợp FE

- socket đã authenticated trước khi gọi STT
- chỉ dùng 1 active stream trên mỗi socket
- `stream_id` là duy nhất cho mỗi session
- audio đúng `linear16/16000/mono`
- `stt:audio` gửi binary thật, không base64
- `sequence` tăng đều
- `partial` chỉ render tạm thời
- `final` mới append vào transcript chính
- khi kết thúc bình thường dùng `stt:finalize`
- xử lý `stt:error` ở mọi state
- cleanup mic/audio context khi completed, error, stop, unmount

## 15. Những assumption backend hiện tại

Đây là các assumption FE không nên vi phạm:

- stream state nằm in-memory theo app instance đang giữ socket
- nếu hệ thống scale ngang, deployment cần sticky session cho inbound socket traffic
- transcript event contract là normalized, FE không nên phụ thuộc semantics riêng của Deepgram
- backend không đảm bảo persistence transcript

## 16. Tóm tắt ngắn cho FE

Nếu chỉ cần phần cốt lõi để làm nhanh:

1. Connect socket đã auth.
2. Emit `stt:start` với `stream_id`, `language`, `linear16`, `16000`, `1`.
3. Gửi binary PCM16 chunks qua `stt:audio`.
4. Render `stt:partial` vào live preview.
5. Append `stt:final` vào transcript chính.
6. Khi user kết thúc bình thường, gửi `stt:finalize` và chờ `stt:completed`.
7. Nếu user cancel, gửi `stt:stop`.
8. Nếu có `stt:error`, cleanup local stream và cho phép start stream mới.
