"""
Diagnostic Test: Frontend DOM Elements Cross-Verification
Ensures that all element IDs referenced by JavaScript exist in index.html OR are
created dynamically at runtime by the application's own JS (template literals /
innerHTML / createElement / setAttribute).

A UI built partly from JS-rendered templates legitimately has no static markup
for those fragments, so the verifier must account for runtime-injected nodes.
That is what the station-detail modal does for the "modal-forecast-*" panels:
they are injected inside app.js and then queried. They are NOT missing.
"""

import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
INDEX_HTML = ROOT_DIR / "frontend" / "index.html"
JS_DIR = ROOT_DIR / "frontend" / "js"

# id="foo" / id='foo' inside HTML strings, .id = "foo" assignments, and
# setAttribute('id', "foo") / id: 'foo' object forms are all runtime creation
# sites we accept as a valid home for a getElementById target.
_ID_IN_TEMPLATE = re.compile(r"""id\s*=\s*["']([A-Za-z0-9_\-:.]+)["']""")
_ID_ASSIGN = re.compile(r"""\.id\s*=\s*["']([A-Za-z0-9_\-:.]+)["']""")
_SET_ATTRIBUTE_ID = re.compile(r"""setAttribute\(\s*["']id["']\s*,\s*["']([A-Za-z0-9_\-:.]+)["']""")
_GET_BY_ID = re.compile(r"""getElementById\(\s*["']([A-Za-z0-9_\-:.]+)["']\s*\)""")


def _read(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_dom_elements():
    print("=== Test 1: Frontend DOM Element References ===")

    html_content = _read(INDEX_HTML)
    html_ids = set(re.findall(r'id=["\']([^"\']+)["\']', html_content))
    print(f"Total element IDs defined in index.html: {len(html_ids)}")

    js_sources = {p: _read(p) for p in JS_DIR.glob("*.js")}

    # IDs the app injects itself at runtime (across every JS module), since a
    # node created in one module can be queried from another.
    runtime_ids = set()
    for src in js_sources.values():
        runtime_ids.update(_ID_IN_TEMPLATE.findall(src))
        runtime_ids.update(_ID_ASSIGN.findall(src))
        runtime_ids.update(_SET_ATTRIBUTE_ID.findall(src))
    if runtime_ids:
        print(f"Total element IDs created dynamically in JS templates: {len(runtime_ids)}")

    known_ids = html_ids | runtime_ids

    missing_ids = {}
    for js_file, js_code in js_sources.items():
        for ref_id in _GET_BY_ID.findall(js_code):
            if ref_id not in known_ids:
                missing_ids.setdefault(js_file.name, []).append(ref_id)

    if missing_ids:
        print("[FAIL] Referenced DOM element IDs are neither static nor created at runtime:")
        for file, ids in missing_ids.items():
            print(f"  In {file}: {sorted(set(ids))}")
        assert False, f"Missing IDs: {missing_ids}"

    print("[PASS] All referenced DOM element IDs are present (static in index.html or injected by JS).")


if __name__ == "__main__":
    test_dom_elements()
