# text-to-image-generation Specification

## Purpose
TBD - created by archiving change add-text-to-image-generation-jobs. Update Purpose after archive.
## Requirements
### Requirement: Create a text-to-image generation job
The system SHALL provide a `POST /api/v1/image-generations/text-to-image` endpoint that accepts a JSON body containing `prompt`, `aspect_ratio`, optional `seed`, and optional `prompt_optimizer`. The request MUST be authenticated, MUST include valid organization context, and MUST create a persistent generation job with `type=text_to_image`, `provider=minimax`, `provider_model=image-01`, `requested_count=1`, and initial `status=pending`. After persisting the job, the system SHALL enqueue the job for asynchronous processing and return the created job identifier and current status without waiting for image generation to complete.

#### Scenario: Successful job creation
- **WHEN** an authenticated user sends `POST /api/v1/image-generations/text-to-image` with a valid prompt and `X-Organization-ID`
- **THEN** the system stores a new `image_generation_job` with `status=pending`, enqueues the job, and returns HTTP 201 with the `job_id` and `status=pending`

#### Scenario: Missing organization context
- **WHEN** an authenticated user sends a create request without the `X-Organization-ID` header
- **THEN** the system returns HTTP 400 and does NOT create or enqueue a job

#### Scenario: Prompt exceeds MiniMax limit
- **WHEN** a user sends a prompt longer than 1500 characters
- **THEN** the system returns HTTP 422 validation error and does NOT create or enqueue a job

#### Scenario: Unsupported aspect ratio
- **WHEN** a user sends an aspect ratio outside the supported MiniMax set
- **THEN** the system returns HTTP 422 validation error and does NOT create or enqueue a job

### Requirement: Persist generation job history
The system SHALL persist text-to-image generation jobs in MongoDB so users can retrieve durable execution history after the original request has completed. Each persisted job SHALL include organization context, creator identity, prompt inputs, lifecycle timestamps, provider metadata, output image references, success/failure counters, and terminal failure details when applicable.

#### Scenario: Job history includes completed job metadata
- **WHEN** a text-to-image job completes successfully
- **THEN** the stored job record includes `organization_id`, `created_by`, prompt parameters, `provider_trace_id`, `status=succeeded`, `output_image_ids`, `success_count=1`, and `completed_at`

#### Scenario: Job history includes failure metadata
- **WHEN** a text-to-image job fails during provider execution
- **THEN** the stored job record includes `status=failed`, `error_code`, `error_message`, and `completed_at`

### Requirement: Process queued text-to-image jobs asynchronously
The system SHALL process text-to-image jobs through a dedicated asynchronous worker that consumes queued job payloads from Redis. Before executing provider work, the worker MUST atomically transition the job from `pending` to `processing`. The worker SHALL ignore queued payloads for jobs that are already terminal or no longer `pending`. While processing, the worker SHALL call MiniMax image generation with `model=image-01`, `response_format=base64`, and phase-1 output count fixed to one image.

#### Scenario: Worker claims and processes a pending job
- **WHEN** the worker dequeues a payload for a job whose current state is `pending`
- **THEN** the worker atomically updates the job to `processing` and calls MiniMax image generation for that job

#### Scenario: Worker ignores a cancelled queued job
- **WHEN** the worker dequeues a payload for a job whose current state is `cancelled`
- **THEN** the worker skips provider execution and leaves the job unchanged

#### Scenario: Worker ignores a duplicate queued payload
- **WHEN** the worker dequeues a payload for a job that is already `processing`, `succeeded`, or `failed`
- **THEN** the worker does NOT call MiniMax again and does NOT create duplicate output images

### Requirement: Persist generated image output as an authenticated image asset
After a successful MiniMax response, the system SHALL decode the returned base64 image, upload the image bytes to Cloudinary using the platform's authenticated image storage path, and create a persistent image record in the `images` collection. The generation job SHALL reference the created image record through `output_image_ids`. Generated images SHALL remain accessible through the platform's existing signed URL and permission model rather than through raw MiniMax provider data.

#### Scenario: Successful image persistence
- **WHEN** MiniMax returns one successful base64 image for a processing job
- **THEN** the system uploads the decoded image to Cloudinary, creates an `images` record for the generated asset, updates the job with the new image ID, and marks the job `succeeded`

#### Scenario: Image storage failure after provider success
- **WHEN** MiniMax returns a successful base64 image but Cloudinary upload or image record creation fails
- **THEN** the system marks the job `failed`, stores an error message explaining the storage failure, and does NOT report the job as succeeded

