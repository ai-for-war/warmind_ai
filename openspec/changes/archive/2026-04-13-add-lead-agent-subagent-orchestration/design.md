## Context

Runtime `lead_agent` hiện tại đã có đủ các điểm mở kiến trúc để thêm
subagent orchestration mà không cần tạo một runtime user-facing thứ hai:

- `create_lead_agent()` tạo một runtime `create_agent(...)` được cache, có
  tool registration, middleware, và MongoDB-backed LangGraph checkpointer
- `LeadAgentService` đang quản lý conversation validation, message
  persistence, background execution, checkpoint access, và socket event
  emission
- checkpointed thread state đã là source of truth của runtime, còn
  conversation và message records chỉ đóng vai trò projection cho frontend
- skill-aware execution và planning đã tồn tại thông qua middleware và các
  internal coordination tools

Thành phần còn thiếu là một lớp manager-worker có kiểm soát để lead agent chỉ
giữ context của phần lập kế hoạch và tổng hợp, còn các worker xử lý những
subtasks nặng trong các context tách biệt.

Các quyết định sản phẩm đã được chốt cho change này:

- subagent orchestration được bật theo từng turn, không phải một runtime riêng
- `POST /lead-agent/messages` hiện có vẫn là frontend contract duy nhất
- lead agent vẫn là agent duy nhất trả lời user
- worker agents được phép tái sử dụng cùng kiểu runtime/factory như lead agent
- delegation depth bị giới hạn ở một lớp worker trong phiên bản đầu tiên

Ràng buộc và thực tế từ codebase hiện tại:

- `LeadAgentService` cache compiled runtime, nên thiết kế không nên phụ thuộc
  vào việc compile runtime theo từng user hoặc từng thread
- socket contract hiện tại đã expose tool lifecycle events theo
  `conversation_id`, đây nên tiếp tục là kênh observability chính
- thread state là dữ liệu bền vững, nhưng orchestration mode theo turn không
  được rò rỉ sai sang các turn tiếp theo
- worker runs cần trusted caller scope và enabled skills, nhưng không nên thừa
  hưởng toàn bộ transcript của parent conversation

## Goals / Non-Goals

**Goals:**
- Thêm lớp manager-worker orchestration cho lead agent mà không tạo public
  runtime mới hoặc thay đổi API conversation-first hiện tại
- Cho phép một turn của lead agent tự quyết định giữa direct execution và
  delegated execution dựa trên độ phức tạp của task
- Giữ worker execution tách biệt để delegated work không làm phình context của
  parent thread
- Hỗ trợ chạy song song các worker tasks độc lập
- Giữ nguyên socket streaming, conversation history, và checkpoint-based
  runtime semantics hiện có
- Enforce backend guardrails cho recursion depth, worker visibility, và sự an
  toàn của delegated execution
- Persist đủ delegation metadata để phục vụ debugging, evaluation, và các cải
  tiến UI trong tương lai

**Non-Goals:**
- Không giới thiệu mô hình peer-to-peer handoff nơi worker agents nói chuyện
  trực tiếp với user
- Không cho phép worker spawn đệ quy ở phiên bản đầu tiên
- Không xây dựng scheduler, queueing subsystem, hoặc worker service riêng cho
  v1
- Không thêm UI ở frontend cho việc chọn worker profiles hay xem raw worker
  transcripts
- Không ép buộc mọi turn phù hợp đều phải dùng subagents; lead agent vẫn có
  thể tự xử lý
- Không redesign runtime sang specialist graphs ở mức node của LangGraph trong
  phase này

## Decisions

### D1: Dùng manager-worker orchestration bên trong runtime hiện có của lead-agent

**Decision**: Hệ thống sẽ giữ một runtime lead-agent làm manager duy nhất ở
user-facing layer. Hành vi subagent sẽ được thêm như một capability nội bộ,
được gọi qua một delegation tool tin cậy thay vì tạo API thứ hai hoặc mô hình
peer handoff.

Recommended shape:

- parent runtime: `create_lead_agent(...)` hiện tại
- internal delegation tool: `delegate_tasks`
- worker runtime: delegated agent invocation với worker-specific prompt và
  bounded tool visibility

