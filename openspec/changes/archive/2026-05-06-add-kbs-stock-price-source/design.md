## Context

The stock price timeseries implementation currently uses a single `VnstockPriceGateway` with `SOURCE = "VCI"`. Both history and intraday endpoints return normalized `vnstock.Quote` data and cache responses by symbol, endpoint section, and query variant.

The vnstock price history documentation states that both `VCI` and `KBS` support `history()` and `intraday()`, but the method contracts are not identical. KBS intraday supports `page_size` and `get_all`, while VCI intraday supports `page_size`, `last_time`, and `last_time_format`. KBS also returns intraday `id` values as strings in documented examples, while VCI returns numeric identifiers.

## Goals / Non-Goals

**Goals:**

- Allow callers to explicitly request stock price timeseries from `VCI` or `KBS`.
- Preserve existing behavior by defaulting to `VCI` when no source is supplied.
- Keep source-specific cache entries isolated.
- Validate source-specific intraday query parameters instead of silently ignoring unsupported cursors.
- Keep the public response shape stable except for allowing KBS-compatible source and intraday identifier values.

**Non-Goals:**

- Automatic fallback between VCI and KBS.
- Provider rotation, health checks, or source preference configuration.
- Exposing KBS-only `get_all` in the public API in the initial change.
- Adding derived analytics or cross-provider field aliases beyond the documented shared fields.

## Decisions

1. Use an explicit `source` query parameter with default `VCI`.

   This keeps existing clients compatible while making KBS usage observable and debuggable. The alternative, automatic VCI-to-KBS fallback, was rejected because it can return mixed provider data for identical client requests and makes cache/debug behavior less predictable.

2. Include `source` in cache variants.

   VCI and KBS can differ in timezone representation, row ordering, identifier type, and casing. Cache keys must include source so a KBS request cannot receive a VCI payload, or vice versa.

3. Validate unsupported KBS intraday cursors as request errors.

   KBS does not document `last_time` or `last_time_format` for intraday reads. If a caller supplies those parameters with `source=KBS`, the service should reject the request rather than silently dropping them, because silent omission would make pagination appear to work while returning an un-cursored slice.

4. Keep normalized fields limited to the documented shared fields.

   Both providers document history fields `time`, `open`, `high`, `low`, `close`, `volume` and intraday fields `time`, `price`, `volume`, `match_type`, `id`. The backend should keep using those canonical fields and avoid speculative alias mappings.

5. Allow intraday identifiers to be integers or strings.

   VCI examples use numeric IDs and KBS examples use composite string IDs. Normalization should preserve a stable integer for numeric values and preserve non-empty strings for KBS identifiers instead of forcing all IDs to integers.

## Risks / Trade-offs

- KBS runtime behavior may differ from documentation -> Verify the installed `vnstock` runtime before finalizing source-specific argument handling, and keep comments near integration points if runtime and docs differ.
- KBS and VCI may return different row ordering or timestamps -> Preserve upstream order and include `source` in the response so clients can interpret provider-specific behavior.
- Expanding `id` to `int | str` can affect clients assuming integers -> This is required to support documented KBS payloads; VCI responses remain numeric where possible.
- Larger `page_size` support can increase upstream latency and response payload size -> Do not raise the public limit in this change unless product explicitly needs it; supporting KBS source does not require changing the current limit.

## Migration Plan

- Deploy as a backward-compatible API extension with `source` defaulting to `VCI`.
- Existing requests without `source` continue to use VCI and existing query semantics.
- New KBS requests use `source=KBS` and must not include VCI-only intraday cursor parameters.
- Rollback is straightforward because no data migration is required; revert the source schema, gateway source selection, and cache variant changes.
