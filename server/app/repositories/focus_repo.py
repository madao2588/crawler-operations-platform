from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notice_focus import NoticeFocus


class NoticeFocusRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_data_ids(self, user_id: int) -> set[int]:
        result = await self.session.execute(
            select(NoticeFocus.data_id).where(NoticeFocus.user_id == user_id)
        )
        return {int(value) for value in result.scalars().all()}

    async def add(self, user_id: int, data_id: int) -> None:
        exists = await self.session.scalar(
            select(NoticeFocus.id).where(
                NoticeFocus.user_id == user_id,
                NoticeFocus.data_id == data_id,
            )
        )
        if exists is None:
            self.session.add(NoticeFocus(user_id=user_id, data_id=data_id))
            await self.session.commit()

    async def remove(self, user_id: int, data_id: int) -> None:
        await self.session.execute(
            delete(NoticeFocus).where(
                NoticeFocus.user_id == user_id,
                NoticeFocus.data_id == data_id,
            )
        )
        await self.session.commit()
