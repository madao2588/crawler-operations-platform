from apscheduler.schedulers.asyncio import AsyncIOScheduler


scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


def get_scheduler() -> AsyncIOScheduler:
    return scheduler
