from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.core.database import AsyncSessionLocal
from app.repositories.template_repo import TemplateRepository
from app.services.template_service import (
    NEW_DRUG_SOURCE_TEMPLATES,
    TemplateService,
)


async def _sync() -> int:
    async with AsyncSessionLocal() as session:
        service = TemplateService(template_repo=TemplateRepository(session))
        await service.sync_required_source_templates()
        templates = await service.list_task_templates()
    print(
        json.dumps(
            {
                "status": "ok",
                "required_source_templates": len(NEW_DRUG_SOURCE_TEMPLATES),
                "total_templates": len(templates),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    return asyncio.run(_sync())


if __name__ == "__main__":
    raise SystemExit(main())
