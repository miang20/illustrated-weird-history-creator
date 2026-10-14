from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from src.story import WORDS_PER_MINUTE, build_story
from src.voice import audio_duration, concatenate_audio, synthesize_paragraphs
from src.visuals import generate_scenes

def _run(command: list[str], timeout: int = 7200) -> None:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command[:8])}\n{result.stdout[-5000:]}")

def _caption_file(paragraphs: list[str], durations: list[float], destination: Path, gap: float = 0.24) -> None:
    def stamp(seconds: float) -> str:
        ms = max(0, int(round(seconds * 1000)))
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    lines, cursor, index = [], 0.0, 1
    def speech_weight(word: str) -> float:
        # Syllable-weighted timing is closer to natural speech than equal time per word.
        clean = re.sub(r"[^A-Za-z']", "", word).lower()
        groups = re.findall(r"[aeiouy]+", clean)
        syllables = max(1, len(groups) - (1 if clean.endswith("e") and len(groups) > 1 else 0))
        pause = 0.35 if word.endswith((".", "!", "?")) else 0.16 if word.endswith((",", ";", ":")) else 0.0
        return float(syllables) + pause
    for paragraph, duration in zip(paragraphs, durations):
        words = paragraph.split()
        weights = [speech_weight(word) for word in words]
        total_weight = max(1.0, sum(weights))
        chunks = [list(range(i, min(i + 5, len(words)))) for i in range(0, len(words), 5)]
        used_weight = 0.0
        for positions in chunks:
            chunk_weight = sum(weights[i] for i in positions)
            start = cursor + duration * used_weight / total_weight
            used_weight += chunk_weight
            end = cursor + duration * used_weight / total_weight
            # Tiny delay avoids captions leading the first audible consonant.
            start = min(end - 0.25, start + 0.08)
            end = max(start + 0.25, end - 0.03)
            lines.append(f"{index}\n{stamp(start)} --> {stamp(end)}\n{' '.join(words[i] for i in positions)}\n")
            index += 1
        cursor += duration + gap
    destination.write_text("\n".join(lines), encoding="utf-8")

def _make_bed(destination: Path, duration: float, sample_rate: int = 24000) -> None:
    count = int(duration * sample_rate)
    t = np.arange(count, dtype=np.float32) / sample_rate
    bed = 0.20*np.sin(2*np.pi*55*t) + 0.10*np.sin(2*np.pi*82.4*t)
    pulse = 0.5 + 0.5*np.sin(2*np.pi*0.08*t)
    bed *= (0.18+0.12*pulse) * np.minimum(1.0,t/2.0) * np.minimum(1.0,(duration-t)/3.0)
    sf.write(str(destination), bed.astype(np.float32), sample_rate)

def _render_scene(image: Path, duration: float, destination: Path, resolution: str, variant: int = 0) -> None:
    width, height = (1920,1080) if resolution == "1920x1080" else (1280,720)
    frames = max(1, int(math.ceil(duration*30)))
    # Each short shot reframes the source image differently, so a generated still never sits unchanged for 20+ seconds.
    x_expr = ["iw/2-(iw/zoom/2)", "0", "iw-iw/zoom", "(iw-iw/zoom)*0.35*(1+sin(on/18))"][variant % 4]
    y_expr = ["ih/2-(ih/zoom/2)", "0", "ih-ih/zoom", "(ih-ih/zoom)*0.35*(1+sin(on/22))"][variant % 4]
    zoom_expr = "min(zoom+0.0012,1.075)" if variant % 2 == 0 else "if(lte(zoom,1.001),1.075,max(1.0,zoom-0.0012))"
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
          f"zoompan=z='{zoom_expr}':d=1:x='{x_expr}':y='{y_expr}':s={width}x{height}:fps=30,"
          "setsar=1,format=yuv420p")
    _run(["ffmpeg","-y","-hide_banner","-loglevel","error","-loop","1","-i",str(image),"-vf",vf,
          "-frames:v",str(frames),"-an","-c:v","libx264","-preset","ultrafast","-crf","22",str(destination)],
         timeout=max(300,int(duration*15)))

