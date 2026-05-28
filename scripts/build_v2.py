import json
from datetime import datetime

print("Reading dashboard data pushed by Apps Script...")

with open('data/dashboard_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

last_updated = data.get('last_updated', datetime.now().strftime('%d %b %Y · %I:%M %p IST'))

data_json = json.dumps(data, default=str)

print(f"  Months:     {len(data.get('months', []))}")
print(f"  Cities:     {len(data.get('cities', []))}")
print(f"  Categories: {len(data.get('categories', []))}")

with open('template.html', 'r', encoding='utf-8') as f:
    html = f.read()

html = html.replace('__DATA_JSON__', data_json)
html = html.replace('__LAST_UPDATED__', last_updated)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"index.html written ({len(html):,} bytes)")
