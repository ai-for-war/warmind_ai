## 1. DDGS MCP Provider Setup

- [x] 1.1 Update the MCP server configuration in `app/config/mcp.py` so the default web-research provider launches the official `ddgs` MCP entrypoint instead of `duckduckgo-mcp-server`
- [x] 1.2 Add or update dependency and environment setup notes needed for running `ddgs mcp` with MCP support in local and deployed environments
- [x] 1.3 Verify the configured provider can still honor proxy-related environment settings without changing the app-level research tool contract

## 2. Normalized Research Tool Adapter

- [x] 2.1 Add a dedicated MCP research-tool normalization module under `app/infrastructure/mcp/` that defines the stable app-level capabilities `search` and `fetch_content`
- [x] 2.2 Implement candidate-name resolution rules so `search` can map to `search` or `search_text` and `fetch_content` can map to `fetch_content` or `extract_content`
- [x] 2.3 Implement thin delegating wrapper tools that expose the normalized public names while forwarding execution to the selected upstream MCP tool
- [x] 2.4 Update `MCPToolsManager` to retain raw loaded tools for diagnostics and expose normalized research tools through its public `get_tools(...)` path

## 3. Agent Runtime And Prompt Integration

- [x] 3.1 Update chat-agent and data-agent MCP tool loading so both runtimes consume only the normalized research tool names
- [x] 3.2 Update lead-agent selectable tool registration and runtime tool catalog so they advertise and resolve only `search` and `fetch_content`
- [x] 3.3 Update lead-agent middleware base-tool rules so research-tool filtering depends only on the normalized contract and not raw provider names
- [x] 3.4 Refresh chat-agent, data-agent, and lead-agent prompt text so research guidance remains provider-agnostic and aligned with the normalized tool surface

## 4. Diagnostics And Graceful Degradation

- [ ] 4.1 Add MCP initialization diagnostics that log the active provider, raw upstream tool names, normalized mappings, and any missing normalized capabilities
- [ ] 4.2 Ensure the MCP manager degrades gracefully when only one normalized research tool or no normalized research tools are available
- [ ] 4.3 Verify selectable tool catalogs and agent runtime wiring expose only the normalized capabilities that were actually loaded

## 5. Verification And Regression Coverage

- [ ] 5.1 Add unit tests for research-tool normalization, including DDGS name mapping, direct-name passthrough, and missing-tool cases
- [ ] 5.2 Update or add tests for chat-agent, data-agent, and lead-agent tool loading so they continue to resolve `search` and `fetch_content` after the provider migration
- [ ] 5.3 Add tests for lead-agent middleware and selectable tool metadata to confirm provider-specific raw names do not leak into runtime policy or public catalog output
- [ ] 5.4 Run targeted verification for MCP initialization, partial-tool degradation, and the existing research-enabled agent flows to confirm the migration stays additive
