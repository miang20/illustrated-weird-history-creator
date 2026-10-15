from __future__ import annotations

import hashlib
import io
import time
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, ImageChops, ImageOps, ImageStat

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt/"
REQUEST_TIMEOUT_SECONDS = 90
MIN_REQUEST_INTERVAL_SECONDS = 15
MIN_IMAGE_BYTES = 5_000
MIN_DIMENSION = 256


def apply_monochrome_line_art(image: Image.Image) -> Image.Image:
    """Optional legacy hard-threshold filter; only use when a preset explicitly enables it."""
    grayscale = ImageOps.autocontrast(ImageOps.grayscale(image.convert("RGB")))
    binary = grayscale.point(lambda value: 0 if value < 178 else 255, mode="1")
    return binary.convert("RGB")


def clean_line_art_background(image: Image.Image, white_threshold: int = 248) -> Image.Image:
    """Gently clean near-white backgrounds while preserving color and anti-aliased edges."""
    cleaned = ImageOps.autocontrast(image.convert("RGB"))
    red, green, blue = cleaned.split()
    minimum = ImageChops.darker(ImageChops.darker(red, green), blue)
    maximum = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    bright_neutral = ImageChops.multiply(
        minimum.point(lambda value: 255 if value >= white_threshold else 0),
        ImageChops.subtract(maximum, minimum).point(lambda value: 255 if value <= 18 else 0),
    )
    white = Image.new("RGB", cleaned.size, (255, 255, 255))
    return Image.composite(white, cleaned, bright_neutral)


_last_request_at = 0.0


def cache_key(prompt: str, seed: int, provider: str) -> str:
    """Stable cache key over the exact prompt, seed, and provider."""
    payload = f"{provider}\0{int(seed)}\0{prompt}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def is_valid_image(payload: bytes) -> bool:
    """Reject error pages, corrupt files, tiny images, and nearly blank frames."""
    if not isinstance(payload, (bytes, bytearray)) or len(payload) < MIN_IMAGE_BYTES:
        return False
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.verify()
        with Image.open(io.BytesIO(payload)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                return False
            if image.width < MIN_DIMENSION or image.height < MIN_DIMENSION:
                return False
            stats = ImageStat.Stat(image.convert("RGB"))
            if max(stats.stddev) < 3.0:
                return False
        return True
    except (OSError, ValueError, Image.DecompressionBombError):
        return False


def _respect_rate_limit(sleep=time.sleep, clock=time.monotonic) -> None:
    global _last_request_at
    elapsed = clock() - _last_request_at
    if _last_request_at and elapsed < MIN_REQUEST_INTERVAL_SECONDS:
        sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)
    _last_request_at = clock()


def _is_url_length_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    message = str(exc).lower()
    return status in {414, 431} or any(
        term in message for term in (
            "url too long", "uri too long", "request-target too large",
            "header fields too large", "request line is too large",
        )
    )


def _shorten_prompt_for_url(prompt: str) -> str:
    """Drop the least important tail first, retaining the core style and first action."""
    if len(prompt) <= 420:
        return prompt
    return prompt[:420].rsplit(" ", 1)[0].rstrip(" ,;:.")


def _fetch_pollinations(prompt: str, seed: int, cached: Path, timeout: int, get, sleep, clock) -> Image.Image:
    url = f"{POLLINATIONS_BASE}{quote(prompt, safe='')}?width=1280&height=720&model=flux&nologo=true&seed={int(seed)}"
    _respect_rate_limit(sleep=sleep, clock=clock)
    response = get(url, timeout=timeout)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()
    payload = response.content
    if not content_type.startswith("image/") or not is_valid_image(payload):
        raise ValueError("Pollinations response was not a valid, non-blank image.")
    with Image.open(io.BytesIO(payload)) as image:
        result = image.convert("RGB")
    result.save(cached, format="JPEG", quality=94, optimize=True)
    return result


def pollinations_image(
    prompt: str,
    seed: int,
    cache_dir: Path,
    *,
    attempts: int = 3,
    timeout: int = REQUEST_TIMEOUT_SECONDS,
    get=requests.get,
    sleep=time.sleep,
    clock=time.monotonic,
) -> tuple[Image.Image, Path, bool]:
    """Fetch a free Pollinations image; retry one URL-length error with a shorter prompt."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = cache_key(prompt, seed, "pollinations")
    cached = cache_dir / f"{key}.jpg"
    if cached.is_file():
        payload = cached.read_bytes()
        if is_valid_image(payload):
            with Image.open(io.BytesIO(payload)) as image:
                return image.convert("RGB").copy(), cached, True
        cached.unlink(missing_ok=True)

    last_error: Exception | None = None
    shortened_attempted = False
    for attempt in range(max(1, attempts)):
        request_prompt = _shorten_prompt_for_url(prompt) if shortened_attempted else prompt
        try:
            image = _fetch_pollinations(request_prompt, seed, cached, timeout, get, sleep, clock)
            return image, cached, False
        except Exception as exc:
            last_error = exc
            if _is_url_length_error(exc) and not shortened_attempted:
                shortened_attempted = True
                try:
                    image = _fetch_pollinations(_shorten_prompt_for_url(prompt), seed, cached, timeout, get, sleep, clock)
                    return image, cached, False
                except Exception as shorter_exc:
                    raise RuntimeError(f"Pollinations URL-length retry failed: {shorter_exc}") from shorter_exc
            if attempt + 1 < max(1, attempts):
                sleep(15 * (attempt + 1))
    raise RuntimeError(f"Pollinations failed after {attempts} attempt(s): {last_error}") from last_error


SUPPORTED_PROVIDERS = {"pollinations", "local"}


def validate_provider(provider: str) -> str:
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError("Unknown image provider. Choose 'pollinations' or 'local'.")
    return provider


def generate_with_fallback(
    prompt: str,
    seed: int,
    cache_dir: Path,
    local_generator,
    *,
    provider: str = "pollinations",
    pollinations_generator=pollinations_image,
) -> tuple[Image.Image, str, bool, str | None]:
    """Provider selection/fallback seam, designed to be testable without network or model downloads."""
    validate_provider(provider)
    if provider == "local":
        image, provider_name, cache_hit = local_generator()
        return image, provider_name, cache_hit, None
    try:
        image, _, cache_hit = pollinations_generator(prompt, seed, cache_dir, attempts=3)
        return image, ("pollinations-cache" if cache_hit else "pollinations"), cache_hit, None
    except Exception as exc:
        image, provider_name, cache_hit = local_generator()
        return image, f"local-fallback:{provider_name}", cache_hit, str(exc)
