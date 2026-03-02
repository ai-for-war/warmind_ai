# AI Chat Assistant - Feature Plan

## Overview

AI Chat Assistant cho phép người dùng query dữ liệu kinh doanh bằng ngôn ngữ tự nhiên (tiếng Việt). Tính năng này giúp democratize data - ai cũng có thể phân tích dữ liệu mà không cần kỹ năng kỹ thuật.

## Data Sources

### Primary (MVP)
- **Google Sheets đã sync**: Orders, Order Items, Customers, Products

### Future Expansion
- External data: Giá đối thủ, trend thị trường
- Platform APIs: Shopee/Lazada API (reviews, ratings...)

## Conversation Features

- **Multi-turn conversation**: Nhớ context của cuộc hội thoại
- **Vietnamese language**: Hỗ trợ tiếng Việt là chính
- **Text response**: MVP chỉ trả lời text, sau này thêm visualizations

---

## Phân loại câu hỏi (Query Classification)

### Level 1: Simple Queries (Dễ - Query trực tiếp)

Câu hỏi có thể trả lời bằng 1 aggregation query đơn giản.

| Loại | Ví dụ câu hỏi | Data Source | MongoDB Operation |
|------|---------------|-------------|-------------------|
| **Count** | "Hôm nay có bao nhiêu đơn?" | Orders | `count()` |
| **Sum** | "Tổng doanh thu tháng này?" | Orders.total_amount | `$sum` |
| **Average** | "Giá trị đơn hàng trung bình?" | Orders.total_amount | `$avg` |
| **Top N** | "Top 5 sản phẩm bán chạy nhất?" | Order_Items | `$sort` + `$limit` |
| **Filter** | "Có bao nhiêu đơn từ Shopee?" | Orders.platform | `$match` |
| **Status** | "Bao nhiêu đơn đang chờ giao?" | Orders.order_status | `$match` |
| **Min/Max** | "Đơn hàng lớn nhất là bao nhiêu?" | Orders.total_amount | `$max` |

**Ví dụ câu hỏi chi tiết:**
- "Hôm nay bán được bao nhiêu đơn?"
- "Tổng doanh thu tuần này là bao nhiêu?"
- "Có bao nhiêu khách hàng?"
- "Sản phẩm nào bán chạy nhất?"
- "Bao nhiêu đơn bị hủy tháng này?"
- "Đơn hàng trung bình là bao nhiêu tiền?"

---

### Level 2: Comparison Queries (Trung bình - So sánh)

Câu hỏi cần so sánh 2+ metrics hoặc time periods.

| Loại | Ví dụ câu hỏi | Complexity | Approach |
|------|---------------|------------|----------|
| **Platform comparison** | "So sánh doanh thu Shopee vs Lazada" | 2 queries | Group by platform |
| **Time comparison** | "Doanh thu tuần này so với tuần trước?" | 2 time ranges | 2 separate queries |
| **Period over period** | "Tháng này tăng/giảm bao nhiêu % so với tháng trước?" | Calculation | Query + math |
| **Product comparison** | "Sản phẩm A bán được bao nhiêu so với B?" | 2 filters | Filter comparison |
| **Status comparison** | "Tỷ lệ đơn thành công vs đơn hủy?" | Ratio | Group by status |

**Ví dụ câu hỏi chi tiết:**
- "So sánh doanh thu Shopee và Lazada tháng này"
- "Tuần này bán được nhiều hơn hay ít hơn tuần trước?"
- "Doanh thu tháng 12 so với tháng 11 thế nào?"
- "Platform nào có tỷ lệ hủy đơn cao nhất?"
- "Sản phẩm A hay sản phẩm B bán chạy hơn?"

---

### Level 3: Trend & Pattern Queries (Khó - Phân tích xu hướng)

Câu hỏi cần phân tích pattern trong data.

| Loại | Ví dụ câu hỏi | Analysis Type | Approach |
|------|---------------|---------------|----------|
| **Trend** | "Doanh thu đang tăng hay giảm?" | Time series | Linear regression / moving average |
| **Peak detection** | "Ngày nào bán được nhiều nhất?" | Max aggregation | Group by date + sort |
| **Time pattern** | "Khung giờ nào bán chạy nhất?" | Hourly analysis | Group by hour |
| **Day pattern** | "Cuối tuần có bán chạy hơn không?" | Day of week | Group by day_of_week |
| **Monthly pattern** | "Tháng nào bán chạy nhất trong năm?" | Monthly analysis | Group by month |
| **Growth rate** | "Tốc độ tăng trưởng doanh thu?" | Growth calculation | Period comparison |

