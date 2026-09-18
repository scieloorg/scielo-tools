from pathlib import Path

from django.contrib.staticfiles.finders import find
from django.test import SimpleTestCase


class AdminThemeCssTests(SimpleTestCase):
    def test_sidebar_hides_search_form(self):
        css_path = find("core_settings/css/admin-theme.css")
        self.assertIsNotNone(css_path)
        css = Path(css_path).read_text()
        icon_start = css.index(".sidebar-menu-item .icon--menuitem")
        icon_end = css.index('.sidebar form[role="search"]')
        icon_rule = css[icon_start:icon_end]
        self.assertIn("color: var(--scielo-text-emphasis", icon_rule)
        self.assertNotIn("display: none", icon_rule)
        self.assertNotIn(
            ".sidebar:not(.sidebar--slim) .sidebar-menu-item .icon--menuitem",
            css,
        )
        self.assertIn('.sidebar form[role="search"]', css)
        self.assertIn(
            '.w-dashboard form[role="search"] input[type="search"]',
            css,
        )
        self.assertIn(
            '.w-dashboard form[role="search"] .w-field__icon',
            css,
        )
        dashboard_icon = css.split(
            '.w-dashboard form[role="search"] .w-field__icon',
            1,
        )[1]
        self.assertIn("top: 50%", dashboard_icon[:180])
        self.assertIn("translateY(-50%)", dashboard_icon[:180])
        self.assertIn("font-family: var(--scielo-font)", css)
        self.assertIn("font-weight: 500", css)
        self.assertIn("--w-font-sans: var(--scielo-font)", css)
        hover_idx = css.index("a.button:hover")
        self.assertIn("color: var(--scielo-white)", css[hover_idx : hover_idx + 220])
        self.assertIn("--w-color-text-button: var(--scielo-white, #fff)", css)
        self.assertIn(".sidebar-footer--open > ul", css)
        self.assertIn(".sidebar-footer:has(.sidebar-sub-menu-item--open) > ul", css)
        self.assertIn("max-height: 24rem", css)
        shadow_start = css.index(".sidebar-menu-item__link:focus")
        shadow_rule = css[shadow_start : css.index("}", shadow_start) + 1]
        self.assertIn(".sidebar-menu-item__link:hover", shadow_rule)
        self.assertIn(".sidebar-menu-item--active", shadow_rule)
        self.assertIn(".sidebar-sub-menu-item--open > a", shadow_rule)
        self.assertIn("text-shadow: none", shadow_rule)

    def test_tokens_use_noto_sans_like_scielo_br(self):
        css_path = find("css/scielo-tokens.css")
        self.assertIsNotNone(css_path)
        css = Path(css_path).read_text()
        self.assertIn('"Noto Sans"', css)
        self.assertIn("fonts.googleapis.com/css2?family=Noto+Sans", css)
        self.assertNotIn("Helvetica Neue", css)

    def test_ds_link_hover_does_not_recolor_wagtail_buttons(self):
        css_path = find("css/scielo-ds-components.css")
        self.assertIsNotNone(css_path)
        css = Path(css_path).read_text()
        self.assertIn(".scielo-ds a:not(.button):hover", css)
        self.assertNotIn(".scielo-ds a:hover {", css)
