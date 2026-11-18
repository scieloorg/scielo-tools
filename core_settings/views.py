from django.shortcuts import render
from django.urls import reverse
from wagtail.admin.auth import require_admin_access
from wagtail.documents.permissions import (
    permission_policy as document_permission_policy,
)
from wagtail.images.permissions import permission_policy as image_permission_policy
from wagtail.permission_policies.base import ModelPermissionPolicy

from manuscript.models import Manuscript
from manuscript.services.workflow import current_step_url_name

SEARCH_RESULT_LIMIT = 50
SEARCH_PERMISSIONS = ["add", "change", "delete"]
INSTANCE_PERMISSIONS = {"add", "change", "delete", "choose"}


@require_admin_access
def admin_search(request):
    query = (request.GET.get("q") or "").strip()
    manuscripts = []
    images = []
    documents = []
    show_manuscripts = ModelPermissionPolicy(Manuscript).user_has_any_permission(
        request.user, SEARCH_PERMISSIONS
    )
    show_images = image_permission_policy.user_has_any_permission(
        request.user, SEARCH_PERMISSIONS
    )
    show_documents = document_permission_policy.user_has_any_permission(
        request.user, SEARCH_PERMISSIONS
    )
    if query:
        if show_manuscripts:
            for manuscript in Manuscript.objects.filter(
                title__icontains=query
            ).order_by("title")[:SEARCH_RESULT_LIMIT]:
                manuscripts.append(
                    {
                        "title": manuscript.title,
                        "url": reverse(
                            current_step_url_name(manuscript), args=[manuscript.pk]
                        ),
                        "meta": manuscript.get_status_display(),
                    }
                )
        if show_images:
            for image in (
                image_permission_policy.instances_user_has_any_permission_for(
                    request.user, INSTANCE_PERMISSIONS
                )
                .filter(title__icontains=query)
                .order_by("title")[:SEARCH_RESULT_LIMIT]
            ):
                images.append(
                    {
                        "title": image.title,
                        "url": reverse("wagtailimages:edit", args=[image.pk]),
                    }
                )
        if show_documents:
            for document in (
                document_permission_policy.instances_user_has_any_permission_for(
                    request.user, INSTANCE_PERMISSIONS
                )
                .filter(title__icontains=query)
                .order_by("title")[:SEARCH_RESULT_LIMIT]
            ):
                documents.append(
                    {
                        "title": document.title,
                        "url": reverse("wagtaildocs:edit", args=[document.pk]),
                    }
                )
    return render(
        request,
        "wagtailadmin/search.html",
        {
            "query": query,
            "manuscripts": manuscripts,
            "images": images,
            "documents": documents,
            "show_manuscripts": show_manuscripts,
            "show_images": show_images,
            "show_documents": show_documents,
        },
    )
