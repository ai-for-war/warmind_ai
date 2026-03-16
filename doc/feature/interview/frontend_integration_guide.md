# Tài Liệu Tính Năng Interview Realtime Assistant

## 1. Mục tiêu tài liệu

Tài liệu này mô tả chính xác những gì backend hiện đang cung cấp cho tính năng
`AI hỗ trợ interview`, cùng với cách feature này hoạt động ở runtime.

Tài liệu này không đi theo hướng checklist triển khai frontend. Trọng tâm của nó là:

- backend nhận dữ liệu gì
- backend phát ra event gì
- transcript được ghép và chốt như thế nào
- AI được trigger trong điều kiện nào
- hệ thống lưu gì vào Redis, MongoDB và khi nào
- state machine và các giới hạn hiện tại của feature

## 2. Nguồn sự thật

Nếu có khác biệt giữa tài liệu này và tài liệu cũ hơn trong repo, thứ tự ưu tiên là:

1. Code runtime backend
2. OpenSpec hiện tại
3. Tài liệu này

Các file backend là nguồn chính cho feature này:

- `app/socket_gateway/server.py`
- `app/domain/schemas/stt.py`
- `app/services/stt/session.py`
- `app/services/stt/session_manager.py`
- `app/services/stt/context_store.py`
- `app/services/interview/answer_service.py`
- `app/infrastructure/deepgram/client.py`
- `app/common/event_socket.py`
- `app/config/settings.py`
- `app/prompts/system/interview_answer.py`

## 3. Phạm vi của feature

Feature hiện tại là một `interview copilot` realtime cho cuộc hội thoại 2 người nói.

Ở phase hiện tại, backend hỗ trợ:

- 1 kết nối Socket.IO đã authenticated
- 1 stream STT active trên mỗi socket
- audio `PCM16`, `16kHz`, `2-channel`
- map từng channel thành đúng 1 speaker role: `interviewer` hoặc `user`
- transcript realtime theo từng speaker
- cơ chế chốt lượt nói dựa trên provider gap detection cộng thêm grace period
- AI answer text-only sau khi interviewer kết thúc một lượt nói ổn định

Ở phase hiện tại, backend chưa hỗ trợ:

- text-to-speech cho câu trả lời AI
- nhiều hơn 2 speaker
- nhiều hơn 1 stream active trên cùng 1 socket
- đưa các AI answer cũ vào context ở turn sau

## 4. Tổng quan luồng end-to-end

```text
Browser / client
  -> Socket.IO: stt:start
  -> Socket.IO: stt:audio(metadata, binary)
  -> Backend STT session
  -> Deepgram multichannel realtime transcription
  -> Backend chuẩn hóa event transcript
  -> stt:partial / stt:final / stt:utterance_closed
  -> Redis lưu recent stable utterances
  -> nếu speaker là interviewer:
       -> build AI context từ Redis
       -> stream GPT answer
       -> interview:answer:started
       -> interview:answer:token
       -> interview:answer:completed
       -> interview:answer
  -> song song:
       -> persist utterance vào MongoDB bất đồng bộ
```

## 5. Các khái niệm cốt lõi

### 5.1 `conversation_id`

`conversation_id` là id logic của một buổi interview.

Nó được dùng để:

- nhóm toàn bộ transcript thuộc cùng một cuộc hội thoại
- build context cho AI
- gắn các event transcript và AI vào cùng một interview

### 5.2 `stream_id`

`stream_id` là id của một session STT live cụ thể trên socket.

Nó được dùng để:

- xác thực ownership khi nhận `stt:audio`, `stt:finalize`, `stt:stop`
- phân biệt session đang chạy với các session cũ

### 5.3 `utterance_id`

`utterance_id` là id của một stable utterance đã được chốt.

`utterance_id` chỉ xuất hiện khi backend đã chốt một lượt nói ổn định, cụ thể trong:

- `stt:utterance_closed`
- `interview:answer:*`

### 5.4 `channel_map`

`channel_map` là khai báo ánh xạ giữa channel audio và speaker role.

Ví dụ:

```json
{
  "0": "interviewer",
  "1": "user"
}
```

Ở runtime hiện tại:

- chỉ có channel `0` và `1`
- bắt buộc phải có đúng một `interviewer` và một `user`
- mapping này giữ nguyên trong suốt session STT đó

## 6. Những gì backend nhận vào

## 6.1 Kết nối

Toàn bộ feature chạy trên Socket.IO đã authenticated.

Nếu socket không có session hợp lệ, backend không cho khởi tạo STT session.

## 6.2 `stt:start`

