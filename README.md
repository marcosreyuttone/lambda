# Neocloud Intelligence Map

An interactive map of **neocloud** GPU compute providers — the CoreWeave /
Lambda / Crusoe / Nebius wave of companies that own Nvidia/AMD GPU fleets and
rent that capacity to AI labs and enterprises. Every company on the map is a
GPU neocloud; a **data-center model** dimension separates those that build and
own their facilities from those that lease colocation space, and each site
names its actual **data-center owner** (e.g. Applied Digital, Core Scientific,
TeraWulf, Cologix).

For each company the map tracks, from public sources:

- **Revenue** (latest full-year or annualized run-rate) and **contracted backlog**
- **Chips** — which Nvidia/AMD GPU generation(s) they run
- **Data-center sites** — where their GPU capacity sits, and **who owns each site**
- **Who owns the GPUs** — self-owned, debt-financed, JV-owned, or vendor lease-back
- **Data-center model** — owns/develops facilities vs. leases colocation
- **Anchor customers and contract length** — e.g. CoreWeave-OpenAI (~5yr,
  $22.4B), Nebius-Meta (5yr, $27B), Applied Digital-CoreWeave (~15yr, ~$11B)
- **Bonds & notes** — every tracked senior/convertible note (coupon,
  maturity, size) with a live spread vs. the maturity-matched US Treasury
- **GPU rental price & unit economics** — on-demand $/GPU-hour by chip, vs.
  hyperscaler list prices and an estimated hardware amortization floor
- **Live financials & margin** — revenue, gross/operating/net margin, net
  PP&E (GPU book value), debt and cash pulled straight from SEC filings, plus
  a live share price and 52-week range
