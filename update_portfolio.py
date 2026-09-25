#!/usr/bin/env python3
"""Keeps the affiliate database up to date.

Inputs you edit (in GitHub, Excel or any editor):
  merchants.csv  - one row per Awin merchant (primary_account, notes, status are yours to change)
  sites.csv      - which merchants each of your websites promotes (advertiser_ids, space-separated)

Generated on every run (do not edit by hand):
  affiliate-links.csv  - every seller's affiliate link, HTML snippet and deep-link prefix
  blog-deeplinks.json  - per-site merchant links used by the daily blog publisher
  pages.csv            - each merchant's important pages (best sellers, trending, new, deals,
                         top products) found automatically and checked to open; add your own
                         rows with source=manual and they are always kept
  creatives.csv        - every vendor's creatives (banners, logos, text links). Add banner rows
                         with just advertiser_id + creative_id + group_id (+ size) and the job
                         fills in image_url, click_url and the ready-to-paste html_code.

If the AWIN_API_TOKEN secret is set, the script first pulls the list of joined
programmes for both publisher accounts from the Awin API: new merchants are added,
names/sites/categories/logos refreshed, and merchants you are no longer joined to
are marked status=left. Your own columns (primary_account, notes) are never overwritten.
"""
import csv, json, os, sys, urllib.parse, urllib.request, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLISHERS = {"3067297": "main", "3075433": "coupondepots.dev"}
PRIMARY_DEFAULT = "3067297"
AWIN = "https://www.awin1.com/cread.php?awinmid={mid}&awinaffid={aff}"

