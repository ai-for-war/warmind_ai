"""Repository scaffold for interview conversation persistence."""

from motor.motor_asyncio import AsyncIOMotorDatabase


class InterviewConversationRepository:
    """Database access wrapper for interview conversations."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.interview_conversations
