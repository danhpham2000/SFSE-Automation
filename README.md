# MVE Patient Profile Automation

This worker reads pending rows from Google Sheets, searches for each patient in My Vision Express, creates the patient if needed, and writes `Y` back to the detected MVE status column only after the patient is confirmed to exist.

## What is included

- No database.
- No background service.
- No tests.
- One bounded batch runner for direct manual execution.

## Required files

- `.env` with `MVE_USERNAME` and `MVE_PASSWORD`
- `credentials.json` for the Google service account

## Install on the Windows machine

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run one batch

```bash
python main.py
```

Optional flags:

```bash
python main.py --limit 1
python main.py --log-level DEBUG
```

## Runtime behavior

- Processes only rows where the status column is blank or `N`
- Scans from the bottom of the sheet upward and takes the first pending rows it finds
- Supports both `MVE Profile Added Y/N` and `MVE Profiled Added Y/N`
- Skips rows missing `First`, `Last`, or `DOB`
- Leaves the sheet unchanged when MVE is uncertain, multiple matches appear, or save/search confirmation fails

## Important note about MVE selectors

The pywinauto automation is implemented against the screen map in the spec. If the Windows machine exposes different control names, adjust the label/button matching logic in [`mve.py`](/Users/danhpham/Desktop/SiteForSoreEyes/mve.py).
