# Tài Liệu Tích Hợp Frontend Cho Lead Agent Subagent Orchestration

## 1. Mục tiêu tài liệu

Tài liệu này mô tả phần backend hiện đang cung cấp cho frontend liên quan đến:

- bật hoặc tắt subagent orchestration khi gửi message cho `lead-agent`
- các event socket mà frontend sẽ nhận trong lúc xử lý
- metadata mà backend persist và emit lại cho assistant message

Tài liệu này chỉ mô tả contract và semantics FE cần biết.

Tài liệu này không hướng dẫn cách viết code frontend.

## 2. Phạm vi capability hiện tại

Backend hiện đã hỗ trợ:

- bật orchestration theo từng user turn bằng `subagent_enabled`
- delegated execution nội bộ qua tool `delegate_tasks`
- stream token, tool lifecycle, completion, failed cho parent run
- persist metadata orchestration vào assistant message

Backend hiện chưa cung cấp:

- socket event riêng cho từng subagent con
- stream token riêng của từng subagent cho FE
- UI-facing tree execution API cho delegated workers

## 3. Endpoint FE cần dùng

Để gửi message cho `lead-agent`, FE dùng:

```text
POST /api/v1/lead-agent/messages
```

Request body hiện có shape:

```json
{
  "conversation_id": "optional_conversation_id",
  "content": "User message",
  "provider": "openai",
  "model": "gpt-5.2",
  "reasoning": "medium",
  "subagent_enabled": true
}
```

Field FE cần lưu ý:

- `conversation_id`: optional; nếu không có thì backend tạo conversation mới
- `content`: nội dung user message
- `provider`, `model`, `reasoning`: runtime selection hiện tại của lead-agent
- `subagent_enabled`: bật hoặc tắt subagent orchestration cho đúng turn này

Response accept message:

```json
{
  "user_message_id": "msg_xxx",
  "conversation_id": "conv_xxx"
}
```

## 4. Ý nghĩa của `subagent_enabled`

`subagent_enabled` là cờ theo từng user turn, không phải setting persistent cho toàn bộ conversation.

Semantics FE cần assume:

- user turn A gửi `subagent_enabled = true` không làm turn B tự động bật theo
- mỗi lần FE gửi message mới, FE phải chủ động truyền lại giá trị mong muốn
- backend persist cờ này vào metadata của user message và dùng nó khi chạy background response cho đúng turn đó

## 5. Socket events FE sẽ nhận

Lead-agent vẫn dùng nhóm `ChatEvents` hiện có:

- `chat:message:started`
- `chat:message:token`
- `chat:message:tool_start`
- `chat:message:tool_end`
- `chat:message:plan_updated`
- `chat:message:completed`
- `chat:message:failed`

Semantics mới cần FE nắm rõ:

- các event trên phản ánh **parent lead-agent run**
- backend đã filter nested subagent events ra khỏi main stream
- FE sẽ **không** nhận token hoặc tool events nội bộ của worker/subagent
- nếu parent gọi `delegate_tasks`, FE chỉ thấy tool lifecycle của chính `delegate_tasks`, không thấy các tool con mà subagent tự gọi

Điều này là chủ ý để main chat stream không bị lẫn token/tool của subagent.

## 6. Shape event FE cần chú ý

### 6.1 `chat:message:tool_start`

Ví dụ:

```json
{
  "conversation_id": "conv_xxx",
  "tool_name": "delegate_tasks",
  "tool_call_id": "run_xxx",
  "arguments": {
    "task": {
      "objective": "Tìm và tổng hợp tin tức nổi bật",
      "expected_output": "Danh sách tin tức nổi bật với tiêu đề và link"
    }
  }
}
```

Semantics:

- khi `tool_name = "delegate_tasks"`, parent đang chờ một delegated worker task
- đây không có nghĩa FE sẽ nhận token của worker
- FE chỉ nên hiểu đây là một tool call của parent

Shape dữ liệu hiện tại của `arguments` với `delegate_tasks`:

```json
{
  "task": {
    "objective": "string, bắt buộc",
    "expected_output": "string | null, optional",
    "context": "string | null, optional"
  }
}
```

Ý nghĩa từng field:

