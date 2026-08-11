"""
GO DESi Banner Studio — central configuration.

This is the ONE file you edit to change behaviour. No code knowledge needed:
just change the text between the quotes.
"""

# ============================================================================
# 1. WHICH GEMINI MODEL TO USE
# ============================================================================
MODELS = {
    "flash_2_5": "gemini-2.5-flash-image",
    "flash_3_1": "gemini-3.1-flash-image-preview",
}

ACTIVE_MODEL = "flash_3_1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


# ============================================================================
# 2. BANNER SIZES  (label shown in app  ->  pixel dimensions)
# ============================================================================
BANNER_SIZES = {
    "Tall vertical (1080 x 1920)": (1080, 1920),
    "Square (1080 x 1080)": (1080, 1080),
    "Landscape wide (1200 x 628)": (1200, 628),
    "Banner strip (1200 x 400)": (1200, 400),
    "Story / Reel (1080 x 1920)": (1080, 1920),
}


# ============================================================================
# 3. PREDEFINED PROMPT TEMPLATES
# ============================================================================
# Each template carries ONLY what is unique to that template's commercial job.
# Everything about background, hierarchy, clean space, and no-clutter lives in
# CORE_RULES (below) — never duplicate it here. Keep these short.
PROMPT_TEMPLATES = {
    "Festive / Occasion": (
        "Make {sku} feel like the right sweet for the occasion, instantly. "
        "Convey the occasion through warm colour and mood."
    ),
    "New Launch": (
        "Announce {sku} as newly launched. The pack is the news — include a clear "
        "NEW badge."
    ),
    "Offer / Discount": (
        "Sell the deal for {sku}. The discount number leads and is the largest "
        "element; the pack sits beside it as proof."
    ),
    "Everyday / Brand": (
        "Make someone hungry for {sku}. Show the actual sweet out of the pack — "
        "textured, fresh, appetising — beside the pack."
    ),
    "Premium / Gifting": (
        "Make {sku} feel worth gifting. Restraint signals value — keep it "
        "understated and elegant."
    ),
}


