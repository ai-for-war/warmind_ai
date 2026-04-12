# Agent Notes

## Third-Party Library Integration

- Do not hard-code broad fallback field mappings for third-party library payloads unless there is concrete evidence that multiple field names are used in the exact runtime path we depend on.
- For a new library integration, verify behavior in this order before coding normalization logic:
  1. Official web docs
  2. Context7 documentation
  3. Installed package source/runtime in the local environment
- When docs and runtime differ, record the mismatch in code comments near the integration point and optimize for the runtime currently installed.
- Prefer a canonical field mapping derived from the exact provider and method scope in use. Example: for `vnstock` VCI listing methods, map only the documented VCI columns instead of speculative aliases like `ticker`, `code`, `name`, or `market`.
