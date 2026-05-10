from app.services.meeting import note_generation_service


def test_meeting_note_generation_uses_responses_openai_gpt_5_4_mini_by_default(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def _fake_get_chat_openai(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        note_generation_service,
        "get_chat_openai",
        _fake_get_chat_openai,
    )

    llm = note_generation_service.MeetingNoteGenerationService._default_llm_factory()

    assert llm is sentinel
    assert captured == {
        "model": "gpt-5.4-mini",
        "temperature": 0.2,
        "streaming": False,
        "max_tokens": 1024,
        "reasoning_effort": "medium",
    }
