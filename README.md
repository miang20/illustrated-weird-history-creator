# Savage Stickman Studio

Manual-script-first, free-first creator for long-form YouTube history, survival, mystery, and other documentary niches.

## Core workflow
- Paste your own narration. The renderer does not rewrite the supplied script.
- Optional Markdown headings or labels such as `SCENE 1 — THE HOOK` are removed from spoken narration.
- Blank lines separate speech beats for narration and captions.
- The app estimates narration duration and warns if the selected 5–8 minute target is a poor match.
- Free Pollinations Flux generates 1280×720 scene images by default; existing local SD-Turbo/Tiny-SD models remain as per-scene fallback.
- Kokoro neural TTS is primary, with Piper neural TTS fallback.
- FFmpeg assembles a 16:9 H.264/AAC MP4 with timed captions and ambient bed.
- GitHub Actions manual workflows provide script preview and final MP4 artifacts.

## Universal visual style
Every niche loads `config/universal_style.json`: one consistent simple 2D hand-drawn stickman, round white head with thick black outline, two dot eyes, simple mouth, thin black stick arms and legs, clean bold black outlines, and pure white background. Flat muted beige/brown/tan/black is permitted only on character clothing and a few relevant props; everything else remains black line art on white. No gradients, shading, textures, colored backgrounds, text, 3D, or photorealism. Niche presets may change the setting and action, not the character definition.

The scene prompt is built from the shared style sentence, the niche's muted clothing hint, one shortened key sentence from the narration beat, a short environment hint, and a brief negative tail. The stored narration is never modified. Prompt length is capped at 900 characters and logged per scene in `prompts.txt` and the image manifest/report.

**Rendering limitation:** image generation creates still scenes, then FFmpeg adds camera pan/zoom. It does not yet animate individual limbs as true frame-by-frame character animation.

## GitHub Actions
- Open Actions → **Preview Manual Script** to parse the script, check estimated runtime, and download a preview artifact.
- **Preview Scene Images** generates six images and prompts for inspection. It does not create voice or video.
- **Render Manual Stickman Documentary** generates the final MP4. Rendering remains manual/opt-in.
- Download the `weird-history-mp4` artifact when the render completes. Artifacts are retained for seven days.

## Free-tier and compute notes
- No AI-provider API key is required.
- Pollinations is free/no-key but availability, speed, and image quality can vary.
- Local fallback keeps the existing free SD-Turbo model and Tiny-SD fallback; CPU model downloads can be slow.
- Scene images are cached in `.image-cache/` by exact prompt + seed + provider.
- Gentle cleanup uses autocontrast and whitens near-white background pixels while preserving color and anti-aliased lines. The legacy hard black/white threshold filter remains available only when a niche explicitly opts into `"postprocess": true`; it defaults off.
- Lightweight tests do not prove image-provider availability or successful full rendering.

## Niche presets
Five presets are available: Stickman History (default), Survival, Psychology, Science, and Dark Mysteries. Each niche JSON contains only its display name, fixed seed, environment hints, action directions, default voice, caption style, and muted clothing hint. Every action centers one main stickman; other people or animals may appear only when the narration needs them and should be simple stickman/line-art.

The same manual narration is passed through regardless of niche; a preset never rewrites or adds narration. To add a niche, copy a preset JSON, update the supported fields, then add its name to the relevant workflow choices. No paid API or new image model is required.
