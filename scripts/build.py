import pandas as pd
import requests
import json
from io import StringIO
from datetime import datetime
import pytz

SHEET_ID = "1dId9aW0hMv74qvOWj8H6xozBcbwONqFPa32S-1QTElM"
MONTHLY_TAB = "Monthly Yield Data"
DAILY_TAB = "Daily yield Data"

def fetch_sheet(tab):
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={requests.utils.quote(tab)}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return pd.read_csv(StringIO(r.text))

def find_col(df, *names):
    lmap = {c.lower().strip().replace(' ','_'): c for c in df.columns}
    for n in names:
        k = n.lower().replace(' ','_')
        if k in lmap:
            return lmap[k]
    return None

def process(df):
    rent  = find_col(df, 'rentamount','rent_amount','rent','rental_amount') or df.columns[4]
    cost  = find_col(df, 'offlinesourcingcost','sourcing_cost','cost','offline_sourcing_cost') or df.columns[5]
    month = find_col(df, 'month','month_date','date') or df.columns[0]
    cat   = find_col(df, 'sub_cat','subcat','sub_category','category') or df.columns[1]
    city  = find_col(df, 'city','city_name') or df.columns[2]
    sku   = find_col(df, 'sku','sku_code','sku_id')
    orders= find_col(df, 'orders','order_count')
    items = find_col(df, 'items','item_count')

    df = df.copy()
    df['_rent']  = pd.to_numeric(df[rent],  errors='coerce').fillna(0)
    df['_cost']  = pd.to_numeric(df[cost],  errors='coerce').fillna(0)
    df['_month'] = pd.to_datetime(df[month],errors='coerce')
    df['_cat']   = df[cat].astype(str).str.strip()
    df['_city']  = df[city].astype(str).str.strip()
    df['_ms']    = df['_month'].dt.strftime('%Y-%m')
    df['_orders']= pd.to_numeric(df[orders], errors='coerce').fillna(0) if orders else 0
    df['_items'] = pd.to_numeric(df[items],  errors='coerce').fillna(0) if items else 0
    df = df.dropna(subset=['_month'])
    df = df[df['_cost'] > 0]

    def agg(grp_cols, extra=None):
        a = df.groupby(grp_cols).agg(
            rent=('_rent','sum'), cost=('_cost','sum'),
            orders=('_orders','sum'), items=('_items','sum')
        ).reset_index()
        a['yield_pct'] = (a['rent']/a['cost']*100).round(2)
        return a[a['cost']>0]

    monthly    = agg(['_ms']).rename(columns={'_ms':'month_str'})
    cat_month  = agg(['_cat','_ms']).rename(columns={'_cat':'sub_cat','_ms':'month_str'})
    city_month = agg(['_city','_ms']).rename(columns={'_city':'city','_ms':'month_str'})
    city_cat   = agg(['_city','_cat','_ms']).rename(columns={'_city':'city','_cat':'sub_cat','_ms':'month_str'})

    df_nac     = df[~df['_cat'].str.lower().str.contains('air condition', na=False)]
    m_nac      = df_nac.groupby('_ms').agg(rent=('_rent','sum'),cost=('_cost','sum')).reset_index()
    m_nac['yield_pct'] = (m_nac['rent']/m_nac['cost']*100).round(2)
    m_nac = m_nac.rename(columns={'_ms':'month_str'})

    total_skus = df[sku].nunique() if sku else 0

    return {
        'monthly':       monthly.to_dict('records'),
        'monthly_no_ac': m_nac.to_dict('records'),
        'cat_month':     cat_month.to_dict('records'),
        'city_month':    city_month.to_dict('records'),
        'city_cat_month':city_cat.to_dict('records'),
        'cities':    sorted(df['_city'].dropna().unique().tolist()),
        'categories':sorted(df['_cat'].dropna().unique().tolist()),
        'months':    sorted(df['_ms'].dropna().unique().tolist()),
        'last_updated': datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d %b %Y · %I:%M %p IST'),
        'total_skus': int(total_skus)
    }

print("Fetching Monthly Yield Data...")
monthly_df = fetch_sheet(MONTHLY_TAB)
print(f"  Rows: {len(monthly_df)}  Cols: {list(monthly_df.columns)}")

print("Fetching Daily Yield Data...")
daily_df   = fetch_sheet(DAILY_TAB)
print(f"  Rows: {len(daily_df)}  Cols: {list(daily_df.columns)}")

print("Computing metrics...")
data = process(monthly_df)
data_json = json.dumps(data, default=str)

months_count = len(data['months'])
cities_count = len(data['cities'])
cats_count   = len(data['categories'])
last_updated = data['last_updated']

HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Yield Dashboard · Rentomojo</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,700;9..144,900&family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,500;12..96,600;12..96,700&family=JetBrains+Mono:wght@300;400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{{
  --bg:#0E0D0B;--bg2:#141210;--surf:#1A1714;--surf2:#221E1A;
  --bdr:#2A2520;--bdr2:#38312A;
  --ink:#F5F0E6;--ink2:#C7BFB1;--ink3:#8A8478;--ink4:#5C5750;
  --amber:#E8B048;--amber2:#D4A04C;--ambersoft:rgba(232,176,72,.12);
  --sage:#8FB89A;--sagesoft:rgba(143,184,154,.14);
  --coral:#E47E6C;--coralsoft:rgba(228,126,108,.14);
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:var(--bg);color:var(--ink);font-family:'Bricolage Grotesque',sans-serif;min-height:100vh;overflow-x:hidden}}
body::before{{content:'';position:fixed;inset:0;background:radial-gradient(ellipse 80% 50% at 80% -10%,rgba(232,176,72,.08),transparent 60%),radial-gradient(ellipse 60% 40% at 10% 110%,rgba(143,184,154,.05),transparent 60%);pointer-events:none;z-index:0}}

