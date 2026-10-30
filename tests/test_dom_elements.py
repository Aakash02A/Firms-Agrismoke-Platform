"""
Diagnostic Test: Frontend DOM Elements Cross-Verification
Ensures that all element IDs referenced by JavaScript exist in index.html.
"""

import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
INDEX_HTML = ROOT_DIR / "frontend" / "index.html"
JS_DIR = ROOT_DIR / "frontend" / "js"

def test_dom_elements():
    print("=== Test 1: Frontend DOM Element References ===")
    
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Extract all id="..." from index.html
    html_ids = set(re.findall(r'id=["\']([^"\']+)["\']', html_content))
    print(f"Total element IDs defined in index.html: {len(html_ids)}")

    # Scan JavaScript files for getElementById('...')
    missing_ids = {}
    for js_file in JS_DIR.glob("*.js"):
        with open(js_file, "r", encoding="utf-8") as f:
            js_code = f.read()
        
        referenced_ids = re.findall(r'getElementById\(["\']([^"\']+)["\']\)', js_code)
        for ref_id in referenced_ids:
            if ref_id not in html_ids:
                if js_file.name not in missing_ids:
                    missing_ids[js_file.name] = []
                missing_ids[js_file.name].append(ref_id)

    if missing_ids:
        print("[FAIL] Missing DOM element IDs found:")
        for file, ids in missing_ids.items():
            print(f"  In {file}: {ids}")
        assert False, f"Missing IDs: {missing_ids}"
    else:
        print("[PASS] All referenced DOM element IDs are present in index.html!")

if __name__ == "__main__":
    test_dom_elements()

