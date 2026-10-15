from __future__ import annotations

import gc
import io
import json
from pathlib import Path

import torch
from diffusers import AutoPipelineForText2Image
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

from src.image_providers import apply_monochrome_line_art, cache_key, generate_with_fallback, is_valid_image, pollinations_image, validate_provider
from src.niche_presets import DEFAULT_NICHE, build_scene_prompt, load_niche_preset

# Free local models remain available as the no-key fallback. Do not remove.
MODEL_CANDIDATES = [
    ("stabilityai/sd-turbo", 4, 0.0, 512, 288),
    ("segmind/tiny-sd", 20, 7.5, 512, 512),
]


def _apply_2d_illustration_treatment(image: Image.Image) -> Image.Image:
    """Optional local-image treatment; Pollinations images skip it by default."""
    image = image.convert("RGB")
    flat = ImageOps.posterize(image, bits=4)
    edges = ImageOps.autocontrast(ImageOps.grayscale(flat).filter(ImageFilter.FIND_EDGES))
    ink = edges.point(lambda value: 74 if value >= 48 else 255)
    ink_rgb = Image.merge("RGB", (ink, ink, ink))
    outlined = ImageChops.multiply(flat, ink_rgb)
    outlined = ImageEnhance.Color(outlined).enhance(1.12)
    return ImageEnhance.Contrast(outlined).enhance(1.06)


def _open_cached(path: Path) -> Image.Image | None:
    if not path.is_file():
        return None
    payload = path.read_bytes()
    if not is_valid_image(payload):
        path.unlink(missing_ok=True)
        return None
    with Image.open(io.BytesIO(payload)) as image:
        return image.convert("RGB").copy()


def _local_image(prompt: str, preset: dict, seed: int, cache_path: Path, local_pipe: dict) -> tuple[Image.Image, str, bool]:
    cached = _open_cached(cache_path)
    if cached is not None:
        return cached, "local-cache", True

    last_error = None
    for model_id, steps, guidance, model_width, model_height in MODEL_CANDIDATES:
        pipe = None
        try:
            if local_pipe.get("pipeline") is None or local_pipe.get("model_id") != model_id:
                if local_pipe.get("pipeline") is not None:
                    del local_pipe["pipeline"]
                    gc.collect()
                device = "cuda" if torch.cuda.is_available() else "cpu"
                dtype = torch.float16 if device == "cuda" else torch.float32
                kwargs = {"torch_dtype": dtype}
                if device == "cuda":
                    kwargs["variant"] = "fp16"
                print(f"Loading local fallback image model: {model_id} on {device}")
                pipe = AutoPipelineForText2Image.from_pretrained(model_id, **kwargs).to(device)
                if device == "cpu":
                    pipe.enable_attention_slicing()
                local_pipe["pipeline"] = pipe
                local_pipe["model_id"] = model_id
            else:
                pipe = local_pipe["pipeline"]
            device = "cuda" if torch.cuda.is_available() else "cpu"
            generator = torch.Generator(device=device).manual_seed(int(seed))
            image = pipe(
                prompt=prompt,
                negative_prompt=preset["negative_prompt"],
                num_inference_steps=steps,
                guidance_scale=guidance,
                width=model_width,
                height=model_height,
                generator=generator,
            ).images[0]
            image = ImageOps.fit(image.convert("RGB"), (1280, 720), method=Image.Resampling.LANCZOS)
            if preset.get("postprocess", False):
                image = _apply_2d_illustration_treatment(image)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(cache_path, format="JPEG", quality=92, optimize=True)
            return image, model_id, False
        except Exception as exc:
            last_error = exc
            print(f"Local model failed ({model_id}); trying next local model: {type(exc).__name__}: {exc}")
            if local_pipe.get("pipeline") is not None:
                del local_pipe["pipeline"]
                local_pipe["pipeline"] = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
    raise RuntimeError(f"All free local image models failed: {last_error}") from last_error


