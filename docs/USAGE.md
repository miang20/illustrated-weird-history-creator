# Usage and deployment

## Manual script is the primary workflow
1. Open the Streamlit app and paste your complete narration into **MANUAL SCRIPT**.
2. Give the project a title, then select the target runtime (5–8 minutes), 18/24/30/36 visual scene frames, narrator, and resolution.
3. Check the displayed word count and estimated duration. A mismatch warning means you should adjust the script or target before spending render time.
4. Choose **Render this script → final MP4**. With a configured `GITHUB_TOKEN` secret the app dispatches GitHub Actions; otherwise it links to the manual workflow.
5. When the workflow completes, download the `weird-history-mp4` artifact.

Scene labels such as `## SCENE 1 — THE HOOK` are removed from spoken narration. Use blank lines to separate speech beats. The text is not rewritten or expanded by an AI script generator.

## Script preview without rendering
Open Actions → **Preview Manual Script**, paste the narration, choose the target duration, and run it. The workflow checks parsed word count and uploads `script.txt` plus `report.json`; it does not download image or voice models.

## Image preview
Open Actions → **Preview Scene Images** to generate six still images and inspect `prompts.txt` and `report.json`. Each scene records its prompt length. This workflow makes no voice or video. Full rendering remains manual/opt-in; do not run it until the previews are approved.

## Universal visual style
All niches load `config/universal_style.json`. The fixed character is a simple 2D hand-drawn stickman with a round white head, thick black outline, two dot eyes, simple mouth, thin black stick arms and legs, clean bold black outlines, and a pure white background. Muted beige/brown/tan/black is allowed only on clothing and a few props; all other elements are black line art on white. No gradients, shading, textures, colored backgrounds, text, 3D, or photorealism.

Niche JSONs contain only `display_name`, `fixed_seed`, `environment_hints`, `action_directions`, `default_voice`, `caption_style`, and `clothing_hint`. Each action direction centers one main stickman. Other people or animals appear only when needed by the narration and must also be simple stickman/line-art. Niche settings cannot redefine the character or palette.

The final prompt combines the shared style sentence, clothing hint, one shortened key sentence from the narration beat, short environment hint, and the short tail “No text, no gradients, no shading.” Stored narration remains unchanged. Prompts are capped at 900 characters; length is written to `prompts.txt` and each image's manifest/report entry.

## Image providers and cache
- **Pollinations (default)** requests free 1280×720 Flux images without an API key. Anonymous service availability, speed, and quality vary.
- **Local fallback** retains SD-Turbo and Tiny-SD exactly as the free fallback models.
- Pollinations uses a 90-second timeout and rate limiting. If the provider reports a URL-length error, it retries once with a shorter prompt before falling back.
- Images are cached in `.image-cache/` using a SHA-256 key over provider, seed, and exact prompt. New prompts produce new keys.
- Gentle cleanup autocontrasts the image and changes near-white background pixels to pure white while retaining color and anti-aliased edges. The legacy hard 1-bit threshold filter is optional through `"postprocess": true`; the default is off.
- No paid AI provider or API key is required. Pollinations may be unavailable or rate-limited; local CPU inference can be slow.

## Free-tier and compute notes
GitHub standard runners are CPU-only. A full render can take a long time. Lightweight CI tests do not prove successful image generation, voice quality, or final MP4 rendering; do not start a full render until explicitly requested.
