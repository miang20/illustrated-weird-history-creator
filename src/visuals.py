from __future__ import annotations

import gc
import re
from pathlib import Path

import torch
from diffusers import AutoPipelineForText2Image
from PIL import Image, ImageEnhance, ImageOps

# Public local models only: no hosted image API or paid image credits.
MODEL_CANDIDATES = [
    ("stabilityai/sd-turbo", 4, 0.0, 512, 288),
    ("segmind/tiny-sd", 20, 7.5, 512, 512),
]

# One coherent visual language across the whole documentary. Individual shot
# directions vary, but every image stays in the same illustrated 2D universe.
STYLE_BIBLE = (
    "professional 2D hybrid historical documentary illustration, premium animated "
    "history-channel art direction, hand-drawn ink outlines, confident clean linework, "
    "expressive simplified faces and readable silhouettes, layered cel shading, "
    "painterly textured backgrounds, subtle print grain and restrained halftone, "
    "dramatic chiaroscuro, strong foreground-midground-background separation, "
    "rich deep teal, burnt orange, parchment cream and charcoal palette, "
    "visually legible at video size, editorially composed, historically grounded"
)

NEGATIVE_DIRECTION = (
    "photograph, photorealistic, 3D render, plastic CGI, glossy toy, anime, chibi, "
    "modern clothing in historical scene, contemporary objects, garbled writing, "
    "letters, captions, typography, logo, watermark, duplicated people, extra limbs, "
    "deformed hands, blurry subject, muddy low-contrast composition"
)

def _scene_prompt(topic: str, paragraph: str, index: int) -> str:
    clean = re.sub(r"\s+", " ", paragraph).strip()[:480]
    visual_directions = [
        "wide establishing shot of the specific historical location, a few expressive period characters in action, dramatic layered composition",
        "hand-illustrated antique map view of the relevant region, parchment coastlines, a clear route or location marker drawn as simple shapes, no written labels",
        "close-up illustrated still life of authentic period objects, documents, tools and material textures arranged as a visual clue",
        "expressive graphic-novel crowd scene reacting to the event, varied poses and clear facial emotion, foreground silhouettes framing the action",
        "medium shot of the key historical figure or ordinary person making a consequential choice, readable gesture and strong silhouette",
        "dramatic environmental shot showing the physical scale or consequences of the event, foreground detail leading the eye into the scene",
    ]
    direction = visual_directions[index % len(visual_directions)]
    return (
        f"{STYLE_BIBLE}. Shot design: {direction}. "
        "Use a single clear visual idea, bold value separation, controlled detail and an intentional focal point. "
        "Keep people and props fully inside the frame. No readable text, no letters, no watermark. "
        f"Historical topic: {topic}. Specific scene context: {clean}. "
        f"Avoid: {NEGATIVE_DIRECTION}."
    )

def generate_scenes(topic: str, paragraphs: list[str], out_dir: Path, scene_count: int = 30) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if not paragraphs:
        raise ValueError("No narration paragraphs were supplied for scene generation.")
    count = max(8, min(scene_count, 36, len(paragraphs)))
    indices = sorted(set(round(i * (len(paragraphs)-1) / max(1, count-1)) for i in range(count)))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    last_error = None

    for model_id, steps, guidance, model_width, model_height in MODEL_CANDIDATES:
        pipe = None
        try:
            kwargs = {"torch_dtype": dtype}
            if device == "cuda":
                kwargs["variant"] = "fp16"
            print(f"Loading local image model: {model_id} on {device}")
            pipe = AutoPipelineForText2Image.from_pretrained(model_id, **kwargs).to(device)
            if device == "cpu":
                pipe.enable_attention_slicing()
            outputs = []
            for n, paragraph_index in enumerate(indices):
                target = out_dir / f"scene_{n:03d}.jpg"
                image = pipe(
                    prompt=_scene_prompt(topic, paragraphs[paragraph_index], n),
                    num_inference_steps=steps,
                    guidance_scale=guidance,
                    width=model_width,
                    height=model_height,
                ).images[0]
                image = ImageOps.fit(image.convert("RGB"), (1024, 576), method=Image.Resampling.LANCZOS)
                image = ImageEnhance.Contrast(image).enhance(1.08)
                image = ImageEnhance.Color(image).enhance(1.04)
                image.save(target, format="JPEG", quality=92, optimize=True)
                outputs.append(target)
            if len(outputs) < 8:
                raise RuntimeError(f"{model_id} returned only {len(outputs)} scenes.")
            print(f"Image provider succeeded: {model_id} ({len(outputs)} scenes)")
            return outputs
        except Exception as exc:
            last_error = exc
            print(f"Image provider failed ({model_id}); trying next local model: {type(exc).__name__}: {exc}")
            for stale in out_dir.glob("scene_*.jpg"):
                stale.unlink(missing_ok=True)
        finally:
            if pipe is not None:
                del pipe
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    raise RuntimeError(
        "All no-key local image providers failed. No fake stock-image fallback was used. "
        f"Last image error: {last_error}"
    ) from last_error
