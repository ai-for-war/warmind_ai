## Why

The AI FOR WAR platform currently has no capability to upload or store images. Chat messages support `Attachment` metadata but assume images exist at external URLs with no upload mechanism. Military operations require sharing tactical maps, satellite imagery, reconnaissance photos, and operational diagrams through the chat system and other features. Without a secure image upload pipeline, users cannot attach visual intelligence to conversations, limiting the platform's tactical decision-support effectiveness.

## What Changes

- Add a new image upload endpoint supporting batch upload (up to 10 files per request) via `multipart/form-data`
- Integrate Cloudinary as the external image storage backend with `type="authenticated"` delivery for maximum security
- Store only image metadata (`public_id`, organization, uploader, filename, size, MIME type) in MongoDB — no binary data in the database
- Generate time-limited signed URLs (2-hour expiry) for image access, enforced at both the backend (JWT + org membership check) and Cloudinary (signature + token verification)
- Validate uploads server-side using magic bytes (`python-magic`) to prevent MIME type spoofing — never trust client-provided `content_type`
- Support image formats: JPEG, PNG, WebP, TIFF, BMP, SVG with a 25MB per-file size limit
- Enforce organization-scoped access control: only users within the same organization can view images; only the uploader, org admin, or super admin can delete
- Wrap synchronous Cloudinary SDK calls with `asyncio.to_thread` for non-blocking concurrent uploads
- Add dedicated image exceptions, repository, service, and infrastructure client following existing codebase patterns

## Capabilities

### New Capabilities
- `image-upload`: Secure image upload, storage, retrieval (signed URL), listing, and deletion scoped to organizations via Cloudinary authenticated delivery

### Modified Capabilities
_(none — this is a standalone feature; the existing `Attachment` model in messages is not modified in this change)_

## Impact

- **New dependencies**: `cloudinary` (Cloudinary Python SDK), `python-magic` / `python-magic-bin` (MIME detection via magic bytes)
- **Configuration**: New environment variables — `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
- **New API surface**: 4 endpoints under `/api/v1/images` — upload, list, get (signed URL), delete
- **New MongoDB collection**: `images` — stores image metadata records
- **New code files**: router, schemas, model, service, repository, cloudinary client infrastructure
- **Modified files**: `settings.py` (Cloudinary config), `router.py` (mount image router), `common/repo.py` and `common/service.py` (DI factories), `common/exceptions.py` (image-specific errors), `requirements.txt` (new packages)
- **Cloudinary account setup required**: Enable strict transformations and configure authenticated delivery in Cloudinary dashboard