/* PASSWORD GATE */
#gate{{position:fixed;inset:0;background:var(--bg);z-index:9999;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:0}}
#gate.hidden{{display:none}}
.gate-box{{background:var(--surf);border:1px solid var(--bdr);border-radius:24px;padding:52px 48px;max-width:440px;width:90%;text-align:center;box-shadow:0 40px 80px -20px rgba(0,0,0,.7)}}
.gate-logo{{font-family:'Fraunces',serif;font-weight:900;font-size:36px;font-style:italic;color:var(--amber);letter-spacing:-.04em;margin-bottom:6px}}
.gate-sub{{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--ink4);margin-bottom:40px}}
.gate-label{{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink3);text-align:left;margin-bottom:10px}}
.gate-input{{width:100%;background:var(--bg);border:1px solid var(--bdr);border-radius:12px;padding:16px 18px;color:var(--ink);font-family:'Bricolage Grotesque',sans-serif;font-size:16px;outline:none;transition:border-color .2s;letter-spacing:.05em}}
.gate-input:focus{{border-color:var(--amber)}}
.gate-btn{{width:100%;margin-top:16px;background:var(--amber);border:0;border-radius:12px;padding:16px;color:#1A1714;font-family:'Bricolage Grotesque',sans-serif;font-size:15px;font-weight:700;cursor:pointer;letter-spacing:.02em;transition:background .2s}}
.gate-btn:hover{{background:var(--amber2)}}
.gate-err{{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--coral);margin-top:12px;height:16px;letter-spacing:.06em}}

/* DASHBOARD */
#dash{{position:relative;z-index:2}}
.wrap{{max-width:1400px;margin:0 auto;padding:28px 32px 80px}}
header{{display:flex;align-items:center;justify-content:space-between;padding:12px 0 28px;border-bottom:1px solid var(--bdr);margin-bottom:36px}}
.brand-mark{{font-family:'Fraunces',serif;font-weight:900;font-size:28px;font-style:italic;letter-spacing:-.04em;color:var(--amber)}}
.brand-sub{{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--ink4);margin-top:4px}}
.pulse{{width:7px;height:7px;border-radius:50%;background:var(--sage);animation:pulse 2s infinite;display:inline-block;margin-right:8px}}
@keyframes pulse{{0%{{box-shadow:0 0 0 0 rgba(143,184,154,.4)}}70%{{box-shadow:0 0 0 10px rgba(143,184,154,0)}}100%{{box-shadow:0 0 0 0 rgba(143,184,154,0)}}}}
.meta-text{{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--ink3)}}
.hero{{margin-bottom:32px;display:flex;justify-content:space-between;align-items:flex-end;gap:40px;flex-wrap:wrap}}
.hero-title{{font-family:'Fraunces',serif;font-weight:300;font-size:clamp(36px,5vw,68px);line-height:.95;letter-spacing:-.04em}}
.hero-title em{{font-style:italic;color:var(--amber);font-weight:400}}
.hero-meta{{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--ink3);text-align:right;line-height:2}}
.hero-meta strong{{color:var(--ink);font-weight:500}}
.controls{{display:flex;gap:24px;align-items:center;margin-bottom:28px;flex-wrap:wrap}}
.tgroup{{display:inline-flex;background:var(--surf);border:1px solid var(--bdr);border-radius:999px;padding:3px}}
.tgroup button{{background:transparent;border:0;color:var(--ink3);font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;padding:9px 18px;border-radius:999px;cursor:pointer;transition:all .25s}}
.tgroup button.on{{background:var(--amber);color:#1A1714;font-weight:600}}
.kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--bdr);border:1px solid var(--bdr);border-radius:18px;overflow:hidden;margin-bottom:36px}}
.kpi{{background:var(--surf);padding:28px 28px 24px;transition:background .3s}}
.kpi:hover{{background:var(--surf2)}}
.kpi-lbl{{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink3);margin-bottom:18px}}
.kpi-val{{font-family:'Fraunces',serif;font-weight:400;font-size:48px;line-height:1;letter-spacing:-.03em;margin-bottom:12px}}
.kpi-val .u{{font-size:22px;color:var(--ink3);margin-left:4px;font-style:italic;font-weight:300}}
.kpi-delta{{font-family:'JetBrains Mono',monospace;font-size:11px}}
.kpi-delta.up{{color:var(--sage)}}.kpi-delta.dn{{color:var(--coral)}}.kpi-delta.fl{{color:var(--ink3)}}
.tabs{{display:flex;gap:4px;margin-bottom:28px;border-bottom:1px solid var(--bdr)}}
.tab{{background:transparent;border:0;color:var(--ink3);font-family:'Bricolage Grotesque',sans-serif;font-size:14px;font-weight:500;padding:14px 22px;cursor:pointer;position:relative;transition:color .2s}}
.tab:hover{{color:var(--ink2)}}.tab.active{{color:var(--ink)}}
.tab.active::after{{content:'';position:absolute;left:22px;right:22px;bottom:-1px;height:2px;background:var(--amber);border-radius:2px}}
.panel{{display:none;animation:fadeIn .4s ease}}.panel.active{{display:block}}
@keyframes fadeIn{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:translateY(0)}}}}
.card{{background:var(--surf);border:1px solid var(--bdr);border-radius:18px;padding:26px 28px}}
.sec-title{{font-family:'Fraunces',serif;font-weight:400;font-size:22px;letter-spacing:-.02em;margin-bottom:4px}}
.sec-sub{{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink4);margin-bottom:18px}}
.exec-grid{{display:grid;grid-template-columns:1.4fr 1fr;gap:20px;margin-bottom:20px}}
.chart-box{{height:320px;position:relative}}
.movers{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}}
.mover-card{{background:var(--surf);border:1px solid var(--bdr);border-radius:18px;padding:24px 26px}}
.mover-head{{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}}
.mtag{{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.16em;text-transform:uppercase;padding:5px 10px;border-radius:4px}}
.mtag.up{{color:var(--sage);background:var(--sagesoft)}}.mtag.dn{{color:var(--coral);background:var(--coralsoft)}}
.mr{{display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-bottom:1px dashed var(--bdr);font-size:14px}}
.mr:last-child{{border:none}}.mr-name{{color:var(--ink);font-weight:500}}
.mr-vals{{display:flex;gap:16px;align-items:baseline}}
.mr-cur{{font-family:'JetBrains Mono',monospace;font-size:14px;color:var(--ink2)}}
.mr-d{{font-family:'JetBrains Mono',monospace;font-size:11px;min-width:64px;text-align:right}}
.mr-d.up{{color:var(--sage)}}.mr-d.dn{{color:var(--coral)}}
.alerts{{background:var(--surf);border:1px solid var(--bdr);border-left:3px solid var(--amber);border-radius:14px;padding:20px 24px;display:flex;align-items:center;gap:20px;margin-bottom:20px}}
.alert-icon{{font-family:'Fraunces',serif;font-style:italic;color:var(--amber);font-size:26px}}
.alert-text{{font-size:14px;line-height:1.5;color:var(--ink2)}}.alert-text strong{{color:var(--ink)}}
.fbar{{display:flex;gap:14px;align-items:center;margin-bottom:20px;flex-wrap:wrap}}
.sinput,.sselect{{background:var(--surf);border:1px solid var(--bdr);color:var(--ink);font-family:'Bricolage Grotesque',sans-serif;font-size:13px;padding:10px 14px;border-radius:10px;outline:none;transition:border-color .2s}}
.sinput{{min-width:240px}}.sinput:focus,.sselect:focus{{border-color:var(--amber)}}
.sinput::placeholder{{color:var(--ink4)}}
.sbtn{{background:var(--surf);border:1px solid var(--bdr);color:var(--ink3);font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;padding:10px 14px;border-radius:10px;cursor:pointer;transition:all .2s}}
.sbtn:hover{{color:var(--ink)}}.sbtn.active{{color:var(--amber);border-color:var(--amber)}}
.twrap{{background:var(--surf);border:1px solid var(--bdr);border-radius:18px;overflow:hidden}}
.tscroll{{max-height:600px;overflow-y:auto}}
.tscroll::-webkit-scrollbar{{width:6px}}.tscroll::-webkit-scrollbar-track{{background:var(--surf)}}.tscroll::-webkit-scrollbar-thumb{{background:var(--bdr2);border-radius:3px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
thead{{position:sticky;top:0;background:var(--surf)}}
th{{text-align:left;padding:14px;font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink3);border-bottom:1px solid var(--bdr2);font-weight:500}}
th.n{{text-align:right}}
td{{padding:14px;border-bottom:1px solid var(--bdr);color:var(--ink2);vertical-align:middle}}
tr:hover td{{background:rgba(232,176,72,.025)}}
.nc{{color:var(--ink);font-weight:500}}.n{{text-align:right;font-family:'JetBrains Mono',monospace}}
.yc{{font-family:'Fraunces',serif;font-size:16px;font-weight:500}}
.dp{{display:inline-block;font-family:'JetBrains Mono',monospace;font-size:11px;padding:3px 8px;border-radius:4px}}
.dp.up{{color:var(--sage);background:var(--sagesoft)}}.dp.dn{{color:var(--coral);background:var(--coralsoft)}}.dp.fl{{color:var(--ink3);background:rgba(255,255,255,.04)}}
.cgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px;margin-bottom:24px}}
.ccard{{background:var(--surf);border:1px solid var(--bdr);border-radius:14px;padding:18px 20px;cursor:pointer;transition:all .25s}}
.ccard:hover{{border-color:var(--amber2);transform:translateY(-2px);box-shadow:0 10px 30px -10px rgba(0,0,0,.6)}}
.cc-head{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}}
.cc-name{{font-family:'Fraunces',serif;font-size:18px;font-weight:500;letter-spacing:-.02em}}
.cc-yield{{font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:500}}
.cc-stats{{display:flex;justify-content:space-between;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--ink4);letter-spacing:.06em;text-transform:uppercase;margin-top:10px}}
.cc-bar{{height:4px;background:var(--bdr);border-radius:2px;overflow:hidden;margin-top:12px}}
.cc-bar-fill{{height:100%;background:linear-gradient(90deg,var(--amber2),var(--amber));border-radius:2px;transition:width .5s ease}}
footer{{margin-top:60px;padding-top:24px;border-top:1px solid var(--bdr);display:flex;justify-content:space-between;font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink4)}}
@media(max-width:880px){{.kpi-grid{{grid-template-columns:repeat(2,1fr)}}.exec-grid{{grid-template-columns:1fr}}.movers{{grid-template-columns:1fr}}}}
@media(max-width:640px){{.wrap{{padding:18px 18px 60px}}.kpi-val{{font-size:36px}}.hero-title{{font-size:36px}}}}
</style>
</head>
<body>

