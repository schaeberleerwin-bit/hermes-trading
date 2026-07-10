"""Buffett-style Quality Screener.

Rankt Aktien nach dem Quality-Minus-Junk-Framework (Asness/Frazzini/Pedersen):
Profitability, Growth, Safety, Payout -> kombiniert mit Cheapness (Value).
Erzeugt eine self-contained HTML-Dashboard-Datei (embedded Daten, kein Server noetig).

Nutzung:
    python quality_screener.py                       # Default-Universe
    python quality_screener.py AAPL MSFT KO PG ...    # eigene Ticker
"""

import json
import sys
from pathlib import Path

import numpy as np
import yfinance as yf

DEFAULT_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "BRK-B", "KO", "PG", "JNJ", "V", "MA",
    "COST", "HD", "MCD", "UNH", "ABBV", "PEP", "WMT", "AXP", "CAT", "CVX",
    "XOM", "TSLA", "NVDA", "META", "DIS", "NKE", "SBUX", "IBM", "CSCO", "ADBE",
]

METRICS = [
    "returnOnEquity", "returnOnAssets", "grossMargins",
    "revenueGrowth", "earningsGrowth",
    "beta", "debtToEquity",
    "dividendYield", "payoutRatio",
    "trailingPE", "priceToBook",
]


def fetch(tickers: list[str]) -> list[dict]:
    rows = []
    for t in tickers:
        info = yf.Ticker(t).info
        if not info or info.get("regularMarketPrice") is None:
            print(f"  ! {t}: keine Daten, uebersprungen", file=sys.stderr)
            continue
        row = {"ticker": t, "name": info.get("shortName", t), "sector": info.get("sector", "-")}
        for m in METRICS:
            row[m] = info.get(m)
        row["marketCap"] = info.get("marketCap")
        rows.append(row)
        print(f"  ok {t}")
    return rows


def zscore(values: list[float | None]) -> np.ndarray:
    arr = np.array([np.nan if v is None else v for v in values], dtype=float)
    mean, std = np.nanmean(arr), np.nanstd(arr)
    if std == 0 or np.isnan(std):
        return np.zeros_like(arr)
    z = (arr - mean) / std
    return np.nan_to_num(z, nan=0.0)


def score(rows: list[dict]) -> list[dict]:
    z_roe = zscore([r["returnOnEquity"] for r in rows])
    z_roa = zscore([r["returnOnAssets"] for r in rows])
    z_margin = zscore([r["grossMargins"] for r in rows])
    z_rev_growth = zscore([r["revenueGrowth"] for r in rows])
    z_earn_growth = zscore([r["earningsGrowth"] for r in rows])
    z_beta = zscore([r["beta"] for r in rows])
    z_debt = zscore([r["debtToEquity"] for r in rows])
    z_div = zscore([r["dividendYield"] for r in rows])
    z_payout = zscore([r["payoutRatio"] for r in rows])
    z_pe = zscore([r["trailingPE"] for r in rows])
    z_pb = zscore([r["priceToBook"] for r in rows])

    for i, r in enumerate(rows):
        profitability = float(np.mean([z_roe[i], z_roa[i], z_margin[i]]))
        growth = float(np.mean([z_rev_growth[i], z_earn_growth[i]]))
        safety = float(np.mean([-z_beta[i], -z_debt[i]]))
        payout = float(np.mean([z_div[i], z_payout[i]]))
        quality = float(np.mean([profitability, growth, safety, payout]))
        value = float(np.mean([-z_pe[i], -z_pb[i]]))
        buffett_score = 0.7 * quality + 0.3 * value

        r["profitability"] = round(profitability, 2)
        r["growth"] = round(growth, 2)
        r["safety"] = round(safety, 2)
        r["payout"] = round(payout, 2)
        r["quality"] = round(quality, 2)
        r["value"] = round(value, 2)
        r["buffettScore"] = round(buffett_score, 2)

    return sorted(rows, key=lambda r: r["buffettScore"], reverse=True)