def render_documentary(topic: str, duration_minutes: int = 6, scene_count: int = 12,
                       voice: str = "af_heart", resolution: str = "1280x720",
                       angle: str = "", output_dir: Path | str = Path("output")) -> dict:
    if not 5 <= int(duration_minutes) <= 8:
        raise ValueError("Duration must be between 5 and 8 minutes.")
    output_dir = Path(output_dir).resolve()
    slug = re.sub(r"[^a-zA-Z0-9_-]+","-",topic.lower()).strip("-")[:48] or "history"
    job_dir = output_dir / slug
    if job_dir.exists():
        shutil.rmtree(job_dir)
    for sub in ["audio","scenes","clips"]:
        (job_dir/sub).mkdir(parents=True,exist_ok=True)
    story = build_story(topic,duration_minutes,angle)
    minimum_words = int(duration_minutes * WORDS_PER_MINUTE * 0.90)
    if story.word_count < minimum_words:
        raise RuntimeError(
            f"Research/script produced only {story.word_count} words for a {duration_minutes}-minute target "
            f"(minimum {minimum_words}). No TTS or image generation was started; choose a broader topic or retry."
        )
    (job_dir/"script.txt").write_text("\n\n".join(story.paragraphs),encoding="utf-8")
    (job_dir/"sources.json").write_text(json.dumps(story.sources,indent=2),encoding="utf-8")
    (job_dir/"metadata.json").write_text(json.dumps({"topic":topic,"title":story.title,"target_minutes":duration_minutes,
        "word_count":story.word_count,"resolution":resolution},indent=2),encoding="utf-8")
    audio_paths, voice_engine = synthesize_paragraphs(story.paragraphs,job_dir/"audio",voice)
    durations = [audio_duration(p) for p in audio_paths]
    narration = job_dir/"narration.wav"
    concatenate_audio(audio_paths,narration)
    voice_seconds = sum(durations)+max(0,len(durations)-1)*0.24
    if voice_seconds < duration_minutes*60*0.82:
        raise RuntimeError(f"Narration is only {voice_seconds/60:.1f} minutes; target is {duration_minutes}. Refusing to create a falsely labelled short video.")
    if voice_seconds > duration_minutes*60*1.15:
        raise RuntimeError(f"Narration is {voice_seconds/60:.1f} minutes, too long for the selected {duration_minutes}-minute target.")
    images = generate_scenes(topic,story.paragraphs,job_dir/"scenes",scene_count)
    total_seconds = voice_seconds
    # Fast visual rhythm: a new 5.5-second shot with a different crop/motion, rather than one still lasting ~25 seconds.
    shot_seconds = 5.5
    shot_count = max(1, int(math.ceil(total_seconds / shot_seconds)))
    clips = []
    for i in range(shot_count):
        clip = job_dir/"clips"/f"clip_{i:03d}.mp4"
        duration = min(shot_seconds, total_seconds - i*shot_seconds)
        image = images[i % len(images)]
        _render_scene(image, duration, clip, resolution, variant=i)
        clips.append(clip)
    concat_file = job_dir/"concat.txt"
    concat_file.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips),encoding="utf-8")
    visuals = job_dir/"visuals.mp4"
    _run(["ffmpeg","-y","-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",str(concat_file),"-c","copy",str(visuals)])
    captions = job_dir/"captions.srt"
    _caption_file(story.paragraphs,durations,captions)
    bed = job_dir/"ambient.wav"
    _make_bed(bed,total_seconds)
    final_path = job_dir/"final_weird_history.mp4"
    subtitle_path = captions.as_posix().replace(":","\\:").replace("'","\\'")
    width,height = (1920,1080) if resolution == "1920x1080" else (1280,720)
    vf = f"subtitles='{subtitle_path}':force_style='FontName=DejaVu Sans,FontSize=22,Outline=2,Shadow=1,Alignment=2,MarginV=46',scale={width}:{height},setsar=1"
    _run(["ffmpeg","-y","-hide_banner","-loglevel","error","-i",str(visuals),"-i",str(narration),"-i",str(bed),
        "-filter_complex","[2:a]volume=0.13[bg];[1:a][bg]amix=inputs=2:duration=first:weights='1 0.12',loudnorm=I=-16:TP=-1.5:LRA=11[a]",
        "-vf",vf,"-map","0:v:0","-map","[a]","-c:v","libx264","-preset","veryfast","-crf","21",
        "-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-movflags","+faststart","-shortest",str(final_path)])
    probe = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration,size","-of","json",str(final_path)],
                           check=True,text=True,stdout=subprocess.PIPE)
    media = json.loads(probe.stdout)["format"]
    video_seconds = float(media["duration"])
    if video_seconds < duration_minutes*60*0.82:
        raise RuntimeError(f"Final MP4 is too short ({video_seconds/60:.1f} minutes).")
    if video_seconds > duration_minutes*60*1.15:
        raise RuntimeError(f"Final MP4 is too long ({video_seconds/60:.1f} minutes).")
    report = {"title":story.title,"topic":topic,"video":str(final_path),"duration_seconds":round(video_seconds,2),
        "word_count":story.word_count,"voice_engine":voice_engine,"scene_count":len(images),"resolution":resolution,
        "size_bytes":int(media["size"]),"sources":story.sources}
    (job_dir/"render_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return {"video":final_path,"report":report,"directory":job_dir}