<!-- PASSWORD GATE -->
<div id="gate">
  <div class="gate-box">
    <div class="gate-logo">yield.</div>
    <div class="gate-sub">Rentomojo · Analytics Dashboard</div>
    <div class="gate-label">Enter password to continue</div>
    <input type="password" id="pwdInput" class="gate-input" placeholder="••••••••••••" onkeydown="if(event.key==='Enter')checkPwd()">
    <button class="gate-btn" onclick="checkPwd()">Access Dashboard →</button>
    <div class="gate-err" id="gateErr"></div>
  </div>
</div>

<!-- DASHBOARD -->
<div id="dash" style="display:none">
<div class="wrap">
<header>
  <div>
    <div class="brand-mark">yield.</div>
    <div class="brand-sub">Rentomojo · Ops Cockpit</div>
  </div>
  <div style="text-align:right">
    <span class="pulse"></span><span class="meta-text" id="lastUpd"></span>
  </div>
</header>

<div class="hero">
  <div class="hero-title">Rental <em>yield</em><br>at a glance.</div>
  <div class="hero-meta">
    <div id="metaMonths">— <strong>MONTHS</strong></div>
    <div id="metaCities">— <strong>CITIES</strong></div>
    <div id="metaCats">— <strong>CATEGORIES</strong></div>
  </div>
