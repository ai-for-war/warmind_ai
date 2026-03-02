# Feature Backlog (Đề xuất)

Tài liệu này là danh sách các tính năng đề xuất cho hệ thống **AI Service (FastAPI + LangChain/LangGraph + MongoDB + Redis + Socket.IO + Google Sheets + MCP)**.

## 1) AI / Conversational Analytics

### 1.1 Proactive Insights (Daily/Weekly) + Anomaly Detection
- **Mục tiêu**: AI chủ động phát hiện vấn đề và gửi insight (không cần user hỏi).
- **Ví dụ**: Doanh thu giảm bất thường, tỉ lệ huỷ tăng, sản phẩm bán chậm bất thường, chi phí vận chuyển tăng.
- **Kênh**: Socket.IO realtime, (tuỳ chọn) email/webhook.
- **Priority**: HIGH  | **Effort**: Medium
- **Phụ thuộc**: worker scheduling + redis queue + lưu Insight vào MongoDB.

### 1.2 AI-Generated Visualizations (Chart spec trong chat)
- **Mục tiêu**: Trả lời kèm biểu đồ (bar/line/pie) và dataset đã query.
- **Output gợi ý**: `{ content, visualization: { type, spec, data } }`
- **Priority**: HIGH | **Effort**: Medium
- **Phụ thuộc**: thống nhất “chart spec format” (Vega-Lite/ECharts) giữa backend & frontend.

### 1.3 Smart Query Suggestions + Follow-up Prompts
- **Mục tiêu**: Gợi ý câu hỏi dựa trên schema/data user đang có; gợi ý follow-up sau mỗi câu trả lời.
- **Priority**: MEDIUM | **Effort**: Low
- **Phụ thuộc**: Data schema tool + conversation context.

### 1.4 Natural-Language Alert Builder (tạo cảnh báo bằng tiếng Việt)
- **Mục tiêu**: User gõ “Báo khi doanh thu giảm >20% so với tuần trước”, hệ thống tạo rule.
- **Priority**: MEDIUM | **Effort**: Medium
- **Phụ thuộc**: rule engine + scheduler + notification channel.

### 1.5 Conversation Memory (Preference & Business Context)
- **Mục tiêu**: Nhớ bối cảnh shop (kênh bán chính, KPI quan tâm, ngôn ngữ, format report).
- **Priority**: MEDIUM | **Effort**: Medium
- **Phụ thuộc**: MongoDB schema cho user preferences + retrieval vào prompt.

## 2) Analytics (API + Cache)

### 2.1 Forecasting API (Revenue/Orders/Quantity)
- **Mục tiêu**: Dự báo theo ngày/tuần/tháng + khoảng tin cậy; phục vụ planning.
- **Priority**: HIGH | **Effort**: High
- **Phụ thuộc**: đủ lịch sử dữ liệu; chọn thuật toán (Prophet/ARIMA/ETS) + lưu model/artifacts.

### 2.2 Inventory Prediction (Stock-out / Reorder)
- **Mục tiêu**: Dự đoán hết hàng & gợi ý nhập hàng; phát hiện sản phẩm “slow-moving”.
- **Priority**: HIGH | **Effort**: High
- **Phụ thuộc**: dữ liệu tồn kho/nhập hàng (nếu chưa có cần thêm sheet type hoặc integration).

### 2.3 Customer Segmentation (RFM) + Churn Risk + CLV
- **Mục tiêu**: Phân nhóm khách hàng; dự đoán churn; ước tính CLV.
- **Priority**: MEDIUM | **Effort**: Medium-High
- **Phụ thuộc**: liên kết customer ↔ orders; chuẩn hoá id/email/phone.

### 2.4 KPI Library + Metric Definitions (chuẩn hoá chỉ số)
- **Mục tiêu**: Bộ định nghĩa KPI chuẩn (GMV, net revenue, cancel rate, refund rate, AOV…).
- **Priority**: MEDIUM | **Effort**: Low-Medium
- **Phụ thuộc**: mapping trường dữ liệu; versioning metric definitions.

## 3) Data / Integrations

### 3.1 Multi-Platform Connectors (Shopee/Lazada/Tiki)
- **Mục tiêu**: Sync trực tiếp từ API sàn thay vì upload/sheet thủ công.
- **Priority**: MEDIUM-HIGH | **Effort**: High
- **Phụ thuộc**: credential management + rate limit + data normalization + background sync.

### 3.2 Webhooks (Outgoing) cho Insights/Alerts/Sync Events
- **Mục tiêu**: Gửi event sang Slack/Telegram/CRM/BI.
- **Priority**: MEDIUM | **Effort**: Low
- **Phụ thuộc**: webhook registry + retry + audit log.

### 3.3 Data Quality Monitor (Schema drift / Missing columns / Outliers)
- **Mục tiêu**: Phát hiện sheet đổi cột, dữ liệu thiếu, format lỗi; hướng dẫn user sửa mapping.
- **Priority**: MEDIUM | **Effort**: Medium
- **Phụ thuộc**: validate pipeline + lưu “quality report”.

## 4) Reporting & Sharing

### 4.1 Scheduled Reports (PDF/Email/HTML)
- **Mục tiêu**: Báo cáo định kỳ (Daily/Weekly/Monthly) gửi tự động.
- **Priority**: MEDIUM | **Effort**: Medium
- **Phụ thuộc**: report templates + renderer + scheduling + permissions.

### 4.2 Shareable Links / Snapshots (đóng băng kết quả)
- **Mục tiêu**: Share insight/report dạng link; đảm bảo dữ liệu không đổi theo thời gian.
- **Priority**: MEDIUM | **Effort**: Medium
- **Phụ thuộc**: snapshot storage + access control + expiry.

## 5) Premium / Monetization (tuỳ chọn)

### 5.1 Competitive Intelligence (Price monitoring, trend)
- **Mục tiêu**: Theo dõi giá/đối thủ; cảnh báo biến động.
- **Priority**: LOW (Premium) | **Effort**: High
- **Phụ thuộc**: crawler/partner data + legal/compliance.

### 5.2 AI Business Advisor (Recommendations + ROI estimate)
- **Mục tiêu**: Không chỉ trả lời số liệu mà còn đề xuất hành động; ước tính impact.
- **Priority**: MEDIUM (Premium) | **Effort**: High
- **Phụ thuộc**: rule-based guardrails + evaluation + safe prompting.

## 6) Gợi ý Roadmap triển khai nhanh

- **Phase 1.5 (2–4 tuần)**: 1.2 Visualizations, 1.3 Suggestions, 3.2 Webhooks
- **Phase 2 (4–8 tuần)**: 1.1 Insights/Anomaly (bản basic), 4.1 Scheduled reports
- **Phase 2+ (8–12 tuần)**: 2.1 Forecasting, 2.3 Customer intelligence
- **Phase 3**: 3.1 Multi-platform connectors, 5.x Premium
