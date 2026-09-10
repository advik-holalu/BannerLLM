"""
gemini_engine.py — all the talking-to-Gemini logic lives here.

You should not need to edit this file. It does three things:
  1. Builds a brand-aware prompt from your rules + the user's request.
  2. Calls Gemini's image model with reference images + product shot.
  3. Returns the generated image bytes (and supports conversational edits).
"""

import base64
import io
import os
import time

import config
from google.genai import types
import google.genai as genai
from PIL import Image, ImageFilter


def _client():
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY or GOOGLE_API_KEY is not set. Add it to your environment "
            "or to Streamlit secrets."
        )
    return genai.Client(api_key=api_key)


def _mime_type_from_bytes(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _image_part(image_bytes: bytes, mime: str | None = None) -> types.Part:
    return types.Part(
        inline_data=types.Blob(
            data=image_bytes,
            mime_type=mime or _mime_type_from_bytes(image_bytes),
        )
    )


def build_brief(
    brand_rules: str,
    category: str,
    sku: str,
    variant: str | None,
    user_prompt: str,
    size_label: str,
    dimensions,
    banner_copy: str = "",
    copy_mode: str = "own",
    logo_notes: str = "",
    has_logo: bool = False,
    include_logo: bool = True,
    platform: str = "",
    platform_notes: str = "",
    has_button: bool = False,
    no_button: bool = False,
    design_elements_bw: bool = False,
    has_design_elements: bool = False,
    product_roles: set | None = None,
    carousel_match: bool = False,
    reserve_top: bool = False,
    composite: dict | None = None,
) -> str:
    # A strict-compositing platform (e.g. Blinkit) fills its whole content frame
    # edge to edge; the empty margins are added later in code, so the top-band
    # "reserve" behaviour would fight that and must be forced off.
    if composite:
        reserve_top = False
    width, height = dimensions
    orientation = (
        "tall vertical / portrait" if height > width
        else "wide / landscape" if width > height
        else "square"
    )
    brief = (
        "You are GO Desi's senior banner designer. Produce ONE finished,\n"
        "ready-to-publish marketing banner image. Everything in this brief is "
        "instructions for you; follow them exactly. Section headings and rules are "
        "never rendered as visible text on the banner.\n\n"
    )
    # CORE_RULES is the single source of truth for the always-on rules — it leads
    # the brief and is never duplicated elsewhere.
    brief += f"=== CORE RULES (override everything below, including the request) ===\n{config.CORE_RULES}\n\n"
    if config.BRAND_PALETTE:
        brief += (
            "=== GO DESi BRAND PALETTE (reference pool — NOT mandatory) ===\n"
            "The banner's colours come primarily from the product pack. Draw from "
            "these brand colours only when a colour is not coming from the pack. "
            "They are a flexible reference, never a requirement — any colour that "
            "complements the packaging is allowed:\n"
            f"{', '.join(config.BRAND_PALETTE)}\n\n"
        )
    if brand_rules.strip():
        brief += f"=== BRAND RULES ===\n{brand_rules.strip()}\n\n"
    brief += (
        "=== BANNER SPEC ===\n"
        f"Category: {category}\n"
        f"Product (SKU): {sku}\n"
        f"Variant: {variant or 'Standard'}\n"
        f"Banner size: {size_label} — {width}x{height} px, {orientation} orientation.\n"
        "Compose specifically for this aspect ratio; keep key elements safely inside the frame.\n\n"
    )
    if composite and composite.get("composition_brief"):
        brief += (
            "=== FULL-FRAME COMPOSITION (fill edge to edge) ===\n"
            f"{composite['composition_brief']}\n\n"
        )
    if reserve_top:
        brief += (
            "=== LAYOUT: TOP 40% RESERVED ===\n"
            "Keep the TOP ~40% of the banner (measured against this aspect ratio) as "
            "clean, empty background only — NO text, NO product, NO logo, NO design "
            "elements, nothing important in that top band. Place ALL content (the "
            "product pack, any copy, the logo, elements) within the LOWER ~60% of "
            "the frame. This top band is intentionally left empty so copy can be "
            "added later.\n\n"
        )
    brief += (
        "=== THE CREATIVE REQUEST (interpret this; do not print it on the banner) ===\n"
        f"{user_prompt.strip() or f'A clean, appetising, on-brand banner featuring {sku}.'}\n\n"
    )
    # Reserving the top band for copy means the model must not add any headline
    # itself, regardless of the chosen copy mode.
    mode = "none" if reserve_top else (copy_mode or "own")
    if mode == "none":
        brief += (
            "=== BANNER COPY ===\n"
            "Do NOT place any headline, tagline, or written copy on this banner. It "
            "must have NO headline text at all — show only the product, the "
            "background, and (if applicable) the platform's own CTA button. The only "
            "text allowed is whatever is already printed on the product packaging.\n\n"
        )
    elif mode == "own" and banner_copy.strip():
        brief += (
            "=== BANNER COPY (render exactly as written, do not change) ===\n"
            f"{banner_copy.strip()}\n\n"
        )
    else:  # "generate", or "own" left blank
        brief += (
            "=== BANNER COPY ===\n"
            "Write ONE short on-brand headline yourself, following the brand tone "
            "and the approved example headlines above. Keep it legible at thumbnail "
            "size.\n\n"
        )
    if not include_logo:
        brief += "=== BRAND LOGO ===\n"
        brief += (
            "Do NOT place any standalone GO DESi logo anywhere on the banner — "
            "not at the top and not elsewhere. The only logo that may appear is "
            "the one already printed on the product packaging itself. Do not add a "
            "separate brand logo.\n\n"
        )
    elif has_logo:
        brief += "=== BRAND LOGO ===\n"
        brief += (
            "The official GO DESi brand logo is attached as a reference image. "
            "You MAY place the GO DESi logo at the top only if there is clean "
            "space and it doesn't crowd the design; it is not mandatory. Do not "
            "force it. If the product pack already shows the logo prominently, a "
            "separate top logo is optional, not required. Whenever the logo IS "
            "shown, the logo mark (the wordmark letters and the starburst) is "
            "sacred: reproduce it exactly, keeping its original colours (starburst "
            "orange #FF8700). Never recolour, restyle, distort, stretch, rotate, "
            "or redraw the logo mark — do NOT tint it to match the background. "
            "Place the logo mark cleanly, with no added circle, disc, or shape "
            "behind it. Keep clear space around the logo.\n"
        )
        if logo_notes.strip():
            brief += f"Logo usage notes:\n{logo_notes.strip()}\n"
        brief += "\n"
    if platform:
        brief += f"=== {platform.upper()} ORDER NOW BUTTON ===\n"
        if no_button:
            brief += (
                f"Do NOT place any Order Now button or CTA button on this banner. "
                f"{platform} supplies its own call-to-action outside the creative, "
                "so the banner must not bake in any button — leave it out "
                "entirely.\n"
            )
            if composite:
                # Overrides any "Order Now" pill described in the composition above.
                brief += (
                    "This overrides the composition above: render NO Order Now "
                    "pill, button, or call-to-action of any kind.\n"
                )
        elif has_button:
            brief += (
                f"The official {platform} Order Now button is attached as a "
                "reference image.\n"
                "MANDATORY: The provided Order Now button must be placed in the "
                "lower portion of the banner (bottom ~30%, within the safe zone). "
                "Reproduce the button EXACTLY as provided — same shape, same "
                "colours, same text, same style. Do NOT redraw, restyle, recolour, "
                "resize disproportionately, or reinterpret it. Treat it with the "
                "same fidelity as the product packaging: it is a fixed asset to be "
                "placed, not redesigned.\n"
            )
        elif composite:
            # Strict-composite platforms draw their CTA per the composition brief
            # above (e.g. Blinkit's white "Order Now" pill); no empty-space note.
            brief += (
                f"Render the {platform} call-to-action as described in the "
                "composition above — do not leave it out and do not add any "
                "second button.\n"
            )
        else:
            brief += (
                f"Do NOT invent or draw an Order Now button for {platform}. "
                "Follow the rules below — typically leave clean, empty space so a "
                "designer can drop in the official button afterwards.\n"
            )
        if platform_notes.strip() and not no_button:
            brief += f"{platform} button rules to follow exactly:\n{platform_notes.strip()}\n"
        brief += "\n"
    if product_roles:
        brief += "=== PRODUCT IMAGES (attached) ===\n"
        if "packaging" in product_roles:
            brief += (
                "PACKAGING: reproduce the product pack EXACTLY as shown — it is the "
                "hero of the banner. Never redraw, restyle, recolour, or alter the "
                "pack.\n"
            )
        if "styling" in product_roles:
            brief += (
                "STYLING / MOOD: use ONLY as a lighting and mood reference — match "
                "its richness, warmth, and photographic feel. Do NOT copy it "
                "literally and do NOT reproduce its background.\n"
            )
        if "pieces" in product_roles:
            brief += (
                "PRODUCT PIECES: loose product to use as appetite elements — place "
                "tastefully to add richness, without cluttering or obscuring the "
                "pack.\n"
            )
        brief += "\n"
    if has_design_elements:
        brief += "=== OPTIONAL DESIGN ELEMENTS ===\n"
        brief += (
            "The attached design elements are a palette you MAY draw from if they "
            "genuinely improve the banner. You are NOT required to use any of them. "
            "Use them sparingly, at the edges only, and only where they serve the "
            "design. A clean banner with zero design elements is better than a "
            "cluttered one. When used, they may be recoloured to suit the banner's "
            "palette.\n"
        )
        if design_elements_bw:
            brief += (
                "These elements are provided in black & white; recolour any you "
                "choose to use so they suit the banner's palette.\n"
            )
        brief += "\n"
    if carousel_match:
        brief += (
            "=== CAROUSEL STYLE MATCH ===\n"
            "This banner is ONE page of a multi-product carousel set. An additional "
            "reference image of the FIRST banner in the set is attached. Match the "
            "colour scheme, background style, layout, and composition of that "
            "reference as closely as possible — only the product and its copy "
            "change. Keep the same format and feel so the pages read as a matched "
            "set.\n\n"
        )
    brief += (
        "=== STYLE REFERENCES ===\n"
        "The attached reference banners show GO DESi's visual style. Match their "
        "colour, mood, energy, and general composition. Do NOT copy their specific "
        "decorative elements or layouts. They are style guidance, not templates to "
        "replicate.\n\n"
        "Output: a single polished banner image.\n"
    )
    return brief


def assemble_payload(
    *,
    brand_rules: str,
    category: str,
    sku: str,
    variant: str | None,
    user_prompt: str,
    size_label: str,
    dimensions,
    banner_copy: str,
    copy_mode: str,
    logo_image: bytes | None,
    logo_notes: str,
    include_logo: bool,
    design_elements: list,   # list[(label, bytes)]
    reference_images: list,  # list[(label, bytes)]
    product_images: list,    # list[{"role", "data", "label"}]
    platform: str,
    platform_notes: str,
    platform_button: bytes | None,
    no_button: bool = False,
    design_elements_bw: bool = True,
    carousel_reference: bytes | None = None,
    reserve_top: bool = False,
    composite: dict | None = None,
) -> dict:
    """Build the brief + labelled image list for one generation.

    Returns {brief, images: [{role, label, data}]}. Per-type and total image
    caps (config.MAX_*) are applied here, with essentials kept first.

    When `composite` is set (a strict-compositing platform), the model is asked
    to render only the CONTENT frame (safe_area x scale). The brief's declared
    size/label are swapped to that content frame; the caller composites the
    result onto the padded final canvas afterwards with composite_final().
    """
    if composite:
        cw, ch = composite["content_size"]
        dimensions = (cw, ch)
        size_label = f"{composite['platform']} content frame ({cw}x{ch})"
    # When the logo toggle is OFF, do not send the logo image at all — the brief
    # tells the model to use only the pack's printed logo.
    send_logo = logo_image if include_logo else None
    # When the platform bakes in no button, never send the button image.
    send_button = None if no_button else platform_button

    # Partition selected product images by role — Packaging is the hero and has
    # the highest priority in the image cap.
    packaging = [p for p in product_images if p.get("role") == "packaging"]
    styling = [p for p in product_images if p.get("role") == "styling"]
    pieces = [p for p in product_images if p.get("role") == "pieces"]
    product_roles = {p.get("role") for p in (packaging + styling + pieces)}

    brief = build_brief(
        brand_rules,
        category,
        sku,
        variant,
        user_prompt,
        size_label,
        dimensions,
        banner_copy=banner_copy,
        copy_mode=copy_mode,
        logo_notes=logo_notes,
        has_logo=bool(send_logo),
        include_logo=include_logo,
        platform=platform,
        platform_notes=platform_notes,
        has_button=bool(send_button),
        no_button=no_button,
        design_elements_bw=design_elements_bw,
        has_design_elements=bool(design_elements),
        product_roles=product_roles,
        carousel_match=bool(carousel_reference),
        reserve_top=reserve_top,
        composite=composite,
    )

    _role_display = {
        "packaging": "Packaging (hero)",
        "styling": "Styling reference",
        "pieces": "Product pieces",
    }

    # Essentials are must-keeps and are NEVER trimmed by the image cap: the
    # packaging (hero) shot, the brand logo (when shown), and the platform Order
    # Now button. Styling/pieces product images come next, then the optional
    # supporting images (references, design elements) which trim first.
    essentials: list[dict] = []
    for p in packaging:
        essentials.append({"role": "Product shot", "label": p.get("label") or "Packaging", "data": p["data"]})
    # The first carousel banner is a must-keep style reference for later pages.
    if carousel_reference:
        essentials.append({"role": "Carousel style match", "label": "First carousel page", "data": carousel_reference})
    if send_logo:
        essentials.append({"role": "Logo", "label": "Brand logo", "data": send_logo})
    if send_button:
        essentials.append({"role": "Platform button", "label": f"{platform} Order Now button", "data": send_button})

    supporting: list[dict] = []
    for p in styling + pieces:
        label = p.get("label") or _role_display.get(p.get("role"), "Product image")
        supporting.append({"role": _role_display.get(p.get("role"), "Product image"), "label": label, "data": p["data"]})

    optional: list[dict] = []
    for label, data in list(reference_images)[: config.MAX_REFERENCES_PER_CALL]:
        optional.append({"role": "Reference banner", "label": label, "data": data})
    for label, data in list(design_elements)[: config.MAX_DESIGN_ELEMENTS_PER_CALL]:
        optional.append({"role": "Design element", "label": label, "data": data})

    remaining = max(0, config.MAX_TOTAL_IMAGES - len(essentials))
    images = essentials + (supporting + optional)[:remaining]

    return {"brief": brief, "images": images}


# Transient Gemini errors worth retrying (server overloaded, deadline expired,
# rate limited). These are per-request and usually clear on a second try.
_RETRYABLE_MARKERS = ("503", "unavailable", "deadline", "overloaded", "500", "internal", "429", "rate limit", "resource exhausted")
_MAX_ATTEMPTS = 4


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in _RETRYABLE_MARKERS)


