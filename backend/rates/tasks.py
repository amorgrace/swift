import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='rates.tasks.refresh_rates')
def refresh_rates():
    """
    Proactively fetch all crypto rates from CoinGecko and update CachedRate.
    Scheduled every 60 seconds via Celery Beat so no user request ever
    triggers a synchronous CoinGecko fetch.
    """
    from rates.services import RateService
    try:
        RateService.fetch_live_rates()
        logger.info("[refresh_rates] Rates updated by Celery Beat.")
    except Exception as exc:
        logger.error(f"[refresh_rates] Rate refresh failed: {exc}")
        # Don't raise — Beat will fire again in 60s anyway
