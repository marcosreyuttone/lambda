#!/usr/bin/env python3
"""
Neocloud Intelligence Map
=========================

Builds and serves an interactive map of "neocloud" GPU compute providers
(CoreWeave, Lambda, Crusoe, Nebius, ...) plus the data-center "landlords"
that host them (Applied Digital, Core Scientific).

Unlike a live-download pipeline, all figures here come from a single
hand-curated, source-linked JSON file (data/neoclouds_curated.json) --
there is no free real-time feed for company revenue, GPU counts or
contract terms, so this is refreshed by editing that file directly.

This script:
  1. Loads data/neoclouds_curated.json.
  2. Computes each company's Neocloud Risk Score from its risk_factors
     using the weights in risk_methodology (see README for methodology).
  3. Writes the enriched data/neoclouds.json that index.html reads.
  4. Serves the interactive map and opens it in your browser.

Usage
-----
    python3 app.py                  # build + serve + open browser
    python3 app.py --no-browser     # don't auto-open a browser
    python3 app.py --port 9000      # pick a port
    python3 app.py --build-only     # just (re)build data/neoclouds.json and exit
"""

import argparse
import json
import os
import sys
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
CURATED_PATH = os.path.join(DATA_DIR, "neoclouds_curated.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "neoclouds.json")


def compute_risk_score(company, weights):
    rf = company.get("risk_factors")
    if not rf:
        return None
    return round(
        rf["customer_concentration"] * weights["customer_concentration"]
        + rf["leverage"] * weights["leverage"]
        + rf["contract_mismatch"] * weights["contract_mismatch"]
        + rf["chip_freshness"] * weights["chip_freshness"],
        1,
    )


def build():
    with open(CURATED_PATH, "r", encoding="utf-8") as f:
        curated = json.load(f)

    weights = curated["risk_methodology"]["weights"]
    for company in curated["companies"]:
        company["risk_score"] = compute_risk_score(company, weights)

    curated["built_at"] = datetime.now(timezone.utc).isoformat()

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(curated, f, indent=2)

    n = len(curated["companies"])
    print(f"Built {OUTPUT_PATH} ({n} companies)")
    return curated


def serve(port, open_browser):
    os.chdir(HERE)
    handler = SimpleHTTPRequestHandler
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
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
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()

    build()
    if args.build_only:
        return
    serve(args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