def generate_scenes(
    topic: str,
    paragraphs: list[str],
    out_dir: Path,
    scene_count: int = 30,
    niche: str = DEFAULT_NICHE,
    provider: str = "pollinations",
    cache_dir: Path | str = Path(".image-cache"),
) -> list[Path]:
    """Generate scene stills with free Pollinations by default and scene-local model fallback."""
    validate_provider(provider)
    preset = load_niche_preset(niche)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not paragraphs:
        raise ValueError("No narration paragraphs were supplied for scene generation.")
    count = max(1, min(int(scene_count), 36))
    indices = [round(i * (len(paragraphs) - 1) / max(1, count - 1)) for i in range(count)]
    cache_root = Path(cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)
    local_pipe: dict = {"pipeline": None, "model_id": None}
    outputs: list[Path] = []
    manifest: list[dict] = []
    prompts: list[str] = []

    try:
        for n, paragraph_index in enumerate(indices):
            prompt = build_scene_prompt(preset, topic, paragraphs[paragraph_index], n)
            seed = int(preset["fixed_seed"])
            prompts.append(f"SCENE {n + 1:02d}\nSEED: {seed}\nPROMPT:\n{prompt}\n")
            target = out_dir / f"scene_{n:03d}.jpg"
            selected_cache = cache_root / f"{cache_key(prompt, seed, provider)}.jpg"
            local_cache = cache_root / f"{cache_key(prompt, seed, 'local')}.jpg"
            image = None
            provider_used = provider
            cache_hit = False
            fallback_reason = None

            if provider == "pollinations":
                image = _open_cached(selected_cache)
                if image is not None:
                    provider_used, cache_hit = "pollinations-cache", True
                else:
                    # If this exact scene previously fell back, reuse it instead of paying latency again.
                    image = _open_cached(local_cache)
                    if image is not None:
                        provider_used, cache_hit = "local-cache-fallback", True
                    else:
                        def local_for_this_scene():
                            return _local_image(prompt, preset, seed, local_cache, local_pipe)
                        image, provider_used, cache_hit, fallback_reason = generate_with_fallback(
                            prompt, seed, cache_root, local_for_this_scene, provider="pollinations"
                        )
                        if fallback_reason:
                            print(f"Pollinations exhausted 3 attempts for scene {n + 1}; using local model for this scene only.")
            else:
                image, provider_used, cache_hit = _local_image(prompt, preset, seed, selected_cache, local_pipe)

            if image is None:
                raise RuntimeError(f"No image produced for scene {n + 1}.")
            image = ImageOps.fit(image.convert("RGB"), (1280, 720), method=Image.Resampling.LANCZOS)
            # Enforce the chosen universal style for Pollinations and local fallback alike.
            image = apply_monochrome_line_art(image)
            image.save(target, format="JPEG", quality=92, optimize=True)
            outputs.append(target)
            manifest.append({
                "scene": n + 1,
                "image": target.name,
                "provider": provider_used,
                "cache_hit": bool(cache_hit),
                "fallback": provider_used.startswith("local-fallback") or provider_used == "local-cache-fallback",
                "fallback_reason": fallback_reason,
                "seed": seed,
                "cache_key": cache_key(prompt, seed, provider if provider_used.startswith("pollinations") else "local"),
            })
            print(f"Scene {n + 1:02d}: provider={provider_used}, cache_hit={cache_hit}")

        (out_dir / "prompts.txt").write_text("\n\n".join(prompts), encoding="utf-8")
        (out_dir / "image_manifest.json").write_text(json.dumps({
            "niche": niche,
            "requested_provider": provider,
            "image_count": len(outputs),
            "fallback_count": sum(1 for item in manifest if item["fallback"]),
            "images": manifest,
        }, indent=2), encoding="utf-8")
        return outputs
    finally:
        if local_pipe.get("pipeline") is not None:
            del local_pipe["pipeline"]
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
