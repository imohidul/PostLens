# Contributing to PostLens

Thanks for helping! Bug reports, fixes and ideas are all welcome.

## Reporting a bug
Open an [issue](https://github.com/imohidul/PostLens/issues/new/choose) and include:
- your operating system and PostLens version (shown in the sidebar),
- what you did, what you expected, and what happened,
- the log file from `.postlens/logs` in your user folder, if there is one.

**Never paste API keys, cookies or personal data** into issues.

## Setting up for development
```bash
git clone https://github.com/imohidul/PostLens.git
cd PostLens
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt pytest   # Windows: .venv\Scripts\python
cd frontend && npm install && cd ..
```
Run the backend with `python -m uvicorn postlens.server:app --reload --port 8765` and the UI with `npm run dev` inside `frontend/`.

## Before opening a pull request
1. `python -m pytest -q` passes. It includes a scan that fails if anything looks like an API key.
2. If you changed the UI, run `npm run build` in `frontend/` and commit the updated `postlens/static/`.
3. Keep changes focused, and describe *why* in the pull request.

## Where things live
- Facebook layout changes: `postlens/scraper/selectors.py` and `graphql_parser.py`
- Website extraction: `postlens/web/`
- AI providers and speed: `postlens/ai/`
- Recommended local models: `postlens/data/models.json`
