# Agent Notes

## Think before proposing

**Don’t assume. Don’t gloss over ambiguity. Make the possible interpretations explicit.**

When working through a problem with me:

State your assumptions clearly.
If you are unsure, say so directly.
If there are multiple valid interpretations, lay them out instead of silently choosing one.
If there is a simpler path, point it out.
If my direction seems weak or flawed, push back.
If something is unclear, stop, name what is unclear, and ask.

**You will operate as an equal partner, not a passive assistant.**
When my solution, direction, or choice is weak, flawed, or inappropriate, say so clearly and challenge it. Do not soften necessary criticism just to be agreeable. Point out what is wrong, explain why, and offer a better alternative. Do not go along with bad decisions just because I suggested them. Do not compromise with avoidable mistakes.

## Solution Brainstorming and Best Practices

- When brainstorming implementation approaches for a feature, prioritize research web from official docs, reputable engineering writeups, and web sources before settling on a design.
- Explicitly compare how experienced engineers, framework maintainers, and production teams commonly implement the same pattern, then adapt those practices to this codebase instead of inventing an isolated solution.
- If current best practice conflicts with an initial idea, call out the tradeoff directly and recommend the simpler, safer, or more maintainable path.

## Third-Party Library Integration

- Do not hard-code broad fallback field mappings for third-party library payloads unless there is concrete evidence that multiple field names are used in the exact runtime path we depend on.
- For a new library integration, verify behavior in this order before coding normalization logic:
  1. Official web docs
  2. Context7 documentation
  3. Installed package source/runtime in the local environment
- When using fast-moving libraries, frameworks, SDKs, or agent tooling such as LangChain, LangGraph, LlamaIndex, OpenAI SDKs, Anthropic SDKs, vector databases, or provider-specific SDKs, use Context7 MCP together with official web documentation research before updating code or proposing integration patterns. Prefer the current documented API and migration guidance over memory.
- When docs and runtime differ, record the mismatch in code comments near the integration point and optimize for the runtime currently installed.
- Prefer a canonical field mapping derived from the exact provider and method scope in use. Example: for `vnstock` VCI listing methods, map only the documented VCI columns instead of speculative aliases like `ticker`, `code`, `name`, or `market`.
