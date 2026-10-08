#!/bin/sh

# Lightweight connector worker. The API deliberately exposes job creation as
# an asynchronous endpoint; this process is the single consumer for queued
# jobs in the local Compose deployment.
set -u

poll_interval="${IMPORT_WORKER_POLL_INTERVAL:-5}"

while :; do
    job_id="$(python manage.py shell -c "from ingestion.models import ImportJob; job=ImportJob.objects.filter(status=ImportJob.Status.QUEUED).order_by('created_at').first(); print(job.pk if job else '')" 2>/dev/null | tail -n 1 | tr -d '\r')"

    if [ -n "$job_id" ]; then
        echo "[api-worker] processing import job $job_id"
        # The management command records a failed state on provider/storage
        # errors. Continue polling so one bad dataset cannot stop the worker.
        python manage.py process_import_job --job-id "$job_id" || true
    else
        sleep "$poll_interval"
    fi
done
