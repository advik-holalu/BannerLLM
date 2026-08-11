"""
app.py — GO Desi Banner Studio
The main screen your growth + design team uses.

Run locally:   streamlit run app.py
"""

import hmac
import streamlit as st

import assets
import config
import gemini_engine as engine
import imaging
import storage


def _widget_key(*parts: str) -> str:
    return "__".join(part.replace(" ", "_").lower() for part in parts)


# On-screen preview is scaled down so the whole banner fits on a laptop screen.
# Downloads always use the original full-resolution bytes — only display scales.
PREVIEW_MAX_HEIGHT = 640
PREVIEW_MAX_WIDTH = 680


def _preview_width(w: int, h: int) -> int:
    """Display width (px) that keeps the whole banner visible without scrolling,
    capping height to PREVIEW_MAX_HEIGHT and width to PREVIEW_MAX_WIDTH."""
    if not h:
        return PREVIEW_MAX_WIDTH
    by_height = round(PREVIEW_MAX_HEIGHT * w / h)
    return max(1, min(by_height, PREVIEW_MAX_WIDTH))


def _show_preview(data: bytes, w: int | None = None, h: int | None = None, caption=None) -> None:
    """Render a scaled-down preview (aspect ratio preserved). Never affects the
    downloaded file, which stays full resolution."""
    if w is None or h is None:
        w, h = imaging.dimensions(data)
    st.image(data, caption=caption, width=_preview_width(w, h))


def _file_sig(upload) -> str:
    """Stable identity for an uploaded file across Streamlit reruns.

    Uses Streamlit's per-file id when present (stable until the user changes the
    selection), falling back to name+size. NEVER use id(upload) — the Python
    object id is not stable across reruns and causes re-upload loops.
    """
    fid = getattr(upload, "file_id", None)
    if fid:
        return str(fid)
    return f"{getattr(upload, 'name', '')}:{getattr(upload, 'size', '')}"


def _files_sig(uploads) -> str:
    """Combined stable signature for a set of uploaded files (multi-uploaders)."""
    return "|".join(_file_sig(u) for u in uploads)


def _consume_upload(sig_key: str, sig: str) -> bool:
    """Return True exactly once for a newly selected upload, then mark it done.

    Gates a side-effectful upload so it runs only when a genuinely new file (or
    set of files) is selected — not on every rerun. Records the signature in
    session state so subsequent reruns skip the upload and the app goes idle.
    """
    if st.session_state.get(sig_key) == sig:
        return False
    st.session_state[sig_key] = sig
    return True


def _confirm_delete(prefix: str, confirm_msg: str, label: str = "Delete") -> bool:
    """Two-step inline delete for items that contain sub-items.

    Renders a delete button that arms an inline confirmation; returns True only
    once the user confirms. Buttons are full-width and stacked so they never
    wrap, even inside a narrow grid card. The caller performs the actual
    deletion and reruns when this returns True.
    """
    state_key = f"{prefix}__confirm"
    if not st.session_state.get(state_key):
        if st.button(label, key=f"{prefix}__arm", type="primary", use_container_width=True):
            st.session_state[state_key] = True
            st.rerun()
        return False

    st.warning(f"{confirm_msg} This can't be undone.")
    if st.button("Yes, delete", key=f"{prefix}__yes", type="primary", use_container_width=True):
        st.session_state.pop(state_key, None)
        return True
    if st.button("Cancel", key=f"{prefix}__no", type="secondary", use_container_width=True):
        st.session_state.pop(state_key, None)
        st.rerun()
    return False


def _delete_category(catalog: dict, category: str) -> None:
    """Delete a category and every product image/variant image it holds."""
    for product in list(catalog.get(category, {}).keys()):
        assets.delete_sku_image(product)  # removes base + all variant images
    catalog.pop(category, None)
    assets.save_catalog(catalog)
    st.cache_data.clear()


def _delete_product(catalog: dict, category: str, sku: str) -> None:
    """Delete a product, its image, and all of its variant images."""
    assets.delete_sku_image(sku)  # removes base + all variant images
    catalog.get(category, {}).pop(sku, None)
    assets.save_catalog(catalog)
    st.cache_data.clear()


def _list_row(
    *,
    name: str,
    delete_key: str,
    subtitle: str = "",
    view_key: str | None = None,
    delete_label: str = "Delete",
    needs_confirm: bool = False,
    confirm_msg: str = "",
) -> tuple[bool, bool]:
    """One full-width list row: name on the left, small View/Delete on the right.

    View is neutral (secondary), Delete is destructive (primary). For container
    items pass needs_confirm=True to require an inline confirmation before the
    delete fires. Returns (view_clicked, delete_confirmed); the caller performs
    the navigation/deletion and reruns.
    """
    view_clicked = False
    delete_confirmed = False
    armed_key = f"{delete_key}__armed"
    with st.container(border=True):
        cols = st.columns([5, 1.6, 1.6] if view_key else [7, 1.6])
        with cols[0]:
            st.markdown(f"**{name}**")
            if subtitle:
                st.caption(subtitle)
        next_col = 1
        if view_key:
            with cols[next_col]:
                if st.button("View", key=view_key, type="secondary", use_container_width=True):
                    view_clicked = True
            next_col += 1
        with cols[next_col]:
            if st.button(delete_label, key=delete_key, type="primary", use_container_width=True):
                if needs_confirm:
                    st.session_state[armed_key] = True
                    st.rerun()
                else:
                    delete_confirmed = True
        if st.session_state.get(armed_key):
            st.warning(f"{confirm_msg} This can't be undone.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Yes, delete", key=f"{delete_key}__yes", type="primary", use_container_width=True):
                    st.session_state.pop(armed_key, None)
                    delete_confirmed = True
            with c2:
                if st.button("Cancel", key=f"{delete_key}__no", type="secondary", use_container_width=True):
                    st.session_state.pop(armed_key, None)
                    st.rerun()
    return view_clicked, delete_confirmed


