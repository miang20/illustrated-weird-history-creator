# Usage and deployment

## Generate a video
- Open the repository Actions tab.
- Choose Build Weird History Video and press Run workflow.
- Enter the topic, select 5–8 minutes, choose a Kokoro narrator, and start the run.
- Download the weird-history-mp4 artifact when the render job completes.

## Streamlit front end
The app is in app.py. Deploy it to Streamlit Community Cloud by selecting this repository and app.py. The app itself does not require AI provider keys. To have the hosted app trigger the remote GitHub workflow, add a narrowly scoped GitHub token with Actions: write access as the Streamlit secret GITHUB_TOKEN. If no token is configured, the app links to the manual Actions workflow instead. Never commit the token to this public repository.

## Free-tier and compute notes
- Wikipedia API and open model downloads require no AI provider key.
- GitHub public standard runners have no GPU; SD-Turbo image generation is CPU-based and may be slow.
- The workflow uploads MP4 plus notes for seven days to limit artifact storage.
- A successful Python smoke test is not proof of natural voice quality or successful full rendering; the first full run is the integration test.

The smoke-test workflow invokes pytest as a Python module so the repository root is importable in CI.
