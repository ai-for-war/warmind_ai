## Context

The current codebase already has a single integration seam for MCP-based web
research:

- `app/config/mcp.py` defines the subprocess configuration for the active MCP
  server
- `app/infrastructure/mcp/manager.py` initializes `MultiServerMCPClient` and
  exposes loaded tools to the rest of the app
- chat agent, data agent, and lead-agent runtime all fetch research tools
  through `get_mcp_tools_manager().get_tools(...)`
- lead-agent middleware and prompts assume the stable app-level tool names
  `search` and `fetch_content`

The problem is that the current provider and the app-level contract are
accidentally coupled. The existing MCP server is a community
DuckDuckGo-specific wrapper that scrapes HTML and returns a generic "no
results" message when multiple failure modes occur. Research also confirmed
that the official `ddgs` project now exposes a maintained MCP server, but it
uses different upstream tool names such as `search_text` and
`extract_content`.

This migration is cross-cutting because it touches MCP startup, runtime tool
selection, prompt guidance, middleware policy, and tests. It also changes an
external dependency boundary, so documenting the design before implementation
is worthwhile.

## Goals / Non-Goals

**Goals:**
- Move the default MCP web-research provider to the official `ddgs` MCP server
- Preserve a stable app-level research contract for agents using the names
  `search` and `fetch_content`
- Keep agent code, middleware rules, and prompt text provider-agnostic
- Make startup diagnostics clearly report which upstream tools were loaded and
  how they were mapped
- Degrade gracefully if one normalized research capability is unavailable
- Keep the rollout internal-only with no public API changes

**Non-Goals:**
- Expose every DDGS MCP tool immediately, such as `search_news`,
  `search_images`, or `search_videos`
- Build a separate custom MCP server just to rename tools
- Redesign the overall MCP manager abstraction for arbitrary provider
  ecosystems
- Introduce frontend-visible provider selection
- Guarantee provider-independent formatting for every raw upstream payload in
  phase 1

## Decisions

### D1: Switch the default MCP subprocess to DDGS, but keep the app-level contract unchanged

**Decision**: The default web-research MCP server will be changed from
`duckduckgo-mcp-server` to the official `ddgs` MCP entrypoint. The application
will continue to present `search` and `fetch_content` as the only normalized
research tools consumed by agents.

Recommended runtime command:

- launch `ddgs mcp` through an installation path that includes MCP extras
- if `uvx` remains the launcher, use a form equivalent to installing
  `ddgs[mcp]` before running `ddgs mcp`

**Rationale**:
- this captures the stability benefit of the maintained upstream project
  without forcing every caller to learn DDGS-specific tool names
- the current app already treats `search` and `fetch_content` as the
  conceptual contract, so preserving those names minimizes code churn

**Alternatives considered:**
- **Only change the subprocess command and use raw DDGS names everywhere**:
  rejected because chat agent, data agent, lead-agent middleware, and prompts
  all currently depend on the app-level names
- **Keep the current community server and tune retries/rate limits**: rejected
  because the root issue is a brittle HTML-scraping provider boundary, not
  just retry policy

### D2: Add a normalization layer inside the MCP manager boundary

**Decision**: Tool normalization will happen inside the existing MCP
infrastructure boundary rather than in each agent. `MCPToolsManager` will load
raw MCP tools first, then build a normalized research-tool view before handing
tools to the rest of the application.

Recommended structure:

- keep raw loaded tools privately in the manager for diagnostics
- add a small normalization module such as
  `app/infrastructure/mcp/research_tools.py`
- define the stable research capabilities centrally, for example:
  - `search` → candidates `["search", "search_text"]`
  - `fetch_content` → candidates `["fetch_content", "extract_content"]`
- expose normalized tools through the manager's public `get_tools(...)` path

**Rationale**:
- one place defines the contract and mapping rules
- callers stay simple and no longer need to know which provider is active
- middleware and prompts can continue using app-level semantics instead of
  provider-specific branches

**Alternatives considered:**
- **Normalize in each agent module**: rejected because it duplicates mapping
  logic and would leave middleware/tests coupled to upstream names
- **Normalize only in prompt text**: rejected because runtime policy also
  depends on tool names, not just prose guidance

### D3: Use thin delegating tool wrappers for renamed capabilities

**Decision**: When the provider exposes a capability under a non-standard
name, the backend will create a thin delegating wrapper tool whose public name
matches the app-level contract and whose execution forwards to the upstream
tool.

Recommended wrapper behavior:

- preserve the public tool name as `search` or `fetch_content`
- reuse the upstream description where possible, with small contract-specific
  wording if needed
- preserve the upstream argument schema whenever it is already compatible
- delegate execution to the selected upstream tool without requiring the model
  to know the raw provider name

For DDGS specifically:

- `search` will delegate to `search_text`
- `fetch_content` will delegate to `extract_content`

**Rationale**:
- the wrapper is the smallest implementation that hides provider naming
  differences while keeping MCP as the real execution backend
- it avoids creating a second server process or a translation hop outside the
  application

**Alternatives considered:**
- **Rename raw tool objects in place**: rejected because third-party tool
  implementations may not safely support post-load mutation
- **Create a custom proxy MCP server**: rejected because it adds another
  runtime component when an in-process adapter is enough

### D4: Keep the normalized surface intentionally narrow in phase 1

**Decision**: Phase 1 will normalize only the two capabilities already assumed
by the application: `search` and `fetch_content`. Extra DDGS capabilities such
as image, news, video, or book search will not be surfaced through
`get_tools(...)` until the product explicitly needs them.

