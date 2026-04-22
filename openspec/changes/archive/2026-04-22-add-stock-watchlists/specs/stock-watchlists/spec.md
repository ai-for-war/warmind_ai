## ADDED Requirements

### Requirement: Stock watchlist APIs follow the existing authenticated organization request model
The system SHALL provide stock watchlist APIs that require an active user and a
valid `X-Organization-ID` request context, consistent with the existing
organization-scoped API contract. Watchlists MUST be scoped by the combination
of `user + organization` and MUST NOT be shared automatically across
organizations.

#### Scenario: Access watchlists within a valid organization context
- **WHEN** an authenticated active user calls a stock watchlist API with a valid `X-Organization-ID`
- **THEN** the system processes the request within that user's scope for the specified organization

#### Scenario: Reject watchlist requests without valid organization access
- **WHEN** a request to a stock watchlist API omits `X-Organization-ID` or the caller does not have access to that organization
- **THEN** the system MUST reject the request

### Requirement: Users can create, list, rename, and delete named stock watchlists
The system SHALL allow a user to manage multiple named stock watchlists inside
the current organization context through dedicated watchlist endpoints. The
system MUST enforce watchlist-name uniqueness per `user + organization`.

#### Scenario: Create a new watchlist with a unique name
- **WHEN** a user creates a watchlist with a name that is not already used by that same user in the current organization
- **THEN** the system creates the watchlist

#### Scenario: Reject a duplicate watchlist name in the same user and organization scope
- **WHEN** a user creates or renames a watchlist to a name already used by that same user in the current organization
- **THEN** the system MUST reject the request

#### Scenario: List the current user's watchlists in one organization
- **WHEN** a user requests the watchlist list endpoint in one valid organization context
- **THEN** the system returns only that user's watchlists for that organization

#### Scenario: Rename an existing watchlist
- **WHEN** a user renames one of their existing watchlists to a unique new name inside the same organization
- **THEN** the system updates that watchlist name

#### Scenario: Delete an existing watchlist
- **WHEN** a user deletes one of their existing watchlists
- **THEN** the system removes that watchlist

### Requirement: Users can add and remove stock symbols within one watchlist
The system SHALL allow a user to add and remove stock symbols within one of
their watchlists. The system MUST normalize symbols into canonical uppercase
form, MUST validate the symbol against the persisted stock catalog before
insertion, and MUST enforce uniqueness of a symbol within one watchlist.

#### Scenario: Add a valid stock symbol to a watchlist
- **WHEN** a user adds a stock symbol that exists in the persisted stock catalog to one of their watchlists
- **THEN** the system stores that symbol in the watchlist

#### Scenario: Reject an unknown stock symbol
- **WHEN** a user adds a symbol that does not exist in the persisted stock catalog
- **THEN** the system MUST reject the request

#### Scenario: Reject a duplicate symbol inside one watchlist
- **WHEN** a user adds a symbol that already exists in the same watchlist
- **THEN** the system MUST reject the request

#### Scenario: Allow the same symbol in different watchlists
- **WHEN** a user adds the same valid symbol to a different watchlist in the same organization
- **THEN** the system stores the symbol in that other watchlist

#### Scenario: Remove a symbol from a watchlist
- **WHEN** a user removes an existing symbol from one of their watchlists
- **THEN** the system deletes that watchlist item

### Requirement: Watchlist item reads merge saved items with the latest persisted stock catalog data
The system SHALL return watchlist items through a dedicated watchlist-item read
endpoint. Each returned item MUST include the saved watchlist-item metadata and
MUST merge the latest available stock metadata from the persisted stock catalog
at read time. The system MUST NOT require save-time stock snapshots to serve
watchlist item reads.

#### Scenario: Return a watchlist item with the latest catalog metadata
- **WHEN** a user requests the items of a watchlist containing a symbol that exists in the current persisted stock catalog
- **THEN** the response includes that saved item and the latest stock metadata resolved from the catalog for that symbol

#### Scenario: Watchlist reads do not depend on save-time stock snapshots
- **WHEN** a user requests watchlist items after the stock catalog has been refreshed
- **THEN** the system resolves stock metadata from the latest persisted catalog instead of from save-time watchlist snapshots

### Requirement: Watchlist items are returned in newest-saved-first order
The system SHALL return watchlist items ordered by most recent save time first.

#### Scenario: List watchlist items by newest save time
- **WHEN** a watchlist contains multiple saved stock symbols with different save timestamps
- **THEN** the system returns those watchlist items ordered from newest `saved_at` to oldest `saved_at`

### Requirement: Watchlist ownership is enforced for all write and read-item operations
The system SHALL ensure that a user can operate only on watchlists they own
within the current organization context. Read, rename, delete, add-item, and
remove-item operations MUST reject access to another user's watchlist in the
same organization.

#### Scenario: Operate on an owned watchlist
- **WHEN** a user performs a read or write operation on a watchlist they own in the current organization
- **THEN** the system processes that operation

#### Scenario: Reject access to another user's watchlist
- **WHEN** a user performs a read or write operation on a watchlist owned by another user in the same organization
- **THEN** the system MUST reject the request

### Requirement: Deleting a watchlist removes its watchlist items
The system SHALL remove watchlist items associated with a watchlist when that
watchlist is deleted.

#### Scenario: Delete a watchlist and its items
- **WHEN** a user deletes an existing watchlist that contains saved symbols
- **THEN** the system removes the watchlist
- **AND** the system removes the saved symbols associated with that watchlist
