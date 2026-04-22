## Context

The backend already has the main building blocks needed for a stock research
feature, but they are still separated by responsibility:

- `/api/v1/stocks` exposes authenticated raw stock reads and symbol validation
- `/api/v1/ai/lead-agent` already uses a `202 + background processing` pattern
  with persisted projection records
- MCP web-research tools already expose the normalized `search` and
  `fetch_content` contract

The requested feature is cross-cutting because it adds a new user-facing stock
workflow that spans API design, persistence, background execution, agent
runtime behavior, and web-source citation handling. Product decisions already
confirmed for this change are:

- the feature uses a dedicated agent/runtime instead of the existing lead-agent
- `POST` requests return `202 Accepted` immediately and run the report in the
  background
- one request targets one Vietnam stock symbol
- the stock symbol must be validated against the persisted stock catalog
- the final artifact is markdown report content plus `sources[]`
- citations are web-only and use `source_id` references such as `[S1]`
- source objects include only `source_id`, `url`, and `title`
- current-price statements may appear in the report without citations
- report history must be persisted and readable later

This change therefore needs a dedicated capability rather than extending the
existing stock raw-data endpoints, the current analytics module, or the
lead-agent conversation surface.

## Goals / Non-Goals

**Goals:**
- Add a dedicated authenticated stock research report API surface
- Accept one stock symbol, validate it, create a report record, and return
  `202 Accepted` without blocking on generation
- Run a background research-agent workflow that collects web evidence and
  generates a markdown report plus `sources[]`
- Persist report lifecycle state and stored artifacts for later retrieval
- Keep citations lightweight but deterministic by requiring `[Sx]` references
  that map to `sources[]`

**Non-Goals:**
- Reuse the existing lead-agent conversation model or chat history projection
- Add a fully structured analytics artifact beyond markdown report content and
  source metadata
- Expose internal stock-service responses as citation sources in v1
- Add portfolio logic, target-price modeling, or numerical valuation engines
- Add multi-symbol batch research, portfolio-wide research, or scheduled
  research jobs
- Add rerun behavior for previously completed reports
- Add user-selectable runtime/provider/model settings in v1

## Decisions

### D1: Add a dedicated stock research report route group and service stack

**Decision**: Introduce a separate route group under
`/api/v1/stock-research/reports` backed by dedicated schemas, repository,
service, and agent-runtime modules.

**Rationale**:
- the feature is not a raw stock-data read, so adding it under `/stocks` would
  blur the boundary between deterministic market data and generated research
- the current `/analytics` module is tied to sheet analytics and is not the
  right semantic home for an agent-generated stock report
- the feature is not conversational, so forcing it into lead-agent projection
  records would add unnecessary coupling

**Alternatives considered:**
- **Add a `/stocks/{symbol}/research` endpoint**: rejected because this
  capability is asynchronous, persisted, and job-like rather than a simple
  stock detail read
- **Reuse `/lead-agent/messages`**: rejected because the user explicitly wants
  a separate agent/runtime and the output is a report artifact rather than a
  conversation turn
- **Put the feature under `/analytics`**: rejected because it would overload an
  existing module that currently represents deterministic data analysis over
  synced sheets

### D2: Use `202 Accepted` plus background execution with persisted lifecycle state

**Decision**: `POST /stock-research/reports` will validate the symbol, create a
report document with status `queued`, return `202 Accepted`, and enqueue a
background task that advances the report through `running`, terminal success,
or failure states.

Recommended status set:

- `queued`
- `running`
- `completed`
- `partial`
- `failed`

**Rationale**:
- stock research is latency-heavy because it requires multiple web lookups and
  LLM synthesis
- the repo already uses asynchronous background processing for long-running AI
  work, so this aligns with established runtime behavior
- persisted lifecycle state makes list/history behavior straightforward

**Alternatives considered:**
- **Hold the HTTP request open until the report completes**: rejected because
  it is brittle under slow research runs and scales poorly
- **Run through an external queue first**: rejected for v1 because the existing
  background-task pattern is sufficient for the first implementation

### D3: Persist one report document that stores both generation state and final artifact

**Decision**: Introduce a dedicated MongoDB-backed report model that stores
report identity, caller scope, stock symbol, status, timestamps, final markdown
content, source metadata, and failure details in one document.

Recommended shape:

```json
{
  "_id": "report_id",
  "user_id": "user-1",
  "organization_id": "org-1",
  "symbol": "FPT",
  "status": "queued",
  "content": null,
  "sources": [],
  "error": null,
  "created_at": "2026-04-21T08:00:00Z",
  "started_at": null,
  "completed_at": null,
  "updated_at": "2026-04-21T08:00:00Z"
}
```

Recommended indexes:

- index `(user_id, organization_id, created_at desc)` for history reads
- index `(organization_id, symbol, created_at desc)` for symbol-scoped history
- optional index `(status, updated_at)` for operations/diagnostics

