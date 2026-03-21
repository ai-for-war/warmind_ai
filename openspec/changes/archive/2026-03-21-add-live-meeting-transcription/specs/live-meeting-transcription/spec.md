## ADDED Requirements

### Requirement: Phiên meeting transcription chạy trên Socket.IO đã xác thực và gắn với organization
Hệ thống SHALL cung cấp meeting transcription realtime trên kết nối Socket.IO đã xác thực hiện có. Mỗi phiên meeting transcription MUST được gắn với đúng user khởi tạo, đúng socket khởi tạo, và đúng `organization_id` được gửi tại thời điểm bắt đầu phiên.

#### Scenario: Bắt đầu một phiên meeting transcription hợp lệ
- **WHEN** một client đã xác thực phát `meeting:start` với `organization_id` và `stream_id` hợp lệ
- **THEN** hệ thống tạo một phiên meeting transcription mới gắn với socket đó
- **AND** hệ thống ràng buộc phiên đó với user hiện tại và organization đã khai báo

#### Scenario: Từ chối yêu cầu thiếu ngữ cảnh xác thực hoặc organization
- **WHEN** một client chưa xác thực hoặc không gửi `organization_id` hợp lệ cố gắng phát `meeting:start`
- **THEN** hệ thống MUST từ chối tạo phiên meeting transcription

### Requirement: Meeting được tạo như một transcript session bền vững với title tùy chọn
Hệ thống SHALL tạo một record `meeting` bền vững khi phiên meeting transcription bắt đầu. Record này MUST lưu tối thiểu `organization_id`, `created_by`, `stream_id`, trạng thái vòng đời, và title tùy chọn.

#### Scenario: Tạo meeting không có title
- **WHEN** client bắt đầu meeting transcription mà không truyền title
- **THEN** hệ thống vẫn MUST tạo record `meeting`
- **AND** title của meeting MUST được lưu dưới dạng rỗng hoặc `null`

#### Scenario: Tạo meeting với title được cung cấp sẵn
- **WHEN** client bắt đầu meeting transcription với title hợp lệ
- **THEN** hệ thống tạo record `meeting`
- **AND** hệ thống lưu title đó cùng meeting record

### Requirement: Audio đầu vào của meeting là PCM16 16kHz một kênh
Hệ thống SHALL chấp nhận audio browser được stream theo cùng kiểu truyền dữ liệu như luồng interview hiện tại, nhưng đối với capability meeting phase 1, audio MUST là raw `PCM16`, `16kHz`, `1-channel`.

#### Scenario: Chấp nhận chunk audio hợp lệ cho meeting
- **WHEN** client phát `meeting:audio` cho một phiên đang hoạt động với audio `PCM16`, `16kHz`, `1-channel`
- **THEN** hệ thống chấp nhận chunk đó và tiếp tục xử lý transcript

#### Scenario: Từ chối cấu hình audio không hỗ trợ
- **WHEN** client cố gắng bắt đầu hoặc gửi audio meeting với encoding, sample rate, hoặc số channel không đúng contract
- **THEN** hệ thống MUST từ chối yêu cầu với lỗi meeting transcription phù hợp

### Requirement: Mỗi socket chỉ có tối đa một phiên meeting transcription đang hoạt động
Hệ thống SHALL cho phép tối đa một phiên meeting transcription đang hoạt động trên mỗi socket trong phase 1.

#### Scenario: Bắt đầu phiên đầu tiên trên socket
- **WHEN** một socket chưa có phiên meeting transcription đang hoạt động phát `meeting:start`
- **THEN** hệ thống bắt đầu phiên mới và đánh dấu đó là phiên đang hoạt động của socket

#### Scenario: Từ chối phiên thứ hai trên cùng socket
- **WHEN** một socket đã có phiên meeting transcription đang hoạt động phát thêm một `meeting:start`
- **THEN** hệ thống MUST từ chối yêu cầu mới
- **AND** hệ thống MUST giữ nguyên phiên đang hoạt động ban đầu

