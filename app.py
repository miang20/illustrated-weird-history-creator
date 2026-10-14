from __future__ import annotations

import os
import io
import zipfile
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Weird History Studio", page_icon="🎞️", layout="wide")
st.title("🎞️ Illustrated Weird History Studio")
st.caption("Topic → researched script → neural English narration → original AI scenes → cinematic 16:9 MP4")
st.info("No AI-provider API keys. The first full render downloads open model weights and can be slow on CPU. Kokoro is primary; Piper is neural fallback.")

with st.sidebar:
    st.header("Production settings")
    minutes = st.slider("Target duration", 5, 8, 6)
    voice = st.selectbox("Narrator", ["Warm female documentary (Kokoro af_heart)", "Warm male documentary (Kokoro am_michael)"])
    scene_count = st.slider("AI scenes", 8, 18, 12)
    resolution = st.selectbox("Export resolution", ["1280 × 720 (recommended for free CPU)", "1920 × 1080 (slower)"])
    st.caption("16:9 landscape, 30 fps, H.264/AAC.")

topic_choices = [
    "The Great Molasses Flood of 1919",
    "The Great Emu War",
    "The Cadaver Synod",
    "The London Beer Flood of 1814",
    "The dancing plague of 1518",
    "The Mary Celeste mystery",
    "The Year Without a Summer",
    "The Tunguska event",
    "Custom topic",
]
topic_choice = st.selectbox("Choose a high-curiosity topic", topic_choices, index=0)
custom_topic = st.text_input("Or enter your own topic", placeholder="Type a custom historical topic (optional)")
topic = custom_topic.strip() or ("" if topic_choice == "Custom topic" else topic_choice)
angle = st.text_area(
    "Story angle / opening direction",
    value="Open with the most surprising documented moment. Explain what caused it, the human consequences, and what happened afterward. No slow encyclopedia-style introduction.",
    height=90,
)
generate = st.button("Generate final MP4", type="primary", use_container_width=True)

def dispatch(topic_value: str, duration: int, scenes: int, voice_name: str, output_size: str, angle_value: str) -> tuple[bool, str]:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        try:
            token = st.secrets.get("GITHUB_TOKEN", "")
        except Exception:
            token = ""
    if not token:
        return False, "No GITHUB_TOKEN configured for remote dispatch."
    import requests
    url = "https://api.github.com/repos/miang20/illustrated-weird-history-creator/actions/workflows/build.yml/dispatches"
    response = requests.post(url, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }, json={"ref": "main", "inputs": {
        "topic": topic_value, "duration": str(duration), "scenes": str(scenes),
        "voice": voice_name, "resolution": output_size, "angle": angle_value[:500],
    }}, timeout=30)
    if response.status_code == 204:
        return True, "GitHub Actions accepted the render. Open Actions to monitor it and download the MP4 artifact."
    return False, f"GitHub dispatch failed ({response.status_code}): {response.text[:400]}"


def configured_github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        try:
            token = st.secrets.get("GITHUB_TOKEN", "")
        except Exception:
            token = ""
    return token

def fetch_latest_mp4(token: str):
    import requests
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    runs_response = requests.get(
        "https://api.github.com/repos/miang20/illustrated-weird-history-creator/actions/runs",
        headers=headers, params={"branch": "main", "per_page": 20}, timeout=30,
    )
    runs_response.raise_for_status()
    runs = runs_response.json().get("workflow_runs", [])
    successful = [run for run in runs if run.get("path") == ".github/workflows/build.yml"
                  and run.get("event") in ("workflow_dispatch", "schedule") and run.get("status") == "completed"
                  and run.get("conclusion") == "success"]
    if not successful:
        raise RuntimeError("No successful manual render was found on main yet.")
    run = successful[0]
    artifacts_response = requests.get(
        f"https://api.github.com/repos/miang20/illustrated-weird-history-creator/actions/runs/{run['id']}/artifacts",
        headers=headers, timeout=30,
    )
    artifacts_response.raise_for_status()
    artifact = next((a for a in artifacts_response.json().get("artifacts", [])
                     if a.get("name") == "weird-history-mp4" and not a.get("expired")), None)
    if not artifact:
        raise RuntimeError("The latest successful run has no downloadable artifact; it may have expired.")
    download = requests.get(artifact["archive_download_url"], headers=headers, timeout=180)
    download.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        candidates = [name for name in archive.namelist() if name.endswith("final_weird_history.mp4")]
        if not candidates:
            raise RuntimeError("The artifact ZIP does not contain the final MP4.")
        video_bytes = archive.read(candidates[0])
    return video_bytes, run


