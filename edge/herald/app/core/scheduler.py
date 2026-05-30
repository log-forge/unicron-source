"""Shared AsyncIOScheduler singleton.

This module exists to avoid circular imports between task modules
and the tasks package by providing a neutral place to import the
shared scheduler instance from.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Global scheduler instance for the herald service
scheduler: AsyncIOScheduler = AsyncIOScheduler()
