"""
Crawler Scheduler Service

Manages scheduled crawler execution using APScheduler with cron expressions.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
import asyncio

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.pool import ThreadPoolExecutor

from core.extensions import db
from core.models import Crawler
from services.scraper_manager import get_scraper_manager, cleanup_scraper_manager

logger = logging.getLogger(__name__)


class CrawlerScheduler:
    """Manages scheduled crawler execution"""

    def __init__(self):
        self.scheduler = BackgroundScheduler(
            executors={"default": ThreadPoolExecutor(max_workers=5)},
            job_defaults={"coalesce": False, "max_instances": 1},
        )
        self.scheduler.start()
        logger.info("✅ Crawler scheduler started")

    def add_crawler_job(self, crawler_id: str, cron_expression: str) -> bool:
        """Add or update a scheduled job for a crawler"""
        try:
            # Validate cron expression
            trigger = CronTrigger.from_crontab(cron_expression)

            # Remove existing job if any
            self.remove_crawler_job(crawler_id)

            # Add new job
            self.scheduler.add_job(
                func=self._execute_crawler,
                trigger=trigger,
                id=crawler_id,
                args=[crawler_id],
                name=f"Crawler: {crawler_id}",
                replace_existing=True,
            )

            logger.info(
                f"✅ Scheduled crawler {crawler_id} with cron: {cron_expression}"
            )

            # Update next run time in database
            self._update_next_run_time(crawler_id)

            return True

        except Exception as e:
            logger.error(f"Failed to schedule crawler {crawler_id}: {e}")
            return False

    def remove_crawler_job(self, crawler_id: str) -> bool:
        """Remove a scheduled job"""
        try:
            self.scheduler.remove_job(crawler_id)
            logger.info(f"✅ Removed schedule for crawler {crawler_id}")
            return True
        except Exception:
            # Job doesn't exist, that's fine
            return True

    def pause_crawler_job(self, crawler_id: str) -> bool:
        """Pause a scheduled job"""
        try:
            self.scheduler.pause_job(crawler_id)
            logger.info(f"⏸️  Paused schedule for crawler {crawler_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to pause crawler {crawler_id}: {e}")
            return False

    def resume_crawler_job(self, crawler_id: str) -> bool:
        """Resume a paused job"""
        try:
            self.scheduler.resume_job(crawler_id)
            logger.info(f"▶️  Resumed schedule for crawler {crawler_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to resume crawler {crawler_id}: {e}")
            return False

    def _execute_crawler(self, crawler_id: str):
        """Execute a crawler (called by scheduler)"""
        logger.info(f"🔔 Scheduled execution triggered for crawler: {crawler_id}")

        try:
            # Get scraper manager
            scraper_manager = get_scraper_manager(crawler_id, admin_id=None)

            # Run asynchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                scraper_manager.start_scraper(run_type="scheduled")
            )
            loop.close()

            if result["success"]:
                logger.info(f"✅ Scheduled run completed for: {crawler_id}")

                # Automatically reschedule for 3 months later at 2 AM
                self._reschedule_quarterly(crawler_id)
            else:
                logger.error(
                    f"❌ Scheduled run failed for: {crawler_id}: {result.get('error')}"
                )

            # Update next run time
            self._update_next_run_time(crawler_id)

        except Exception as e:
            logger.error(
                f"Error executing scheduled crawler {crawler_id}: {e}", exc_info=True
            )
        finally:
            cleanup_scraper_manager(crawler_id)

    def _reschedule_quarterly(self, crawler_id: str):
        """Automatically reschedule crawler for 3 months later at 2 AM"""
        try:
            # Calculate date 3 months from now
            next_date = datetime.now() + timedelta(days=90)  # ~3 months

            # Set time to 2:00 AM
            next_date = next_date.replace(hour=2, minute=0, second=0, microsecond=0)

            # Build cron expression: "0 2 {day} {month} *"
            new_cron = f"0 2 {next_date.day} {next_date.month} *"

            logger.info(
                f"🔄 Auto-rescheduling {crawler_id} for {next_date.strftime('%Y-%m-%d %H:%M')}"
            )

            # Update database
            crawler = Crawler.query.get(crawler_id)
            if crawler:
                crawler.schedule_cron = new_cron
                db.session.commit()

                # Reschedule the job
                self.add_crawler_job(crawler_id, new_cron)
                logger.info(f"✅ Auto-reschedule complete: {new_cron}")
            else:
                logger.error(f"Crawler {crawler_id} not found for rescheduling")

        except Exception as e:
            logger.error(f"Failed to auto-reschedule {crawler_id}: {e}", exc_info=True)

    def _update_next_run_time(self, crawler_id: str):
        """Update the next_run_at field in database"""
        try:
            job = self.scheduler.get_job(crawler_id)
            if job:
                next_run = job.next_run_time
                crawler = Crawler.query.get(crawler_id)
                if crawler:
                    crawler.next_run_at = next_run
                    db.session.commit()
        except Exception as e:
            logger.error(f"Failed to update next run time: {e}")

    def load_all_schedules(self):
        """Load all active crawler schedules from database"""
        logger.info("Loading crawler schedules from database...")

        crawlers = Crawler.query.filter_by(is_active=True).all()

        for crawler in crawlers:
            if crawler.schedule_cron:
                self.add_crawler_job(crawler.id, crawler.schedule_cron)

        logger.info(f"✅ Loaded {len(crawlers)} crawler schedules")

    def get_scheduled_jobs(self):
        """Get all scheduled jobs"""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": job.next_run_time.isoformat()
                    if job.next_run_time
                    else None,
                    "trigger": str(job.trigger),
                }
            )
        return jobs

    def shutdown(self):
        """Shutdown the scheduler"""
        self.scheduler.shutdown()
        logger.info("Crawler scheduler shutdown")


# Global scheduler instance
_scheduler_instance: Optional[CrawlerScheduler] = None


def get_scheduler() -> CrawlerScheduler:
    """Get or create the global scheduler instance"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = CrawlerScheduler()
    return _scheduler_instance


def init_scheduler():
    """Initialize scheduler and load schedules"""
    scheduler = get_scheduler()
    scheduler.load_all_schedules()
    return scheduler
