import io
import os
import re
import zipfile

from PIL import Image

from body.exceptions import BodyImageError
from body.utils import (
    FIG_MENTION_RE,
    float_number,
    insert_float_after_mention,
    iter_content_lists,
)

FIG_FILE_RE = re.compile(r"^fig-(\d+)\.(tif|tiff|jpg|jpeg)$", re.IGNORECASE)
ANY_IMAGE_EXT_RE = re.compile(r"^.+?\.(tif|tiff|jpg|jpeg|png)$", re.IGNORECASE)
FIG_IDENTIFIER_RE = re.compile(
    r"^(?:fig(?:ure|ura)?[-_\s]*)?(\d+)(?:\.(?:tif|tiff|jpg|jpeg|png))?$",
    re.IGNORECASE,
)
TIFF_EXTS = {"tif", "tiff"}
CONVERT_TO_JPEG_EXTS = {"tif", "tiff", "png"}


def parse_figure_filename(name):
    basename = os.path.basename(str(name or "").replace("\\", "/"))
    match = FIG_FILE_RE.match(basename)
    if not match:
        return None
    return str(int(match.group(1))), match.group(2).lower()


def parse_image_extension(name):
    basename = os.path.basename(str(name or "").replace("\\", "/"))
    match = ANY_IMAGE_EXT_RE.match(basename)
    if not match:
        return None
    return match.group(1).lower()


def normalize_figure_identifier(value):
    text = os.path.basename(str(value or "").strip().replace("\\", "/"))
    match = FIG_IDENTIFIER_RE.match(text)
    if not match:
        raise BodyImageError(f"Invalid figure identifier: {value}")
    number = int(match.group(1))
    if number < 1:
        raise BodyImageError(f"Invalid figure identifier: {value}")
    return number, f"fig-{number}.jpg"


def figure_jpeg_bytes(name, data, ext):
    if not data:
        raise BodyImageError(f"Empty image file: {os.path.basename(name)}")
    if ext not in CONVERT_TO_JPEG_EXTS:
        return data
    try:
        image = Image.open(io.BytesIO(data))
        image.seek(0)
        converted = io.BytesIO()
        image.convert("RGB").save(converted, format="JPEG")
        jpeg = converted.getvalue()
        if not jpeg:
            raise BodyImageError(f"Could not convert {os.path.basename(name)} to JPEG.")
        return jpeg
    except BodyImageError:
        raise
    except Exception as exc:
        raise BodyImageError(
            f"Could not convert {os.path.basename(name)} to JPEG."
        ) from exc


def collect_image_assets(
    images=None,
    images_zip=None,
    allow_any_filename=False,
    reserved_numbers=None,
):
    assets = {}
    used_numbers = {int(n) for n in (reserved_numbers or []) if str(n).isdigit()}
    next_number = 1
    for uploaded in images or []:
        name = getattr(uploaded, "name", "") or ""
        parsed = parse_figure_filename(name)
        if parsed is None:
            if not allow_any_filename:
                raise BodyImageError(
                    f"Invalid image filename: {os.path.basename(name)}"
                )
            ext = parse_image_extension(name)
            if ext is None:
                raise BodyImageError(
                    f"Invalid image filename: {os.path.basename(name)}"
                )
            basename_stem = os.path.splitext(
                os.path.basename(str(name).replace("\\", "/"))
            )[0]
            stem_match = FIG_IDENTIFIER_RE.match(basename_stem)
            if (
                stem_match
                and int(stem_match.group(1)) >= 1
                and int(stem_match.group(1)) not in used_numbers
                and str(int(stem_match.group(1))) not in assets
            ):
                number = str(int(stem_match.group(1)))
            else:
                while next_number in used_numbers or str(next_number) in assets:
                    next_number += 1
                number = str(next_number)
                next_number += 1
        else:
            number, ext = parsed
            if number in assets:
                if not allow_any_filename:
                    raise BodyImageError(f"Duplicate figure number: {number}")
                while next_number in used_numbers or str(next_number) in assets:
                    next_number += 1
                number = str(next_number)
                next_number += 1
        used_numbers.add(int(number))
        data = uploaded.read()
        if hasattr(uploaded, "seek"):
            uploaded.seek(0)
        jpeg = figure_jpeg_bytes(name, data, ext)
        assets[number] = {
            "href": f"fig-{number}.jpg",
            "bytes": jpeg,
            "original_name": os.path.basename(str(name).replace("\\", "/")),
        }
    if not images_zip:
        return assets
    zip_bytes = images_zip.read()
    if hasattr(images_zip, "seek"):
        images_zip.seek(0)
    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise BodyImageError("Invalid zip file.") from exc
    for info in archive.infolist():
        if info.is_dir():
            continue
        parsed = parse_figure_filename(info.filename)
        if parsed is None:
            if not allow_any_filename:
                continue
            ext = parse_image_extension(info.filename)
            if ext is None:
                continue
            basename_stem = os.path.splitext(
                os.path.basename(info.filename.replace("\\", "/"))
            )[0]
            stem_match = FIG_IDENTIFIER_RE.match(basename_stem)
            if (
                stem_match
                and int(stem_match.group(1)) >= 1
                and int(stem_match.group(1)) not in used_numbers
                and str(int(stem_match.group(1))) not in assets
            ):
                number = str(int(stem_match.group(1)))
            else:
                while next_number in used_numbers or str(next_number) in assets:
                    next_number += 1
                number = str(next_number)
                next_number += 1
        else:
            number, ext = parsed
            if number in assets:
                if not allow_any_filename:
                    raise BodyImageError(f"Duplicate figure number: {number}")
                while next_number in used_numbers or str(next_number) in assets:
                    next_number += 1
                number = str(next_number)
                next_number += 1
        used_numbers.add(int(number))
        data = archive.read(info)
        jpeg = figure_jpeg_bytes(info.filename, data, ext)
        assets[number] = {
            "href": f"fig-{number}.jpg",
            "bytes": jpeg,
            "original_name": os.path.basename(info.filename.replace("\\", "/")),
        }
    return assets


def collect_image_hrefs(images=None, images_zip=None):
    assets = collect_image_assets(images, images_zip)
    return {number: asset["href"] for number, asset in assets.items()}


def attach_figure_hrefs(marked, hrefs):
    data = marked if isinstance(marked, dict) else {}
    mapping = {
        str(number): href
        for number, href in (hrefs or {}).items()
        if str(href or "").strip()
    }
    if not mapping:
        return data
    sections = data.get("sections") or []
    seen = set()
    for section in sections:
        for content in iter_content_lists(section):
            for block in content:
                if not isinstance(block, dict):
                    continue
                figs = []
                if block.get("type") == "fig":
                    figs = [block]
                elif block.get("type") == "fig-group":
                    figs = [
                        item
                        for item in (block.get("figs") or [])
                        if isinstance(item, dict)
                    ]
                for fig in figs:
                    number = float_number(fig)
                    if number in mapping:
                        fig["href"] = mapping[number]
                        seen.add(number)
    missing = [number for number in mapping if number not in seen]
    if missing and sections:
        missing.sort(key=lambda number: int(number) if number.isdigit() else 0)
        for number in missing:
            insert_float_after_mention(
                sections,
                {
                    "type": "fig",
                    "id": f"f{number}",
                    "label": f"Figure {number}",
                    "caption": "",
                    "href": mapping[number],
                },
                FIG_MENTION_RE,
                number,
            )
    return data
