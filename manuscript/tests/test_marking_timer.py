from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from manuscript.models import Manuscript, ManuscriptStatus


class FrontMarkingTimerTests(TestCase):
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

    def test_front_step_includes_marking_timer_overlay(self):
        response = self.client.get(
            reverse("manuscript_step_front", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="manuscript-marking-overlay"')
        self.assertContains(response, 'id="manuscript-marking-timer"')
        self.assertContains(response, "Elapsed time")
        self.assertContains(response, 'value="mark"')
        self.assertContains(response, "Mark front")
        self.assertContains(response, "manuscript/js/wizard.js")
        self.assertContains(response, "markingFront")

    def test_marking_overlay_lets_native_submit_proceed(self):
        source = Path("manuscript/static/manuscript/js/wizard.js").read_text(
            encoding="utf-8"
        )
        overlay = source.split("function bindManuscriptMarkingOverlay()", 1)[1]
        self.assertNotIn("fetch(", overlay)
        self.assertNotIn("window.location.assign", overlay)
        self.assertIn("requestAnimationFrame", overlay)
        self.assertIn("requestSubmit", overlay)
        self.assertIn("allowNative", overlay)
        self.assertIn("event.preventDefault()", overlay)

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
