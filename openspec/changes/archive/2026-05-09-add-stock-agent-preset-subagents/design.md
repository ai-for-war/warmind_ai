## Context

Stock agent hiện dùng LangChain `create_agent` với middleware riêng cho prompt orchestration, tool selection, delegation limit, summarization, skill prompt, todo, và tool error handling. Khi subagent mode được bật, parent stock agent có thể gọi `delegate_tasks`; executor hiện tạo một worker runtime bằng chính `create_stock_agent(..., subagent_enabled=False)` và truyền một delegated task gồm `objective`, `expected_output`, và `context`.

Thiết kế hiện tại có hai vấn đề:

- Worker generic giúp cô lập context nhưng không tạo chuyên môn hóa thật sự. Mọi worker đều dùng prompt/tool behavior giống nhau.
- `expected_output` cho phép parent stock agent định nghĩa output shape theo từng lần gọi, làm contract giữa parent và worker không ổn định.

Mục tiêu mới là giữ khả năng spawn worker thường, đồng thời bổ sung preset specialist đầu tiên là `event_analyst`. Specialist phải có prompt, tool surface, và output contract cố định, còn parent stock agent chỉ quyết định mục tiêu điều tra và context cần truyền.

## Goals / Non-Goals

**Goals:**

- Thêm registry subagent cho stock agent với `general_worker` và `event_analyst`.
- Giữ `general_worker` tương thích về hành vi với worker hiện tại, trừ việc delegated input không còn `expected_output`.
- Tạo `event_analyst` là agent mới, chuyên phân tích sự kiện/news/catalyst/policy/regulatory/macro-industry impact cho Vietnam-listed equities.
- Giới hạn `event_analyst` chỉ dùng `search` và `fetch_content`.
- Cố định output contract ở từng subagent thay vì để parent truyền `expected_output`.
- Giữ parent stock agent là agent duy nhất tổng hợp và trả lời user cuối cùng.
- Giữ guardrail không cho worker/subagent delegate tiếp.

**Non-Goals:**

- Không thêm `technical_analyst`, `fundamental_analyst`, hoặc các specialist khác trong change này.
- Không thay đổi public API của stock-agent conversation.
- Không thêm field chuyên biệt như `symbol` hoặc `time_window` vào delegated task input; parent sẽ đưa các thông tin này vào `objective` hoặc `context`.
- Không thêm third-party dependency mới.
- Không thay đổi endpoint hoặc storage model của stock research reports/schedules.

## Decisions

### Decision 1: Dùng một dispatch tool `delegate_tasks` với `agent_id`

`delegate_tasks` sẽ tiếp tục là internal tool duy nhất cho delegation, nhưng `DelegatedTaskInput` sẽ chuyển thành:

```python
class DelegatedTaskInput(BaseModel):
    agent_id: Literal["general_worker", "event_analyst"]
    objective: str
    context: str | None = None
```

Lý do:

- Giữ kiến trúc hiện có: tool, executor, middleware limit, và streaming integration không phải viết lại.
- Khi thêm specialist mới, chỉ mở rộng registry và prompt, không làm phình tool surface.
- `agent_id` bắt buộc giúp parent stock agent chọn rõ loại worker thay vì fallback ngầm.

Alternatives considered:

- Tạo tool riêng như `analyze_stock_events`: rõ hơn với model nhưng dễ phình tool surface khi thêm nhiều specialist.
- Tự route trong backend dựa trên objective text: ít schema churn nhưng khó kiểm soát và khó test vì routing trở thành heuristic ẩn.

### Decision 2: `general_worker` là registry entry chính thức

`general_worker` không phải fallback implicit. Nó là một subagent id hợp lệ trong registry, dùng lại cách chạy worker hiện tại.

Lý do:

- Đáp ứng yêu cầu stock agent vẫn spawn được worker thường cho tác vụ generic.
- Giữ behavior hiện tại ở mức tối đa.
- Tránh tình trạng thiếu `agent_id` vẫn chạy được và làm delegation mơ hồ.

### Decision 3: Loại bỏ `expected_output`

Delegated task input sẽ không còn `expected_output` cho cả `general_worker` lẫn `event_analyst`.

Lý do:

- Output format là contract của subagent, không phải thứ parent agent thay đổi theo từng lần gọi.
- Specialist như `event_analyst` cần structured result ổn định để parent synthesize.
- `general_worker` vẫn có thể trả kết quả synthesis-ready thông qua prompt generic hiện tại, không cần field riêng.

Migration detail:

- `_render_worker_task_message` sẽ bỏ section `Expected output`.
- Prompt orchestration sẽ dặn parent không yêu cầu output format trong delegated task.

### Decision 4: `event_analyst` là agent mới, không reuse `stock_research_agent`

Tạo implementation mới cho event analyst thay vì rename hoặc reuse trực tiếp `stock_research_agent`.

Lý do:

- `stock_research_agent` hiện tạo report đầu tư tổng hợp, bao gồm price snapshot, thesis, risks, recommendation.
- `event_analyst` phải hẹp hơn: chỉ cung cấp evidence package về sự kiện và tác động, không đưa khuyến nghị cuối cùng.
- Tách agent giúp prompt và output schema không bị kéo theo mục tiêu rộng của stock research report.

Vẫn có thể reuse pattern:

- runtime builder theo `create_agent`;
- MCP tool surface resolution cho `search` và `fetch_content`;
- summarization/tool-error middleware pattern;
- structured response validation tương tự `StockResearchAgentOutput`.

### Decision 5: Output của `event_analyst` là structured event impact package

`event_analyst` sẽ trả structured response, dự kiến gồm:

- `summary`
- `events`
- `impact_direction`
- `impact_confidence`
- `bullish_catalysts`
- `bearish_risks`
- `uncertainties`
- `sources`

Lý do:

- Parent stock agent cần dữ liệu ổn định để tổng hợp, không cần parse markdown tùy ý.
- Event analysis rất nhạy với citations/source quality, nên source mapping cần được validate.
- Specialist không được lấn sang recommendation cuối cùng; parent mới quyết định kết luận user-facing.

## Risks / Trade-offs

- **Risk: Parent truyền objective/context thiếu mã cổ phiếu hoặc time window** -> Mitigation: prompt orchestration phải yêu cầu parent đưa symbol/company/time window/user decision context vào `objective` hoặc `context` khi gọi `event_analyst`; nếu user request thiếu blocking context thì parent phải hỏi trước theo stock context gate.
- **Risk: Model vẫn dùng `general_worker` cho task event vì general worker rộng hơn** -> Mitigation: prompt liệt kê routing rule rõ ràng: nếu task match event/news/catalyst/policy/regulatory/macro-industry impact thì dùng `event_analyst`, chỉ dùng `general_worker` khi không có specialist phù hợp.
- **Risk: Structured response từ `event_analyst` fail validation** -> Mitigation: validation parser cần test markdown/JSON fallback nếu runtime trả format không chuẩn; tool-error middleware phải biến tool failures thành bounded messages để agent vẫn có thể trả uncertainty/gaps.
- **Risk: Thay đổi `DelegatedTaskInput` có thể làm tests/prompt snapshots cũ fail** -> Mitigation: cập nhật unit tests cho delegation, tools, middleware, prompt; đây là internal tool schema nên không ảnh hưởng public API.
- **Risk: Thêm agent mới làm tăng compile/cache overhead** -> Mitigation: cache compiled event analyst runtime theo runtime config giống worker cache hiện tại; giữ tool surface chỉ gồm `search` và `fetch_content`.
