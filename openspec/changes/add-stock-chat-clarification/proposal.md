## Why

Users need a dedicated stock-chat entry point that can determine whether a stock question has enough context before expensive or specialized analyst agents run. This first phase reduces ambiguity by adding a clarification loop that collects missing context through natural chat history and option-based prompts, while deferring actual stock analysis to later phases.

## What Changes

- Add a dedicated authenticated stock-chat message endpoint for phase 1 intake and clarification.
- Store stock-chat conversations and messages in stock-chat-specific MongoDB collections instead of reusing the existing generic chat or lead-agent collections.
- Add a Clarification Agent that reads the full stock-chat message history and emits a user-facing socket response with a clarification list only when clarification is required.
- Persist user messages for every stock-chat turn.
- Persist assistant clarification messages only when additional context is required.
- Return the persisted `conversation_id` and `user_message_id` immediately after persisting the user turn; run clarification asynchronously and emit clarification results through Socket.IO.
- When clarification is not required, hand off to downstream processing instead of returning a readiness response to the client.
- Keep phase 1 scoped to clarification only; it MUST NOT run technical, fundamental, news, risk, or decision agents.

## Capabilities

### New Capabilities
- `stock-chat-clarification`: Dedicated stock-chat conversation intake, persistence, and clarification readiness detection.

### Modified Capabilities

None.

## Impact

- New API surface under `/api/v1/stock-chat`.
- New domain schemas and service layer for stock-chat messages, conversations, and clarification responses.
- New MongoDB collections for stock-chat conversations and stock-chat messages.
- New Clarification Agent prompt/runtime with structured output validation.
- Existing `/chat`, `/lead-agent`, and `/stock-research/reports` behavior remains unchanged.
