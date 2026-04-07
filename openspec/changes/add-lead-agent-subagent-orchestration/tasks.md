## 1. Hợp đồng API và Runtime

- [x] 1.1 Mở rộng lead-agent request và persistence models để nhận input `subagent_enabled` theo từng turn trên `POST /lead-agent/messages`
- [x] 1.2 Cập nhật phần dựng runtime payload trong service để orchestration mode theo turn được inject vào runtime state mà không trở thành thread mode cố định
- [x] 1.3 Mở rộng lead-agent runtime state và assistant metadata models với các trường liên quan đến delegation như orchestration mode, delegation depth, và delegated execution metadata

## 2. Prompt Orchestration và Tool Visibility

- [ ] 2.1 Bổ sung lead-agent prompt cho orchestration và worker-specific prompt trong module system prompt của lead-agent
- [ ] 2.2 Cập nhật middleware của lead-agent để chuyển prompt behavior khi turn-scoped subagent orchestration được bật
- [ ] 2.3 Cập nhật tool-selection rules để `delegate_tasks` chỉ hiển thị cho parent runs hợp lệ và bị ẩn khỏi worker executions ở `delegation_depth = 1`

## 3. Delegation Tool và Worker Executor

- [ ] 3.1 Implement internal tool `delegate_tasks` với structured delegated task input và bounded aggregate output
- [ ] 3.2 Thêm delegation executor module để tạo isolated worker execution payloads với trusted caller scope, enabled skills, và worker-specific policy
- [ ] 3.3 Implement bounded parallel worker execution, timeout handling, và per-worker failure capture trong delegation executor
- [ ] 3.4 Tái sử dụng lead-agent factory/runtime helpers cho worker runs trong khi enforce no-recursion và no-direct-user-clarification behavior cho workers

## 4. Streaming và Observability

- [ ] 4.1 Kết nối delegated execution với existing tool lifecycle socket events để activity của `delegate_tasks` quan sát được trên conversation stream
- [ ] 4.2 Mở rộng assistant message metadata persistence để lưu delegated coordination outcomes cho các orchestrated turns hoàn tất
- [ ] 4.3 Đảm bảo delegated tool result serialization luôn có giới hạn và phù hợp cho parent synthesis cũng như frontend inspection

## 5. Kiểm thử và Regression Coverage

- [ ] 5.1 Thêm tests cho orchestration input theo turn, bao gồm direct-execution turns và delegated turns trong cùng một conversation
- [ ] 5.2 Thêm tests cho middleware và tool visibility để parent runs có thể delegate còn worker runs thì không thể delegate đệ quy
- [ ] 5.3 Thêm tests cho isolated worker execution và bounded aggregation, bao gồm partial worker failures và các delegated tasks chạy song song
- [ ] 5.4 Thêm tests cho assistant metadata và socket streaming để delegated execution vẫn quan sát được qua các contract hiện có
- [ ] 5.5 Chạy targeted regression checks cho flow conversation hiện tại của lead-agent, skill loading, planning, token streaming, và tool streaming behavior
