from __future__ import annotations

import gc
import re
from pathlib import Path

import torch
from diffusers import AutoPipelineForText2Image
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

from src.niche_presets import DEFAULT_NICHE, build_scene_prompt, load_niche_preset

# Free, locally-run image models only. No hosted image API or paid credits.
MODEL_CANDIDATES = [
    ("stabilityai/sd-turbo", 4, 0.0, 512, 288),
    ("segmind/tiny-sd", 20, 7.5, 512, 512),
]

def _scene_prompt(topic: str, paragraph: str, index: int, preset: dict | None = None) -> str:
    selected = preset or load_niche_preset(DEFAULT_NICHE)
    return build_scene_prompt(selected, topic, paragraph, index)


def _apply_2d_illustration_treatment(image: Image.Image) -> Image.Image:
    """Flatten colors and reinforce drawn contours to keep generated frames in a coherent 2D style."""
    image = image.convert("RGB")
    flat = ImageOps.posterize(image, bits=4)
    edges = ImageOps.autocontrast(ImageOps.grayscale(flat).filter(ImageFilter.FIND_EDGES))
    ink = edges.point(lambda value: 74 if value >= 48 else 255)
    ink_rgb = Image.merge("RGB", (ink, ink, ink))
    outlined = ImageChops.multiply(flat, ink_rgb)
    outlined = ImageEnhance.Color(outlined).enhance(1.12)
    return ImageEnhance.Contrast(outlined).enhance(1.06)


def generate_scenes(
    topic: str, paragraphs: list[str], out_dir: Path, scene_count: int = 30,
    niche: str = DEFAULT_NICHE,
) -> list[Path]:
    preset = load_niche_preset(niche)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not paragraphs:
        raise ValueError("No narration paragraphs were supplied for scene generation.")
    count = max(8, min(int(scene_count), 36))
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
                generator = torch.Generator(device=device).manual_seed(int(preset["fixed_seed"]))
                image = pipe(
                    prompt=_scene_prompt(topic, paragraphs[paragraph_index], n, preset),
                    negative_prompt=preset["negative_prompt"],
                    num_inference_steps=steps,
                    guidance_scale=guidance,
                    width=model_width,
                    height=model_height,
                    generator=generator,
                ).images[0]
                image = ImageOps.fit(image.convert("RGB"), (1024, 576), method=Image.Resampling.LANCZOS)
                image = _apply_2d_illustration_treatment(image)
                image.save(target, format="JPEG", quality=92, optimize=True)
                outputs.append(target)
            if len(outputs) != count:
                raise RuntimeError(f"{model_id} returned {len(outputs)} scenes; expected {count}.")
            print(f"Image provider succeeded: {model_id} ({len(outputs)} 2D stickman scene frames)")
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
