"""
assets.py — helper functions for catalog, rule persistence, and cloud-backed image storage.
"""

import json
import os
import re
import time
from pathlib import Path

import streamlit as st

import config
import storage

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _ensure_local_assets_dir() -> None:
    os.makedirs(config.BRAND_ASSETS_DIR, exist_ok=True)


def _slug(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "unnamed"


def _normalize_filename(name: str) -> str:
    name = Path(name).stem
    return f"{_slug(name)}"


def _file_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return ext if ext in _IMAGE_EXTENSIONS else ".png"


def _mime_type(ext: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")


def _sku_image_basename(sku: str, variant: str | None = None) -> str:
    slug = _slug(sku)
    if variant:
        return f"{slug}__{_slug(variant)}"
    return slug


def _migrate_catalog(catalog: dict) -> tuple[dict, bool]:
    migrated = False
    if not isinstance(catalog, dict):
        catalog = {}
        migrated = True

    for category, value in list(catalog.items()):
        if isinstance(value, list):
            catalog[category] = {
                sku: {"variants": []}
                for sku in value
            }
            migrated = True
        elif isinstance(value, dict):
            if set(value.keys()) == {"variants"} and isinstance(value.get("variants"), list):
                catalog[category] = {}
                migrated = True
            else:
                for sku, sku_value in list(value.items()):
                    if isinstance(sku_value, list):
                        catalog[category][sku] = {"variants": sku_value}
                        migrated = True
                    elif isinstance(sku_value, dict):
                        catalog[category][sku] = {
                            "variants": sku_value.get("variants", [])
                        }
                    else:
                        catalog[category][sku] = {"variants": []}
                        migrated = True
        else:
            catalog[category] = {}
            migrated = True

    # One-time content migration: "Coconut Barfi" used to live under the old
    # "Indian Sweets" default. Move it (and its variants) to "DESi Meetha" so
    # the product and its uploaded image — keyed by product slug in GCS, not by
    # category — are preserved. The image resolves unchanged after the move.
    legacy_sweets = "Indian Sweets"
    meetha = "DESi Meetha"
    barfi = "Coconut Barfi"
    if legacy_sweets in catalog and barfi in catalog.get(legacy_sweets, {}):
        catalog.setdefault(meetha, {})
        if barfi not in catalog[meetha]:
            catalog[meetha][barfi] = catalog[legacy_sweets][barfi]
        del catalog[legacy_sweets][barfi]
        migrated = True

    # Ensure the current default categories exist (adds any that are missing,
    # in defined order). Existing categories/products are never touched.
    for category in config.DEFAULT_CATEGORIES:
        if category not in catalog:
            catalog[category] = {}
            migrated = True

    # Clean up empty leftovers from the old default set. Categories that still
    # hold products are kept regardless.
    for category in config.LEGACY_DEFAULT_CATEGORIES:
        if category in catalog and not catalog[category]:
            del catalog[category]
            migrated = True

    return catalog, migrated


@st.cache_data(show_spinner=False)
def load_catalog() -> dict:
    if os.path.exists(config.CATALOG_FILE):
        with open(config.CATALOG_FILE, "r", encoding="utf-8") as f:
            catalog = json.load(f)
    else:
        catalog = {}

    catalog, migrated = _migrate_catalog(catalog)
    if migrated:
        save_catalog(catalog)
    return catalog


def save_catalog(catalog: dict) -> None:
    _ensure_local_assets_dir()
    with open(config.CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    load_catalog.clear()


# ---------------------------------------------------------------------------
# Brand rules — one editable free-text block (replaces the old separate
# Copywriter + Designer structured rules). Saved locally, fed into the brief.
# ---------------------------------------------------------------------------
_BRAND_RULES_TEXT_FILE = "brand_rules_combined.md"

# Migrated default: the previous Copywriter + Designer content folded into one
# block. Shown until the team saves their own.
_DEFAULT_BRAND_RULES_TEXT = (
    "Brand tone: Fun, Quirky, Playful. Feel / keywords: Nostalgic, Candy, Lollipop.\n"
    "Language style: English.\n"
    "Exact CTA button text: Order Now.\n\n"
    "Approved example headlines (guide to tone — do not copy verbatim):\n"
    "- Besan Laddu with Pure Cow Ghee\n"
    "- Creamy Peda made with Pure Milk\n"
    "- Many Names, One OG Bengaluru Snack\n"
    "- Add DESi Crunch to Your Tea Time\n"
    "- Kaccha Aam Popz with a Sour Kick\n\n"
    "Words / claims to never use: none specified yet.\n\n"
    "Logo colour: #FF8700 (Taste-Burst Orange).\n"
    "Product placement: centred (for vertical banners).\n"
    "Target audience: 25-40.\n"
    "Never use AI-generated children; if people are used, keep them within the 25-40 audience."
)


def _brand_rules_text_path() -> str:
    return os.path.join(config.BRAND_ASSETS_DIR, _BRAND_RULES_TEXT_FILE)


def load_brand_rules_text() -> str:
    path = _brand_rules_text_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return _DEFAULT_BRAND_RULES_TEXT
    return _DEFAULT_BRAND_RULES_TEXT


def save_brand_rules_text(text: str) -> None:
    _ensure_local_assets_dir()
    with open(_brand_rules_text_path(), "w", encoding="utf-8") as f:
        f.write(text.strip() + "\n")


# ---------------------------------------------------------------------------
# Reference banners (good on-brand examples, organised by category)
#
# GCS layout:
#   references/<category-slug>/<image>      one subfolder per catalog category
#   references/notes.json                   {"<category-slug>/<image>": "note"}
# Any legacy images sitting directly in references/ (no subfolder) are still
# picked up by the cross-category fallback.
# ---------------------------------------------------------------------------
_REFERENCE_NOTES_FILE = "notes.json"


def reference_folder(category: str) -> str:
    """GCS folder for a category's reference banners, e.g. references/desi_meetha."""
    return f"references/{_slug(category)}"


def _reference_relpath(category: str, filename: str) -> str:
    """Key used in notes.json: '<category-slug>/<filename>'."""
    return f"{_slug(category)}/{filename}"


def list_reference_images(category: str) -> list[str]:
    """Filenames (basenames) of reference banners in one category."""
    return sorted(storage.list_images(reference_folder(category)))


def _all_reference_relpaths() -> list[str]:
    """Image relative paths under references/, across every category."""
    out = []
    for relpath in storage.list_images("references"):
        base = Path(relpath).name
        if base == _REFERENCE_NOTES_FILE:
            continue
        if Path(base).suffix.lower() not in _IMAGE_EXTENSIONS:
            continue
        out.append(relpath)
    return sorted(out)


def _load_reference_by_relpath(relpath: str) -> bytes | None:
    parts = relpath.split("/")
    if len(parts) == 1:  # legacy image stored directly in references/
        return storage.get_image("references", parts[0])
    folder = "references/" + "/".join(parts[:-1])
    return storage.get_image(folder, parts[-1])


@st.cache_data(show_spinner=False)
def load_reference_images(category: str | None = None) -> list[bytes]:
    """Reference images to feed the model.

    If a category is given and it has its own references, use only those.
    Otherwise fall back to ALL reference banners across categories.
    """
    images = []
    if category:
        for name in list_reference_images(category):
            data = storage.get_image(reference_folder(category), name)
            if data:
                images.append(data)
        if images:
            return images

    for relpath in _all_reference_relpaths():
        data = _load_reference_by_relpath(relpath)
        if data:
            images.append(data)
    return images


@st.cache_data(show_spinner=False)
def load_reference_images_named(category: str | None = None) -> list[tuple[str, bytes]]:
    """Same selection logic as load_reference_images, but each item is paired
    with a human label of its source (for the debug panel)."""
    out = []
    if category:
        for name in list_reference_images(category):
            data = storage.get_image(reference_folder(category), name)
            if data:
                out.append((f"{category}: {name}", data))
        if out:
            return out

    for relpath in _all_reference_relpaths():
        data = _load_reference_by_relpath(relpath)
        if data:
            out.append((relpath, data))
    return out


def upload_reference_image(category: str, filename: str, data: bytes) -> None:
    ext = _file_extension(filename)
    storage.upload_image(
        reference_folder(category),
        _normalize_filename(filename) + ext,
        data,
        content_type=_mime_type(ext),
    )
    load_reference_images.clear()


def delete_reference_image(category: str, filename: str) -> bool:
    deleted = storage.delete_image(reference_folder(category), filename)
    if deleted:
        notes = load_reference_notes()
        if notes.pop(_reference_relpath(category, filename), None) is not None:
            save_reference_notes(notes)
    load_reference_images.clear()
    return deleted


def load_reference_notes() -> dict:
    data = storage.get_image("references", _REFERENCE_NOTES_FILE)
    if not data:
        return {}
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return {}


def save_reference_notes(notes: dict) -> None:
    payload = json.dumps(notes, indent=2, ensure_ascii=False).encode("utf-8")
    storage.upload_image(
        "references",
        _REFERENCE_NOTES_FILE,
        payload,
        content_type="application/json",
    )


def get_reference_note(category: str, filename: str) -> str:
    return load_reference_notes().get(_reference_relpath(category, filename), "")


def set_reference_note(category: str, filename: str, note: str) -> None:
    notes = load_reference_notes()
    key = _reference_relpath(category, filename)
    if note.strip():
        notes[key] = note.strip()
    else:
        notes.pop(key, None)
    save_reference_notes(notes)


# ---------------------------------------------------------------------------
# Brand logo (single, replaceable official logo + placement/usage notes)
#
# GCS layout:
#   brand/logo.png      the official logo (any uploaded format, kept as-is)
#   brand/logo_notes.txt   free-text logo rules (placement, clear space, etc.)
# ---------------------------------------------------------------------------
_LOGO_FILE = "logo.png"
_LOGO_NOTES_FILE = "logo_notes.txt"

# Shown until the team saves their own logo notes.
_DEFAULT_LOGO_NOTES = (
    "Place the GO DESi logo mark cleanly, with no added circle, disc, or shape "
    "behind it. Reproduce the logo mark exactly as provided; never recolour or "
    "alter it. The logo mark (the wordmark letters and the starburst) keeps its "
    "exact original colours, starburst orange #FF8700. When the logo is used, "
    "prefer the top with clear space around it, at a consistent size "
    "(PLACEHOLDER: exact size pending from Priyanka) — but only if it doesn't "
    "crowd the design."
)


@st.cache_data(show_spinner=False)
def load_logo() -> bytes | None:
    return storage.get_image("brand", _LOGO_FILE)


def upload_logo(data: bytes) -> None:
    # Stored under a fixed name so a new upload simply replaces the old logo.
    storage.upload_image("brand", _LOGO_FILE, data, content_type="image/png")
    load_logo.clear()


def delete_logo() -> bool:
    deleted = storage.delete_image("brand", _LOGO_FILE)
    load_logo.clear()
    return deleted


@st.cache_data(show_spinner=False)
def load_logo_notes() -> str:
    data = storage.get_image("brand", _LOGO_NOTES_FILE)
    if not data:
        return _DEFAULT_LOGO_NOTES
    try:
        return data.decode("utf-8")
    except Exception:
        return _DEFAULT_LOGO_NOTES


def save_logo_notes(notes: str) -> None:
    storage.upload_image(
        "brand",
        _LOGO_NOTES_FILE,
        notes.strip().encode("utf-8"),
        content_type="text/plain",
    )
    load_logo_notes.clear()


# ---------------------------------------------------------------------------
# Platforms (q-commerce slots; each has a fixed Order Now button + rules)
#
# GCS layout:
#   platforms/registry.json                          extra platform names added in-app
#   platforms/<platform-slug>/order_now_button.png   the fixed button image
#   platforms/<platform-slug>/notes.txt              button placement/usage rules
# ---------------------------------------------------------------------------
_PLATFORM_REGISTRY_FILE = "registry.json"
_PLATFORM_BUTTON_FILE = "order_now_button.png"
_PLATFORM_NOTES_FILE = "notes.txt"
_PLATFORM_NO_BUTTON_FILE = "no_button.txt"

# Default button rules per platform slug (shown until the team saves their own).
_DEFAULT_PLATFORM_NOTES = {
    "blinkit": (
        "PLACEHOLDER: Blinkit-specific design rules pending from Priyanka/Arpita. "
        "Use the official Blinkit Order Now button exactly once uploaded."
    ),
}


def platform_folder(platform: str) -> str:
    """GCS folder for one platform's assets, e.g. platforms/blinkit."""
    return f"platforms/{_slug(platform)}"


@st.cache_data(show_spinner=False)
def load_platforms() -> list[str]:
    """Platform names: config defaults first, then any added in-app."""
    names = list(config.DEFAULT_PLATFORMS)
    data = storage.get_image("platforms", _PLATFORM_REGISTRY_FILE)
    if data:
        try:
            stored = json.loads(data.decode("utf-8"))
        except Exception:
            stored = []
        if isinstance(stored, list):
            for name in stored:
                if isinstance(name, str) and name.strip() and name not in names:
                    names.append(name)
    return names


def add_platform(name: str) -> bool:
    """Add a new platform name. Returns False if blank or already present."""
    name = name.strip()
    if not name or name in load_platforms():
        return False
    data = storage.get_image("platforms", _PLATFORM_REGISTRY_FILE)
    try:
        stored = json.loads(data.decode("utf-8")) if data else []
    except Exception:
        stored = []
    if not isinstance(stored, list):
        stored = []
    stored.append(name)
    storage.upload_image(
        "platforms",
        _PLATFORM_REGISTRY_FILE,
        json.dumps(stored, indent=2, ensure_ascii=False).encode("utf-8"),
        content_type="application/json",
    )
    load_platforms.clear()
    return True


def delete_platform(name: str) -> bool:
    """Remove a user-added platform: drop it from the registry and delete its
    GCS assets (button + notes). Default platforms from config cannot be
    deleted (they are always re-listed). Returns True if removed."""
    name = name.strip()
    if not name or name in config.DEFAULT_PLATFORMS:
        return False
    data = storage.get_image("platforms", _PLATFORM_REGISTRY_FILE)
    try:
        stored = json.loads(data.decode("utf-8")) if data else []
    except Exception:
        stored = []
    if not isinstance(stored, list) or name not in stored:
        return False
    stored = [n for n in stored if n != name]
    storage.upload_image(
        "platforms",
        _PLATFORM_REGISTRY_FILE,
        json.dumps(stored, indent=2, ensure_ascii=False).encode("utf-8"),
        content_type="application/json",
    )
    storage.delete_image(platform_folder(name), _PLATFORM_BUTTON_FILE)
    storage.delete_image(platform_folder(name), _PLATFORM_NOTES_FILE)
    storage.delete_image(platform_folder(name), _PLATFORM_NO_BUTTON_FILE)
    load_platforms.clear()
    load_platform_button.clear()
    load_platform_notes.clear()
    load_platform_no_button.clear()
    return True


def platform_fixed_size(platform: str) -> tuple | None:
    """Fixed generation size for a platform as (label, (w, h)), or None if the
    platform uses the manual Banner size selector."""
    return config.PLATFORM_FIXED_SIZE.get(platform)


@st.cache_data(show_spinner=False)
def load_platform_no_button(platform: str) -> bool:
    """Whether this platform must NOT bake in an Order Now button. Defaults to
    the config NO_BUTTON_PLATFORMS list until the team overrides it in-app."""
    data = storage.get_image(platform_folder(platform), _PLATFORM_NO_BUTTON_FILE)
    if data is None:
        return platform in config.NO_BUTTON_PLATFORMS
    return data.decode("utf-8").strip() == "1"


def save_platform_no_button(platform: str, no_button: bool) -> None:
    storage.upload_image(
        platform_folder(platform),
        _PLATFORM_NO_BUTTON_FILE,
        b"1" if no_button else b"0",
        content_type="text/plain",
    )
    load_platform_no_button.clear()


@st.cache_data(show_spinner=False)
def load_platform_button(platform: str) -> bytes | None:
    return storage.get_image(platform_folder(platform), _PLATFORM_BUTTON_FILE)


def upload_platform_button(platform: str, data: bytes) -> None:
    # Fixed filename so a new upload simply replaces the old button.
    storage.upload_image(
        platform_folder(platform),
        _PLATFORM_BUTTON_FILE,
        data,
        content_type="image/png",
    )
    load_platform_button.clear()


def delete_platform_button(platform: str) -> bool:
    deleted = storage.delete_image(platform_folder(platform), _PLATFORM_BUTTON_FILE)
    load_platform_button.clear()
    return deleted


@st.cache_data(show_spinner=False)
def load_platform_notes(platform: str) -> str:
    default = _DEFAULT_PLATFORM_NOTES.get(_slug(platform), "")
    data = storage.get_image(platform_folder(platform), _PLATFORM_NOTES_FILE)
    if not data:
        return default
    try:
        return data.decode("utf-8")
    except Exception:
        return default


def save_platform_notes(platform: str, notes: str) -> None:
    storage.upload_image(
        platform_folder(platform),
        _PLATFORM_NOTES_FILE,
        notes.strip().encode("utf-8"),
        content_type="text/plain",
    )
    load_platform_notes.clear()


@st.cache_data(show_spinner=False)
def load_design_elements() -> list[bytes]:
    names = storage.list_images("design_elements")
    images = []
    for name in sorted(names):
        data = storage.get_image("design_elements", name)
        if data:
            images.append(data)
    return images


@st.cache_data(show_spinner=False)
def load_design_elements_named() -> list[tuple[str, bytes]]:
    """(filename, bytes) pairs — used by the debug panel to label each image."""
    out = []
    for name in sorted(storage.list_images("design_elements")):
        data = storage.get_image("design_elements", name)
        if data:
            out.append((name, data))
    return out


def list_design_elements() -> list[str]:
    return storage.list_images("design_elements")


def upload_design_element(filename: str, data: bytes) -> None:
    ext = _file_extension(filename)
    storage.upload_image(
        "design_elements",
        _normalize_filename(filename) + ext,
        data,
        content_type=_mime_type(ext),
    )
    load_design_elements.clear()


def delete_design_element(filename: str) -> bool:
    deleted = storage.delete_image("design_elements", filename)
    # remove any metadata label for this element
    meta_path = Path(config.BRAND_ASSETS_DIR) / "design_elements.json"
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            meta = {}
        if filename in meta:
            meta.pop(filename, None)
            try:
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
    load_design_elements.clear()
    return deleted


def _design_elements_meta_path() -> Path:
    _ensure_local_assets_dir()
    return Path(config.BRAND_ASSETS_DIR) / "design_elements.json"


def list_design_elements_with_meta() -> list[tuple[str, str]]:
    """Return a list of (filename, label) tuples for design elements."""
    names = storage.list_images("design_elements")
    meta_path = _design_elements_meta_path()
    labels = {}
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                labels = json.load(f)
        except Exception:
            labels = {}
    return [(n, labels.get(n, "")) for n in sorted(names)]


def set_design_element_label(filename: str, label: str) -> None:
    meta_path = _design_elements_meta_path()
    try:
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        else:
            meta = {}
    except Exception:
        meta = {}
    meta[filename] = label or ""
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def get_design_element_label(filename: str) -> str:
    meta_path = _design_elements_meta_path()
    if not meta_path.exists():
        return ""
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return meta.get(filename, "")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Product images — MULTIPLE per product/variant, each tagged with a role.
#
# GCS layout:
#   skus/<product-slug>[__<variant-slug>]/<role>_<ms>.<ext>
# Legacy single images stored directly at skus/<product-slug>[__<variant>].<ext>
# are still recognised and surfaced as "Packaging".
# ---------------------------------------------------------------------------
SKU_IMAGE_ROLES = [
    ("packaging", "Packaging"),
    ("styling", "Styling / mood"),
    ("pieces", "Product pieces"),
]
_SKU_ROLE_LABELS = dict(SKU_IMAGE_ROLES)
_DEFAULT_SKU_ROLE = "packaging"


def sku_role_label(role: str) -> str:
    return _SKU_ROLE_LABELS.get(role, _SKU_ROLE_LABELS[_DEFAULT_SKU_ROLE])


def sku_image_filename(sku: str, variant: str | None = None, ext: str = ".png") -> str:
    return _sku_image_basename(sku, variant) + ext


def sku_image_folder(sku: str, variant: str | None = None) -> str:
    return "skus/" + _sku_image_basename(sku, variant)


def _role_from_filename(file: str) -> str:
    prefix = Path(file).stem.split("_", 1)[0]
    return prefix if prefix in _SKU_ROLE_LABELS else _DEFAULT_SKU_ROLE


def _split_sku_name(name: str) -> tuple[str, str]:
    """Split a name relative to 'skus/' into (folder, filename) for storage calls."""
    if "/" in name:
        sub, file = name.rsplit("/", 1)
        return f"skus/{sub}", file
    return "skus", name


def _clear_sku_caches() -> None:
    load_sku_image.clear()
    list_sku_images.clear()
    load_sku_image_data.clear()


def upload_sku_image(sku: str, variant: str | None, data: bytes, filename: str, role: str = _DEFAULT_SKU_ROLE) -> None:
    role = role if role in _SKU_ROLE_LABELS else _DEFAULT_SKU_ROLE
    ext = _file_extension(filename)
    fname = f"{role}_{int(time.time() * 1000)}{ext}"
    storage.upload_image(
        sku_image_folder(sku, variant),
        fname,
        data,
        content_type=_mime_type(ext),
    )
    _clear_sku_caches()


@st.cache_data(show_spinner=False)
def list_sku_images(sku: str, variant: str | None = None) -> list[dict]:
    """Images for one product/variant: [{folder, file, role}] (legacy included)."""
    base = _sku_image_basename(sku, variant)
    entries: list[dict] = []
    for name in sorted(storage.list_images("skus")):
        if "/" in name:
            folder0, _, file = name.partition("/")
            if folder0 != base or "/" in file:
                continue
            if Path(file).suffix.lower() not in _IMAGE_EXTENSIONS:
                continue
            entries.append({"folder": f"skus/{base}", "file": file, "role": _role_from_filename(file)})
        elif Path(name).stem == base and Path(name).suffix.lower() in _IMAGE_EXTENSIONS:
            entries.append({"folder": "skus", "file": name, "role": _DEFAULT_SKU_ROLE})
    return entries


@st.cache_data(show_spinner=False)
def load_sku_image_data(folder: str, file: str) -> bytes | None:
    return storage.get_image(folder, file)


def delete_sku_image_file(folder: str, file: str) -> bool:
    """Delete one specific product image."""
    deleted = storage.delete_image(folder, file)
    _clear_sku_caches()
    return deleted


def delete_sku_image(sku: str, variant: str | None = None) -> bool:
    """Delete ALL images for a product/variant. With variant=None this also
    removes every variant's images (used when deleting a product or category)."""
    base = _sku_image_basename(sku, variant) if variant else _slug(sku)
    deleted = False
    for name in storage.list_images("skus"):
        if "/" in name:
            folder0 = name.split("/", 1)[0]
            match = (folder0 == base) if variant else (folder0 == base or folder0.startswith(f"{base}__"))
        else:
            stem = Path(name).stem
            match = (stem == base) if variant else (stem == base or stem.startswith(f"{base}__"))
        if match:
            deleted |= storage.delete_image(*_split_sku_name(name))
    _clear_sku_caches()
    return deleted


@st.cache_data(show_spinner=False)
def load_sku_image(sku: str, variant: str | None = None) -> bytes | None:
    """Backward-compatible single image (prefers Packaging, else first)."""
    imgs = list_sku_images(sku, variant)
    if not imgs and variant:
        imgs = list_sku_images(sku)
    if not imgs:
        return None
    packs = [i for i in imgs if i["role"] == "packaging"]
    chosen = packs[0] if packs else imgs[0]
    return load_sku_image_data(chosen["folder"], chosen["file"])


# ---------------------------------------------------------------------------
# Generated banners (Gallery)
#
# GCS layout:
#   generated/<platform-slug>/<product-slug>[__<variant-slug>]_<ms>.png
# Older banners saved before per-platform organisation live directly in
# generated/<file> and surface under the "Uncategorized" bucket.
# ---------------------------------------------------------------------------
_GENERATED_FOLDER = "generated"
_UNCATEGORIZED = "uncategorized"


def _generated_subfolder(platform_slug: str) -> str:
    return f"{_GENERATED_FOLDER}/{platform_slug}"


def save_generated_banner(platform: str, sku: str, variant: str | None, data: bytes) -> None:
    """Save a generated banner grouped by platform, newest identifiable by name."""
    slug = _slug(platform) if platform else _UNCATEGORIZED
    base = _sku_image_basename(sku, variant)
    filename = f"{base}_{int(time.time() * 1000)}.png"
    storage.upload_image(_generated_subfolder(slug), filename, data, content_type="image/png")
    load_generated_index.clear()


@st.cache_data(show_spinner=False)
def load_generated_index() -> list[dict]:
    """Generated banners grouped by platform for the Gallery (one GCS list call).

    Returns ordered buckets: current platforms first (even if empty), then any
    orphan slugs, then "Uncategorized" last. Each bucket:
        {"slug", "label", "count", "items": [{"folder","file","updated"} ...]}
    with items sorted newest-first.
    """
    meta = storage.list_blobs_meta(_GENERATED_FOLDER)
    groups: dict[str, list] = {}
    for entry in meta:
        parts = entry["name"].split("/")
        if len(parts) == 1:
            slug, file = _UNCATEGORIZED, parts[0]
            folder = _GENERATED_FOLDER
        else:
            slug, file = parts[0], parts[-1]
            folder = _GENERATED_FOLDER + "/" + "/".join(parts[:-1])
        groups.setdefault(slug, []).append(
            {"folder": folder, "file": file, "updated": entry["updated"]}
        )

    def _sorted(items: list) -> list:
        return sorted(items, key=lambda x: x["updated"], reverse=True)

    platforms = load_platforms()
    slug_to_label = {_slug(p): p for p in platforms}

    ordered: list[dict] = []
    seen: set[str] = set()
    for p in platforms:
        s = _slug(p)
        items = _sorted(groups.get(s, []))
        ordered.append({"slug": s, "label": p, "count": len(items), "items": items})
        seen.add(s)
    for s, its in groups.items():
        if s in seen or s == _UNCATEGORIZED:
            continue
        items = _sorted(its)
        label = slug_to_label.get(s) or s.replace("_", " ").title()
        ordered.append({"slug": s, "label": label, "count": len(items), "items": items})
        seen.add(s)
    if groups.get(_UNCATEGORIZED):
        items = _sorted(groups[_UNCATEGORIZED])
        ordered.append(
            {"slug": _UNCATEGORIZED, "label": "Uncategorized", "count": len(items), "items": items}
        )
    return ordered


@st.cache_data(show_spinner=False)
def load_generated_image(folder: str, file: str) -> bytes | None:
    """Fetch one generated banner's bytes (cached per blob so reruns are free)."""
    return storage.get_image(folder, file)


def delete_generated_banner(folder: str, file: str) -> bool:
    deleted = storage.delete_image(folder, file)
    load_generated_index.clear()
    load_generated_image.clear()
    return deleted
