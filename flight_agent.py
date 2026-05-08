import io
import json
import os
import smtplib
from datetime import date, datetime, timedelta
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from itertools import product
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from fast_flights import FlightData, Passengers, Result, get_flights

with open("config.json") as f:
    cfg = json.load(f)

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PW = os.environ["GMAIL_APP_PASSWORD"]

HISTORY_DIR = Path("history")
HISTORY_DIR.mkdir(exist_ok=True)
ALL_OFFERS_CSV = HISTORY_DIR / "all_offers.csv"
WEEKLY_SUMMARY_CSV = HISTORY_DIR / "weekly_summary.csv"


def daterange(start_str, end_str):
    start = date.fromisoformat(start_str)
    end = date.fromisoformat(end_str)
    for i in range((end - start).days + 1):
        yield (start + timedelta(days=i)).isoformat()


def search_fast_flights(origin, destination, depart, ret, adults):
    try:
        result: Result = get_flights(
            flight_data=[
                FlightData(date=depart, from_airport=origin, to_airport=destination),
                FlightData(date=ret,    from_airport=destination, to_airport=origin),
            ],
            trip="round-trip",
            seat="economy",
            passengers=Passengers(adults=adults, children=0, infants_in_seat=0,
                                  infants_on_lap=0),
            fetch_mode="fallback",
        )
        return result.flights or []
    except Exception as e:
        print(f"  ! fast-flights error for {depart}->{ret}: {e}")
        return []


