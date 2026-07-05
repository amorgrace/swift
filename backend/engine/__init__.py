# This ensures the Celery app is loaded whenever Django starts,
# so the @shared_task decorator works correctly in all apps.
from .celery import app as celery_app

__all__ = ('celery_app',)
