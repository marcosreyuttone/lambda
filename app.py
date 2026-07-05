#!/usr/bin/env python3
"""
Neocloud Intelligence Map
=========================

Builds and serves an interactive map of "neocloud" GPU compute providers
(CoreWeave, Lambda, Crusoe, Nebius, ...) plus the data-center "landlords"
that host them (Applied Digital, Core Scientific).

Data model
----------
* data/neoclouds_curated.json -- the hand-curated source of truth: revenue,
  GPU counts, chips, sites, ownership, customers & contract terms, bonds,
  GPU rental pricing, the risk methodology, and the financing/compute-flow
  graph. Each company carries a `sources` array of public links.

Live free-API enrichment (no API keys required)
-----------------------------------------------
On every build the app pulls, for the public companies, live figures from
three free/keyless sources and merges them into the output:

* SEC EDGAR companyfacts (data.sec.gov) -- real revenue, cost of revenue,
  gross/operating/net margin, total debt, net PP&E (a proxy for GPU book
  value) and cash, straight from XBRL filings. Public filers only.
* US Treasury daily par yield curve (home.treasury.gov) -- the risk-free
  benchmark used to compute an indicative spread for each tracked bond.
* Yahoo Finance chart endpoint -- live share price and 52-week range for
  the listed tickers.

If any live source fails (no network, rate-limited, etc.) the build logs a
warning and falls back to the curated figures, so the map always works.

Usage
-----
    python3 app.py                  # live-enrich + build + serve + open browser
    python3 app.py --no-live        # skip live APIs, use curated data only
    python3 app.py --no-browser     # don't auto-open a browser
    python3 app.py --port 9000      # pick a port
    python3 app.py --build-only     # just (re)build data/neoclouds.json and exit
"""

import argparse
import csv
import io
import json
import os
import sys
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
CURATED_PATH = os.path.join(DATA_DIR, "neoclouds_curated.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "neoclouds.json")

# SEC asks for a descriptive User-Agent with contact info on its APIs.
UA = "neocloud-intelligence-map (contact: marcosreyuttone@gmail.com)"

EDGAR_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
TREASURY_CSV = ("https://home.treasury.gov/resource-center/data-chart-center/"
                "interest-rates/daily-treasury-rates.csv/{year}/all"
                "?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv")
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=1d"

# XBRL concept fallbacks (companies tag the same line differently).
REV_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
            "RevenueFromContractWithCustomerIncludingAssessedTax"]
COST_TAGS = ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfServices"]
OPINC_TAGS = ["OperatingIncomeLoss"]
NETINC_TAGS = ["NetIncomeLoss"]
DEBT_TAGS = ["LongTermDebt", "LongTermDebtNoncurrent", "DebtLongtermAndShorttermCombinedAmount"]
PPE_TAGS = ["PropertyPlantAndEquipmentNet"]
CASH_TAGS = ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]


def _http_json(url):
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urlopen(req, timeout=30) as r:
        return json.load(r)


def _http_text(url):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _days(start, end):
    try:
        a = datetime.strptime(start, "%Y-%m-%d")
        b = datetime.strptime(end, "%Y-%m-%d")
        return (b - a).days
    except Exception:
        return None


def _first_tag(gaap, tags):
    for t in tags:
        if t in gaap:
            return gaap[t]
    return None


def _usd_points(fact):
    if not fact:
        return []
    units = fact.get("units", {})
    for key in ("USD", "usd"):
        if key in units:
            return units[key]
    # fall back to whatever unit is present
    return next(iter(units.values()), []) if units else []


def _latest_instant(fact):
    """Latest balance-sheet value (points have `end`, no meaningful duration)."""
    pts = _usd_points(fact)
    pts = [p for p in pts if p.get("val") is not None and p.get("end")]
    if not pts:
        return None
    pts.sort(key=lambda p: p["end"])
    return {"val": pts[-1]["val"], "end": pts[-1]["end"]}


def _latest_duration(fact, lo, hi):
    """Latest income-statement value whose period length (days) is in [lo,hi]."""
    pts = _usd_points(fact)
    out = []
    for p in pts:
        if p.get("val") is None or not p.get("start") or not p.get("end"):
            continue
        d = _days(p["start"], p["end"])
        if d is not None and lo <= d <= hi:
            out.append(p)
    if not out:
        return None
    out.sort(key=lambda p: p["end"])
    return {"val": out[-1]["val"], "end": out[-1]["end"], "start": out[-1]["start"]}


