## Context

Hệ thống hiện tại đã có một luồng live speech-to-text chạy trên Socket.IO và
Deepgram, nhưng luồng đó được tối ưu cho bài toán `interview`:

- audio `2-channel`
- mapping speaker cố định `interviewer` và `user`
- có preview partial cho UI
- có Redis context và AI answer flow
- dữ liệu bền vững xoay quanh `interview_conversation` và `interview_utterance`

Capability meeting mới có shape khác rõ rệt:

- audio đầu vào là `1-channel` đã trộn từ Google Meet
- speaker identity đến từ diarization thay vì channel map
- frontend chỉ cần realtime `final` và `utterance_closed`
- không lưu file audio
- không lưu partial transcript
- không lưu raw words bền vững
- mỗi `meeting_utterance` chỉ lưu `messages[]` đã chuẩn hóa theo speaker
- socket disconnect được xem là kết thúc session và phải cố gắng flush transcript
  cuối trước khi đóng phiên

Thay đổi này là cross-cutting vì nó chạm vào:

- realtime contract của Socket.IO
- provider adapter Deepgram
- session state machine
- MongoDB data model và index
- service/repo wiring

**Tài liệu Deepgram chính thức dùng cho thiết kế này:**
- [Live Audio API reference](https://developers.deepgram.com/reference/speech-to-text-api/listen-streaming)
- [Speaker Diarization](https://developers.deepgram.com/docs/diarization/)
- [Utterance End](https://developers.deepgram.com/docs/utterance-end)
- [Configure Endpointing and Interim Results](https://developers.deepgram.com/docs/understand-endpointing-interim-results)
- [Finalize](https://developers.deepgram.com/docs/finalize)
- [Audio Keep Alive](https://developers.deepgram.com/docs/audio-keep-alive)

**Các phát hiện chính từ docs ảnh hưởng trực tiếp đến thiết kế:**
- `utterance_end_ms` cần `interim_results=true`, kể cả khi ứng dụng không muốn
  phát partial ra frontend
- live diarization trả speaker ở mức `word`, nên muốn có
  `speaker_1: ... / speaker_2: ...` thì backend phải tự nhóm words
- `speech_final` và `utterance_end` không hoàn toàn đồng nghĩa; `utterance_end`
  là mốc phù hợp hơn để persist utterance theo yêu cầu hiện tại
- `Finalize` là cơ chế phù hợp để flush audio còn pending trước khi đóng stream
- keepalive vẫn cần khi stream mở nhưng đang im lặng

## Goals / Non-Goals

**Goals:**
- Bổ sung một luồng meeting transcription riêng, không reuse trực tiếp state
  machine của interview
- Dùng Deepgram live transcription cho audio `PCM16`, `16kHz`, `1-channel`
- Bật diarization và giữ đủ dữ liệu word-level trong memory để nhóm
  `messages[]`
- Chỉ phát `meeting:final` và `meeting:utterance_closed` cho frontend
- Chỉ persist `meeting_utterance` khi có `utterance_end`
- Lưu `meeting` như một session bền vững theo `organization` và `created_by`
- Khi disconnect, cố gắng `Finalize`, persist utterance cuối nếu hợp lệ, rồi
  đóng meeting ở trạng thái `interrupted`
- Giữ nguyên semantics của interview flow hiện tại

**Non-Goals:**
- Lưu file audio hoặc URL audio
- Persist raw `words[]` từ Deepgram
- Persist partial transcript
- Map diarization speaker sang participant thật của Google Meet
- Resume transcript session sau reconnect
- Chia sẻ session ownership giữa nhiều app instance
- Gom meeting transcript và interview transcript vào chung một capability

## Decisions

### D1: Tách meeting thành một capability realtime riêng thay vì nhồi thêm nhánh điều kiện vào interview flow

**Decision**: Tạo namespace socket, service layer, session state, repository, và
data model riêng cho meeting transcription.

**Alternatives considered:**
- **Reuse trực tiếp `STTSession`/`STTSessionManager` của interview**: nhanh hơn
  lúc đầu nhưng tạo ra state machine lai giữa `2-channel` channel map và
  `1-channel` diarization, rất khó đọc và dễ regression
- **Nhét meeting thành một mode trong session hiện tại**: làm tăng số nhánh
  điều kiện trong cùng một code path realtime đang phục vụ interview

**Rationale**: Interview và meeting khác nhau ở speaker attribution, event
contract, persistence rule, và terminal semantics. Tách riêng giúp giảm nguy cơ
đụng vào logic AI answer hiện có và giữ mỗi state machine đúng với business
rule của nó.

**Hệ quả kiến trúc:**
- inbound events mới: `meeting:start`, `meeting:audio`, `meeting:finalize`,
  `meeting:stop`
- outbound events mới: `meeting:started`, `meeting:final`,
  `meeting:utterance_closed`, `meeting:completed`, `meeting:interrupted`,
  `meeting:error`
- package mới: `app/services/meeting/`

### D2: Giữ adapter Deepgram dùng chung nhưng chỉ mở rộng theo hướng additive

**Decision**: Không tạo adapter Deepgram thứ hai. Thay vào đó, mở rộng
normalized provider model hiện có bằng các field tùy chọn mới phục vụ meeting,
đặc biệt là word-level speaker data.

**Alternatives considered:**
- **Fork adapter riêng cho meeting**: giảm coupling ngắn hạn nhưng tạo duplicate
  logic kết nối, keepalive, finalize, close, và normalize event
- **Cho meeting đọc raw Deepgram SDK payload trực tiếp**: nhanh nhưng phá vỡ
  boundary abstraction của infrastructure layer

**Rationale**: Kết nối Deepgram vẫn là cùng một provider transport problem.
Điều cần khác nhau là session behavior ở lớp application, không phải cách mở
websocket. Mở rộng additive là safe path vì interview hiện tại chỉ dùng
`transcript`, `confidence`, `start_ms`, `end_ms`; nếu thêm field mới kiểu
`normalized_words | None`, interview sẽ không đổi hành vi.

**Quy tắc an toàn để không ảnh hưởng interview:**
- không đổi ý nghĩa các field cũ trong `ProviderTranscriptEvent`
- không đổi default config đang được factory interview sử dụng
- không để `diarize=true`, `channels=1`, `multichannel=false` trở thành default
  dùng chung
- meeting phải truyền config riêng khi tạo provider client

### D3: Dùng audio contract giống interview về transport, nhưng contract business của meeting là mono diarization

**Decision**: Frontend tiếp tục gửi audio theo cơ chế binary chunk giống luồng
interview hiện tại, nhưng meeting phase 1 chấp nhận duy nhất `PCM16`, `16kHz`,
`1-channel`.

**Alternatives considered:**
- **Cho phép nhiều format browser khác nhau**: tăng branching và validation
- **Chuyển sang upload file hoặc callback async**: không đúng với requirement
  streaming realtime

**Rationale**: Reuse transport shape hiện có giúp frontend/backend integration
đỡ rủi ro, nhưng business semantics phải được fix rõ ràng để provider config và
session logic không mơ hồ.

### D4: Provider vẫn phải bật interim results dù frontend không nhận partial

**Decision**: Meeting session sẽ mở Deepgram với `interim_results=true`,
`diarize=true`, `channels=1`, `multichannel=false`, `endpointing`, và
`utterance_end_ms`, nhưng ứng dụng chỉ phát `meeting:final` và
`meeting:utterance_closed`.

**Alternatives considered:**
- **Tắt interim results vì frontend không cần partial**: không dùng được
  `utterance_end`
- **Forward luôn partial cho FE**: trái với quyết định sản phẩm hiện tại

**Rationale**: Requirement business là "không stream partial", không phải
"provider không được sinh partial". Ta vẫn cần interim ở phía provider để lấy
`utterance_end`, nhưng chặn partial ở application boundary.

**Provider config đề xuất cho meeting:**

```python
{
    "model": "nova-3",
    "encoding": "linear16",
    "sample_rate": "16000",
    "channels": "1",
    "multichannel": "false",
    "interim_results": "true",
    "vad_events": "true",
    "endpointing": "400",
    "utterance_end_ms": "1000",
    "diarize": "true",
    "smart_format": "true",
    "punctuate": "true",
}
```

### D5: Persist ở mốc utterance_end, không ở speech_final

**Decision**: Meeting session sẽ tích lũy final words trong memory. Chỉ khi có
`utterance_end`, session mới đóng utterance, build `messages[]`, persist Mongo,
và emit `meeting:utterance_closed`.

**Alternatives considered:**
- **Persist mỗi `speech_final`**: gần realtime hơn nhưng dễ cắt vụn transcript
  trong một câu nói dài
- **Persist theo timer application-side riêng**: thêm heuristic không cần thiết
  khi provider đã có `utterance_end`

**Rationale**: User đã chốt rõ “record chỉ tạo khi `utterance_end` từ
Deepgram”. `speech_final` vẫn hữu ích để emit `meeting:final`, nhưng không phải
mốc bền vững cuối cùng cho durable storage.

### D6: `meeting:final` là event realtime cho final fragment, còn `meeting_utterance` là record canonical

**Decision**: Có hai lớp output khác nhau:

- `meeting:final`: stream final fragment về frontend để hiển thị realtime
- `meeting:utterance_closed`: gửi canonical payload đã group speaker theo
  `messages[]`

**Alternatives considered:**
- **Chỉ phát utterance_closed**: UI chậm hơn và mất cảm giác realtime
- **Dùng final fragment làm durable record luôn**: không khớp business rule
  persist tại `utterance_end`

**Rationale**: Điều này tách rõ “preview ổn định ngắn hạn cho UI” với “record
chuẩn để lưu trữ”. Frontend có thể hiển thị ngay final fragment, rồi commit bản
canonical khi utterance đóng.

### D7: `meeting_utterance` chỉ lưu `messages[]` đã chuẩn hóa, không lưu transcript phẳng hay raw words

**Decision**: Record bền vững của `meeting_utterance` sẽ tối thiểu gồm:

- `_id`
- `meeting_id`
- `sequence`
- `messages[]`
- `created_at`

Trong đó mỗi message gồm:

- `speaker_index`
- `speaker_label`
- `text`

**Alternatives considered:**
- **Lưu thêm `transcript` phẳng ở mức utterance**: dư thừa với `messages[]`
  và user đã yêu cầu bỏ
- **Lưu raw `words[]` bền vững**: thuận tiện cho reprocessing nhưng tăng kích
  thước document và đi ngược requirement hiện tại
- **Lưu timing/confidence**: hữu ích cho analytics sau này nhưng hiện tại bị coi
  là noise

**Rationale**: Product contract đang tối ưu cho dữ liệu tối thiểu đủ để render
speaker transcript. Nếu sau này cần analytics hoặc re-segmentation, có thể mở
spec riêng thay vì giữ dữ liệu thừa ngay từ phase đầu.

### D8: Dùng grouping word liên tiếp theo speaker để build messages

**Decision**: Sau khi một utterance đóng, backend sẽ duyệt final words theo thứ
tự thời gian và gộp các word liên tiếp có cùng `speaker` thành một message.

**Thuật toán:**
1. lấy danh sách final words của utterance theo thứ tự đã finalize
2. bỏ các word rỗng sau normalize
3. nếu speaker của word hiện tại trùng speaker của message đang mở thì append
4. nếu speaker đổi thì đóng message hiện tại và mở message mới
5. map `speaker_index=0` -> `speaker_label="speaker_1"` theo quy ước 1-based ở UI

**Alternatives considered:**
- **Một utterance chỉ có một speaker**: không đúng với mixed audio có xen lời
- **Tách message theo dấu câu thay vì speaker**: không phản ánh requirement
  speaker-aware

**Rationale**: Deepgram live diarization gắn speaker ở mức word. Grouping theo
speaker liên tiếp là phép biến đổi đơn giản nhất khớp với output product mong
muốn.

### D9: Sequence là ordering key chính của meeting_utterances

**Decision**: Vì user không muốn lưu `started_at`, `ended_at`, `turn_closed_at`
trong `meeting_utterance`, backend sẽ gán `sequence` tăng dần theo từng meeting.

**Alternatives considered:**
- **Sort bằng timestamp của record**: dễ bị phụ thuộc clock và race condition
  khi có async path về sau
- **Không có ordering key riêng**: frontend/repo khó truy vấn ổn định

**Rationale**: `sequence` là đủ để giữ thứ tự business của utterance mà không
cần giữ timing metadata chi tiết trong durable model.

**Quy tắc cấp số:**
- mỗi meeting bắt đầu với `sequence=1`
- mỗi utterance persist thành công tăng thêm 1
- sequence được quản lý trong session memory và ghi bền vững cùng utterance

### D10: Meeting có trạng thái terminal phân biệt `completed`, `interrupted`, `failed`

**Decision**: Meeting lifecycle sẽ dùng các trạng thái chính:

- `streaming`
- `finalizing`
- `completed`
- `interrupted`
- `failed`

**Semantics:**
- `completed`: kết thúc chủ động qua `meeting:finalize` hoặc `meeting:stop` sau
  khi đã flush sạch provider
- `interrupted`: socket disconnect khi session còn hoạt động; backend đã cố
  gắng finalize nhưng kết thúc không được coi là sạch
- `failed`: lỗi input/provider/internal khiến session không thể tiếp tục

**Rationale**: Trạng thái `interrupted` là quan trọng vì disconnect được xem là
end session, nhưng khác với một phiên hoàn tất chủ động.

### D11: Disconnect phải thử finalize trước khi cleanup

**Decision**: Khi socket disconnect, meeting session sẽ:

1. chuyển sang chế độ đóng phiên
2. gọi `Finalize` sang Deepgram
3. drain các final events còn pending trong một grace window ngắn
4. nếu còn buffer hợp lệ thì build và persist utterance cuối
5. đóng provider connection
6. đánh dấu meeting là `interrupted`

**Alternatives considered:**
- **Đóng thẳng provider khi disconnect**: đơn giản hơn nhưng dễ mất final words
  cuối
- **Cố resume sau reconnect**: ngoài scope

**Rationale**: User đã đồng ý với hướng “disconnect thì xử lý như vậy”. Đây là
điểm khác biệt intentional so với flow interview hiện tại.

### D12: Data model và indexing phải tối ưu cho truy vấn theo meeting

**Decision**: Thêm hai collection mới:

**Meeting**

```json
{
  "_id": "string",
  "organization_id": "string",
  "created_by": "string",
  "title": "string|null",
  "source": "google_meet",
  "provider": "deepgram",
  "status": "streaming|finalizing|completed|interrupted|failed",
  "language": "string|null",
  "stream_id": "string",
  "started_at": "datetime",
  "ended_at": "datetime|null",
  "error_message": "string|null"
}
```

**MeetingUtterance**

```json
{
  "_id": "string",
  "meeting_id": "string",
  "sequence": 1,
  "messages": [
    {
      "speaker_index": 0,
      "speaker_label": "speaker_1",
      "text": "string"
    }
  ],
  "created_at": "datetime"
}
```

**Index đề xuất:**
- `meetings`: `(organization_id, started_at desc)`
- `meetings`: `(created_by, organization_id, started_at desc)`
- `meetings`: `(status, started_at desc)`
- `meeting_utterances`: `(meeting_id, sequence asc)` unique trong phạm vi meeting

**Rationale**: Mọi query thực tế đều xoay quanh timeline của một meeting hoặc
danh sách meeting theo org/user.

### D13: Service/repo wiring mới phải giữ biên giới rõ giữa meeting và interview

**Decision**: Tạo service factory và repository riêng cho meeting thay vì reuse
`interview_*_repo` hoặc `STTService`.

**File structure đề xuất:**

```text
app/
├── domain/models/
│   ├── meeting.py
│   └── meeting_utterance.py
├── domain/schemas/
│   └── meeting.py
├── repo/
│   ├── meeting_repo.py
│   └── meeting_utterance_repo.py
├── services/meeting/
│   ├── session.py
│   ├── session_manager.py
│   └── meeting_service.py
├── infrastructure/deepgram/
│   └── client.py
├── socket_gateway/
│   └── server.py
└── common/
    ├── event_socket.py
    └── service.py
```

**Rationale**: Ranh giới này giúp team không vô tình gắn requirement meeting
vào interview stack và ngược lại.

## Risks / Trade-offs

**[Diarization trên audio trộn có thể đổi speaker sai ở một số đoạn]** ->
Mitigation: chỉ nhóm trên final words, không nhóm trên partial; giữ event
`meeting:final` và `meeting:utterance_closed` tách biệt để UI có canonical state
sau cùng.

**[Không lưu raw words làm mất khả năng reprocess về sau]** -> Mitigation: chấp
nhận trade-off cho phase 1; nếu cần analytics/debug sâu hơn sẽ mở capability
mới để lưu raw transcript payload hoặc export provider result.

**[`utterance_end` không đồng nghĩa tuyệt đối với “ý đã nói xong”]** ->
Mitigation: đây là business rule đã được user chốt. Thiết kế không thêm grace
heuristic mới để tránh lệch requirement.

**[Sequence chỉ được quản lý trong session memory]** -> Mitigation: mỗi socket
chỉ có một session meeting hoạt động và reconnect không resume, nên sequence
memory-local là chấp nhận được trong phase 1.

**[Mở rộng adapter Deepgram có thể regression interview nếu sửa sai default]** ->
Mitigation: chỉ thêm field optional và config factory riêng cho meeting; không
đổi default runtime config interview đang dùng.

**[Disconnect finalize có thể không flush hết nếu provider/network đã chết]** ->
Mitigation: đánh dấu `interrupted` thay vì `completed`, persist phần cuối chỉ
khi buffer còn đủ final data hợp lệ, và ghi log rõ để quan sát.

**[Session state vẫn process-local nên scale ngang cần sticky session]** ->
Mitigation: chấp nhận trong phase 1 và ghi rõ ràng trong ghi chú vận hành.

## Migration Plan

1. Thêm event constants và schema payload cho namespace `meeting:*`
2. Thêm model/repo/index cho `meetings` và `meeting_utterances`
3. Mở rộng Deepgram adapter để normalize được word-level diarization theo hướng
   additive
4. Tạo `MeetingSession`, `MeetingSessionManager`, và `MeetingService`
5. Đăng ký Socket.IO handlers cho `meeting:start`, `meeting:audio`,
   `meeting:finalize`, `meeting:stop`
6. Thêm lifecycle xử lý disconnect theo hướng `Finalize -> drain -> persist cuối -> interrupted`
7. Verify end-to-end với audio contract hiện đang dùng ở interview flow nhưng
   cấu hình `1-channel`

**Rollback**
- disable meeting socket events
- bỏ service wiring mới của meeting
- giữ nguyên interview flow và adapter additive fields chưa được sử dụng
- dữ liệu `meetings`/`meeting_utterances` đã ghi có thể để nguyên vì là additive

## Open Questions

- Có cần expose REST endpoint để list/detail meeting transcript ngay trong phase
  implementation đầu tiên hay chỉ cần hoàn tất realtime + persistence trước?
- Có cần cho phép update title sau khi meeting đã tạo ở cùng change này hay để
  capability sau xử lý?
