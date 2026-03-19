# Coding Conventions

**Analysis Date:** 2026-03-19

## Naming Patterns

**Files:**
- Use `snake_case.py` module names for source files, such as `app/api/v1/users/routes.py`, `app/services/user/user_service.py`, `app/repo/user_repo.py`, and `app/workers/image_generation_worker.py`.
- Use package marker files named `__init__.py`; curated barrel exports appear selectively in `app/domain/models/__init__.py`, `app/infrastructure/mcp/__init__.py`, and `app/graphs/workflows/conversation_orchestrator_workflow/nodes/__init__.py`.

**Functions:**
- Use `snake_case` for module functions, methods, and async handlers, for example `get_current_active_user` in `app/api/deps.py`, `create_user` in `app/services/user/user_service.py`, and `consume_due_turn_closures` in `app/services/stt/session.py`.
- Prefix internal helpers with `_`, for example `_to_user_response` in `app/api/v1/users/routes.py`, `_ensure_org_admin` in `app/services/user/user_service.py`, `_parse_json_response` in `app/infrastructure/minimax/client.py`, and `_compose_transcript` in `app/services/stt/session.py`.

**Variables:**
- Use `snake_case` for locals, instance attributes, and keyword arguments, such as `organization_id`, `stable_text_cache`, and `provider_result`.
- Use `UPPER_SNAKE_CASE` for module and class constants, such as `MCP_INIT_TIMEOUT` in `app/infrastructure/mcp/manager.py`, `MAX_LIMIT` in `app/services/ai/pipeline_validator.py`, and `BASE_URL` in `app/infrastructure/minimax/client.py`.
- Standardize loggers as `logger = logging.getLogger(__name__)` in modules that log, including `app/main.py`, `app/services/analytics/analytics_service.py`, and `app/workers/image_generation_worker.py`.

**Types:**
- Use `PascalCase` for classes, dataclasses, enums, and typed payload objects, such as `UserService`, `STTSessionEvent`, `MiniMaxClient`, and `OrganizationContext`.
- Use `PascalCase` for type aliases and literals too, such as `STTSpeakerRole` and `STTChannelIndex` in `app/domain/schemas/stt.py`.

## Code Style

**Formatting:**
- No formatter configuration file is checked in. `pyproject.toml`, `ruff.toml`, `.ruff.toml`, `.editorconfig`, and `setup.cfg` are not present at the repository root.
- Existing code follows a stable manual style: 4-space indentation, double-quoted strings, trailing commas in multiline calls, and one blank line between stdlib, third-party, and `app.*` imports. See `app/main.py`, `app/api/deps.py`, and `app/infrastructure/minimax/client.py`.
- Keep module, class, and public function docstrings. Nearly every inspected module starts with a top-level docstring, for example `app/main.py`, `app/common/exceptions.py`, `app/services/stt/session.py`, and `app/infrastructure/minimax/client.py`.
- Pydantic configuration style is mixed. Older models use inner `class Config` in files like `app/domain/models/user.py` and `app/domain/schemas/auth.py`, while newer models use `model_config = ConfigDict(...)` in `app/domain/models/interview_conversation.py` and `app/domain/schemas/stt.py`.

**Linting:**
- No lint configuration file is checked in. `.flake8`, `mypy.ini`, `.pre-commit-config.yaml`, and root-level Ruff config files are not present.
- Inline suppressions reference Ruff/Bugbear-style codes, so future code should follow the same pattern when broad catches are necessary: `# noqa: BLE001` appears in `app/main.py`, `app/infrastructure/mcp/manager.py`, and `app/workers/image_generation_worker.py`; `# noqa: ARG001` appears in `app/workers/image_generation_worker.py`.
- Broad exception catches are tolerated only at integration and process boundaries. Preserve that convention and annotate intentional catches with `noqa` rather than using silent blanket `except` blocks.

## Import Organization

**Order:**
1. Standard library imports such as `logging`, `datetime`, `functools`, and `typing`
2. Third-party imports such as `fastapi`, `pydantic`, `httpx`, `motor`, and `langchain_*`
3. Application imports rooted at `app.*`

**Path Aliases:**
- Use absolute imports from the `app` package, such as `from app.common.service import get_user_service` in `app/api/v1/users/routes.py` and `from app.repo.user_repo import UserRepository` in `app/services/user/user_service.py`.
- Relative imports are effectively not used for application code. Follow the existing `app.*` import convention for new modules.

## Error Handling

