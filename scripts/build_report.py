#!/usr/bin/env python3
import csv
import json
import os
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path

START_DATE = '2026-05-01'
WORKSPACE = Path('/Users/rudolfkonfal/.openclaw/workspace')
REPORTING_ROOT = WORKSPACE / 'reporting-v2'
ORDER_FACT_PATH = REPORTING_ROOT / 'data' / 'current' / 'order_fact_ytd_window.json'
REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / 'docs'
SITE_DIR = REPO_ROOT / 'site'
CSV_FILENAME = 'denni_trzby_retence_vs_zbytek_2026-05-01_plus_cz_sk_bez_pokladen.csv'
HTML_PATH = DOCS_DIR / 'index.html'
CSV_PATH = DOCS_DIR / CSV_FILENAME
GENERATED_JSON = DOCS_DIR / 'latest.json'
REFRESH_SCRIPT = REPORTING_ROOT / 'scripts' / 'refresh_data.py'


def fmt_money(value: float) -> str:
    return f"{value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', ' ')


def fmt_int(value: int) -> str:
    return f"{value:,}".replace(',', ' ')


def refresh_source_data():
    subprocess.run(['python3', str(REFRESH_SCRIPT)], cwd=str(REPORTING_ROOT), check=True)


def load_orders():
    payload = json.loads(ORDER_FACT_PATH.read_text(encoding='utf-8'))
    orders = payload['orders']
    rows = []
    for order in orders:
        dt = datetime.fromisoformat(order['dateCreated'])
        rows.append({**order, 'dt': dt, 'date': dt.date().isoformat()})
    rows.sort(key=lambda row: row['dt'])
    return payload, rows


def build_daily_rows(orders):
    seen_customers = set()
    aggregated = defaultdict(lambda: {
        'cz_retence_orders': 0,
        'cz_retence_revenue_with_vat': 0.0,
        'cz_zbytek_orders': 0,
        'cz_zbytek_revenue_with_vat': 0.0,
        'sk_retence_orders': 0,
        'sk_retence_revenue_with_vat': 0.0,
        'sk_zbytek_orders': 0,
        'sk_zbytek_revenue_with_vat': 0.0,
    })

    for order in orders:
        if order.get('cancelled'):
            continue
        source_name = (order.get('sourceName') or '').strip().lower()
        if source_name == 'pokladna':
            continue

        customer_key = order.get('customerKey') or ''
        if order['date'] < START_DATE:
            if customer_key:
                seen_customers.add(customer_key)
            continue

        market = 'sk' if (order.get('countryCode') or '').upper() == 'SK' else 'cz'
        segment = 'retence' if customer_key and customer_key in seen_customers else 'zbytek'
        target = aggregated[order['date']]
        target[f'{market}_{segment}_orders'] += 1
        target[f'{market}_{segment}_revenue_with_vat'] += float(order.get('revenueWithVat') or 0.0)

        if customer_key:
            seen_customers.add(customer_key)

    rows = []
    for day in sorted(aggregated):
        row = {'date': day, **aggregated[day]}
        row['cz_total_orders'] = row['cz_retence_orders'] + row['cz_zbytek_orders']
        row['cz_total_revenue_with_vat'] = row['cz_retence_revenue_with_vat'] + row['cz_zbytek_revenue_with_vat']
        row['sk_total_orders'] = row['sk_retence_orders'] + row['sk_zbytek_orders']
        row['sk_total_revenue_with_vat'] = row['sk_retence_revenue_with_vat'] + row['sk_zbytek_revenue_with_vat']
        row['total_orders'] = row['cz_total_orders'] + row['sk_total_orders']
        row['total_revenue_with_vat'] = row['cz_total_revenue_with_vat'] + row['sk_total_revenue_with_vat']
        rows.append(row)
    return rows


