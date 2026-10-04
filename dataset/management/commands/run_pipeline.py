from django.core.management.base import BaseCommand, CommandError

from dataset.models import PipelineRun
from dataset.pipeline import process_pipeline_run


class Command(BaseCommand):
    help = 'Process queued preprocessing runs through the safe metadata gate.'

    def add_arguments(self, parser):
        parser.add_argument('--run-id', type=int)
        parser.add_argument('--limit', type=int, default=1)

    def handle(self, *args, **options):
        run_id = options.get('run_id')
        if run_id is not None:
            run_ids = [run_id]
        else:
            if options['limit'] < 1:
                raise CommandError('--limit must be positive')
            run_ids = list(
                PipelineRun.objects
                .filter(status=PipelineRun.Status.QUEUED)
                .order_by('created_at')
                .values_list('id', flat=True)[:options['limit']]
            )

        if not run_ids:
            self.stdout.write('No queued pipeline runs.')
            return

        for selected_id in run_ids:
            try:
                run = process_pipeline_run(selected_id)
            except PipelineRun.DoesNotExist as exc:
                raise CommandError(f'Pipeline run not found: {selected_id}') from exc
            self.stdout.write(
                self.style.SUCCESS(
                    f'pipeline_run={run.id} status={run.status}'
                )
            )
