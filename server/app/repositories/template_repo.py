from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import TaskTemplate
from app.schemas.template import TaskTemplateCreate, TaskTemplateRead, TaskTemplateUpdate


class TemplateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self) -> Sequence[TaskTemplate]:
        statement = select(TaskTemplate).order_by(TaskTemplate.label.asc(), TaskTemplate.id.asc())
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def get_by_id(self, template_id: str) -> TaskTemplate | None:
        statement = select(TaskTemplate).where(TaskTemplate.id == template_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def create(self, template: TaskTemplateCreate | TaskTemplateRead) -> TaskTemplate:
        model = TaskTemplate(**template.model_dump())
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return model

    async def create_many(self, templates: list[TaskTemplateRead]) -> None:
        self.session.add_all([TaskTemplate(**template.model_dump()) for template in templates])
        await self.session.commit()

    async def update(self, template: TaskTemplate, payload: TaskTemplateUpdate) -> TaskTemplate:
        for field, value in payload.model_dump().items():
            setattr(template, field, value)
        await self.session.commit()
        await self.session.refresh(template)
        return template

    async def delete(self, template: TaskTemplate) -> None:
        await self.session.delete(template)
        await self.session.commit()

    async def track_use(self, template: TaskTemplate, used_at: datetime) -> TaskTemplate:
        template.usage_count += 1
        template.last_used_at = used_at
        await self.session.commit()
        await self.session.refresh(template)
        return template

    async def count_all(self) -> int:
        statement = select(func.count()).select_from(TaskTemplate)
        return await self.session.scalar(statement) or 0
