from app.domain.models.meeting_utterance import MeetingUtteranceMessage
from app.domain.schemas.meeting import MeetingUtteranceMessageRecord
from app.repo.meeting_utterance_repo import MeetingUtteranceRepository
from app.services.meeting.note_state_store import RedisMeetingNoteStateStore


def test_meeting_utterance_repo_normalizes_schema_messages_to_domain_model() -> None:
    record = MeetingUtteranceMessageRecord(
        speaker_index=0,
        speaker_label="speaker_1",
        text="Xin chao",
    )

    [message] = MeetingUtteranceRepository._normalize_messages([record])

    assert isinstance(message, MeetingUtteranceMessage)
    assert message.model_dump(mode="python") == record.model_dump(mode="python")


def test_note_state_store_normalizes_domain_messages_to_schema_model() -> None:
    message = MeetingUtteranceMessage(
        speaker_index=1,
        speaker_label="speaker_2",
        text="Toi dang ghi chu",
    )

    [record] = RedisMeetingNoteStateStore._normalize_messages([message])

    assert isinstance(record, MeetingUtteranceMessageRecord)
    assert record.model_dump(mode="python") == message.model_dump(mode="python")
