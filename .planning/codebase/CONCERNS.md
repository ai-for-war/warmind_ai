# Codebase Concerns

**Analysis Date:** 2026-03-19

## Tech Debt

**Queue durability and retry semantics:**
- Issue: `app/infrastructure/redis/redis_queue.py` uses `lpop` and `blpop`, so jobs leave Redis before processing starts. `app/workers/sheet_sync_worker.py` only re-enqueues after handled failures, and `app/workers/image_generation_worker.py` marks even `ImageGenerationRetryableProviderError` as terminal failure instead of retrying.
- Files: `app/infrastructure/redis/redis_queue.py`, `app/workers/sheet_sync_worker.py`, `app/workers/image_generation_worker.py`
- Impact: Worker crash, deploy interruption, or process kill can silently lose in-flight tasks. Transient image-generation provider failures become permanent user-visible failures.
- Fix approach: Replace list-pop semantics with ack/visibility-timeout semantics such as Redis Streams or a processing queue pattern, then requeue retryable image failures with bounded attempts and dead-letter handling.

**Database constraints and indexes are incomplete:**
- Issue: `app/infrastructure/database/mongodb.py` creates indexes for a subset of collections only. Core paths still rely on application-level assumptions: `app/repo/user_repo.py` checks email uniqueness without a database unique index, and `app/repo/sheet_data_repo.py` upserts by `(connection_id, row_number)` without a supporting unique index.
- Files: `app/infrastructure/database/mongodb.py`, `app/repo/user_repo.py`, `app/services/auth/auth_service.py`, `app/services/user/user_service.py`, `app/repo/sheet_data_repo.py`, `app/repo/sheet_sync_state_repo.py`
- Impact: Concurrent requests can create duplicate users or duplicate sheet rows, and high-volume analytics/sheet queries degrade into collection scans.
- Fix approach: Add unique indexes on `users.email`, `sheet_raw_data(connection_id,row_number)`, and `sheet_sync_states.connection_id`, plus query-supporting indexes for organization-scoped media and voice/audio lookups.

**Documentation and code surface drift:**
- Issue: `README.md` describes tests, Docker assets, and richer module layouts that are not present in the tracked repository. `app/api/v1/business/users.py` duplicates `/users/me` but is not registered in `app/api/v1/router.py`, while `app/api/v1/business/projects.py` and `app/services/business/project_service.py` are placeholders.
- Files: `README.md`, `app/api/v1/router.py`, `app/api/v1/business/users.py`, `app/api/v1/business/projects.py`, `app/services/business/project_service.py`
- Impact: New contributors can extend dead paths, trust outdated structure guidance, or assume infrastructure and tests exist when they do not.
- Fix approach: Remove placeholder and duplicate modules or wire them deliberately, then rewrite `README.md` to match the actual tracked codebase.

**Oversized modules concentrate multiple responsibilities:**
- Issue: Runtime-critical modules combine transport, orchestration, validation, persistence, and provider concerns in single files. The largest files include `app/services/stt/session_manager.py`, `app/infrastructure/deepgram/client.py`, `app/services/stt/session.py`, `app/api/v1/sheet_crawler/router.py`, and `app/services/analytics/analytics_service.py`.
- Files: `app/services/stt/session_manager.py`, `app/infrastructure/deepgram/client.py`, `app/services/stt/session.py`, `app/api/v1/sheet_crawler/router.py`, `app/services/analytics/analytics_service.py`
- Impact: Review scope is large, regression risk is high, and bugs are harder to isolate because behavior changes span multiple concerns inside one file.
- Fix approach: Split by lifecycle boundary and preserve behavior with contract tests around provider adapters, session control, and route orchestration.

## Known Bugs

**Retryable image-generation failures are treated as terminal:**
- Symptoms: Image jobs end in `FAILED` with `provider_retryable` metadata even when the upstream failure is transient.
- Files: `app/workers/image_generation_worker.py`, `app/infrastructure/minimax/image_client.py`
- Trigger: MiniMax timeouts, 429 responses, or transient 5xx/network failures during `generate_text_to_image()`.
- Workaround: Resubmit the job manually through the API; there is no automatic retry path.

**Analytics access control is inconsistent with organization-scoped sheet connections:**
- Symptoms: Analytics endpoints use `current_user.id` ownership checks and do not resolve `OrganizationContext`, while sheet connections themselves are created and listed in an organization scope.
- Files: `app/api/v1/analytics/router.py`, `app/services/analytics/analytics_service.py`, `app/api/v1/sheet_crawler/router.py`
- Trigger: An org admin or super admin attempts analytics against a connection they can manage but did not personally create.
- Workaround: Use the original connection owner account or move data access through APIs that already honor organization context.

**Operational health checks can report healthy during dependency outages:**
- Symptoms: `/health` always returns a healthy payload even when MongoDB, Redis, or provider integrations are unavailable.
- Files: `app/api/v1/health.py`, `app/main.py`
- Trigger: Dependency outage after process start, partial startup degradation, or provider failure during runtime.
- Workaround: Use external smoke tests and infrastructure monitoring instead of the built-in health endpoint.