def read_csv(name):
    with open(os.path.join(HERE, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def write_csv(name, rows, fields):
    with open(os.path.join(HERE, name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

def home(url):
    url = (url or "").strip()
    if not url: return ""
    if "://" not in url: url = "https://" + url
    p = urllib.parse.urlparse(url)
    return f"{p.scheme}://{p.netloc}/"

def awin_joined(pid, token):
    url = f"https://api.awin.com/publishers/{pid}/programmes?relationship=joined"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": "affiliate-data-updater"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def sync_from_awin(merchants):
    token = os.environ.get("AWIN_API_TOKEN", "").strip()
    if not token:
        print("AWIN_API_TOKEN not set - skipping Awin sync, regenerating outputs only"); return merchants
    by_id = {m["advertiser_id"]: m for m in merchants}
    joined = {}
    for pid in PUBLISHERS:
        try:
            progs = awin_joined(pid, token)
        except Exception as e:
            print(f"Awin API failed for {pid}: {e} - keeping existing data"); return merchants
        for p in progs:
            joined.setdefault(str(p["id"]), {"p": p, "accounts": set()})["accounts"].add(pid)
    for mid, j in joined.items():
        p = j["p"]; accs = ";".join(sorted(j["accounts"]))
        region = p.get("primaryRegion") or {}
        m = by_id.get(mid)
        if m is None:
            m = {"advertiser_id": mid, "primary_account": PRIMARY_DEFAULT if PRIMARY_DEFAULT in j["accounts"] else sorted(j["accounts"])[0], "notes": "added automatically"}
            merchants.append(m); by_id[mid] = m; print("NEW merchant", mid, p.get("name"))
        m.update({"brand": m.get("brand") or p.get("name", ""),
                  "website": home(p.get("displayUrl")) or m.get("website", ""),
                  "category": (p.get("primarySector") or {}).get("name", m.get("category", "")) if isinstance(p.get("primarySector"), dict) else p.get("primarySector") or m.get("category", ""),
                  "region": region.get("countryCode", m.get("region", "")) if isinstance(region, dict) else m.get("region", ""),
                  "logo_url": p.get("logoUrl") or m.get("logo_url", ""),
                  "joined_on_accounts": accs, "status": "joined"})
        if m.get("primary_account") not in j["accounts"]:
            m["primary_account"] = sorted(j["accounts"])[0]
    for m in merchants:
        if m["advertiser_id"] not in joined and m.get("status") != "left":
            m["status"] = "left"; print("LEFT (no longer joined):", m["advertiser_id"], m.get("brand"))
    return merchants

def main():
    merchants = read_csv("merchants.csv")
    fields = list(merchants[0].keys()) if merchants else []
    merchants = sync_from_awin(merchants)
    merchants.sort(key=lambda m: m.get("brand", "").lower())
    write_csv("merchants.csv", merchants, fields)

    sites = read_csv("sites.csv")
    by_id = {m["advertiser_id"]: m for m in merchants}
    pages = build_pages(merchants, sites)
    used = {}
    for s in sites:
        for mid in s["advertiser_ids"].split():
            used.setdefault(mid, []).append(s["site"])

    links = []
    for m in merchants:
        aff = m.get("primary_account") or PRIMARY_DEFAULT
        link = AWIN.format(mid=m["advertiser_id"], aff=aff)
        accs = m.get("joined_on_accounts", "")
        links.append({
            "brand": m.get("brand", ""), "advertiser_id": m["advertiser_id"], "account": aff,
            "joined_on_accounts": accs.replace(";", " + "), "status": m.get("status", ""),
            "website": m.get("website", ""), "category": m.get("category", ""),
            "used_on_sites": ", ".join(used.get(m["advertiser_id"], [])),
            "affiliate_link": link,
            "affiliate_link_3075433": AWIN.format(mid=m["advertiser_id"], aff="3075433") if "3075433" in accs else "",
            "html_link": f'<a href="{link}" target="_blank" rel="sponsored noopener">{m.get("brand","")}</a>',
            "deep_link_prefix": link + "&ued=",
            "deep_link_home": link + "&ued=" + urllib.parse.quote(m.get("website", ""), safe=""),
            "logo_url": m.get("logo_url", ""),
            "awin_profile": f"https://ui.awin.com/merchant-profile/{m['advertiser_id']}",
        })
    write_csv("affiliate-links.csv", links, list(links[0].keys()))

    out = {"updated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
           "deep_link_format": "https://www.awin1.com/cread.php?awinmid={advertiser_id}&awinaffid={account}&ued={URL_ENCODED_PAGE}",
           "sites": []}
    for s in sites:
        ms = []
        for mid in s["advertiser_ids"].split():
            m = by_id.get(mid)
            if not m:
                print(f"WARNING: site {s['site']} lists unknown advertiser {mid}"); continue
            if m.get("status") == "left":
                print(f"WARNING: site {s['site']} promotes {m.get('brand')} but you are no longer joined"); continue
            aff = m.get("primary_account") or PRIMARY_DEFAULT
            ms.append({"advertiser_id": mid, "brand": m.get("brand", ""), "website": m.get("website", ""),
                       "category": m.get("category", ""), "account": aff,
                       "affiliate_link": AWIN.format(mid=mid, aff=aff),
                       "deep_link_prefix": AWIN.format(mid=mid, aff=aff) + "&ued=",
                       "pages": [{"type": p["page_type"], "label": p["label"], "url": p["url"],
                                  "deep_link": p["deep_link"]}
                                 for p in pages.get(mid, []) if p.get("status") == "ok"]})
        out["sites"].append({k: s[k] for k in ("site", "url", "niche", "countries", "github_repo")} | {"merchants": ms})
    with open(os.path.join(HERE, "blog-deeplinks.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    build_creatives(merchants)
    print(f"OK: {len(merchants)} merchants, {len(sites)} sites")

PAGE_FIELDS = ["advertiser_id", "brand", "account", "page_type", "label", "url", "deep_link",
               "source", "status", "last_checked"]

def build_pages(merchants, sites):
    """pages.csv: automatic rows are refreshed each run for merchants used on a site
    (set DISCOVER_PAGES=0 to skip); manual rows are never removed. Returns {mid: [rows]}."""
    import discover_pages
    path = os.path.join(HERE, "pages.csv")
    old = read_csv("pages.csv") if os.path.exists(path) else []
    by_id = {m["advertiser_id"]: m for m in merchants}
    active = {mid for s in sites for mid in s["advertiser_ids"].split()}
    do_discover = os.environ.get("DISCOVER_PAGES", "1") != "0"
    today = datetime.date.today().isoformat()
    rows = [r for r in old if r.get("source") == "manual"]
    for mid in sorted(active):
        m = by_id.get(mid)
        if not m or m.get("status") == "left" or not m.get("website"):
            continue
        auto_old = [r for r in old if r["advertiser_id"] == mid and r.get("source") != "manual"]
        found, err = discover_pages.discover(m["website"]) if do_discover else ([], "skipped")
        if found:
            for p in found:
                rows.append({"advertiser_id": mid, "page_type": p["page_type"], "label": p["label"], "url": p["url"],
                             "source": "auto", "status": "ok", "last_checked": today})
            print(f"  pages: {m.get('brand')}: {len(found)} found")
        else:
            rows.extend(auto_old)  # keep yesterday's pages if the store could not be read today
            if do_discover:
                print(f"  pages: {m.get('brand')}: none found ({err or 'no matching pages'}) - kept {len(auto_old)} previous")
    for r in rows:
        m = by_id.get(r["advertiser_id"], {})
        acc = m.get("primary_account") or PRIMARY_DEFAULT
        r["brand"], r["account"] = m.get("brand", r.get("brand", "")), acc
        r["deep_link"] = AWIN.format(mid=r["advertiser_id"], aff=acc) + "&ued=" + urllib.parse.quote(r["url"], safe="")
        r.setdefault("status", "ok")
    order = {"manual": 0, "auto": 1}
    typ = {"product": 0, "bestsellers": 1, "new": 2, "deals": 3}
    rows.sort(key=lambda r: (r.get("brand", "").lower(), order.get(r.get("source"), 2), typ.get(r.get("page_type"), 9)))
    write_csv("pages.csv", rows, PAGE_FIELDS)
    out = {}
    for r in rows:
        out.setdefault(r["advertiser_id"], []).append(r)
    return out

CREATIVE_FIELDS = ["advertiser_id", "brand", "account", "creative_type", "size", "creative_id", "group_id",
                   "image_url", "click_url", "html_code", "awin_creatives_page", "notes"]

def build_creatives(merchants):
    """creatives.csv: one Awin logo row per merchant (automatic) + any banners you add.
    Awin creative links: image  https://www.awin1.com/cshow.php?s={creative}&v={mid}&q={group}&r={account}
                         click  https://www.awin1.com/cread.php?s={creative}&v={mid}&q={group}&r={account}"""
    path = os.path.join(HERE, "creatives.csv")
    rows = []
    if os.path.exists(path):
        rows = read_csv("creatives.csv")
    by_id = {m["advertiser_id"]: m for m in merchants}
    have_logo = {r["advertiser_id"] for r in rows if r.get("creative_type") == "logo"}
    for m in merchants:
        if m["advertiser_id"] not in have_logo and m.get("status") != "left":
            rows.append({"advertiser_id": m["advertiser_id"], "creative_type": "logo", "size": "Awin logo"})
    for r in rows:
        m = by_id.get(r.get("advertiser_id", ""), {})
        mid = r.get("advertiser_id", "")
        acc = r.get("account") or m.get("primary_account") or PRIMARY_DEFAULT
        r["account"] = acc
        r["brand"] = m.get("brand", r.get("brand", ""))
        r["awin_creatives_page"] = f"https://ui.awin.com/merchant-profile/{mid}"
        cid, grp = r.get("creative_id", "").strip(), r.get("group_id", "").strip()
        if cid:  # a banner / text-link creative from the Awin library
            q = f"s={cid}&v={mid}&q={grp}&r={acc}"
            if r.get("creative_type") != "text":
                r["image_url"] = r.get("image_url") or f"https://www.awin1.com/cshow.php?{q}"
            r["click_url"] = f"https://www.awin1.com/cread.php?{q}"
        elif r.get("creative_type") == "logo":
            r["image_url"] = m.get("logo_url") or f"https://ui.awin.com/images/upload/merchant/profile/{mid}.png"
            r["click_url"] = AWIN.format(mid=mid, aff=acc)
        if r.get("click_url"):
            alt = htmlesc(r["brand"])
            if r.get("creative_type") == "text":
                r["html_code"] = f'<a href="{r["click_url"]}" target="_blank" rel="sponsored noopener">{htmlesc(r.get("notes") or r["brand"])}</a>'
            elif r.get("image_url"):
                r["html_code"] = (f'<a href="{r["click_url"]}" target="_blank" rel="sponsored noopener">'
                                  f'<img src="{r["image_url"]}" alt="{alt}" loading="lazy"></a>')
    order = {"logo": 0, "banner": 1, "text": 2}
    rows.sort(key=lambda r: (r.get("brand", "").lower(), order.get(r.get("creative_type"), 3), r.get("size", "")))
    write_csv("creatives.csv", rows, CREATIVE_FIELDS)

def htmlesc(t):
    return (t or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")

if __name__ == "__main__":
    main()