- `task.objective`: mô tả subtask mà parent giao cho worker
- `task.expected_output`: mô tả đầu ra hoặc format mong muốn
- `task.context`: ngữ cảnh bổ sung nếu parent truyền thêm

Semantics FE cần assume:

- hiện tại mỗi `delegate_tasks` chỉ nhận đúng một object `task`
- backend không còn nhận mảng `tasks`
- `arguments` trong socket event là payload đã được backend serialize sang JSON-safe dict
- FE có thể hiển thị trực tiếp `objective`, `expected_output`, `context` nếu muốn show detail của subtask

Ví dụ thực tế FE có thể nhận:

```json
{
  "conversation_id": "69d56598655a8c7d52b67aec",
  "tool_name": "delegate_tasks",
  "tool_call_id": "019d6995-243c-7fd1-aa35-fbc4a461c363",
  "arguments": {
    "task": {
      "objective": "Tìm kiếm và tổng hợp các tin tức, bài viết nổi bật từ trang kenh14.vn...",
      "expected_output": "Danh sách các tin tức nổi bật với tiêu đề, mô tả, thời gian, và link nguồn"
    }
  }
}
```

### 6.2 `chat:message:tool_end`

Ví dụ:

```json
{
  "conversation_id": "conv_xxx",
  "tool_call_id": "run_xxx",
  "result": "..."
}
```

Semantics:

- với `delegate_tasks`, `result` là tool output cuối cùng sau khi worker đã hoàn tất hoặc lỗi/timeout
- backend chỉ emit `tool_end` sau khi delegated execution của tool đó kết thúc

Quan trọng: `result` trong socket event hiện là string, không phải object JSON typed.

Lý do:

- backend hiện convert tool output sang text trước khi emit socket event
- với output dạng object/dict của `delegate_tasks`, backend thường stringify object đó thành text

Vì vậy FE nên assume:

- `data.result` là `string`
- không nên assume `data.result` luôn parse được thành JSON hợp lệ
- nếu FE chỉ cần hiển thị trạng thái tool, có thể hiển thị raw text
- nếu FE muốn parse sâu hơn, nên coi đó là best-effort behavior chứ không phải contract cứng hiện tại

Tool output gốc của `delegate_tasks` ở backend hiện có shape sau trước khi bị stringify:

```json
{
  "status": "completed | failed | rejected",
  "worker_timeout_seconds": 30,
  "result": {
    "status": "completed | failed | timeout",
    "objective": "string",
    "summary": "string | null",
    "error": "string | null"
  }
}
```

Ý nghĩa:

- root `status`:
  - `"completed"`: delegated task hoàn tất thành công
  - `"failed"`: worker fail hoặc timeout
  - `"rejected"`: backend từ chối delegated execution
- `worker_timeout_seconds`: timeout hiện áp cho worker run
- `result.status`:
  - `"completed"`: worker trả được kết quả
  - `"failed"`: worker exception
  - `"timeout"`: worker timeout
- `result.objective`: objective đã chuẩn hóa/truncate để trace
- `result.summary`: nội dung worker trả về khi thành công
- `result.error`: lỗi nếu worker fail hoặc timeout

Ví dụ text FE có thể nhận ở `tool_end.result`:

```text
{'status': 'completed', 'worker_timeout_seconds': 30.0, 'result': {'status': 'completed', 'objective': 'Tìm kiếm và tổng hợp các tin tức...', 'summary': 'Đã tổng hợp 6 bài viết nổi bật...', 'error': None}}
```

Hoặc khi timeout/lỗi:

```text
{'status': 'failed', 'worker_timeout_seconds': 30.0, 'result': {'status': 'timeout', 'objective': 'Tìm kiếm và tổng hợp các tin tức...', 'summary': None, 'error': 'Worker timed out after 30s.'}}
```

Semantics FE nên dùng:

- `tool_end` của `delegate_tasks` nghĩa là worker cho tool đó đã xong
- nếu FE chỉ cần UX đơn giản, có thể xem `tool_end` là dấu hiệu "subtask completed"
- nếu FE cần hiển thị chi tiết hơn, nên dựa trên raw `result` text nhưng không nên ràng buộc UI logic cứng vào format string hiện tại

### 6.3 `chat:message:token`

Semantics:

- token chỉ là token của parent assistant response
- không bao gồm token think/tool/model nội bộ của subagent