def _margins(rev, cost, opinc, netinc):
    m = {}
    if rev and rev.get("val"):
        r = rev["val"]
        m["revenue"] = r
        m["period_end"] = rev["end"]
        if cost and cost.get("val") is not None:
            gp = r - cost["val"]
            m["gross_profit"] = gp
            m["gross_margin_pct"] = round(100.0 * gp / r, 1)
        if opinc and opinc.get("val") is not None:
            m["operating_income"] = opinc["val"]
            m["operating_margin_pct"] = round(100.0 * opinc["val"] / r, 1)
        if netinc and netinc.get("val") is not None:
            m["net_income"] = netinc["val"]
            m["net_margin_pct"] = round(100.0 * netinc["val"] / r, 1)
    return m or None


def fetch_edgar(cik):
    """Return live financials for one CIK, or None on failure."""
    try:
        facts = _http_json(EDGAR_FACTS.format(cik=cik))
    except (URLError, HTTPError, ValueError, TimeoutError) as e:
        print(f"  ! EDGAR {cik}: {e}")
        return None
    gaap = facts.get("facts", {}).get("us-gaap", {})
    if not gaap:
        return None
    rev = _first_tag(gaap, REV_TAGS)
    cost = _first_tag(gaap, COST_TAGS)
    opinc = _first_tag(gaap, OPINC_TAGS)
    netinc = _first_tag(gaap, NETINC_TAGS)
    debt = _first_tag(gaap, DEBT_TAGS)
    ppe = _first_tag(gaap, PPE_TAGS)
    cash = _first_tag(gaap, CASH_TAGS)

    annual = _margins(_latest_duration(rev, 350, 380), _latest_duration(cost, 350, 380),
                      _latest_duration(opinc, 350, 380), _latest_duration(netinc, 350, 380))
    quarter = _margins(_latest_duration(rev, 80, 100), _latest_duration(cost, 80, 100),
                       _latest_duration(opinc, 80, 100), _latest_duration(netinc, 80, 100))
    bal_debt = _latest_instant(debt)
    bal_ppe = _latest_instant(ppe)
    bal_cash = _latest_instant(cash)
    balance = None
    if any([bal_debt, bal_ppe, bal_cash]):
        balance = {
            "period_end": (bal_ppe or bal_debt or bal_cash)["end"],
            "total_debt": bal_debt["val"] if bal_debt else None,
            "ppe_net": bal_ppe["val"] if bal_ppe else None,
            "cash": bal_cash["val"] if bal_cash else None,
        }
    if not any([annual, quarter, balance]):
        return None
    return {"source": "SEC EDGAR (companyfacts XBRL)", "cik": cik,
            "annual": annual, "latest_quarter": quarter, "balance": balance}


def fetch_treasury():
    """Latest US Treasury par yields, {tenor_years: pct}. None on failure."""
    year = datetime.now(timezone.utc).year
    for y in (year, year - 1):
        try:
            text = _http_text(TREASURY_CSV.format(year=y))
        except (URLError, HTTPError, TimeoutError) as e:
            print(f"  ! Treasury {y}: {e}")
            continue
        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows:
            continue
        # newest row is the first data row
        row = rows[0]
        tenor_map = {"2 Yr": 2, "3 Yr": 3, "5 Yr": 5, "7 Yr": 7,
                     "10 Yr": 10, "20 Yr": 20, "30 Yr": 30}
        curve = {}
        for col, yrs in tenor_map.items():
            v = row.get(col)
            if v:
                try:
                    curve[yrs] = float(v)
                except ValueError:
                    pass
        if curve:
            return {"as_of": row.get("Date"), "curve": curve,
                    "source": "US Treasury daily par yield curve"}
    return None