### Requirement: Expose job detail and history through REST APIs
The system SHALL provide REST endpoints to retrieve a single job and to list job history for the active organization. Job detail responses SHALL return the authoritative current state of the job and SHALL include completed output image references. Job history responses SHALL be paginated, scoped to the active organization, and sorted by creation time descending. Regular users SHALL only see jobs they created, while org admins and super admins SHALL be able to view all jobs within the organization scope permitted by existing access rules.

#### Scenario: Creator retrieves their job detail
- **WHEN** the user who created a job requests `GET /api/v1/image-generations/{job_id}`
- **THEN** the system returns the job's current status, persisted metadata, and any completed output images for that job

#### Scenario: Regular member cannot see another member's job
- **WHEN** a regular organization member requests a job created by another member in the same organization
- **THEN** the system returns HTTP 403

#### Scenario: Job from a different organization is hidden
- **WHEN** a user requests a job that belongs to a different organization
- **THEN** the system returns HTTP 404

#### Scenario: Paginated history for organization
- **WHEN** an authenticated user requests `GET /api/v1/image-generations?skip=0&limit=20` with valid organization context
- **THEN** the system returns a paginated list of generation jobs for the permitted scope, ordered by newest first, along with the total count

### Requirement: Cancel a pending text-to-image job
The system SHALL provide a `POST /api/v1/image-generations/{job_id}/cancel` endpoint that cancels a job only when its current status is `pending`. Cancellation MUST be implemented as an atomic state transition from `pending` to `cancelled`. The system MUST reject cancellation for jobs that are already `processing`, `succeeded`, `failed`, or `cancelled`.

#### Scenario: Successful pending cancellation
- **WHEN** the creator, an org admin, or a super admin sends `POST /api/v1/image-generations/{job_id}/cancel` for a job currently in `pending`
- **THEN** the system atomically updates the job to `cancelled`, records `cancelled_at`, and returns the cancelled job state

#### Scenario: Cancel loses race to worker claim
- **WHEN** a cancel request is made for a job that has already been atomically transitioned from `pending` to `processing` by the worker
- **THEN** the system rejects the cancel request and indicates that the job can no longer be cancelled

#### Scenario: Cancel already terminal job
- **WHEN** a user sends a cancel request for a job in `succeeded`, `failed`, or `cancelled`
- **THEN** the system rejects the request and leaves the job unchanged

### Requirement: Emit realtime lifecycle events for generation jobs
The system SHALL emit Socket.IO business events for text-to-image job lifecycle changes using the existing user-scoped room model and additive top-level `organization_id`. At minimum, the system SHALL emit events for job creation, processing start, successful completion, failed completion, and cancellation. Event payloads SHALL include `job_id`, `status`, `organization_id`, and enough lifecycle metadata for the client to reconcile state with the REST API.

#### Scenario: Created event emitted after job persistence
- **WHEN** a new text-to-image job is created successfully
- **THEN** the server emits an `image:generation:created` event to the creator's user room after the job has been persisted

#### Scenario: Processing event emitted by worker
- **WHEN** the worker successfully claims a pending job and updates it to `processing`
- **THEN** the worker emits an `image:generation:processing` event with the job identifier and `organization_id`

#### Scenario: Succeeded event emitted after persistence
- **WHEN** a processing job has been updated to `succeeded` and its output image record has been stored
- **THEN** the worker emits an `image:generation:succeeded` event containing the job identifier and output image identifiers

#### Scenario: Failed event emitted after terminal failure
- **WHEN** a processing job transitions to `failed`
- **THEN** the worker emits an `image:generation:failed` event containing the job identifier, `organization_id`, and failure detail

#### Scenario: Cancelled event emitted after cancellation
- **WHEN** a pending job is successfully cancelled
- **THEN** the server emits an `image:generation:cancelled` event after the job state has been persisted as `cancelled`

### Requirement: Preserve ordering and consistency between persisted state and events
For every lifecycle transition that emits a socket event, the system SHALL persist the new job state before publishing the corresponding realtime event. Clients that refetch the job immediately after receiving an event MUST observe the same state in the REST API that the event announced.

#### Scenario: Event follows persisted cancelled state
- **WHEN** the system emits `image:generation:cancelled`
- **THEN** a subsequent `GET /api/v1/image-generations/{job_id}` returns `status=cancelled`

#### Scenario: Event follows persisted succeeded state
- **WHEN** the system emits `image:generation:succeeded`
- **THEN** a subsequent `GET /api/v1/image-generations/{job_id}` returns `status=succeeded` and includes the persisted output image references

