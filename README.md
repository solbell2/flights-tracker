# Flights Tracker

Weekly flight-price monitoring agent. Scrapes Google Flights via the
[`fast-flights`](https://pypi.org/project/fast-flights/) library (with
[SerpAPI](https://serpapi.com/) as a fallback when scraping fails), finds the
top N cheapest round-trip offers per trip across configurable date ranges,
tracks price history in CSVs committed back to the repo, and emails a
two-table summary (with a trend chart) to a list of recipients via Gmail SMTP.

## What it does

1. Reads [config.json](config.json) for origin, destination, currency, passenger
   count, top-N size, and trip date windows.
2. For each trip, searches every (depart, return) date combination where
   `return > depart`.
3. Primary engine: `fast-flights` running a local headless Chromium via
   Playwright. If a search raises *or* returns zero flights and `SERPAPI_KEY`
   is set, retries that date pair against SerpAPI's `google_flights` engine.
4. Appends every offer to [history/all_offers.csv](history/) and writes a
   per-trip summary row to [history/weekly_summary.csv](history/).
5. Computes week-over-week trend (delta vs. previous run, all-time low) and
   renders a PNG line chart of the cheapest price across runs.
6. Sends an HTML email containing **one table per trip** (top N cheapest within
   that trip), clickable price cells linking to that route's Google Flights
   search, the trend bullets, and the inline chart image.

## Editing the config

Open [config.json](config.json) and edit:

- `origin` / `destination`: IATA airport codes (e.g. `SEA`, `XIY`).
- `currency`: display currency for the email.
- `adults`: passenger count.
- `top_n`: how many cheapest offers to show **per trip** in the email.
- `trips`: list of trips, each with a `depart_start`/`depart_end` and
  `return_start`/`return_end` window. The agent searches every combination
  where `return > depart`.
- `recipients`: leave as the placeholder. Real recipient addresses live in
  the `RECIPIENTS` env var (see below) so they don't get committed to a
  public repo. The env var takes precedence over `config.json` at runtime.

## Schedule

Runs every Saturday at 16:23 UTC (9:23 AM PDT / 8:23 AM PST) via
[`.github/workflows/weekly.yml`](.github/workflows/weekly.yml). GitHub
Actions cron does not observe DST, so the local time shifts by one hour
between the summer and winter halves of the year. You can also trigger a
run manually from the GitHub Actions tab using **Run workflow**.

After each run, the workflow commits any new rows in `history/` back to
`main` so the trend chart keeps growing across runs.

## Secrets / env vars

Used by both local runs and the GitHub Actions workflow:

- `GMAIL_USER` — the Gmail address that sends the email.
- `GMAIL_APP_PASSWORD` — a 16-character Gmail app password (not your normal
  Gmail password). Requires 2-Factor Auth on the account; generate one at
  <https://myaccount.google.com/apppasswords>. Paste it without spaces.
- `RECIPIENTS` — comma-separated list of email addresses to send the report
  to (e.g. `a@example.com,b@example.com`). The `To:` header is set to
  `GMAIL_USER`, so each recipient sees only themselves (BCC behavior).
- `SERPAPI_KEY` *(optional but recommended)* — SerpAPI key used as a fallback
  when fast-flights fails or returns no flights for a date pair. Get one at
  <https://serpapi.com/>. Free tier is 100 searches/month; sufficient for
  this agent's usage so long as you don't significantly expand
  `config.json`'s date matrix.

For GitHub Actions, configure these in
**Settings -> Secrets and variables -> Actions** as repository secrets with
the same names.

## Run locally

One-time setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

Create a `.env` file in the repo root (already gitignored):

```
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=your16charpassword
RECIPIENTS=you@gmail.com,someone-else@example.com
SERPAPI_KEY=optional-serpapi-key
```

Then `chmod 600 .env`. To run:

```bash
source .venv/bin/activate
set -a; source .env; set +a
python -u flight_agent.py
```

`-u` makes stdout unbuffered so you see each `Searching ...` line as it
happens. A full run with the default config takes ~2–10 minutes depending
on how many fast-flights searches time out and have to fall back to SerpAPI.

The script writes to `history/` and sends a real email — make sure
`RECIPIENTS` is correct first.

## Reliability / failure modes

- Each fast-flights search has a 30s Playwright timeout. If Google Flights
  renders an unexpected DOM (it sometimes does for date ranges spanning
  major holidays), the selector lookup times out, the exception is caught,
  and the date pair is logged + retried via SerpAPI when configured.
- If both engines fail (or `SERPAPI_KEY` isn't set and fast-flights fails),
  that date pair contributes zero offers; the rest of the run continues.
- If a trip ends up with zero offers, its email section shows
  "No flights found for this trip." instead of a missing table.
- If *all* searches return empty across all trips, an email goes out anyway
  noting that no flights were found this run.

## Output files

- `history/all_offers.csv` — every offer from every run, with timestamp,
  origin, destination, trip name, price, airlines, stops, duration, and
  the dates searched.
- `history/weekly_summary.csv` — one summary row per trip per run
  (`n_offers` / `min_price` / `median_price` / `mean_price` / `max_price`).
  The trend chart is built from this file.

The first run won't include a trend chart — at least two runs of history
are required.