**Rationale**:
- the app, prompts, and tests already center on a narrow research workflow:
  search first, then fetch a chosen URL
- exposing more tools immediately would change model behavior and make the
  migration harder to reason about
- the normalization layer should first stabilize the existing workflow before
  broadening the tool surface

**Alternatives considered:**
- **Expose all DDGS tools immediately**: rejected because it expands runtime
  behavior beyond the scope of this migration and would require prompt and eval
  retuning
- **Hide DDGS extras forever**: rejected because the architecture should leave
  room to normalize more capabilities later

### D5: Treat result-shape differences as an adapter concern, but only where needed for runtime compatibility

**Decision**: The primary compatibility guarantee in phase 1 is the app-level
tool identity and availability contract, not a perfect byte-for-byte match of
legacy provider outputs. The wrapper layer may adapt obvious field differences
when it materially improves runtime compatibility, but it will not introduce a
large transformation subsystem unless tests or execution quality prove it is
necessary.

Recommended approach:

- preserve invocation semantics first
- prefer structured DDGS outputs over lossy stringification
- keep prompt text generic enough that agents can work with either structured
  results or extracted content
- add tests around the normalized contract rather than the raw upstream shape

**Rationale**:
- the current system already has weak guarantees around MCP payload shape
- DDGS returning structured data is generally a quality improvement for agent
  reasoning
- over-specifying output conversion up front would add complexity before we
  know which fields the runtime truly depends on

**Alternatives considered:**
- **Fully normalize every output into a custom schema immediately**: rejected
  for phase 1 because it adds a larger translation layer than the migration
  strictly requires
- **Pass through every raw payload with no thought to compatibility**:
  rejected because some light adaptation and testing are still needed to keep
  the runtime predictable

### D6: Make diagnostics first-class during MCP initialization

**Decision**: MCP initialization will record both the raw provider tools and
the normalized research capabilities that were successfully built from them.
Diagnostic logs should make it obvious whether the system loaded:

- both normalized capabilities
- only one normalized capability
- no usable normalized research tools

Recommended startup information:

- active MCP server name and command
- raw tool names returned by the provider
- normalized mapping chosen for each app-level capability
- missing normalized capabilities

**Rationale**:
- the current failure mode is opaque; operators need to distinguish "provider
  process failed", "tool names changed", and "search returned no results"
- clear mapping diagnostics make future provider swaps much easier

**Alternatives considered:**
- **Rely on existing generic MCP initialization logs only**: rejected because
  they do not explain whether the loaded tools satisfy the app's research
  contract

### D7: Preserve graceful degradation instead of failing application startup

**Decision**: Missing research capabilities will not crash the application.
If MCP initializes with only `search`, only `fetch_content`, or neither, the
manager will expose the subset it can satisfy and the affected agents will
continue running with fewer tools.

Expected behavior:

- startup succeeds even with partial normalized mapping
- tool catalogs expose only available normalized tools
- prompts remain static, but runtime logs clearly note missing capabilities
- existing application behavior of "continue without MCP tools" remains intact

**Rationale**:
- the application already treats MCP as optional infrastructure
- production resilience is more important than strict startup failure for this
  class of dependency

**Alternatives considered:**
- **Hard-fail startup if either normalized capability is missing**: rejected
  because it would turn an optional external dependency into a full app outage
- **Silently ignore missing tools**: rejected because operators need explicit
  diagnostics when the normalized contract is incomplete

## Risks / Trade-offs

- **[DDGS installation path is different from the current `uvx duckduckgo-mcp-server` flow]** → Mitigation: make the launcher command explicit in config, document the required `ddgs[mcp]` installation path, and verify startup in tests or deployment checks.
- **[Tool wrappers may expose slightly different argument or output behavior than the legacy provider]** → Mitigation: add unit tests around normalized tool selection and a focused integration test for search/fetch invocation through the manager boundary.
- **[Prompt text may still imply old provider behavior]** → Mitigation: update chat, data, and lead-agent prompts in the same change so the model is instructed against the normalized contract rather than raw provider semantics.
- **[Future providers may introduce additional naming collisions]** → Mitigation: keep the normalization table centralized and deterministic, with exact precedence rules and diagnostics for ambiguous matches.
- **[Partial tool availability could confuse operators if only one capability loads]** → Mitigation: log the normalized mapping outcome clearly and ensure catalog/runtime tests cover one-tool and zero-tool scenarios.

## Migration Plan

1. Update MCP configuration so the default research provider launches the
   official DDGS MCP server.
2. Add the normalization module and thin delegating wrappers for `search` and
   `fetch_content`.
3. Update `MCPToolsManager` to build and expose normalized research tools,
   while retaining raw-tool diagnostics internally.
4. Update chat agent, data agent, lead-agent tool catalog, and lead-agent
   middleware to rely only on the normalized contract.
5. Refresh prompts and tests to reflect the provider-agnostic research surface.
6. Deploy with DDGS as the default provider and monitor startup logs for the
   normalized mapping outcome.

Rollback strategy:

- revert the MCP configuration and normalization code in one deployment if DDGS
  proves unstable in the target environment
- because the change is internal-only and does not alter public API contracts,
  rollback should not require data migration

## Open Questions

- Do we want the normalized wrapper to reshape DDGS search results into a
  stricter app-level schema, or is preserving DDGS structured output
  sufficient for phase 1?
- Should we expose `search_news` as a normalized capability in the next
  iteration, or keep the research surface strictly limited to search plus fetch
  until post-migration evaluation?
- Do we want an env-driven provider toggle for easier runtime fallback, or is
  standard deployment rollback enough for the first release?