Đây là event dùng để mở một session interview STT mới.

Payload:

```json
{
  "stream_id": "strm_20260316_001",
  "conversation_id": "interview_20260316_001",
  "language": "en",
  "encoding": "linear16",
  "sample_rate": 16000,
  "channels": 2,
  "channel_map": {
    "0": "interviewer",
    "1": "user"
  }
}
```

Các điều kiện hợp lệ ở runtime:

- `encoding` phải là `"linear16"`
- `sample_rate` phải là `16000`
- `channels` phải là `2`
- `channel_map` phải gán đủ hai role `interviewer` và `user`
- mỗi socket chỉ có tối đa một active STT stream

Nếu payload không hợp lệ, backend trả `stt:error`.

## 6.3 `stt:audio`

Backend nhận `stt:audio` theo dạng:

```ts
socket.emit("stt:audio", metadata, binaryAudioBuffer)
```

Metadata:

```json
{
  "stream_id": "strm_20260316_001",
  "conversation_id": "interview_20260316_001",
  "encoding": "linear16",
  "sample_rate": 16000,
  "channels": 2,
  "sequence": 0,
  "timestamp_ms": 1760000000000
}
```

Audio payload:

- là binary raw PCM16
- 2 channel được interleave
- không phải base64 string

Ở runtime hiện tại, backend:

- validate schema của metadata
- validate `stream_id`
- validate `conversation_id`
- validate ownership của session theo socket
- validate audio payload thực sự là binary

## 6.4 `stt:finalize`

Payload:

```json
{
  "stream_id": "strm_20260316_001"
}
```

Ý nghĩa:

- yêu cầu provider finalize stream hiện tại
- flush phần transcript còn lại
- chuyển session sang trạng thái finalizing

`stt:finalize` là hành động ở mức session, không phải tín hiệu chốt một turn của speaker.

## 6.5 `stt:stop`

Payload:

```json
{
  "stream_id": "strm_20260316_001"
}
```

Ý nghĩa:

- đóng session hiện tại
- đóng provider connection
- cleanup state của session trên backend

`stt:stop` mang nghĩa terminate/cancel session chứ không phải graceful turn closure.

## 7. Cấu hình audio và provider runtime

Backend đang dùng Deepgram realtime với các thông số chính:

- model: `nova-3`
- encoding: `linear16`
- sample rate: `16000`
- channels: `2`
- multichannel: `true`
- interim results: bật
- VAD events: bật
- endpointing: `500ms`
- utterance_end_ms: `1000ms`
- keepalive interval: `5s`

Ngoài ra, ứng dụng có thêm một grace period ở tầng app:

- `INTERVIEW_TURN_CLOSE_GRACE_MS = 800`

Grace period này rất quan trọng vì đây là phần quyết định khi nào backend phát
`stt:utterance_closed`.

## 8. Các event mà backend phát ra

## 8.1 Nhóm STT event

Backend phát các event STT sau:

- `stt:started`
- `stt:partial`
- `stt:final`
- `stt:utterance_closed`
- `stt:completed`
- `stt:error`

## 8.2 `stt:started`

Payload:

```json
{
  "stream_id": "strm_20260316_001",
  "conversation_id": "interview_20260316_001",
  "language": "en",
  "encoding": "linear16",
  "sample_rate": 16000,
  "channels": 2,
  "channel_map": {
    "0": "interviewer",
    "1": "user"
  }
}
```

Ý nghĩa:

- session đã mở thành công
- provider connection đã được tạo
- backend đã chấp nhận cấu hình multichannel interview cho session đó

## 8.3 `stt:partial`

Payload mẫu:

```json
{
  "stream_id": "strm_20260316_001",
  "conversation_id": "interview_20260316_001",
  "source": "interviewer",
  "channel": 0,
  "transcript": "Can you walk me through your experience with Python",
  "is_final": false
}
```

Ý nghĩa chính xác của event này:

- đây là preview hiện tại của một utterance đang mở trên một speaker cụ thể
- `transcript` là full preview hiện tại của utterance đó
- text này được tạo từ `stable_text + preview_text`
- đây không phải delta token và cũng không phải closed turn

## 8.4 `stt:final`

Payload mẫu:

```json
{
  "stream_id": "strm_20260316_001",
  "conversation_id": "interview_20260316_001",
  "source": "interviewer",
  "channel": 0,
  "transcript": "with Python",
  "is_final": true,
  "confidence": 0.97,
  "start_ms": 1200,
  "end_ms": 2100
}
```

Ý nghĩa chính xác:

