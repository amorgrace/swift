import os

from celery import Celery

# Tell Celery which Django settings to use
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'engine.settings')

app = Celery('engine')

# Pull all CELERY_* settings from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks.py in every INSTALLED_APP
app.autodiscover_tasks()
