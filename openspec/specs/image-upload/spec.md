## ADDED Requirements

### Requirement: Upload images to organization
The system SHALL allow authenticated users to upload one or more image files (up to 10 per request) to their organization via a `POST /api/v1/images/upload` endpoint using `multipart/form-data`. The user MUST have an active membership in the target organization. Each file SHALL be uploaded to Cloudinary with `type="authenticated"` and the metadata SHALL be stored in MongoDB.

#### Scenario: Successful single image upload
- **WHEN** an authenticated user with org membership uploads a valid JPEG image (5MB) to `POST /api/v1/images/upload`
- **THEN** the system uploads the image to Cloudinary with `type="authenticated"`, stores metadata in MongoDB (public_id, org_id, uploader_id, filename, mime_type, size_bytes), and returns a response with `uploaded: 1`, `failed: 0`, and the image record including its `id`

#### Scenario: Successful batch upload of multiple images
- **WHEN** an authenticated user uploads 5 valid image files in a single request
- **THEN** the system uploads all 5 concurrently via `asyncio.gather`, stores metadata for each, and returns a response with `uploaded: 5`, `failed: 0`, and all image records

#### Scenario: Partial batch failure
- **WHEN** an authenticated user uploads 3 files where 2 are valid images and 1 is an invalid format
- **THEN** the system uploads the 2 valid images, returns `uploaded: 2`, `failed: 1`, and includes the failure reason for the rejected file

#### Scenario: Upload without organization context
- **WHEN** an authenticated user sends an upload request without the `X-Organization-ID` header
- **THEN** the system returns HTTP 400

#### Scenario: Upload by non-member
- **WHEN** an authenticated user who is NOT a member of the specified organization attempts to upload
- **THEN** the system returns HTTP 403

### Requirement: Validate image file type using magic bytes
The system SHALL validate uploaded files by reading magic bytes (binary file signature) using `python-magic`, NOT by trusting the client-provided `Content-Type` header. The system SHALL accept only: `image/jpeg`, `image/png`, `image/webp`, `image/tiff`, `image/bmp`, `image/svg+xml`.

#### Scenario: Valid MIME type detected by magic bytes
- **WHEN** a user uploads a file with `Content-Type: image/jpeg` and the magic bytes confirm it is JPEG
- **THEN** the system accepts the file and proceeds with upload

#### Scenario: Spoofed MIME type rejected
- **WHEN** a user uploads an executable file renamed to `.jpg` with `Content-Type: image/jpeg` but magic bytes indicate `application/x-executable`
- **THEN** the system returns HTTP 400 with detail indicating the detected MIME type is not allowed

#### Scenario: Unsupported image format
- **WHEN** a user uploads a valid GIF image
- **THEN** the system returns HTTP 400 indicating `image/gif` is not in the allowed formats list

### Requirement: Enforce file size limit
The system SHALL reject any individual file exceeding 25MB. File size SHALL be validated by reading the file in chunks (streaming), aborting as soon as the limit is exceeded without reading the entire file.

#### Scenario: File within size limit
- **WHEN** a user uploads a 10MB PNG image
- **THEN** the system accepts the file and proceeds with upload

#### Scenario: File exceeding size limit
- **WHEN** a user uploads a 30MB TIFF image
- **THEN** the system returns HTTP 413 with detail indicating the file exceeds the 25MB limit

#### Scenario: Batch with one oversized file
- **WHEN** a user uploads 3 files where 1 exceeds 25MB
- **THEN** the oversized file is rejected, the other 2 valid files are uploaded, and the response reflects `uploaded: 2`, `failed: 1`

### Requirement: Enforce batch size limit
The system SHALL reject requests containing more than 10 files.

#### Scenario: Batch within limit
- **WHEN** a user uploads 10 files in one request
- **THEN** the system accepts and processes all 10 files

#### Scenario: Batch exceeding limit
- **WHEN** a user uploads 11 files in one request
- **THEN** the system returns HTTP 400 with detail indicating the maximum is 10 files per request

### Requirement: Retrieve image with signed URL
The system SHALL provide a `GET /api/v1/images/{image_id}` endpoint that returns image metadata along with a time-limited signed URL (2-hour expiry) for accessing the image on Cloudinary. The user MUST be authenticated and MUST be a member of the organization that owns the image.

#### Scenario: Successful image retrieval
- **WHEN** an authenticated user who is a member of the image's organization requests `GET /api/v1/images/{image_id}`
- **THEN** the system returns the image metadata and a Cloudinary signed URL valid for 2 hours