## Security Considerations

**Socket transport accepts any origin and allows JWTs in query strings:**
- Risk: `app/socket_gateway/server.py` sets `cors_allowed_origins="*"`, and `app/socket_gateway/auth.py` accepts `?token=` query parameters. Tokens in URLs can leak through browser history, proxy logs, referrer headers, and telemetry.
- Files: `app/socket_gateway/server.py`, `app/socket_gateway/auth.py`
- Current mitigation: JWTs are validated before the socket joins a user room.
- Recommendations: Restrict allowed origins, disable query-string token fallback outside local development, and prefer auth payloads or short-lived websocket tickets.

**Super-admin bootstrap is public on an empty database and race-prone:**
- Risk: `POST /api/v1/auth/bootstrap-super-admin` is unauthenticated. If the database is empty or reset, the first caller can create the initial admin. The flow also uses separate `count_all()` and `create()` operations, and `users.email` has no unique database constraint.
- Files: `app/api/v1/auth/routes.py`, `app/services/auth/auth_service.py`, `app/repo/user_repo.py`, `app/infrastructure/database/mongodb.py`
- Current mitigation: The route rejects new bootstrap attempts once at least one user exists.
- Recommendations: Gate bootstrap behind a deployment-only secret or one-time token, make the operation atomic, and add a unique index on `users.email`.

**Internal automation relies on a single shared API key with minimal request hardening:**
- Risk: `app/api/v1/internal/router.py` authorizes high-impact queue fan-out with one `X-API-Key` header, no request signing, no source verification, and no replay protection.
- Files: `app/api/v1/internal/router.py`
- Current mitigation: A configured header value is required for access.
- Recommendations: Move to signed requests or workload identity, rotate secrets, and add provenance checks and rate limits around internal endpoints.

## Performance Bottlenecks

**Sheet sync performs serial per-row writes:**
- Problem: `app/services/sheet_crawler/crawler_service.py` fetches rows and awaits `upsert()` once per row.
- Files: `app/services/sheet_crawler/crawler_service.py`, `app/repo/sheet_data_repo.py`
- Cause: The sync path uses one Mongo round-trip per row instead of bulk persistence.
- Improvement path: Use `bulk_write` with chunked batches and back it with a unique `(connection_id, row_number)` index for idempotent ingestion.

**Analytics queries scan and transform raw sheet data on demand:**
- Problem: Search and analytics rely on regex filters and `$toDouble` conversions over raw sheet data, but `app/infrastructure/database/mongodb.py` does not provision indexes for `sheet_raw_data`.
- Files: `app/services/analytics/analytics_service.py`, `app/services/analytics/strategies.py`, `app/repo/sheet_data_repo.py`, `app/infrastructure/database/mongodb.py`
- Cause: Raw rows are stored schemaless and queried directly without pre-normalized numeric/date fields or targeted indexes.
- Improvement path: Normalize query-critical fields during sync, add indexes for common filters, and precompute heavy aggregates where latency matters.

**Uploads buffer full payloads in memory before storage:**
- Problem: Image and voice validation read entire files into memory before upload. The image route accepts up to 10 files and each file can be 25 MB.
- Files: `app/services/image/image_service.py`, `app/services/voice/voice_service.py`, `app/api/v1/images/router.py`, `app/api/v1/voices/router.py`
- Cause: MIME validation is implemented after full-buffer reads instead of staged or streamed validation.
- Improvement path: Stream to temp storage or staged uploads, sniff only leading bytes for type checks, and cap aggregate request size.

**Organization and user listing uses N+1 database access:**
- Problem: Membership collections are loaded first, then each user is fetched individually.
- Files: `app/services/organization/organization_service.py`, `app/services/user/user_service.py`, `app/repo/organization_member_repo.py`, `app/repo/user_repo.py`
- Cause: Response assembly loops over members and calls `find_by_id()` for each user.
- Improvement path: Add batched user lookups or repository methods that return joined membership/user data in one query path.

## Fragile Areas

**Process-local STT session orchestration:**
- Files: `app/services/stt/session_manager.py`, `app/services/stt/session.py`, `app/infrastructure/deepgram/client.py`, `app/socket_gateway/server.py`
- Why fragile: Session ownership, provider lifecycle, audio backpressure, deferred persistence, and socket cleanup span several large modules with broad exception handling and in-memory state keyed by `sid`.
- Safe modification: Change one lifecycle boundary at a time and preserve ownership, timeout, and finalization invariants. Validate disconnect, reconnect, timeout, and provider-error paths before merging.
- Test coverage: No tracked STT tests are present in `tests/`; `pytest -q` reports `no tests ran in 0.09s`.

**Socket and worker event delivery under partial Redis failure:**
- Files: `app/socket_gateway/manager.py`, `app/socket_gateway/worker_gateway.py`, `app/main.py`
- Why fragile: Redis manager initialization failures fall back to local-only mode or warning-only drops. Background work can complete while clients receive no realtime updates.
- Safe modification: Treat Redis transport availability as an explicit dependency for features that promise realtime progress, and surface degraded mode clearly instead of silently dropping events.
- Test coverage: No tracked integration tests cover Redis outage, cross-process Socket.IO delivery, or worker event fan-out.

