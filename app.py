from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
REPO = "miang20/illustrated-weird-history-creator"
ACTIONS_URL = f"https://github.com/{REPO}/actions"
BUILD_URL = f"{ACTIONS_URL}/workflows/build.yml"

st.set_page_config(page_title="Savage Stickman Studio", page_icon="🪨", layout="wide")
st.title("🪨 Savage Stickman Studio")
st.caption("Paste your own script → scene-matched 2D stickman visuals → neural English VO → captions → downloadable 16:9 MP4")
st.info(
    "Manual script is the permanent primary workflow. Your wording is preserved; the app only removes scene headings "
    "from narration and splits the text into timed paragraphs. No AI-provider API key is required. First render can be slow on CPU."
)

with st.sidebar:
    st.header("Production settings")
    minutes = st.slider("Target duration", 5, 8, 5)
    scene_count = st.select_slider("Visual scenes", options=[18, 24, 30, 36], value=30)
    voice = st.selectbox(
        "Narrator",
        ["Warm female documentary (Kokoro af_heart)", "Warm male documentary (Kokoro am_michael)"],
    )
    resolution = st.selectbox(
        "Export resolution",
        ["1920 × 1080 (Full HD)", "1280 × 720 (faster CPU export)"],
    )
    st.caption("16:9 landscape, 30 fps, H.264/AAC. Default is 5 minutes, 30 scenes, 1080p.")

project_title = st.text_input("Video title / project name", value="My Stickman Documentary")
manual_script = st.text_area(
    "MANUAL SCRIPT — paste your complete narration",
    height=360,
    placeholder=(
        "Paste your full script here. You can include headings such as:\n"
        "## SCENE 1 — THE HOOK\n"
        "Your narration goes here...\n\n"
        "## SCENE 2 — THE TWIST\n"
        "Next narration paragraph..."
    ),
    help=(
        "This is a manual-script-only creator. Markdown headings and lines like 'SCENE 1 — THE HOOK' are not spoken. "
        "Use blank lines to separate beats. The script is not rewritten."
    ),
)
script_clean = "\n".join(
    line for line in manual_script.splitlines()
    if not line.strip().startswith("#") and not __import__("re").match(r"(?i)^\s*scene\s+\d+\b", line.strip())
).strip()
word_count = len(script_clean.split())
estimated_minutes = word_count / 135 if word_count else 0
metrics = st.columns(3)
metrics[0].metric("Script words", f"{word_count:,}")
metrics[1].metric("Estimated narration", f"{estimated_minutes:.1f} min" if word_count else "—")
metrics[2].metric("Visual scenes", str(scene_count))
if word_count:
    target_words = minutes * 135
    low, high = int(target_words * 0.90), int(target_words * 1.12)
    if not low <= word_count <= high:
        st.warning(
            f"This script is about {estimated_minutes:.1f} minutes at the current voice pace, while the selected target is "
            f"{minutes} minutes. Choose a matching duration or edit the script before rendering."
        )
    else:
        st.success("Script length is in the expected range for the selected duration.")

def configured_github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        try:
            token = st.secrets.get("GITHUB_TOKEN", "")
        except Exception:
            token = ""
    return token


def dispatch(script_value: str, title_value: str, duration: int, scenes: int, voice_name: str, output_size: str) -> tuple[bool, str]:
    token = configured_github_token()
    if not token:
        return False, "No GITHUB_TOKEN configured for remote dispatch."
    import requests
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/build.yml/dispatches"
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={
            "ref": "main",
            "inputs": {
                "script": script_value,
                "title": title_value[:120],
                "duration": str(duration),
                "scenes": str(scenes),
                "voice": voice_name,
                "resolution": output_size,
            },
        },
        timeout=30,
    )
    if response.status_code == 204:
        return True, "GitHub Actions accepted your manual script. Open Actions to monitor the render and download its MP4 artifact."
    return False, f"GitHub dispatch failed ({response.status_code}): {response.text[:400]}"