#### Scenario: Image not found
- **WHEN** a user requests an image ID that does not exist
- **THEN** the system returns HTTP 404

#### Scenario: Image belongs to different organization
- **WHEN** a user who is a member of Org-A requests an image that belongs to Org-B
- **THEN** the system returns HTTP 404 (not 403, to avoid revealing existence)

#### Scenario: Deleted image
- **WHEN** a user requests an image that has been soft-deleted (deleted_at is set)
- **THEN** the system returns HTTP 404

### Requirement: List images in organization
The system SHALL provide a `GET /api/v1/images` endpoint that returns a paginated list of images belonging to the user's current organization. Only non-deleted images SHALL be returned.

#### Scenario: List images with default pagination
- **WHEN** an authenticated user requests `GET /api/v1/images` with org context
- **THEN** the system returns the first page of images (default limit 20) belonging to that organization, sorted by `created_at` descending

#### Scenario: List images with pagination parameters
- **WHEN** a user requests `GET /api/v1/images?skip=20&limit=10`
- **THEN** the system returns images 21-30, with total count in the response

#### Scenario: Empty organization
- **WHEN** a user requests images for an organization with no uploads
- **THEN** the system returns an empty list with `total: 0`

### Requirement: Delete image
The system SHALL provide a `DELETE /api/v1/images/{image_id}` endpoint. Deletion SHALL be permitted only for: the user who uploaded the image, an organization admin, or a super admin. Deletion SHALL soft-delete the MongoDB record (set `deleted_at`) and hard-delete the binary from Cloudinary with CDN cache invalidation.

#### Scenario: Owner deletes their own image
- **WHEN** the user who uploaded an image sends `DELETE /api/v1/images/{image_id}`
- **THEN** the system sets `deleted_at` on the MongoDB record, calls `cloudinary.uploader.destroy` with `invalidate=True`, and returns HTTP 204

#### Scenario: Org admin deletes another user's image
- **WHEN** an organization admin sends `DELETE /api/v1/images/{image_id}` for an image uploaded by another member of the same organization
- **THEN** the system deletes the image and returns HTTP 204

#### Scenario: Super admin deletes any image
- **WHEN** a super admin sends `DELETE /api/v1/images/{image_id}` for any image in any organization
- **THEN** the system deletes the image and returns HTTP 204

#### Scenario: Regular user attempts to delete another user's image
- **WHEN** a regular org member (not admin) attempts to delete an image uploaded by another user
- **THEN** the system returns HTTP 403

#### Scenario: Delete non-existent image
- **WHEN** a user attempts to delete an image ID that does not exist
- **THEN** the system returns HTTP 404

### Requirement: Cloudinary authenticated delivery
All images uploaded to Cloudinary SHALL use `type="authenticated"`. This ensures that no public URL exists for any image. The only way to access an image is through a signed URL generated by the backend.

#### Scenario: Public URL is inaccessible
- **WHEN** someone constructs a standard Cloudinary public URL for an authenticated image
- **THEN** Cloudinary returns HTTP 401 (unauthorized) — the image is not accessible without a valid signature

#### Scenario: Signed URL with valid signature
- **WHEN** the backend generates a signed URL with a valid signature and the client uses it within the 2-hour window
- **THEN** Cloudinary serves the image

#### Scenario: Expired signed URL
- **WHEN** a client uses a signed URL that was generated more than 2 hours ago
- **THEN** Cloudinary returns HTTP 401 (token expired)

### Requirement: Cloudinary configuration
The system SHALL read Cloudinary credentials from environment variables: `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`. These SHALL be added to the `Settings` class and loaded via `.env` file.

#### Scenario: Valid configuration
- **WHEN** the application starts with all three Cloudinary environment variables set
- **THEN** the Cloudinary SDK is configured and the image upload service is operational

#### Scenario: Missing configuration
- **WHEN** the application starts without `CLOUDINARY_API_SECRET`
- **THEN** the application fails to start with a validation error from pydantic-settings

### Requirement: Non-blocking Cloudinary operations
All Cloudinary SDK calls (upload, destroy, URL generation) SHALL be wrapped in `asyncio.to_thread()` to prevent blocking the FastAPI event loop. Batch uploads SHALL use `asyncio.gather()` for concurrent execution.

#### Scenario: Concurrent batch upload
- **WHEN** a user uploads 5 images in a batch
- **THEN** all 5 uploads execute concurrently via `asyncio.gather(asyncio.to_thread(...))`, not sequentially