</div>

<div class="controls">
  <div class="tgroup" id="acToggle">
    <button class="on" data-val="total">Total</button>
    <button data-val="no_ac">Without AC</button>
  </div>
  <span style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--ink4);letter-spacing:.1em;text-transform:uppercase;margin-left:auto">Yield = Rent ÷ Sourcing Cost</span>
</div>

<div class="kpi-grid" id="kpis"></div>

<nav class="tabs">
  <button class="tab active" data-tab="exec">Executive</button>
  <button class="tab" data-tab="cat">Categories</button>
  <button class="tab" data-tab="city">Cities</button>
</nav>

<!-- EXEC -->
<section class="panel active" id="panel-exec">
  <div class="alerts"><div class="alert-icon">!</div><div class="alert-text" id="alertText">Loading...</div></div>
  <div class="exec-grid">
    <div class="card"><div class="sec-title">Yield trajectory</div><div class="sec-sub">Monthly · Rent ÷ Sourcing Cost</div><div class="chart-box"><canvas id="trendChart"></canvas></div></div>
    <div class="card"><div class="sec-title">Revenue mix</div><div class="sec-sub">Top categories · latest month</div><div class="chart-box"><canvas id="mixChart"></canvas></div></div>
  </div>
  <div class="movers">
    <div class="mover-card"><div class="mover-head"><div class="sec-title">Rising</div><div class="mtag up">MoM ↑</div></div><div id="winners"></div></div>
    <div class="mover-card"><div class="mover-head"><div class="sec-title">Declining</div><div class="mtag dn">MoM ↓</div></div><div id="losers"></div></div>
  </div>
  <div class="card"><div class="sec-title">All categories · 3-month yield</div><div class="sec-sub">Grouped bar</div><div class="chart-box" style="height:400px"><canvas id="heatChart"></canvas></div></div>
</section>

<!-- CATEGORIES -->
<section class="panel" id="panel-cat">
  <div class="fbar">
    <input type="text" id="catSearch" class="sinput" placeholder="Search category...">
    <button class="sbtn active" data-sort="cost">Sort: Volume</button>
    <button class="sbtn" data-sort="yield">Sort: Yield</button>
    <button class="sbtn" data-sort="delta">Sort: Δ MoM</button>
  </div>
  <div class="twrap"><div class="tscroll">
    <table><thead><tr>
      <th>Category</th><th class="n" id="h1">Month 1</th><th class="n" id="h2">Month 2</th><th class="n" id="h3">Month 3</th>
      <th class="n">Δ MoM</th><th class="n">Rent</th><th class="n">Cost</th><th>Trend</th>
    </tr></thead><tbody id="catBody"></tbody></table>
  </div></div>
</section>

<!-- CITIES -->
<section class="panel" id="panel-city">
  <div class="fbar">
    <input type="text" id="citySearch" class="sinput" placeholder="Search city...">
    <select class="sselect" id="cityCat"><option value="">All categories</option></select>
    <button class="sbtn active" data-csort="cost">Sort: Volume</button>
    <button class="sbtn" data-csort="yield">Sort: Yield</button>
    <button class="sbtn" data-csort="delta">Sort: Δ MoM</button>
  </div>
  <div class="cgrid" id="cityGrid"></div>
  <div class="twrap"><div class="tscroll">
    <table><thead><tr>
      <th>City</th><th class="n" id="ch1">M1</th><th class="n" id="ch2">M2</th><th class="n" id="ch3">M3</th>
      <th class="n">Δ MoM</th><th class="n">Rent</th><th class="n">Cost</th><th class="n">Orders</th><th>Trend</th>
    </tr></thead><tbody id="cityBody"></tbody></table>
  </div></div>
