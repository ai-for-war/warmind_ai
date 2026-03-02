# organization-membership Specification

## Purpose
TBD - created by archiving change add-organization-multi-tenancy. Update Purpose after archive.
## Requirements
### Requirement: Organization membership entity exists
The system SHALL support OrganizationMember as a junction entity representing the many-to-many relationship between User and Organization.

An OrganizationMember SHALL have the following attributes:
- `id`: Unique identifier
- `user_id`: Reference to the User
- `organization_id`: Reference to the Organization
- `role`: Organization-level role (ADMIN or USER)
- `added_by`: Reference to user who added this member
- `is_active`: Boolean status (default: true)
- `created_at`: Timestamp
- `updated_at`: Timestamp

#### Scenario: Membership has required fields
- **WHEN** an OrganizationMember is created
- **THEN** it MUST have id, user_id, organization_id, role, added_by, is_active, created_at, and updated_at fields

#### Scenario: User-Organization pair is unique
- **WHEN** a membership is created for a user already in the organization
- **THEN** the system MUST reject with an error (duplicate membership)

### Requirement: Organization roles are defined
The system SHALL support two organization-level roles:
- `ADMIN`: Can manage members within the organization
- `USER`: Can access and create data within the organization

#### Scenario: Valid organization roles
- **WHEN** setting a membership role
- **THEN** the role MUST be either "admin" or "user"

### Requirement: Super Admin can add members to any organization
The system SHALL allow Super Admin to add any existing user to any organization with any role.

#### Scenario: Super Admin adds user to organization
- **WHEN** a Super Admin sends POST /api/v1/organizations/{org_id}/members with user_email and role
- **THEN** the system creates membership and returns the member details

#### Scenario: User not found when adding member
- **WHEN** adding a member with non-existent email
- **THEN** the system MUST return 404 with "User not found" message

#### Scenario: User already a member
- **WHEN** adding a user who is already an active member of the organization
- **THEN** the system MUST return 400 with "Already a member" message

### Requirement: Org Admin can add members to their organization
The system SHALL allow Org Admin to add existing users to their organization.

#### Scenario: Org Admin adds user to their organization
- **WHEN** an Org Admin sends POST /api/v1/organizations/{org_id}/members for their own organization
- **THEN** the system creates membership and returns the member details

#### Scenario: Org Admin cannot add to other organizations
- **WHEN** an Org Admin sends POST /api/v1/organizations/{org_id}/members for an organization they don't admin
- **THEN** the system MUST return 403 Forbidden

### Requirement: Members can view organization member list
The system SHALL allow any member of an organization to view the list of members.

#### Scenario: Member lists organization members
- **WHEN** a member sends GET /api/v1/organizations/{org_id}/members
- **THEN** the system returns list of members with their roles and join dates

#### Scenario: Non-member cannot list members
- **WHEN** a user who is not a member sends GET /api/v1/organizations/{org_id}/members
- **THEN** the system MUST return 403 Forbidden

### Requirement: Admin can change member roles
The system SHALL allow Super Admin and Org Admin to change a member's role within the organization.

#### Scenario: Org Admin changes member role
- **WHEN** an Org Admin sends PATCH /api/v1/organizations/{org_id}/members/{user_id} with new role
- **THEN** the system updates the role and returns updated membership

#### Scenario: Cannot demote yourself
- **WHEN** an Org Admin tries to change their own role to USER
- **THEN** the system MUST return 400 with "Cannot change your own role" message

### Requirement: Admin can remove members
The system SHALL allow Super Admin and Org Admin to remove members from an organization.

#### Scenario: Org Admin removes member
- **WHEN** an Org Admin sends DELETE /api/v1/organizations/{org_id}/members/{user_id}
- **THEN** the system sets membership is_active=false (soft delete)

#### Scenario: Cannot remove yourself
- **WHEN** an Admin tries to remove themselves from the organization
- **THEN** the system MUST return 400 with "Cannot remove yourself" message

#### Scenario: Removed member loses access
- **WHEN** a member is removed from an organization
- **THEN** they can no longer access any data within that organization

### Requirement: User can view their organizations
The system SHALL allow users to see all organizations they belong to.

#### Scenario: User lists their organizations
- **WHEN** a user sends GET /api/v1/users/me/organizations
- **THEN** the system returns list of organizations with their role in each

### Requirement: Organization context via header
The system SHALL use X-Organization-ID header to determine the current organization context for data operations.

#### Scenario: Valid organization context
- **WHEN** a request includes X-Organization-ID header with valid org_id
- **AND** the user is a member of that organization
- **THEN** the request proceeds with that organization context

#### Scenario: Missing organization header
- **WHEN** a data endpoint request does not include X-Organization-ID header
- **THEN** the system MUST return 400 Bad Request

#### Scenario: User not member of organization
- **WHEN** a request includes X-Organization-ID for an org the user doesn't belong to
- **THEN** the system MUST return 403 Forbidden

#### Scenario: Super Admin bypasses membership check
- **WHEN** a Super Admin includes X-Organization-ID header
- **THEN** the request proceeds regardless of membership status

