#!/usr/bin/env python3
"""GARPify reports — DAILY data layer producer.

The fast-moving numbers every report (and the monitor) needs, per company, pulled
once and published as one small JSON. Runs on a schedule (GitHub Actions, market
hours) exactly like pull_monitor_quotes.py — no key in the browser.

  price, 50-day, 200-day, 52-wk high/low   -> the current price + trend reads
  forward EPS + forward growth              -> the GARP-native PEG (fwd P/E / fwd growth)

The slow layer (46-quarter / 13-year fundamentals history) is a separate quarterly
rebuild from SEC (feed.py); this file owns only the daily current values.

  export FMP_KEY=...
  python3 pull_reports_data.py            # writes reports_data.json next to this file
"""
import os, sys, json, datetime, urllib.request, pathlib

TICKERS = ["NVDA","TSM","AVGO","FIX","ETN","HEI","TDG","HWM","SPGI","MCO","MSCI",
           "TJX","ROST","BURL","ISRG","SYK","GMED","WM","RSG","WCN"]
KEY = os.environ.get("FMP_KEY", "")
FMP = "https://financialmodelingprep.com/stable"
OUT = pathlib.Path(__file__).with_name("reports_data.json")

def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "GARPify-reports"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())

def one(tk):
    q = _get(f"{FMP}/quote?symbol={tk}&apikey={KEY}")
    q = q[0] if isinstance(q, list) and q else {}
    est = _get(f"{FMP}/analyst-estimates?symbol={tk}&period=annual&limit=2&apikey={KEY}")
    fwd_eps = fwd_growth = None
    if isinstance(est, list) and est:
        fwd_eps = est[0].get("estimatedEpsAvg") or est[0].get("epsAvg")
        nxt = (est[1].get("estimatedEpsAvg") or est[1].get("epsAvg")) if len(est) > 1 else None
        if fwd_eps and nxt and fwd_eps > 0:
            fwd_growth = round((nxt / fwd_eps - 1) * 100, 1)
    price = q.get("price")
    return {
        "price": price,
        "ma50": q.get("priceAvg50"), "ma200": q.get("priceAvg200"),
        "yearHigh": q.get("yearHigh"), "yearLow": q.get("yearLow"),
        "fwd_eps": fwd_eps, "fwd_growth": fwd_growth,
        # spot trailing P/E is computed at rebuild time from price / trailing EPS;
        # trailing EPS lives in the quarterly layer, so we publish the raw price here.
    }

def main():
    if not KEY:
        raise SystemExit("FMP_KEY not set")
    data, missing = {}, []
    for tk in TICKERS:
        try:
            d = one(tk)
            if d.get("price") is None: missing.append(tk)
            data[tk] = d
        except Exception as e:
            missing.append(tk); print(f"  {tk}: {e}")
    payload = {
        "asof": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "count": len([t for t in TICKERS if t not in missing]),
        "missing": missing,
        "companies": data,
    }
    tmp = OUT.with_suffix(".json.tmp"); tmp.write_text(json.dumps(payload, separators=(",", ":")))
    tmp.replace(OUT)
    print(f"wrote {OUT.name} — {payload['count']}/{len(TICKERS)} companies" + (f" | MISSING {missing}" if missing else ""))

if __name__ == "__main__":
    main()