- đây là một stable transcript fragment mới được provider chốt
- event này vẫn thuộc utterance đang mở
- một utterance có thể nhận nhiều `stt:final` trước khi bị close
- `stt:final` không đồng nghĩa với closed turn

## 8.5 `stt:utterance_closed`

Payload mẫu:

```json
{
  "conversation_id": "interview_20260316_001",
  "utterance_id": "utt_abc123",
  "source": "interviewer",
  "channel": 0,
  "text": "Can you walk me through your experience with Python?",
  "started_at": "2026-03-16T08:00:00.100000Z",
  "ended_at": "2026-03-16T08:00:04.400000Z",
  "turn_closed_at": "2026-03-16T08:00:05.200000Z"
}
```

Đây là event chốt turn chính thức của feature.

Ý nghĩa:

- utterance đang mở của speaker đó đã được đóng ổn định
- `text` là full stable text cuối cùng của utterance
- event này chỉ phát ra sau khi đã qua logic turn-close của backend

## 8.6 `stt:completed`

Payload:

```json
{
  "stream_id": "strm_20260316_001",
  "conversation_id": "interview_20260316_001",
  "status": "completed"
}
```

Ý nghĩa:

- session đã hoàn tất cleanly
- provider stream đã được đóng
- backend đã kết thúc lifecycle của session

## 8.7 `stt:error`

Payload mẫu:

```json
{
  "stream_id": "strm_20260316_001",
  "error_code": "stt_request_error",
  "error_message": "Invalid STT payload",
  "retryable": false
}
```

Các `error_code` có thể xuất hiện trong runtime hiện tại:

- `stt_request_error`
- `stt_provider_connection_failed`
- `stt_session_timeout`
- `stt_keepalive_failed`
- `stt_session_failed`
- `redis_context_write_failed`
- `async_utterance_persistence_failed`

Ý nghĩa tổng quát:

- một phần của lifecycle STT hoặc persistence đã thất bại
- có lỗi là fatal ở mức session
- có lỗi chỉ là degraded behavior sau khi turn đã được chốt

## 8.8 Nhóm AI answer event

Backend phát các event AI answer sau:

- `interview:answer:started`
- `interview:answer:token`
- `interview:answer:completed`
- `interview:answer`
- `interview:answer:failed`

## 8.9 `interview:answer:started`

Payload:

```json
{
  "conversation_id": "interview_20260316_001",
  "utterance_id": "utt_abc123"
}
```

Ý nghĩa:

- backend đã bắt đầu generate AI answer cho interviewer utterance có id tương ứng

## 8.10 `interview:answer:token`

Payload:

```json
{
  "conversation_id": "interview_20260316_001",
  "utterance_id": "utt_abc123",
  "token": "I have "
}
```

Ý nghĩa:

- đây là một chunk text trong quá trình stream answer

## 8.11 `interview:answer:completed`

Payload:

```json
{
  "conversation_id": "interview_20260316_001",
  "utterance_id": "utt_abc123",
  "text": "I have worked with Python for about five years..."
}
```

Ý nghĩa:

- answer đã generate xong
- `text` là full final text của AI answer

## 8.12 `interview:answer`

Payload giống `interview:answer:completed`.

Ở runtime hiện tại:

- backend emit cả `interview:answer:completed`
- và emit thêm `interview:answer`

Hai event này cùng đại diện cho final answer. Chúng không mang hai ý nghĩa khác nhau.

## 8.13 `interview:answer:failed`

Payload:

```json
{
  "conversation_id": "interview_20260316_001",
  "utterance_id": "utt_abc123",
  "error": "Failed to generate an interview answer"
}
```

Ý nghĩa:

- AI answer cho interviewer utterance tương ứng đã thất bại
- thất bại này không đồng nghĩa toàn bộ STT session bị fail

## 9. Cách backend xử lý transcript theo speaker

## 9.1 Open utterance state

Backend giữ open utterance state riêng cho từng channel:

- channel `0`
- channel `1`

Mỗi channel có thể có một utterance đang mở.

Vì vậy, ở runtime:

- interviewer và user có state live riêng
- partial/final của mỗi người không bị ghép lẫn nếu channel map đúng

## 9.2 Stable segment và preview segment

Mỗi open utterance có hai lớp text:

- `stable_segments`: các final fragments đã được provider chốt
- `preview_text`: phần text chưa final

Khi backend phát `stt:partial`, text trả về chính là:

```text
stable_text + preview_text
```

Khi backend phát `stt:final`, event đó chỉ phản ánh fragment vừa được chốt thêm vào `stable_segments`.

