## MODIFIED Requirements

### Requirement: Lead-agent state mở rộng từ AgentState
Lead-agent runtime SHALL định nghĩa state schema của nó bằng cách mở rộng
`AgentState`. Custom state SHALL hỗ trợ thread-scoped metadata cần cho
backend, bao gồm `user_id` và `organization_id` tùy chọn, SHALL đồng thời hỗ
trợ skill-related runtime metadata để giữ được skill-aware execution qua nhiều
turns, bao gồm enabled skills, active skill identity, loaded skill history, và
skill-scoped tool availability, SHALL hỗ trợ planning metadata để giữ được
checkpoint-backed todo state qua nhiều turns, và SHALL hỗ trợ delegation-related
runtime metadata cần cho subagent orchestration, bao gồm orchestration mode
theo turn, delegation depth, và parent-worker execution tracking.

#### Scenario: Tạo lead-agent với state model hỗ trợ skill, planning, và delegation
- **WHEN** lead-agent runtime được khởi tạo
- **THEN** agent được tạo với một state schema mở rộng từ `AgentState`
- **AND** runtime state model có thể biểu diễn caller scope, skill-related
  execution metadata, planning state, và delegation-related metadata cho cùng
  một thread

#### Scenario: Runtime metadata khả dụng trong thread state
- **WHEN** hệ thống invoke lead agent cho một authenticated user
- **THEN** thread state bao gồm `user_id` của requester
- **AND** thread state bao gồm `organization_id` khi giá trị này được cung cấp
- **AND** thread state có thể giữ lại skill-related execution metadata,
  planning metadata, và delegation-related metadata mà runtime cần cho thread
  đó

### Requirement: Lead-agent send-message endpoint dùng conversation handles
Hệ thống SHALL cung cấp endpoint xác thực `POST /lead-agent/messages` nhận
`content`, `conversation_id` tùy chọn, và optional turn-scoped subagent
orchestration input. Client MUST NOT bị yêu cầu phải cung cấp trực tiếp
`thread_id` cho việc gửi message lead-agent thông thường.

#### Scenario: Message đầu tiên tạo conversation và thread
- **WHEN** một authenticated client gửi lead-agent message mà không có
  `conversation_id`
- **THEN** hệ thống tạo một `conversation` ở tầng ứng dụng
- **AND** hệ thống tạo một LangGraph `thread_id` mới
- **AND** hệ thống gắn `thread_id` đó với conversation vừa tạo
- **AND** hệ thống persist user message
- **AND** hệ thống trả về `conversation_id` và `user_message_id` đã tạo

#### Scenario: Message tiếp theo tái sử dụng thread theo conversation
- **WHEN** một authenticated client gửi lead-agent message với
  `conversation_id` hợp lệ
- **THEN** hệ thống load conversation đó
- **AND** hệ thống tái sử dụng `thread_id` đã lưu của conversation
- **AND** hệ thống persist user message mới trước khi background runtime
  execution bắt đầu

#### Scenario: Chấp nhận subagent mode theo turn mà không đổi conversation entry point
- **WHEN** một authenticated client gửi lead-agent message với
  turn-scoped subagent orchestration được bật
- **THEN** hệ thống chấp nhận input đó trên chính endpoint
  `POST /lead-agent/messages` hiện có
- **AND** hệ thống chỉ áp dụng orchestration mode đã gửi cho đúng turn
  lead-agent đó

#### Scenario: Từ chối các conversation handles không hợp lệ hoặc không thuộc lead-agent
- **WHEN** một authenticated client gửi lead-agent message với
  `conversation_id` không tồn tại
- **OR** với một conversation nằm ngoài caller scope
- **OR** với một conversation không được map tới `thread_id` của lead-agent
- **THEN** hệ thống từ chối request bằng một not-found style error phù hợp

### Requirement: Lead-agent runtime hỗ trợ skill-aware tool registration
Lead-agent runtime SHALL đăng ký các internal tools cần cho skill discovery,
planning-aware execution, và subagent orchestration. Runtime MAY đăng ký thêm
các domain tools khác, nhưng MUST chỉ expose đúng tập tool được phép theo
current skill context, caller scope, và delegation boundary cho mỗi model call.

#### Scenario: Runtime bao gồm các internal coordination tools
- **WHEN** lead-agent runtime được khởi tạo cho skill-aware và
  orchestration-aware execution
- **THEN** runtime đăng ký internal tool surface cần thiết để discover hoặc
  load skills, giữ planning state, và delegate work trong một turn

#### Scenario: Runtime chỉ expose các tools được phép cho một model call
- **WHEN** lead-agent runtime chuẩn bị một model call bên trong thread
- **THEN** runtime chỉ expose các tools được current skill context, caller
  scope, và delegation boundary cho phép ở model call đó

