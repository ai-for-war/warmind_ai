## ADDED Requirements

### Requirement: Organization entity exists
The system SHALL support Organization as a first-class entity representing a company in the multi-tenant SaaS architecture.

An Organization SHALL have the following attributes:
- `id`: Unique identifier
- `name`: Display name of the organization
- `slug`: URL-friendly unique identifier (kebab-case)
- `description`: Optional description
- `is_active`: Boolean status (default: true)
- `created_by`: Reference to Super Admin who created it
- `created_at`: Timestamp
- `updated_at`: Timestamp

#### Scenario: Organization has required fields
- **WHEN** an Organization is created
- **THEN** it MUST have id, name, slug, is_active, created_by, created_at, and updated_at fields

#### Scenario: Organization slug is unique
- **WHEN** an Organization is created with a slug that already exists
- **THEN** the system MUST reject the creation with an error

### Requirement: Super Admin can create organizations
The system SHALL allow only users with SUPER_ADMIN role to create new organizations.

#### Scenario: Super Admin creates organization successfully
- **WHEN** a Super Admin sends POST /api/v1/organizations with valid name
- **THEN** the system creates the organization with auto-generated slug and returns the organization details

#### Scenario: Non-Super Admin cannot create organization
- **WHEN** a user without SUPER_ADMIN role sends POST /api/v1/organizations
- **THEN** the system MUST return 403 Forbidden

#### Scenario: Organization name generates unique slug
- **WHEN** a Super Admin creates organization with name "Acme Corporation"
- **THEN** the system generates slug "acme-corporation" (or with suffix if already exists)

### Requirement: Super Admin can list all organizations
The system SHALL allow Super Admin to retrieve a list of all organizations in the system.

#### Scenario: Super Admin lists all organizations
- **WHEN** a Super Admin sends GET /api/v1/organizations
- **THEN** the system returns a paginated list of all organizations

#### Scenario: Regular user cannot list all organizations
- **WHEN** a non-Super Admin sends GET /api/v1/organizations
- **THEN** the system MUST return 403 Forbidden

### Requirement: Super Admin can view organization details
The system SHALL allow Super Admin to view details of any organization.

#### Scenario: Super Admin views organization by ID
- **WHEN** a Super Admin sends GET /api/v1/organizations/{org_id}
- **THEN** the system returns the organization details including member count

#### Scenario: Organization not found
- **WHEN** any user sends GET /api/v1/organizations/{org_id} with invalid ID
- **THEN** the system MUST return 404 Not Found

### Requirement: Super Admin can update organization
The system SHALL allow Super Admin to update organization details (name, description, is_active).

#### Scenario: Super Admin updates organization name
- **WHEN** a Super Admin sends PATCH /api/v1/organizations/{org_id} with new name
- **THEN** the system updates the name and regenerates slug if needed

#### Scenario: Super Admin deactivates organization
- **WHEN** a Super Admin sends PATCH /api/v1/organizations/{org_id} with is_active=false
- **THEN** the organization is soft-deleted and members can no longer access it

### Requirement: Super Admin can delete organization
The system SHALL allow Super Admin to delete (deactivate) an organization.

#### Scenario: Super Admin deletes organization
- **WHEN** a Super Admin sends DELETE /api/v1/organizations/{org_id}
- **THEN** the system sets is_active=false (soft delete)
- **AND** all members lose access to the organization

#### Scenario: Deleted organization data is preserved
- **WHEN** an organization is deleted
- **THEN** all data (conversations, connections) within the organization MUST be preserved but inaccessible