## 9.3 Compose transcript

Backend có logic ghép text để tránh duplicate khi fragment mới trùng đầu hoặc cuối
với text cũ.

Điều này có nghĩa:

- `stt:final` có thể là text mới ngắn
- `stt:partial` có thể là text đầy đủ hơn
- `stt:utterance_closed.text` mới là bản final authoritative của cả turn

## 10. Cơ chế turn closure

## 10.1 Tín hiệu từ provider

Deepgram phát `utterance_end` khi thấy một điểm ngắt đủ mạnh ở channel tương ứng.

## 10.2 Grace period ở tầng ứng dụng

Sau khi nhận `utterance_end`, backend không close turn ngay.

Backend đặt thêm một grace timer `800ms`.

Nếu trong 800ms đó có:

- `speech_started` mới trên cùng channel
- hoặc transcript activity mới trên cùng channel

thì pending close bị hủy và utterance đang mở tiếp tục được dùng.

Nếu hết 800ms mà không có activity mới trên cùng channel:

- utterance đó được đóng
- backend phát `stt:utterance_closed`

## 10.3 Ý nghĩa nghiệp vụ

Cơ chế này làm cho turn boundary của feature không phụ thuộc hoàn toàn vào provider,
mà là:

```text
provider gap detection + application grace
```

Đây là lý do `stt:final` không phải mốc commit turn cuối cùng.

## 11. Cơ chế persistence

## 11.1 Redis là nguồn context nhanh

Khi một utterance đã close:

- backend ghi utterance đó vào Redis
- Redis giữ một recent window các stable utterance theo timeline

Redis key logic hiện tại:

- recent utterances: `conv:{conversation_id}:recent_utterances`
- metadata: `conv:{conversation_id}:metadata`

Metadata đi kèm hiện tại gồm:

- `conversation_id`
- `channel_map`

## 11.2 MongoDB là durable persistence

Sau khi Redis ghi thành công:

- backend schedule một background task để persist utterance vào MongoDB

Điều này có nghĩa:

- Mongo persistence không nằm trên critical path của AI trigger
- turn có thể đã được close và AI đã chạy trong khi Mongo vẫn đang persist

## 11.3 Chỉ stable closed utterance mới được lưu

Backend không persist:

- partial preview state
- live unstable transcript

Backend chỉ persist:

- utterance đã close
- có `utterance_id`
- có `turn_closed_at`

## 12. Cơ chế trigger AI

## 12.1 Điều kiện trigger

AI chỉ được trigger khi:

1. event là `stt:utterance_closed`
2. speaker của utterance là `interviewer`
3. utterance đó đã được ghi thành công vào Redis

Nếu speaker là `user`:

- utterance vẫn được ghi Redis
- utterance vẫn được persist Mongo
- nhưng AI không được trigger

## 12.2 AI context được build từ đâu

Khi interviewer turn close:

- backend đọc recent stable utterances từ Redis
- nếu utterance vừa close chưa có trong Redis result, backend fallback sang Mongo window
- backend luôn ép đưa utterance vừa close vào context window

Context window hiện tại:

- giới hạn mặc định `12 utterances`
- chỉ lấy speaker `interviewer` và `user`
- không dùng previous AI answers trong phase hiện tại

## 12.3 Prompt AI dùng gì

Backend gửi vào model:

- system prompt cho interview copilot
- user prompt chứa:
  - recent stable transcript
  - latest interviewer utterance

Prompt được thiết kế để:

- trả lời ngắn gọn
- bám đúng transcript
- không bịa thêm dữ kiện ngoài transcript
- nếu không đủ dữ kiện thì ưu tiên continuation hợp lý hoặc câu hỏi làm rõ ngắn

## 12.4 Model và output

AI answer hiện tại:

- dùng `gpt-5.2`
- streaming enabled
- max tokens `1024`
- output text-only

Backend không phát audio và không yêu cầu TTS trong flow này.

## 13. Session lifecycle và state machine

## 13.1 Trạng thái session

Ở tầng backend, session có các state:

- `STARTING`
- `STREAMING`
- `FINALIZING`
- `COMPLETED`
- `FAILED`

## 13.2 Chuyển trạng thái cơ bản

```text
STARTING
  -> provider open thành công
  -> STREAMING

STREAMING
  -> nhận finalize
  -> FINALIZING

FINALIZING
  -> provider finalize xong + close xong
  -> COMPLETED

STREAMING / FINALIZING
  -> lỗi provider / timeout / lỗi nghiêm trọng
  -> FAILED
```

## 13.3 Timeout policy

