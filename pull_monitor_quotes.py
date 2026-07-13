#!/usr/bin/env python3
"""GARPify monitor — quote producer (the DAILY/live layer).

Pulls a batch quote for the coverage list and writes a small JSON the published
members' monitor reads. Run it on a schedule (every ~15 min during market hours);
the page just fetches the file, so no API key is ever exposed in the browser.

  export FMP_KEY=...                 # your Financial Modeling Prep key
  python3 pull_monitor_quotes.py     # writes monitor_quotes.json next to this file

Only the fast-moving fields live here (price, 50/200-day, 52-wk range). The slow
layer — fundamentals + guidance (FUND / GUID) — is baked into the page and refreshed
on the quarterly rebuild, not here.
"""
import os, sys, json, time, urllib.request, datetime, pathlib

TICKERS = ["NVDA","TSM","AVGO","FIX","ETN","HEI","TDG","HWM","SPGI","MCO","MSCI",
           "TJX","ROST","BURL","ISRG","SYK","GMED","WM","RSG","WCN"]
KEY = os.environ.get("FMP_KEY", "")
OUT = pathlib.Path(__file__).with_name("monitor_quotes.json")
FIELDS = ("symbol","price","priceAvg50","priceAvg200","yearHigh","yearLow")

def fetch_quotes():
    if not KEY:
        raise SystemExit("FMP_KEY not set")
    # Modern /stable/ endpoint, one symbol per call (20 calls; well under the Starter 300/min limit).
    out = []
    for t in TICKERS:
        url = "https://financialmodelingprep.com/stable/quote?symbol=%s&apikey=%s" % (t, KEY)
        req = urllib.request.Request(url, headers={"User-Agent": "GARPify-monitor"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.loads(r.read())
            q = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})
            if q.get("symbol"):
                out.append({k: q.get(k) for k in FIELDS})
        except Exception as e:
            print("  %s: %s" % (t, e))   # skip; it'll show up in 'missing'
    return out

def main():
    quotes = fetch_quotes()
    got = {q["symbol"] for q in quotes}
    missing = [t for t in TICKERS if t not in got]
    payload = {
        "asof": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "count": len(quotes),
        "missing": missing,          # surfaced so a bad pull is visible, never silent
        "quotes": quotes,
    }
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    tmp.replace(OUT)                 # atomic swap so the page never reads a half-written file
    print("wrote %s — %d quotes%s" % (OUT.name, len(quotes),
          (" | MISSING: " + ",".join(missing)) if missing else ""))

if __name__ == "__main__":
    main()
