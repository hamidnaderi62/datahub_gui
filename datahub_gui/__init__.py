# Celery is optional for local Django commands; production worker images install it.
try:
    from .celery import app as celery_app
except ModuleNotFoundError:  # pragma: no cover - dependency is installed in worker images
    celery_app = None

__all__ = ('celery_app',)