def write_csv(rows):
    fieldnames = [
        'date',
        'cz_retence_orders', 'cz_retence_revenue_with_vat',
        'cz_zbytek_orders', 'cz_zbytek_revenue_with_vat',
        'cz_total_orders', 'cz_total_revenue_with_vat',
        'sk_retence_orders', 'sk_retence_revenue_with_vat',
        'sk_zbytek_orders', 'sk_zbytek_revenue_with_vat',
        'sk_total_orders', 'sk_total_revenue_with_vat',
        'total_orders', 'total_revenue_with_vat',
    ]
    with CSV_PATH.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_summary(rows, generated_at):
    if not rows:
        return {
            'generatedAt': generated_at,
            'days': 0,
            'totals': {},
            'latestDay': None,
        }
    latest = rows[-1]
    return {
        'generatedAt': generated_at,
        'days': len(rows),
        'latestDay': latest,
        'totals': {
            'cz_retence_revenue_with_vat': round(sum(r['cz_retence_revenue_with_vat'] for r in rows), 2),
            'cz_zbytek_revenue_with_vat': round(sum(r['cz_zbytek_revenue_with_vat'] for r in rows), 2),
            'sk_retence_revenue_with_vat': round(sum(r['sk_retence_revenue_with_vat'] for r in rows), 2),
            'sk_zbytek_revenue_with_vat': round(sum(r['sk_zbytek_revenue_with_vat'] for r in rows), 2),
            'total_revenue_with_vat': round(sum(r['total_revenue_with_vat'] for r in rows), 2),
            'total_orders': sum(r['total_orders'] for r in rows),
        },
    }