**Rationale**:
- one-document persistence is enough for v1 because the artifact is small
- reads become simple because the API returns the same persisted object shape
  regardless of whether the report is queued, running, or completed
- one stored document is sufficient because v1 does not include rerun behavior
  or derived report revisions

**Alternatives considered:**
- **Separate source collection**: rejected for v1 because source rows are only
  meaningful within one report and do not need independent lifecycle
- **Conversation/message projection like lead-agent**: rejected because the
  output is a single report artifact, not a multi-turn dialogue

### D4: Keep citations web-only and represent them as `content + sources[]`

**Decision**: The research agent will return a payload with:

- `content`: markdown report body
- `sources`: array of `{source_id, url, title}`

The markdown content will cite sources using `[S1]`, `[S2]`, and similar
tokens that must map to one entry in `sources[]`. Internal stock-service data
will not be represented as citation sources in v1, and current-price
statements may appear without citations.

**Rationale**:
- this keeps the artifact small and matches the product choice to avoid a
  larger structured output
- citation IDs are easier to validate and deduplicate than arbitrary inline
  markdown links scattered throughout the report
- excluding internal data citations avoids introducing pseudo-URL rules the
  user did not want

**Alternatives considered:**
- **Markdown-only with inline `[]()` links and no separate sources array**:
  rejected because it is harder to validate and deduplicate at the backend
- **Full structured report with recommendation/confidence metadata**: rejected
  for v1 because the user explicitly chose a lightweight artifact
- **Include internal data as citation sources**: rejected because the user
  explicitly wants citations to be web-only

### D5: Validate report output lightly before marking a run successful

**Decision**: The service layer will apply lightweight validation to the agent
result before setting a report to `completed` or `partial`:

1. `content` must be non-empty markdown text
2. each source must include non-blank `source_id`, `url`, and `title`
3. `source_id` values must be unique within the report
4. every `[Sx]` reference found in `content` must map to one source entry

If research partially succeeds but still produces a usable report, the system
may persist it as `partial`.

**Rationale**:
- even without a structured analytics artifact, the backend still needs a
  minimum integrity gate before publishing generated output
- lightweight validation is enough to catch broken references without
  over-designing the v1 report format

**Alternatives considered:**
- **Trust model output blindly**: rejected because missing or broken citations
  would degrade the contract immediately
- **Require deep semantic citation-to-claim validation**: rejected for v1
  because it is expensive and not necessary to launch the feature

### D6: Use the stock symbol catalog only for request validation, not report citations

**Decision**: The stock symbol catalog remains the authoritative gate for
whether a requested symbol is valid, but stock catalog, company, or price
services will not be used as citation sources in the generated report.

**Rationale**:
- symbol validation must remain deterministic and cheap
- the user explicitly chose not to represent internal sources in `sources[]`
- this keeps v1 aligned with the requested web-only citation policy

**Alternatives considered:**
- **Skip catalog validation and rely on web search alone**: rejected because it
  weakens the product contract for Vietnam stock symbols
- **Use internal stock services as both validation and citation inputs**:
  rejected because it conflicts with the agreed citation format

## Risks / Trade-offs

**[Web-only evidence can produce less stable current-price context than internal stock data]** ->
Mitigation: keep catalog validation deterministic, allow current-price text
without citation, and treat web research as the evidence source of record for
v1.

**[Markdown-only artifacts are harder to aggregate later than structured output]** ->
Mitigation: keep the stored report envelope stable and leave room to add
derived metadata later without changing the v1 content contract.

**[Background tasks can be interrupted by process restarts]** -> Mitigation:
persist `queued` and `running` state clearly so interrupted jobs are observable
and can be investigated or retried later through future operational tooling.

**[Broken or hallucinated citations could leak into final reports]** ->
Mitigation: apply source-ID integrity validation before marking reports
successful and require citation IDs to map to stored source objects.

**[Separate stock research runtime may drift from lead-agent runtime patterns]** ->
Mitigation: reuse proven service and runtime patterns where practical, but keep
the stock research runtime isolated at the API and persistence layers.

## Migration Plan

1. Add new stock research report domain models and request/response schemas.
2. Add a dedicated stock research report repository and collection indexes.
3. Add a stock research service that handles symbol validation, lifecycle
   transitions, result validation, and read/list behavior.
4. Add a dedicated stock research agent/runtime that uses MCP web research
   tools and returns `content + sources[]`.
5. Add authenticated report routes under `/api/v1/stock-research/reports` and
   register them in the v1 router aggregation.
6. Add tests for access control, symbol validation, `202` response behavior,
   lifecycle transitions, citation integrity, and list/history reads.

**Rollback**

- remove the stock research router registration
- remove shared service/repository wiring for stock research
- stop creating new stock research reports
- optionally drop the new report collection if full cleanup is required

## Open Questions

- Does v1 need realtime socket status events in addition to polling through the
  read endpoints, or is polling alone sufficient for the first release?