### Requirement: Quyền sở hữu stream được ràng buộc với socket đã khởi tạo
Hệ thống SHALL ràng buộc mọi audio event và control event của meeting transcription với socket đã tạo phiên. Audio hoặc control event cho một stream MUST chỉ được chấp nhận từ socket sở hữu stream đó.

#### Scenario: Chấp nhận audio và finalize từ socket sở hữu stream
- **WHEN** socket đã tạo phiên meeting phát `meeting:audio` hoặc `meeting:finalize` cho đúng `stream_id`
- **THEN** hệ thống xử lý yêu cầu cho phiên đang hoạt động tương ứng

#### Scenario: Từ chối control event từ socket khác
- **WHEN** một socket khác cố gắng gửi audio hoặc finalize cho `stream_id` mà nó không sở hữu
- **THEN** hệ thống MUST từ chối yêu cầu đó
- **AND** hệ thống MUST NOT thay đổi trạng thái của phiên gốc

### Requirement: Hệ thống phải dùng Deepgram live transcription với diarization cho audio trộn một kênh
Hệ thống SHALL forward audio meeting hợp lệ tới Deepgram live transcription. Đối với capability meeting phase 1, hệ thống MUST cấu hình provider để xử lý audio trộn `1-channel` và trả về dữ liệu đủ để nhận diện speaker theo word-level diarization.

#### Scenario: Forward audio meeting tới provider
- **WHEN** hệ thống nhận chunk audio hợp lệ cho một phiên meeting đang hoạt động
- **THEN** hệ thống stream chunk đó tới Deepgram live transcription connection của phiên đó

#### Scenario: Giữ được dữ liệu speaker ở mức word cho một phiên meeting
- **WHEN** Deepgram trả về transcript final cho audio meeting đang hoạt động
- **THEN** hệ thống MUST giữ được dữ liệu word-level cần thiết để xác định speaker cho từng từ trong bộ đệm realtime của phiên

### Requirement: Frontend chỉ nhận transcript realtime ở mức final và utterance đã đóng
Hệ thống SHALL stream transcript realtime cho frontend ở phase 1 chỉ bằng các final transcript fragment và các utterance đã đóng. Hệ thống MUST NOT phát transcript partial cho capability meeting.

#### Scenario: Emit final transcript fragment cho frontend
- **WHEN** Deepgram trả về một transcript fragment với trạng thái final cho phiên meeting đang hoạt động
- **THEN** hệ thống phát event realtime final tương ứng về frontend để giao diện có thể hiển thị ngay

#### Scenario: Không emit partial transcript cho meeting
- **WHEN** provider trả về transcript interim hoặc partial cho phiên meeting
- **THEN** hệ thống MUST NOT phát event partial transcript cho frontend của capability meeting

### Requirement: Utterance ổn định chỉ được đóng khi provider phát tín hiệu utterance_end
Hệ thống SHALL chỉ coi một meeting utterance là ổn định khi provider phát tín hiệu `utterance_end` cho phần transcript final đang được tích lũy.

#### Scenario: Đóng utterance khi provider phát utterance_end
- **WHEN** hệ thống đã tích lũy được final words cho một utterance đang mở
- **AND** Deepgram phát tín hiệu `utterance_end` cho vùng transcript đó
- **THEN** hệ thống đóng utterance hiện tại
- **AND** hệ thống chuẩn bị persist utterance đó như một record bền vững

#### Scenario: Không persist utterance trước khi có utterance_end
- **WHEN** hệ thống mới chỉ nhận được final transcript fragment nhưng chưa nhận `utterance_end`
- **THEN** hệ thống MUST NOT persist meeting utterance đó xuống durable storage

### Requirement: Meeting utterance được lưu dưới dạng messages nhóm theo speaker liên tiếp
Hệ thống SHALL xây dựng `messages[]` của mỗi `meeting_utterance` bằng cách nhóm các final words liên tiếp có cùng speaker. Mỗi message MUST chứa `speaker_index`, `speaker_label`, và `text`.

