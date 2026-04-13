## Why

The current web-search integration depends on a community
`duckduckgo-mcp-server` that scrapes DuckDuckGo HTML directly and collapses
multiple failure modes into a generic "no results" response. That makes the
agent research path brittle and hard to diagnose when DuckDuckGo changes its
markup, bot detection triggers, or the upstream server returns an unexpected
tool surface.

Research confirms the official `ddgs` project now provides a maintained MCP
server with structured search and content-extraction tools, but this codebase
is tightly coupled to provider-specific tool names such as `search` and
`fetch_content`. We need to migrate to the more stable MCP provider while
preserving a stable internal tool contract for chat, data, and lead-agent
workflows.

## What Changes

- Replace the current DuckDuckGo MCP subprocess configuration with the
  official `ddgs` MCP entrypoint and its required MCP-capable package setup
- Introduce an internal normalized web-research tool contract so application
  code continues to work with stable app-level tool names like `search` and
  `fetch_content` even when the upstream MCP server exposes names such as
  `search_text` and `extract_content`
- Update MCP tool resolution, lead-agent selectable tool registration,
  chat-agent/data-agent tool loading, and lead-agent skill middleware to use
  the normalized contract instead of assuming raw upstream tool names
- Refresh system prompts and internal guidance so agent instructions describe
  the normalized research tools rather than coupling prompt text to one MCP
  provider implementation
- Add startup diagnostics and tests that verify required research tools are
  present, log the upstream mapping in use, and degrade gracefully when only a
  subset of the research tool surface is available

## Capabilities

### New Capabilities

- `agent-web-search-tools`: provide a provider-agnostic MCP web-research layer
  that normalizes search and fetch tool names, validates required research
  tools at startup, and allows the backend to swap MCP search providers
  without rewriting agent-facing prompts or runtime contracts

### Modified Capabilities

- None.

## Impact

- **Runtime behavior**: agent web research becomes less dependent on one HTML
  scraping server and more resilient to upstream provider churn
- **No public API break**: existing API routes and app-level research tool
  semantics remain the same; the migration is internal to MCP integration and
  agent runtime wiring
- **Dependency and environment changes**: MCP startup must use the `ddgs`
  package with MCP support and should preserve proxy/env-based configuration
  options for hosted environments
- **Observability**: initialization logs and health diagnostics should make it
  obvious which upstream MCP tools were loaded and how they were mapped into
  the app-level contract
- **Affected code**: `app/config/mcp.py`,
  `app/infrastructure/mcp/manager.py`,
  `app/agents/implementations/chat_agent/agent.py`,
  `app/agents/implementations/data_agent/agent.py`,
  `app/agents/implementations/lead_agent/tool_catalog.py`,
  `app/agents/implementations/lead_agent/middleware.py`,
  `app/prompts/system/chat_agent.py`,
  `app/prompts/system/data_agent.py`,
  `app/prompts/system/lead_agent.py`, and related MCP/lead-agent tests