# ============================================================================
# 3b. CORE RULES  (Tier 1)
# The single source of truth for the rules that apply to EVERY generation.
# Do NOT restate any of this in PROMPT_TEMPLATES or the Designer/Copywriter
# screens — this is the only place these rules live. Rendered in the brief
# under one "CORE RULES" heading.
# ============================================================================
CORE_RULES = (
    "These override any decorative, \"vibrant\", \"festive\", or \"busy\" "
    "language in the user's prompt.\n\n"
    "INSTRUCTION INTEGRITY\n"
    "- Never render any instruction, rule, constraint, or meta-text as visible "
    "text on the banner. The only text on the banner is the copy provided in the "
    "copy input, plus the CTA button.\n"
    "- Never invent, imply, or display any discount, offer, percentage, price, or "
    "claim not explicitly given. Never repurpose numbers or text from the "
    "packaging (e.g. \"61% Cashew\") as an offer or discount.\n"
    "- Never invent product claims, ingredients, or benefits not stated in the "
    "prompt or visible on the pack.\n\n"
    "PRODUCT FIDELITY\n"
    "- Reproduce the product packaging exactly as shown in the reference image. "
    "Never redraw, restyle, recolour, or alter pack artwork or text.\n"
    "- Never obstruct, overlap, or cover any part of the product pack. No props, "
    "gift boxes, ingredients, or graphics in front of or on top of the pack. Show "
    "the pack whole and fully visible, including all callouts, badges, claims, and "
    "disclaimer text printed on it.\n\n"
    "COLOUR\n"
    "- Derive the banner's colour palette primarily FROM THE PRODUCT PACKAGING. "
    "Echo the pack's dominant colours so the banner and the product feel like one "
    "cohesive piece. This is the main colour rule.\n"
    "- The GO DESi brand palette is a reference pool to draw from when a colour "
    "isn't coming from the pack — it is NOT a rigid requirement. Other colours are "
    "allowed if they complement the packaging.\n"
    "- The background colour should be drawn from or complement the pack's own "
    "colours, chosen to make the pack stand out.\n\n"
    "BACKGROUND\n"
    "- The background must be clean and uncluttered so the pack stands out — but "
    "it should have DEPTH and richness, not look flat or sterile. A solid colour, "
    "a soft gradient, a subtle two-tone, or a lightly textured surface are all "
    "good. Rich, warm, professional lighting.\n"
    "- Dimensional appetite elements ARE encouraged when they serve the product: "
    "a ghee splash, drizzle, loose product pieces with real shadows, a subtle "
    "premium surface. These add appetite and richness.\n"
    "- What's still forbidden: busy photographic scenes with unrelated props (no "
    "clocks, books, random objects), and traditional festive clutter (no rangoli, "
    "mandalas, marigolds, diyas). Richness comes from lighting, depth, and "
    "appetite — NOT from clutter or clichés.\n\n"
    "EXECUTION QUALITY\n"
    "- The banner must look like a professional product photoshoot, not a flat "
    "graphic. Use rich, directional lighting, real shadows under the pack and "
    "pieces, dimensionality, and appetising warmth. Make the product look premium "
    "and mouth-watering.\n"
    "- Avoid a flat, sticker-like, cut-out look. The pack and pieces should feel "
    "grounded with realistic shadows and depth.\n\n"
    "LOGO\n"
    "- The GO DESi logo mark is sacred and must NEVER be altered. Reproduce it "
    "exactly as provided: the wordmark and starburst keep their exact original "
    "colours (starburst orange #FF8700). Never recolour, restyle, distort, or "
    "redraw the logo mark.\n"
    "- ONLY the circular background disc behind the logo may change colour to suit "
    "the banner. The logo mark itself (letters + starburst) never changes.\n\n"
    "THE PHONE TEST\n"
    "- This banner appears small on a phone, scrolled past in under two seconds, "
    "beside competitors. If it doesn't work at thumbnail size, it has failed.\n"
    "- The product pack is the hero — the largest, highest-contrast element.\n"
    "- The area directly behind and around the pack must be clean, plain, and "
    "low-contrast. Never place dense patterns, rangoli, mandalas, or busy motifs "
    "behind or overlapping the pack.\n"
    "- Decoration lives at the edges/periphery only. The centre belongs to the "
    "product.\n"
    "- Contrast, not clutter, creates depth. Separate the pack from its "
    "background with clean contrast and lighting.\n"
    "- Loudness resolution: the pack, colour palette, and copy carry the energy — "
    "bold, warm, high-contrast. The background stays calm and uncluttered. Never "
    "resolve \"fun and loud\" by filling the frame with decoration.\n"
    "- Maintain 30-40% clean negative space. Do not fill it with decoration.\n\n"
    "BRAND IDENTITY — WHAT \"FUN AND LOUD\" MEANS\n"
    "- GO DESi is modern, playful, quirky, and clean. It is NOT traditional-ornate "
    "Indian mithai branding.\n"
    "- Never use generic Indian-festive visual cliches: no marigold garlands, no "
    "diyas, no rangoli, no mandalas, no ornate gold filigree, no temple or pooja "
    "imagery, no Haldiram's-style traditional sweet-shop aesthetic.\n"
    "- Festivity, when needed, is conveyed through warm colour and playful GO DESi "
    "elements — not through traditional religious or ceremonial motifs.\n\n"
    "COPY RENDERING\n"
    "- Render the provided copy exactly as given. Do not rewrite, extend, or "
    "embellish it.\n"
    "- Render it legibly — it must read at thumbnail size on a phone. Legibility "
    "beats style.\n"
    "- Headline font: bold, rounded, friendly sans-serif.\n\n"
    "HEADLINE STYLING\n"
    "- Render the headline in a dynamic, layered GO DESi style — not one flat "
    "uniform line. Vary weight, size, and style across the lines of the headline "
    "for visual interest and hierarchy.\n"
    "- Emphasise the key phrase (e.g. the flavour or the hero benefit) with a "
    "larger, bolder, or more playful treatment, while connecting words (like "
    "\"made with\", \"with\") can be smaller, lighter, or in a script/italic "
    "style.\n"
    "- Example of the intended feel: a headline like \"Creamy Peda made with Pure "
    "Milk\" would render \"Creamy Peda\" bold and playful, \"made with\" small and "
    "secondary, and \"Pure Milk\" large and emphasised — three distinct treatments "
    "in one headline.\n"
    "- Use bold, rounded, friendly fonts. Keep it highly legible at small mobile "
    "size. The layering adds energy but must never hurt readability.\n"
    "- Render the exact copy provided — only the styling/treatment varies, never "
    "the words."
)