**Rationale**:
- runtime hiện tại đã sở hữu thread state, conversation projection, và socket
  streaming nên manager pattern là kiến trúc ít phá vỡ nhất
- yêu cầu sản phẩm chốt rõ rằng lead agent là actor duy nhất user nhìn thấy
- manager-worker khớp trực tiếp với nhu cầu "lead agent điều phối và chỉ nhận
  kết quả cuối từ worker"

**Alternatives considered:**
- **Peer handoff topology**: loại bỏ vì chuyển quyền điều khiển khỏi lead agent
  và không khớp yêu cầu rằng một agent duy nhất phải là bên tổng hợp cuối cùng
- **Separate orchestration service**: loại bỏ ở v1 vì làm tăng độ phức tạp
  triển khai trước khi xác thực hành vi runtime

### D2: Mô hình hóa subagent execution như một internal tool có input có cấu trúc

**Decision**: Delegation sẽ được expose cho lead agent thông qua một internal
tool tin cậy, tạm gọi là `delegate_tasks`, thay vì rẽ nhánh đặc biệt trong
service layer bên ngoài model loop.

Recommended tool contract:

- input: danh sách delegated tasks với task objective, optional expected
  output, và optional skill/tool hints
- behavior: spawn một worker run cho mỗi task, chạy concurrent khi phù hợp,
  aggregate results, và trả về một summary payload có giới hạn
- output: danh sách ngắn gọn các worker outcomes cùng aggregate status metadata

**Rationale**:
- tool là primitive orchestration tự nhiên mà runtime hiện tại đã dùng
- giữ delegation bên trong model loop giúp lead agent tự quyết định khi nào
  delegation đáng với chi phí tăng thêm
- delegated execution sẽ tự động đi qua tool start/end socket contract hiện có

**Alternatives considered:**
- **Hardcode delegation trong `LeadAgentService` trước runtime invocation**:
  loại bỏ vì sẽ bỏ qua model reasoning và làm task decomposition kém linh hoạt
- **Inject workers trực tiếp bằng middleware mà không có tool call**: loại bỏ
  vì explicit tool invocation dễ trace, test, và constrain hơn

### D3: Giữ orchestration mode ở mức turn và inject qua runtime payload

**Decision**: `subagent_enabled` sẽ được coi là input runtime theo từng turn.
`LeadAgentService` sẽ truyền giá trị này vào runtime payload và message
metadata cho turn cụ thể, thay vì biến nó thành thread mode cố định.

Recommended model:

- API request nhận optional `subagent_enabled`
- `LeadAgentService.send_message(...)` persist turn với input này
- `_build_runtime_payload(...)` inject orchestration mode vào state cho run
  hiện tại
- middleware đọc giá trị đó và áp dụng orchestration prompt/tool policy cho
  model call tương ứng

**Rationale**:
- khớp với quyết định sản phẩm là orchestration theo message
- tránh việc tách một conversation thành nhiều runtime types
- ngăn stale thread state ép orchestration ở các turn sau vốn không bật cờ này

**Alternatives considered:**
- **Persist orchestration mode như một thread-level setting**: loại bỏ vì mâu
  thuẫn với hành vi per-turn đã chọn
- **Compile hai runtime khác nhau và chọn theo request**: loại bỏ vì runtime
  hiện tại đã dùng middleware/state cho dynamic behavior và compiled-runtime
  cache nên giữ đơn giản

### D4: Tái sử dụng lead-agent factory cho worker nhưng áp dụng worker-specific prompt và guardrails

**Decision**: Worker agents sẽ tái sử dụng cùng kiểu agent construction pattern
và runtime services như lead agent, nhưng chạy với worker-specific prompt và
bị giới hạn coordination surface.

Worker policy:

- worker chỉ nhận delegated task cộng trusted scope
- worker có thể dùng runtime tools và skills bình thường nếu task đó được phép
- worker không được hỏi clarification trực tiếp từ user
- worker không được spawn thêm worker khác
- worker phải trả về output có giới hạn, sẵn sàng cho bước synthesis thay vì
  raw traces

**Rationale**:
- tái sử dụng factory và runtime helpers hiện có giúp giảm rủi ro
  implementation
- đáp ứng lựa chọn "full lead clone" ở mức hạ tầng nhưng vẫn enforce hành vi
  an toàn ở mức sản phẩm