def fetch_yahoo(ticker):
    """Live price + 52-week range for one ticker. None on failure."""
    try:
        data = _http_json(YAHOO_CHART.format(ticker=ticker))
    except (URLError, HTTPError, ValueError, TimeoutError) as e:
        print(f"  ! Yahoo {ticker}: {e}")
        return None
    try:
        meta = data["chart"]["result"][0]["meta"]
    except (KeyError, IndexError, TypeError):
        return None
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    chg = None
    if price is not None and prev:
        chg = round(100.0 * (price - prev) / prev, 2)
    return {
        "source": "Yahoo Finance",
        "symbol": meta.get("symbol", ticker),
        "price": price,
        "currency": meta.get("currency"),
        "change_pct": chg,
        "week52_high": meta.get("fiftyTwoWeekHigh"),
        "week52_low": meta.get("fiftyTwoWeekLow"),
    }


def compute_risk_score(company, weights):
    rf = company.get("risk_factors")
    if not rf:
        return None
    return round(
        rf["customer_concentration"] * weights["customer_concentration"]
        + rf["leverage"] * weights["leverage"]
        + rf["contract_mismatch"] * weights["contract_mismatch"]
        + rf["chip_freshness"] * weights["chip_freshness"], 1)


def nearest_tenor(curve, years):
    if not curve:
        return None, None
    tenors = sorted(curve.keys())
    best = min(tenors, key=lambda t: abs(t - years))
    return best, curve[best]


def annotate_bond_spreads(company, treasury):
    """Attach an indicative benchmark yield + coupon-vs-benchmark gap to each bond."""
    curve = (treasury or {}).get("curve")
    if not curve:
        return
    now = datetime.now(timezone.utc).year
    for b in company.get("bonds", []):
        mat = b.get("maturity")
        cpn = b.get("coupon")
        if mat is None:
            continue
        yrs = max(1, mat - now)
        tnr, bench = nearest_tenor(curve, yrs)
        b["benchmark_tenor_yr"] = tnr
        b["benchmark_yield_pct"] = bench
        if cpn is not None and bench is not None:
            b["coupon_vs_benchmark_bps"] = round((cpn - bench) * 100)


def build(live=True):
    with open(CURATED_PATH, "r", encoding="utf-8") as f:
        curated = json.load(f)

    weights = curated["risk_methodology"]["weights"]
    for company in curated["companies"]:
        company["risk_score"] = compute_risk_score(company, weights)

    treasury = None
    if live:
        print("Fetching live free-API data (SEC EDGAR, US Treasury, Yahoo)…")
        treasury = fetch_treasury()
        if treasury:
            print(f"  Treasury curve as of {treasury['as_of']}: "
                  f"10Y={treasury['curve'].get(10)}%  2Y={treasury['curve'].get(2)}%")
        for company in curated["companies"]:
            cik = company.get("sec_cik")
            if cik:
                fin = fetch_edgar(cik)
                if fin:
                    company["live_financials"] = fin
                    a = (fin.get("annual") or {})
                    gm = a.get("gross_margin_pct")
                    print(f"  EDGAR {company['name']}: rev={a.get('revenue')} "
                          f"gross_margin={gm}%")
            tk = company.get("ticker_yahoo")
            if tk:
                q = fetch_yahoo(tk)
                if q and q.get("price") is not None:
                    company["live_quote"] = q
                    print(f"  Yahoo {company['name']} ({tk}): "
                          f"${q['price']} ({q.get('change_pct')}%)")
            annotate_bond_spreads(company, treasury)
    else:
        print("Skipping live APIs (--no-live); curated data only.")

    if treasury:
        curated["treasury"] = treasury
    curated["built_at"] = datetime.now(timezone.utc).isoformat()
    curated["live_enriched"] = bool(live)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(curated, f, indent=2)

    n = len(curated["companies"])
    nlive = sum(1 for c in curated["companies"] if c.get("live_financials"))
    print(f"Built {OUTPUT_PATH} ({n} companies, {nlive} live-enriched)")
    return curated


def serve(port, open_browser):
    os.chdir(HERE)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), SimpleHTTPRequestHandler)
    url = f"http://127.0.0.1:{port}/index.html"
    print(f"Serving Neocloud Intelligence Map at {url}  (Ctrl+C to stop)")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
        httpd.shutdown()


def main():
    parser = argparse.ArgumentParser(description="Neocloud Intelligence Map")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-live", action="store_true",
                        help="skip live free-API enrichment, use curated data only")
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()

    build(live=not args.no_live)
    if args.build_only:
        return
    serve(args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
