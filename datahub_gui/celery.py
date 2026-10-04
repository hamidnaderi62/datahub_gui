import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'datahub_gui.settings')

app = Celery('datahub_gui')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
