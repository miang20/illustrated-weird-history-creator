# Savage Stickman Studio

Manual-script-first, free-first creator for long-form YouTube history, survival, mystery, and other documentary niches.

## Core workflow
- Paste your own narration. The renderer does not rewrite the supplied script.
- Optional Markdown headings or labels such as `SCENE 1 — THE HOOK` are removed from spoken narration.
- Blank lines separate speech beats for narration and captions.
- The app estimates narration duration and warns if the selected 5–8 minute target is a poor match.
- A local open image model generates 2D stickman/caveman-style scene frames based on each narration beat.
- Kokoro neural TTS is primary, with Piper neural TTS fallback.
- FFmpeg assembles a 16:9 H.264/AAC MP4 with timed captions and ambient bed.
- GitHub Actions manual workflows provide script preview and final MP4 artifacts.

## Visual direction
The default art direction is the familiar YouTube ancient-survival/caveman stickman explainer look: simple 2D stick characters, round heads, thin line limbs, flat cartoon colors, rough ancient clothing/tools when the setting calls for them, expressive/savage body language, and hand-drawn story environments. Clothing, props, and settings adapt to the pasted script's topic while the simple stickman character design stays consistent.

**Current rendering limitation:** image generation creates scene stills, then FFmpeg adds camera pan/zoom motion. It does not yet animate individual limbs as true frame-by-frame character animation. The prompts aim for strong action poses and visual variety, but do not claim full character animation.

## GitHub Actions
- Open Actions → **Preview Manual Script** to parse the script, check its estimated runtime, and download a preview artifact.
- Open Actions → **Render Manual Stickman Documentary** to paste the script and choose duration, 18/24/30/36 scene frames, voice, and resolution.
- Download the `weird-history-mp4` artifact when the render completes. Artifacts are retained for seven days.
- Render is manual/opt-in; pushing code does not start an expensive full render.

## Streamlit deployment
Deploy `app.py` from this repository. To let the hosted app trigger GitHub Actions directly, add a narrowly scoped GitHub token with Actions: write permission to Streamlit secrets as `GITHUB_TOKEN`. Never commit the token to the repository. Without that token, the app links to the manual Actions workflow.

## Free-tier and compute notes
- No AI-provider API key is needed.
- Public model downloads and Wikipedia may require internet access.
- GitHub standard runners are CPU-only; the first image-model download and 30-scene render can take a long time.
- A successful smoke test is not proof of natural voice quality or a successful full render. Full render remains the integration test.

## Niche presets

Choose a niche preset in the Streamlit sidebar or the manual GitHub Actions workflow: **Stickman History (default)**, Survival, Psychology, Science, or Dark Mysteries. The default preset keeps the existing simple 2D stickman/caveman-history direction and uses `af_heart` by default. Your pasted narration is not rewritten by a preset; presets only guide scene prompts, palette, caption appearance, and default voice.

To add a niche, copy one JSON file from `config/niches/`, give it a new filename such as `space.json`, and edit the same fields. Keep `style_prefix` explicitly simple 2D stickman (not photorealistic or 3D), keep 8–10 `action_directions`, and use `af_heart` or `am_michael` for `default_voice`. Add the new preset name to the choices in both GitHub workflow files. The image model is unchanged and runs locally; no paid API is introduced.
## Image providers and six-scene preview

- **Pollinations (default)** requests free 1280×720 Flux images without an API key. Anonymous service availability, speed, and image quality can vary.
- **Local** uses the existing free SD-Turbo model, with Tiny-SD as a fallback; these models are retained.
- Each Pollinations scene is tried up to three times, with a 90-second request timeout and at least 15 seconds between requests. Invalid, tiny, or nearly blank responses are rejected. If Pollinations still fails, only that scene falls back to a local model.
- Images are cached by prompt + niche seed + provider in `.image-cache/`; GitHub Actions restores/saves this cache between runs. Each render report records the provider and cache/fallback status for every image.
- Pollinations images skip the optional local 2D outline/posterization filter by default. The niche JSON `postprocess` flag controls the filter for local model images.
- To judge the look before spending time on a full video, open Actions → **Preview Scene Images**, paste the script, choose a niche and provider, and run it. It creates six still images only—no voice and no video—and uploads `scene-preview-images` with `prompts.txt` and `report.json`.
- These are free, no-key providers, but the external Pollinations service is not guaranteed to be always available or consistently high quality. The local models remain the fallback.