#### Scenario: Worker runtime không expose recursive delegation tools
- **WHEN** runtime chuẩn bị model call cho một delegated worker execution
- **THEN** tool surface không bao gồm recursive delegation capability
- **AND** worker vẫn bị giới hạn bởi maximum delegation depth đã cấu hình

### Requirement: Lead-agent runtime hỗ trợ custom middleware cho skill-aware execution
Lead-agent runtime SHALL dùng custom middleware layers để hỗ trợ skill-aware
execution, todo-based planning, và subagent orchestration. Middleware MUST có
thể inject available skill summaries vào runtime context, gắn lead-agent
planning instructions và planning tool surface, chuyển lead agent sang hành vi
orchestration khi turn-scoped subagent mode được bật, và áp dụng dynamic tool
selection trước mỗi model call.

#### Scenario: Runtime inject discoverable skill context và orchestration guidance trước khi model reasoning
- **WHEN** lead-agent runtime chuẩn bị model call cho một caller có enabled
  skills và có bật turn-scoped subagent orchestration
- **THEN** middleware inject available skill summaries vào runtime context
  trước khi model reasoning cho turn đó
- **AND** middleware vẫn giữ planning guidance cần thiết cho todo-based
  execution ở model call đó
- **AND** middleware áp dụng orchestration guidance để lead agent có thể quyết
  định giữa việc trả lời trực tiếp hoặc delegate work

#### Scenario: Runtime đánh giá lại tool exposure sau khi skill, planning, hoặc delegation context thay đổi
- **WHEN** current thread state làm thay đổi active skill, allowed tool set,
  persisted planning context, hoặc delegation context trong lúc execution
- **THEN** middleware áp dụng updated tool exposure rules trước model call kế
  tiếp
- **AND** trusted runtime coordination tools bắt buộc theo backend policy vẫn
  khả dụng ở model call đó

### Requirement: Lead-agent responses stream qua chat socket contract hiện có
Lead-agent message processing SHALL stream realtime progress và completion tới
client bằng cách tái sử dụng chat socket namespace hiện có theo
`conversation_id`. Ngoài các events started, token, tool, completed, và failed
đang tồn tại, lead-agent runtime SHALL tiếp tục emit dedicated plan update
event khi persisted todo snapshot thay đổi và SHALL expose delegated tool
activity qua existing tool event contract.

#### Scenario: Lead-agent response bắt đầu sau khi message submission trả về
- **WHEN** hệ thống chấp nhận một request `POST /lead-agent/messages` hợp lệ
- **THEN** HTTP response được trả về mà không chờ final assistant text
- **AND** lead-agent response processing tiếp tục chạy bất đồng bộ ở background
- **AND** hệ thống emit existing started event cho `conversation_id` đó

#### Scenario: Lead-agent response emit token và completion events
- **WHEN** lead-agent runtime sinh ra streamed assistant response cho một
  persisted lead-agent conversation
- **THEN** hệ thống emit token events bằng existing chat socket event names và
  payload shape theo `conversation_id`
- **AND** hệ thống emit existing completed event sau khi final assistant
  message đã được persist

#### Scenario: Delegated execution đi qua existing tool events
- **WHEN** lead agent gọi internal delegation trong một turn
- **THEN** hệ thống emit existing tool start và tool end events cho bước
  delegated coordination đó
- **AND** delegated execution vẫn quan sát được qua cùng conversation-scoped
  socket stream

#### Scenario: Lead-agent response emit persisted plan update events
- **WHEN** một lead-agent turn persist một todo snapshot đã thay đổi trong lúc
  execution
- **THEN** hệ thống emit dedicated plan update event theo `conversation_id`
- **AND** event payload phản ánh latest persisted todo snapshot của
  conversation đó

#### Scenario: Lead-agent runtime failure emit existing failed event
- **WHEN** background lead-agent processing thất bại sau khi message đã được
  chấp nhận
- **THEN** hệ thống emit existing failed event theo `conversation_id`

## ADDED Requirements

### Requirement: Lead-agent assistant metadata lưu delegated execution
Hệ thống SHALL persist delegation-related metadata cùng với final assistant
message của một lead-agent turn khi subagent orchestration được thực thi.

#### Scenario: Final assistant message ghi lại delegated coordination metadata
- **WHEN** một lead-agent turn sử dụng một hoặc nhiều worker agents
- **THEN** persisted assistant metadata ghi lại delegated coordination activity
  của turn đó
- **AND** metadata này vẫn được gắn với cùng conversation và message
  projection mà frontend đang dùng
