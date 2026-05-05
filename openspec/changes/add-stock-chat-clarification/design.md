## Context

The project already has multiple conversation-like paths:

- Legacy `/chat` persists generic conversations/messages and processes assistant responses asynchronously.
- `/lead-agent` persists conversation projections mapped to LangGraph threads.
- `/stock-research/reports` creates asynchronous one-symbol research report jobs.

The stock-chat feature needs a separate phase-1 entry point for conversational stock questions. The first phase is not a stock-analysis engine; it only determines whether the user's conversation has enough context to start the later analyst graph. The user has explicitly chosen a history-driven design: the Clarification Agent reads the full stock-chat message history instead of relying on backend-managed normalized request state or option value patches.

Stock-chat persistence must use dedicated MongoDB collections, not the existing generic conversation/message collections. This avoids overloading `Conversation.thread_id` or adding another discriminator to collections that already serve legacy chat and lead-agent projections.

## Goals / Non-Goals

**Goals:**

- Provide a dedicated authenticated stock-chat message endpoint.
- Persist stock-chat conversations and messages in separate collections.
- Let the Clarification Agent read full stock-chat history for each turn.
- Return structured clarification prompts with options when context is missing.
- Hand off to downstream processing when enough context exists for later analyst agents.
- Persist assistant clarification messages so short follow-up replies like "Trung hạn" retain context.
- Avoid returning or persisting a synthetic readiness assistant message, because no user-facing clarification has been produced.

**Non-Goals:**

- No technical, fundamental, news, risk, decision, or final-response agent execution in phase 1.
- No investment recommendation, price target, buy/sell/hold conclusion, or data retrieval in phase 1.
- No backend canonical normalized state machine for stock-chat clarification answers.
- No LangGraph `interrupt()`/resume implementation for phase 1.
- No stock-chat conversation list/history browsing endpoints unless a later change explicitly scopes them.

## Decisions

### Decision: Use dedicated stock-chat collections

Stock-chat will use dedicated MongoDB collections, tentatively:

- `stock_chat_conversations`
- `stock_chat_messages`

This is preferred over adding a new `kind` field to the existing `conversations` and `messages` collections because stock-chat has different persistence semantics: it does not use generic chat background response streaming, and it does not use lead-agent checkpoint-backed thread projections.

Alternative considered: reuse existing conversations/messages with a discriminator. That would reduce repository code, but it increases coupling with legacy chat and lead-agent filtering rules and risks future endpoint leakage.

### Decision: Return only clarification prompts from the clarification step

`POST /api/v1/stock-chat/messages` will persist the user message and run the Clarification Agent. If context is missing, the endpoint returns the clarification question and options in the HTTP response. If context is sufficient, the system hands off to downstream processing instead of returning a `ready_for_analysis` response to the client.

This is preferred because the client only needs to render a prompt when more context is required. A readiness-only response would expose an internal routing decision and force the frontend to handle an unnecessary terminal state.

Alternative considered: reuse the existing chat Socket.IO workflow. That adds unnecessary async lifecycle and event handling for a response that is expected to be short and structured.

### Decision: Clarification is history-driven, not state-patch-driven

The Clarification Agent will receive the full persisted stock-chat message history in chronological order. Option objects returned to the client will contain user-facing `id`, `label`, and `description`, but they will not contain backend state patches like `{"time_horizon": "short_term"}`.

The follow-up turn will be submitted as natural content, for example `Trung hạn - vài tuần đến vài tháng.` The next Clarification Agent call will infer readiness from the full history.

Alternative considered: backend-managed normalized state with option `value` patches. That would be deterministic, but it conflicts with the chosen design where downstream agents understand context from the message transcript.

### Decision: Persist assistant clarification only

When context is missing, the system will persist the assistant's clarification question and options as an assistant message. This is required so later short answers remain understandable from history.

When context is sufficient, the system will not persist an assistant message for clarification and will hand off internally. No assistant answer has been produced at this point, and persisting a synthetic readiness message would pollute the transcript that later analyst agents read.

### Decision: Structured output validates agent behavior

The Clarification Agent will use a strict structured output schema with:

- `status`: `clarification_required` or `continue`
- `clarification`: required only for `clarification_required`
- no user-facing payload for `continue`

The prompt will forbid stock analysis and require the agent to ask at most one clarification question per turn. The service will validate the structured output before persisting or returning it.

### Decision: Minimal readiness policy for phase 1

The Clarification Agent should prioritize missing context in this order:

1. Stock symbol/company identity.
2. User intent.
3. Time horizon, but only when the user is asking for an investment decision such as buy, sell, hold, or "có nên mua không".

Risk profile, capital, current position, and preferred analysis depth are optional in phase 1.

## Risks / Trade-offs

- History-driven interpretation can be less deterministic than backend state patches -> mitigate with structured output validation, a narrow prompt, persisted assistant clarification turns, and focused tests for short follow-up answers.
- Separate collections add repository and schema code -> mitigate by keeping the collection model small and scoped to phase-1 needs.
- Synchronous LLM calls can increase endpoint latency -> mitigate by keeping the prompt small, limiting history length if needed, and avoiding tool calls or analyst execution.
- The Clarification Agent may accidentally provide analysis -> mitigate through prompt rules, response schema constraints, and tests that assert only clarification prompts are user-facing.
- Future analyst agents may need a canonical summary -> mitigate in the downstream analysis flow while still treating message history as the source of context.

## Migration Plan

No existing data migration is required. Deploying the change creates new code paths and writes only to new stock-chat collections.

Rollback is straightforward: remove or disable the `/stock-chat` router. Existing legacy chat, lead-agent, and stock-research report data remain unaffected because they use separate routes and collections.

## Open Questions

None for phase 1.
