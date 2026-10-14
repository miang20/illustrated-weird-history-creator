from __future__ import annotations

import gc
import re
from pathlib import Path

import torch
from diffusers import AutoPipelineForText2Image
from PIL import Image, ImageEnhance, ImageOps

# Both are public model repositories; no hosted image API keys are used.
MODEL_CANDIDATES = [
    ("stabilityai/sd-turbo", 4, 0.0, 512, 288),
    ("segmind/tiny-sd", 20, 7.5, 512, 512),
]

def _scene_prompt(topic: str, paragraph: str, index: int) -> str:
    clean = re.sub(r"\s+", " ", paragraph).strip()[:480]
    return (
        "Historically grounded cinematic editorial illustration for a serious weird-history documentary, "
        "hand-painted realism, dramatic natural light, textured brushwork, rich muted ochre and deep teal palette, "
        "period-appropriate clothing and architecture, strong visual composition, widescreen establishing shot, "
        "no text, no letters, no watermark, not a modern photograph. "
        f"Subject and context: {topic}. Scene {index + 1}: {clean}"
    )

def generate_scenes(topic: str, paragraphs: list[str], out_dir: Path, scene_count: int = 12) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if not paragraphs:
        raise ValueError("No narration paragraphs were supplied for scene generation.")
    count = max(8, min(scene_count, 18, len(paragraphs)))
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
                image = ImageEnhance.Contrast(image).enhance(1.04)
                image.save(target, format="JPEG", quality=90, optimize=True)
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