def _generate(parts: list) -> bytes:
    """Call the image model with retries + exponential backoff on transient errors."""
    client = _client()
    model = config.MODELS[config.ACTIVE_MODEL]
    delay = 2.0
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=parts,
                config=types.GenerateContentConfig(response_modalities=["image"]),
            )
            return _extract_image(response)
        except Exception as exc:
            if attempt >= _MAX_ATTEMPTS or not _is_retryable(exc):
                raise
            time.sleep(delay)
            delay *= 2


def generate_from_payload(brief: str, images: list) -> bytes:
    """Send an already-assembled payload (from assemble_payload) to Gemini."""
    parts = [types.Part(text=brief)]
    for item in images:
        parts.append(_image_part(item["data"]))
    return _generate(parts)


def edit_banner(previous_image: bytes, edit_instruction: str) -> bytes:
    parts = [
        types.Part(
            text=(
                "Here is the current banner. Apply ONLY this change, keeping "
                "everything else the same and staying fully on-brand:\n\n"
                f"{edit_instruction.strip()}"
            )
        ),
        _image_part(previous_image),
    ]
    return _generate(parts)


def _decode_data_url(data_url: str) -> bytes:
    if not data_url.startswith("data:"):
        raise ValueError("Invalid data URL")
    parts = data_url.split(",", 1)
    if len(parts) != 2:
        raise ValueError("Invalid data URL")
    return base64.b64decode(parts[1])


