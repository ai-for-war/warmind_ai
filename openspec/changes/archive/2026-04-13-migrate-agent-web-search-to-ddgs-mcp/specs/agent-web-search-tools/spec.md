## ADDED Requirements

### Requirement: Default MCP web-search provider uses the official DDGS MCP server
The system SHALL configure its default MCP web-search integration to use the
official `ddgs` MCP server instead of the current community
DuckDuckGo-specific HTML scraping server.

#### Scenario: Application starts with DDGS as the configured research provider
- **WHEN** the application initializes its MCP server configuration for web
  research
- **THEN** the configured stdio server launches the official `ddgs` MCP
  entrypoint
- **AND** the backend treats that MCP server as the default source of web
  search and content extraction tools

#### Scenario: Hosted environments preserve MCP proxy configuration
- **WHEN** the deployment environment provides proxy-related configuration for
  outbound MCP search traffic
- **THEN** the DDGS MCP integration uses that configuration when launching or
  calling the provider
- **AND** the presence of proxy support does not change the app-level research
  tool contract exposed to agents

### Requirement: MCP research tools are normalized to a stable app-level contract
The system SHALL normalize upstream MCP research tools into a stable internal
contract with the app-level tool names `search` and `fetch_content`. Agent
runtime code MUST NOT depend directly on provider-specific MCP tool names such
as `search_text` or `extract_content`.

#### Scenario: DDGS tool names are mapped into the app-level contract
- **WHEN** the upstream MCP server exposes DDGS research tools named
  `search_text` and `extract_content`
- **THEN** the backend registers an app-level research tool named `search`
- **AND** the backend registers an app-level research tool named
  `fetch_content`
- **AND** invoking `search` executes the upstream `search_text` capability
- **AND** invoking `fetch_content` executes the upstream `extract_content`
  capability

#### Scenario: Compatible upstream names remain consumable through the normalized contract
- **WHEN** an upstream MCP server already exposes tools named `search` and
  `fetch_content`
- **THEN** the backend may use those tools directly
- **AND** downstream agent code still resolves research tools only through the
  normalized app-level contract

### Requirement: Agent runtimes expose only the normalized research tool names
The system SHALL expose normalized research tool names consistently across chat
agent runtime, data agent runtime, lead-agent selectable tool registration, and
lead-agent skill-aware tool filtering.

#### Scenario: Chat, data, and lead-agent runtimes receive normalized research tools
- **WHEN** the MCP integration successfully loads research tools from the
  configured provider
- **THEN** chat-agent runtime resolves research tools by the app-level names
  `search` and `fetch_content`
- **AND** data-agent runtime resolves research tools by the app-level names
  `search` and `fetch_content`
- **AND** lead-agent runtime and selectable tool catalog expose the app-level
  names `search` and `fetch_content`

#### Scenario: Lead-agent tool filtering uses the normalized contract
- **WHEN** lead-agent middleware computes the base runtime tool surface or a
  skill-constrained tool subset
- **THEN** the filtering rules reference the normalized research tool names
  `search` and `fetch_content`
- **AND** provider-specific raw MCP tool names are not required in middleware
  policy rules

### Requirement: Research prompts and metadata remain provider-agnostic
The system SHALL describe web-research tools using the normalized app-level
contract so prompt text, runtime metadata, and selectable tool descriptors do
not leak provider-specific MCP tool names.

#### Scenario: System prompts reference normalized research tools
- **WHEN** the backend renders chat-agent, data-agent, or lead-agent research
  guidance
- **THEN** prompt instructions refer to `search` as the web-search tool
- **AND** prompt instructions refer to `fetch_content` as the web-content
  retrieval tool
- **AND** prompt text does not require the model to know provider-specific
  names such as `search_text` or `extract_content`

#### Scenario: Lead-agent selectable tool metadata stays stable after provider migration
- **WHEN** the lead-agent exposes selectable research tools for runtime or
  public catalog consumers
- **THEN** the tool metadata continues to advertise the stable app-level names
  `search` and `fetch_content`
- **AND** the display semantics remain "Web Search" and "Fetch Web Content"
  regardless of the upstream MCP provider

### Requirement: MCP startup validates research tool availability and degrades gracefully
The system SHALL validate which normalized research tools are available during
MCP initialization and SHALL degrade gracefully when only a subset of the
expected research tool surface is loaded.

#### Scenario: Startup records a complete normalized mapping
- **WHEN** MCP initialization loads provider tools that satisfy both
  normalized research capabilities
- **THEN** the backend records that `search` and `fetch_content` are available
- **AND** startup diagnostics identify which upstream MCP tools were mapped
  into each normalized capability

#### Scenario: Missing research tools do not crash agent initialization
- **WHEN** MCP initialization loads only one or none of the normalized
  research capabilities
- **THEN** the backend initializes successfully without crashing
- **AND** only the available normalized research tools are exposed to agents
- **AND** diagnostics clearly identify which normalized capabilities are
  missing