# ----------------------------------------------------------------------------
# Page setup
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="GO Desi Banner Studio",
    layout="centered",
)


# ----------------------------------------------------------------------------
# Session state
# ----------------------------------------------------------------------------

def _init_state():
    st.session_state.setdefault("current_image", None)
    # Conversation thread for the session: list of
    # {"prompt": str, "image": bytes} rounds, newest last.
    st.session_state.setdefault("thread", [])
    st.session_state.setdefault("last_brief", "")
    st.session_state.setdefault("manage_nav_level", "categories")
    st.session_state.setdefault("manage_selected_category", None)
    st.session_state.setdefault("manage_selected_sku", None)
    st.session_state.setdefault("manage_selected_variant", None)
    st.session_state.setdefault("uploaded_sku_file_id", None)
    st.session_state.setdefault("uploaded_variant_file_id", None)
    st.session_state.setdefault("uploaded_logo_file_id", None)
    st.session_state.setdefault("cached_sku_images", {})
    st.session_state.setdefault("cached_variant_images", {})
    st.session_state.setdefault("cached_design_elements", {})
    st.session_state.setdefault("cached_reference_images", {})
    st.session_state.setdefault("gallery_platform", None)
    st.session_state.setdefault("gallery_page", 0)



_init_state()


# ----------------------------------------------------------------------------
# Password gate
# The password is read from st.secrets (key APP_PASSWORD) — NEVER hardcoded —
# so it stays out of the repo, exactly like the API keys.
# ----------------------------------------------------------------------------
def _expected_password() -> str | None:
    try:
        return st.secrets.get("APP_PASSWORD")
    except Exception:
        # No secrets file configured at all.
        return None


def _render_login() -> None:
    st.title("GO Desi Banner Studio")
    expected = _expected_password()
    if not expected:
        st.error(
            "APP_PASSWORD is not set. Add APP_PASSWORD to your Streamlit secrets "
            "(.streamlit/secrets.toml locally, and the Streamlit Cloud secrets "
            "when deployed) to enable access."
        )
        return

    st.caption("Enter the password to continue.")
    with st.form("login_form"):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Enter", type="primary", use_container_width=True)
    if submitted:
        if hmac.compare_digest(password, expected):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")


if not st.session_state.get("authenticated"):
    _render_login()
    st.stop()  # Nothing below (sidebar, screens) renders until authenticated.