</section>

<footer>
  <div>Yield Analytics · Rentomojo · Auto-updated daily 10:00 AM IST</div>
  <div>Source: Google Sheets → GitHub Actions → GitHub Pages</div>
</footer>
</div>
</div>

<script>
const PWD = 'UmVudG9tb2pvMTIz'; // encoded
const DATA = {data_json};

function checkPwd(){{
  const v = document.getElementById('pwdInput').value;
  if(btoa(v)===PWD){{
    sessionStorage.setItem('yd_auth',PWD);
    document.getElementById('gate').classList.add('hidden');
    document.getElementById('dash').style.display='block';
    init();
  }}else{{
    document.getElementById('gateErr').textContent='Incorrect password. Try again.';
    document.getElementById('pwdInput').value='';
    document.getElementById('pwdInput').focus();
  }}
}}

// Auto-login if session exists
if(sessionStorage.getItem('yd_auth')===PWD){{
  document.getElementById('gate').classList.add('hidden');
  document.getElementById('dash').style.display='block';
  window.addEventListener('DOMContentLoaded',init);
}}

const fINR=n=>n>=1e7?'₹'+(n/1e7).toFixed(2)+' Cr':n>=1e5?'₹'+(n/1e5).toFixed(2)+' L':'₹'+(n/1e3).toFixed(1)+'k';
const fN=n=>n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'k':n.toFixed(0);
const lbl=m=>{{const[y,mo]=m.split('-');return['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+mo-1]+"'"+y.slice(2)}};
let MODE='total',catSort='cost',citySort='cost';
let TC=null,MC=null,HC=null;

function getSeries(){{return MODE==='no_ac'?DATA.monthly_no_ac:DATA.monthly;}}

function renderKPIs(){{
  const s=getSeries();
  const last=s[s.length-1],prev=s[s.length-2]||last;
  const d=last.yield_pct-prev.yield_pct;
  const dc=d>0.05?'up':d<-0.05?'dn':'fl';
  const arr=v=>v>0.05?'↑':v<-0.05?'↓':'→';
  const rd=prev.rent?((last.rent-prev.rent)/prev.rent*100):0;
  const items=[
    {{l:'Yield · Latest Month',v:last.yield_pct.toFixed(2),u:'%',d,dt:(d>0?'+':'')+d.toFixed(2)+' pp vs prev'}},
    {{l:'Rent Earned',v:'₹'+(last.rent/1e7).toFixed(2),u:'Cr',d:rd,dt:(rd>0?'+':'')+rd.toFixed(1)+'% MoM'}},
    {{l:'Sourcing Cost',v:'₹'+(last.cost/1e7).toFixed(1),u:'Cr',d:0,dt:fINR(last.cost)}},
    {{l:'Orders (latest)',v:last.orders?fN(last.orders):'—',u:'',d:0,dt:DATA.months.length+' months tracked'}},
  ];
  document.getElementById('kpis').innerHTML=items.map(k=>`
    <div class="kpi">
      <div class="kpi-lbl">${{k.l}}</div>
      <div class="kpi-val">${{k.v}}<span class="u">${{k.u}}</span></div>
      <div class="kpi-delta ${{k.d>0.05?'up':k.d<-0.05?'dn':'fl'}}">${{arr(k.d)}} ${{k.dt}}</div>
    </div>`).join('');
}}

function cOpts(yPct,legend,indexAxis){{
  return{{responsive:true,maintainAspectRatio:false,indexAxis:indexAxis||'x',
    plugins:{{
      legend:{{display:!!legend,position:'top',align:'end',labels:{{color:'#C7BFB1',font:{{family:'JetBrains Mono',size:10}},boxWidth:10,boxHeight:10}}}},
      tooltip:{{backgroundColor:'#221E1A',borderColor:'#38312A',borderWidth:1,titleColor:'#F5F0E6',bodyColor:'#C7BFB1',padding:12,
        callbacks:{{label:c=>c.dataset.label+': '+(yPct?c.parsed[indexAxis==='y'?'x':'y'].toFixed(2)+'%':fINR(c.parsed.y))}}}}
    }},
    scales:{{
      x:{{grid:{{color:'rgba(255,255,255,.04)'}},ticks:{{color:'#8A8478',font:{{family:'JetBrains Mono',size:10}}}},border:{{color:'#2A2520'}}}},
      y:{{grid:{{color:'rgba(255,255,255,.04)'}},ticks:{{color:'#8A8478',font:{{family:'JetBrains Mono',size:10}},callback:v=>yPct?v.toFixed(1)+'%':v}},border:{{color:'#2A2520'}}}}
    }}
  }};
}}

function renderTrend(){{
  const s=getSeries();
  const ctx=document.getElementById('trendChart').getContext('2d');
  const g=ctx.createLinearGradient(0,0,0,320);
  g.addColorStop(0,'rgba(232,176,72,.35)');g.addColorStop(1,'rgba(232,176,72,0)');
  if(TC)TC.destroy();
  TC=new Chart(ctx,{{type:'line',data:{{labels:s.map(x=>lbl(x.month_str)),datasets:[{{label:'Yield %',data:s.map(x=>x.yield_pct),borderColor:'#E8B048',backgroundColor:g,fill:true,tension:.32,borderWidth:2.5,pointBackgroundColor:'#F5F0E6',pointBorderColor:'#E8B048',pointBorderWidth:2,pointRadius:6,pointHoverRadius:9}}]}},options:cOpts(true,false)}});
}}

function renderMix(){{
  const lm=DATA.months[DATA.months.length-1];
  const rows=DATA.cat_month.filter(r=>r.month_str===lm&&(MODE==='no_ac'?!/air condition/i.test(r.sub_cat):true)).sort((a,b)=>b.rent-a.rent);
  const top=rows.slice(0,7),rest=rows.slice(7).reduce((s,r)=>s+r.rent,0);
  const labels=top.map(r=>r.sub_cat).concat(rest>0?['Others']:[]);
  const vals=top.map(r=>r.rent).concat(rest>0?[rest]:[]);
  const pal=['#E8B048','#D4A04C','#B5A4D9','#8FB89A','#E47E6C','#9DB4D4','#C7A88A','#5C5750'];
  if(MC)MC.destroy();
  MC=new Chart(document.getElementById('mixChart').getContext('2d'),{{type:'doughnut',data:{{labels,datasets:[{{data:vals,backgroundColor:pal,borderColor:'#1A1714',borderWidth:2}}]}},options:{{responsive:true,maintainAspectRatio:false,cutout:'62%',plugins:{{legend:{{position:'right',labels:{{color:'#C7BFB1',font:{{family:'JetBrains Mono',size:10}},boxWidth:10,boxHeight:10,padding:10}}}},tooltip:{{backgroundColor:'#221E1A',borderColor:'#38312A',borderWidth:1,callbacks:{{label:c=>c.label+': '+fINR(c.raw)}}}}}}}}}}); 
}}

function renderHeat(){{
  const lm=DATA.months[DATA.months.length-1];
  const cats=[...new Set(DATA.cat_month.map(r=>r.sub_cat))].filter(c=>MODE==='no_ac'?!/air condition/i.test(c):true);
  const mc={{}};DATA.cat_month.filter(r=>r.month_str===lm).forEach(r=>mc[r.sub_cat]=r.cost);
  cats.sort((a,b)=>(mc[b]||0)-(mc[a]||0));
  const top=cats.slice(0,18);
  const gy=(c,m)=>{{const r=DATA.cat_month.find(x=>x.sub_cat===c&&x.month_str===m);return r?r.yield_pct:0;}};
  if(HC)HC.destroy();
  HC=new Chart(document.getElementById('heatChart').getContext('2d'),{{
    type:'bar',
    data:{{labels:top,datasets:DATA.months.map((m,i)=>({
      label:lbl(m),
      data:top.map(c=>gy(c,m)),
      backgroundColor:['#5C5750','#B5A4D9','#E8B048'][i]||'#888',
      borderRadius:3
    }})}},
    options:cOpts(true,true,'y')
  }});
}}

function renderMovers(){{
  const lm=DATA.months[DATA.months.length-1];
  const pm=DATA.months[DATA.months.length-2];
  if(!pm){{document.getElementById('winners').innerHTML='<div style="color:var(--ink4);font-size:13px;padding:20px 0">Need 2+ months of data</div>';document.getElementById('losers').innerHTML='';return;}}
  const cats=[...new Set(DATA.cat_month.map(r=>r.sub_cat))].filter(c=>MODE==='no_ac'?!/air condition/i.test(c):true);
  const arr=cats.map(cat=>{{
    const cm=DATA.cat_month.find(r=>r.sub_cat===cat&&r.month_str===lm);
    const pp=DATA.cat_month.find(r=>r.sub_cat===cat&&r.month_str===pm);
    if(!cm||!pp||pp.cost<1e6)return null;
    return{{cat,cur:cm.yield_pct,prev:pp.yield_pct,delta:cm.yield_pct-pp.yield_pct,cost:cm.cost}};
  }}).filter(Boolean);
  arr.sort((a,b)=>b.delta-a.delta);
  const tpl=items=>items.map(i=>`<div class="mr"><div class="mr-name">${{i.cat}}</div><div class="mr-vals"><div class="mr-cur">${{i.cur.toFixed(2)}}%</div><div class="mr-d ${{i.delta>=0?'up':'dn'}}">${{i.delta>=0?'+':''}}${{i.delta.toFixed(2)}} pp</div></div></div>`).join('');
  document.getElementById('winners').innerHTML=tpl(arr.slice(0,5));
  document.getElementById('losers').innerHTML=tpl(arr.slice(-5).reverse());
}}

function spark(vals,color){{
  if(vals.length<2)return '';
  const w=80,h=26,max=Math.max(...vals),min=Math.min(...vals),range=max-min||1;
  const pts=vals.map((v,i)=>[i/(vals.length-1)*w,h-4-((v-min)/range)*(h-8)]);
  const path=pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+','+p[1].toFixed(1)).join(' ');
  const lp=pts[pts.length-1];
  return`<svg viewBox="0 0 ${{w}} ${{h}}" style="width:80px;height:26px;display:inline-block"><path d="${{path}}" fill="none" stroke="${{color}}" stroke-width="1.5" stroke-linecap="round"/><circle cx="${{lp[0]}}" cy="${{lp[1]}}" r="2.5" fill="${{color}}"/></svg>`;
}}

function renderCatTable(){{
  const search=document.getElementById('catSearch').value.toLowerCase();
  const months=DATA.months;
  const [m1,m2,m3]=months.length>=3?months.slice(-3):months.length===2?[null,...months]:months.length===1?[null,null,...months]:[null,null,null];
  document.getElementById('h1').textContent=m1?lbl(m1):'—';
  document.getElementById('h2').textContent=m2?lbl(m2):'—';
  document.getElementById('h3').textContent=m3?lbl(m3):'—';
  const cats=[...new Set(DATA.cat_month.map(r=>r.sub_cat))].filter(c=>(MODE==='no_ac'?!/air condition/i.test(c):true)&&c.toLowerCase().includes(search));
  const rows=cats.map(cat=>{{
    const g=m=>{{const r=DATA.cat_month.find(x=>x.sub_cat===cat&&x.month_str===m);return r?r:{{yield_pct:0,rent:0,cost:0}};}}
    const r1=m1?g(m1):{{yield_pct:0}},r2=m2?g(m2):{{yield_pct:0}},r3=m3?g(m3):{{yield_pct:0}};
    const delta=r3.yield_pct-(r2.yield_pct||r1.yield_pct);
    return{{cat,y1:r1.yield_pct,y2:r2.yield_pct,y3:r3.yield_pct,delta,rent:r3.rent||0,cost:r3.cost||0}};
  }}).filter(r=>r.cost>0);
  if(catSort==='cost')rows.sort((a,b)=>b.cost-a.cost);
  else if(catSort==='yield')rows.sort((a,b)=>b.y3-a.y3);
  else rows.sort((a,b)=>b.delta-a.delta);
  const dc=d=>d>0.05?'up':d<-0.05?'dn':'fl';
  document.getElementById('catBody').innerHTML=rows.map(r=>`<tr>
    <td class="nc">${{r.cat}}</td>
    <td class="n">${{r.y1?r.y1.toFixed(2)+'%':'—'}}</td>
    <td class="n">${{r.y2?r.y2.toFixed(2)+'%':'—'}}</td>
    <td class="n yc">${{r.y3.toFixed(2)}}%</td>
    <td class="n"><span class="dp ${{dc(r.delta)}}">${{r.delta>0?'+':''}}${{r.delta.toFixed(2)}} pp</span></td>
    <td class="n">${{fINR(r.rent)}}</td>
    <td class="n">${{fINR(r.cost)}}</td>
    <td>${{spark([r.y1,r.y2,r.y3].filter(Boolean),r.delta>=0?'#8FB89A':'#E47E6C')}}</td>
  </tr>`).join('')||'<tr><td colspan="8" style="text-align:center;color:var(--ink4);padding:30px">No results</td></tr>';
}}

function renderCityView(){{
  const search=document.getElementById('citySearch').value.toLowerCase();
  const catF=document.getElementById('cityCat').value;
  const months=DATA.months;
  const [m1,m2,m3]=months.length>=3?months.slice(-3):months.length===2?[null,...months]:months.length===1?[null,null,...months]:[null,null,null];
  ['ch1','ch2','ch3'].forEach((id,i)=>document.getElementById(id).textContent=[m1,m2,m3][i]?lbl([m1,m2,m3][i]):'—');
  const cities=DATA.cities.filter(c=>c.toLowerCase().includes(search));
  const rows=cities.map(city=>{{
    const agg=(m)=>{{
      if(!m)return{{rent:0,cost:0,orders:0}};
      let src;
      if(catF)src=DATA.city_cat_month.filter(r=>r.city===city&&r.sub_cat===catF&&r.month_str===m);
      else if(MODE==='no_ac')src=DATA.city_cat_month.filter(r=>r.city===city&&!/air condition/i.test(r.sub_cat)&&r.month_str===m);
      else src=DATA.city_month.filter(r=>r.city===city&&r.month_str===m);
      return src.reduce((a,r)=>{{a.rent+=r.rent||0;a.cost+=r.cost||0;a.orders+=r.orders||0;return a;}},{{rent:0,cost:0,orders:0}});
    }};
    const a1=agg(m1),a2=agg(m2),a3=agg(m3);
    const y=(a)=>a.cost>0?a.rent/a.cost*100:0;
    const y3=y(a3),y2=y(a2),y1=y(a1);
    return{{city,y1,y2,y3,delta:y3-(y2||y1),rent:a3.rent,cost:a3.cost,orders:a3.orders}};
  }}).filter(r=>r.cost>0);
  if(citySort==='cost')rows.sort((a,b)=>b.cost-a.cost);
  else if(citySort==='yield')rows.sort((a,b)=>b.y3-a.y3);
  else rows.sort((a,b)=>b.delta-a.delta);
  const mc=Math.max(...rows.map(r=>r.cost),1);
  const dc=d=>d>0.05?'up':d<-0.05?'dn':'fl';
  document.getElementById('cityGrid').innerHTML=rows.map(r=>`
    <div class="ccard">
      <div class="cc-head"><div class="cc-name">${{r.city}}</div><div class="cc-yield" style="color:${{r.y3>=8.5?'var(--sage)':r.y3>=7.5?'var(--amber)':'var(--coral)}}">${{r.y3.toFixed(2)}}%</div></div>
      <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--ink3)">${{fINR(r.rent)}} rent &nbsp;<span class="dp ${{dc(r.delta)}}" style="font-size:10px;padding:2px 6px">${{r.delta>0?'+':''}}${{r.delta.toFixed(2)}}pp</span></div>
      <div class="cc-stats"><span>ORDERS <strong>${{r.orders.toLocaleString()}}</strong></span><span>COST <strong>${{fINR(r.cost)}}</strong></span></div>
      <div class="cc-bar"><div class="cc-bar-fill" style="width:${{(r.cost/mc*100).toFixed(1)}}%"></div></div>
    </div>`).join('')||'<div style="color:var(--ink4);padding:40px;text-align:center;grid-column:1/-1">No results</div>';
  const dc2=d=>d>0.05?'up':d<-0.05?'dn':'fl';
  document.getElementById('cityBody').innerHTML=rows.map(r=>`<tr>
    <td class="nc">${{r.city}}</td>
    <td class="n">${{r.y1?r.y1.toFixed(2)+'%':'—'}}</td>
    <td class="n">${{r.y2?r.y2.toFixed(2)+'%':'—'}}</td>
    <td class="n yc">${{r.y3.toFixed(2)}}%</td>
    <td class="n"><span class="dp ${{dc2(r.delta)}}">${{r.delta>0?'+':''}}${{r.delta.toFixed(2)}} pp</span></td>
    <td class="n">${{fINR(r.rent)}}</td>
    <td class="n">${{fINR(r.cost)}}</td>
    <td class="n">${{r.orders.toLocaleString()}}</td>
    <td>${{spark([r.y1,r.y2,r.y3].filter(Boolean),r.delta>=0?'#8FB89A':'#E47E6C')}}</td>
  </tr>`).join('')||'<tr><td colspan="9" style="text-align:center;color:var(--ink4);padding:30px">No results</td></tr>';
}}

function buildAlert(){{
  const s=getSeries();
  if(s.length<2){{document.getElementById('alertText').innerHTML='Dashboard is live. Add more months of data for trend analysis.';return;}}
  const last=s[s.length-1],prev=s[s.length-2];
  const d=(last.yield_pct-prev.yield_pct).toFixed(2);
  const sign=d>0?'up':'down';
  const abs=Math.abs(d);
  const lm=DATA.months[DATA.months.length-1];
  const pm=DATA.months[DATA.months.length-2];
  const cats=DATA.cat_month.filter(r=>r.month_str===lm);
  const pcat=DATA.cat_month.filter(r=>r.month_str===pm);
  let worst='',best='';
  let maxDrop=-Infinity,maxRise=-Infinity;
  cats.forEach(r=>{{const p=pcat.find(x=>x.sub_cat===r.sub_cat);if(p&&p.cost>5e6){{const delta=r.yield_pct-p.yield_pct;if(delta<maxDrop){{maxDrop=delta;worst=r.sub_cat;}}if(delta>maxRise){{maxRise=delta;best=r.sub_cat;}}}}}});
  document.getElementById('alertText').innerHTML=`Yield moved <strong>${{sign==='up'?'+':''}}${{d}} pp</strong> from ${{lbl(pm)}} (${{prev.yield_pct.toFixed(2)}}%) to ${{lbl(lm)}} (${{last.yield_pct.toFixed(2)}}%). ${{worst?`Biggest drop: <strong>${{worst}}</strong> (${{maxDrop.toFixed(2)}} pp).`:''}} ${{best?`Top riser: <strong>${{best}}</strong> (+${{maxRise.toFixed(2)}} pp).`:''}}`;
}}

function init(){{
  document.getElementById('lastUpd').textContent='Updated '+DATA.last_updated;
  document.getElementById('metaMonths').innerHTML=DATA.months.length+' <strong>MONTHS</strong>';
  document.getElementById('metaCities').innerHTML=DATA.cities.length+' <strong>CITIES</strong>';
  document.getElementById('metaCats').innerHTML=DATA.categories.length+' <strong>CATEGORIES</strong>';
  const cf=document.getElementById('cityCat');
  DATA.categories.forEach(c=>{{const o=document.createElement('option');o.value=c;o.textContent=c;cf.appendChild(o);}});
  renderAll();
  wireEvents();
}}

function renderAll(){{
  renderKPIs();renderTrend();renderMix();renderHeat();renderMovers();renderCatTable();renderCityView();buildAlert();
}}

function wireEvents(){{
  document.getElementById('acToggle').addEventListener('click',e=>{{
    if(e.target.tagName!=='BUTTON')return;
    document.querySelectorAll('#acToggle button').forEach(b=>b.classList.remove('on'));
    e.target.classList.add('on');MODE=e.target.dataset.val;renderAll();
  }});
  document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click',()=>{{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');document.getElementById('panel-'+t.dataset.tab).classList.add('active');
  }}));
  document.getElementById('catSearch').addEventListener('input',renderCatTable);
  document.querySelectorAll('[data-sort]').forEach(b=>b.addEventListener('click',()=>{{
    document.querySelectorAll('[data-sort]').forEach(x=>x.classList.remove('active'));
    b.classList.add('active');catSort=b.dataset.sort;renderCatTable();
  }}));
  document.getElementById('citySearch').addEventListener('input',renderCityView);
  document.getElementById('cityCat').addEventListener('change',renderCityView);
  document.querySelectorAll('[data-csort]').forEach(b=>b.addEventListener('click',()=>{{
    document.querySelectorAll('[data-csort]').forEach(x=>x.classList.remove('active'));
    b.classList.add('active');citySort=b.dataset.csort;renderCityView();
  }}));
}}
</script>
</body>
</html>"""

with open('index.html','w',encoding='utf-8') as f:
    f.write(HTML)

print(f"index.html written ({len(HTML):,} bytes)")