HTML_TEMPLATE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Quality Ledger</title>
<style>
:root {
  --paper: #f7f4ec; --page: #efeade; --ink: #1c1a15; --ink-soft: #5c564a;
  --muted: #948d7c; --rule: rgba(28,26,21,0.14); --gold: #96701d;
  --good: #1f7a4d; --critical: #b23a2e; --good-wash: rgba(31,122,77,0.12);
  --critical-wash: rgba(178,58,46,0.12);
}
@media (prefers-color-scheme: dark) {
  :root { --paper: #14181a; --page: #0c0f10; --ink: #f2efe6; --ink-soft: #b9b3a4;
    --muted: #7d7669; --rule: rgba(242,239,230,0.14); --gold: #c9a227;
    --good: #4caf7d; --critical: #e2685c; --good-wash: rgba(76,175,125,0.14);
    --critical-wash: rgba(226,104,92,0.14); }
}
:root[data-theme="dark"] { --paper: #14181a; --page: #0c0f10; --ink: #f2efe6; --ink-soft: #b9b3a4;
  --muted: #7d7669; --rule: rgba(242,239,230,0.14); --gold: #c9a227;
  --good: #4caf7d; --critical: #e2685c; --good-wash: rgba(76,175,125,0.14);
  --critical-wash: rgba(226,104,92,0.14); }
:root[data-theme="light"] { --paper: #f7f4ec; --page: #efeade; --ink: #1c1a15; --ink-soft: #5c564a;
  --muted: #948d7c; --rule: rgba(28,26,21,0.14); --gold: #96701d;
  --good: #1f7a4d; --critical: #b23a2e; --good-wash: rgba(31,122,77,0.12);
  --critical-wash: rgba(178,58,46,0.12); }

* { box-sizing: border-box; }
body { margin:0; background: var(--page); color: var(--ink);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased; }
.wrap { max-width: 1180px; margin: 0 auto; padding: 48px 32px 64px; }

header { border-bottom: 2px solid var(--ink); padding-bottom: 20px; margin-bottom: 24px;
  display:flex; justify-content:space-between; align-items:flex-end; gap:24px; flex-wrap:wrap; }
h1 { font-family: Georgia, "Iowan Old Style", "Times New Roman", serif; font-weight: 400;
  font-size: 34px; letter-spacing: -0.01em; margin: 0 0 6px; text-wrap: balance; }
p.sub { color: var(--ink-soft); margin: 0; font-size: 14px; max-width: 62ch; line-height: 1.5; }
.meta { text-align:right; font-size:12px; color: var(--muted); text-transform:uppercase; letter-spacing:.06em; }

.controls { display:flex; gap:10px; margin-bottom:20px; flex-wrap:wrap; align-items:center; }
.controls input, .controls select { padding:8px 12px; border-radius:3px; border:1px solid var(--rule);
  background: var(--paper); color: var(--ink); font-size:13px; font-family: inherit; }
.controls input { min-width: 220px; }
.controls input:focus, .controls select:focus { outline: 2px solid var(--gold); outline-offset: 1px; }
.count { margin-left:auto; font-size:12px; color: var(--muted); font-variant-numeric: tabular-nums; }

.legend { display:flex; gap:18px; margin-bottom:14px; font-size:12px; color: var(--ink-soft); flex-wrap:wrap; }
.legend span.dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:5px; vertical-align:1px; }

.card { background: var(--paper); border: 1px solid var(--rule); border-radius: 4px; overflow-x: auto; }
table { width:100%; border-collapse: collapse; font-size: 13px; min-width: 900px; }
thead th { text-align:left; padding: 10px 14px; font-size:11px; text-transform:uppercase; letter-spacing:.06em;
  font-weight:600; color: var(--muted); border-bottom: 1.5px solid var(--ink); cursor:pointer; user-select:none;
  white-space:nowrap; }
