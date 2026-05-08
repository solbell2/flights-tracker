# Flights Tracker

Weekly flight-price monitoring agent. Scrapes Google Flights via the
[`fast-flights`](https://pypi.org/project/fast-flights/) library, finds the
top 5 cheapest round-trip offers across configurable date ranges, tracks price
history in CSVs committed back to the repo, and emails the results (with a
trend chart) to a list of recipients via Gmail SMTP.

## What it does

1. Reads `config.json` for origin, destination, recipients, and trip date ranges.
2. Searches every (depart, return) date combination for each trip.
3. Appends every offer to `history/all_offers.csv` and writes a per-trip
   summary row to `history/weekly_summary.csv`.
4. Computes week-over-week trend (delta vs. previous run, all-time low) and
   renders a PNG line chart of the cheapest price across runs.
5. Sends an HTML email with the top N offers, trend bullets, and an inline
   chart image.

## Editing the config

Open [config.json](config.json) and edit:

- `origin` / `destination`: IATA airport codes (e.g. `SEA`, `XIY`).
- `currency`: display currency for the email.
- `adults`: passenger count.
- `top_n`: how many cheapest offers to show in the email.
- `trips`: list of trips, each with a `depart_start`/`depart_end` and
  `return_start`/`return_end` window. The agent searches every combination
  where `return > depart`.
- `recipients`: list of email addresses to send the report to.

## Schedule

Runs every Saturday at 16:00 UTC (9:00 AM PDT / 8:00 AM PST) via
[`.github/workflows/weekly.yml`](.github/workflows/weekly.yml). GitHub
Actions cron does not observe DST, so the local time shifts by one hour
between the summer and winter halves of the year. You can also trigger a
run manually from the GitHub Actions tab using **Run workflow**.

## GitHub secrets required

Configure these in **Settings -> Secrets and variables -> Actions**:

- `GMAIL_USER` — the Gmail address that sends the email (e.g. `you@gmail.com`).
- `GMAIL_APP_PASSWORD` — a 16-character Gmail app password (not your normal
  Gmail password). Requires 2-Factor Auth on the account; generate one at
  <https://myaccount.google.com/apppasswords>.
- `RECIPIENTS` — comma-separated list of email addresses to send the report
  to (e.g. `a@example.com,b@example.com`). Each recipient is BCC'd.
- `SERPAPI_KEY` *(optional but recommended)* — SerpAPI key used as a fallback
  when fast-flights fails or returns no flights for a date pair. Get one at
  <https://serpapi.com/>. Free tier is 100 searches/month, which fits this
  agent's usage so long as you don't expand `config.json`'s date matrix
  significantly.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

export GMAIL_USER="you@gmail.com"
export GMAIL_APP_PASSWORD="your-16-char-app-password"
python flight_agent.py
```

The script writes to `history/` and sends an email to whatever recipients are
configured in `config.json` — so make sure that list is correct before running.

## Output files

- `history/all_offers.csv` — every offer from every run, with timestamp.
- `history/weekly_summary.csv` — one summary row per trip per run (min /
  median / mean / max price). The trend chart is built from this file.

The first run won't include a trend chart — at least two runs of history are
required.
