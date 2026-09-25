from celery import shared_task
from django.contrib.auth import get_user_model

from reference.data_utils import resolve_references_result

TASK_SOFT_TIME_LIMIT = 30 * 60
TASK_TIME_LIMIT = 31 * 60


@shared_task(
    bind=True,
    soft_time_limit=TASK_SOFT_TIME_LIMIT,
    time_limit=TASK_TIME_LIMIT,
)
def mark_reference_texts_task(self, texts, user_id=None, output_type="json"):
    total = len(texts) if isinstance(texts, list) else 0

    def on_progress(done, progress_total):
        percent = 0
        if progress_total:
            percent = int((done / progress_total) * 100)
        self.update_state(
            state="PROGRESS",
            meta={"percent": percent, "done": done, "total": progress_total},
        )

    on_progress(0, total)
    user = None
    if user_id is not None:
        user = get_user_model().objects.filter(pk=user_id).first()
    return resolve_references_result(
        texts,
        user=user,
        output_type=output_type,
        on_progress=on_progress,
    )
