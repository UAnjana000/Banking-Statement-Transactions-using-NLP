# Deploy FinUnderWrite on Hugging Face Spaces (free)

Hugging Face Spaces offers a free Docker CPU tier (2 vCPU / 16 GB RAM) that fits this app.

## Important

Do **not** follow the Gradio/`app.py`/torch template Hugging Face shows for new Spaces.
FinUnderWrite is a **Docker + FastAPI** app (`sdk: docker`, port `7860`). No Gradio file is needed.

Your Space `UAnjana000/AIML` was created as Gradio — uploading this repo’s README switches it to Docker.

## Fast path (recommended)

From the project root in PowerShell:

```powershell
.\deploy\push-to-hf-space.ps1
# or: .\deploy\push-to-hf-space.ps1 -SpaceId "UAnjana000/AIML"
```

That will:

1. Prompt you to log in to Hugging Face (token from https://huggingface.co/settings/tokens — enable **Write**)
2. Upload this project into the Space
3. Set `sdk: docker` via the README YAML so Spaces builds the `Dockerfile`

Then open https://huggingface.co/spaces/UAnjana000/AIML and wait for the Docker build (several minutes).

## Manual setup (new Space)

1. https://huggingface.co/new-space → SDK **Docker** (not Gradio), hardware **CPU Basic**
2. Run `.\deploy\push-to-hf-space.ps1 -SpaceId "UAnjana000/YourSpaceName"`
3. Confirm README YAML has `sdk: docker` and `app_port: 7860`
4. Open the Space URL — UI `/`, health `/health`, docs `/docs`

## Database (optional)

- **Default:** SQLite inside the container (works with zero config; data resets when the Space sleeps/rebuilds).
- **Persistent:** set Space secret `FINUNDERWRITE_DATABASE_URL` to a free Neon/Supabase Postgres URL (`postgresql+psycopg://...`).

## Notes

- Free Spaces sleep after idle; the first visit wakes them (cold start).
- Scanned-PDF OCR stays offline; native PDF/CSV/XLSX ingest runs in the Space.