def fetch_latest_mp4(token: str):
    import requests
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    runs_response = requests.get(
        f"https://api.github.com/repos/{REPO}/actions/runs",
        headers=headers,
        params={"branch": "main", "per_page": 20},
        timeout=30,
    )
    runs_response.raise_for_status()
    runs = runs_response.json().get("workflow_runs", [])
    successful = [
        run for run in runs
        if run.get("path") == ".github/workflows/build.yml"
        and run.get("event") == "workflow_dispatch"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
    ]
    if not successful:
        raise RuntimeError("No successful manual render was found on main yet.")
    run = successful[0]
    artifacts_response = requests.get(
        f"https://api.github.com/repos/{REPO}/actions/runs/{run['id']}/artifacts",
        headers=headers,
        timeout=30,
    )
    artifacts_response.raise_for_status()
    artifact = next(
        (a for a in artifacts_response.json().get("artifacts", [])
         if a.get("name") == "weird-history-mp4" and not a.get("expired")),
        None,
    )
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


if st.button("Render this script → final MP4", type="primary", use_container_width=True):
    if len(script_clean) < 250:
        st.error("Paste the complete narration first (at least 250 characters).")
        st.stop()
    if len(project_title.strip()) < 3:
        st.error("Enter a short video title so the output can be identified.")
        st.stop()
    voice_name = "af_heart" if voice.startswith("Warm female") else "am_michael"
    output_size = "1920x1080" if resolution.startswith("1920") else "1280x720"
    ok, message = dispatch(script_clean, project_title.strip(), minutes, int(scene_count), voice_name, output_size)
    if ok:
        st.success(message)
        st.link_button("Open GitHub Actions", ACTIONS_URL)
    else:
        st.warning(message)
        st.markdown(
            "Remote one-click rendering requires a GitHub authorization token stored in Streamlit secrets as "
            "`GITHUB_TOKEN`. This is not an AI-provider key. Never put a token in this public repository."
        )
        st.link_button("Open manual render workflow", BUILD_URL)
        if os.environ.get("RUN_LOCAL_RENDER", "").lower() == "true":
            from src.render import render_documentary
            with st.status("Rendering your manual script on this machine…", expanded=True) as status:
                result = render_documentary(
                    topic=project_title.strip(),
                    duration_minutes=minutes,
                    scene_count=int(scene_count),
                    voice=voice_name,
                    resolution=output_size,
                    manual_script=script_clean,
                    output_dir=ROOT / "output",
                )
                status.update(label="Render complete", state="complete")
            st.video(str(result["video"]))
            st.download_button(
                "Download final MP4", result["video"].read_bytes(),
                file_name=result["video"].name, mime="video/mp4",
            )

st.divider()
st.subheader("Download a finished render")
token_for_download = configured_github_token()
if st.button("Check latest completed MP4", use_container_width=True):
    try:
        with st.spinner("Checking GitHub Actions and retrieving the MP4…"):
            video_bytes, completed_run = fetch_latest_mp4(token_for_download)
        st.session_state["latest_mp4_bytes"] = video_bytes
        st.session_state["latest_mp4_title"] = completed_run.get("display_title", "Stickman documentary")
        st.session_state["latest_mp4_run_url"] = completed_run["html_url"]
    except Exception as exc:
        st.error(str(exc))
if st.session_state.get("latest_mp4_bytes"):
    st.success(f"Ready: {st.session_state.get('latest_mp4_title', 'Stickman documentary')}")
    st.download_button(
        "Download final MP4", st.session_state["latest_mp4_bytes"],
        file_name="stickman_documentary.mp4", mime="video/mp4",
        use_container_width=True, key="download_latest_mp4",
    )
    st.link_button("View render logs", st.session_state["latest_mp4_run_url"])
if not token_for_download:
    st.caption(
        "No AI-provider key is needed. Public artifact access will be tried; if GitHub restricts direct download, "
        "download the artifact from the linked Actions run. Triggering a render directly from this app needs optional GitHub authorization."
    )