**Legacy and partially wired API surface:**
- Files: `app/api/v1/router.py`, `app/api/v1/business/users.py`, `app/api/v1/business/projects.py`, `app/services/business/project_service.py`, `README.md`
- Why fragile: Some modules are placeholders or duplicates but not registered, so future changes can land in code paths that never run.
- Safe modification: Verify router registration before editing endpoint files, and delete dead modules once the active surface is confirmed.
- Test coverage: No tracked route-level tests exist to catch edits made in the wrong module tree.

## Scaling Limits

**STT requires sticky-session routing and per-process ownership:**
- Current capacity: Live interview/STT state lives in one in-memory session map per app process.
- Limit: `app/services/stt/session_manager.py` and `app/socket_gateway/server.py` require audio and control traffic to hit the same instance; cross-instance routing without stickiness breaks active sessions.
- Scaling path: Externalize session ownership/state or move interview STT into a dedicated stateful service boundary.

**Google Sheets rate limiting is per worker, not global:**
- Current capacity: `GoogleSheetsRateLimiter` only throttles requests inside one `SheetSyncWorker` process.
- Limit: Adding more workers multiplies total allowed throughput and can exceed Google quota across the fleet.
- Scaling path: Move quota enforcement into Redis or another distributed coordinator so all workers share one rate budget.

**Queue throughput and reliability stop at Redis list semantics:**
- Current capacity: A task is removed from Redis as soon as a worker pops it.
- Limit: There is no visibility timeout, ack, or dead-letter queue, so restarts and horizontal scale increase the odds of silent task loss and stuck business state.
- Scaling path: Adopt broker semantics with acknowledgement, redelivery, and DLQ support.

## Dependencies at Risk

**Unpinned Python dependencies with no lockfile:**
- Risk: `requirements.txt` does not pin versions for FastAPI, LangChain, LangGraph, Deepgram, Redis, Cloudinary, or pytest tooling.
- Impact: Reproducibility is weak, deployments can drift between environments, and provider SDK behavior can change without code changes.
- Migration plan: Pin versions, generate a lockfile, and separate runtime dependencies from developer/test dependencies.

## Missing Critical Features

**Tracked automated tests are absent:**
- Problem: The tracked `tests/` tree only contains package markers, and `pytest -q` exits with `no tests ran`.
- Blocks: Safe refactoring of auth, STT/socket flows, background workers, and organization-scoped permissions.

**Dependency-aware readiness and health checks are absent:**
- Problem: `app/api/v1/health.py` does not verify MongoDB, Redis, Cloudinary, Deepgram, or MiniMax availability.
- Blocks: Reliable orchestration, alerting, rollout gating, and automated recovery decisions.

**Worker recovery and reconciliation are absent:**
- Problem: There is no recovery loop that reclaims lost queue items or requeues jobs left in `PROCESSING` after worker crashes.
- Blocks: Automatic recovery from node restarts and safe scale-out of image-generation and sheet-sync workers.

## Test Coverage Gaps

**Authentication and bootstrap flows:**
- What's not tested: Login, password change, bootstrap-super-admin, duplicate-email handling, and empty-database bootstrap behavior.
- Files: `app/api/v1/auth/routes.py`, `app/services/auth/auth_service.py`, `app/repo/user_repo.py`
- Risk: Auth regressions and bootstrap takeover issues can ship unnoticed.
- Priority: High

**Socket/STT lifecycle and provider failure handling:**
- What's not tested: Connect/auth, sticky-session assumptions, Deepgram disconnects, finalize/stop races, and reconnect/error delivery.
- Files: `app/socket_gateway/server.py`, `app/services/stt/session_manager.py`, `app/services/stt/session.py`, `app/infrastructure/deepgram/client.py`
- Risk: Live interview flows can fail under concurrency or network churn without early detection.
- Priority: High

**Background worker durability and retry behavior:**
- What's not tested: Lost-job recovery, dequeue/requeue semantics, image retryable failures, and sheet-sync retry exhaustion.
- Files: `app/infrastructure/redis/redis_queue.py`, `app/workers/sheet_sync_worker.py`, `app/workers/image_generation_worker.py`
- Risk: Silent task loss and incorrect terminal states can accumulate in production.
- Priority: High

**Organization-scoped permission consistency:**
- What's not tested: Cross-feature behavior for org admins versus resource owners across analytics, sheet crawler, images, voices, and TTS.
- Files: `app/api/v1/analytics/router.py`, `app/api/v1/sheet_crawler/router.py`, `app/services/image/image_service.py`, `app/services/voice/voice_service.py`, `app/services/tts/tts_service.py`
- Risk: Permission regressions and inconsistent access models can appear only after rollout.
- Priority: High

---

*Concerns audit: 2026-03-19*