- worker-specific prompt policy rẻ hơn việc xây một worker framework riêng

**Alternatives considered:**
- **Tạo worker agent implementation hoàn toàn khác**: loại bỏ ở v1 vì lặp lại
  logic runtime quá sớm
- **Cho worker thừa hưởng đúng hệt prompt và tools của lead mà không đổi
  policy**: loại bỏ vì sẽ mở đường cho recursion, clarification loop với user,
  và context sprawl

### D5: Cô lập worker context và chỉ trả về final worker results ngắn gọn

**Decision**: Mỗi worker run sẽ bắt đầu với fresh context và chỉ nhận delegated
task input, trusted caller scope, enabled skills, cùng các constraints cần
thiết để hoàn thành task. Parent thread chỉ giữ delegation tool call và bounded
result mà worker executor trả về.

Recommended flow:

1. lead agent gọi `delegate_tasks`
2. tool tạo worker execution payloads
3. từng worker chạy trong context tách biệt
4. worker tool traces chỉ tồn tại cục bộ trong worker run
5. tool trả về final worker summaries và aggregate status

**Rationale**:
- vấn đề chính cần giải là context bloat của parent thread
- worker isolation giữ các task nặng về search/tool không làm bẩn lead thread
- output có giới hạn giúp bước tổng hợp cuối rẻ hơn và dễ hơn cho parent model

**Alternatives considered:**
- **Truyền toàn bộ parent history cho mọi worker**: loại bỏ vì triệt tiêu mục
  tiêu isolation
- **Persist toàn bộ worker trace ngược lại parent messages**: loại bỏ vì tái
  tạo lại chính bài toán context ở một hình thức khác

### D6: Chạy worker song song bên trong delegation tool

**Decision**: Parallel execution sẽ nằm trong implementation của delegation
tool bằng asynchronous concurrency cho các tasks độc lập.

Recommended model:

- task decomposition do lead agent quyết định
- execution của các task đó được runtime thực thi bằng `asyncio.gather(...)`
  hoặc cơ chế async fan-out tương đương nhưng có giới hạn
- bước aggregate chờ tất cả workers hoặc timeout/failure boundaries rồi trả về
  một payload kết quả cho lead agent

**Rationale**:
- concurrency thuộc responsibility của tool executor, không phải prompt
  composition
- giữ lead agent reasoning gọn nhưng vẫn giảm latency cho các tasks nghiên cứu
  độc lập
- bounded parallelism có thể được enforce tập trung ở một chỗ

**Alternatives considered:**
- **Chỉ chạy tuần tự**: loại bỏ vì các tasks độc lập như nghiên cứu đa góc nhìn
  sẽ chịu latency không cần thiết
- **Fan-out không giới hạn**: loại bỏ vì tạo rủi ro lớn về cost và reliability

### D7: Enforce depth, visibility, và execution limits bằng middleware và executor policy

**Decision**: Guardrails sẽ được enforce ở hai lớp:

- middleware/tool selection layer: quyết định tools nào hiện ra với parent và
  worker runs
- delegation executor layer: enforce max depth, max parallel workers,
  timeouts, và bounded error handling

Recommended runtime additions:

- `subagent_enabled`
- `delegation_depth`
- `delegation_parent_run_id`
- optional worker execution counters hoặc limits metadata

Recommended policy:

- lead agent chỉ thấy `delegate_tasks` khi `subagent_enabled=true`
- worker runs luôn chạy với `delegation_depth=1`
- worker-visible tools không bao gồm `delegate_tasks`
- worker failures được chuyển thành bounded per-task outcomes thay vì làm crash
  toàn bộ turn theo mặc định

**Rationale**:
- middleware đã là cơ chế dynamic visibility của runtime hiện có
- executor-layer limits vẫn cần thiết vì prompt-only restrictions là không đủ
- thiết kế này giữ được kiểu runtime "full lead clone" nhưng vẫn enforce safety
  ở mức sản phẩm

**Alternatives considered:**
- **Chỉ kiểm soát recursion bằng prompt**: loại bỏ vì policy không nên phụ
  thuộc hoàn toàn vào việc model nghe lời
