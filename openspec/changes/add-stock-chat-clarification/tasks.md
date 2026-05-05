## 1. Data Model and Persistence

- [ ] 1.1 Add stock-chat conversation and message domain models for dedicated collections.
- [ ] 1.2 Add stock-chat conversation and message repositories scoped by user and organization.
- [ ] 1.3 Add MongoDB indexes for stock-chat conversation ownership, organization scope, message ordering, and soft-delete filtering if soft delete is used.

## 2. API Schemas and Router

- [ ] 2.1 Add request and response schemas for `POST /stock-chat/messages`, including `clarification_required` and `ready_for_analysis` response shapes.
- [ ] 2.2 Add a dedicated stock-chat router under `/api/v1/stock-chat`.
- [ ] 2.3 Register the stock-chat router with the v1 API router.
- [ ] 2.4 Ensure invalid, inaccessible, or cross-organization `conversation_id` values are rejected before appending messages.

## 3. Clarification Agent

- [ ] 3.1 Add a stock-chat clarification system prompt that forbids stock analysis and requires one of two structured statuses.
- [ ] 3.2 Add structured output validation for clarification result, clarification question/options, and ready summary.
- [ ] 3.3 Add runtime helpers to build the stock-chat clarification model from the existing provider/model configuration patterns.
- [ ] 3.4 Ensure clarification options contain user-facing `id`, `label`, and `description` only, without backend state patch values.

## 4. Stock-Chat Service

- [ ] 4.1 Implement first-message flow that creates a stock-chat conversation, persists the user message, loads history, and invokes the Clarification Agent.
- [ ] 4.2 Implement follow-up flow that validates the stock-chat conversation, persists the user message, loads full chronological history, and invokes the Clarification Agent.
- [ ] 4.3 Persist assistant clarification messages only when the agent returns `clarification_required`.
- [ ] 4.4 Return `ready_for_analysis` without persisting an assistant message when context is sufficient.
- [ ] 4.5 Ensure phase-1 service flow does not invoke analyst, risk, report-generation, or trading agents.

## 5. Tests

- [ ] 5.1 Add API/service tests for first-message creation and dedicated stock-chat collection persistence.
- [ ] 5.2 Add tests for missing-symbol clarification response.
- [ ] 5.3 Add tests for investment-decision questions missing time horizon.
- [ ] 5.4 Add tests showing a short follow-up answer is evaluated using persisted assistant clarification history.
- [ ] 5.5 Add tests that `ready_for_analysis` returns `assistant_message_id: null` and does not persist an assistant message.
- [ ] 5.6 Add tests that stock-chat requests cannot access another user's or organization's conversation.
