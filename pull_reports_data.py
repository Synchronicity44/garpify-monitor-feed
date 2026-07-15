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

def slope_200(tk):
    """Direction of the 200-day average — the primary trend, classic technical-analysis style.

    We measure the 200-day now vs ~one quarter ago and compound-annualize the change, so
    the % reads as the trend's rate. Classification is purely by DIRECTION, with a small
    flat deadband so a barely-moving average isn't called a trend (avoids whipsaw):
      rising  > +2%/yr      falling < -2%/yr      flat / sideways in between
    Needs ~263 daily closes (200 to average, ending ~63 trading days back). If the
    history is short, returns (None, None) and the reader falls back to a level-only read.
    """
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=430)).isoformat()   # ~300 trading days of cushion
    h = _get(f"{FMP}/historical-price-eod/light?symbol={tk}&from={start}&to={today.isoformat()}&apikey={KEY}")
    rows = h if isinstance(h, list) else h.get("historical") if isinstance(h, dict) else None
    if not rows:
        return None, None
    # ascending by date; each row has 'date' and 'price' (close) on the light endpoint
    closes = [r.get("price") for r in sorted(rows, key=lambda r: r.get("date","")) if r.get("price") is not None]
    LOOK = 63                                    # ~one quarter of trading days
    if len(closes) < 200 + LOOK:
        return None, None
    sma = lambda end: sum(closes[end-200:end]) / 200.0
    now200, past200 = sma(len(closes)), sma(len(closes) - LOOK)
    if past200 <= 0:
        return None, None
    ann = round((( now200 / past200) ** (252.0 / LOOK) - 1) * 100, 1)   # compound-annualized 200-day slope
    trend = "rising" if ann > 2 else ("falling" if ann < -2 else "sideways")   # direction, small flat deadband
    return trend, ann

def one(tk):
    q = _get(f"{FMP}/quote?symbol={tk}&apikey={KEY}")
    q = q[0] if isinstance(q, list) and q else {}
    try:
        trend200, slope200 = slope_200(tk)
    except Exception:
        trend200, slope200 = None, None
    est = _get(f"{FMP}/analyst-estimates?symbol={tk}&period=annual&limit=10&apikey={KEY}")
    fwd_eps = fwd_growth = None
    if isinstance(est, list) and est:
        # one entry per fiscal year, dated at year-end. Keep the years whose end is still
        # in the FUTURE (the current forward fiscal year onward), nearest first.
        today = datetime.date.today().isoformat()
        fwd = sorted([e for e in est if e.get("date") and e.get("epsAvg")], key=lambda e: e["date"])
        fwd = [e for e in fwd if e["date"] > today]
        if fwd and fwd[0]["epsAvg"] > 0:
            fwd_eps = round(fwd[0]["epsAvg"], 2)                      # next fiscal year's expected EPS
            if len(fwd) > 1 and fwd[1].get("epsAvg"):
                fwd_growth = round((fwd[1]["epsAvg"] / fwd_eps - 1) * 100, 1)   # next -> following year
    price = q.get("price")
    return {
        "price": price,
        "ma50": q.get("priceAvg50"), "ma200": q.get("priceAvg200"),
        "yearHigh": q.get("yearHigh"), "yearLow": q.get("yearLow"),
        "fwd_eps": fwd_eps, "fwd_growth": fwd_growth,
        "trend200": trend200, "slope200_ann": slope200,   # primary-trend direction (rising/falling/flat)
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
