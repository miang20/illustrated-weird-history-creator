from __future__ import annotations

import subprocess
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf

PIPER_VOICES = {
    # Match the requested Kokoro voice's broad presentation when falling back to Piper.
    "af_heart": "en_US-lessac-medium",
    "am_michael": "en_US-ryan-medium",
}
PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US"

def _kokoro(paragraphs: list[str], out_dir: Path, voice: str) -> list[Path]:
    from kokoro import KPipeline
    pipeline = KPipeline(lang_code="a")
    outputs = []
    for i, paragraph in enumerate(paragraphs):
        pieces = []
        for _, _, audio in pipeline(paragraph, voice=voice, speed=1.04):
            if audio is not None:
                arr = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
                pieces.append(np.asarray(arr, dtype=np.float32).reshape(-1))
        if not pieces:
            raise RuntimeError(f"Kokoro produced no audio for paragraph {i + 1}")
        path = out_dir / f"voice_{i:03d}.wav"
        sf.write(path, np.concatenate(pieces), 24000)
        outputs.append(path)
    return outputs

def _download(url: str, target: Path) -> None:
    if not target.exists() or target.stat().st_size < 1000:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=90) as response, target.open("wb") as out:
            out.write(response.read())

def _piper(paragraphs: list[str], out_dir: Path, voice: str) -> list[Path]:
    voice_model = PIPER_VOICES.get(voice, PIPER_VOICES["af_heart"])
    voice_family = voice_model.split("-")[1]
    model_url = f"{PIPER_BASE}/{voice_family}/medium/{voice_model}.onnx"
    model = out_dir / f"{voice_model}.onnx"
    config = out_dir / f"{voice_model}.onnx.json"
    _download(model_url, model)
    _download(model_url + ".json", config)
    outputs = []
    for i, paragraph in enumerate(paragraphs):
        path = out_dir / f"voice_{i:03d}.wav"
        subprocess.run(["piper","--model",str(model),"--config",str(config),"--output_file",str(path)],
            input=paragraph, text=True, check=True, timeout=180, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if not path.exists() or path.stat().st_size < 1000:
            raise RuntimeError(f"Piper produced empty audio for paragraph {i + 1}")
        outputs.append(path)
    return outputs

def synthesize_paragraphs(paragraphs: list[str], out_dir: Path, voice: str = "af_heart") -> tuple[list[Path], str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        return _kokoro(paragraphs, out_dir, voice), "Kokoro neural TTS"
    except Exception as primary_error:
        print(f"Kokoro unavailable; switching to Piper: {type(primary_error).__name__}: {primary_error}")
        try:
            return _piper(paragraphs, out_dir, voice), "Piper neural TTS fallback"
        except Exception as fallback_error:
            raise RuntimeError(f"Both neural TTS engines failed; no robotic system voice used. Kokoro: {primary_error}; Piper: {fallback_error}") from fallback_error

def audio_duration(path: Path) -> float:
    return float(sf.info(str(path)).duration)

def concatenate_audio(paths: list[Path], destination: Path, gap_seconds: float = 0.24) -> None:
    if not paths:
        raise ValueError("No narration audio segments were generated.")
    arrays = []
    rate_out = 24000
    for path in paths:
        data, rate = sf.read(str(path), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        if rate != rate_out:
            old_x = np.linspace(0, 1, len(data), endpoint=False)
            new_len = int(len(data) * rate_out / rate)
            data = np.interp(np.linspace(0, 1, new_len, endpoint=False), old_x, data).astype(np.float32)
        arrays.extend([data, np.zeros(int(gap_seconds * rate_out), dtype=np.float32)])
    combined = np.concatenate(arrays)
    peak = float(np.max(np.abs(combined))) if len(combined) else 0.0
    if peak < 0.001:
        raise RuntimeError("Narration audio is silent.")
    if peak > 0.98:
        combined *= 0.95 / peak
    sf.write(str(destination), combined, rate_out)
