## 1. Configuration and shared contracts

- [x] 1.1 Add `IMAGE_GENERATION_QUEUE_NAME` to `app/config/settings.py` with a dedicated Redis queue name for text-to-image jobs
- [x] 1.2 Add a new `TextToImageGenerationEvents` group to `app/common/event_socket.py` for `created`, `processing`, `succeeded`, `failed`, and `cancelled` event names
- [x] 1.3 Add generation-specific exception classes to `app/common/exceptions.py` for job-not-found, invalid job state, cancellation conflict, and provider/storage failure mapping
- [x] 1.4 Register repository and service factory placeholders in `app/common/repo.py` and `app/common/service.py` for the new generation components

## 2. Job domain model and schemas

- [x] 2.1 Create `app/domain/models/image_generation_job.py` with the full persisted job model, status enum, timestamps, provider metadata, and output image references
- [x] 2.2 Extend `app/domain/models/image.py` with additive generated-image metadata such as `source`, `generation_job_id`, `provider`, and `provider_model`
- [x] 2.3 Create `app/domain/schemas/image_generation.py` request schemas for create-job input with strict validation for prompt length, supported aspect ratios, optional seed, and `prompt_optimizer`
- [x] 2.4 Create `app/domain/schemas/image_generation.py` response schemas for create response, detail response, summary list item, paginated history response, and cancel response
- [x] 2.5 Decide and encode the API-visible job status enum in schemas so REST and socket payloads use the same canonical values

## 3. Repository layer and MongoDB indexes

- [ ] 3.1 Create `app/repo/image_generation_job_repo.py` with methods to create jobs, find job by id, list jobs by organization/creator scope, and update terminal state
- [ ] 3.2 Implement atomic `claim_pending_job(job_id)` in the job repository using a single MongoDB compare-and-set update from `pending` to `processing`
- [ ] 3.3 Implement atomic `cancel_pending_job(job_id, actor scope)` in the job repository using a single MongoDB compare-and-set update from `pending` to `cancelled`
- [ ] 3.4 Add repository methods to mark job success, mark job failure, and persist provider trace IDs, output image IDs, and timestamps
- [ ] 3.5 Register `get_image_generation_job_repo()` in `app/common/repo.py`
- [ ] 3.6 Update MongoDB startup/index initialization to create indexes for `image_generation_jobs`
- [ ] 3.7 Add any needed additive indexes on `images` for generated assets, especially `generation_job_id` if introduced

## 4. MiniMax image provider client

- [ ] 4.1 Create `app/infrastructure/minimax/image_client.py` as a dedicated MiniMax text-to-image client separate from the existing voice/TTS client
- [ ] 4.2 Implement request payload construction for MiniMax `POST /v1/image_generation` with fixed `model=image-01`, fixed `response_format=base64`, and phase-1 output count fixed to one image
- [ ] 4.3 Implement provider response normalization returning provider trace id, base64 image list, success count, failed count, and raw payload
- [ ] 4.4 Map MiniMax provider and transport errors into retryable vs non-retryable application exceptions without exposing sensitive provider details to clients
- [ ] 4.5 Register `get_minimax_image_client()` in `app/common/service.py`

## 5. Image generation service

- [ ] 5.1 Create `app/services/image/image_generation_service.py` with create, get detail, list history, and cancel methods
- [ ] 5.2 Implement create-job flow: validate input, persist `pending` job, enqueue minimal queue payload, and return the created job response
- [ ] 5.3 Implement list-history flow with organization-scoped filtering and role-aware visibility (regular user sees own jobs, org admin/super admin can see broader scope)
- [ ] 5.4 Implement get-detail flow with permission checks and completed output image references
- [ ] 5.5 Implement cancel flow using repository compare-and-set semantics and translate failed cancel attempts into the correct API error behavior
- [ ] 5.6 Emit `created` and `cancelled` socket events from the service only after the corresponding DB state has been committed
- [ ] 5.7 Register `get_image_generation_service()` in `app/common/service.py`

## 6. Worker execution pipeline

