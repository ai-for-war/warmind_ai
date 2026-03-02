## ADDED Requirements

### Requirement: System roles are updated
The system SHALL support the following system-level roles in UserRole enum:
- `USER`: Regular user (default)
- `SUPER_ADMIN`: System administrator with full access (renamed from ADMIN)

#### Scenario: UserRole enum values
- **WHEN** checking UserRole enum
- **THEN** it MUST contain exactly "user" and "super_admin" values

### Requirement: Self-registration is disabled
The system SHALL NOT allow users to self-register. The /api/v1/auth/register endpoint MUST be removed.

#### Scenario: Register endpoint does not exist
- **WHEN** any request is sent to POST /api/v1/auth/register
- **THEN** the system MUST return 404 Not Found

### Requirement: Super Admin can create users
The system SHALL allow Super Admin to create new user accounts.

#### Scenario: Super Admin creates user without organization
- **WHEN** a Super Admin sends POST /api/v1/users with email and password
- **THEN** the system creates the user account (not assigned to any organization)

#### Scenario: Super Admin creates user with organization
- **WHEN** a Super Admin sends POST /api/v1/users with email, password, organization_id, and organization_role
- **THEN** the system creates the user AND adds them to the specified organization with the specified role

#### Scenario: Email already exists
- **WHEN** creating a user with an email that already exists
- **THEN** the system MUST return 400 with "Email already exists" message

#### Scenario: Invalid organization when creating user
- **WHEN** a Super Admin creates user with non-existent organization_id
- **THEN** the system MUST return 404 with "Organization not found" message

### Requirement: Org Admin can create users in their organization
The system SHALL allow Org Admin to create new user accounts that are automatically added to their organization.

#### Scenario: Org Admin creates user
- **WHEN** an Org Admin sends POST /api/v1/users with email, password, and organization_id (their org)
- **THEN** the system creates the user AND adds them to that organization

#### Scenario: Org Admin must specify organization
- **WHEN** an Org Admin sends POST /api/v1/users without organization_id
- **THEN** the system MUST return 400 with "Organization ID required" message

#### Scenario: Org Admin cannot create for other organizations
- **WHEN** an Org Admin sends POST /api/v1/users with organization_id of another organization
- **THEN** the system MUST return 403 Forbidden

#### Scenario: Org Admin cannot create Super Admin
- **WHEN** an Org Admin tries to create a user with system role SUPER_ADMIN
- **THEN** the system MUST return 403 Forbidden

### Requirement: Admin can list users
The system SHALL allow admins to list users within their scope.

#### Scenario: Super Admin lists all users
- **WHEN** a Super Admin sends GET /api/v1/users
- **THEN** the system returns all users in the system

#### Scenario: Super Admin filters users by organization
- **WHEN** a Super Admin sends GET /api/v1/users?organization_id={org_id}
- **THEN** the system returns only users who are members of that organization

#### Scenario: Org Admin lists users in their organization
- **WHEN** an Org Admin sends GET /api/v1/users with organization_id of their org
- **THEN** the system returns users who are members of that organization

#### Scenario: Org Admin cannot list users without org filter
- **WHEN** an Org Admin sends GET /api/v1/users without organization_id
- **THEN** the system MUST return 400 with "Organization ID required" message

### Requirement: User can view their profile
The system SHALL allow users to view their own profile information.

#### Scenario: User gets their profile
- **WHEN** a user sends GET /api/v1/users/me
- **THEN** the system returns the user's profile (id, email, role, is_active, created_at)

### Requirement: Admin can view user details
The system SHALL allow admins to view details of users within their scope.

#### Scenario: Super Admin views any user
- **WHEN** a Super Admin sends GET /api/v1/users/{user_id}
- **THEN** the system returns the user's details

#### Scenario: Org Admin views user in their organization
- **WHEN** an Org Admin sends GET /api/v1/users/{user_id} for a user in their organization
- **THEN** the system returns the user's details

#### Scenario: Org Admin cannot view user outside their organization
- **WHEN** an Org Admin sends GET /api/v1/users/{user_id} for a user not in their organization
- **THEN** the system MUST return 403 Forbidden

### Requirement: Admin can deactivate users
The system SHALL allow admins to deactivate user accounts within their scope.

#### Scenario: Super Admin deactivates user
- **WHEN** a Super Admin sends PATCH /api/v1/users/{user_id} with is_active=false
- **THEN** the user account is deactivated and cannot login

#### Scenario: Org Admin deactivates user in their organization
- **WHEN** an Org Admin sends PATCH /api/v1/users/{user_id} with is_active=false for a user in their org
- **THEN** the user account is deactivated

#### Scenario: Cannot deactivate yourself
- **WHEN** an admin tries to deactivate their own account
- **THEN** the system MUST return 400 with "Cannot deactivate yourself" message

### Requirement: Admin can reset user password
The system SHALL allow admins to reset a user's password within their scope.

#### Scenario: Super Admin resets password
- **WHEN** a Super Admin sends POST /api/v1/users/{user_id}/reset-password with new_password
- **THEN** the user's password is updated

#### Scenario: Org Admin resets password for user in their org
- **WHEN** an Org Admin sends POST /api/v1/users/{user_id}/reset-password for a user in their org
- **THEN** the user's password is updated

### Requirement: User can change their own password
The system SHALL allow users to change their own password.

#### Scenario: User changes password
- **WHEN** a user sends POST /api/v1/auth/change-password with current_password and new_password
- **THEN** the system verifies current password and updates to new password

#### Scenario: Wrong current password
- **WHEN** a user sends change-password with incorrect current_password
- **THEN** the system MUST return 400 with "Current password is incorrect" message

#### Scenario: Password requirements
- **WHEN** changing password with new_password less than 8 characters
- **THEN** the system MUST return 400 with validation error