def parse_price(price_str):
    if not price_str:
        return None
    cleaned = "".join(c for c in str(price_str) if c.isdigit() or c == ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def summarize_flight(f, depart, ret, currency):
    price = parse_price(f.price)
    if price is None:
        return None
    return {
        "price": price,
        "currency": currency,
        "depart_date": depart,
        "return_date": ret,
        "airlines": f.name or "Unknown",
        "stops": f.stops if f.stops is not None else -1,
        "duration": f.duration or "",
    }


def collect_all_offers():
    all_offers = []
    for trip in cfg["trips"]:
        print(f"\n=== {trip['name']} ===")
        deps = list(daterange(trip["depart_start"], trip["depart_end"]))
        rets = list(daterange(trip["return_start"], trip["return_end"]))
        for dep, ret in product(deps, rets):
            if date.fromisoformat(ret) <= date.fromisoformat(dep):
                continue
            print(f"  Searching {dep} -> {ret} ...")
            raw = search_fast_flights(cfg["origin"], cfg["destination"],
                                      dep, ret, cfg["adults"])
            for f in raw:
                s = summarize_flight(f, dep, ret, cfg["currency"])
                if s:
                    s["trip_name"] = trip["name"]
                    all_offers.append(s)
    return all_offers


def append_to_history(offers, run_timestamp):
    if not offers:
        return
    df_new = pd.DataFrame(offers)
    df_new.insert(0, "run_timestamp", run_timestamp)
    df_new.insert(1, "origin", cfg["origin"])
    df_new.insert(2, "destination", cfg["destination"])
    if ALL_OFFERS_CSV.exists():
        df_new.to_csv(ALL_OFFERS_CSV, mode="a", header=False, index=False)
    else:
        df_new.to_csv(ALL_OFFERS_CSV, index=False)

    summary_rows = []
    for trip_name, group in df_new.groupby("trip_name"):
        summary_rows.append({
            "run_timestamp": run_timestamp,
            "origin": cfg["origin"],
            "destination": cfg["destination"],
            "trip_name": trip_name,
            "currency": cfg["currency"],
            "n_offers": len(group),
            "min_price": group["price"].min(),
            "median_price": group["price"].median().round(2),
            "mean_price": group["price"].mean().round(2),
            "max_price": group["price"].max(),
        })
    df_summary = pd.DataFrame(summary_rows)
    if WEEKLY_SUMMARY_CSV.exists():
        df_summary.to_csv(WEEKLY_SUMMARY_CSV, mode="a", header=False, index=False)
    else:
        df_summary.to_csv(WEEKLY_SUMMARY_CSV, index=False)


def compute_trends():
    if not WEEKLY_SUMMARY_CSV.exists():
        return {}
    df = pd.read_csv(WEEKLY_SUMMARY_CSV)
    df = df[(df["origin"] == cfg["origin"]) & (df["destination"] == cfg["destination"])]
    trends = {}
    for trip_name, group in df.groupby("trip_name"):
        group = group.sort_values("run_timestamp")
        if len(group) < 2:
            trends[trip_name] = {
                "current": group["min_price"].iloc[-1], "delta": None,
                "pct": None, "history_count": len(group),
                "all_time_min": group["min_price"].min(),
            }
            continue
        current = group["min_price"].iloc[-1]
        previous = group["min_price"].iloc[-2]
        delta = current - previous
        pct = (delta / previous) * 100 if previous else 0
        trends[trip_name] = {
            "current": current, "previous": previous,
            "delta": delta, "pct": pct,
            "history_count": len(group),
            "all_time_min": group["min_price"].min(),
        }
    return trends


def make_trend_chart():
    if not WEEKLY_SUMMARY_CSV.exists():
        return None
    df = pd.read_csv(WEEKLY_SUMMARY_CSV)
    df = df[(df["origin"] == cfg["origin"]) & (df["destination"] == cfg["destination"])]
    if df.empty or df["run_timestamp"].nunique() < 2:
        return None
    df["run_timestamp"] = pd.to_datetime(df["run_timestamp"])
    fig, ax = plt.subplots(figsize=(8, 4))
    for trip_name, group in df.groupby("trip_name"):
        group = group.sort_values("run_timestamp")
        ax.plot(group["run_timestamp"], group["min_price"], marker="o", label=trip_name)
    ax.set_title(f"Cheapest price over time: {cfg['origin']} -> {cfg['destination']}")
    ax.set_ylabel(f"Price ({cfg['currency']})")
    ax.set_xlabel("Run date")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return buf.getvalue()


def build_email_html(top_offers, trends, has_chart):
    rows = ""
    for i, o in enumerate(top_offers, 1):
        rows += f"""
        <tr>
          <td>{i}</td>
          <td><b>{o['currency']} {o['price']:.2f}</b></td>
          <td>{o['trip_name']}</td>
          <td>{o['depart_date']} -> {o['return_date']}</td>
          <td>{o['airlines']}</td>
          <td>{o['stops']}</td>
          <td>{o['duration']}</td>
        </tr>"""

    trend_html = "<h3>Week-over-week trends</h3><ul>"
    for trip_name, t in trends.items():
        if t["delta"] is None:
            trend_html += (f"<li><b>{trip_name}</b>: {cfg['currency']} {t['current']:.2f} "
                           f"(first data point - trend available next week)</li>")
        else:
            arrow = "DOWN" if t["delta"] < 0 else ("UP" if t["delta"] > 0 else "FLAT")
            color = "green" if t["delta"] < 0 else ("red" if t["delta"] > 0 else "gray")
            at_min = " <b>all-time low</b>" if t["current"] <= t["all_time_min"] else ""
            trend_html += (
                f"<li><b>{trip_name}</b>: {cfg['currency']} {t['current']:.2f} "
                f"<span style='color:{color}'>{arrow} {t['delta']:+.2f} "
                f"({t['pct']:+.1f}%)</span> vs last week "
                f"(history: {t['history_count']} weeks, all-time low "
                f"{cfg['currency']} {t['all_time_min']:.2f}){at_min}</li>"
            )
    trend_html += "</ul>"
    chart_html = '<img src="cid:trendchart" style="max-width:100%">' if has_chart else ""

    return f"""
    <html><body style="font-family:Arial,sans-serif">
    <h2>Top {cfg['top_n']} cheapest: {cfg['origin']} -> {cfg['destination']}</h2>
    <p>Run: {date.today().isoformat()}</p>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse">
      <tr style="background:#f0f0f0">
        <th>#</th><th>Price</th><th>Trip</th><th>Dates</th>
        <th>Airline(s)</th><th>Stops</th><th>Duration</th>
      </tr>
      {rows}
    </table>
    {trend_html}
    {chart_html}
    <p style="color:#777;font-size:12px">
      Source: Google Flights via fast-flights. Edit config.json to change route or dates.
    </p>
    </body></html>
    """


def send_email(html_body, subject, chart_png):
    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = ", ".join(cfg["recipients"])
    alt = MIMEMultipart("alternative")
    msg.attach(alt)
    alt.attach(MIMEText(html_body, "html"))
    if chart_png:
        img = MIMEImage(chart_png)
        img.add_header("Content-ID", "<trendchart>")
        img.add_header("Content-Disposition", "inline", filename="trend.png")
        msg.attach(img)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PW)
        server.sendmail(GMAIL_USER, cfg["recipients"], msg.as_string())
    print(f"Email sent to {len(cfg['recipients'])} recipient(s).")


def main():
    run_ts = datetime.utcnow().isoformat(timespec="seconds")
    offers = collect_all_offers()
    print(f"\nCollected {len(offers)} total offers.")
    append_to_history(offers, run_ts)
    trends = compute_trends()
    chart_png = make_trend_chart()

    if not offers:
        send_email("<p>No flights found this week. fast-flights returned empty for all date combinations.</p>",
                   f"Flight agent: no results {date.today()}", None)
        return

    top = sorted(offers, key=lambda x: x["price"])[: cfg["top_n"]]
    html = build_email_html(top, trends, chart_png is not None)
    subject = (f"Top {cfg['top_n']} cheapest {cfg['origin']}->{cfg['destination']} "
               f"flights - {date.today().isoformat()}")
    send_email(html, subject, chart_png)


if __name__ == "__main__":
    main()
