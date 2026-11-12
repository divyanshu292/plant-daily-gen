# TTPS Daily Data Entry

Daily generation data for Tenughat Thermal Power Station (2 x 210 MW).

Each morning the plant prints a one-page **Daily System Report**. Staff photograph it and upload it here. The backend has Google Gemini transcribe the page, checks the page's own arithmetic, and stores the previous day's figures in MongoDB. It also re-implements the formulas of the plant's Excel workbook (`TTPS DAILY GEN DATA 2026-27.xlsx`), so the site can show daily, month-to-date and year-to-date performance: PLF, availability, specific coal and oil, heat rate, outages, stocks and so on.

- `frontend/`: React + Vite site.
- `backend/`: FastAPI API (`main.py`).
  - `extract.py`: prepares the image and calls Gemini.
  - `report_schema.py`: the page as a schema. Every cell is a string.
  - `validate.py`: parses the cells and runs the arithmetic checks.
  - `calc.py`: the workbook's formulas.
  - `workbook_import.py`: reads history from the workbook.

## Upload flow

`POST /api/reports` with the photo:

1. **Transcribe.** The image is upright-rotated from its EXIF data and sent as the whole page plus two enlarged, overlapping half-page crops. Gemini copies every cell exactly as printed. The same call also says whether the image is the TVNL Daily System Report at all; if it isn't, the response is `422`. A file that is not an image gets `415`, and anything over 15 MB gets `413`.
2. **Check the arithmetic.** The printed form is redundant, so `validate.py` recomputes it:
   - Unit 1 + Unit 2 = Station for generation, coal, oil, DM water, H2 and backing down. Outage is checked too, but only as a warning.
   - Road + Rail = Total coal receipt, and Plant + Sub-station = Station aux. power.
   - PLF, availability, specific coal and oil, DM % and APC % recomputed from the cells they depend on.

   Station totals must add up exactly. Generation is the one exception: it is metered to more decimals than the page prints, so it may be out by one unit in the last place.
3. **Save or hold.**
   - If every error-level check passes, the day is **saved** automatically.
   - Otherwise the page is read once more, with the failing cells named in the prompt.
   - If it still does not add up, the report is kept as **needs_review** and nothing is written to the day. A reviewer corrects it and saves it with `POST /api/reports/{id}/confirm` (`{"entry": {...}, "dataDate": "YYYY-MM-DD"}`). `dataDate` is only needed when the printed date was unreadable.

Comparisons with the database are warnings only and never block a save:

- Month-to-date totals, run only once every earlier day of the month is present. The days that are still missing are listed.
- Stock roll-forward: previous stock + receipt - consumption.

Re-uploading a day reports `replaced: true` and lists the fields whose values changed.

**Page images** are stored in MongoDB (`report_images`, as JPEG bytes, at most 1800 px on the long edge) and deleted **15 days after upload** by a TTL index on `createdAt`, so storage stays at a couple of weeks of pages. The report record and the day's figures are kept; only the picture goes. The period is `IMAGE_RETENTION_DAYS` in `backend/main.py`, and the index is updated on the next start if it changes.

**Dates.** The page is published the next morning, so its figures belong to the day before: **data date = printed date - 1 day**. A page printed `4/11/26` (day/month/year) holds the data for 3 Nov 2026. A page dated more than a day in the future is blocked, and an unreadable date sends the report to review.

What the page cannot check: the coal and oil stocks, oil receipt and oil in pipeline have no arithmetic on the page, so a misread there is caught only by the stock roll-forward warning. The 5th decimal of the plant aux. power figure and a few seconds of outage are finer than anything else printed.

## Environment

Put the variables in `.env` in the project root (template: `backend/.env.example`). Docker Compose reads the same file.

| Variable | Needed | Purpose |
|---|---|---|
| `MONGODB_URI` | yes | MongoDB connection string. Without it the API starts, but data endpoints return 503 and `/api/health` reports `database: false`. |
| `MONGODB_DB` | no | Database name (default `ttps`). |
| `GEMINI_API_KEY` | to read images | Google Gemini API key. Without it uploads return 503; everything else works. |
| `EXTRACTION_MODEL` | no | Gemini model that reads the page, or a comma-separated list tried in order when one is overloaded, over quota or too slow (default: `MODELS` in `backend/extract.py`). |
| `PORT` | no | Port for `dev_server.py` (default 8000). |