**Patterns:**
- Raise domain-specific `AppException` subclasses from business and infrastructure code. The canonical exception catalog lives in `app/common/exceptions.py`.
- Convert `AppException` into HTTP responses through the global FastAPI exception handler in `app/main.py`.
- Raise `HTTPException` directly in request-validation and authorization dependencies where the failure is an HTTP concern, as in `app/api/deps.py`, `app/api/v1/organizations/routes.py`, and `app/api/v1/sheet_crawler/router.py`.
- Wrap vendor and integration failures with application exceptions and preserve chaining via `raise ... from exc`, as in `app/services/auth/auth_service.py`, `app/infrastructure/google_sheets/client.py`, and `app/infrastructure/minimax/client.py`.
- Use broad `except Exception` blocks mainly around worker loops, streaming sessions, startup/shutdown, and optional integrations. Examples: `app/main.py`, `app/services/stt/session.py`, `app/socket_gateway/manager.py`, and `app/workers/image_generation_worker.py`.

## Logging

**Framework:** `logging`

**Patterns:**
- Define one module logger with `logging.getLogger(__name__)` and reuse it throughout the file.
- Configure process-level logging with `logging.basicConfig(...)` in entrypoints such as `app/main.py`, `app/workers/image_generation_worker.py`, and `app/workers/sheet_sync_worker.py`.
- Use `logger.info(...)` for lifecycle and routing events, `logger.warning(...)` for recoverable issues, `logger.error(...)` for explicit failure states, and `logger.exception(...)` when emitting stack traces.
- Some infrastructure modules attach structured context through `extra=...`, especially `app/infrastructure/deepgram/client.py`. Preserve that pattern for provider-facing telemetry.

## Comments

**When to Comment:**
- Prefer docstrings over inline comments. Public modules and classes are documented consistently in `app/common/exceptions.py`, `app/common/service.py`, `app/repo/user_repo.py`, and `app/services/stt/session.py`.
- Reserve inline comments for architecture notes, compatibility quirks, and non-obvious control flow. Examples include the MCP fallback explanation in `app/main.py`, the legacy compatibility key note in `app/infrastructure/minimax/client.py`, and security rationale comments in `app/services/ai/pipeline_validator.py`.
- Avoid explanatory comments for straightforward CRUD or mapping code. Those areas rely on method names and type hints instead, for example `app/services/user/user_service.py` and `app/repo/user_repo.py`.

**JSDoc/TSDoc:**
- Not applicable. Python docstrings are the project documentation style.
- Use triple-quoted docstrings for modules, classes, and public functions. Many methods include `Args`, `Returns`, and `Raises` sections, especially in `app/api/deps.py`, `app/common/service.py`, and `app/repo/user_repo.py`.

## Function Design

**Size:**
- Keep repository methods narrow and single-purpose, as in `app/repo/user_repo.py` and `app/repo/image_generation_job_repo.py`.
- Keep complex workflows inside classes with many focused private helpers rather than giant free functions. Representative examples are `app/services/stt/session.py`, `app/services/stt/session_manager.py`, and `app/infrastructure/deepgram/client.py`.

**Parameters:**
- Use explicit type hints throughout the codebase.
- Prefer keyword-only parameters for service methods with multiple inputs, using `*` after `self`, as in `app/services/user/user_service.py`, `app/services/auth/auth_service.py`, and `app/services/image/image_generation_service.py`.
- The codebase mixes `Optional[T]` and `T | None` syntax. New code should match the surrounding file rather than forcing one style across old and new modules.

**Return Values:**
- Repository methods usually return a domain model or `None`; list endpoints return typed lists such as `list[User]` or `list[dict[str, Any]]`.
- API routes return response schemas explicitly, often through small adapter helpers like `_to_user_response` in `app/api/v1/users/routes.py`.
- Streaming and orchestration code returns normalized event objects instead of raw SDK payloads, as in `STTSessionEvent` from `app/services/stt/session.py`.

## Module Design

**Exports:**
- Most modules expose one primary class, router, or helper group and are imported directly by path.
- Centralized singleton factories live in `app/common/repo.py` and `app/common/service.py`. They use `@lru_cache` to provide shared repository, service, queue, and client instances.

**Barrel Files:**
- Barrel files exist selectively where a package has a public surface. Use `__all__` when exporting a curated set of symbols, as in `app/domain/models/__init__.py`, `app/infrastructure/mcp/__init__.py`, and `app/graphs/workflows/conversation_orchestrator_workflow/nodes/__init__.py`.
- Many package `__init__.py` files are intentionally empty markers. Do not assume every new package needs a barrel export; follow the pattern already used in the target directory.

---

*Convention analysis: 2026-03-19*
