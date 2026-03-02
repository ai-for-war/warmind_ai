## Context

The AI FOR WAR platform is a multi-tenant tactical decision-support system built on FastAPI + MongoDB + Redis. The current architecture follows a layered pattern: API routes → services → repositories → MongoDB, with JWT authentication and organization-scoped RBAC (UserRole: USER/SUPER_ADMIN, OrganizationRole: ADMIN/USER).

The `Message` model already defines an `Attachment` schema (type, url, filename, mime_type, size_bytes), but no upload mechanism exists. Images are a new external dependency (Cloudinary) and introduce the first binary file handling in the system.

**Constraints:**
- Cloudinary Python SDK (`pycloudinary`) is synchronous — must be wrapped for async FastAPI
- Files up to 25MB must be handled in memory (Cloudinary SDK expects bytes or file path)
- Organization-scoped isolation is mandatory — images MUST NOT leak across organizations
- Cloudinary `type="authenticated"` disables on-the-fly transformations; eager transforms must be used if needed in the future

## Goals / Non-Goals

**Goals:**
- Secure image upload pipeline with server-side MIME validation via magic bytes
- Cloudinary authenticated delivery ensuring no public URL access to images
- Signed URL generation with 2-hour expiry for time-limited access
- Batch upload (up to 10 files) with concurrent Cloudinary uploads via `asyncio.gather`
- Organization-scoped access control consistent with existing RBAC patterns
- Follow existing codebase conventions (layered architecture, DI factories, exception hierarchy)

**Non-Goals:**
- Image processing (resize, thumbnail, watermark, compression) — deferred
- EXIF metadata stripping — not required
- Audit logging of image access — deferred
- Direct client-to-Cloudinary upload (presigned upload) — all uploads go through BE
- Integration with chat `Message.attachments` — upload is standalone; linking is a separate change
- Classification levels (RESTRICTED, CONFIDENTIAL) — deferred; using org-scoped access only

## Decisions

### D1: Storage Backend → Cloudinary with Authenticated Delivery

**Decision:** Use Cloudinary with `type="authenticated"` for all image uploads.

**Rationale:** Authenticated delivery ensures no public URL exists for any uploaded image. Access requires a signed URL generated server-side. This provides defense-in-depth: even if someone discovers the `public_id` or cloud name, they cannot access the image without a valid signature.

**Alternatives considered:**
- `type="upload"` (public) + signed URL endpoint: Simpler, but public URL still works as a bypass. Unacceptable for military content.
- `type="private"`: Original requires signed URL, but derived/transformed versions are public. Insufficient.
- S3/MinIO: More control, but requires managing infrastructure. Cloudinary provides CDN + transformation pipeline out of the box.
- Server proxy (stream through BE): Maximum control but BE becomes bandwidth bottleneck. Not worth the cost for current scale.

### D2: Async Strategy → `asyncio.to_thread` with Bounded Concurrency

**Decision:** Wrap each `cloudinary.uploader.upload()` call in `asyncio.to_thread()` and use `asyncio.gather()` for concurrent batch uploads, capped at 10 concurrent operations.

**Rationale:** The Cloudinary Python SDK is synchronous. `asyncio.to_thread` delegates blocking I/O to the default thread pool executor without blocking the event loop. For batch uploads, `asyncio.gather` enables concurrent uploads while the 10-file cap prevents thread pool exhaustion.

**Alternatives considered:**
- Custom `ThreadPoolExecutor(max_workers=10)`: More control over thread count, but `asyncio.to_thread` uses the default executor which is sufficient and simpler.
- Sequential uploads: Simpler but slow — 10 files × ~2s each = ~20s vs ~2-3s concurrent.
- `httpx` async to Cloudinary REST API directly: True async but loses SDK features (signature generation, transformation helpers). High implementation cost.

### D3: MIME Validation → `python-magic` (Magic Bytes)

**Decision:** Use `python-magic` to detect actual file type from binary content (magic bytes). Never trust client-provided `Content-Type` header.

**Rationale:** Client headers are trivially spoofable. An attacker could upload a malicious file with `Content-Type: image/jpeg`. Magic byte detection reads the first bytes of the file to determine the actual format, preventing file type spoofing.

**Alternatives considered:**
- `file.content_type` from FastAPI: Relies on client header — unsafe.
- File extension check: Trivially bypassed by renaming files.
- `filetype` library: Lighter but less comprehensive than `python-magic` for edge cases (SVG, TIFF variants).

### D4: File Size Validation → Streaming Chunk-Based Check

**Decision:** Read file in 64KB chunks, accumulating size. Reject immediately when 25MB limit is exceeded without reading the entire file.

**Rationale:** Prevents unnecessary memory consumption for oversized files. The server stops reading as soon as the limit is crossed, returning 413 immediately.

### D5: MongoDB Schema → Metadata Only, No Binary

**Decision:** Store image metadata in a dedicated `images` collection. Fields: `_id`, `public_id`, `organization_id`, `uploaded_by`, `original_filename`, `mime_type`, `size_bytes`, `cloudinary_folder`, `created_at`, `deleted_at`.

**Rationale:** Binary storage in MongoDB (GridFS) would duplicate Cloudinary storage and increase database size. Metadata-only approach keeps MongoDB lean and query-fast.

### D6: Soft Delete → MongoDB Soft Delete + Cloudinary Hard Delete

**Decision:** Set `deleted_at` timestamp in MongoDB (soft delete) and call `cloudinary.uploader.destroy()` to remove the actual binary (hard delete + CDN invalidation).

**Rationale:** Soft delete in MongoDB preserves an audit trail of what was uploaded. Hard delete in Cloudinary ensures storage is freed and CDN cache is invalidated so the signed URL no longer works.

### D7: Folder Organization on Cloudinary

**Decision:** Use pattern `{org_id}/{year-month}/{uuid}` for Cloudinary folder/public_id structure.

**Rationale:** Organization-level grouping enables bulk operations (e.g., delete all images for an org). Year-month partitioning prevents flat folder bloat. UUID ensures uniqueness without exposing original filenames.

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cloudinary SDK is synchronous | Blocks event loop if not wrapped | `asyncio.to_thread` wrapping for all SDK calls |
| 25MB files × 10 = 250MB in memory per request | Memory pressure under concurrent batch uploads | Limit to 10 files/request; streaming size check aborts early; consider Nginx `client_max_body_size` as first-line defense |
| Cloudinary rate limiting (HTTP 420) | Batch uploads may be throttled | Cap concurrent uploads at 10; implement retry with exponential backoff at service level |
| `python-magic` requires `libmagic` system library | Deployment friction on Windows/Docker | Use `python-magic-bin` on Windows (bundles libmagic); document Docker setup with `apt-get install libmagic1` |
| Signed URL valid for 2 hours after generation | Leaked URL is usable within window | Acceptable trade-off — short enough to limit damage, long enough for UX. Can reduce in future if needed |
| Cloudinary `authenticated` disables on-the-fly transforms | Cannot resize/crop dynamically via URL | Use `eager` transforms at upload time if transformations are needed in the future |
| Cloudinary account dependency | Single point of failure for image serving | Monitor Cloudinary status; implement circuit breaker pattern in CloudinaryClient; cache signed URLs briefly in Redis if needed |
