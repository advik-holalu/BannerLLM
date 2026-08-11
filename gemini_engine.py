"""
gemini_engine.py — all the talking-to-Gemini logic lives here.

You should not need to edit this file. It does three things:
  1. Builds a brand-aware prompt from your rules + the user's request.
  2. Calls Gemini's image model with reference images + product shot.
  3. Returns the generated image bytes (and supports conversational edits).
"""

import base64
import os

import config
from google.genai import types
import google.genai as genai


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
    logo_notes: str = "",
    has_logo: bool = False,
    include_logo: bool = True,
    platform: str = "",
    platform_notes: str = "",
    has_button: bool = False,
    no_button: bool = False,
    design_elements_bw: bool = False,
    has_design_elements: bool = False,
) -> str:
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
    brief += (
        "=== THE CREATIVE REQUEST (interpret this; do not print it on the banner) ===\n"
        f"{user_prompt.strip() or f'A clean, appetising, on-brand banner featuring {sku}.'}\n\n"
    )
    if banner_copy.strip():
        brief += (
            "=== BANNER COPY (render exactly as written, do not change) ===\n"
            f"{banner_copy.strip()}\n\n"
        )
    else:
        brief += (
            "=== BANNER COPY ===\n"
            "No exact copy was provided. You may write ONE short headline that "
            "follows the brand tone and the approved example headlines above. Keep "
            "it legible at thumbnail size.\n\n"
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
            "ONLY the circular disc behind the logo may change colour to suit the "
            "banner. Keep clear space around the logo.\n"
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
        else:
            brief += (
                f"Do NOT invent or draw an Order Now button for {platform}. "
                "Follow the rules below — typically leave clean, empty space so a "
                "designer can drop in the official button afterwards.\n"
            )
        if platform_notes.strip() and not no_button:
            brief += f"{platform} button rules to follow exactly:\n{platform_notes.strip()}\n"
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
    brief += (
        "=== STYLE REFERENCES ===\n"
        "These show GO DESi's visual style. Match their colour, mood, energy, and "
        "general composition. Do NOT copy their specific decorative elements or "
        "layouts. They are style guidance, not templates to replicate.\n"
        "The provided product image also shows GO DESi's photoshoot styling — "
        "match its lighting quality, richness, warmth, and surface/mood. Reproduce "
        "the pack exactly, but carry over the premium, appetising photographic "
        "feel into the banner.\n\n"
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
    logo_image: bytes | None,
    logo_notes: str,
    include_logo: bool,
    design_elements: list,   # list[(label, bytes)]
    reference_images: list,  # list[(label, bytes)]
    product_image: bytes | None,
    product_label: str,
    platform: str,
    platform_notes: str,
    platform_button: bytes | None,
    no_button: bool = False,
    design_elements_bw: bool = True,
) -> dict:
    """Build the brief + labelled image list for one generation.

    Returns {brief, images: [{role, label, data}]}. Per-type and total image
    caps (config.MAX_*) are applied here, with essentials kept first.
    """
    # When the logo toggle is OFF, do not send the logo image at all — the brief
    # tells the model to use only the pack's printed logo.
    send_logo = logo_image if include_logo else None
    # When the platform bakes in no button, never send the button image.
    send_button = None if no_button else platform_button

    brief = build_brief(
        brand_rules,
        category,
        sku,
        variant,
        user_prompt,
        size_label,
        dimensions,
        banner_copy=banner_copy,
        logo_notes=logo_notes,
        has_logo=bool(send_logo),
        include_logo=include_logo,
        platform=platform,
        platform_notes=platform_notes,
        has_button=bool(send_button),
        no_button=no_button,
        design_elements_bw=design_elements_bw,
        has_design_elements=bool(design_elements),
    )

    # Essentials are must-keeps and are NEVER trimmed by the image cap: the
    # product shot, the brand logo (when shown), and the platform Order Now
    # button. Only the optional supporting images (references, design elements)
    # are trimmed to fit the cap.
    essentials: list[dict] = []
    if product_image:
        essentials.append({"role": "Product shot", "label": product_label, "data": product_image})
    if send_logo:
        essentials.append({"role": "Logo", "label": "Brand logo", "data": send_logo})
    if send_button:
        essentials.append({"role": "Platform button", "label": f"{platform} Order Now button", "data": send_button})

    optional: list[dict] = []
    for label, data in list(reference_images)[: config.MAX_REFERENCES_PER_CALL]:
        optional.append({"role": "Reference banner", "label": label, "data": data})
    for label, data in list(design_elements)[: config.MAX_DESIGN_ELEMENTS_PER_CALL]:
        optional.append({"role": "Design element", "label": label, "data": data})

    keep_optional = max(0, config.MAX_TOTAL_IMAGES - len(essentials))
    images = essentials + optional[:keep_optional]

    return {"brief": brief, "images": images}


def generate_from_payload(brief: str, images: list) -> bytes:
    """Send an already-assembled payload (from assemble_payload) to Gemini."""
    client = _client()
    model = config.MODELS[config.ACTIVE_MODEL]
    parts = [types.Part(text=brief)]
    for item in images:
        parts.append(_image_part(item["data"]))

    response = client.models.generate_content(
        model=model,
        contents=parts,
        config=types.GenerateContentConfig(response_modalities=["image"]),
    )
    return _extract_image(response)


def edit_banner(previous_image: bytes, edit_instruction: str) -> bytes:
    client = _client()
    model = config.MODELS[config.ACTIVE_MODEL]
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
    response = client.models.generate_content(
        model=model,
        contents=parts,
        config=types.GenerateContentConfig(response_modalities=["image"]),
    )
    return _extract_image(response)


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
