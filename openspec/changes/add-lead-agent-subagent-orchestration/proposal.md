## Lý do

Runtime `lead_agent` hiện tại xử lý toàn bộ tác vụ bên trong một luồng agent
duy nhất. Cách này đơn giản về mặt kiến trúc, nhưng với các tác vụ nghiên cứu
phức tạp hoặc cần nhiều góc nhìn, context của lead agent sẽ nhanh chóng bị đầy
bởi tool traces, kết quả trung gian, và nội dung fetch lớn.

Sản phẩm hiện cần một mô hình điều phối subagent có kiểm soát để lead agent
tập trung vào lập kế hoạch, phân rã công việc, và tổng hợp kết quả cuối cùng,
trong khi các worker agent xử lý các subtasks nặng trong các context tách
biệt. Điều này giúp mở rộng tốt hơn cho các yêu cầu phức tạp mà không thay đổi
trải nghiệm conversation-first ở frontend.

## Thay đổi gì

- Thêm capability nội bộ mới cho lead agent để quyết định theo từng turn xem
  nên trả lời trực tiếp hay ủy quyền công việc phức tạp cho một hoặc nhiều
  worker agents
- Mở rộng luồng gửi message của lead agent để client có thể bật orchestration
  cho từng turn mà không cần tạo entry point runtime riêng
- Bổ sung một internal tool tin cậy để spawn nhiều worker agents, chạy song
  song, và chỉ trả về kết quả tổng hợp ngắn gọn cho lead agent
- Mở rộng runtime state của lead agent với metadata liên quan đến delegation
  như orchestration mode theo turn, theo dõi parent/worker execution, và giới
  hạn recursion depth
- Thêm orchestration-aware prompt và middleware để lead agent chạy theo vai
  trò manager khi bật subagent mode, còn worker agents chạy dưới worker policy
  bị giới hạn
- Giữ nguyên contract hiện có của conversation, message history, và socket
  streaming, đồng thời bổ sung observability cho delegated tool activity và
  worker outcomes

## Capabilities

### New Capabilities
- `lead-agent-subagent-orchestration`: cung cấp cơ chế delegation theo mô hình
  manager-worker, thực thi worker song song, cô lập context của worker, tổng
  hợp kết quả từ worker, và các guardrails ở backend cho depth, visibility, và
  completion của worker

### Modified Capabilities
- `lead-agent-runtime`: mở rộng contract của runtime `lead-agent` để các turn
  theo conversation có thể opt-in vào subagent orchestration, persist
  delegation-related state, và stream delegated execution metadata trong khi
  vẫn giữ mô hình runtime hiện tại dựa trên thread-backed state

## Ảnh hưởng

- **Mã nguồn bị tác động**: `app/api/v1/ai/lead_agent.py`,
  `app/domain/schemas/lead_agent.py`,
  `app/agents/implementations/lead_agent/agent.py`,
  `app/agents/implementations/lead_agent/state.py`,
  `app/agents/implementations/lead_agent/tools.py`,
  `app/agents/implementations/lead_agent/middleware.py`,
  `app/services/ai/lead_agent_service.py`, và các helper mới liên quan đến
  delegation dưới `app/agents/implementations/lead_agent/`
- **Ảnh hưởng API**: `POST /lead-agent/messages` nhận thêm input orchestration
  theo từng turn; các endpoint hiện tại vẫn được giữ nguyên
- **Ảnh hưởng runtime**: luồng thực thi của lead agent được bổ sung
  manager-worker delegation, worker isolation, và guardrails như max depth và
  max parallel workers
- **State và observability**: thread state và assistant metadata được bổ sung
  các trường liên quan đến delegation để phục vụ debug và evaluation
- **Không tạo runtime frontend riêng**: flow conversation hiện tại của
  lead-agent vẫn là entry point duy nhất mà user nhìn thấy