- [ ] 6.1 Create `app/workers/image_generation_worker.py` following the structure of `sheet_sync_worker.py`
- [ ] 6.2 Define a worker task payload/dataclass carrying `job_id`, `organization_id`, `user_id`, `queued_at`, and `retry_count`
- [ ] 6.3 Implement dequeue + stale-task handling so cancelled or already-terminal jobs are skipped without provider calls
- [ ] 6.4 Implement the atomic worker-claim step that transitions `pending` to `processing` before provider execution
- [ ] 6.5 Emit a `processing` socket event after the job state is persisted as `processing`
- [ ] 6.6 Call the MiniMax image client, decode the returned base64 image bytes, and prepare the upload payload for authenticated Cloudinary storage
- [ ] 6.7 Persist the generated image into Cloudinary and create the generated asset record in `images`
- [ ] 6.8 Mark the job `succeeded` with provider trace id, output image id, success counters, and completion timestamp, then emit the `succeeded` event
- [ ] 6.9 Mark the job `failed` with normalized error metadata and completion timestamp when provider or storage execution fails, then emit the `failed` event
- [ ] 6.10 Add worker bootstrap and cleanup for MongoDB/Redis connections and graceful shutdown behavior consistent with existing workers

## 7. REST API router

- [ ] 7.1 Create `app/api/v1/image_generations/router.py`
- [ ] 7.2 Implement `POST /api/v1/image-generations/text-to-image` with auth, organization context resolution, and service injection
- [ ] 7.3 Implement `GET /api/v1/image-generations/{job_id}` with role-aware access checks through the service layer
- [ ] 7.4 Implement `GET /api/v1/image-generations` with pagination parameters and organization-scoped history retrieval
- [ ] 7.5 Implement `POST /api/v1/image-generations/{job_id}/cancel` and return the updated cancelled job state when successful
- [ ] 7.6 Register the new router in `app/api/v1/router.py`

## 8. Socket event integration

- [ ] 8.1 Reuse the existing Socket.IO user-room model and `organization_id` payload enrichment for all generation lifecycle events
- [ ] 8.2 Define a single payload shape shared across server-side and worker-side generation event emitters
- [ ] 8.3 Emit `image:generation:created` from the API/server path after job creation has been persisted
- [ ] 8.4 Emit `image:generation:processing`, `image:generation:succeeded`, and `image:generation:failed` from the worker path after each corresponding state transition is persisted
- [ ] 8.5 Emit `image:generation:cancelled` from the API/server path only after the pending job has been atomically cancelled
- [ ] 8.6 Verify that each event payload includes top-level `organization_id`, `job_id`, `status`, and any lifecycle metadata needed by the frontend to reconcile state

## 9. Access control and edge-case handling

- [ ] 9.1 Reuse the existing 3-tier permission model for job detail, history visibility, and cancellation authority
- [ ] 9.2 Ensure cross-organization job lookups return hidden/not-found behavior where required by existing security patterns
- [ ] 9.3 Handle the cancel-vs-worker-claim race by returning a non-cancellable response when the worker has already claimed the job
- [ ] 9.4 Ensure duplicate or stale queued payloads do not re-run provider work or create duplicate generated images
- [ ] 9.5 Ensure list responses do not generate signed image URLs for every historical record, while detail responses can include completed output access data

## 10. Verification and implementation readiness

- [ ] 10.1 Add tests for create-job validation and successful enqueue behavior
- [ ] 10.2 Add tests for repository compare-and-set semantics covering `pending -> processing` and `pending -> cancelled`
- [ ] 10.3 Add tests for worker handling of cancelled jobs, duplicate queue payloads, provider success, and provider/storage failure
- [ ] 10.4 Add tests for REST detail/history visibility across regular user, org admin, and super admin roles
- [ ] 10.5 Add tests for socket lifecycle emission ordering to verify DB state is persisted before the emitted event
- [ ] 10.6 Run targeted verification of the full happy path: create job -> pending event -> processing event -> generated image persisted -> succeeded event -> detail endpoint reflects final state
- [ ] 10.7 Run targeted verification of the cancel happy path: create job -> cancel while pending -> cancelled event -> worker later skips stale queued payload
