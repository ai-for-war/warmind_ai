## Why

Stock agent hiện đã có cơ chế spawn worker agent, nhưng worker hiện tại chỉ là một stock-agent clone với prompt generic. Cách này giúp tách context, nhưng chưa tạo được chuyên môn hóa thật sự cho các mảng quan trọng như phân tích sự kiện, tin tức, chính sách, và catalyst ảnh hưởng tới cổ phiếu.

Thay đổi này chuẩn hóa delegation thành một registry subagent rõ ràng: vẫn giữ `general_worker` để xử lý tác vụ generic như hiện tại, đồng thời thêm `event_analyst` là preset subagent đầu tiên với tool surface và output contract cố định.

## What Changes

- Thêm registry subagent nội bộ cho stock agent, bắt đầu với hai `agent_id` hợp lệ:
  - `general_worker`: giữ hành vi spawn worker generic hiện tại.
  - `event_analyst`: agent mới chuyên phân tích sự kiện/news/catalyst/policy/regulatory/macro-industry impact cho cổ phiếu Việt Nam.
- Thay đổi contract của `delegate_tasks` để nhận input tối giản và thống nhất:
  - `agent_id`
  - `objective`
  - `context`
- Loại bỏ `expected_output` khỏi delegated task input. Stock agent không được định nghĩa output format theo từng lần gọi; mỗi subagent chịu trách nhiệm về output contract cố định của chính nó.
- `event_analyst` chỉ dùng web research tools hiện có: `search` và `fetch_content`.
- Cập nhật orchestration prompt để stock agent chọn subagent theo mục đích:
  - dùng `event_analyst` khi task liên quan tới tin tức, sự kiện doanh nghiệp, chính sách, quy định, ngành, vĩ mô, catalyst hoặc event risk;
  - dùng `general_worker` khi task generic hoặc chưa có preset specialist phù hợp.
- Giữ guardrail hiện tại: worker/subagent không được spawn subagent tiếp theo.
- Bổ sung validation và test coverage cho:
  - `agent_id` hợp lệ;
  - payload worker không còn `expected_output`;
  - `general_worker` vẫn giữ hành vi hiện tại;
  - `event_analyst` chỉ thấy `search` và `fetch_content`;
  - stock agent prompt mô tả đúng các subagent có sẵn.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `stock-agent-runtime`: mở rộng runtime delegation của stock agent từ worker generic duy nhất thành registry subagent có `general_worker` và preset `event_analyst`, đồng thời thay đổi delegated task input contract để bỏ `expected_output`.

## Impact

- **Code bị tác động**:
  - `app/agents/implementations/stock_agent/delegation.py`
  - `app/agents/implementations/stock_agent/tools.py`
  - `app/agents/implementations/stock_agent/tool_catalog.py`
  - `app/agents/implementations/stock_agent/middleware/orchestration.py`
  - `app/agents/implementations/stock_agent/middleware/tool_selection.py`
  - `app/prompts/system/stock_agent.py`
  - module mới cho `event_analyst` dưới `app/agents/implementations/`
- **Runtime behavior**:
  - parent stock agent vẫn là agent duy nhất tổng hợp câu trả lời cuối cùng cho user;
  - delegated worker chạy trong context cô lập;
  - `general_worker` giữ hành vi tương thích với worker hiện tại, trừ input không còn `expected_output`;
  - `event_analyst` có prompt, tools, và structured result riêng.
- **API/public surface**:
  - không thay đổi endpoint stock-agent conversation;
  - thay đổi nội bộ tool schema của `delegate_tasks`, có thể ảnh hưởng tới tests hoặc prompt snapshots phụ thuộc vào schema cũ.
- **Dependencies**:
  - không thêm third-party dependency mới;
  - tận dụng MCP research tools hiện có `search` và `fetch_content`.
