# CLAUDE.md — GO DESi Banner Studio

Project context for Claude Code. Read this before making changes.

## What this is
A Streamlit app that generates on-brand marketing banners for GO DESi
(Indian sweets/snacks brand) for q-commerce ad slots (Blinkit, Zepto) and D2C.
Users pick a category + SKU + size, prompt what they want, get a banner from
Google's Gemini image model, download it as PNG, and refine it conversationally.

Primary users: GO DESi growth team (non-designers) and designers speeding up
repetitive banner work. Keep the UI simple and non-technical.

## Architecture (how the files fit together)
- `app.py` — the Streamlit UI and all screens (Create / Manage SKUs / Brand rules).
  This is the only file with user-facing UI. Four screens, routed by sidebar.
- `gemini_engine.py` — all Gemini API calls. `build_brief()`, `generate_banner()`,
  `edit_banner()` (conversational refine), `_extract_image()`. No UI here.
- `assets.py` — manages catalog and rule persistence, and reads/writes images
  through the cloud storage backend.
- `storage.py` — Google Cloud Storage helper. Uploads and downloads files from
  bucket folders: `skus/`, `design_elements/`, `references/`, and `generated/`.
- `config.py` — THE settings file. Model choice, banner sizes, prompt templates,
  category defaults, and asset file paths. This is meant to be human-edited;
  keep it readable and commented.
- `brand_assets/` — local persistence for catalog.json and editor rule files.
  Images are stored in GCS, not in the local `brand_assets` subfolders.

## Data flow for one generation
user picks category/SKU/size/prompt
  -> assets.load_brand_rules() + load_reference_images() + load_sku_image()
  -> engine.build_brief() assembles the text brief
  -> engine.generate_banner() sends brief + ref images + product shot to Gemini
  -> PNG bytes returned, shown, downloadable
  -> "Apply change" -> engine.edit_banner() sends previous image + instruction

## Hard rules — do NOT break these
- NEVER hardcode the API key in any file. It comes from the GEMINI_API_KEY
  environment variable / Streamlit secret only. `.streamlit/secrets.toml` is
  git-ignored and must stay that way.
- NEVER use localStorage/sessionStorage — irrelevant here, it's Streamlit.
- Keep `config.py` the single place a non-coder edits for normal changes
  (sizes, templates, model). If you add a tunable, put it there with a comment.
- Model strings live ONLY in config.py MODELS dict. Don't scatter them.
- The two valid models are gemini-2.5-flash-image and
  gemini-3.1-flash-image-preview. If a call fails, suspect the model name first.

## Deployment
Streamlit Community Cloud, deployed from a private GitHub repo. The key is set
as a Streamlit secret in the app's Advanced settings, NOT committed. Editing a
file on GitHub auto-redeploys.

## Known limitations (by design — this is "Path A")
- Output is a flat PNG. Designers finish in their own tool. This is expected.
- Brand-match quality depends mostly on the number/quality of reference banners
  in brand_assets/references/. If output looks generic, add more references —
  that's the fix, not prompt-wrangling.

## When making changes
- Prefer small, reviewable diffs.
- After editing, sanity-check imports compile: `python -m py_compile *.py`.
- Test non-API logic without a key (catalog, brief building) before assuming
  an API problem.
- Don't add dependencies casually; requirements.txt is intentionally tiny
  (streamlit, openai).
