## 1. Dependencies & Configuration

- [x] 1.1 Add `cloudinary` and `python-magic-bin` to `requirements.txt`
- [x] 1.2 Add Cloudinary settings (`CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`) to `app/config/settings.py`
- [x] 1.3 Add `.env.example` entries for the three Cloudinary environment variables

## 2. Domain Models & Schemas

- [ ] 2.1 Create `app/domain/models/image.py` with `Image` model (id, public_id, organization_id, uploaded_by, original_filename, mime_type, size_bytes, cloudinary_folder, created_at, deleted_at)
- [ ] 2.2 Create `app/domain/schemas/image.py` with request/response schemas: `ImageUploadResponse`, `ImageDetailResponse` (with signed_url field), `ImageListResponse` (paginated), `ImageRecord`

## 3. Exceptions

- [ ] 3.1 Add `ImageNotFoundError`, `ImageUploadError`, `InvalidImageTypeError`, `FileSizeLimitExceededError` to `app/common/exceptions.py`

## 4. Infrastructure — Cloudinary Client

- [ ] 4.1 Create `app/infrastructure/cloudinary/client.py` with `CloudinaryClient` class
- [ ] 4.2 Implement `configure()` method to initialize Cloudinary SDK from settings
- [ ] 4.3 Implement `async upload(file_bytes, filename, folder, org_id)` wrapping `cloudinary.uploader.upload` with `asyncio.to_thread`, using `type="authenticated"`
- [ ] 4.4 Implement `async delete(public_id)` wrapping `cloudinary.uploader.destroy` with `asyncio.to_thread` and `invalidate=True`
- [ ] 4.5 Implement `generate_signed_url(public_id, expiry_seconds=7200)` using `cloudinary.utils.cloudinary_url` with `sign_url=True` and `type="authenticated"`
- [ ] 4.6 Add `get_cloudinary_client()` factory function to `app/common/service.py`

## 5. Repository

- [ ] 5.1 Create `app/repo/image_repo.py` with `ImageRepository` class
- [ ] 5.2 Implement `create(image_data)` — insert image metadata into `images` collection
- [ ] 5.3 Implement `find_by_id(image_id)` — find non-deleted image by ID
- [ ] 5.4 Implement `find_by_id_and_org(image_id, org_id)` — find non-deleted image scoped to organization
- [ ] 5.5 Implement `list_by_organization(org_id, skip, limit)` — paginated list with total count, sorted by `created_at` desc, excluding deleted
- [ ] 5.6 Implement `soft_delete(image_id)` — set `deleted_at` timestamp
- [ ] 5.7 Add `get_image_repo()` factory function to `app/common/repo.py`

## 6. Service

- [ ] 6.1 Create `app/services/image/image_service.py` with `ImageService` class
- [ ] 6.2 Implement `validate_file(file)` — streaming chunk-based size check (25MB), magic bytes MIME validation via `python-magic`
- [ ] 6.3 Implement `upload_images(files, user_id, org_id)` — validate each file, upload concurrently via `asyncio.gather`, store metadata, return successes/failures
- [ ] 6.4 Implement `get_image(image_id, org_id)` — fetch metadata, generate signed URL (2h expiry), return combined response
- [ ] 6.5 Implement `list_images(org_id, skip, limit)` — delegate to repository with pagination
- [ ] 6.6 Implement `delete_image(image_id, user_id, user_role, org_id, org_role)` — check permission (owner OR org_admin OR super_admin), soft-delete in MongoDB, hard-delete in Cloudinary
- [ ] 6.7 Add `get_image_service()` factory function to `app/common/service.py`

## 7. API Router

- [ ] 7.1 Create `app/api/v1/images/router.py` with `APIRouter(prefix="/images", tags=["Images"])`
- [ ] 7.2 Implement `POST /upload` endpoint — accept `list[UploadFile]` (max 10), require `get_current_active_user` + `get_current_organization_context`, return `ImageUploadResponse`
- [ ] 7.3 Implement `GET /` endpoint — accept `skip` and `limit` query params, require auth + org context, return `ImageListResponse`
- [ ] 7.4 Implement `GET /{image_id}` endpoint — require auth + org context, return `ImageDetailResponse` with signed URL
- [ ] 7.5 Implement `DELETE /{image_id}` endpoint — require auth + org context, check delete permission, return 204
- [ ] 7.6 Register image router in `app/api/v1/router.py`

## 8. Cloudinary Initialization

- [ ] 8.1 Add Cloudinary SDK configuration call in `app/main.py` lifespan startup (call `CloudinaryClient.configure()`)