### 6.4 `chat:message:completed`

Event completed sẽ mang metadata của assistant message cuối cùng.

FE nên đọc phần `metadata` từ event này như nguồn sự thật cho trạng thái orchestration của response.

## 7. Metadata backend hiện cung cấp cho assistant message

Assistant message hiện có thể chứa các field metadata sau:

```json
{
  "model": "gpt-5.2",
  "tokens": {
    "prompt": 11,
    "completion": 7,
    "total": 18
  },
  "finish_reason": "stop",
  "tool_calls": [
    {
      "id": "run_xxx",
      "name": "delegate_tasks",
      "arguments": {
        "task": {
          "objective": "..."
        }
      }
    }
  ],
  "skill_id": "web-research",
  "skill_version": "2.1.0",
  "loaded_skills": ["web-research"],
  "subagent_enabled": true,
  "orchestration_mode": "subagent",
  "delegation_depth": 0,
  "delegation_parent_run_id": null,
  "delegated_execution_metadata": null
}
```

Ý nghĩa FE cần hiểu:

- `subagent_enabled`: response này được chạy với orchestration bật hay không
- `orchestration_mode`:
  - `"direct"`: parent run bình thường
  - `"subagent"`: parent run có orchestration bật
  - `"worker"`: dùng cho delegated worker execution nội bộ; FE thông thường không cần expect field này ở main conversation stream
- `delegation_depth`:
  - `0`: parent run
  - `>0`: worker run nội bộ
- `delegation_parent_run_id`, `delegated_execution_metadata`: metadata phục vụ trace nội bộ; FE có thể hiển thị nếu cần debug nhưng không nên coi là field bắt buộc cho UI chính

## 8. Semantics FE cần đặc biệt lưu ý

### 8.1 Không có subagent progress riêng cho FE

Hiện tại FE không có stream riêng cho từng subagent.

Những gì FE có thể hiển thị an toàn:

- parent đang gọi `delegate_tasks`
- parent đã hoàn tất tool đó
- parent đang stream câu trả lời cuối

### 8.2 `delegate_tasks` là tool call blocking ở backend

Với FE, contract observable đúng là:

- `delegate_tasks` start
- sau đó không có token/tool event nội bộ của worker
- khi worker xong, parent mới tiếp tục lifecycle của mình

FE không nên assume `delegate_tasks` là fire-and-forget background job.

### 8.3 Skill activation không còn carry qua turn mới

Backend hiện reset active skill state ở đầu mỗi user turn mới.

Điều FE cần hiểu:

- danh sách skill enabled của user vẫn còn theo organization
- nhưng skill đang active trong turn trước không tự động carry sang turn tiếp theo
- assistant metadata vẫn có thể chứa `skill_id`, `skill_version`, `loaded_skills` của chính turn vừa chạy xong

### 8.4 Tool events hiện là top-level only

Trong context orchestration:

- FE có thể thấy `delegate_tasks` ở `tool_calls`
- FE không nên kỳ vọng thấy các tool nội bộ như `search`, `fetch_content` của subagent trong main assistant message metadata hoặc socket stream

## 9. Những gì FE nên dùng làm source of truth

- Trạng thái orchestration của một request:
  - request body `subagent_enabled`
- Trạng thái orchestration của một assistant response đã hoàn tất:
  - `assistant_message.metadata.subagent_enabled`
  - `assistant_message.metadata.orchestration_mode`
  - `assistant_message.metadata.delegation_depth`
- Tool lifecycle đang hiển thị realtime:
  - `chat:message:tool_start`
  - `chat:message:tool_end`
- Nội dung trả lời cuối:
  - token stream của parent
  - assistant message persisted sau `chat:message:completed`

## 10. Tóm tắt contract FE nên assume

1. Mỗi lần gửi message, FE tự quyết định có truyền `subagent_enabled` hay không.
2. `subagent_enabled` là turn-scoped, không phải conversation-scoped.
3. Socket stream hiện chỉ phản ánh parent lead-agent run.
4. Khi parent gọi `delegate_tasks`, FE chỉ thấy top-level tool lifecycle của `delegate_tasks`.
5. FE sẽ không nhận token hoặc tool events nội bộ của subagent.
6. Assistant metadata là nơi FE nên đọc trạng thái orchestration cuối cùng của response.
