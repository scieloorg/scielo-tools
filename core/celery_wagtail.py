import inspect
import json

from celery import current_app
from django.conf import settings
from django.contrib import messages
from django.db.models import Case, Value, When
from django.shortcuts import get_object_or_404, redirect
from django.template.defaultfilters import pluralize
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import (
    ClockedSchedule,
    CrontabSchedule,
    IntervalSchedule,
    PeriodicTask,
    PeriodicTasks,
    SolarSchedule,
)
from django_celery_beat.utils import is_database_scheduler
from kombu.utils.json import loads
from wagtail import hooks
from wagtail.admin import messages as wagtail_messages
from wagtail_modeladmin.helpers import ButtonHelper
from wagtail_modeladmin.options import ModelAdmin, ModelAdminGroup, modeladmin_register

from config.menu import get_menu_order


class PeriodicTaskHelper(ButtonHelper):
    run_button_classnames = [
        "button-small",
        "icon",
    ]

    def run_button(self, obj):
        text = _("Run")
        return {
            "url": reverse("celery_task_run") + f"?task_id={str(obj.id)}",
            "label": text,
            "classname": self.finalise_classname(self.run_button_classnames),
            "title": text,
        }

    def get_buttons_for_obj(
        self, obj, exclude=None, classnames_add=None, classnames_exclude=None
    ):
        btns = super().get_buttons_for_obj(
            obj, exclude, classnames_add, classnames_exclude
        )
        if "run" not in (exclude or []):
            btns.append(self.run_button(obj))
        return btns


class PeriodicTaskAdmin(ModelAdmin):
    button_helper_class = PeriodicTaskHelper
    model = PeriodicTask
    menu_icon = "cog"
    celery_app = current_app
    date_hierarchy = "start_time"
    list_display = (
        "__str__",
        "enabled",
        "interval",
        "start_time",
        "last_run_at",
        "one_off",
    )
    list_filter = [
        "enabled",
        "one_off",
        "task",
    ]
    actions = ("enable_tasks", "disable_tasks", "toggle_tasks", "run_tasks")
    search_fields = ("name",)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        scheduler = getattr(settings, "CELERYBEAT_SCHEDULER", None)
        extra_context["wrong_scheduler"] = not is_database_scheduler(scheduler)
        return super().changelist_view(request, extra_context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("interval", "crontab", "solar", "clocked")

    def _message_user_about_update(self, request, rows_updated, verb):
        self.message_user(
            request,
            _("{0} task{1} {2} successfully {3}").format(
                rows_updated,
                pluralize(rows_updated),
                pluralize(rows_updated, _("was,were")),
                verb,
            ),
        )

    def enable_tasks(self, request, queryset):
        rows_updated = queryset.update(enabled=True)
        PeriodicTasks.update_changed()
        self._message_user_about_update(request, rows_updated, "enabled")

    enable_tasks.short_description = _("Enable selected tasks")

    def disable_tasks(self, request, queryset):
        rows_updated = queryset.update(enabled=False, last_run_at=None)
        PeriodicTasks.update_changed()
        self._message_user_about_update(request, rows_updated, "disabled")

    disable_tasks.short_description = _("Disable selected tasks")

    def _toggle_tasks_activity(self, queryset):
        return queryset.update(
            enabled=Case(
                When(enabled=True, then=Value(False)),
                default=Value(True),
            )
        )

    def toggle_tasks(self, request, queryset):
        rows_updated = self._toggle_tasks_activity(queryset)
        PeriodicTasks.update_changed()
        self._message_user_about_update(request, rows_updated, "toggled")

    toggle_tasks.short_description = _("Toggle activity of selected tasks")

    def run_tasks(self, request, queryset):
        self.celery_app.loader.import_default_modules()
        tasks = [
            (
                self.celery_app.tasks.get(task.task),
                loads(task.args),
                loads(task.kwargs),
                task.queue,
                task.name,
            )
            for task in queryset
        ]

        for i, t in enumerate(tasks):
            if t[0] is None:
                self.message_user(
                    request,
                    _('task "{}" not found').format(queryset[i].task),
                    level=messages.ERROR,
                )
                return

        task_ids = [
            task.apply_async(
                args=args,
                kwargs=kwargs,
                queue=queue,
                periodic_task_name=periodic_task_name,
            )
            if queue and len(queue)
            else task.apply_async(
                args=args, kwargs=kwargs, periodic_task_name=periodic_task_name
            )
            for task, args, kwargs, queue, periodic_task_name in tasks
        ]
        tasks_run = len(task_ids)
        self.message_user(
            request,
            _("{0} task{1} {2} successfully run").format(
                tasks_run,
                pluralize(tasks_run),
                pluralize(tasks_run, _("was,were")),
            ),
        )

    run_tasks.short_description = _("Run selected tasks")


class ClockedScheduleAdmin(ModelAdmin):
    menu_icon = "time"
    model = ClockedSchedule
    fields = ("clocked_time",)
    list_display = ("clocked_time",)


class IntervalScheduleAdmin(ModelAdmin):
    menu_icon = "date"
    model = IntervalSchedule


class CrontabScheduleAdmin(ModelAdmin):
    menu_icon = "date"
    model = CrontabSchedule


class SolarScheduleAdmin(ModelAdmin):
    menu_icon = "date"
    model = SolarSchedule


class TasksModelsAdminGroup(ModelAdminGroup):
    menu_name = "celery_wagtail"
    menu_label = _("Tarefas agendadas")
    menu_icon = "time"
    menu_order = get_menu_order("celery_wagtail")
    add_to_admin_menu = False
    add_to_settings_menu = True
    items = (
        PeriodicTaskAdmin,
        CrontabScheduleAdmin,
        IntervalScheduleAdmin,
        ClockedScheduleAdmin,
        SolarScheduleAdmin,
    )


modeladmin_register(TasksModelsAdminGroup)


def task_run(request):
    task_id = int(request.GET.get("task_id", None))
    p_task = get_object_or_404(PeriodicTask, pk=task_id)

    current_app.loader.import_default_modules()

    task = current_app.tasks.get(p_task.task)
    if not task:
        wagtail_messages.error(request, _('Task "{0}" not found').format(p_task.task))
        return redirect(request.META.get("HTTP_REFERER", "/"))

    kwargs = json.loads(p_task.kwargs) if p_task.kwargs else {}

    try:
        sig = inspect.signature(task.run)
        has_user_id_param = "user_id" in sig.parameters
        has_var_keyword = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
    except ValueError, TypeError:
        has_user_id_param = False
        has_var_keyword = False

    if (has_user_id_param or has_var_keyword) and getattr(
        request.user, "id", None
    ) is not None:
        kwargs["user_id"] = request.user.id

    task.apply_async(
        args=json.loads(p_task.args) if p_task.args else [],
        kwargs=kwargs,
        queue=p_task.queue,
        periodic_task_name=p_task.name,
    )

    wagtail_messages.success(
        request, _("Task {0} was successfully run").format(p_task.name)
    )
    return redirect(request.META.get("HTTP_REFERER", "/"))


@hooks.register("register_admin_urls")
def register_celery_task_url():
    return [
        path("celery_wagtail/", task_run, name="celery_task_run"),
    ]
