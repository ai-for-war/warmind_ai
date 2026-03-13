## Why

The platform can upload and manage images, but it cannot generate them from text prompts. Tactical and operational workflows need an asynchronous text-to-image capability that can survive provider latency, preserve a full job history, support real-time frontend updates, and allow safe cancellation before work begins.

## What Changes

- Add a new job-based text-to-image generation flow backed by MiniMax `image-01`, with one image generated per request in phase 1
- Add REST endpoints to create a text-to-image job, read job status/detail, list generation history, and cancel a job while it is still `pending`
- Persist generation jobs in MongoDB with lifecycle metadata, provider trace IDs, retry counters, timestamps, and durable links to generated image records
- Process queued generation jobs through a dedicated Redis-backed worker instead of holding open the original HTTP request
- Request MiniMax image output as `base64`, upload the generated image to Cloudinary, and store only metadata in MongoDB
- Emit organization-scoped socket events for job lifecycle transitions such as created, processing, succeeded, failed, and cancelled
- Preserve the existing authenticated image access model by exposing generated images through backend-managed metadata and signed URLs rather than raw provider URLs or base64 blobs

## Capabilities

### New Capabilities
- `text-to-image-generation`: Create, queue, process, observe, and cancel organization-scoped text-to-image jobs with persistent history, generated image persistence, and socket lifecycle events

### Modified Capabilities
- None

## Impact

- **New API surface**: REST endpoints under an image-generation route group for create, get detail, list history, and cancel pending jobs
- **New realtime contract**: additive Socket.IO events for text-to-image job lifecycle updates, emitted with `organization_id`
- **New MongoDB collection**: persistent job records for text-to-image generation history and execution state
- **New worker path**: Redis queue + dedicated worker process for asynchronous image generation execution and retry handling
- **New infrastructure client**: MiniMax image generation client focused on `POST /v1/image_generation`
- **Affected code**: `app/api/v1/`, `app/services/image/`, `app/repo/`, `app/domain/models/`, `app/domain/schemas/`, `app/infrastructure/minimax/`, `app/workers/`, `app/common/service.py`, `app/common/repo.py`, `app/common/exceptions.py`, `app/config/settings.py`, and socket gateway/event modules
- **Dependencies/configuration**: no new external provider beyond MiniMax and existing Redis/Cloudinary stack, but a new queue setting will be required for image generation jobs
