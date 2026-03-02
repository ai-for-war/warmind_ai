## Context

Hệ thống hiện tại là một AI Service với các tính năng:
- User authentication với JWT (login/register)
- Conversations và Messages cho AI chat
- SheetConnection để kết nối Google Sheets
- Data được scope theo `user_id`

**Current State:**
- Single-tenant: mỗi user có data riêng nhưng không có khái niệm "company/organization"
- UserRole chỉ có USER và ADMIN (system-level)
- Không có cơ chế để group users hoặc share data trong một organization

**Constraints:**
- MongoDB với Motor (async)
- FastAPI với dependency injection
- Pydantic models cho domain objects
- Cần backward compatible migration path (dù chưa có production data)

## Goals / Non-Goals

**Goals:**
- Multi-tenant architecture với Organization là unit of isolation
- User có thể thuộc nhiều Organizations với role khác nhau trong mỗi org
- Role hierarchy: Super Admin (system) > Org Admin > Org User
- Data (Conversations, SheetConnections) được scope theo organization_id + user_id
- Admin-controlled user creation (không self-register)
- Org switching qua header X-Organization-ID

**Non-Goals:**
- Billing/Subscription per organization (future work)
- Granular permissions (chỉ role-based cho hiện tại)
- Organization hierarchy (org within org)
- Data sharing across organizations
- SSO/SAML integration

## Decisions

### Decision 1: Role Architecture - Separate System Roles vs Org Roles

**Choice:** Tách biệt System Role (UserRole) và Organization Role (OrganizationRole)

**Rationale:**
- User.role = system-level permission (SUPER_ADMIN có thể quản lý tất cả orgs)
- OrganizationMember.role = org-level permission (ADMIN/USER trong context của org đó)
- Một user có thể là ADMIN ở Org A nhưng USER ở Org B

**Alternatives Considered:**
- Single unified role system → Phức tạp khi user thuộc nhiều orgs với role khác nhau
- Permission-based system → Over-engineering cho requirements hiện tại

### Decision 2: Organization Context - Header-based

**Choice:** Sử dụng HTTP Header `X-Organization-ID` để xác định organization context

**Rationale:**
- Flexible: Frontend có thể switch org mà không cần thay đổi URL structure
- Clean separation: URL paths không bị polluted với org_id
- Easy to implement: Dependency injection trong FastAPI

**Alternatives Considered:**
- URL path (`/orgs/{org_id}/...`) → Breaking change lớn cho existing APIs
- Subdomain (`{org}.app.com`) → Phức tạp cho infrastructure, cần wildcard SSL
- JWT claim → Cần refresh token khi switch org

### Decision 3: Data Model - Junction Table for Membership

**Choice:** Tạo separate `organization_members` collection thay vì embedded array

**Rationale:**
- Scalability: Organizations có thể có nhiều members
- Query flexibility: Dễ query "all orgs for user" hoặc "all users for org"
- Additional metadata: Có thể thêm `invited_by`, `joined_at`, etc.

**Alternatives Considered:**
- Embedded array trong User → Khó query ngược, document size limit
- Embedded array trong Organization → Same issues

### Decision 4: User Creation Flow - Admin-only

**Choice:** Xóa self-registration, chỉ Super Admin và Org Admin có thể tạo user

**Rationale:**
- Business requirement: SaaS enterprise model
- Security: Kiểm soát ai được access hệ thống
- Org Admin chỉ tạo user trong org của mình

**Alternatives Considered:**
- Invitation link → Phức tạp hơn, cần email integration
- Self-register + approval → Thêm workflow không cần thiết

### Decision 5: Database Indexes Strategy

**Choice:** Compound indexes cho multi-tenant queries

**Indexes:**
```
organizations:
  - slug (unique)
  - is_active

organization_members:
  - (user_id, organization_id) unique
  - organization_id
  - user_id

conversations:
  - (organization_id, user_id, deleted_at, updated_at)

sheet_connections:
  - (organization_id, user_id)
```

**Rationale:**
- Cover common query patterns
- Support efficient filtering by org + user
- Unique constraint prevents duplicate memberships

## Risks / Trade-offs

### Risk 1: Breaking Changes
**Risk:** Existing API clients sẽ break khi require X-Organization-ID header
**Mitigation:** 
- Document breaking changes clearly
- Versioned rollout nếu cần
- Hiện tại chưa có production clients nên impact thấp

### Risk 2: Query Performance
**Risk:** Thêm organization_id vào mọi query có thể ảnh hưởng performance
**Mitigation:**
- Proper compound indexes
- organization_id đặt đầu tiên trong index để filter hiệu quả

### Risk 3: Super Admin Bypass Complexity
**Risk:** Super Admin cần bypass org check ở nhiều nơi, có thể miss cases
**Mitigation:**
- Centralized permission check trong dependencies
- Unit tests cho permission logic

### Risk 4: Orphaned Data
**Risk:** Khi remove user khỏi org, data của họ trong org đó như thế nào?
**Mitigation:**
- Soft delete membership (is_active = false)
- Data vẫn thuộc org, chỉ user không access được
- Future: có thể thêm data transfer feature

## Migration Plan

### Phase 1: Schema & Models (Non-breaking)
1. Tạo Organization và OrganizationMember models
2. Tạo repositories mới
3. Tạo OrganizationService và UserService
4. Thêm organization_id (OPTIONAL) vào Conversation, SheetConnection
5. Create database indexes
6. Đổi ADMIN → SUPER_ADMIN trong UserRole

### Phase 2: API Layer
1. Thêm organization management endpoints
2. Thêm member management endpoints
3. Thêm user management endpoints (create user by admin)
4. Update deps.py với org context dependencies
5. Xóa /api/v1/auth/register endpoint

### Phase 3: Data Endpoints Update
1. Update conversation endpoints để require X-Organization-ID
2. Update sheet connection endpoints
3. Update repos để filter by org_id
4. Make organization_id REQUIRED trong models

### Rollback Strategy
- Revert code changes
- organization_id fields có thể để nullable để không cần data migration rollback

## Open Questions

1. **Default organization behavior:** Khi Super Admin tạo user không chỉ định org, user đó access gì? 
   - Current decision: User không thuộc org nào sẽ không access được data endpoints (cần được thêm vào org trước)

2. **Organization deletion:** Khi delete org, xử lý data như thế nào?
   - Current decision: Soft delete org (is_active = false), data preserved

3. **Last admin protection:** Có cần ngăn remove admin cuối cùng khỏi org không?
   - Suggest: Implement trong future iteration
