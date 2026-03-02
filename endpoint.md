# API Endpoints Updated (For FE)

Base URL: `/api/v1`

## 1. Auth

- `POST /auth/login`
  - Request: `{ "email": "user@example.com", "password": "string" }`
  - Response: `{ "access_token": "jwt", "token_type": "bearer" }`

- `POST /auth/change-password`
  - Auth: `Bearer token`
  - Request: `{ "current_password": "string", "new_password": "string(min 8)" }`
  - Response: `{ "message": "Password changed successfully" }`

- `POST /auth/bootstrap-super-admin`
  - Auth: none (public bootstrap endpoint)
  - Request: `{ "email": "superadmin@example.com", "password": "string(min 8)" }`
  - Chi hoat dong khi he thong chua co user nao
  - Response: `UserResponse`

- Removed:
  - `POST /auth/register` (khong con dung)

## 2. Organizations

- `POST /organizations` (Super Admin)
  - Auth: `Bearer token`
  - Request: `{ "name": "Acme", "description": "optional" }`

- `GET /organizations` (Super Admin)
  - Query: `is_active?`, `skip?`, `limit?`

- `GET /organizations/{org_id}` (Super Admin)

- `PATCH /organizations/{org_id}` (Super Admin)
  - Request: `{ "name"?: "...", "description"?: "...", "is_active"?: true/false }`

- `DELETE /organizations/{org_id}` (Super Admin)

## 3. Organization Members

- `POST /organizations/{org_id}/members`
  - Auth: `Bearer token` (Super Admin hoac Org Admin)
  - Request: `{ "user_email": "member@example.com", "role": "admin|user" }`

- `GET /organizations/{org_id}/members`
  - Auth: `Bearer token` (member cua org)

- `PATCH /organizations/{org_id}/members/{user_id}`
  - Auth: `Bearer token` (Super Admin hoac Org Admin)
  - Request: `{ "role": "admin|user" }`

- `DELETE /organizations/{org_id}/members/{user_id}`
  - Auth: `Bearer token` (Super Admin hoac Org Admin)

## 4. Users

- `POST /users`
  - Auth: `Bearer token` (Super Admin hoac Org Admin scope)
  - Request:
    `{ "email": "...", "password": "...", "organization_id"?: "...", "organization_role"?: "admin|user" }`

- `GET /users`
  - Auth: `Bearer token`
  - Query: `organization_id?`, `skip?`, `limit?`

- `GET /users/me`
  - Auth: `Bearer token`

- `GET /users/me/organizations`
  - Auth: `Bearer token`

- `GET /users/{user_id}`
  - Auth: `Bearer token`
  - Query: `organization_id?` (can cho org-admin scope)

- `PATCH /users/{user_id}`
  - Auth: `Bearer token`
  - Query: `organization_id?`
  - Request: `{ "is_active": false }` (chi support deactivate)

- `POST /users/{user_id}/reset-password`
  - Auth: `Bearer token`
  - Query: `organization_id?`
  - Request: `{ "new_password": "string(min 8)" }`

## 5. Required Org Header (Behavior Change)

Cac endpoint data hien yeu cau header:

- Header bat buoc: `X-Organization-ID: <org_id>`
- Auth: `Bearer token`

### 5.1 Chat

- `POST /chat/messages`
- `GET /chat/conversations`
- `GET /chat/conversations/{conversation_id}/messages`

### 5.2 Sheet Connections

- `GET /sheet-connections/service-account`
- `POST /sheet-connections`
- `GET /sheet-connections`
- `GET /sheet-connections/{connection_id}`
- `PUT /sheet-connections/{connection_id}`
- `DELETE /sheet-connections/{connection_id}`
- `POST /sheet-connections/{connection_id}/sync`
- `GET /sheet-connections/{connection_id}/sync-status`
- `GET /sheet-connections/{connection_id}/preview`
- `GET /sheet-connections/{connection_id}/data`

## 6. FE Notes

- Luon gui:
  - `Authorization: Bearer <token>`
  - `X-Organization-ID: <org_id>` cho chat + sheet-connections
- Neu user switch organization o UI, phai doi `X-Organization-ID` tuong ung cho request data.
