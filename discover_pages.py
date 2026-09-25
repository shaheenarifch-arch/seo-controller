"""Finds each merchant's most useful pages to deep-link to: best sellers, trending,
new arrivals, deals, and the current top products. Every page is checked to open
before it is used. Manual rows you add to pages.csv (source=manual) are kept as-is."""
import json, re, urllib.parse, urllib.request, html as htmllib

UA = {"User-Agent": "Mozilla/5.0 (compatible; affiliate-data-bot/1.0; +https://github.com/shaheenarifch-arch/seo-controller)",
      "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}
TIMEOUT = 15
KEYWORDS = [  # (page_type, label, pattern) - first match wins, one page per type
    ("bestsellers", "Best sellers", r"best[-_ ]?sell|bestsell|top[-_ ]?sell|top[-_ ]?rated|most[-_ ]?popular|popular|trending|hot[-_ ]?(sale|deals|items)"),
    ("new", "New arrivals", r"new[-_ ]?arrival|new[-_ ]?in\b|just[-_ ]?in|what'?s[-_ ]?new|latest|new[-_ ]?products"),
    ("deals", "Deals & sale", r"\bsale\b|deals?\b|clearance|offers?\b|discount|outlet|black[-_ ]?friday|promotion"),
]
MAX_PRODUCTS = 3

def get(url, want_json=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        if r.status != 200:
            raise ValueError(f"HTTP {r.status}")
        body = r.read(3_000_000)
        final = r.geturl()
    text = body.decode("utf-8", "replace")
    return (json.loads(text), final) if want_json else (text, final)

def opens(url):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status == 200
    except Exception:
        return False

def same_site(a, b):
    ha, hb = urllib.parse.urlparse(a).netloc.lower(), urllib.parse.urlparse(b).netloc.lower()
    strip = lambda h: h[4:] if h.startswith("www.") else h
    return strip(ha) == strip(hb) or strip(ha).endswith("." + strip(hb)) or strip(hb).endswith("." + strip(ha))

def classify(text):
    for ptype, label, pat in KEYWORDS:
        if re.search(pat, text, re.I):
            return ptype, label
    return None, None

def shopify_pages(base):
    pages = []
    try:
        data, _ = get(base + "products.json?limit=1", want_json=True)
        if "products" not in data:
            return None
    except Exception:
        return None  # not a Shopify-style store
    found = {}
    try:
        cols, _ = get(base + "collections.json?limit=250", want_json=True)
        for c in cols.get("collections", []):
            if not c.get("products_count", 1):
                continue
            ptype, label = classify(f"{c.get('handle','')} {c.get('title','')}")
            if ptype and ptype not in found:
                title = htmllib.unescape(c.get("title", "")).strip()
                found[ptype] = {"page_type": ptype, "label": title if classify(title)[0] else f"{label} – {title}",
                                "url": f"{base}collections/{c['handle']}", "handle": c["handle"]}
    except Exception:
        pass
    if "bestsellers" not in found:  # every Shopify store supports this sort
        found["bestsellers"] = {"page_type": "bestsellers", "label": "Best sellers",
                                "url": f"{base}collections/all?sort_by=best-selling", "handle": None}
    pages.extend(found.values())
    # top products: from the best-seller collection if there is one, else the newest products
    h = found["bestsellers"].get("handle")
    src = f"{base}collections/{h}/products.json?limit=10" if h else f"{base}products.json?limit=10"
    try:
        prods, _ = get(src, want_json=True)
        n = 0
        for p in prods.get("products", []):
            title = htmllib.unescape(p.get("title", "")).strip()
            if not title or re.search(r"wholesale|gift card|gap fee|price difference|replacement part|filter", title, re.I):
                continue
            pages.append({"page_type": "product", "label": title[:90], "url": f"{base}products/{p['handle']}"})
            n += 1
            if n >= MAX_PRODUCTS:
                break
    except Exception:
        pass
    for p in pages:
        p.pop("handle", None)
    return pages

def html_pages(base):
    try:
        text, final = get(base)
    except Exception:
        return []
    found = {}
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', text, re.I | re.S):
        href, inner = m.group(1).strip(), re.sub(r"<[^>]+>", " ", m.group(2))
        inner = " ".join(htmllib.unescape(inner).split())
        url = urllib.parse.urljoin(final, href)
        if not url.startswith("http") or not same_site(url, base) or len(inner) > 60:
            continue
        ptype, label = classify(f"{inner} {urllib.parse.urlparse(url).path}")
        if ptype and ptype not in found:
            found[ptype] = {"page_type": ptype, "label": inner if inner and classify(inner)[0] else label, "url": url}
    return [p for p in found.values() if opens(p["url"])]

def discover(website):
    """Returns (pages, error). pages = [{page_type,label,url}] ordered best-first."""
    base = website if website.endswith("/") else website + "/"
    try:
        pages = shopify_pages(base)
        if pages is None:
            pages = html_pages(base)
    except Exception as e:
        return [], str(e)
    order = {"product": 0, "bestsellers": 1, "new": 2, "deals": 3}
    pages.sort(key=lambda p: order.get(p["page_type"], 9))
    return pages, None
