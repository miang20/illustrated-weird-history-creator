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

## GitHub Actions
Open Actions → **Render Manual Stickman Documentary** to paste a script directly into GitHub, select 5–8 minutes, scene count, Kokoro voice, and resolution, then download the `weird-history-mp4` artifact. Rendering is manual/opt-in: code pushes do not launch a costly full render. Artifacts are retained for seven days.

## Visual style and limitation
The art direction uses simple 2D YouTube-style stickman/caveman characters with readable silhouettes, primitive clothing/tools for ancient scenes, and edgy expressive body language. Props and environments follow the script's topic. Current video assembly animates the camera over generated still frames; it does not yet produce true frame-by-frame limb animation.

## Free-tier and compute notes
- No AI-provider key is required.
- The local open image model downloads weights and runs on CPU on standard GitHub runners, so first render can be slow.
- To trigger the workflow directly from a hosted Streamlit app, configure a narrowly scoped GitHub token with Actions: write access as the Streamlit secret `GITHUB_TOKEN`. Never commit a token.
- CI smoke tests do not prove successful full rendering or voice quality; a full render is the integration test.

## Pick a niche preset

In the Streamlit sidebar, choose **Niche preset** before pasting/rendering. The default is **Stickman History (Default)**, which keeps the current stickman history look. Survival, Psychology, Science, and Dark Mysteries use their own character description, action list, environment hints, colors, caption settings, and default voice. The same manual narration is passed through regardless of the selected niche; a preset never rewrites or adds narration.

The GitHub Actions **Preview Manual Script** and **Render Manual Stickman Documentary** workflows also have a niche input. Preview records the selected preset in `report.json`; render applies it to scene prompts and caption styling.

## Add another niche

1. Copy a file from `config/niches/` and rename it, for example `space.json`.
2. Edit the style prefix, fixed main-character description, palette, environment hints, 8–10 action directions, negative prompt, integer seed, caption style, and default voice.
3. Keep the art direction simple 2D stickman, explicitly not photorealistic and not 3D. Use `af_heart` or `am_michael` as the default voice.
4. Add `space` to the niche choice list in both `.github/workflows/build.yml` and `.github/workflows/script-preview.yml`.
5. Run lightweight CI/tests before any full render. No paid API or new image model is required.