def _extract_image(response) -> bytes:
    def _check_parts(parts):
        for part in parts or []:
            inline_data = getattr(part, "inline_data", None)
            if inline_data and getattr(inline_data, "data", None):
                return inline_data.data
            text = getattr(part, "text", None)
            if text and "data:image" in text:
                data_url = text[text.index("data:image") :]
                return _decode_data_url(data_url)
        return None

    if getattr(response, "candidates", None):
        for candidate in response.candidates:
            content = getattr(candidate, "content", None)
            result = _check_parts(getattr(content, "parts", None) if content is not None else None)
            if result:
                return result
            result = _check_parts(getattr(candidate, "parts", None))
            if result:
                return result

    text = getattr(response, "text", None)
    if text and "data:image" in text:
        data_url = text[text.index("data:image") :]
        return _decode_data_url(data_url)

    raise RuntimeError(
        "No image was returned by the model. This usually means the prompt was "
        "refused or the model name is wrong. Try rephrasing, or switch ACTIVE_MODEL "
        "in config.py."
    )


# ============================================================================
# STRICT-PLATFORM COMPOSITING (e.g. Blinkit Listing Spotlight)
# The model renders ONLY the content frame; the mandatory padding is added here
# in code so it is GUARANTEED empty, whatever the model does.
# ============================================================================
def composite_spec(platform: str) -> dict | None:
    """Resolve config.PLATFORM_COMPOSITE for a platform into a ready-to-use spec,
    or None if the platform uses the normal (non-composited) flow.

    Adds derived sizes so callers never recompute them:
      content_size = safe_area * scale   (what the model generates)
      canvas_size  = final_size * scale  (the padded hi-res canvas)
    """
    raw = config.PLATFORM_COMPOSITE.get(platform)
    if not raw:
        return None
    scale = int(raw.get("scale", 4))
    fw, fh = raw["final_size"]
    sw, sh = raw["safe_area"]
    return {
        "platform": platform,
        "scale": scale,
        "final_size": (fw, fh),
        "safe_area": (sw, sh),
        "content_size": (sw * scale, sh * scale),
        "canvas_size": (fw * scale, fh * scale),
        "fallback_bg": raw.get("fallback_bg", "#FFFFFF"),
        "composition_brief": raw.get("composition_brief", ""),
    }


