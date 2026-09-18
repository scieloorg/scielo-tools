WAGTAIL_MENU_GROUPS_ORDER = [
    "manuscript",
    "sps_package_validation",
    "images",
    "documents",
    "celery_wagtail",
]


def get_menu_order(app_name):
    try:
        return WAGTAIL_MENU_GROUPS_ORDER.index(app_name) + 1
    except ValueError:
        return 9000
