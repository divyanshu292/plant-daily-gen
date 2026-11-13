# TTPS Daily Data Entry

Daily generation data for Tenughat Thermal Power Station (2 x 210 MW).

Each morning the plant prints a one-page **Daily System Report**. Staff photograph it and upload it here. The backend has Google Gemini transcribe the page, checks the page's own arithmetic, and stores the previous day's figures in MongoDB. It also re-implements the formulas of the plant's Excel workbook (`TTPS DAILY GEN DATA 2026-27.xlsx`), so the site can show daily, month-to-date and year-to-date performance: PLF, availability, specific coal and oil, heat rate, outages, stocks and so on.

- `frontend/`: React + Vite site, built for phones first. Tabs: Home (live generation, targets, things to look at, trends), Upload, Report, Data, Logs, Users and Account. Upload is for admins and Users for the super admin only (see [Sign-in and access](#sign-in-and-access)). It can be installed to the home screen (`public/manifest.webmanifest`).
- `backend/`: FastAPI API (`main.py`).
  - `auth.py`: password hashing, session tokens and input checks for sign-in.
  - `extract.py`: prepares the image and calls Gemini.
  - `report_schema.py`: the page as a schema. Every cell is a string.
  - `validate.py`: parses the cells and runs the arithmetic checks.
  - `calc.py`: the workbook's formulas.
  - `analytics.py`: trends and things to look at for the Home screen (`GET /api/analytics?on=YYYY-MM-DD`, default the latest day with data).
  - `live.py`: samples the plant portal's live MW feed every minute and turns a day of it into a load curve, energy, PLF and trips (see [Live generation history](#live-generation-history)).
  - `workbook_import.py`: reads history from the workbook.
  - `logbook_forms.py` and `logbook.py`: the readings staff send on WhatsApp, a feature of its own (see [Readings from WhatsApp messages](#readings-from-whatsapp-messages)).

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
- Unit 1 and Unit 2 generation against the recorded live feed (below), run only when the feed covers at least 95 % of the day. The page may differ from the feed by 3 % or 0.1 MU, whichever is larger.

Re-uploading a day reports `replaced: true` and lists the fields whose values changed.

**Page images** are stored in MongoDB (`report_images`, as JPEG bytes, at most 1800 px on the long edge) and deleted **15 days after upload** by a TTL index on `createdAt`, so storage stays at a couple of weeks of pages. The report record and the day's figures are kept; only the picture goes. The period is `IMAGE_RETENTION_DAYS` in `backend/main.py`, and the index is updated on the next start if it changes.

**Dates.** The page is published the next morning, so its figures belong to the day before: **data date = printed date - 1 day**. A page printed `4/11/26` (day/month/year) holds the data for 3 Nov 2026. A page dated more than a day in the future is blocked, and an unreadable date sends the report to review.

What the page cannot check: the coal and oil stocks, oil receipt and oil in pipeline have no arithmetic on the page, so a misread there is caught only by the stock roll-forward warning. The 5th decimal of the plant aux. power figure and a few seconds of outage are finer than anything else printed.

## Live generation history

The plant portal shows each unit's present load in MW, stamped to the minute in IST, with a new reading every 2 to 4 minutes, about 2 minutes late. It keeps no history, so the backend samples it **every minute** into MongoDB (`live_readings`, one document per sampled minute, with the portal's own stamp as `feedAt`). Only the scheduler writes; opening the app never changes the history. From those samples the backend builds the day's load curve, energy, PLF and trips.

- `GET /api/live-generation` proxies the portal for the Home screen. It never writes. If the portal cannot be reached, it returns the last recorded reading with `"stale": true` on each item.
- `GET|POST /api/live/record` fetches the portal and stores this minute's sample, even if the portal has not published anything new since the last minute. It needs the key in `LIVE_RECORD_KEY`, sent as `?key=` or an `X-Record-Key` header: a wrong or missing key gets `401`, and `503` means the server has no key set. A second call in the same minute keeps the first sample (`"recorded": false`).
- `GET /api/live/day?date=YYYY-MM-DD` (default today, IST) returns the day's readings and its figures:
  - **Energy** is integrated (trapezoids) only over stretches where samples are at most 15 minutes apart. A sample whose portal reading is more than 15 minutes old (the portal was stuck) counts as missing. `hours.covered` says how much of the day that is, PLF is over those hours, and a day is `complete` once they reach 95 % of 24 h.
  - **Events**: a *trip* is a fall from 50 MW or more to under 5 MW between readings at most 10 minutes apart; any other fall under 5 MW is a *stop*; the first reading back at 5 MW or more is *back*. A unit under 5 MW is offline: a stopped unit's feed shows a small non-zero value.
  - The thresholds are constants at the top of `backend/live.py`.

**The scheduler.** An outside scheduler calls the record endpoint every minute; without it nothing is recorded. Vercel's free plan runs its own cron jobs only once a day, so a free external one is used:

1. Generate a key with `openssl rand -hex 16` and set it as `LIVE_RECORD_KEY` in the Vercel project's environment variables. Redeploy so the function sees it.
2. Create a free job at [cron-job.org](https://cron-job.org), run **every 1 minute**, calling `https://<your-app>/api/live/record?key=<LIVE_RECORD_KEY>`. (Sending the key in an `X-Record-Key` header instead keeps it out of request logs; cron-job.org can set headers under the job's advanced settings.)
3. The job's history should show `200` responses with `"recorded": true` every minute.

Each minute is stored once. Samples are deleted **90 days** after they were taken by a TTL index on `ts`: `LIVE_RETENTION_DAYS` in `backend/main.py`, updated on the next start if it changes.

## Readings from WhatsApp messages

Every day the staff of each area send their routine readings on WhatsApp: mills, ID and FD fans, ESP, turbine side, stator water and CW, the generation report, chemistry, the ash silos, fuel oil, the DG sets and ACW. Each message is typed by hand in its own layout, and the same readings are laid out differently by Unit 1 and Unit 2. The **Logs** tab turns them into a fixed set of keys, so one day can be set beside another. It shares nothing with the daily entries or the report pages: its own collection (`logs`), its own routes, its own screen.

**The fixed set** is `backend/logbook_forms.py`: 12 forms and 221 fields. A form is one kind of message, or one piece of equipment in it.

| Form | One per | Fields |
|---|---|---|
| Generation report | day | 15 |
| Mill | mill (1A ... 2F) | 30 |
| ID fan, FD fan | fan (1A ... 2B) | 7 each |
| ESP | unit | 58: current (mA) and voltage (kV) of fields 1A to 7D, fields under voltage, remarks |
| Turbine side | unit | 21 |
| Stator water and CW | unit | 12 |
| Chemical report | day | 28 |
| Silo system | day | 14 |
| Fuel oil | day | 11 |
| DG set | set | 5 |
| ACW and CW valves | day | 13 |

Each field has a key, a label, a unit and a note on how staff write it (`'LPD-Main-2.3' is 2.3; 'L P discharge : 5.7'`). To add a reading, add a field there; nothing else changes.

**Pasting.** A day's messages come in several pieces, at different times. An admin pastes each piece into the Logs tab as it comes, or several together (`POST /api/logs` with `{"text": ..., "date": "YYYY-MM-DD"}`). The next piece can be pasted while the last is still being read: the app reads them one after another, in order, and keeps going while another tab is open. "Save what is copied" sends the clipboard straight to the list. One Gemini call (the same models as the page reader, about 10 to 30 seconds) splits the paste into sections and files each value under its key. The answer's schema lists the keys, so the model cannot return any other. The code in `logbook.py` then does what is not left to the model:

- **Dates** are copied as written and read here, day first (`12.11.2026`, `12 - 11- 2026`, `4/11/26`). Each message is filed under its own date, whatever day is on screen. A message with no date in its heading takes the date of WhatsApp's stamp above it (`[12/11/26, 7:05:12 AM] Name:`, which WhatsApp adds when several messages are copied together); `date` is used only when there is neither. The app sends as `date` the day chosen under the paste box, else the date of the last dated piece pasted in the past 20 minutes (a piece without a date is usually the rest of the message before it), else the day on screen. It is worked out when the piece's turn comes, so it follows a dated piece still being read ahead of it. A date the message does not carry, or one more than a day ahead or a year back, is not believed.
- **Values** are stored as written (`04.80`, `42×100`, `17 to 18`, `Main`). A unit stuck to a number is taken off (`154MW`), and the sign is taken from the line: staff write `:-`, `--` or `.-` between a label and its value, so `tem. :-43` is 43 and only `Vacuum:- -640` is negative. A value written as dashes is stored as `-`, not taken.
- **Every value must be on the line it is said to come from**, as written, or it is marked to check.
- **Numbers left over** on a line that was read are listed with the section, so a dropped value shows.
- **A message that was skipped** (four or more lines with numbers that ended up in no section) is reported when the paste is saved.
- **A reading with no field** is kept with its section under "no field in the fixed set", and a message that fits no form goes whole under "Not in the fixed set". Nothing pasted is dropped, and that list says which fields to add.

**Pieces add up.** What a paste brings is added to what the day already has, section by section, in one MongoDB update per section (so two pastes at once cannot lose either). Each value pasted is set, and a later paste of a reading wins, even over a hand correction. Every other stored value stays, and the pieces of message, extras and left-over numbers are kept once each, so pasting the same text twice changes nothing. An admin can correct a value by hand, mark a section as checked, or remove it. Under the day, "Not here yet" lists the sections that came on the previous day with readings and have not come for this one.

**How long it takes.** The wait is the answer being written: 10 to 20 seconds for a day's messages. A paste whose messages carry WhatsApp's stamps is cut at the stamps and read in up to six parts at once, so several days copied together still take about 15 seconds. Without stamps there is no safe place to cut, so the paste is one request, limited to 300 lines of text (`413` beyond that, and beyond 24,000 characters in all): paste the messages a few at a time, and they are put together by their dates.

**Comparing.** `GET /api/logs?date=YYYY-MM-DD` (default: the latest day with readings) returns the day's sections, every value beside the same value on the last earlier day that section was reported (within 45 days), with the difference for numbers. `&with=YYYY-MM-DD` compares with a chosen day instead. `absent` lists the sections that came on the previous day with readings and have no message for this one. The screen opens on what changed.

**The collection.** `logs` holds one document per day and section (unique on `date` + `section`): `{"date": "2026-11-12", "section": "mill_1a", "form": "mill", "tag": "1A", "values": {"lp_discharge": "5.7", ...}, "src": {"lp_discharge": "L P discharge : 5.7", ...}, "pieces": ["<the message as pasted>", ...], ...}`. Values are the strings as written; numbers are parsed when read. `src` is the line each value came from.

Routes: `GET`/`POST /api/logs`, `PUT /api/logs/{date}/{section}` (`{"key", "value"}` to correct, blank to remove; `{"checked": true}`), `DELETE /api/logs/{date}/{section}`.

Three things in the fixed set are read from the layout rather than stated in the messages, and are worth confirming with the mill staff: in a Unit 1 mill message `Flow :-26/29` is taken as NDE then DE, `Grease pump pr.: 10.0/6.0` as grease pressure then atomising air pressure, and `Reducer oil pressure :- 1.5/4000` as pressure then flow.

## Sign-in and access

Everyone signs in with an email and password. Each person has a name and one of three kinds of access:

| Access | Can |
|---|---|
| Viewer | See everything. Cannot upload, paste, edit, import or manage anyone. |
| Admin | Also upload reports, confirm reviews, edit a day's values, import the workbook, change targets, and paste and correct the readings on the Logs tab. |
| Super admin | Also onboard people (email, name, first password, admin or viewer), switch them between admin and viewer, set a new password for someone who forgot theirs, remove them, and see anyone's activity. There is exactly one. |

- **The super admin** is created from `SUPERADMIN_EMAIL` and `SUPERADMIN_PASSWORD` (and `SUPERADMIN_NAME`, default "Super admin") when the database has none: at startup, and again at sign-in in case the host skipped startup. An existing user is never changed, so editing these settings later does nothing. Without them nobody can sign in, and the startup log says so.
- **Your own account.** Anyone can change their own name and password on the Account tab, and see their activity there: sign-ins, uploads, confirmations, edits, imports, target changes and pasted readings, plus the super admin's changes to users. The newest 200 entries are kept. The email never changes.
- **Sessions** are a random token in an HttpOnly cookie (`ttps_session`, 30 days, `SameSite=Lax`, `Secure` over https). The database keeps only its SHA-256, in the person's document in `users`, the newest 10 per person. Every request looks the person up again, so a change of access or a removal applies at once.
- **Passwords** are 8 to 128 characters, hashed with scrypt from Python's standard library. Five wrong passwords in a row lock the account for 5 minutes (`429`). Changing your password signs out your other devices; a password set by the super admin signs that person out everywhere.
- Without a session every `/api` route answers `401`, and a viewer trying to write gets `403`. Only `/api/health`, sign-in, sign-out and `/api/live/record` (which has its own key) are open.

Routes: `POST /api/auth/login` (`{email, password}`), `POST /api/auth/logout`, `GET`/`PATCH /api/auth/me` (`{name}`), `POST /api/auth/password` (`{currentPassword, newPassword}`), `GET /api/auth/activity`. For the super admin: `GET`/`POST /api/users`, `PATCH`/`DELETE /api/users/{id}`, `POST /api/users/{id}/password` and `GET /api/users/{id}/activity`.

## Environment

Put the variables in `.env` in the project root (template: `backend/.env.example`). Docker Compose reads the same file.

| Variable | Needed | Purpose |
|---|---|---|
| `MONGODB_URI` | yes | MongoDB connection string. Without it the API starts, but data endpoints return 503 and `/api/health` reports `database: false`. |
| `MONGODB_DB` | no | Database name (default `ttps`). |
| `GEMINI_API_KEY` | to read images and messages | Google Gemini API key. Without it report uploads and pasted messages return 503; everything else works. |
| `EXTRACTION_MODEL` | no | Gemini model that reads the page and the pasted messages, or a comma-separated list tried in order when one is overloaded, over quota or too slow (default: `MODELS` in `backend/extract.py`). |
| `LIVE_RECORD_KEY` | for the scheduler | Key for `/api/live/record` (see [Live generation history](#live-generation-history)). Without it that endpoint returns 503 and nothing is recorded. |
| `SUPERADMIN_EMAIL` | to sign in the first time | Email of the super admin, created when the database has none (see [Sign-in and access](#sign-in-and-access)). |
| `SUPERADMIN_PASSWORD` | to sign in the first time | That account's first password, at least 8 characters. Change it on the Account tab afterwards. |
| `SUPERADMIN_NAME` | no | The super admin's name (default "Super admin"). |
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
- Live readings start empty. `DEV_SEED_LIVE=1 .venv/bin/python dev_server.py` fills today up to now with a synthetic day (both units around 140-165 MW, one Unit 2 trip and return). The live feed itself still comes from the real portal.
- The Logs tab starts with three sample days (10 to 12 Nov 2026) built from the two days of messages in `backend/tests/fixtures/logs_*.txt`; the numbers on the earlier of each pair are nudged so there is something to compare. Without `GEMINI_API_KEY` only those two sample pastes can be read.
- Three users are created, one per kind of access, all with the password `ttps-dev-pass`: `super@ttps.local` (super admin), `admin@ttps.local` (admin) and `viewer@ttps.local` (viewer). Startup prints them. `SUPERADMIN_*` is not used here.

**Real backend:** with `.env` filled in, run `.venv/bin/uvicorn main:app --reload` from `backend/`.

**Frontend:** run `npm install && npm run dev` in `frontend/`. It serves on http://localhost:5173 and proxies `/api` to `http://localhost:8000` (override with `VITE_API_URL`).

**Docker:** `docker compose up --build` runs the backend on 8000 and the frontend on 5173.

**Vercel:** `vercel.json` defines two services: `backend/` (FastAPI, `main:app`) and `frontend/` (Vite). Requests to `/api/*` go to the backend with the path unchanged; everything else goes to the frontend. Set `MONGODB_URI`, `MONGODB_DB`, `GEMINI_API_KEY`, `LIVE_RECORD_KEY`, `SUPERADMIN_EMAIL`, `SUPERADMIN_PASSWORD` and `SUPERADMIN_NAME` in the Vercel project's environment variables. `"regions": ["bom1"]` runs the functions in Mumbai, next to the Atlas cluster (GCP asia-south1). Each database round trip is then a few milliseconds instead of a couple of hundred from Vercel's default US region. If the cluster ever moves, move this with it. Vercel installs `backend/requirements.txt`, which holds runtime dependencies only. Test tools are in `requirements-dev.txt`.

## Importing history from the workbook

The workbook's **DAILY DATA** sheet holds the typed-in figures; the other sheets are derived from it. **TARGET** supplies the monthly targets, and **COAL OIL** the opening stock balances, including the 11 Jun 2026 re-base.

Sign in as an admin or the super admin first (shown with a `dev_server.py` user), then send the file with the session cookie:

```sh
curl -c cookies.txt -H "Content-Type: application/json" \
  -d '{"email": "admin@ttps.local", "password": "ttps-dev-pass"}' http://localhost:8000/api/auth/login
curl -b cookies.txt -F "file=@TTPS DAILY GEN DATA 2026-27.xlsx" http://localhost:8000/api/import/workbook
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
- `tests/fixtures/` holds hand-checked transcriptions of two real pages, and two real days of WhatsApp messages (`logs_*.txt`) with the checked reading of each (`logs_*.json`).

## Where `calc.py` differs from the workbook

Every other figure matches the workbook's cached values (DAILY REPORT, GEN-PLF, COAL OIL, APC and TRIP BTL sheets, every day from 1 Apr to 4 Nov 2026). The differences, all deliberate except the last:

- **Station availability, outage %, loading factor and running hours.** The workbook divides the two units' summed outage hours by one unit's 24 h a day. `calc` uses 48 unit-hours a day, and gives no station running hours.
- **Partial loading (DAILY REPORT rows 29-31).** The workbook subtracts PLF and outage *fractions* from 100, so it always shows about 99 %. `calc` uses percentages.
- **Monthly trips and boiler tube leaks.** These reset on the 1st in `calc`. In 2026 the workbook resets a day late in May, July, August and October (TRIP BTL rows 33, 94, 125, 186).
- **Coal stock on 11 Jun 2026 (not settled as deliberate).** The plant re-based the stock to 297,377.915 MT in 12 June's formula. `calc` treats that figure as the closing stock of 11 June. The workbook still shows the old balance on 11 June. The two agree from 12 June on.

As in the workbook, days without data count as zero in month and year totals. The performance report lists those days.
