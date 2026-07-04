"""APScheduler 定时任务管理。

管理每日早间简报的定时触发。
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def create_scheduler() -> AsyncIOScheduler:
    """创建调度器实例。

    Returns:
        AsyncIOScheduler 实例。
    """
    global _scheduler
    _scheduler = AsyncIOScheduler(
        timezone="Asia/Shanghai",
        job_defaults={
            "coalesce": True,           # 合并错过的任务
            "max_instances": 1,         # 同一任务最多同时运行1个
            "misfire_grace_time": 300,  # 错过后5分钟内的任务仍执行
        },
    )
    return _scheduler


def get_scheduler() -> AsyncIOScheduler:
    """获取当前调度器实例。

    Returns:
        AsyncIOScheduler 实例。

    Raises:
        RuntimeError: 调度器未初始化。
    """
    if _scheduler is None:
        raise RuntimeError("调度器未初始化，请先调用 create_scheduler()")
    return _scheduler


def add_morning_briefing_job(
    scheduler: AsyncIOScheduler,
    job_func,
    time_str: str = "08:00",
    timezone: str = "Asia/Shanghai",
) -> str:
    """添加早间简报定时任务。

    Args:
        scheduler: 调度器实例。
        job_func: 要执行的协程函数。
        time_str: 触发时间 "HH:MM"。
        timezone: 时区。

    Returns:
        任务 ID。
    """
    hour, minute = time_str.split(":")
    trigger = CronTrigger(
        hour=int(hour),
        minute=int(minute),
        timezone=timezone,
    )

    job = scheduler.add_job(
        job_func,
        trigger=trigger,
        id="morning_briefing",
        name="早间简报",
        replace_existing=True,
    )

    logger.info(f"已添加早间简报定时任务: 每日 {time_str} ({timezone})")
    return job.id


def start_scheduler(scheduler: AsyncIOScheduler) -> None:
    """启动调度器。

    Args:
        scheduler: 调度器实例。
    """
    scheduler.start()
    logger.info("调度器已启动")

    # 输出下次执行时间
    job = scheduler.get_job("morning_briefing")
    if job:
        logger.info(f"下次早间简报: {job.next_run_time}")


def stop_scheduler(scheduler: AsyncIOScheduler) -> None:
    """停止调度器。

    Args:
        scheduler: 调度器实例。
    """
    scheduler.shutdown(wait=False)
    logger.info("调度器已停止")
