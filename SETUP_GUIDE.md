# GO DESi Banner Studio — Setup Guide

A banner generator for the growth + design team. Pick a category and SKU,
prompt what you want, get an on-brand banner, refine it by chatting, download it.

This guide assumes **zero coding knowledge**. Follow it top to bottom.

---

## What you're setting up

```
You (browser)  →  Banner Studio website  →  Gemini image AI  →  banner
                         ↑
            your brand rules + reference banners + product shots
            (these make every banner look like GO DESi)
```

There are two one-time setup jobs: **(A)** get a Gemini API key, **(B)** put the
app online. After that, the team just uses a web link.

---

## PART A — Get your Gemini API key (5 minutes)

1. Go to **https://aistudio.google.com/apikey**
2. Sign in with a Google account (use a GO DESi account, not personal).
3. Click **Create API key**. Copy the long string it gives you. Keep it safe —
   treat it like a password.
4. **Set a spending cap so it can never surprise you:**
   - Go to **https://console.cloud.google.com/billing**
   - Open **Budgets & alerts → Create budget**
   - Set a monthly budget (e.g. **$20**) with email alerts at 50% / 90% / 100%.
   - At your volume (15–20 banners/month ≈ 100 generations) you'll spend
     roughly **$5–7/month**, so $20 is a comfortable ceiling.

> Note: image generation needs the **paid tier** enabled (add a billing card in
> Google Cloud). You still only pay per image — there's no subscription. The
> free tier alone won't generate images on the current models.

---

## PART B — Put the app online (Streamlit Community Cloud, free)

### B1. Put the code on GitHub
1. Make a free account at **https://github.com**.
2. Click **New repository** → name it `godesi-banner-studio` → set it to
   **Private** → Create.
3. On the new repo page, click **uploading an existing file**.
4. Drag in **everything from this folder** (app.py, config.py, the
   brand_assets folder, etc.). Commit.

   - ⚠️ Do **not** upload `secrets.toml` (your key). The `.gitignore` already
     prevents this — just don't add it manually.

### B2. Deploy on Streamlit Cloud
1. Go to **https://share.streamlit.io** and sign in with the same GitHub account.
2. Click **Create app → Deploy a public app from GitHub**.
3. Choose your `godesi-banner-studio` repo, branch `main`, main file `app.py`.
4. Before clicking deploy, open **Advanced settings → Secrets** and paste:
   ```
   GEMINI_API_KEY = "your-key-from-part-A"
   ```
5. Click **Deploy**. Wait ~2 minutes. You'll get a link like
   `https://godesi-banner-studio.streamlit.app`.

### B3. Restrict who can see it (optional but recommended)
- In your app's settings on Streamlit Cloud → **Sharing**, switch from public to
  **specific viewers** and add your team's emails. Now only they can open it.

**Done.** Share the link with the growth + design team.

---

## Loading your real brand assets (do this for good results)

The app works out of the box, but it gets *on-brand* only once you feed it your
real material. All of this lives in the `brand_assets` folder:

| What | Where | How |
|---|---|---|
| **Reference banners** (your best past ads) | `brand_assets/references/` | Drop 4–8 `.png`/`.jpg` files. These teach the AI your style. Most important step. |
| **Product shots** | `brand_assets/skus/` | One image per SKU, named after it, e.g. `coconut_laddu.png`. Keeps packaging accurate. |
| **Brand rules** | `brand_assets/brand_rules.md` | Plain-English do's and don'ts. Already filled with a starter — edit freely. |
| **Categories & SKUs** | managed **in the app** | Use the **Manage SKUs** screen. No files to touch. |

To add/update these after deploy: upload the files to the same place in your
GitHub repo (drag-and-drop on github.com), and Streamlit auto-redeploys.

---

## Switching the AI model

Open `config.py`, find `ACTIVE_MODEL`, and set it to either:
- `"flash_3_1"` — newer, slightly pricier, higher resolution (current default)
- `"flash_2_5"` — cheaper, proven

Generate the same banner on both once, keep whichever you like better.

---

## Trying it on your own laptop first (optional)

If you'd rather test before deploying:
1. Install Python 3.11+ from python.org.
2. In a terminal, inside this folder, run:
   ```
   pip install -r requirements.txt
   ```
3. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and paste
   your key inside.
4. Run:
   ```
   streamlit run app.py
   ```
   It opens in your browser at `localhost:8501`.

---

## If something breaks

- **"GEMINI_API_KEY is not set"** → you didn't add the secret in Streamlit Cloud
  (Part B2, step 4) or in your local `secrets.toml`.
- **"No image was returned"** → the prompt may have been refused, or the model
  name changed. Try rephrasing, or switch `ACTIVE_MODEL` in `config.py`.
- **Banners look generic / off-brand** → add more reference banners to
  `brand_assets/references/`. This is the single biggest quality lever.
- **App is slow to load first time** → free tier "sleeps" when idle and takes
  ~30 sec to wake. Normal.
- **Billing worry** → check the budget you set in Part A. You control the cap.
