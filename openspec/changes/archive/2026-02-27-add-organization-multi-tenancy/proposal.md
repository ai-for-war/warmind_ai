## Why

Hệ thống hiện tại là single-tenant, không hỗ trợ phân chia dữ liệu theo Organization (Company). 
Để trở thành SaaS multi-tenant, cần implement Organization feature cho phép:
- Nhiều company sử dụng chung hệ thống nhưng data isolated
- User có thể thuộc nhiều organizations với role khác nhau
- Admin quản lý users trong phạm vi organization của mình

## What Changes

- **Thêm Organization model**: Đại diện cho Company trong hệ thống
- **Thêm OrganizationMember model**: Quan hệ many-to-many giữa User và Organization với role
- **Cập nhật User model**: Đổi role ADMIN → SUPER_ADMIN (system-level)
- **Thêm organization_id vào Conversation, SheetConnection**: Data scoping theo org
- **Xóa self-registration**: User được tạo bởi Super Admin hoặc Org Admin
- **Thêm Organization management APIs**: CRUD organizations, member management
- **Thêm X-Organization-ID header validation**: Context switching giữa orgs

## Capabilities

### New Capabilities
- `organization-management`: CRUD operations cho Organization entities, chỉ Super Admin được tạo/xóa organizations
- `organization-membership`: Quản lý user membership trong organizations với role-based access (Org Admin, Org User)
- `user-management`: Admin tạo user accounts (thay vì self-register), Super Admin và Org Admin có thể tạo users

### Modified Capabilities
<!-- Không có existing specs nên không có modified capabilities -->

## Impact

- **Models**: User, Conversation, SheetConnection cần thêm/sửa fields
- **Auth**: JWT flow thay đổi, thêm org context validation qua X-Organization-ID header
- **APIs**: Tất cả data endpoints cần filter by organization_id
- **Database**: Thêm collections `organizations`, `organization_members`; thêm indexes cho multi-tenant queries
- **Breaking changes**: 
  - **BREAKING**: Xóa `/api/v1/auth/register` endpoint
  - **BREAKING**: Require `X-Organization-ID` header cho data endpoints
  - **BREAKING**: Role `ADMIN` đổi thành `SUPER_ADMIN` trong UserRole enum