# GO DESi brand palette. A FLEXIBLE reference pool the model may draw from when a
# colour is not coming from the product pack — never a rigid requirement (see the
# COLOUR rule in CORE_RULES). Surfaced in the brief as reference, not mandatory.
BRAND_PALETTE = [
    "#C1272D",
    "#FEBE2E",
    "#0F8A57",
    "#CA1D7A",
    "#954FC0",
    "#DA3031",
    "#E2632A",
    "#F7931D",
    "#E16528",
    "#000003",
    "#F6892B",
]


# ============================================================================
# 4. CATALOG / RULES FILES
# ============================================================================
# Categories created automatically when no catalog exists yet (fresh setup).
# Order here is the order new installs see them in.
DEFAULT_CATEGORIES = [
    "Namkeen",
    "Fruti Twist",
    "DESi POPz",
    "DESi Mints",
    "DESi Meetha",
    "DESi Gifting",
    "DESi Essentials",
]

# Q-commerce / delivery platforms the team designs banners for. Each platform
# has its own fixed "Order Now" button + placement rules (managed in the app,
# under Brand rules -> Platforms). The team can add more platforms in-app; this
# list is just the starting set.
DEFAULT_PLATFORMS = [
    "Blinkit",
    "Zepto",
    "Meta / Instagram",
]

# ----------------------------------------------------------------------------
# Per-platform FIXED SIZE. A platform listed here generates ONE banner at this
# exact size — the "Banner size" selector is hidden on the Create screen and no
# cropping happens. Each entry: (label, (width, height)).
# Platforms NOT listed here use the "Banner size" selector (Blinkit, Zepto).
# To pin another platform to a fixed size later, just add an entry here.
# ----------------------------------------------------------------------------
PLATFORM_FIXED_SIZE = {
    # Meta feed testing: a single 4:5 banner.
    "Meta / Instagram": ("4:5 feed (1080x1350)", (1080, 1350)),
    # Example: pin Blinkit/Zepto too by filling their exact sizes:
    # "Blinkit": ("Blinkit banner (208x520)", (208, 520)),
    # "Zepto":   ("Zepto banner (WxH)", (1080, 1080)),
}

# Platforms whose banners must NOT bake in an Order Now / CTA button — the ad
# platform supplies its own call-to-action. This is the DEFAULT "no Order Now
# button" state (toggle ON) for these platforms; it can be overridden per
# platform in Rules & Assets -> Platforms.
NO_BUTTON_PLATFORMS = [
    "Meta / Instagram",
]

# Old default categories from earlier versions. Used ONLY during migration to
# clean up empty leftovers — they are never recreated. Categories that still
# contain products are always kept, even if listed here.
LEGACY_DEFAULT_CATEGORIES = [
    "Indian Sweets",
    "Confectionary and Mints",
    "Snacks",
    "Gifting",
    "Others",
]

BRAND_ASSETS_DIR = "brand_assets"
REFERENCES_DIR = "brand_assets/references"
SKUS_DIR = "brand_assets/skus"
BRAND_RULES_FILE = "brand_assets/brand_rules.md"
DESIGNER_RULES_FILE = "brand_assets/designer_rules.md"
COPYWRITER_RULES_FILE = "brand_assets/copywriter_rules.md"
CATALOG_FILE = "brand_assets/catalog.json"

# ============================================================================
# 5. IMAGE CAP LIMITS
# ============================================================================
MAX_REFERENCES_PER_CALL = 3
MAX_DESIGN_ELEMENTS_PER_CALL = 2

# Hard cap on the TOTAL number of images sent to Gemini in one generation
# (product shot + logo + platform button + references + design elements).
# Too many images can dilute the signal and hurt quality — lower this to test.
# Priority when the cap trims: product shot, logo, platform button, then
# reference banners, then design elements.
MAX_TOTAL_IMAGES = 8

# Design elements are uploaded in black & white by convention, so the brief
# tells Gemini it may recolour the ones it chooses to use. Set False if you
# start uploading pre-coloured design elements.
DESIGN_ELEMENTS_ARE_BW = True