def write_html(rows, summary):
    max_rev = max((row['total_revenue_with_vat'] for row in rows), default=1)
    bar_rows = []
    table_rows = []
    for row in rows:
        width = (row['total_revenue_with_vat'] / max_rev) * 100 if max_rev else 0
        bar_rows.append(
            f"<div class='bar-row'><div class='bar-label'>{row['date']}</div><div class='bar-track'><div class='bar-fill' style='width:{width:.2f}%'></div></div><div class='bar-value'>{fmt_money(row['total_revenue_with_vat'])} Kč</div></div>"
        )
        table_rows.append(
            '<tr>'
            f"<td>{row['date']}</td>"
            f"<td>{fmt_int(row['cz_retence_orders'])}</td>"
            f"<td>{fmt_money(row['cz_retence_revenue_with_vat'])} Kč</td>"
            f"<td>{fmt_int(row['cz_zbytek_orders'])}</td>"
            f"<td>{fmt_money(row['cz_zbytek_revenue_with_vat'])} Kč</td>"
            f"<td>{fmt_int(row['sk_retence_orders'])}</td>"
            f"<td>{fmt_money(row['sk_retence_revenue_with_vat'])} Kč</td>"
            f"<td>{fmt_int(row['sk_zbytek_orders'])}</td>"
            f"<td>{fmt_money(row['sk_zbytek_revenue_with_vat'])} Kč</td>"
            f"<td>{fmt_money(row['total_revenue_with_vat'])} Kč</td>"
            '</tr>'
        )

    latest = summary.get('latestDay') or {}
    totals = summary.get('totals') or {}
    html = f"""<!doctype html>
<html lang='cs'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>RETENCE vs zbytek světa</title>
  <style>
    :root {{ --bg:#f6f8fb; --card:#fff; --line:#e2e8f0; --text:#0f172a; --muted:#64748b; --blue:#2563eb; --green:#059669; --orange:#d97706; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Arial,sans-serif; background:var(--bg); color:var(--text); }}
    .wrap {{ max-width:1200px; margin:0 auto; padding:28px; }}
    h1 {{ margin:0 0 8px; font-size:30px; }}
    .sub {{ color:var(--muted); font-size:14px; line-height:1.5; }}
    .grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:22px 0; }}
    .card {{ background:var(--card); border:1px solid var(--line); border-radius:16px; padding:18px; box-shadow:0 6px 20px rgba(15,23,42,.04); }}
    .kicker {{ font-size:12px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); margin-bottom:8px; }}
    .big {{ font-size:28px; font-weight:700; }}
    .bars {{ display:flex; flex-direction:column; gap:10px; }}
    .bar-row {{ display:grid; grid-template-columns:110px 1fr 150px; gap:12px; align-items:center; font-size:14px; }}
    .bar-track {{ height:14px; background:#eaf0fb; border-radius:999px; overflow:hidden; }}
    .bar-fill {{ height:100%; background:linear-gradient(90deg,var(--blue),#60a5fa); border-radius:999px; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th, td {{ padding:10px 8px; border-bottom:1px solid var(--line); text-align:left; }}
    th {{ font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }}
    .section {{ margin-top:18px; }}
    .note {{ color:var(--muted); font-size:13px; line-height:1.5; }}
    a {{ color:var(--blue); text-decoration:none; }}
    @media (max-width: 960px) {{ .grid {{ grid-template-columns:1fr; }} .bar-row {{ grid-template-columns:90px 1fr 120px; }} }}
  </style>
</head>
<body>
  <div class='wrap'>
    <h1>Denní tržby, RETENCE vs zbytek světa</h1>
    <div class='sub'>Od 1. 5. 2026, po dnech, <strong>CZ a SK zvlášť</strong>, <strong>bez pokladen</strong>. RETENCE = zákazník měl v datech aspoň jednu dřívější objednávku před daným dnem. Zdroj je order fact z reporting-v2, refresh běží každou hodinu.</div>

    <div class='grid'>
      <div class='card'><div class='kicker'>Poslední dostupný den</div><div class='big'>{latest.get('date','-')}</div><div class='note'>Aktualizováno {summary.get('generatedAt','-')}</div></div>
      <div class='card'><div class='kicker'>Celkem tržby od 1. 5.</div><div class='big'>{fmt_money(totals.get('total_revenue_with_vat', 0.0))} Kč</div><div class='note'>{fmt_int(totals.get('total_orders', 0))} objednávek</div></div>
      <div class='card'><div class='kicker'>CZ retence</div><div class='big'>{fmt_money(totals.get('cz_retence_revenue_with_vat', 0.0))} Kč</div><div class='note'>CZ zbytek {fmt_money(totals.get('cz_zbytek_revenue_with_vat', 0.0))} Kč</div></div>
      <div class='card'><div class='kicker'>SK retence</div><div class='big'>{fmt_money(totals.get('sk_retence_revenue_with_vat', 0.0))} Kč</div><div class='note'>SK zbytek {fmt_money(totals.get('sk_zbytek_revenue_with_vat', 0.0))} Kč</div></div>
    </div>

    <div class='card section'>
      <div class='kicker'>Vývoj po dnech</div>
      <div class='bars'>
        {''.join(bar_rows)}
      </div>
    </div>

    <div class='card section'>
      <div class='kicker'>Denní rozpad</div>
      <table>
        <thead>
          <tr>
            <th>Datum</th>
            <th>CZ retence obj.</th>
            <th>CZ retence tržby</th>
            <th>CZ zbytek obj.</th>
            <th>CZ zbytek tržby</th>
            <th>SK retence obj.</th>
            <th>SK retence tržby</th>
            <th>SK zbytek obj.</th>
            <th>SK zbytek tržby</th>
            <th>Celkem</th>
          </tr>
        </thead>
        <tbody>
          {''.join(table_rows)}
        </tbody>
      </table>
      <div class='note' style='margin-top:10px;'>CSV export: <a href='./{CSV_PATH.name}'>{CSV_PATH.name}</a></div>
    </div>
  </div>
</body>
</html>
"""
    HTML_PATH.write_text(html, encoding='utf-8')


def sync_site_copy():
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    for name in ['index.html', CSV_FILENAME, 'latest.json']:
        (SITE_DIR / name).write_text((DOCS_DIR / name).read_text(encoding='utf-8'), encoding='utf-8') if name.endswith(('.html', '.json', '.csv')) else None


def main():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    if os.environ.get('SKIP_REFRESH') != '1':
        refresh_source_data()
    payload, orders = load_orders()
    rows = build_daily_rows(orders)
    write_csv(rows)
    summary = build_summary(rows, payload.get('generatedAt'))
    GENERATED_JSON.write_text(json.dumps({'summary': summary, 'rows': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
    write_html(rows, summary)
    sync_site_copy()
    print(f'OK: {HTML_PATH}')


if __name__ == '__main__':
    main()
