# OQUAT Website — Local Setup

## Prerequisites
- **Python 3.10 or 3.11** (NOT 3.13/3.14 — passlib 1.7.4 and python-jose 3.3.0
  predate the removal of the `crypt` module and will fail on auth)
- **Node 20 LTS** (react-scripts 5.0.1 predates Node 22+)
- Do NOT place this folder inside OneDrive. OneDrive partially syncs
  node_modules and venv, which produces missing-module errors that look like
  install failures but aren't.

## Backend

```powershell
cd Arcturus_Tool-main

py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1

# must print a path INSIDE venv - if it prints C:\Python3xx you are not in the venv
python -c "import sys; print(sys.executable)"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

$env:GROQ_API_KEY="your_key_here"
$env:AI_PROVIDER="groq"

python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Always use `python -m uvicorn`, never bare `uvicorn` — bare resolves through
PATH and can silently pick a different interpreter.

Check: http://localhost:8000/health → `{"status":"healthy","database":"connected"}`

## Frontend

```powershell
cd frontend
copy .env.local.example .env.local     # points the UI at localhost:8000
npm install
npm start
```

Without `.env.local` the frontend calls the **deployed** backend, not yours —
you would be testing the old unpatched code.

## Verify the parity fix

```powershell
curl.exe -X POST http://localhost:8000/scrape -H "Content-Type: application/json" -d "{\"url\":\"https://docs.oracle.com/en/cloud/saas/readiness/scm/26b/inv26b/26B-inventory-wn-t73741.htm\"}"
```

Expected:
- `"count": 61`
- `"release_version": "26B"`
- no `t73741.htm/` inside any feature URL

If you see 62, `26A`, or that path segment, the old `backend/main.py` is loaded.

## Notes
- `.env` is supported via python-dotenv if you prefer a file over env vars.
- First `/extract` run takes several minutes: `OQUAT_REQUEST_DELAY_SECONDS`
  defaults to 7.0s between AI calls.
