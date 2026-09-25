from celery import shared_task
from django.contrib.auth import get_user_model

from front.data_utils import resolve_front_result

TASK_SOFT_TIME_LIMIT = 30 * 60
TASK_TIME_LIMIT = 31 * 60


@shared_task(
    bind=True,
    soft_time_limit=TASK_SOFT_TIME_LIMIT,
    time_limit=TASK_TIME_LIMIT,
)
def mark_front_text(
    self, text, language=None, counts=None, user_id=None, output_type="json"
):
    self.update_state(state="PROGRESS", meta={"percent": 10})
    user = None
    if user_id is not None:
        user = get_user_model().objects.filter(pk=user_id).first()
    return resolve_front_result(
        text,
        user=user,
        output_type=output_type,
        language=language,
        counts=counts,
    )