# ----------------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### GO Desi Banner Studio")
    # Simple button-based navigation to make the sidebar feel intentional
    st.session_state.setdefault("screen_mode", "Create banner")
    for label in ["Create banner", "Gallery", "Manage Products", "Rules & Assets"]:
        is_active = st.session_state.get("screen_mode") == label
        # Active tab renders red (primary); the others render as normal buttons.
        if st.button(
            label,
            key=f"nav_{label}",
            type="primary" if is_active else "secondary",
            use_container_width=True,
        ):
            st.session_state["screen_mode"] = label
            st.rerun()

    st.divider()
    st.caption(f"Model: **{config.MODELS[config.ACTIVE_MODEL]}**")
    references_loaded = len(assets.load_reference_images())
    st.caption(f"Style references loaded: **{references_loaded}**")
    if references_loaded == 0:
        st.warning(
            "No style references are available. Add some under "
            "Rules & Assets → Style references for better brand matching."
        )
    if st.button("Refresh assets", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()

    if st.button("Log out", type="secondary", use_container_width=True):
        st.session_state.pop("authenticated", None)
        st.rerun()


# ============================================================================
# SCREEN 1 — CREATE BANNER
# ============================================================================
def screen_create():
    st.title("Create a banner")

    catalog = assets.load_catalog()
    if not catalog:
        st.info("No categories yet. Add categories and products in Manage Products.")
        return

    col1, col2 = st.columns(2)
    with col1:
        category = st.selectbox("Category", list(catalog.keys()))
    with col2:
        skus = catalog.get(category, {})
        sku = st.selectbox("Product", list(skus.keys())) if skus else None

    if not sku:
        st.info("This category has no products yet. Add one in Manage Products.")
        return

    variants = catalog[category][sku].get("variants", [])
    variant = None
    if variants:
        selection = st.selectbox("Variant (optional)", [""] + variants)
        variant = selection or None

    product_image = assets.load_sku_image(sku, variant)
    if not product_image and variant:
        product_image = assets.load_sku_image(sku)

    if product_image:
        st.caption("Product shot that will be used.")
        st.image(product_image, width=180)
    else:
        st.info(
            "No product shot found for this product or variant. Upload one in Manage Products."
        )

    platforms = assets.load_platforms()
    # A platform is ALWAYS selected (defaults to the first, e.g. Blinkit) so the
    # Order Now button is never skipped for lack of a chosen platform.
    platform = st.selectbox("Platform", platforms, index=0) if platforms else None
    no_button = assets.load_platform_no_button(platform) if platform else False
    platform_button = assets.load_platform_button(platform) if platform else None

    if platform and no_button:
        st.caption(f"{platform} uses its own CTA — no Order Now button is added to the banner.")
    elif platform and platform_button:
        st.caption(f"The {platform} Order Now button will be placed on the banner.")
    elif platform:
        st.caption(
            f"No Order Now button uploaded for {platform}. Add one under "
            "Rules & Assets → Platforms, or its notes will still be applied."
        )

    # Some platforms (e.g. Meta) are pinned to a fixed size — the selector is
    # hidden and one banner is generated at that size. Others use the selector.
    fixed_size = assets.platform_fixed_size(platform) if platform else None
    if fixed_size:
        size_label, dimensions = fixed_size
        st.caption(f"{platform} banners are generated at {dimensions[0]}x{dimensions[1]} ({size_label}).")
    else:
        size_label = st.selectbox("Banner size", list(config.BANNER_SIZES.keys()))
        dimensions = config.BANNER_SIZES[size_label]

    st.markdown("**What should the banner look like?**")
    template_choice = st.selectbox(
        "Start from a template (optional)",
        ["— Write my own —"] + list(config.PROMPT_TEMPLATES.keys()),
    )
    if template_choice != "— Write my own —":
        default_prompt = config.PROMPT_TEMPLATES[template_choice].format(
            sku=sku, category=category
        )
    else:
        default_prompt = ""

    user_prompt = st.text_area(
        "Prompt",
        value=default_prompt,
        height=140,
        placeholder=f"e.g. A Diwali banner for {sku} with festive elements and a clear offer.",
    )

    banner_copy = st.text_area(
        "Banner copy (optional)",
        height=80,
        placeholder="Exact words to appear on the banner. Leave blank to let the model write a short headline.",
        help="Whatever you type here is rendered on the banner exactly as written, not rewritten.",
    )

    include_logo = st.checkbox(
        "Include GO DESi logo at top",
        value=True,
        help="When off, no separate GO DESi logo is added — only the logo printed on the product pack appears.",
    )

    if st.button("Generate banner", type="primary", use_container_width=True):
        with st.spinner("Designing the banner..."):
            try:
                brand_rules = assets.load_brand_rules_text()
                logo_image = assets.load_logo()
                logo_notes = assets.load_logo_notes()
                # Prefer this category's references; fall back to all categories.
                reference_named = assets.load_reference_images_named(category)
                design_elements_named = assets.load_design_elements_named()
                platform_notes = assets.load_platform_notes(platform) if platform else ""

                payload = engine.assemble_payload(
                    brand_rules=brand_rules,
                    category=category,
                    sku=sku,
                    variant=variant,
                    user_prompt=user_prompt,
                    size_label=size_label,
                    dimensions=dimensions,
                    banner_copy=banner_copy,
                    logo_image=logo_image,
                    logo_notes=logo_notes,
                    include_logo=include_logo,
                    design_elements=design_elements_named,
                    reference_images=reference_named,
                    product_image=product_image,
                    product_label=assets.sku_image_filename(sku, variant),
                    platform=platform or "",
                    platform_notes=platform_notes,
                    platform_button=platform_button,
                    no_button=no_button,
                    design_elements_bw=config.DESIGN_ELEMENTS_ARE_BW,
                )
                img = engine.generate_from_payload(payload["brief"], payload["images"])
                st.session_state.last_brief = payload["brief"]

                st.session_state.current_image = img
                # Start a fresh conversation thread with this banner.
                initial_prompt = user_prompt.strip() or f"Generate a banner for {sku}."
                st.session_state.thread = [{"prompt": initial_prompt, "image": img}]
                # Save grouped by platform so the Gallery can drill down by platform.
                assets.save_generated_banner(platform or "", sku, variant, img)
                st.success("Banner generated and saved to cloud storage.")
            except Exception as exc:
                st.error(f"Generation failed: {exc}")

    sku_slug = sku.replace(" ", "_").lower()

    # The session as a scrolling conversation thread. Each round
    # shows the user's prompt/instruction, then the resulting banner (capped
    # preview) with its own full-resolution download. New rounds append below.
    thread = st.session_state.get("thread") or []
    if thread:
        st.divider()
        st.markdown("**Session**")
        last_index = len(thread) - 1
        for index, round_ in enumerate(thread):
            # User prompt — right-aligned bubble (offset into the right columns).
            _, user_col = st.columns([1, 3])
            with user_col:
                with st.container(border=True):
                    st.markdown(round_["prompt"])
            # AI banner — left-aligned (full width; the capped preview sits left).
            caption = "Latest version" if index == last_index else f"Version {index + 1}"
            _show_preview(round_["image"], caption=caption)
            st.download_button(
                "Download PNG",
                data=round_["image"],
                file_name=f"godesi_{sku_slug}_v{index + 1}.png",
                mime="image/png",
                key=_widget_key("dl_round", str(index)),
                type="primary",
                use_container_width=True,
            )

        st.markdown("**Refine the banner**")
        st.caption("Refinements apply to the most recent banner and append a new round below.")
        in_col, send_col = st.columns([6, 1], vertical_alignment="bottom")
        with in_col:
            edit = st.text_input(
                "Refine",
                placeholder="Describe a change, for example make the layout cleaner or increase product prominence.",
                label_visibility="collapsed",
            )
        with send_col:
            send = st.button(
                "Send",
                icon=":material/send:",
                type="primary",
                use_container_width=True,
            )
        if send and edit.strip():
            with st.spinner("Applying the edit..."):
                try:
                    new_img = engine.edit_banner(thread[-1]["image"], edit)
                    st.session_state.thread.append({"prompt": edit.strip(), "image": new_img})
                    st.session_state.current_image = new_img
                    st.rerun()
                except Exception as exc:
                    st.error(f"Edit failed: {exc}")


# ============================================================================
# SCREEN 1b — GALLERY
# ============================================================================
_GALLERY_PAGE_SIZE = 12


def screen_gallery():
    st.title("Gallery")
    index = assets.load_generated_index()
    selected = st.session_state.get("gallery_platform")

    # --- Top level: platform cards with counts ---
    if not selected:
        st.caption("Past generated banners, grouped by platform. Newest first.")
        if not index:
            st.info("No banners generated yet.")
            return
        per_row = 3
        for i in range(0, len(index), per_row):
            cols = st.columns(per_row)
            for col, bucket in zip(cols, index[i : i + per_row]):
                with col:
                    with st.container(border=True):
                        st.subheader(bucket["label"])
                        n = bucket["count"]
                        st.caption(f"{n} banner{'s' if n != 1 else ''}")
                        if st.button(
                            "View",
                            key=_widget_key("gal_view", bucket["slug"]),
                            type="primary",
                            use_container_width=True,
                            disabled=n == 0,
                        ):
                            st.session_state.gallery_platform = bucket["slug"]
                            st.session_state.gallery_page = 0
                            st.rerun()
        return

    # --- Platform level: paginated grid of that platform's banners ---
    bucket = next((b for b in index if b["slug"] == selected), None)
    if st.button("< back to platforms", key="gallery_back", type="secondary"):
        st.session_state.gallery_platform = None
        st.session_state.gallery_page = 0
        st.rerun()
    if bucket is None or not bucket["items"]:
        st.markdown(f"### {bucket['label'] if bucket else selected}")
        st.info("No banners for this platform yet.")
        return

    st.markdown(f"### {bucket['label']}")
    items = bucket["items"]  # already newest-first
    total_pages = (len(items) + _GALLERY_PAGE_SIZE - 1) // _GALLERY_PAGE_SIZE
    page = max(0, min(st.session_state.get("gallery_page", 0), total_pages - 1))
    start = page * _GALLERY_PAGE_SIZE
    page_items = items[start : start + _GALLERY_PAGE_SIZE]

    per_row = 3
    for i in range(0, len(page_items), per_row):
        cols = st.columns(per_row)
        for col, item in zip(cols, page_items[i : i + per_row]):
            with col:
                with st.container(border=True):
                    data = assets.load_generated_image(item["folder"], item["file"])
                    if not data:
                        st.caption("(image unavailable)")
                        continue
                    st.image(data, use_container_width=True)
                    st.download_button(
                        "Download",
                        data=data,
                        file_name=item["file"],
                        mime="image/png",
                        key=_widget_key("gal_dl", item["folder"], item["file"]),
                        type="primary",
                        use_container_width=True,
                    )
                    if _confirm_delete(
                        _widget_key("gal_del", item["folder"], item["file"]),
                        "Remove this banner?",
                        label="Remove",
                    ):
                        assets.delete_generated_banner(item["folder"], item["file"])
                        st.toast("Banner removed.")
                        st.rerun()

    if total_pages > 1:
        p1, p2, p3 = st.columns([1, 2, 1])
        with p1:
            if page > 0 and st.button("Previous", key="gallery_prev", use_container_width=True):
                st.session_state.gallery_page = page - 1
                st.rerun()
        with p2:
            st.caption(f"Page {page + 1} of {total_pages}")
        with p3:
            if page < total_pages - 1 and st.button("Next", key="gallery_next", use_container_width=True):
                st.session_state.gallery_page = page + 1
                st.rerun()


# ============================================================================
# SCREEN 2 — MANAGE PRODUCTS
# ============================================================================
def screen_manage():
    st.title("Manage categories and products")
    catalog = assets.load_catalog()

    # Breadcrumbs for visual hierarchy
    nav_level = st.session_state.get("manage_nav_level", "categories")
    cat = st.session_state.get("manage_selected_category")
    sku = st.session_state.get("manage_selected_sku")
    var = st.session_state.get("manage_selected_variant")
    crumb = " » ".join([p for p in [cat, sku, var] if p])
    if crumb:
        st.caption(crumb)

    if nav_level == "categories":
        _manage_level_categories(catalog)
    elif nav_level == "category":
        _manage_level_category(catalog)
    elif nav_level == "sku":
        _manage_level_sku(catalog)
    elif nav_level == "variant":
        _manage_level_variant(catalog)


def _manage_level_categories(catalog: dict) -> None:
    st.markdown("### All Categories")

    col1, col2 = st.columns([3, 1])
    with col1:
        new_category = st.text_input("New category name", label_visibility="collapsed", placeholder="Enter category name")
    with col2:
        if st.button("Add", type="primary", use_container_width=True):
            name = new_category.strip()
            if name:
                catalog.setdefault(name, {})
                assets.save_catalog(catalog)
                st.toast(f"Added category: {name}")
                st.rerun()

    st.divider()

    if not catalog:
        st.info("No categories yet. Add one above.")
        return

    for category in sorted(catalog.keys()):
        sku_count = len(catalog[category])
        prefix = _widget_key("cat_row", category)
        view_clicked, delete_confirmed = _list_row(
            name=category,
            subtitle=f"{sku_count} product{'s' if sku_count != 1 else ''}",
            view_key=f"{prefix}__view",
            delete_key=f"{prefix}__del",
            needs_confirm=True,
            confirm_msg=(
                f"Delete '{category}' and its {sku_count} product(s)?"
                if sku_count
                else f"Delete category '{category}'?"
            ),
        )
        if view_clicked:
            st.session_state.manage_nav_level = "category"
            st.session_state.manage_selected_category = category
            st.rerun()
        if delete_confirmed:
            _delete_category(catalog, category)
            st.toast(f"Deleted category: {category}")
            st.rerun()


def _manage_level_category(catalog: dict) -> None:
    category = st.session_state.manage_selected_category
    if not category or category not in catalog:
        st.session_state.manage_nav_level = "categories"
        st.rerun()

    bcol, _ = st.columns([1.3, 5])
    with bcol:
        if st.button("< back", key="back_to_categories", type="secondary", use_container_width=True):
            st.session_state.manage_nav_level = "categories"
            st.session_state.manage_selected_category = None
            st.rerun()

    st.markdown(f"### {category}")

    col1, col2 = st.columns([3, 1])
    with col1:
        new_sku = st.text_input("New product name", label_visibility="collapsed", placeholder="Enter product name", key="new_sku_input")
    with col2:
        if st.button("Add Product", type="primary", use_container_width=True):
            name = new_sku.strip()
            if name:
                if name not in catalog[category]:
                    catalog[category][name] = {"variants": []}
                    assets.save_catalog(catalog)
                    st.toast(f"Added product: {name}")
                    st.rerun()
                else:
                    st.toast("This product already exists.")

    st.divider()

    skus = sorted(catalog[category].keys())
    if not skus:
        st.info("No products in this category yet.")
        return

    for sku in skus:
        variant_count = len(catalog[category][sku].get("variants", []))
        prefix = _widget_key("prod_row", category, sku)
        view_clicked, delete_confirmed = _list_row(
            name=sku,
            subtitle=f"{variant_count} variant{'s' if variant_count != 1 else ''}",
            view_key=f"{prefix}__view",
            delete_key=f"{prefix}__del",
            needs_confirm=True,  # container: image + variants
            confirm_msg=f"Delete '{sku}' and everything in it?",
        )
        if view_clicked:
            st.session_state.manage_nav_level = "sku"
            st.session_state.manage_selected_sku = sku
            st.rerun()
        if delete_confirmed:
            _delete_product(catalog, category, sku)
            st.toast(f"Deleted product: {sku}")
            st.rerun()


def _manage_level_sku(catalog: dict) -> None:
    category = st.session_state.manage_selected_category
    sku = st.session_state.manage_selected_sku

    if not category or not sku or sku not in catalog.get(category, {}):
        st.session_state.manage_nav_level = "category"
        st.session_state.manage_selected_sku = None
        st.rerun()

    bcol, _ = st.columns([1.3, 5])
    with bcol:
        if st.button("< back", key="back_to_category", type="secondary", use_container_width=True):
            st.session_state.manage_nav_level = "category"
            st.session_state.manage_selected_sku = None
            st.rerun()

    st.markdown(f"### {sku}")

    # A product is a container (image + variants) — confirm before deleting.
    if _confirm_delete(
        _widget_key("del_prod", category, sku),
        f"Delete '{sku}' and everything in it (image and variants)?",
        label="Delete Product",
    ):
        _delete_product(catalog, category, sku)
        st.toast(f"Deleted product: {sku}")
        st.session_state.manage_nav_level = "category"
        st.session_state.manage_selected_sku = None
        st.rerun()

    st.divider()

    _manage_sku_image_section(sku, None, category, catalog)

    st.divider()
    st.markdown("#### Variants")

    variant_list = catalog[category][sku].get("variants", [])
    col1, col2 = st.columns([3, 1])
    with col1:
        new_variant = st.text_input("New variant name", label_visibility="collapsed", placeholder="Enter variant name", key="new_variant_input")
    with col2:
        if st.button("Add Variant", type="primary", use_container_width=True):
            name = new_variant.strip()
            if name:
                if name not in variant_list:
                    variant_list.append(name)
                    catalog[category][sku]["variants"] = variant_list
                    assets.save_catalog(catalog)
                    st.toast(f"Added variant: {name}")
                    st.rerun()
                else:
                    st.toast("This variant already exists.")

    if not variant_list:
        st.info("No variants for this product yet.")
        return

    for variant in list(variant_list):
        prefix = _widget_key("var_row", category, sku, variant)
        view_clicked, delete_confirmed = _list_row(
            name=variant,
            view_key=f"{prefix}__view",
            delete_key=f"{prefix}__del",
            needs_confirm=True,
            confirm_msg=f"Delete variant '{variant}' and its image?",
        )
        if view_clicked:
            st.session_state.manage_nav_level = "variant"
            st.session_state.manage_selected_variant = variant
            st.rerun()
        if delete_confirmed:
            variant_list.remove(variant)
            catalog[category][sku]["variants"] = variant_list
            assets.delete_sku_image(sku, variant)
            assets.save_catalog(catalog)
            st.cache_data.clear()
            st.toast(f"Deleted variant: {variant}")
            st.rerun()


def _manage_level_variant(catalog: dict) -> None:
    category = st.session_state.manage_selected_category
    sku = st.session_state.manage_selected_sku
    variant = st.session_state.manage_selected_variant

    if not category or not sku or not variant or variant not in catalog.get(category, {}).get(sku, {}).get("variants", []):
        st.session_state.manage_nav_level = "sku"
        st.session_state.manage_selected_variant = None
        st.rerun()

    bcol, _ = st.columns([1.3, 5])
    with bcol:
        if st.button("< back", key="back_to_product", type="secondary", use_container_width=True):
            st.session_state.manage_nav_level = "sku"
            st.session_state.manage_selected_variant = None
            st.rerun()

    st.markdown(f"### {variant}")
    if _confirm_delete(
        _widget_key("del_variant_detail", category, sku, variant),
        f"Delete variant '{variant}' and its image?",
        label="Delete Variant",
    ):
        variant_list = catalog[category][sku]["variants"]
        variant_list.remove(variant)
        catalog[category][sku]["variants"] = variant_list
        assets.delete_sku_image(sku, variant)
        st.cache_data.clear()
        assets.save_catalog(catalog)
        st.toast(f"Deleted variant: {variant}")
        st.session_state.manage_nav_level = "sku"
        st.session_state.manage_selected_variant = None
        st.rerun()

    st.divider()
    _manage_sku_image_section(sku, variant, category, catalog)


def _manage_sku_image_section(sku: str, variant: str | None, category: str, catalog: dict) -> None:
    section_key = f"{sku}__{variant}" if variant else sku
    cache_key = f"cached_{section_key}"
    file_id_key = f"uploaded_{section_key}_file_id"

    st.markdown("#### Product Image")

    cached_image = st.session_state.cached_sku_images.get(cache_key)
    current_image = cached_image or assets.load_sku_image(sku, variant)

    if current_image:
        if cache_key not in st.session_state.cached_sku_images:
            st.session_state.cached_sku_images[cache_key] = current_image

        st.image(current_image, caption="Current image", use_container_width=True)
        if _confirm_delete(
            _widget_key("remove_img", section_key),
            "Remove this image?",
            label="Remove",
        ):
            deleted = assets.delete_sku_image(sku, variant)
            st.cache_data.clear()
            if deleted:
                st.session_state.cached_sku_images.pop(cache_key, None)
                st.session_state[file_id_key] = None
                st.toast("Image removed.")
            else:
                st.error("Image not found or deletion failed.")
            st.rerun()
    else:
        st.caption("No image uploaded yet.")

    upload = st.file_uploader(
        "Upload new image",
        type=["png", "jpg", "jpeg", "webp"],
        key=_widget_key("upload_img", section_key),
        label_visibility="collapsed",
    )

    if upload and _consume_upload(file_id_key, _file_sig(upload)):
        try:
            data = upload.read()
            assets.upload_sku_image(sku, variant, data, upload.name)
            st.session_state.cached_sku_images[cache_key] = data
            st.toast("Image saved to cloud storage.")
            st.rerun()
        except Exception as exc:
            # Roll back the guard so the user can retry the same file.
            st.session_state[file_id_key] = None
            st.error(f"Upload failed: {exc}")



# ============================================================================
# SCREEN 3 — BRAND RULES
# ============================================================================
def _style_references_tab() -> None:
    st.markdown("#### Style references")
    st.caption(
        "Upload only banners that follow the Core rules — clean background, pack "
        "dominant, no traditional festive cliches. These teach the AI your style. "
        "If a past banner breaks the core rules, don't upload it."
    )

    catalog = assets.load_catalog()
    if not catalog:
        st.info("No categories yet. Add categories in Manage Products first.")
        return

    category = st.selectbox(
        "Category",
        list(catalog.keys()),
        key="reference_category_select",
    )

    uploaded = st.file_uploader(
        "Upload style references for this category",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key=_widget_key("ref_upload", category),
    )
    if uploaded and _consume_upload(_widget_key("ref_upload_sig", category), _files_sig(uploaded)):
        for item in uploaded:
            assets.upload_reference_image(category, item.name, item.read())
        st.toast(f"Uploaded to {category}.")
        st.rerun()

    names = assets.list_reference_images(category)
    notes = assets.load_reference_notes()

    if not names:
        st.info("No style references in this category yet.")
        return

    st.markdown(f"**Style references in {category}**")
    per_row = 3
    for i in range(0, len(names), per_row):
        row = names[i : i + per_row]
        cols = st.columns(per_row)
        for col, name in zip(cols, row):
            with col:
                cache_key = f"reference__{assets._slug(category)}__{name}"
                data = st.session_state["cached_reference_images"].get(cache_key)
                if data is None:
                    data = storage.get_image(assets.reference_folder(category), name)
                    if data:
                        st.session_state["cached_reference_images"][cache_key] = data
                if not data:
                    continue
                note_key = f"{assets._slug(category)}/{name}"
                with st.container(border=True):
                    st.image(data, caption=name, use_container_width=True)
                    new_note = st.text_input(
                        "Note (optional)",
                        value=notes.get(note_key, ""),
                        key=_widget_key("ref_note", category, name),
                        placeholder="e.g. our best Diwali style",
                    )
                    # Full-width stacked buttons so they never squish in the grid.
                    if st.button(
                        "Save note",
                        key=_widget_key("ref_save_note", category, name),
                        type="primary",
                        use_container_width=True,
                    ):
                        assets.set_reference_note(category, name, new_note)
                        st.success("Note saved.")
                    if _confirm_delete(
                        _widget_key("ref_remove", category, name),
                        "Remove this style reference?",
                        label="Remove",
                    ):
                        deleted = assets.delete_reference_image(category, name)
                        st.session_state["cached_reference_images"].pop(cache_key, None)
                        st.cache_data.clear()
                        if deleted:
                            st.toast("Style reference removed.")
                        else:
                            st.error("Image not found or deletion failed.")
                        st.rerun()


def _platforms_tab() -> None:
    st.markdown("#### Platforms")
    st.caption(
        "Each platform has a fixed Order Now button and placement rules, used "
        "when generating banners for that platform."
    )

    platforms = assets.load_platforms()

    col1, col2 = st.columns([3, 1])
    with col1:
        new_platform = st.text_input(
            "Add a platform",
            label_visibility="collapsed",
            placeholder="Add a new platform (e.g. Swiggy Instamart)",
            key="new_platform_input",
        )
    with col2:
        if st.button("Add platform", type="primary", use_container_width=True):
            if assets.add_platform(new_platform):
                st.success(f"Added platform: {new_platform.strip()}")
                # Refresh the local list so the selectbox below includes it,
                # without a rerun that would reset the active tab.
                platforms = assets.load_platforms()
            else:
                st.warning("Enter a new, unique platform name.")

    if not platforms:
        st.info("No platforms yet. Add one above.")
        return

    st.divider()
    platform = st.selectbox("Platform", platforms, key="platform_admin_select")

    current_no_button = assets.load_platform_no_button(platform)
    no_button_val = st.checkbox(
        "No Order Now button (this platform uses its own CTA)",
        value=current_no_button,
        key=_widget_key("platform_no_button", platform),
        help="When on, generated banners for this platform never bake in an Order Now button.",
    )
    if no_button_val != current_no_button:
        assets.save_platform_no_button(platform, no_button_val)
        st.toast("Saved.")
        st.rerun()

    st.markdown("##### Order Now button")
    if no_button_val:
        st.caption("This platform is set to use its own CTA — any uploaded button below is ignored during generation.")
    button = assets.load_platform_button(platform)
    if button:
        st.image(button, caption=f"Current {platform} button", width=220)
        if _confirm_delete(
            _widget_key("remove_platform_btn", platform),
            "Remove this Order Now button?",
            label="Remove",
        ):
            deleted = assets.delete_platform_button(platform)
            st.cache_data.clear()
            if not deleted:
                st.error("Button not found or deletion failed.")
            else:
                st.toast("Button removed.")
            st.rerun()
        uploader_label = "Replace Order Now button"
    else:
        st.caption("No Order Now button uploaded yet.")
        uploader_label = "Upload Order Now button"

    button_upload = st.file_uploader(
        uploader_label,
        type=["png", "jpg", "jpeg", "webp"],
        key=_widget_key("platform_btn_upload", platform),
    )
    if button_upload is not None:
        sig_key = _widget_key("uploaded_platform_btn", platform)
        if _consume_upload(sig_key, _file_sig(button_upload)):
            try:
                assets.upload_platform_button(platform, button_upload.read())
                st.cache_data.clear()
                st.toast("Order Now button saved.")
                st.rerun()
            except Exception as exc:
                st.session_state[sig_key] = None
                st.error(f"Upload failed: {exc}")

    st.markdown("##### Button rules")
    notes_value = assets.load_platform_notes(platform)
    new_notes = st.text_area(
        "Button placement and usage rules",
        value=notes_value,
        height=140,
        placeholder=(
            "e.g. Use this exact Blinkit Order Now button, do not redraw or "
            "restyle it; place it bottom-center. Or: leave clear empty space "
            "bottom-center for the button to be added by a designer later."
        ),
        key=_widget_key("platform_notes", platform),
    )
    if st.button("Save button rules", key=_widget_key("save_platform_notes", platform), type="primary", use_container_width=True):
        assets.save_platform_notes(platform, new_notes)
        st.success("Button rules saved.")

    st.divider()
    st.markdown("##### Delete platform")
    if platform in config.DEFAULT_PLATFORMS:
        st.caption("Default platforms can't be deleted.")
    elif _confirm_delete(
        _widget_key("del_platform", platform),
        f"Delete platform '{platform}' and its button and rules?",
        label="Delete platform",
    ):
        assets.delete_platform(platform)
        st.cache_data.clear()
        # Drop the stale selectbox value so it re-defaults to a valid platform.
        st.session_state.pop("platform_admin_select", None)
        st.toast(f"Deleted platform: {platform}")
        st.rerun()


def _core_rules_tab() -> None:
    st.markdown("#### Core rules")
    st.caption(
        "These are the structural rules that keep banners working on q-commerce "
        "platforms. They apply to every generation and cannot be edited here. To "
        "change them, contact Advik."
    )
    with st.container(border=True):
        # Preserve the line structure of CORE_RULES when rendering as markdown.
        st.markdown(config.CORE_RULES.replace("\n", "  \n"))


def _brand_rules_tab() -> None:
    st.markdown("#### Brand rules")
    st.caption(
        "Your brand voice and visual preferences in one place — tone, CTA, "
        "approved headlines, words to avoid, colours, placement, audience. Edit "
        "freely. This is included in every banner brief."
    )
    text = st.text_area(
        "Brand rules",
        value=assets.load_brand_rules_text(),
        height=420,
        label_visibility="collapsed",
        key="brand_rules_text",
    )
    if st.button("Save", type="primary", use_container_width=True, key="save_brand_rules"):
        assets.save_brand_rules_text(text)
        st.success("Brand rules saved.")


def _logo_tab() -> None:
    st.markdown("#### Logo")
    st.caption(
        "The official logo is sent with every generation and placed per the notes below."
    )
    logo = assets.load_logo()
    if logo:
        st.image(logo, caption="Current brand logo", width=220)
        if _confirm_delete("remove_logo", "Remove the brand logo?", label="Remove"):
            deleted = assets.delete_logo()
            st.cache_data.clear()
            if not deleted:
                st.error("Logo not found or deletion failed.")
            else:
                st.toast("Logo removed.")
            st.rerun()
        uploader_label = "Replace logo"
    else:
        st.caption("No logo uploaded yet.")
        uploader_label = "Upload brand logo"

    logo_upload = st.file_uploader(
        uploader_label, type=["png", "jpg", "jpeg", "webp"], key="logo_uploader"
    )
    if logo_upload is not None and _consume_upload("uploaded_logo_file_id", _file_sig(logo_upload)):
        try:
            assets.upload_logo(logo_upload.read())
            st.cache_data.clear()
            st.toast("Logo saved.")
            st.rerun()
        except Exception as exc:
            st.session_state["uploaded_logo_file_id"] = None
            st.error(f"Upload failed: {exc}")

    new_logo_notes = st.text_area(
        "Logo notes (Noor circle rule, placement, usage)",
        value=assets.load_logo_notes(),
        height=160,
        placeholder=(
            "e.g. Noor rule: the circle behind the logo changes colour to "
            "complement the banner. Always place the logo at the top. Never "
            "recolour or distort the logo mark itself."
        ),
        key="logo_notes_input",
    )
    if st.button("Save logo notes", type="primary", use_container_width=True, key="save_logo_notes"):
        assets.save_logo_notes(new_logo_notes)
        st.success("Logo notes saved.")


def _design_elements_tab() -> None:
    st.markdown("#### Design elements")
    st.caption(
        "Optional decorative assets the AI may draw from, sparingly, at the edges. "
        "Upload in black & white; the AI recolours the ones it uses."
    )
    uploaded = st.file_uploader(
        "Upload design element images",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key="design_elements_upload",
    )
    if uploaded and _consume_upload("design_elements_upload_sig", _files_sig(uploaded)):
        for item in uploaded:
            assets.upload_design_element(item.name, item.read())
        st.toast("Design elements uploaded.")
        st.rerun()

    elements = assets.list_design_elements_with_meta()
    if not elements:
        st.info("No design elements have been uploaded yet.")
        return

    st.markdown("**Current design elements**")
    per_row = 3
    for i in range(0, len(elements), per_row):
        row = elements[i : i + per_row]
        cols = st.columns(per_row)
        for col, (name, label) in zip(cols, row):
            with col:
                cache_key = f"design_element__{name}"
                data = st.session_state["cached_design_elements"].get(cache_key)
                if data is None:
                    data = storage.get_image("design_elements", name)
                    if data:
                        st.session_state["cached_design_elements"][cache_key] = data
                if not data:
                    continue
                with st.container(border=True):
                    st.image(data, caption=name, use_container_width=True)
                    new_label = st.text_input(
                        "Label (optional)", value=label, key=_widget_key("label", name)
                    )
                    if st.button(
                        "Save label",
                        key=_widget_key("save_label", name),
                        type="primary",
                        use_container_width=True,
                    ):
                        assets.set_design_element_label(name, new_label.strip())
                        st.success("Label saved.")
                    if _confirm_delete(
                        _widget_key("remove_design", name),
                        "Remove this design element?",
                        label="Remove",
                    ):
                        deleted = assets.delete_design_element(name)
                        st.session_state["cached_design_elements"].pop(cache_key, None)
                        st.cache_data.clear()
                        if deleted:
                            st.toast("Design element removed.")
                        else:
                            st.error("Image not found or deletion failed.")
                        st.rerun()


def screen_rules():
    st.title("Rules & Assets")
    tabs = st.tabs([
        "Core rules",
        "Brand rules",
        "Logo",
        "Design elements",
        "Style references",
        "Platforms",
    ])
    with tabs[0]:
        _core_rules_tab()
    with tabs[1]:
        _brand_rules_tab()
    with tabs[2]:
        _logo_tab()
    with tabs[3]:
        _design_elements_tab()
    with tabs[4]:
        _style_references_tab()
    with tabs[5]:
        _platforms_tab()


# ----------------------------------------------------------------------------
# Router
# ----------------------------------------------------------------------------
screen_mode = st.session_state.get("screen_mode", "Create banner")
if screen_mode == "Create banner":
    screen_create()
elif screen_mode == "Gallery":
    screen_gallery()
elif screen_mode == "Manage Products":
    screen_manage()
else:
    screen_rules()
