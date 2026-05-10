from types import SimpleNamespace

from app.services.interview import answer_service


def test_interview_answer_uses_responses_openai_gpt_5_4_mini_medium_reasoning(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def _fake_get_chat_openai(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        answer_service,
        "get_chat_openai",
        _fake_get_chat_openai,
    )

    llm = answer_service.InterviewAnswerService._default_llm_factory()

    assert llm is sentinel
    assert captured == {
        "model": "gpt-5.4-mini",
        "temperature": 0.5,
        "streaming": True,
        "max_tokens": 1024,
        "reasoning_effort": "medium",
    }


def test_interview_answer_extracts_stream_text_from_content_blocks() -> None:
    chunk = SimpleNamespace(
        text="",
        content_blocks=[
            {"type": "reasoning", "reasoning": "thinking"},
            {"type": "text", "text": "final answer"},
        ],
        content="",
    )

    token = answer_service.InterviewAnswerService._extract_stream_token(chunk)

    assert token == "final answer"


def test_interview_answer_extracts_stream_text_from_responses_content() -> None:
    content = [
        {"type": "reasoning", "reasoning": "thinking"},
        {"type": "text", "text": "hello"},
        {"type": "text", "text": " world"},
    ]

    token = answer_service.InterviewAnswerService._extract_stream_token(content)

    assert token == "hello world"
