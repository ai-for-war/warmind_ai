## 1. Domain và persistence

- [x] 1.1 Thêm model/schema cho `meeting` và `meeting_utterance` với các field đã chốt trong design
- [x] 1.2 Tạo repository cho `meetings` và `meeting_utterances` kèm index truy vấn theo meeting và sequence
- [x] 1.3 Wiring collection mới vào dependency/container hiện có mà không ảnh hưởng repo của interview

## 2. Deepgram adapter cho meeting

- [x] 2.1 Mở rộng normalized provider event để hỗ trợ word-level speaker data theo hướng additive, không đổi semantics field cũ của interview
- [x] 2.2 Thêm cấu hình Deepgram riêng cho meeting với `PCM16`, `16kHz`, `1-channel`, `diarize=true`, `interim_results=true`
- [x] 2.3 Giữ nguyên default config và code path interview để tránh regression khi meeting bật diarization

## 3. Meeting session core

- [ ] 3.1 Tạo `MeetingSession` với state machine `streaming -> finalizing -> completed|interrupted|failed`
- [ ] 3.2 Buffer chỉ các final words của meeting và emit `meeting:final` cho frontend, không forward partial transcript
- [ ] 3.3 Implement thuật toán group final words theo speaker liên tiếp để build `messages[]` canonical
- [ ] 3.4 Persist `meeting_utterance` chỉ khi nhận `utterance_end`, gán `sequence` tăng dần theo từng meeting

## 4. Session manager và lifecycle cleanup

- [ ] 4.1 Tạo `MeetingSessionManager` để enforce tối đa một meeting session đang hoạt động trên mỗi socket
- [ ] 4.2 Ràng buộc ownership của `stream_id` với socket đã tạo session cho mọi event `meeting:audio`, `meeting:finalize`, `meeting:stop`
- [ ] 4.3 Xử lý `meeting:finalize` và `meeting:stop` theo luồng flush provider, persist utterance cuối nếu hợp lệ, rồi đánh dấu `completed`
- [ ] 4.4 Xử lý disconnect theo luồng `Finalize -> drain grace window -> persist cuối -> close provider -> interrupted`

## 5. Socket contract và service wiring

- [ ] 5.1 Thêm event constants và payload schema cho `meeting:start`, `meeting:audio`, `meeting:finalize`, `meeting:stop`
- [ ] 5.2 Tạo `MeetingService` và đăng ký handlers Socket.IO để khởi tạo session từ user/socket/organization đã xác thực
- [ ] 5.3 Emit đầy đủ các outbound event `meeting:started`, `meeting:final`, `meeting:utterance_closed`, `meeting:completed`, `meeting:interrupted`, `meeting:error`

## 6. Kiểm thử và xác minh

- [ ] 6.1 Viết unit test cho thuật toán group `words -> messages[]` với case đổi speaker trong cùng một utterance
- [ ] 6.2 Viết test cho lifecycle meeting: start, final-only stream, persist tại `utterance_end`, finalize sạch, và disconnect interrupted
- [ ] 6.3 Chạy targeted verification để xác nhận interview flow cũ vẫn hoạt động và meeting flow mới không lưu audio, partial, hay raw words
