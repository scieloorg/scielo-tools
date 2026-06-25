from __future__ import annotations

import platform

from spsvalidator import build_info


def get_footer_build_label(language: str, translations: dict[str, str]) -> str:
    if (
        build_info.BUILD_MACOS_VERSION != "development"
        and build_info.BUILD_PLATFORM == "macOS"
    ):
        return translations["footer_built_for_macos"].format(
            version=build_info.BUILD_MACOS_VERSION
        )
    runtime_platform = platform.system()
    if runtime_platform == "Darwin":
        mac_version = platform.mac_ver()[0]
        build_number = platform.mac_ver()[2]
        version_label = mac_version
        if build_number:
            version_label = f"{mac_version} ({build_number})"
        return translations["footer_built_for_macos"].format(version=version_label)
    return translations["footer_dev_build"].format(platform=runtime_platform)
