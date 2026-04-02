from sqlalchemy.ext.asyncio import AsyncSession


class ConversationRepository:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    pass
