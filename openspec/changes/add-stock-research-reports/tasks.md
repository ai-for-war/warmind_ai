## 1. Domain and persistence foundations

- [ ] 1.1 Add stock research report domain models under `app/domain/models/` for report status, ownership, timestamps, markdown content, source metadata, and failure details
- [ ] 1.2 Add request and response schemas under `app/domain/schemas/` for create, get, and list stock research report flows
- [ ] 1.3 Add a stock research report repository under `app/repo/` with create, update lifecycle state, find-owned report, and list-by-user-and-organization behavior
- [ ] 1.4 Create MongoDB indexes for report history reads by `user + organization`, symbol-scoped history, and operational status lookups
- [ ] 1.5 Wire the new repository into `app/common/repo.py`

## 2. Research runtime and validation behavior

- [ ] 2.1 Add a dedicated stock research agent/runtime module under `app/agents/implementations/` that is separate from the existing lead-agent runtime
- [ ] 2.2 Implement web-research tool usage through the normalized `search` and `fetch_content` contract for company, industry, and macro/news evidence gathering
- [ ] 2.3 Define the research-agent output contract as markdown `content` plus `sources[]` with `source_id`, `url`, and `title`
- [ ] 2.4 Implement lightweight output validation for non-empty markdown, unique source IDs, complete source fields, and `[Sx]` reference integrity

## 3. Stock research service lifecycle

- [ ] 3.1 Add a stock research service under `app/services/` for symbol validation, report creation, lifecycle transitions, and report reads
- [ ] 3.2 Reuse the persisted stock catalog only for symbol validation before creating a report request
- [ ] 3.3 Implement `202 Accepted` create behavior that persists a queued report and schedules background processing
- [ ] 3.4 Implement background execution that advances reports through `queued`, `running`, `completed`, `partial`, and `failed`
- [ ] 3.5 Persist final markdown content and web-only `sources[]` on successful or partial runs
- [ ] 3.6 Persist failure details for unsuccessful runs without publishing broken report artifacts
- [ ] 3.7 Wire the stock research service into `app/common/service.py`

## 4. API integration

- [ ] 4.1 Add authenticated stock research report endpoints under `app/api/v1/stock_research/` for create, get, and list operations
- [ ] 4.2 Apply `get_current_active_user` and `get_current_organization_context` to all stock research report endpoints
- [ ] 4.3 Register the stock research router in the v1 router aggregation
- [ ] 4.4 Ensure get and list responses expose persisted lifecycle state and, when available, stored markdown content plus `sources[]`

## 5. Tests and verification

- [ ] 5.1 Add repository tests for report creation, ownership-scoped lookup, lifecycle updates, and history listing behavior
- [ ] 5.2 Add service tests for catalog-based symbol validation, `202` create behavior, background lifecycle transitions, partial/failure handling, and citation-reference validation
- [ ] 5.3 Add API tests for organization-auth access control, unknown-symbol rejection, accepted create responses, and owned report reads/listing
- [ ] 5.4 Add agent or service tests that verify reports may include current-price text without citations while web citations still map correctly to stored `sources[]`