- **Chỉ validate ở service mà không đổi tool visibility**: loại bỏ vì model
  không nên nhìn thấy những tools mà nó không được phép dùng

### D8: Tái sử dụng socket/tool telemetry hiện có và mở rộng assistant metadata theo kiểu additive

**Decision**: Delegated execution sẽ tái sử dụng existing tool lifecycle socket
events và mở rộng final assistant metadata với các fields liên quan đến
delegation thay vì tạo một worker event channel riêng ở v1.

Recommended telemetry model:

- `delegate_tasks` xuất hiện như một internal tool start/end pair bình thường
- result payload chứa bounded worker status summary
- assistant metadata có thể thêm các fields như delegated task count, worker
  outcomes, hoặc delegation depth

**Rationale**:
- frontend contract hiện tại đã hiểu tool lifecycle events
- additive metadata là đủ cho debugging và evaluation mà chưa cần thiết kế
  transport contract mới
- rollout vẫn backward-compatible cho các client chưa biết chi tiết về
  subagent

**Alternatives considered:**
- **Dedicated worker socket events**: loại bỏ ở v1 vì yêu cầu hiện tại là
  observability, không phải UI full worker-trace
- **Không persist delegation metadata**: loại bỏ vì debugging và evals sẽ quá
  yếu cho một runtime phức tạp hơn

## Risks / Trade-offs

- **[Worker output quá dài và làm bẩn parent context]** → Mitigation: enforce
  worker prompt rules cho output ngắn gọn và truncate hoặc summarize kết quả ở
  delegation executor trước khi trả về
- **[Per-turn orchestration mode bị rò sang các turn sau]** → Mitigation:
  inject orchestration mode từ request hiện tại vào runtime payload và không
  coi nó là permanent thread mode
- **[Full lead clone workers tái tạo hành vi không an toàn như recursion hoặc
  clarification loop với user]** → Mitigation: ẩn delegation tools khỏi worker
  runs, dùng worker-specific prompt rules, và enforce depth ở executor policy
- **[Parallel fan-out làm tăng token cost mạnh]** → Mitigation: đặt backend
  limits cho số task và chỉ dùng delegation cho các request thực sự phức tạp
- **[Worker failures làm parent behavior trở nên mong manh]** → Mitigation:
  trả về bounded per-worker failure outcomes để lead agent có thể tổng hợp kết
  quả từng phần
- **[Runtime metadata nhiều hơn làm state evolution phức tạp]** → Mitigation:
  giữ các additions ở dạng additive và chỉ lưu semantics liên quan đến
  delegation, không lưu raw worker traces vào checkpoint state
- **[Tool filtering hiện có làm orchestration hoặc worker restrictions bị sai]**
  → Mitigation: thêm integration tests cho parent/worker tool visibility và
  depth boundaries

## Migration Plan

1. Thêm support ở schema và runtime state cho orchestration input theo turn và
   delegation metadata.
2. Bổ sung orchestration prompt và middleware behavior trong khi vẫn giữ
   behavior hiện tại nếu `subagent_enabled` không có hoặc bằng `false`.
3. Thêm internal `delegate_tasks` tool và worker executor với guardrail
   `depth=1`.
4. Mở rộng assistant metadata và tool-result serialization cho delegated
   execution observability.
5. Rollout sau cờ request hiện có để các turn không bật orchestration vẫn tiếp
   tục dùng single-agent path như cũ.

Rollback strategy:

- tắt hoặc bỏ qua `subagent_enabled` ở request handling
- loại `delegate_tasks` khỏi visible tool surface
- giữ nguyên các state/metadata fields additive nhưng không sử dụng; không cần
  migration conversation vì base lead-agent runtime vẫn giữ nguyên

## Open Questions

- Worker outcomes nên chỉ được persist trong assistant metadata dạng aggregate,
  hay hệ thống cũng nên giữ một server-side audit record có giới hạn cho từng
  worker run để phục vụ offline debugging?
- Giá trị mặc định an toàn ban đầu cho `max_parallel_subagents` trong
  production nên là `3`, `5`, hay cấu hình theo môi trường?
- Delegation có nên cho phép với mọi enabled skill, hay một số skills cần cờ
  opt-in riêng trước khi coi worker reuse là an toàn?
