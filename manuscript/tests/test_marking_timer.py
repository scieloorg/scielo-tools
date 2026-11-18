from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from manuscript.models import Manuscript, ManuscriptStatus


class FrontMarkingStatusUiTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(user)
        self.manuscript = Manuscript.objects.create(
            title="bn-2025-1834",
            status=ManuscriptStatus.FRONT,
            creator=user,
        )

    def test_front_step_includes_marking_status_ui(self):
        response = self.client.get(
            reverse("manuscript_step_front", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-marking-part="front"')
        self.assertContains(response, "manuscript-wizard__step-meter")
        self.assertContains(response, "manuscript-wizard__step-btn")
        self.assertContains(response, "manuscript-wizard__action-btn")
        self.assertContains(response, "manuscript-wizard__step-percent")
        self.assertContains(response, "manuscript-marking-state")
        self.assertContains(response, "/api/marking-status/")
        self.assertContains(response, 'value="mark"')
        self.assertContains(response, "Mark front")
        self.assertContains(response, "manuscript/js/wizard.js")
        self.assertNotContains(response, "manuscript-marking-overlay")

    def test_wizard_js_polls_marking_status(self):
        source = Path("manuscript/static/manuscript/js/wizard.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("function bindManuscriptMarkingStatus()", source)
        self.assertIn("function applyManuscriptMarkingState(state)", source)
        self.assertIn(
            "function applyManuscriptMeter(host, meter, info, active)", source
        )
        self.assertIn('classList.add("is-complete")', source)
        self.assertIn("manuscript-wizard__step-percent", source)
        self.assertIn("clipPath", source)
        self.assertIn("fetch(", source)
        self.assertIn("window.location.reload()", source)
        self.assertNotIn("bindManuscriptMarkingOverlay", source)
        self.assertNotIn("requestSubmit", source)

    def test_front_editor_shows_section_counts_in_labels(self):
        source = Path("manuscript/static/manuscript/js/front-editor.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("function countedLabelText(key, fallback, count)", source)
        self.assertIn('createFrontCollapse("authorsLabel")', source)
        self.assertIn('createFrontCollapse("abstractsLabel")', source)
        self.assertIn('createFrontCollapse("keywordsLabel")', source)
        self.assertIn("updateAuthorsLabel(authorsWrap)", source)
        self.assertIn("updateAbstractsLabel(abstractsWrap)", source)
        self.assertIn("updateKeywordsLabel(keywordsWrap)", source)
        self.assertIn("function keywordItemCount(list)", source)
        self.assertIn('createFrontCollapse("historyLabel")', source)
        self.assertIn('createFrontCollapse("countsLabel")', source)
        self.assertIn("function createHistoryRow(item)", source)
        self.assertIn("updateHistoryLabel(historyWrap)", source)
        self.assertIn('data-field="fig_count"', source)
        self.assertIn("data.history", source)
        self.assertIn("data.counts = counts", source)

    def test_front_editor_collapses_authors_abstracts_and_keywords(self):
        source = Path("manuscript/static/manuscript/js/front-editor.js").read_text(
            encoding="utf-8"
        )
        css = Path("manuscript/static/manuscript/css/wizard.css").read_text(
            encoding="utf-8"
        )
        self.assertIn('createElement("details")', source)
        self.assertIn('createElement("summary")', source)
        self.assertIn("wrap.open = false", source)
        self.assertIn('wrap.dataset.frontCollapse = "1"', source)
        self.assertIn("accordion-item", source)
        self.assertIn("accordion-body", source)
        self.assertIn(
            ".manuscript-wysiwyg details.accordion-item > summary::before", css
        )

    def test_body_editor_shows_paragraph_count_in_label(self):
        source = Path("manuscript/static/manuscript/js/body-editor.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("function countedLabelText(key, fallback, count)", source)
        self.assertIn('createBodyCollapse("paragraphsLabel")', source)
        self.assertIn("updateParagraphsLabel(paragraphsWrap)", source)

    def test_body_editor_collapses_paragraphs(self):
        source = Path("manuscript/static/manuscript/js/body-editor.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('createElement("details")', source)
        self.assertIn('createElement("summary")', source)
        self.assertIn("wrap.open = false", source)
        self.assertIn('wrap.dataset.bodyCollapse = "1"', source)
        self.assertIn("accordion-item", source)
        self.assertIn("accordion-body", source)

    def test_back_editor_shows_reference_count_in_label(self):
        source = Path("manuscript/static/manuscript/js/back-editor.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("function countedLabelText(key, fallback, count)", source)
        self.assertIn('createBackCollapse("referencesLabel")', source)
        self.assertIn("updateReferencesLabel(referencesWrap)", source)

    def test_back_editor_collapses_references_and_structured_marked(self):
        source = Path("manuscript/static/manuscript/js/back-editor.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('createElement("details")', source)
        self.assertIn('createElement("summary")', source)
        self.assertIn("wrap.open = false", source)
        self.assertIn('wrap.dataset.backCollapse = "1"', source)
        self.assertIn("accordion-item", source)
        self.assertIn("accordion-body", source)
        self.assertIn("structuredMarkedJson", source)

    def test_wizard_css_has_running_meter(self):
        css = Path("manuscript/static/manuscript/css/wizard.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".manuscript-wizard__steps .nav-link", css)
        self.assertNotIn(".nav-pills .manuscript-wizard__steps .nav-link", css)
        self.assertIn(".manuscript-wizard__step-meter", css)
        self.assertIn(".manuscript-wizard__step-btn", css)
        self.assertIn(".manuscript-wizard__action-btn", css)
        self.assertIn(".manuscript-wizard__step-percent", css)
        self.assertIn(".is-running", css)
        self.assertIn(".is-error", css)
        self.assertIn("inset: 0", css)
        self.assertIn("var(--scielo-white, #fff)", css)
        self.assertIn("var(--scielo-black, #000)", css)
        self.assertIn("var(--scielo-text-subtle, #6c6b6b)", css)
        self.assertIn("var(--scielo-positive, #2c9d45)", css)
        self.assertIn("var(--scielo-danger, #dc3545)", css)
        self.assertNotIn("min-width: 5.75rem", css)
        self.assertNotIn(".manuscript-marking-overlay", css)
