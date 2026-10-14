from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from src.story import build_story
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
    for paragraph, duration in zip(paragraphs, durations):
        words = paragraph.split()
        chunks = [words[i:i+9] for i in range(0, len(words), 9)]
        total_words, used = max(1, len(words)), 0
        for chunk in chunks:
            start = cursor + duration * used / total_words
            used += len(chunk)
            end = cursor + duration * used / total_words
            if end-start < 0.35:
                end = min(cursor+duration, start+0.35)
            lines.append(f"{index}\n{stamp(start)} --> {stamp(end)}\n{' '.join(chunk)}\n")
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

def _render_scene(image: Path, duration: float, destination: Path, resolution: str) -> None:
    width, height = (1920,1080) if resolution == "1920x1080" else (1280,720)
    frames = max(1, int(math.ceil(duration*30)))
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
          f"zoompan=z='min(zoom+0.00025,1.07)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps=30,"
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
    (job_dir/"script.txt").write_text("\n\n".join(story.paragraphs),encoding="utf-8")
    (job_dir/"sources.json").write_text(json.dumps(story.sources,indent=2),encoding="utf-8")
    (job_dir/"metadata.json").write_text(json.dumps({"topic":topic,"title":story.title,"target_minutes":duration_minutes,
        "word_count":story.word_count,"resolution":resolution},indent=2),encoding="utf-8")
    audio_paths, voice_engine = synthesize_paragraphs(story.paragraphs,job_dir/"audio",voice)
    durations = [audio_duration(p) for p in audio_paths]
    narration = job_dir/"narration.wav"
    concatenate_audio(audio_paths,narration)
    voice_seconds = sum(durations)+max(0,len(durations)-1)*0.24
    if voice_seconds < duration_minutes*60*0.65:
        raise RuntimeError(f"Narration is only {voice_seconds/60:.1f} minutes; target is {duration_minutes}. Refusing to create a falsely labelled short video.")
    images = generate_scenes(topic,story.paragraphs,job_dir/"scenes",scene_count)
    total_seconds, per_scene = voice_seconds, voice_seconds/len(images)
    clips = []
    for i,image in enumerate(images):
        clip = job_dir/"clips"/f"clip_{i:03d}.mp4"
        duration = per_scene if i < len(images)-1 else total_seconds-per_scene*(len(images)-1)
        _render_scene(image,duration,clip,resolution)
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
        "-filter_complex","[2:a]volume=0.13[bg];[1:a][bg]amix=inputs=2:duration=first:weights=1 0.12, loudnorm=I=-16:TP=-1.5:LRA=11[a]",
        "-vf",vf,"-map","0:v:0","-map","[a]","-c:v","libx264","-preset","veryfast","-crf","21",
        "-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-movflags","+faststart","-shortest",str(final_path)])
    probe = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration,size","-of","json",str(final_path)],
                           check=True,text=True,stdout=subprocess.PIPE)
    media = json.loads(probe.stdout)["format"]
    video_seconds = float(media["duration"])
    if video_seconds < duration_minutes*60*0.65:
        raise RuntimeError(f"Final MP4 is too short ({video_seconds/60:.1f} minutes).")
    report = {"title":story.title,"topic":topic,"video":str(final_path),"duration_seconds":round(video_seconds,2),
        "word_count":story.word_count,"voice_engine":voice_engine,"scene_count":len(images),"resolution":resolution,
        "size_bytes":int(media["size"]),"sources":story.sources}
    (job_dir/"render_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return {"video":final_path,"report":report,"directory":job_dir}
