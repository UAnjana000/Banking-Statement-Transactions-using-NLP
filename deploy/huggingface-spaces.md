# Deploy FinUnderWrite on Hugging Face Spaces (free)

Hugging Face Spaces offers a free Docker CPU tier (2 vCPU / 16 GB RAM) that fits this app.

## One-time setup

1. Create a free account at https://huggingface.co/join
2. Open https://huggingface.co/new-space
3. Fill in:
   - **Space name:** `FinUnderWrite` (or any name)
   - **SDK:** Docker
   - **Hardware:** CPU Basic (free)
   - **Visibility:** Public (or Private)
4. After the empty Space is created, push this GitHub repo into it (or duplicate files):

```bash
# From this project root (after `huggingface-cli login`)
pip install -U huggingface_hub
huggingface-cli login
huggingface-cli upload YOUR_HF_USERNAME/FinUnderWrite . . \
  --repo-type=space \
  --exclude=".venv/*" \
  --exclude="Banking transactions/*" \
  --exclude=".git/*" \
  --exclude="*.db" \
  --exclude="local.db"
```

Or in the Space **Settings → Repository**, connect / mirror your GitHub repo `UAnjana000/Banking-Statement-Transactions-using-NLP` if you prefer git sync.

5. Confirm the Space README YAML has `sdk: docker` and `app_port: 7860` (already at the top of this repo's `README.md`).
6. Wait for the build. Open the Space URL — UI at `/`, health at `/health`, docs at `/docs`.

## Database (optional)

- **Default:** SQLite inside the container (works with zero config; data resets when the Space sleeps/rebuilds).
- **Persistent:** set Space secret `FINUNDERWRITE_DATABASE_URL` to a free Neon/Supabase Postgres URL (`postgresql+psycopg://...`).

## Notes

- Free Spaces sleep after idle; the first visit wakes them (cold start).
- Scanned-PDF OCR stays offline; native PDF/CSV/XLSX ingest runs in the Space.