thead th:hover { color: var(--gold); }
tbody td { padding: 9px 14px; border-bottom: 1px solid var(--rule); white-space:nowrap; }
tbody tr:hover { background: color-mix(in srgb, var(--ink) 4%, transparent); }
td.num, th.num { text-align:right; font-variant-numeric: tabular-nums; }
.ticker { font-weight: 700; letter-spacing: .01em; }
.name { color: var(--ink-soft); font-size:11.5px; margin-top:1px; }
.rank { color: var(--muted); font-variant-numeric: tabular-nums; }

.divbar { position:relative; width:88px; height:14px; margin-left:auto; background:
  linear-gradient(to right, transparent 49.5%, var(--rule) 49.5%, var(--rule) 50.5%, transparent 50.5%); }
.divbar > span { position:absolute; top:2px; height:10px; border-radius:2px; }
.divbar > span.g { background: var(--good); left:50%; }
.divbar > span.r { background: var(--critical); right:50%; }
.divbar-val { display:inline-block; width:40px; text-align:right; margin-right:8px; }
.divbar-row { display:flex; align-items:center; justify-content:flex-end; }
.g-text { color: var(--good); } .r-text { color: var(--critical); }

footer { margin-top:22px; color: var(--muted); font-size:11.5px; line-height:1.6; max-width: 70ch; }
a { color: var(--gold); }
</style>
</head>
<body>
<div class="wrap">
<header>
  <div>
    <h1>Quality Ledger</h1>
    <p class="sub">Ranking nach Profitability, Growth, Safety und Payout (Quality) kombiniert mit Bewertung (Value) &mdash;
    Framework nach Frazzini/Kabiller/Pedersen (&bdquo;Buffett's Alpha&ldquo;) und Asness/Frazzini/Pedersen (&bdquo;Quality Minus Junk&ldquo;).</p>
  </div>
  <div class="meta">Generiert __TIMESTAMP__<br>__COUNT__ Werte im Universum</div>
</header>

<div class="controls">
  <input id="search" type="text" placeholder="Ticker oder Name suchen...">
  <select id="sector"><option value="">Alle Sektoren</option></select>
  <span class="count" id="count"></span>
</div>

<div class="legend">
  <span><span class="dot" style="background:var(--good)"></span>positiv (ueber Median des Universums)</span>
  <span><span class="dot" style="background:var(--critical)"></span>negativ (unter Median)</span>
  <span>Buffett Score = 0,7 &times; Quality + 0,3 &times; Value (z-standardisiert im Universum)</span>
</div>

<div class="card">
<table>
<thead><tr>
  <th data-key="rank">#</th>
  <th data-key="ticker">Wert</th>
  <th data-key="sector">Sektor</th>
  <th class="num" data-key="buffettScore">Buffett&nbsp;Score</th>
  <th class="num" data-key="quality">Quality</th>
  <th class="num" data-key="value">Value</th>
  <th class="num" data-key="profitability">Profit.</th>
  <th class="num" data-key="growth">Growth</th>
  <th class="num" data-key="safety">Safety</th>
  <th class="num" data-key="payout">Payout</th>
  <th class="num" data-key="trailingPE">P/E</th>
  <th class="num" data-key="priceToBook">P/B</th>
</tr></thead>
<tbody id="tbody"></tbody>
</table>
</div>

<footer>Daten via Yahoo Finance (yfinance), Fundamentaldaten koennen verzoegert oder unvollstaendig sein.
Scores sind relativ zum geladenen Universum und keine absolute Kennzahl &mdash; kein Anlageberatungstool, keine Kaufempfehlung.</footer>
</div>
<script>
const DATA = __DATA__;
let sortKey = "buffettScore", sortDir = -1;

function divBar(v, max) {
  const pct = Math.min(100, Math.abs(v) / max * 50);
  const cls = v >= 0 ? "g" : "r";
  const textCls = v >= 0 ? "g-text" : "r-text";
  const bar = v >= 0
    ? `<span class="g" style="width:${pct}%"></span>`
    : `<span class="r" style="width:${pct}%"></span>`;
  return `<div class="divbar-row"><span class="divbar-val ${textCls}">${v.toFixed(2)}</span><div class="divbar">${bar}</div></div>`;
}

function render() {
  const q = document.getElementById("search").value.toLowerCase();
  const sec = document.getElementById("sector").value;
  let rows = DATA.filter(r =>
    (!q || r.ticker.toLowerCase().includes(q) || r.name.toLowerCase().includes(q)) &&
    (!sec || r.sector === sec)
  );
  rows.sort((a, b) => (a[sortKey] - b[sortKey]) * sortDir || 0);
  const maxAbs = Math.max(1, ...DATA.map(r => Math.abs(r.buffettScore)), ...DATA.map(r => Math.abs(r.quality)));
  document.getElementById("tbody").innerHTML = rows.map((r, i) => `
    <tr>
      <td class="rank">${i + 1}</td>
      <td><div class="ticker">${r.ticker}</div><div class="name">${r.name}</div></td>
      <td>${r.sector}</td>
      <td class="num">${divBar(r.buffettScore, maxAbs)}</td>
      <td class="num">${divBar(r.quality, maxAbs)}</td>
      <td class="num">${r.value.toFixed(2)}</td>
      <td class="num">${r.profitability.toFixed(2)}</td>
      <td class="num">${r.growth.toFixed(2)}</td>
      <td class="num">${r.safety.toFixed(2)}</td>
      <td class="num">${r.payout.toFixed(2)}</td>
      <td class="num">${r.trailingPE != null ? r.trailingPE.toFixed(1) : "&ndash;"}</td>
      <td class="num">${r.priceToBook != null ? r.priceToBook.toFixed(1) : "&ndash;"}</td>
    </tr>`).join("");
  document.getElementById("count").textContent = rows.length + " von " + DATA.length + " angezeigt";
}

document.querySelectorAll("th[data-key]").forEach(th => {
  th.addEventListener("click", () => {
    const key = th.dataset.key;
    if (key === "rank") return;
    if (sortKey === key) sortDir *= -1; else { sortKey = key; sortDir = -1; }
    render();
  });
});
document.getElementById("search").addEventListener("input", render);
document.getElementById("sector").addEventListener("change", render);

const sectors = [...new Set(DATA.map(r => r.sector))].sort();
document.getElementById("sector").innerHTML += sectors.map(s => `<option>${s}</option>`).join("");
render();
</script>
</body>
</html>
"""


def build_html(rows: list[dict], out_path: Path) -> None:
    import datetime
    html = HTML_TEMPLATE.replace("__DATA__", json.dumps(rows))
    html = html.replace("__TIMESTAMP__", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    html = html.replace("__COUNT__", str(len(rows)))
    out_path.write_text(html, encoding="utf-8")


def main() -> None:
    tickers = sys.argv[1:] or DEFAULT_TICKERS
    print(f"Lade Fundamentaldaten fuer {len(tickers)} Ticker...")
    rows = fetch(tickers)
    if len(rows) < 3:
        print("Zu wenige Ticker mit Daten fuer sinnvolle Z-Scores (mind. 3 noetig).", file=sys.stderr)
        sys.exit(1)
    ranked = score(rows)

    out_dir = Path(__file__).resolve().parent.parent / "state"
    out_dir.mkdir(exist_ok=True)
    json_path = out_dir / "quality_screener.json"
    html_path = out_dir / "quality_screener.html"
    json_path.write_text(json.dumps(ranked, indent=2), encoding="utf-8")
    build_html(ranked, html_path)

    print(f"\nTop 5:")
    for r in ranked[:5]:
        print(f"  {r['ticker']:6s} Buffett Score {r['buffettScore']:+.2f}  (Quality {r['quality']:+.2f}, Value {r['value']:+.2f})")
    print(f"\nJSON: {json_path}")
    print(f"HTML: {html_path}")


if __name__ == "__main__":
    main()
