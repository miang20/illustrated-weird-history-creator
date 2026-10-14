from __future__ import annotations

import re
from pathlib import Path

import torch
from diffusers import AutoPipelineForText2Image
from PIL import Image, ImageEnhance, ImageOps

MODEL_ID = "stabilityai/sd-turbo"

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
    count = max(8, min(scene_count, 18, len(paragraphs)))
    indices = sorted(set(round(i * (len(paragraphs)-1) / max(1, count-1)) for i in range(count)))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    kwargs = {"torch_dtype": dtype}
    if device == "cuda":
        kwargs["variant"] = "fp16"
    pipe = AutoPipelineForText2Image.from_pretrained(MODEL_ID, **kwargs).to(device)
    if device == "cpu":
        pipe.enable_attention_slicing()
    outputs = []
    for n, paragraph_index in enumerate(indices):
        target = out_dir / f"scene_{n:03d}.jpg"
        if target.exists() and target.stat().st_size > 5000:
            outputs.append(target)
            continue
        image = pipe(prompt=_scene_prompt(topic, paragraphs[paragraph_index], n),
                     num_inference_steps=1, guidance_scale=0.0, width=512, height=288).images[0]
        image = ImageOps.fit(image.convert("RGB"), (1024,576), method=Image.Resampling.LANCZOS)
        image = ImageEnhance.Contrast(image).enhance(1.04)
        image.save(target, format="JPEG", quality=90, optimize=True)
        outputs.append(target)
    del pipe
    if len(outputs) < 8:
        raise RuntimeError(f"AI scene generation returned only {len(outputs)} scenes.")
    return outputs
