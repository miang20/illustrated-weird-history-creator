from __future__ import annotations

import gc
import re
from pathlib import Path

import torch
from diffusers import AutoPipelineForText2Image
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

# Public local models only: no hosted image API or paid image credits.
MODEL_CANDIDATES = [
    ("stabilityai/sd-turbo", 4, 0.0, 512, 288),
    ("segmind/tiny-sd", 20, 7.5, 512, 512),
]

# One coherent visual language across the whole documentary. Individual shot
# directions vary, but every image stays in the same illustrated 2D universe.
STYLE_BIBLE = (
    "EXCLUSIVELY HYBRID 2D ANIMATED HISTORY SCENE, premium hand-drawn 2D animation keyframe, illustrated documentary art direction, "
    "clearly drawn ink contours, expressive hand-drawn characters in a readable action pose, designed for 2D cutout motion and parallax, readable silhouettes, "
    "flat graphic shapes, cel-shaded color blocks, layered cutout-animation aesthetic, "
    "painted 2D backgrounds, layered foreground/midground/background artwork for subtle parallax, graphic-novel panel composition, restrained halftone and paper grain, "
    "deep teal, burnt orange, parchment cream and charcoal palette, bold clean outlines, "
    "deliberate foreground midground background layers, designed animation keyframe, "
    "not a photograph, not live action, not photorealism, not 3D rendering"
)

NEGATIVE_DIRECTION = (
    "photograph, photorealistic, realistic skin texture, live action, cinematic still, 3D render, CGI, "
    "plastic CGI, glossy toy, anime, chibi, photographic lighting, depth-of-field bokeh, "
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

def _apply_2d_illustration_treatment(image: Image.Image) -> Image.Image:
    """Force a consistent drawn/cel-shaded finish even when the diffusion model drifts realistic."""
    image = image.convert("RGB")
    flat = ImageOps.posterize(image, bits=4)
    edges = ImageOps.autocontrast(
        ImageOps.grayscale(flat).filter(ImageFilter.FIND_EDGES)
    )
    # Keep only stronger contours as dark ink, then multiply them over flattened colors.
    ink = edges.point(lambda value: 82 if value >= 48 else 255)
    ink_rgb = Image.merge("RGB", (ink, ink, ink))
    outlined = ImageChops.multiply(flat, ink_rgb)
    outlined = ImageEnhance.Color(outlined).enhance(1.16)
    outlined = ImageEnhance.Contrast(outlined).enhance(1.05)
    return outlined


def generate_scenes(topic: str, paragraphs: list[str], out_dir: Path, scene_count: int = 30) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if not paragraphs:
        raise ValueError("No narration paragraphs were supplied for scene generation.")
    # Honour the requested number of shots even when the script has fewer paragraphs.
    # Several distinct shot designs can illustrate one paragraph; set() here previously
    # silently reduced a requested 30-scene video to only 10-16 images.
    count = max(8, min(scene_count, 36))
    indices = [round(i * (len(paragraphs) - 1) / max(1, count - 1)) for i in range(count)]
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
                    negative_prompt=NEGATIVE_DIRECTION,
                    num_inference_steps=steps,
                    guidance_scale=guidance,
                    width=model_width,
                    height=model_height,
                ).images[0]
                image = ImageOps.fit(image.convert("RGB"), (1024, 576), method=Image.Resampling.LANCZOS)
                image = _apply_2d_illustration_treatment(image)
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
