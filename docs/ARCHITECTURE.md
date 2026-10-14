# Architecture

1. Research: Wikipedia public API is used as a no-key source for a selected topic. The source URL is written into sources.json.
2. Narration: Kokoro neural English TTS is attempted first. If it cannot initialize or generate speech, Piper neural TTS is attempted. If both fail, the job stops rather than silently producing robotic eSpeak audio.
3. Images: Stable Diffusion Turbo is downloaded from its public model repository and run locally with CPU-compatible one-step inference. No hosted image-generation API key is used.
4. Assembly: FFmpeg animates stills with subtle zoom, concatenates scenes, burns captions, mixes a generated low-volume ambient bed, normalizes narration, and exports H.264/AAC.
5. Delivery: GitHub Actions stores the MP4 and script/source/report artifacts for two days.

A remote Streamlit app cannot securely dispatch a private-action API call without GitHub authorization. The app therefore supports optional GITHUB_TOKEN dispatch; otherwise it links directly to the manual workflow. No credentials belong in committed source.
