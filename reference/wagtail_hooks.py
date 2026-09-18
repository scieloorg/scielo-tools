from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel, InlinePanel, ObjectList
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import CreateView, SnippetViewSet

from reference.create_forms import ReferenceCreateAdminForm
from reference.data_utils import resolve_references_result
from reference.exceptions import (
    ReferenceLlamaDisabledError,
    ReferenceLlamaMisconfiguredError,
    ReferenceLlamaUnavailableError,
)
from reference.models import Reference


class ReferenceCreateView(CreateView):
    def get_panel(self):
        return ObjectList(
            [
                FieldPanel("mixed_citation"),
                FieldPanel("docx_file"),
                InlinePanel("element_citation", label=_("Cited Elements")),
            ],
            base_form_class=ReferenceCreateAdminForm,
        ).bind_to_model(self.model)

    def get_form_class(self):
        return self.panel.get_form_class()

    def form_valid(self, form):
        try:
            results = resolve_references_result(
                form.cleaned_data["mixed_citation"],
                user=self.request.user,
                output_type="json",
            )
        except (
            ReferenceLlamaDisabledError,
            ReferenceLlamaMisconfiguredError,
            ReferenceLlamaUnavailableError,
        ) as exc:
            messages.error(
                self.request,
                _("Llama model is not available: %(error)s") % {"error": str(exc)},
            )
            return self.render_to_response(self.get_context_data(form=form))

        if results:
            messages.success(
                self.request,
                _("Marked %(count)s reference(s).") % {"count": len(results)},
            )

        return HttpResponseRedirect(self.get_success_url())


class ReferenceModelViewSet(SnippetViewSet):
    model = Reference
    add_view_class = ReferenceCreateView
    menu_name = "reference"
    menu_label = _("References")
    menu_icon = "openquote"
    exclude_from_explorer = False
    list_per_page = 20
    add_to_admin_menu = False


register_snippet(ReferenceModelViewSet)
