# Push FinUnderWrite into your Hugging Face Docker Space.
# Usage (from project root):
#   .\deploy\push-to-hf-space.ps1
#   .\deploy\push-to-hf-space.ps1 -SpaceId "UAnjana000/AIML"

param(
    [string]$SpaceId = "UAnjana000/AIML"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "Installing/updating huggingface_hub..."
.\.venv\Scripts\python.exe -m pip install -q -U huggingface_hub

Write-Host ""
Write-Host "Login required (browser will open, or paste a token from https://huggingface.co/settings/tokens)."
.\.venv\Scripts\python.exe -c "from huggingface_hub import login; login()"

Write-Host ""
Write-Host "Uploading project to Space: $SpaceId (Docker SDK via README YAML)..."
.\.venv\Scripts\python.exe -c @"
from pathlib import Path
from huggingface_hub import HfApi

space_id = r'$SpaceId'
root = Path(r'$(Get-Location)')
api = HfApi()

ignore = {
    '.venv', '.git', '.mypy_cache', '.pytest_cache', '.ruff_cache',
    'Banking transactions', 'htmlcov', 'models', '__pycache__',
    '.coverage', 'local.db', 'agent-transcripts',
}
suffix_block = {'.db', '.duckdb', '.sqlite3', '.pyc'}

def keep(path: Path) -> bool:
    rel = path.relative_to(root)
    parts = set(rel.parts)
    if parts & ignore:
        return False
    if any(p.startswith('.') and p not in {'.env.example', '.dockerignore', '.gitattributes'} for p in rel.parts[:-1]):
        # allow root dotfiles we care about; skip nested junk
        pass
    if rel.suffix.lower() in suffix_block:
        return False
    if rel.name in {'.coverage', 'Thumbs.db', '.DS_Store'}:
        return False
    if 'Banking transactions' in rel.parts:
        return False
    if '.venv' in rel.parts or '__pycache__' in rel.parts:
        return False
    return True

files = [p for p in root.rglob('*') if p.is_file() and keep(p)]
print(f'Uploading {len(files)} files...')
api.upload_folder(
    folder_path=str(root),
    repo_id=space_id,
    repo_type='space',
    ignore_patterns=[
        '.venv/**',
        '.git/**',
        'Banking transactions/**',
        '**/__pycache__/**',
        '.mypy_cache/**',
        '.pytest_cache/**',
        '.ruff_cache/**',
        'htmlcov/**',
        'models/**',
        '*.db',
        '*.duckdb',
        '*.sqlite3',
        '.coverage',
        '.coverage.*',
        'local.db',
    ],
)
print('Done. Open: https://huggingface.co/spaces/' + space_id)
print('Build may take several minutes. SDK must show Docker (from README.yaml sdk: docker).')
"@

Write-Host ""
Write-Host "If the Space still says Gradio, open https://huggingface.co/spaces/$SpaceId/blob/main/README.md"
Write-Host "and confirm the YAML at the top has: sdk: docker  and  app_port: 7860"
Write-Host "Then Factory reboot from the Space Settings page."