**Ví dụ câu hỏi chi tiết:**
- "Doanh thu 3 tháng gần đây có xu hướng thế nào?"
- "Ngày nào trong tuần bán chạy nhất?"
- "Tháng nào có doanh thu cao nhất?"
- "Doanh thu đang tăng hay giảm?"
- "Cuối tuần có bán được nhiều hơn ngày thường không?"

---

### Level 4: Why Analysis (Phức tạp - Phân tích nguyên nhân)

Câu hỏi cần AI reasoning để tìm nguyên nhân.

| Loại | Ví dụ câu hỏi | Analysis Required | AI Reasoning |
|------|---------------|-------------------|--------------|
| **Revenue drop** | "Tại sao doanh thu tuần này giảm?" | Multi-factor | Check: orders count, avg value, platform, products |
| **Cancellation** | "Tại sao tỷ lệ hủy đơn tăng?" | Correlation | Check: platform, products, time, cancel_reason |
| **Product decline** | "Tại sao sản phẩm X bán chậm lại?" | Product analysis | Check: price, competition, seasonality |
| **Customer behavior** | "Tại sao khách hàng không quay lại?" | Churn analysis | Check: order frequency, satisfaction |

**Ví dụ câu hỏi chi tiết:**
- "Tại sao doanh thu tuần này giảm 20%?"
- "Tại sao đơn hàng từ Shopee giảm?"
- "Tại sao tỷ lệ hủy đơn tăng cao?"
- "Tại sao sản phẩm X không bán được nữa?"
- "Nguyên nhân doanh thu tháng này thấp hơn tháng trước?"

**AI Reasoning Process:**
1. Xác định metric bị ảnh hưởng (revenue, orders, cancellation...)
2. So sánh với period trước để xác nhận vấn đề
3. Phân tích các factors có thể ảnh hưởng:
   - Số lượng đơn hàng
   - Giá trị đơn trung bình
   - Platform distribution
   - Product mix
   - Tỷ lệ hủy đơn
4. Tìm factor có sự thay đổi lớn nhất
5. Đưa ra kết luận với evidence

---

### Level 5: Recommendation Queries (Phức tạp nhất - Gợi ý hành động)

Câu hỏi cần AI đưa ra recommendations dựa trên data analysis.

| Loại | Ví dụ câu hỏi | Output Type | Data Required |
|------|---------------|-------------|---------------|
| **Action** | "Tôi nên làm gì để tăng doanh thu?" | Actionable suggestions | Full analysis |
| **Product focus** | "Sản phẩm nào nên đẩy mạnh?" | Product recommendations | Sales + margin data |
| **Platform** | "Nên tập trung vào platform nào?" | Platform strategy | Platform performance |
| **Pricing** | "Có nên giảm giá sản phẩm X không?" | Pricing advice | Price elasticity |
| **Inventory** | "Sản phẩm nào cần nhập thêm?" | Stock recommendations | Sales velocity |

**Ví dụ câu hỏi chi tiết:**
- "Tôi nên làm gì để tăng doanh thu?"
- "Sản phẩm nào nên đẩy mạnh marketing?"
- "Nên tập trung bán trên Shopee hay Lazada?"
- "Có nên ngừng bán sản phẩm X không?"
- "Làm sao để giảm tỷ lệ hủy đơn?"

**AI Recommendation Process:**
1. Phân tích current state (strengths, weaknesses)
2. Identify opportunities từ data
3. Prioritize actions theo impact và feasibility
4. Provide specific, actionable recommendations
5. Include expected outcome nếu có thể

---

## Implementation Roadmap

| Phase | Levels | Timeline | Effort | Coverage |
|-------|--------|----------|--------|----------|
| **MVP** | Level 1 + 2 | 2-3 weeks | Medium | ~70% use cases |
| **V1.1** | Level 3 | 2 weeks | Medium | ~85% use cases |
| **V1.2** | Level 4 + 5 | 4+ weeks | High | ~95% use cases |

### MVP Scope (Level 1 + 2)

**Included:**
- Simple aggregation queries (count, sum, avg, min, max)
- Top N queries
- Filter queries (by platform, status, date range)
- Basic comparisons (platform vs platform, period vs period)
- Percentage calculations

**Not Included:**
- Trend analysis
- Why analysis (root cause)
- Recommendations
- Visualizations

---
