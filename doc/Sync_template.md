# Google Sheet Sync Data Template

Template chuẩn cho việc sync dữ liệu đơn hàng từ các sàn TMĐT (Shopee/Lazada/Tiki) về hệ thống AI phân tích.

---

## Sheet 1: Orders (Đơn hàng)

| Cột | Tên cột | Mô tả | Kiểu dữ liệu | Bắt buộc |
|-----|---------|-------|--------------|----------|
| A | `order_id` | Mã đơn hàng (từ sàn hoặc tự tạo) | String | ✅ |
| B | `order_number` | Số đơn hàng hiển thị cho khách | String | |
| C | `platform` | Nguồn đơn: Shopee/Lazada/Tiki/Other | String | ✅ |
| D | `order_status` | Trạng thái: pending/paid/shipped/delivered/cancelled/returned | String | ✅ |
| E | `customer_id` | Liên kết đến sheet Customers | String | ✅ |
| F | `order_date` | Ngày tạo đơn | DateTime (YYYY-MM-DD HH:mm) | ✅ |
| G | `payment_date` | Ngày thanh toán | DateTime | |
| H | `ship_date` | Ngày giao cho vận chuyển | DateTime | |
| I | `delivered_date` | Ngày giao thành công | DateTime | |
| J | `payment_method` | COD/Bank Transfer/E-wallet/Credit Card | String | |
| K | `shipping_carrier` | Đơn vị vận chuyển (GHN, GHTK, J&T...) | String | |
| L | `tracking_number` | Mã vận đơn | String | |
| M | `subtotal` | Tổng tiền hàng (trước giảm giá) | Number | ✅ |
| N | `discount_amount` | Số tiền giảm giá | Number | |
| O | `shipping_fee` | Phí vận chuyển | Number | |
| P | `total_amount` | Tổng thanh toán | Number | ✅ |
| Q | `platform_fee` | Phí sàn (nếu có) | Number | |
| R | `note` | Ghi chú của seller | String | |
| S | `cancel_reason` | Lý do hủy (nếu có) | String | |

### Giá trị cho cột `order_status`:
- `pending` - Chờ xác nhận
- `paid` - Đã thanh toán
- `processing` - Đang xử lý
- `shipped` - Đang giao hàng
- `delivered` - Giao thành công
- `cancelled` - Đã hủy
- `returned` - Hoàn trả

### Giá trị cho cột `platform`:
- `Shopee`
- `Lazada`
- `Tiki`
- `Website`
- `Facebook`
- `Other`

---

## Sheet 2: Order_Items (Chi tiết sản phẩm trong đơn)

| Cột | Tên cột | Mô tả | Kiểu dữ liệu | Bắt buộc |
|-----|---------|-------|--------------|----------|
| A | `order_item_id` | ID dòng (tự tạo hoặc auto) | String | ✅ |
| B | `order_id` | Liên kết đến sheet Orders | String | ✅ |
| C | `product_id` | Liên kết đến sheet Products | String | ✅ |
| D | `product_name` | Tên sản phẩm (snapshot tại thời điểm mua) | String | ✅ |
| E | `sku` | Mã SKU | String | |
| F | `variant` | Biến thể (size, màu...) | String | |
| G | `quantity` | Số lượng | Number | ✅ |
| H | `unit_price` | Giá gốc/đơn vị | Number | ✅ |
| I | `discount_per_item` | Giảm giá/sản phẩm | Number | |
| J | `final_price` | Giá sau giảm/đơn vị | Number | ✅ |
| K | `line_total` | Thành tiền (quantity × final_price) | Number | ✅ |
| L | `cost_price` | Giá vốn (để tính lợi nhuận) | Number | |

---

## Sheet 3: Customers (Khách hàng)

| Cột | Tên cột | Mô tả | Kiểu dữ liệu | Bắt buộc |
|-----|---------|-------|--------------|----------|
| A | `customer_id` | ID khách hàng (tự tạo hoặc từ sàn) | String | ✅ |
| B | `customer_name` | Tên khách hàng | String | ✅ |
| C | `phone` | Số điện thoại | String | ✅ |
| D | `email` | Email | String | |
| E | `shipping_address` | Địa chỉ giao hàng | String | |
| F | `city` | Thành phố/Tỉnh | String | |
| G | `district` | Quận/Huyện | String | |
| H | `ward` | Phường/Xã | String | |
| I | `first_order_date` | Ngày mua đầu tiên | Date | |
| J | `total_orders` | Tổng số đơn | Number | |
| K | `total_spent` | Tổng chi tiêu | Number | |
| L | `customer_note` | Ghi chú về khách | String | |

---

## Sheet 4: Products (Sản phẩm) - Optional

| Cột | Tên cột | Mô tả | Kiểu dữ liệu | Bắt buộc |
|-----|---------|-------|--------------|----------|
| A | `product_id` | ID sản phẩm | String | ✅ |
| B | `product_name` | Tên sản phẩm | String | ✅ |
| C | `sku` | Mã SKU | String | |
| D | `category` | Danh mục | String | |
| E | `brand` | Thương hiệu | String | |
| F | `cost_price` | Giá vốn | Number | |
| G | `selling_price` | Giá bán | Number | |
| H | `stock_quantity` | Tồn kho hiện tại | Number | |

---
