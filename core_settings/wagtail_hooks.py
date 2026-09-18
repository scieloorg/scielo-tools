from django.templatetags.static import static
from django.urls import path, reverse
from django.utils.html import format_html, json_script
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.menu import MenuItem, admin_menu
from wagtail.admin.search import SearchArea, admin_search_areas
from wagtail.admin.site_summary import PagesSummaryItem
from wagtail.admin.telepath import JSContext
from wagtail.admin.templatetags.wagtailadmin_tags import (
    register as wagtailadmin_register,
)
from wagtail.admin.ui import sidebar

from config.menu import WAGTAIL_MENU_GROUPS_ORDER, get_menu_order
from core_settings.views import admin_search

ACCOUNT_EXTRA_MENU_NAMES = frozenset({"reports", "settings", "help"})
HIDDEN_MAIN_MENU_NAMES = frozenset({"explorer", "snippets", "reference"})
SCIELO_SEARCH_AREA_NAME = "scielo-search"


@hooks.register("insert_global_admin_css")
def scielo_admin_theme_css():
    tokens = static("css/scielo-tokens.css")
    theme = static("core_settings/css/admin-theme.css")
    components = static("css/scielo-ds-components.css")
    return format_html(
        '<link rel="stylesheet" href="{}">'
        '<link rel="stylesheet" href="{}">'
        '<link rel="stylesheet" href="{}">',
        tokens,
        theme,
        components,
    )


@hooks.register("register_admin_urls")
def register_scielo_admin_search_urls():
    return [
        path("search/", admin_search, name="scielo_admin_search"),
    ]


@hooks.register("register_admin_search_area")
def register_scielo_search_area():
    return SearchArea(
        _("Buscar"),
        reverse("scielo_admin_search"),
        name=SCIELO_SEARCH_AREA_NAME,
        icon_name="search",
        order=0,
    )


@hooks.register("construct_search")
def restrict_admin_search_areas(request, search_areas):
    search_areas[:] = [
        area for area in search_areas if area.name == SCIELO_SEARCH_AREA_NAME
    ]


@hooks.register("register_admin_menu_item")
def register_search_home_menu_item():
    return MenuItem(
        _("Buscar"),
        reverse("wagtailadmin_home"),
        name="search-home",
        icon_name="search",
        order=0,
    )


@hooks.register("construct_homepage_summary_items", order=100)
def hide_pages_summary_item(request, items):
    items[:] = [item for item in items if not isinstance(item, PagesSummaryItem)]


@hooks.register("construct_main_menu")
def hide_pages_menu_item(request, menu_items):
    extra = []
    kept = []
    for item in menu_items:
        if item.name in HIDDEN_MAIN_MENU_NAMES:
            continue
        if item.name in WAGTAIL_MENU_GROUPS_ORDER:
            item.order = get_menu_order(item.name)
        if item.name in ACCOUNT_EXTRA_MENU_NAMES:
            extra.append(item)
            continue
        kept.append(item)
    extra.sort(key=lambda item: item.order)
    request._scielo_account_extra_menu_items = extra
    menu_items[:] = kept


@wagtailadmin_register.simple_tag(takes_context=True)
def sidebar_props(context):
    request = context["request"]
    search_areas = admin_search_areas.search_items_for_request(request)
    for fn in hooks.get_hooks("construct_search"):
        fn(request, search_areas)
    search_area = search_areas[0] if search_areas else None
    main_menu = admin_menu.render_component(request)
    account_menu = [
        sidebar.LinkMenuItem(
            "account",
            _("Account"),
            reverse("wagtailadmin_account"),
            icon_name="user",
        )
    ]
    for item in getattr(request, "_scielo_account_extra_menu_items", []):
        account_menu.append(item.render_component(request))
    account_menu.append(
        sidebar.ActionMenuItem(
            "logout",
            _("Log out"),
            reverse("wagtailadmin_logout"),
            icon_name="logout",
        )
    )
    modules = [
        sidebar.WagtailBrandingModule(),
        sidebar.SearchModule(search_area) if search_area else None,
        sidebar.MainMenuModule(main_menu, account_menu, request.user),
    ]
    modules = [module for module in modules if module is not None]
    return json_script(
        {"modules": JSContext().pack(modules)},
        element_id="wagtail-sidebar-props",
    )
