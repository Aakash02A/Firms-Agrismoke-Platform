import re
from pathlib import Path

with open("frontend/index.html", encoding="utf-8") as f:
    html = f.read()

print("Searching for canvas, charts, gauges in index.html:")
for m in re.finditer(r'<([a-zA-Z0-9]+)[^>]*id=["\']([^"\']+)["\'][^>]*>', html):
    tag, el_id = m.group(1), m.group(2)
    if any(k in el_id for k in ['chart', 'gauge', 'canvas', 'map', 'tab-']):
        print(f"<{tag} id='{el_id}'>")

