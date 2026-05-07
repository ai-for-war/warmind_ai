## 1. Delegation Contract And Registry

- [ ] 1.1 Update `DelegatedTaskInput` to require `agent_id` and remove `expected_output`.
- [ ] 1.2 Add a stock-agent subagent registry with initial entries for `general_worker` and `event_analyst`.
- [ ] 1.3 Route `general_worker` through the existing cached stock-agent worker runtime.
- [ ] 1.4 Reject unknown `agent_id` values before invoking any worker runtime.
- [ ] 1.5 Remove expected-output rendering from worker task message construction.

## 2. Event Analyst Runtime

- [ ] 2.1 Create a new `event_analyst` agent implementation module.
- [ ] 2.2 Resolve the event analyst tool surface from normalized MCP `search` and `fetch_content` only.
- [ ] 2.3 Add event analyst system prompt focused on Vietnam-listed equity events, news, catalysts, policy/regulatory, macro, and industry impact.
- [ ] 2.4 Add structured event analyst output validation for event impact package and sources.
- [ ] 2.5 Add runtime caching for event analyst workers by resolved runtime config.

## 3. Stock-Agent Orchestration Integration

- [ ] 3.1 Update `delegate_tasks` tool documentation to describe `agent_id`, `objective`, and `context`.
- [ ] 3.2 Update stock-agent orchestration prompt with available subagents and routing rules.
- [ ] 3.3 Ensure worker payload/state records the selected delegated subagent id for observability.
- [ ] 3.4 Ensure recursive delegation remains unavailable for both `general_worker` and `event_analyst`.
- [ ] 3.5 Ensure event analyst execution failures return bounded delegation failure outcomes to the parent.

## 4. Tests

- [ ] 4.1 Update delegation unit tests for the new input schema and missing `expected_output`.
- [ ] 4.2 Add tests that `general_worker` preserves existing isolated worker payload behavior.
- [ ] 4.3 Add tests that unsupported `agent_id` values are rejected without invoking a worker.
- [ ] 4.4 Add tests for event analyst tool surface containing only `search` and `fetch_content`.
- [ ] 4.5 Add tests for event analyst output validation and citation/source integrity.
- [ ] 4.6 Add middleware/prompt tests confirming stock-agent orchestration guidance lists `general_worker` and `event_analyst`.

## 5. Verification

- [ ] 5.1 Run targeted stock-agent unit tests.
- [ ] 5.2 Run targeted event analyst unit tests.
- [ ] 5.3 Run relevant integration tests for stock-agent message execution if local environment supports required services.
