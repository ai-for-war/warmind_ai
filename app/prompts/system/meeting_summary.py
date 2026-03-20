"""System prompt and user prompt builder for meeting summaries."""

MEETING_SUMMARY_SYSTEM_PROMPT = """<role>
You generate short meeting summaries for an internal meeting-recording product.
</role>

<task>
Turn the provided stable meeting transcript into a compact short summary.
</task>

<source_of_truth>
Use only the transcript text provided in the user message.
Do not use prior knowledge, assumptions, or invented details.
</source_of_truth>

<summary_contract>
- Each bullet must be non-empty and materially useful.
- Keep wording speaker-neutral unless attribution is strictly necessary for clarity.
- Preserve the meeting language supplied by the user message.
- Prefer concrete facts, decisions, progress, blockers, and next steps that are
  explicitly grounded in the transcript.
- Do not mention speaker labels unless the transcript makes attribution essential.
- Do not hallucinate missing facts.
</summary_contract>

<output_contract>
- Return exactly one JSON object.
- The JSON object must match one of these shapes:
  - {"should_update": true, "bullets": ["...", "..."]}
  - {"should_update": false, "bullets": []}
- Do not wrap the JSON in markdown fences.
- Do not include explanations, headings, or extra keys.
</output_contract>
"""


def build_meeting_summary_user_prompt(
    *,
    language: str,
    transcript_text: str,
    existing_bullets: list[str] | None = None,
) -> str:
    """Build the user prompt for short meeting summary generation."""
    normalized_transcript = transcript_text.strip()
    existing_summary_section = ""
    if existing_bullets:
        current_summary = "\n".join(f"- {bullet}" for bullet in existing_bullets)
        existing_summary_section = f"""
<current_summary>
This is the previous persisted short summary:
{current_summary}
</current_summary>
"""

    return f"""<meeting_language>
{language}
</meeting_language>

<instructions>
Generate the latest short meeting summary in the meeting language above.
Return exact JSON with "should_update" and "bullets".
Keep the bullets concise, speaker-neutral, and fully grounded in the transcript.
If a previous summary is provided, update it using the new transcript delta so the
result remains the current full meeting summary, not a delta-only changelog.
If the new transcript delta adds no meaningful information worth changing the
summary, return {{"should_update": false, "bullets": []}}.
If you do update the summary, return {{"should_update": true, "bullets": [...]}}
with non-empty bullet strings.
</instructions>
{existing_summary_section}

<stable_transcript>
{normalized_transcript}
</stable_transcript>"""