Backend có các timeout chính:

- startup idle timeout: `15s`
- stream inactivity timeout: `45s`
- finalize grace timeout: `10s`

Ngoài ra backend có keepalive:

- gửi `KeepAlive` mỗi `5s` trong thời gian im lặng nếu session vẫn active

## 13.4 Ownership và scale assumptions

Session live được giữ trong memory của process theo `sid`.

Điều đó kéo theo hai đặc điểm runtime:

- stream ownership gắn với socket đã tạo stream
- deployment scale ngang cần sticky session cho traffic Socket.IO

Nếu request audio/control đi sang instance khác:

- backend sẽ không thấy active session đó
- request bị từ chối như không có session hợp lệ

## 14. Các chuỗi sự kiện thường gặp

## 14.1 Interviewer nói và AI trả lời

```text
stt:start
-> stt:started
-> stt:partial(interviewer)
-> stt:final(interviewer)
-> stt:partial(interviewer)
-> utterance_end từ provider
-> 800ms không có speech mới
-> stt:utterance_closed(interviewer)
-> Redis append closed utterance
-> interview:answer:started
-> interview:answer:token
-> interview:answer:token
-> interview:answer:completed
-> interview:answer
-> Mongo persist async
```

## 14.2 User nói nhưng không trigger AI

```text
stt:partial(user)
-> stt:final(user)
-> utterance_end từ provider
-> 800ms không có speech mới
-> stt:utterance_closed(user)
-> Redis append closed utterance
-> Mongo persist async
```

Flow này không có `interview:answer:*`.

## 14.3 Speech resume trước khi close

```text
stt:partial
-> stt:final
-> provider utterance_end
-> trong 800ms có speech_started hoặc transcript mới
-> pending close bị hủy
-> utterance tiếp tục mở
```

## 14.4 Kết thúc session bằng finalize

```text
STREAMING
-> stt:finalize
-> FINALIZING
-> provider finalize
-> provider close
-> stt:completed
```

## 14.5 Dừng session bằng stop

```text
STREAMING hoặc FINALIZING
-> stt:stop
-> provider close
-> cleanup session
```

`stop` là close session ở mức transport/lifecycle, không phải cơ chế chốt turn cho AI.

## 15. Những điểm semantics quan trọng nhất của feature

## 15.1 `stt:partial` không phải delta

`stt:partial.transcript` là full preview hiện tại của một utterance đang mở.

## 15.2 `stt:final` không phải closed turn

`stt:final` chỉ là một stable fragment mới.

## 15.3 `stt:utterance_closed` mới là turn boundary chính thức

Nếu cần biết khi nào một lượt nói đã được chốt ổn định, event authoritative là:

- `stt:utterance_closed`

## 15.4 AI chỉ chạy sau interviewer turn đã close

AI không chạy:

- ở `stt:partial`
- ở `stt:final`
- ở `stt:finalize`
- ở user turn

## 15.5 `interview:answer:completed` và `interview:answer` hiện đang là hai final signal trùng nghĩa

Runtime hiện tại phát cả hai event với cùng payload final answer.

## 16. Các giới hạn hiện tại

- Chỉ có 2 speaker role: `interviewer`, `user`
- Chỉ có 2 channel audio: `0`, `1`
- Chỉ có 1 active stream trên mỗi socket
- Session state không survive cross-instance rebalance
- AI context phase 1 không đưa AI answers cũ vào window
- Flow này chưa có TTS

## 17. Lưu ý về tài liệu cũ trong repo

Guide cũ ở `doc/feature/s2t/live_speech_to_text_frontend_guide.md` mô tả:

- audio mono
- `channels = 1`
- chưa có speaker-aware interview flow

Feature interview hiện tại đã khác:

- `channels = 2`
- có `conversation_id`
- có `channel_map`
- có `stt:utterance_closed`
- có `interview:answer:*`

Vì vậy, tài liệu cũ không còn là mô tả đúng cho feature interview này.

## 18. Tóm tắt ngắn

Feature hiện tại cung cấp một realtime interview assistant với hành vi cốt lõi như sau:

1. Nhận audio 2 kênh qua Socket.IO và gán từng kênh cho `interviewer` hoặc `user`.
2. Tách transcript realtime theo từng speaker, gồm partial và final fragments.
3. Chỉ chốt một turn khi provider thấy khoảng ngắt và sau đó vẫn im lặng thêm `800ms`.
4. Ghi stable closed utterance vào Redis trước, Mongo sau.
5. Chỉ khi interviewer turn đã close và đã vào Redis thì mới trigger AI answer text-only.
