"""Repository scaffold for interview utterance persistence."""

from motor.motor_asyncio import AsyncIOMotorDatabase


class InterviewUtteranceRepository:
    """Database access wrapper for interview utterances."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.interview_utterances