if generate:
    if len(topic.strip()) < 4:
        st.error("Enter a clear topic (at least 4 characters).")
        st.stop()
    voice_name = "af_heart" if voice.startswith("Warm female") else "am_michael"
    output_size = "1280x720" if resolution.startswith("1280") else "1920x1080"
    ok, message = dispatch(topic.strip(), minutes, scene_count, voice_name, output_size, angle.strip())
    if ok:
        st.success(message)
        st.link_button("Open GitHub Actions", "https://github.com/miang20/illustrated-weird-history-creator/actions")
    else:
        st.warning(message)
        st.markdown("Remote one-click mode needs a GitHub authorization token in Streamlit secrets (GITHUB_TOKEN). This is not an AI-provider key.")
        st.link_button("Open manual GitHub workflow", "https://github.com/miang20/illustrated-weird-history-creator/actions/workflows/build.yml")
        if os.environ.get("RUN_LOCAL_RENDER", "").lower() == "true":
            from src.render import render_documentary
            with st.status("Building the documentary on this machine…", expanded=True) as status:
                result = render_documentary(topic.strip(), minutes, scene_count, voice_name, output_size, angle.strip(), ROOT / "output")
                status.update(label="Render complete", state="complete")
            st.video(str(result["video"]))
            st.download_button("Download final MP4", result["video"].read_bytes(), file_name=result["video"].name, mime="video/mp4")
        else:
            st.caption("For local rendering, install requirements-render.txt and FFmpeg, then launch with RUN_LOCAL_RENDER=true.")
else:
    cols = st.columns(4)
    cols[0].metric("Duration", f"{minutes} min")
    cols[1].metric("AI scenes", str(scene_count))
    cols[2].metric("Narration", "Kokoro → Piper")
    cols[3].metric("Format", "16:9 MP4")
    st.markdown("No upload is required. Enter a topic and the system researches it, builds narration, generates original illustrated scenes, then assembles a downloadable video.")

st.divider()
st.subheader("Download a finished render")
token_for_download = configured_github_token()
if st.button("Check latest completed MP4", use_container_width=True):
    try:
        with st.spinner("Checking GitHub Actions and retrieving the MP4…"):
            video_bytes, completed_run = fetch_latest_mp4(token_for_download)
        st.session_state["latest_mp4_bytes"] = video_bytes
        st.session_state["latest_mp4_title"] = completed_run.get("display_title", "Weird History documentary")
        st.session_state["latest_mp4_run_url"] = completed_run["html_url"]
    except Exception as exc:
        st.error(str(exc))
if st.session_state.get("latest_mp4_bytes"):
    st.success(f"Ready: {st.session_state.get('latest_mp4_title', 'Weird History documentary')}")
    st.download_button("Download final MP4", st.session_state["latest_mp4_bytes"], file_name="weird_history_final.mp4", mime="video/mp4", use_container_width=True, key="download_latest_mp4")
    st.link_button("View render logs", st.session_state["latest_mp4_run_url"])
if not token_for_download:
    st.caption("No AI API key is needed. Public artifact access will be tried; if GitHub restricts direct download, use the run page to download the artifact. Triggering a remote render directly from this app still needs optional GitHub authorization.")
