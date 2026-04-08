## ADDED Requirements

### Requirement: Lead agent có thể ủy quyền công việc phức tạp cho worker agents
Hệ thống SHALL cho phép lead agent quyết định theo từng turn xem nên trả lời
trực tiếp hay ủy quyền công việc phức tạp cho một hoặc nhiều worker agents
thông qua một cơ chế delegation nội bộ. Lead agent SHALL tiếp tục là agent duy
nhất tạo ra phản hồi cuối cùng hiển thị cho user trong conversation.

#### Scenario: Lead agent tự xử lý công việc đơn giản
- **WHEN** một lead-agent turn không cần phân rã thành các subtasks
- **THEN** lead agent hoàn tất turn đó mà không gọi worker agents

#### Scenario: Lead agent ủy quyền công việc phức tạp
- **WHEN** một lead-agent turn cần xử lý nhiều bước hoặc nhiều góc nhìn và
  subagent orchestration theo turn được bật
- **THEN** lead agent gọi cơ chế delegation nội bộ
- **AND** delegated work được thực thi thông qua một hoặc nhiều worker agents
- **AND** lead agent vẫn chịu trách nhiệm tổng hợp phản hồi cuối cùng

### Requirement: Worker agents chạy trong các context tách biệt
Mỗi worker agent SHALL chạy trong một runtime context tách biệt với context
của parent lead-agent. Worker runtime SHALL chỉ nhận delegated task
instructions, trusted runtime scope, và các input được chỉ định rõ cần thiết
cho delegated task đó.

#### Scenario: Worker nhận delegated task thay vì toàn bộ parent history
- **WHEN** lead agent ủy quyền một task cho worker agent
- **THEN** worker bắt đầu với execution context riêng, sạch
- **AND** worker không thừa hưởng toàn bộ parent conversation transcript
- **AND** worker nhận delegated task description cùng trusted caller scope cần
  thiết để hoàn thành task đó

#### Scenario: Parent context vẫn gọn sau khi worker hoàn thành
- **WHEN** một worker agent hoàn thành delegated task
- **THEN** lead agent nhận delegated result cuối cùng từ worker
- **AND** parent context không cần giữ toàn bộ intermediate tool trace của
  worker để tiếp tục turn đó

### Requirement: Delegated workers có thể chạy song song
Hệ thống SHALL hỗ trợ chạy song song nhiều worker agents cho cùng một
lead-agent turn khi các delegated subtasks là độc lập.

#### Scenario: Lead agent ủy quyền nhiều research tasks độc lập
- **WHEN** lead agent phân rã một request phức tạp thành nhiều subtasks độc
  lập
- **THEN** hệ thống có thể thực thi các worker tasks đó đồng thời
- **AND** hệ thống thu thập kết quả của từng worker trước khi lead agent tổng
  hợp phản hồi cuối cùng

### Requirement: Delegation bị ràng buộc bởi backend guardrails
Hệ thống SHALL enforce backend guardrails cho subagent orchestration, bao gồm
maximum delegation depth và trusted worker execution boundaries. Ở phiên bản
đầu tiên, worker agents MUST NOT được phép spawn thêm worker agents khác.

#### Scenario: Worker không thể ủy quyền đệ quy
- **WHEN** một worker agent đang thực thi delegated task
- **THEN** cơ chế delegation không khả dụng để spawn thêm một worker layer
- **AND** execution hiện tại vẫn bị chặn trong maximum depth đã cấu hình

#### Scenario: Delegation tuân thủ các backend limits
- **WHEN** lead agent cố gắng ủy quyền công việc cho một turn
- **THEN** hệ thống áp dụng các delegation limits đã cấu hình như allowed
  depth, worker concurrency, và worker execution boundaries trước hoặc trong
  lúc thực thi

### Requirement: Worker completion chỉ trả về kết quả ngắn gọn cho lead agent
Worker agents SHALL trả về các task results ngắn gọn, phù hợp để lead agent
tổng hợp, thay vì raw execution traces hoặc unbounded intermediate output.

#### Scenario: Worker trả về synthesis-ready summary
- **WHEN** một worker agent hoàn thành delegated task thành công
- **THEN** worker trả về một delegated result ngắn gọn cho lead agent
- **AND** kết quả đó phù hợp để được tổng hợp trực tiếp vào final answer

#### Scenario: Worker failure trả về bounded error outcome
- **WHEN** một worker agent không thể hoàn thành delegated task
- **THEN** worker trả về một failure result có giới hạn cho lead agent
- **AND** lead agent có thể tiếp tục turn bằng cách retry, dùng các worker
  results khác, hoặc phản hồi mà không có đóng góp của worker đó
