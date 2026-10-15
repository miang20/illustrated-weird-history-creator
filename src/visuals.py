from __future__ import annotations

import gc
import re
from pathlib import Path

import torch
from diffusers import AutoPipelineForText2Image
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

# Free, locally-run image models only. No hosted image API or paid credits.
MODEL_CANDIDATES = [
    ("stabilityai/sd-turbo", 4, 0.0, 512, 288),
    ("segmind/tiny-sd", 20, 7.5, 512, 512),
]

# Target the familiar YouTube ancient-survival / caveman stickman explainer look:
# simple 2D stick characters, readable silhouettes, expressive action, hand-drawn backgrounds.
STYLE_BIBLE = (
    "popular YouTube 2D stickman storytelling/explainer animation style, with ancient-survival/caveman treatment when the script calls for it, simple 2D cartoon scene, "
    "clear stickman/caveman characters with round simple heads, tiny readable facial features, "
    "thin black line arms and legs, simple compact torsos, minimal flat cartoon anatomy, "
    "rough primitive tunic or ragged loincloth when the setting is ancient, crude wooden spear or stone tool when relevant, "
    "bold clean dark outlines, flat colors, hand-drawn 2D environment, readable cave and forest shapes, "
    "simple painted backgrounds with clear foreground and background separation, expressive poses and exaggerated body language, "
    "dynamic action frozen at the most readable moment, humorous but tense storytelling, "
    "slightly rough hand-drawn explainer aesthetic, uncluttered composition, strong silhouette, "
    "not 3D, not realistic humans, not photorealistic"
)

NEGATIVE_DIRECTION = (
    "photograph, photorealistic, realistic human anatomy, live action, 3D render, CGI, glossy toy, "
    "anime, chibi, glowing eyes, superhero armor, hyper-detailed character concept art, "
    "overdesigned character, realistic skin texture, depth-of-field bokeh, modern clothing in an ancient scene, "
    "contemporary objects unless the script is modern history, garbled writing, letters, captions, typography, logo, watermark, "
    "duplicated characters, extra limbs, extra fingers, deformed hands, blurry subject, muddy low contrast, "
    "static lineup, character turnaround sheet"
)

ACTION_DIRECTIONS = [
    "wide story shot: the main stickman character is actively doing something in the environment, bold readable pose, clear setting",
    "action beat: stickman crouching, sneaking, running, climbing, carrying, pointing, or reacting according to the scene context",
    "strong reaction shot: stickman recoils, throws both arms up, stares in disbelief, or leans forward aggressively; exaggerated body language",
    "consequence shot: several simple stickman characters panic, argue, celebrate, flee, or work together around one clear event",
    "medium shot: one stickman makes a consequential choice with an obvious gesture; props support the narration, not distract from it",
    "dynamic low-angle or high-angle shot showing danger, scale, or a surprising reveal, with the stickman silhouette easy to read",
    "visual punchline or twist: a stickman reacts with a smug, horrified, suspicious, or fed-up posture that fits the narration",
    "environment-and-action shot: a cave, village, ship, street, battlefield, or other relevant location with stickman characters moving through it",
]


def _scene_prompt(topic: str, paragraph: str, index: int) -> str:
    clean = re.sub(r"\s+", " ", paragraph).strip()[:420]
    direction = ACTION_DIRECTIONS[index % len(ACTION_DIRECTIONS)]
    ancient_hint = (
        "If this scene is prehistoric or ancient, use a simple caveman stickman with ragged primitive clothing, "
        "a cave or rough ancient setting, and crude tools only when historically appropriate. "
        "If the script covers another era or niche, keep the same simple 2D stickman design but adapt clothing, props, and setting to the actual story."
    )
    return (
        f"{STYLE_BIBLE}. Scene action: {direction}. {ancient_hint} "
        "Show an action pose, not a character lineup and not a decorative still life. "
        "Use 1-4 main characters, simple faces, readable limbs, expressive posture, strong silhouette, "
        "clear 2D background, limited earthy colors, and one obvious visual idea. "
        "No written words or labels inside the image. "
        f"Topic: {topic}. Narration beat to illustrate: {clean}. "
        f"Avoid: {NEGATIVE_DIRECTION}."
    )


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


def generate_scenes(topic: str, paragraphs: list[str], out_dir: Path, scene_count: int = 30) -> list[Path]:
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
