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

    def agg(grp_cols):
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

    df_nac  = df[~df['_cat'].str.lower().str.contains('air condition', na=False)]
    m_nac   = df_nac.groupby('_ms').agg(rent=('_rent','sum'),cost=('_cost','sum')).reset_index()
    m_nac['yield_pct'] = (m_nac['rent']/m_nac['cost']*100).round(2)
    m_nac   = m_nac.rename(columns={'_ms':'month_str'})

    total_skus = df[sku].nunique() if sku else 0

    return {
        'monthly':        monthly.to_dict('records'),
        'monthly_no_ac':  m_nac.to_dict('records'),
        'cat_month':      cat_month.to_dict('records'),
        'city_month':     city_month.to_dict('records'),
        'city_cat_month': city_cat.to_dict('records'),
        'cities':     sorted(df['_city'].dropna().unique().tolist()),
        'categories': sorted(df['_cat'].dropna().unique().tolist()),
        'months':     sorted(df['_ms'].dropna().unique().tolist()),
        'last_updated': datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d %b %Y · %I:%M %p IST'),
        'total_skus': int(total_skus)
    }

print("Fetching Monthly Yield Data...")
monthly_df = fetch_sheet(MONTHLY_TAB)
print(f"  Rows: {len(monthly_df)}  Cols: {list(monthly_df.columns)}")

print("Fetching Daily Yield Data...")
daily_df = fetch_sheet(DAILY_TAB)
print(f"  Rows: {len(daily_df)}  Cols: {list(daily_df.columns)}")

print("Computing metrics...")
data = process(monthly_df)
data_json = json.dumps(data, default=str)

# ---- HTML is written as a plain string (no f-string) to avoid brace conflicts ----
with open('template.html', 'r', encoding='utf-8') as f:
    html = f.read()

html = html.replace('__DATA_JSON__', data_json)
html = html.replace('__LAST_UPDATED__', data['last_updated'])

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"index.html written ({len(html):,} bytes)")
