from celery import shared_task

from .pipeline import process_pipeline_run


@shared_task(
    bind=True,
    name='dataset.process_pipeline_run',
    acks_late=True,
    track_started=True,
)
def process_pipeline_task(self, run_id):
    """Execute one durable run in a separately scalable worker process."""
    run = process_pipeline_run(run_id)
    return {'run_id': run.id, 'status': run.status}