#### Scenario: Tạo một message khi các word liên tiếp thuộc cùng speaker
- **WHEN** các final words liên tiếp trong một utterance đều thuộc cùng một speaker
- **THEN** hệ thống gộp các word đó thành một message duy nhất trong `messages[]`

#### Scenario: Tách thành nhiều message khi speaker thay đổi trong cùng utterance
- **WHEN** speaker thay đổi bên trong cùng một utterance đã đóng
- **THEN** hệ thống MUST tạo nhiều message theo đúng thứ tự xuất hiện của speaker
- **AND** mỗi message MUST giữ `speaker_index` theo provider
- **AND** mỗi message MUST có `speaker_label` dạng `speaker_<n>` để frontend sử dụng

### Requirement: Durable storage của utterance chỉ lưu dữ liệu transcript đã chuẩn hóa
Hệ thống SHALL persist mỗi `meeting_utterance` chỉ với dữ liệu transcript đã chuẩn hóa phục vụ product behavior. Record utterance MUST tham chiếu `meeting_id`, có `sequence` tăng dần, và lưu `messages[]`. Hệ thống MUST NOT lưu file audio, raw word payload bền vững, partial transcript, hoặc một trường transcript phẳng ở mức utterance.

#### Scenario: Lưu một meeting utterance tối thiểu
- **WHEN** một utterance đã đóng được persist
- **THEN** record `meeting_utterance` MUST chứa `meeting_id`, `sequence`, `messages[]`, và timestamp tạo record

#### Scenario: Không lưu audio hoặc raw transcript payload bền vững
- **WHEN** hệ thống persist dữ liệu transcript của meeting
- **THEN** hệ thống MUST NOT lưu file audio
- **AND** hệ thống MUST NOT lưu raw word payload bền vững
- **AND** hệ thống MUST NOT lưu partial transcript
- **AND** hệ thống MUST NOT lưu trường transcript phẳng ở mức `meeting_utterance`

### Requirement: Kết thúc phiên phải flush transcript cuối và đánh dấu trạng thái terminal phù hợp
Hệ thống SHALL kết thúc phiên meeting transcription bằng cách cố gắng flush transcript cuối từ provider trước khi cleanup. Khi kết thúc chủ động, meeting MUST được đánh dấu hoàn tất sạch. Khi socket disconnect, hệ thống MUST cố gắng finalize để vớt final words còn pending, persist utterance cuối nếu có thể, và đánh dấu meeting là bị gián đoạn.

#### Scenario: Finalize sạch một phiên meeting
- **WHEN** client phát `meeting:finalize` cho một phiên meeting đang hoạt động
- **THEN** hệ thống finalize provider-side stream
- **AND** hệ thống flush mọi final transcript còn pending
- **AND** hệ thống persist utterance cuối nếu đủ dữ liệu
- **AND** hệ thống đánh dấu meeting ở trạng thái hoàn tất sạch

#### Scenario: Socket disconnect trong lúc meeting đang hoạt động
- **WHEN** socket disconnect trong khi một phiên meeting transcription còn hoạt động
- **THEN** hệ thống MUST cố gắng finalize provider stream trước khi cleanup
- **AND** hệ thống MUST persist utterance cuối nếu còn dữ liệu final hợp lệ
- **AND** hệ thống MUST đánh dấu meeting là bị gián đoạn thay vì hoàn tất sạch

#### Scenario: Phát tín hiệu lỗi khi phiên thất bại
- **WHEN** phiên meeting transcription thất bại do input không hợp lệ, lỗi provider, hoặc lỗi xử lý nội bộ
- **THEN** hệ thống MUST phát tín hiệu lỗi realtime cho frontend
- **AND** hệ thống MUST đánh dấu meeting với trạng thái lỗi phù hợp
