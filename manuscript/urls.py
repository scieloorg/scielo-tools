from django.urls import path

from manuscript import views

urlpatterns = [
    path("<int:pk>/front/", views.step_front, name="manuscript_step_front"),
    path("<int:pk>/body/", views.step_body, name="manuscript_step_body"),
    path("<int:pk>/back/", views.step_back, name="manuscript_step_back"),
    path("<int:pk>/validate/", views.step_validate, name="manuscript_step_validate"),
    path("<int:pk>/package/", views.step_package, name="manuscript_step_package"),
    path(
        "<int:pk>/preview/<str:part>/",
        views.preview_part,
        name="manuscript_preview_part",
    ),
    path("<int:pk>/api/front/", views.api_save_front, name="manuscript_api_save_front"),
    path("<int:pk>/api/body/", views.api_save_body, name="manuscript_api_save_body"),
    path("<int:pk>/api/back/", views.api_save_back, name="manuscript_api_save_back"),
    path(
        "<int:pk>/api/references/<int:ref_pk>/remark/",
        views.api_remark_reference,
        name="manuscript_api_remark_reference",
    ),
    path("<int:pk>/api/publish/", views.api_publish, name="manuscript_api_publish"),
]
