# Illustrated Weird History Creator

Free-first, no AI-provider API key, topic-to-16:9 documentary creator.

## Features
- Streamlit topic-to-video UI.
- Research via Wikipedia's public API.
- Structured English narration with source notes.
- Kokoro neural TTS primary, Piper neural TTS fallback.
- Original AI scenes via Stable Diffusion Turbo, downloaded and run locally on CPU.
- FFmpeg pan/zoom, captions, generated ambient music, MP4.
- GitHub Actions manual rendering and downloadable artifact.
- Lightweight smoke tests on pushes.

## Important limits
- GitHub public runners provide CPU, not a GPU. Image generation may be slow and first run downloads several GB of weights.
- No AI-provider API keys are required. Public model downloads and Wikipedia are used.
- To let a separately hosted Streamlit app remotely trigger GitHub Actions, it needs a GitHub authorization token in Streamlit secrets as GITHUB_TOKEN. This is not an AI-provider key. Without it, run the workflow from the repository Actions tab.
- The app records its research source and avoids invented quotes, but generated narration still needs editorial review for important factual claims.
- Generated illustrations are not authentic historical photographs.

## Run locally
Python 3.11 and FFmpeg recommended. Install requirements.txt and requirements-render.txt, then launch app.py with Streamlit.

## GitHub Actions
Weekly schedule runs automatically with a rotating no-key topic. For an on-demand render, open Actions > Build Weird History Video > Run workflow, optionally enter a topic, choose 5–8 minutes, then download the weird-history-mp4 artifact. Pushes run smoke tests only.

## Voice policy
Kokoro af_heart is primary; Piper en_US-lessac-medium is fallback. The code never silently substitutes eSpeak or another robotic system voice. If both neural engines fail, the render fails visibly.

## Source layout
app.py; src/story.py; src/voice.py; src/visuals.py; src/render.py; tests/test_story.py; .github/workflows/build.yml.