def _hex_to_rgb(value: str) -> tuple:
    value = (value or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if len(value) != 6:
        return (255, 255, 255)
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (255, 255, 255)


def _edge_spread(content: "Image.Image") -> float:
    """Mean absolute deviation of the content's border ring from its median colour.

    Low => the outer ring is a clean single background that can be extended
    seamlessly. High => content bleeds to the edge / the edge is busy, so
    stretching it outward would smear objects into the padding.
    """
    img = content.convert("RGB")
    w, h = img.size
    px = img.load()
    samples = []
    step_x = max(1, w // 64)
    step_y = max(1, h // 64)
    for x in range(0, w, step_x):
        samples.append(px[x, 0])
        samples.append(px[x, h - 1])
    for y in range(0, h, step_y):
        samples.append(px[0, y])
        samples.append(px[w - 1, y])
    if not samples:
        return 0.0
    n = len(samples)
    mid = n // 2
    med = tuple(sorted(s[c] for s in samples)[mid] for c in range(3))
    return sum(
        abs(s[0] - med[0]) + abs(s[1] - med[1]) + abs(s[2] - med[2]) for s in samples
    ) / (3 * n)


def _extend_edges(canvas: "Image.Image", content: "Image.Image", off_x: int, off_y: int) -> None:
    """Grow the content's own edge pixels outward to fill the padding, in place.

    Each padding band is the adjacent 1px edge strip stretched out (clamp/
    replicate), so the background continues past the safe area with no seam —
    the boundary pixels match the content exactly. Because all real content is
    kept inside the safe area, only background gets extended.
    """
    safe_w, safe_h = content.size
    canvas_w, canvas_h = canvas.size
    right_x = off_x + safe_w
    bottom_y = off_y + safe_h
    if off_x > 0:
        canvas.paste(content.crop((0, 0, 1, safe_h)).resize((off_x, safe_h)), (0, off_y))
    if canvas_w - right_x > 0:
        canvas.paste(content.crop((safe_w - 1, 0, safe_w, safe_h)).resize((canvas_w - right_x, safe_h)), (right_x, off_y))
    if off_y > 0:
        canvas.paste(content.crop((0, 0, safe_w, 1)).resize((safe_w, off_y)), (off_x, 0))
    if canvas_h - bottom_y > 0:
        canvas.paste(content.crop((0, safe_h - 1, safe_w, safe_h)).resize((safe_w, canvas_h - bottom_y)), (off_x, bottom_y))
    # Four corners: the corner pixel, extended to fill the corner rectangle.
    canvas.paste(content.getpixel((0, 0)), (0, 0, off_x, off_y))
    canvas.paste(content.getpixel((safe_w - 1, 0)), (right_x, 0, canvas_w, off_y))
    canvas.paste(content.getpixel((0, safe_h - 1)), (0, bottom_y, off_x, canvas_h))
    canvas.paste(content.getpixel((safe_w - 1, safe_h - 1)), (right_x, bottom_y, canvas_w, canvas_h))


def _png_bytes(img: "Image.Image") -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def composite_final(content_png: bytes, spec: dict) -> dict:
    """Place the generated content into the centred safe area and extend its
    background out to the canvas edges so the banner reads as ONE seamless image.

    All real content (pack, text, CTA, logo) exists only inside the safe area —
    that stays guaranteed. The padding is not a flat block: it is the content's
    own background stretched outward (a natural vignette), so there is no
    visible inner-banner box. Returns:
      {"full_res": <canvas_size PNG>, "deliverable": <final_size PNG>}
    """
    canvas_w, canvas_h = spec["canvas_size"]
    safe_w, safe_h = spec["content_size"]
    final_w, final_h = spec["final_size"]
    scale = int(spec.get("scale", 4))

    content = Image.open(io.BytesIO(content_png)).convert("RGB")
    # The model may return a slightly off size; force it to the exact safe area.
    if content.size != (safe_w, safe_h):
        content = content.resize((safe_w, safe_h), Image.LANCZOS)

    off_x = (canvas_w - safe_w) // 2
    off_y = (canvas_h - safe_h) // 2

    if _edge_spread(content) <= 55:
        # Clean edges: extend the background outward, then soften only the
        # padding so any stretch banding blends into a continuous background.
        canvas = Image.new("RGB", (canvas_w, canvas_h))
        canvas.paste(content, (off_x, off_y))
        _extend_edges(canvas, content, off_x, off_y)
        canvas = canvas.filter(ImageFilter.GaussianBlur(max(2, scale * 2)))
        # Put the crisp content back on top; the blurred padding meets it
        # seamlessly because the colours are continuous across the boundary.
        canvas.paste(content, (off_x, off_y))
    else:
        # Busy / edge-bleeding content: stretching would smear objects into the
        # padding, so fall back to a flat on-brand fill (deterministic, clean).
        canvas = Image.new("RGB", (canvas_w, canvas_h), _hex_to_rgb(spec.get("fallback_bg", "#FFFFFF")))
        canvas.paste(content, (off_x, off_y))

    deliverable = canvas.resize((final_w, final_h), Image.LANCZOS)
    return {"full_res": _png_bytes(canvas), "deliverable": _png_bytes(deliverable)}