- **Neocloud Risk Score** (this map's original contribution — see below)

Click any site to open a full company profile drawer. Use **"Open
leaderboard"** to rank all companies, **"Show financing graph"** to draw the
money-and-compute web on the map, and **"Debt & bond maturity wall"** to see
the sector's refinancing wall.

## Quick start

No third-party packages required — just Python 3.8+.

```bash
python3 app.py
```

This pulls live free-API data, builds `data/neoclouds.json`, and serves the
map at `http://127.0.0.1:8000/index.html`.

```bash
python3 app.py --no-live        # skip live APIs, use curated data only (offline)
python3 app.py --no-browser     # don't auto-open a browser
python3 app.py --port 9000      # pick a port
python3 app.py --build-only     # just (re)build data/neoclouds.json and exit
```

## Live public data via free APIs (no keys required)

Every build enriches the curated dataset with live data from three free,
keyless sources (and falls back to curated figures if any is unreachable):

| Source | Endpoint | What it adds |
|---|---|---|
| **SEC EDGAR** | `data.sec.gov/api/xbrl/companyfacts` | Real revenue, cost of revenue, **gross / operating / net margin**, net PP&E (GPU book value), total debt and cash — straight from XBRL filings, for every public filer (CoreWeave, Nebius, IREN, Applied Digital, Core Scientific). |
| **US Treasury** | `home.treasury.gov` daily par yield curve | The risk-free benchmark used to compute an indicative **spread** for each tracked bond. |
| **Yahoo Finance** | `query1.finance.yahoo.com/v8/finance/chart` | Live **share price**, daily change, and 52-week range for the listed tickers. |

The margin data is the point: neoclouds post *high gross margins* (CoreWeave
~72%, Nebius ~69%) but *thin-or-negative net margins* once GPU depreciation
and interest are subtracted (CoreWeave net margin ≈ **−23%**), while the
landlords (Applied Digital, Core Scientific) run much thinner gross margins.
That gap is the crux of the whole debate.

### Optional: richer bond-market context via FRED

Everything above works with **no API key**. If you want to benchmark neocloud
bond spreads against the broad market (ICE BofA high-yield / IG option-adjusted
spreads, SOFR, etc.), grab a free [FRED API key](https://fredaccount.stlouisfed.org/apikeys)
and it can be wired into the build as a follow-up — Treasury already covers the
risk-free curve, so this is a nice-to-have, not a requirement.

## Bonds, pricing & the financing graph

- **Bonds & notes** — `bonds[]` per company: CoreWeave's 9.0–9.75% senior
  notes and 1.75% convertible, Nebius' and IREN's convertible stacks, plus the
  landlords' and TeraWulf's (FluidStack's host) notes. ~$22B of principal
  tracked. The **Debt & bond maturity wall** panel stacks them all by maturity
  year and shows the 2030–2033 refinancing bunch.
- **GPU rental pricing** — `pricing[]` per company: on-demand $/GPU-hour by
  chip, with hyperscaler reference prices and an illustrative hardware
  amortization floor so you can eyeball unit economics.
- **Financing / compute-flow graph** — `financing_graph` (nodes + typed,
  directed edges) captures the sector's "circular financing" web: who
  **supplies the GPUs**, **invests / vendor-finances**, **buys the compute**,
  **hosts / leases the data center**, and **lends / guarantees**. Toggle *Show
  financing graph* to draw it on the map; each company's own edges also appear
  in its profile drawer.

## The Neocloud Risk Score (value-add)

The headline number in every AI-infrastructure conversation right now is
*"how much of this GPU buildout is on solid financial footing?"* — the
[circular-financing](https://tomtunguz.com/nvidia_nortel_vendor_financing_comparison/)
debate (Nvidia investing in the same companies that buy its chips and lease
compute back), the
[GPU-depreciation debate](https://www.techi.com/nvidia-stock-gpu-depreciation-blackwell-rubin/)
(is an H100 a 6-year asset or a 2-3 year one?), and customer-concentration
risk (CoreWeave was >60% Microsoft in 2024).

This map turns that into a single, transparent, per-company **0-100 score**
(higher = riskier), computed from four weighted factors defined in
`data/neoclouds_curated.json → risk_methodology`:

| Factor | Weight | What it captures |
|---|---|---|
| Customer concentration | 30% | Share of revenue/backlog tied to one or two anchor customers |
| Leverage / debt reliance | 25% | Reliance on debt, SPVs, or circular vendor-financing vs. equity |
| Contract-vs-chip mismatch | 25% | Gap between debt tenor, contract tenor, and GPU refresh cycles |
| Chip-generation freshness | 20% | Exposure to Hopper-class (H100/H200) obsolescence vs. Blackwell/MI350-class |

The score is model-agnostic: whether a neocloud owns its data centers or
leases colocation, `chip_freshness` still reflects its own fleet's
obsolescence exposure. The separate **data-center owner** field names who owns
the building/power at each site.

As of this build, the distribution runs from Vultr / Together AI / Nebius
(~40-44, diversified, equity-funded, or already on Blackwell) up to Northern
Data (~73, revenue down 34% YoY with tripled losses while being acquired at a
fraction of invested capital) and CoreWeave/Crusoe (~68-69, heaviest disclosed
debt loads). Edit the weights or per-company `risk_factors` in the curated JSON
and re-run `python3 app.py --build-only` to recompute.

*(This score is an illustrative, editable model for exploring the sector's
structure — not investment advice.)*

## Companies tracked

All are **GPU neoclouds** (they own the GPUs). The **data-center model**
column shows whether each builds/owns its facilities or leases colocation.

**Owns / develops data centers:** Crusoe Energy, Nebius Group, IREN Limited,
Nscale, Northern Data / Taiga Cloud, OVHcloud, Scaleway, Sesterce, Denvr Dataworks.

**Colocation (leases space):** CoreWeave, Lambda, Together AI, Voltage Park,
FluidStack, TensorWave, Vultr, GMI Cloud, Genesis Cloud, DataCrunch (Verda),
RunPod, E2E Networks, Ori.

Each company's **sites are its data centers** (office HQs are tagged and hidden
from the map). Every circle is one data center, sized by default by its
**estimated GPU revenue** — a company's revenue split across its data centers by
power capacity (an estimate, not a disclosed per-site figure). A live
**OpenStreetMap** layer overlays *all* operators' data-center buildings for
context, and **PeeringDB** powers the interconnection-hubs layer (those are
peering points of presence, deliberately not treated as GPU data centers).

**Data-center owners referenced** (not GPU providers — they own the building &
power): Applied Digital, Core Scientific, TeraWulf, Cologix, Centeris, Hypertec.

## Data sources & accuracy

All figures are compiled from company press releases, investor-relations
pages, SEC/EDGAR filings (10-K/6-K/8-K), and press reporting (CNBC,
TechCrunch, Data Center Dynamics, The Next Platform, Forbes, Reuters-sourced
outlets, etc). Each company record in `data/neoclouds_curated.json` carries
a `sources` array with the specific links used.

> ⚠️ Revenue, debt, GPU-count, contract, and risk figures are **best-effort
> public estimates** compiled for visualization and education. This is one
> of the fastest-moving corners of the economy — a company's revenue run-rate
> or debt load can be stale within weeks. Verify against primary sources
> before relying on any number here. Site coordinates are metro/campus-level
> approximations, not exact addresses.

### Curated record schema

```jsonc
{
  "id": "coreweave", "name": "...", "category": "gpu_neocloud|landlord",
  "hq": "...", "founded": 2017, "public": true, "ticker": "...",
  "chip_vendor": "Nvidia|AMD|N/A (landlord)", "chips": ["H100", "GB200 NVL72"],
  "gpu_count_est": 250000,
  "gpu_owner": "...", "gpu_owner_detail": "...",
  "revenue_usd": 5131000000, "revenue_year": 2025, "revenue_note": "...",
  "backlog_usd": 66800000000, "debt_usd": 21600000000, "debt_note": "...",
  "funding_total_usd": null, "valuation_usd": null,
  "customers": [{"name": "OpenAI", "contract_usd": 22400000000, "contract_years": 5, "note": "..."}],
  "contract_years_weighted": 5,
  "risk_factors": {"customer_concentration": 75, "leverage": 90, "contract_mismatch": 65, "chip_freshness": 40},
  "risk_notes": "...",
  "sources": ["https://..."],
  "sites": [{"name": "Kenilworth, NJ", "city": "Kenilworth", "state": "NJ", "country": "US", "lat": 40.68, "lng": -74.29, "note": "..."}]
}
```

## Files

| File | Purpose |
|---|---|
| `app.py` | Pulls live free-API data (EDGAR/Treasury/Yahoo), computes risk scores & bond spreads, builds `data/neoclouds.json`, serves the map |
| `index.html` | Interactive Leaflet map UI: profile drawer, leaderboard, financing-graph layer, debt maturity wall |
| `data/neoclouds_curated.json` | Editable curated dataset: companies, bonds, pricing, risk methodology, financing graph (source of truth) |
| `data/neoclouds.json` | Generated file the map reads (risk scores + live financials merged in; git-ignored) |
