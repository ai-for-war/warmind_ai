## Why

The backend already exposes raw stock catalog, company, and price endpoints,
but it still lacks a first-class research workflow that can turn stock-related
web evidence into a user-consumable report. Product now needs an asynchronous
stock research capability so users can request one Vietnam stock symbol, wait
for background processing, and later read a persisted markdown report with
source links and recommendation-oriented analysis.

## What Changes

- Add a new authenticated stock research report capability under a dedicated
  API surface instead of overloading the existing `/stocks`, `/analytics`, or
  `/lead-agent` routes
- Accept one Vietnam stock symbol per request, validate it against the
  persisted stock catalog, create a report job, and return `202 Accepted`
  immediately
- Run a dedicated background research-agent workflow that gathers web-based
  evidence about the company, industry, macro context, and world news impact
- Persist the final report as markdown `content` plus a `sources[]` list with
  `source_id`, `url`, and `title`
- Expose read APIs for report status, completed content, source metadata, and
  list history
- Support report lifecycle states such as queued, running, completed, partial,
  and failed

## Capabilities

### New Capabilities
- `stock-research-reports`: request, run, persist, and read asynchronous stock
  research reports for one catalog-validated Vietnam stock symbol, with
  markdown output and web-source citations

### Modified Capabilities
- None.

## Impact

- **Affected APIs**: adds authenticated stock research report endpoints under a
  new `/api/v1/stock-research/reports` route group for create, get, and list
  flows
- **Affected code**: new domain models, schemas, repositories, services,
  router wiring, and research-agent runtime modules under `app/domain/`,
  `app/repo/`, `app/services/`, `app/agents/`, `app/common/`, and `app/api/v1/`
- **Persistence**: introduces a dedicated MongoDB collection for stock
  research reports and their stored markdown/source artifacts
- **Background processing**: adds asynchronous report execution that reuses the
  existing FastAPI background-task pattern rather than blocking the request
  path
- **Dependencies**: depends on the existing stock symbol catalog for input
  validation and the existing MCP web research tool contract for web search and
  content fetching