## Running locally

Python 3.11 or newer.

```sh
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

**Trial run, without a database or an API key:**

```sh
.venv/bin/python dev_server.py
```

- The database is in memory. It is seeded from the workbook if the workbook is in the project root.
- Without `GEMINI_API_KEY`, a stand-in reader replaces Gemini:
  - The two sample pages return their hand-checked transcriptions (recognised by image shape).
  - Any other portrait image returns a page with one wrong digit, to exercise review.
  - A landscape image is rejected as not a report.

**Real backend:** with `.env` filled in, run `.venv/bin/uvicorn main:app --reload` from `backend/`.

**Frontend:** run `npm install && npm run dev` in `frontend/`. It serves on http://localhost:5173 and proxies `/api` to `http://localhost:8000` (override with `VITE_API_URL`).

**Docker:** `docker compose up --build` runs the backend on 8000 and the frontend on 5173.

**Vercel:** `vercel.json` defines two services: `backend/` (FastAPI, `main:app`) and `frontend/` (Vite). Requests to `/api/*` go to the backend with the path unchanged; everything else goes to the frontend. Set `MONGODB_URI`, `MONGODB_DB` and `GEMINI_API_KEY` in the Vercel project's environment variables. Vercel installs `backend/requirements.txt`, which holds runtime dependencies only. Test tools are in `requirements-dev.txt`.

## Importing history from the workbook

The workbook's **DAILY DATA** sheet holds the typed-in figures; the other sheets are derived from it. **TARGET** supplies the monthly targets, and **COAL OIL** the opening stock balances, including the 11 Jun 2026 re-base.

```sh
curl -F "file=@TTPS DAILY GEN DATA 2026-27.xlsx" http://localhost:8000/api/import/workbook
```

- The response gives the fiscal year, the date range, and how many days were `added` or `updated`.
- Days already filled from a report image keep their values. The workbook only adds what the page does not carry (GCV, trips, boiler tube leaks, planned outage).
- Add `?overwrite=true` to let the workbook replace those values.
- Targets and opening stocks are stored per fiscal year. `GET`/`PUT /api/config/{fy}` read and override them.

## Tests

```sh
cd backend
.venv/bin/python -m pytest
```

- No network, database or API key is needed. The API tests use an in-memory database and a fake reader.
- The tests that compare `calc.py` with the workbook's cached values need the workbook in the project root and skip without it. `TTPS_WORKBOOK=/path/to/book.xlsx` points them at a copy elsewhere.
- `tests/fixtures/` holds hand-checked transcriptions of two real pages.

## Where `calc.py` differs from the workbook

Every other figure matches the workbook's cached values (DAILY REPORT, GEN-PLF, COAL OIL, APC and TRIP BTL sheets, every day from 1 Apr to 4 Nov 2026). The differences, all deliberate except the last:

- **Station availability, outage %, loading factor and running hours.** The workbook divides the two units' summed outage hours by one unit's 24 h a day. `calc` uses 48 unit-hours a day, and gives no station running hours.
- **Partial loading (DAILY REPORT rows 29-31).** The workbook subtracts PLF and outage *fractions* from 100, so it always shows about 99 %. `calc` uses percentages.
- **Monthly trips and boiler tube leaks.** These reset on the 1st in `calc`. In 2026 the workbook resets a day late in May, July, August and October (TRIP BTL rows 33, 94, 125, 186).
- **Coal stock on 11 Jun 2026 (not settled as deliberate).** The plant re-based the stock to 297,377.915 MT in 12 June's formula. `calc` treats that figure as the closing stock of 11 June. The workbook still shows the old balance on 11 June. The two agree from 12 June on.

As in the workbook, days without data count as zero in month and year totals. The performance report lists those days.
