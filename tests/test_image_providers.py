from __future__ import annotations

import io

from PIL import Image

from src import image_providers as providers


def _valid_image_bytes() -> bytes:
    image = Image.effect_noise((320, 320), 90).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class _Response:
    def __init__(self, content: bytes, content_type: str = "image/png"):
        self.content = content
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self):
        return None


class _HTTPError(Exception):
    def __init__(self, status_code, message="URL too long"):
        super().__init__(message)
        self.response = type("ResponseInfo", (), {"status_code": status_code})()


def test_provider_selection_accepts_only_supported_providers():
    assert providers.validate_provider("pollinations") == "pollinations"
    assert providers.validate_provider("local") == "local"
    try:
        providers.validate_provider("paid_api")
    except ValueError as exc:
        assert "pollinations" in str(exc) and "local" in str(exc)
    else:
        raise AssertionError("unsupported provider should fail clearly")


def test_cache_key_is_stable_and_includes_exact_prompt():
    prompt = "simple 2D stickman standing in a cave"
    first = providers.cache_key(prompt, 194711, "pollinations")
    assert first == providers.cache_key(prompt, 194711, "pollinations")
    assert first != providers.cache_key(prompt + " in muted tan clothing", 194711, "pollinations")
    assert first != providers.cache_key(prompt, 194712, "pollinations")
    assert first != providers.cache_key(prompt, 194711, "local")


def test_invalid_or_tiny_image_is_rejected():
    assert not providers.is_valid_image(b"<html>service error</html>")
    tiny = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(tiny, format="PNG")
    assert not providers.is_valid_image(tiny.getvalue())


def test_pollinations_retry_count_timeout_and_cache_without_network(tmp_path):
    providers._last_request_at = 0.0
    calls = []
    delays = []
    payload = _valid_image_bytes()

    def fake_get(url, timeout):
        calls.append((url, timeout))
        if len(calls) < 3:
            raise OSError("mock network failure")
        return _Response(payload)

    image, cache_path, cache_hit = providers.pollinations_image(
        "simple 2D stickman", 194711, tmp_path,
        get=fake_get, sleep=delays.append, clock=lambda: 100.0,
    )
    assert image.size == (320, 320)
    assert cache_path.is_file()
    assert cache_hit is False
    assert len(calls) == 3
    assert all(timeout == 90 for _, timeout in calls)
    assert "width=1280&height=720&model=flux&nologo=true&seed=194711" in calls[0][0]
    assert delays

    def should_not_be_called(*args, **kwargs):
        raise AssertionError("valid cached image must be reused")

    _, second_path, second_hit = providers.pollinations_image(
        "simple 2D stickman", 194711, tmp_path, get=should_not_be_called,
        sleep=delays.append, clock=lambda: 100.0,
    )
    assert second_path == cache_path
    assert second_hit is True


def test_url_length_error_retries_once_with_shorter_prompt(tmp_path):
    providers._last_request_at = 0.0
    calls = []
    payload = _valid_image_bytes()
    long_prompt = "Universal stickman style. " + ("extra prompt detail " * 35)

    def fake_get(url, timeout):
        calls.append(url)
        if len(calls) == 1:
            raise _HTTPError(414)
        return _Response(payload)

    image, _, cache_hit = providers.pollinations_image(
        long_prompt, 7, tmp_path, get=fake_get, sleep=lambda _: None, clock=lambda: 100.0,
    )
    assert image.size == (320, 320)
    assert cache_hit is False
    assert len(calls) == 2
    assert len(calls[1]) < len(calls[0])


def test_three_failed_pollinations_attempts_fall_back_to_local_mock(tmp_path):
    failed_attempts = []
    local_calls = []

    def failing_pollinations(prompt, seed, cache_dir, attempts=3):
        for _ in range(attempts):
            failed_attempts.append("failed")
        raise RuntimeError("mock Pollinations outage")

    def local_generator():
        local_calls.append(True)
        return Image.new("RGB", (320, 320), (30, 100, 160)), "mock-local-model", False

    image, provider_name, cache_hit, reason = providers.generate_with_fallback(
        "test prompt", 7, tmp_path, local_generator,
        provider="pollinations", pollinations_generator=failing_pollinations,
    )
    assert image.size == (320, 320)
    assert provider_name == "local-fallback:mock-local-model"
    assert cache_hit is False
    assert "mock Pollinations outage" in reason
    assert len(failed_attempts) == 3
    assert len(local_calls) == 1
