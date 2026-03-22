## Why

Hệ thống hiện tại đã có live speech-to-text cho luồng `interview`, nhưng luồng đó được thiết kế cho audio `2-channel`, ánh xạ cố định `interviewer/user`, có preview partial, và gắn với logic AI answer. Cấu trúc đó không phù hợp với bài toán ghi nhận transcript cuộc họp realtime từ audio trộn `1-channel` của Google Meet, dùng diarization để tách speaker và lưu transcript theo `meeting` cùng các `utterance` bền vững.

Sản phẩm cần một luồng meeting transcription riêng chạy trên Socket.IO hiện có, không lưu file audio, hiển thị transcript realtime cho frontend, và chỉ persist dữ liệu ổn định khi Deepgram xác định kết thúc một utterance.

## What Changes

- Bổ sung capability live meeting transcription riêng cho audio cuộc họp realtime, sử dụng kết nối Socket.IO đã xác thực thay vì reuse trực tiếp luồng `interview`
- Giữ contract audio frontend tương thích với luồng interview hiện tại về kiểu dữ liệu stream, nhưng chuẩn hóa meeting phase 1 là `PCM16`, `16kHz`, `1-channel`
- Mở một Deepgram live transcription session riêng cho mỗi meeting session và bật diarization để nhận diện speaker trên audio trộn một kênh
- Chỉ stream các transcript `final` và sự kiện `utterance_closed` về frontend; không phát sự kiện partial cho capability meeting trong phase 1
- Tạo collection `meetings` để lưu metadata và vòng đời phiên transcript theo `organization`, `created_by`, `title`, `status`, `stream_id`, và thời gian bắt đầu/kết thúc
- Tạo collection `meeting_utterances` để lưu từng utterance đã ổn định, mỗi record chỉ chứa `meeting_id`, `sequence`, và `messages[]`
- Xây dựng `messages[]` từ các final words đã được diarization của Deepgram bằng cách nhóm các word liên tiếp theo speaker, ví dụ `speaker_1` và `speaker_2`
- Chỉ persist utterance khi Deepgram phát tín hiệu `utterance_end`; không lưu partial transcript, không lưu raw word payload bền vững, và không lưu file audio
- Khi socket disconnect, backend phải cố gắng finalize Deepgram stream để vớt final words còn pending, persist utterance cuối nếu đủ dữ liệu, rồi đóng meeting dưới trạng thái bị gián đoạn thay vì coi là hoàn tất sạch
- Giữ nguyên hành vi hiện tại của capability `interview`; mọi thay đổi dùng chung ở adapter/provider phải là additive để không làm thay đổi contract hoặc semantics của interview flow

## Capabilities

### New Capabilities
- `live-meeting-transcription`: Ghi nhận transcript cuộc họp realtime từ audio trộn một kênh, stream final transcript về frontend, và persist các utterance đã ổn định dưới dạng `messages[]` được tách speaker bằng diarization

### Modified Capabilities
Không có.

## Impact

- **Realtime contract mới**: bổ sung inbound socket events cho meeting như `meeting:start`, `meeting:audio`, `meeting:finalize`, `meeting:stop`, cùng outbound events như `meeting:started`, `meeting:final`, `meeting:utterance_closed`, `meeting:completed`, `meeting:interrupted`, và `meeting:error`
- **Persistence mới**: thêm durable model, schema, repository, và index cho `meetings` và `meeting_utterances`
- **Provider integration**: mở rộng normalized Deepgram live adapter theo hướng additive để capability meeting có thể giữ dữ liệu word-level cần thiết cho diarization grouping mà không làm thay đổi logic interview hiện có
- **Service layer mới**: thêm meeting-specific session, session manager, service, và cleanup policy riêng thay vì nhồi thêm nhánh điều kiện vào interview STT flow
- **Frontend behavior mới**: frontend nhận final transcript realtime và utterance đã đóng; phase 1 không yêu cầu partial preview, participant identity mapping, hay audio upload/storage
- **Affected code**: `app/socket_gateway/`, `app/common/event_socket.py`, `app/common/service.py`, `app/config/settings.py`, `app/infrastructure/deepgram/`, `app/infrastructure/database/`, `app/domain/models/`, `app/domain/schemas/`, `app/repo/`, và `app/services/meeting/`
- **Operational semantics**: meeting transcript vẫn là session state gắn với app instance đang giữ socket; khi scale ngang vẫn cần affinity nếu không externalize session state trong tương lai
