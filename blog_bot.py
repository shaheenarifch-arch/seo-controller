#!/usr/bin/env python3
"""
Daily affiliate blog bot.

Every run:
  1. Picks today's sites from sites.json (rotation, or FORCE_SITES).
  2. For each site: builds Awin deep links (Link Builder API, cread.php fallback).
  3. Asks Claude for long-tail, low-competition keywords not used before.
  4. Writes a 1200+ word article per keyword with [[LINK_n]] placeholders.
  5. Swaps placeholders for real Awin deep links (rel="sponsored nofollow").
  6. Wraps it in a clean SEO page (canonical, OG, Article + FAQ JSON-LD, disclosure).
  7. Updates blog/index.html, blog/posts.json and sitemap.xml, then commits + pushes.

Env vars (GitHub secrets):
  ANTHROPIC_API_KEY   Claude API key
  GH_TOKEN            fine-grained PAT with Contents: read/write on the site repos
  AWIN_PUBLISHER_ID   your Awin publisher (affiliate) ID
  AWIN_API_TOKEN      Awin API token (optional; without it links use cread.php format)
Optional:
  GH_ORG, SITES_PER_DAY (2), POSTS_PER_SITE (2), MIN_WORDS (1200),
  KEYWORD_MODEL, ARTICLE_MODEL, FORCE_SITES ("repo1,repo2"), DRY_RUN ("1")
"""
import datetime
import html as htmllib
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.parse
import urllib.request

import anthropic

ORG = os.getenv("GH_ORG", "shaheenarifch-arch")
GH_TOKEN = os.environ["GH_TOKEN"]
AWIN_PUBLISHER_ID = os.environ["AWIN_PUBLISHER_ID"]
AWIN_TOKEN = os.getenv("AWIN_API_TOKEN", "").strip()
KEYWORD_MODEL = os.getenv("KEYWORD_MODEL", "claude-haiku-4-5-20251001")
ARTICLE_MODEL = os.getenv("ARTICLE_MODEL", "claude-sonnet-5")
SITES_PER_DAY = int(os.getenv("SITES_PER_DAY", "2"))
POSTS_PER_SITE = int(os.getenv("POSTS_PER_SITE", "2"))
MIN_WORDS = int(os.getenv("MIN_WORDS", "1200"))
FORCE_SITES = [s.strip() for s in os.getenv("FORCE_SITES", "").split(",") if s.strip()]
DRY_RUN = os.getenv("DRY_RUN", "0") in ("1", "true", "True")

client = anthropic.Anthropic()
TODAY = datetime.date.today().isoformat()


# ---------------------------------------------------------------- sites
def load_sites():
    raw = json.loads(pathlib.Path("sites.json").read_text(encoding="utf-8"))
    sites = []
    for s in raw:
        if isinstance(s, str):  # backwards compatible with the old ["repo", ...] format
            s = {"repo": s}
        s.setdefault("domain", s["repo"])
        s.setdefault("niche", s["repo"].replace("-", " ").replace(".", " "))
        s.setdefault("audience", "US online shoppers")
        s.setdefault("blog_dir", "blog")
        s.setdefault("advertisers", [])
        s.setdefault("enabled", True)
        if s["enabled"]:
            sites.append(s)
    return sites


def pick_sites(sites):
    if FORCE_SITES:
        return [s for s in sites if s["repo"] in FORCE_SITES]
    n = len(sites)
    if n == 0:
        return []
    start = ((datetime.date.today() - datetime.date(2024, 1, 1)).days * SITES_PER_DAY) % n
    return [sites[(start + i) % n] for i in range(min(SITES_PER_DAY, n))]


# ---------------------------------------------------------------- Awin
def awin_deeplink(advertiser_id, destination, clickref):
    """Awin Link Builder API; falls back to the standard cread.php deep-link format."""
    if AWIN_TOKEN:
        try:
            req = urllib.request.Request(
                f"https://api.awin.com/publishers/{AWIN_PUBLISHER_ID}/linkbuilder/generate",
                data=json.dumps({
                    "advertiserId": int(advertiser_id),
                    "destinationUrl": destination,
                    "parameters": {"clickref": clickref},
                    "shorten": False,
                }).encode(),
                headers={"Authorization": f"Bearer {AWIN_TOKEN}",
                         "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.load(r)
            if data.get("url"):
                return data["url"]
        except Exception as e:
            print(f"  awin api -> fallback link for {advertiser_id}: {e}")
    q = urllib.parse.urlencode({
        "awinmid": advertiser_id,
        "awinaffid": AWIN_PUBLISHER_ID,
        "clickref": clickref,
        "ued": destination,
    })
    return f"https://www.awin1.com/cread.php?{q}"


def build_links(site):
    """One deep link per configured product/landing URL. Returns [{id,label,advertiser,url}]."""
    links, n = [], 0
    clickref = re.sub(r"[^a-z0-9]+", "", site["repo"].lower())[:20] + TODAY.replace("-", "")
    for adv in site["advertisers"]:
        adv_id = str(adv.get("awin_id", ""))
        if not adv_id.isdigit():
            print(f"  skipping {adv.get('name')}: set a numeric awin_id in sites.json")
            continue
        for item in adv.get("urls", []):
            if "REPLACE" in item.get("url", "") or not item.get("url", "").startswith("http"):
                continue
            n += 1
            links.append({
                "id": f"LINK_{n}",
                "advertiser": adv["name"],
                "label": item.get("label", adv["name"]),
                "url": awin_deeplink(adv_id, item["url"], clickref),
            })
    return links


# ---------------------------------------------------------------- Claude
def ask(model, messages, max_tokens):
    r = client.messages.create(model=model, max_tokens=max_tokens, messages=messages)
    return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")


def get_keywords(site, used, n):
    brands = ", ".join(a["name"] for a in site["advertisers"]) or "general retailers"
    products = "; ".join(
        f'{u.get("label")}' for a in site["advertisers"] for u in a.get("urls", []))[:1500]
    prompt = f"""You are an SEO strategist for {site['domain']}, a small affiliate site about {site['niche']} for {site['audience']}.
Partner brands: {brands}. Products we can link to: {products or 'n/a'}.

Suggest {n + 3} long-tail, LOW-COMPETITION keywords a new, low-authority site can realistically rank for:
- 4-9 words, buyer or problem intent ("best X for Y", "X vs Y for Z", "how to choose X for Y", "is X worth it for Y")
- clearly answerable by linking to the products above
- no years, no bare brand names, no medical or financial claims
- must NOT repeat or closely paraphrase any of these used keywords: {json.dumps(used[-80:])}

Return ONLY a JSON array of strings."""
    try:
        text = ask(KEYWORD_MODEL, [{"role": "user", "content": prompt}], 600)
        arr = json.loads(re.search(r"\[.*\]", text, re.S).group(0))
    except Exception as e:
        print(f"  keyword error: {e}")
        arr = [f"how to choose {site['niche']} for beginners",
               f"best {site['niche']} for small budgets",
               f"{site['niche']} buying guide for first timers"]
    used_l = {u.lower() for u in used}
    out = []
    for k in arr:
        k = re.sub(r"\s+", " ", str(k)).strip().strip('"')
        if k and k.lower() not in used_l and k.lower() not in {o.lower() for o in out}:
            out.append(k)
    return out[:n]


ARTICLE_RULES = """Output EXACTLY these three blocks and nothing else (no markdown fences):
<title>SEO title, 50-60 characters, contains the keyword</title>
<meta_description>140-155 characters, contains the keyword</meta_description>
<article>
...article HTML...
</article>

Article rules:
- {min_words}-1700 words of genuinely helpful content, written for humans first.
- One <h1> containing the keyword, then <h2>/<h3> sections, short <p> paragraphs, <ul> lists, and one comparison <table> if it fits.
- Use the exact keyword in the first 100 words, one H2, and the conclusion; use natural variations elsewhere.
- Embed 3-6 affiliate links naturally, ONLY as <a href="[[LINK_n]]">descriptive anchor text</a> using the IDs below. Put the first one within the first 3 paragraphs and end with a short "Where to buy" section.
- Do NOT write any other external URL. Internal links may only be "/" or "/{blog_dir}/".
- End with an <h2>FAQ</h2> section: 4 questions as <h3>, each answered in a <p> of 40-60 words.
- Never invent prices, discount codes, ratings, stock, or claims of personally testing products. Say "check the current price" instead.
- No dates or years anywhere.

Affiliate links you may use:
{links}"""


def write_article(site, kw, links):
    link_list = "\n".join(
        f"- [[{l['id']}]] = {l['advertiser']}: {l['label']}" for l in links) or "- (none; skip links)"
    prompt = (f"Write an SEO blog article targeting the keyword \"{kw}\" for {site['domain']}, "
              f"an affiliate site about {site['niche']} for {site['audience']}.\n\n"
              + ARTICLE_RULES.format(min_words=MIN_WORDS + 100, links=link_list, blog_dir=site["blog_dir"]))
    messages = [{"role": "user", "content": prompt}]
    text = ask(ARTICLE_MODEL, messages, 8000)
    post = parse_article(text)
    if word_count(post["body"]) < MIN_WORDS:  # one expansion pass
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content":
                      f"That article is {word_count(post['body'])} words. Expand it to at least "
                      f"{MIN_WORDS + 150} words with more genuinely useful detail. Return the full "
                      "article again in the same three-block format."}]
        post = parse_article(ask(ARTICLE_MODEL, messages, 8000))
    return post


def parse_article(text):
    text = re.sub(r"```(?:html)?", "", text)
    get = lambda tag: (re.search(rf"<{tag}>(.*?)</{tag}>", text, re.S | re.I) or [None, ""])[1].strip()
    body = get("article") or text
    return {"title": htmllib.unescape(get("title")), "description": htmllib.unescape(get("meta_description")),
            "body": body}


def word_count(body):
    return len(re.sub(r"<[^>]+>", " ", body).split())


# ---------------------------------------------------------------- HTML
def embed_links(body, links):
    by_id = {l["id"]: l for l in links}
    used = []

    def repl(m):
        attrs, inner = m.group(1), m.group(2)
        href = (re.search(r'href\s*=\s*"([^"]*)"', attrs) or [None, ""])[1]
        ph = re.fullmatch(r"\[\[(LINK_\d+)\]\]", href.strip())
        if ph and ph.group(1) in by_id:
            used.append(ph.group(1))
            url = htmllib.escape(by_id[ph.group(1)]["url"], quote=True)
            return f'<a href="{url}" rel="sponsored nofollow noopener" target="_blank">{inner}</a>'
        if href.startswith(("/", "#")):
            return f'<a href="{htmllib.escape(href, quote=True)}">{inner}</a>'
        return inner  # unknown / hallucinated external link -> plain text

    body = re.sub(r"<a\b([^>]*)>(.*?)</a>", repl, body, flags=re.S | re.I)
    body = re.sub(r"\[\[LINK_\d+\]\]", "", body)  # stray placeholders

    if links and not used:  # model ignored the links: add a buying section
        items = "".join(
            f'<li><a href="{htmllib.escape(l["url"], quote=True)}" rel="sponsored nofollow noopener" '
            f'target="_blank">{htmllib.escape(l["label"])}</a> ({htmllib.escape(l["advertiser"])})</li>'
            for l in links[:4])
        body += f"<h2>Where to buy</h2><ul>{items}</ul>"
    return body, len(set(used))


def faq_jsonld(body):
    faq = re.split(r"<h2[^>]*>\s*FAQ", body, flags=re.I)
    if len(faq) < 2:
        return None
    pairs = re.findall(r"<h3[^>]*>(.*?)</h3>\s*<p[^>]*>(.*?)</p>", faq[1], re.S | re.I)
    strip = lambda s: htmllib.unescape(re.sub(r"<[^>]+>", "", s)).strip()
    if not pairs:
        return None
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": strip(q),
         "acceptedAnswer": {"@type": "Answer", "text": strip(a)}} for q, a in pairs]}


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
{css}<script type="application/ld+json">{article_ld}</script>
{faq_ld}<style>
:root{{--text:#1d1d1f;--muted:#6e6e73;--bg:#fff;--accent:#0a66c2;--line:#e5e5ea}}
@media (prefers-color-scheme:dark){{:root{{--text:#f2f2f7;--muted:#a1a1a6;--bg:#111;--accent:#6cb4ff;--line:#2c2c2e}}}}
body{{margin:0;background:var(--bg);color:var(--text);font:17px/1.7 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
.wrap{{max-width:760px;margin:0 auto;padding:24px 16px 64px}}
nav a,.meta{{color:var(--muted);font-size:14px}} a{{color:var(--accent)}}
h1{{line-height:1.25;font-size:clamp(28px,5vw,38px)}} h2{{margin-top:2em}}
table{{width:100%;border-collapse:collapse;font-size:15px;display:block;overflow-x:auto}}
th,td{{border:1px solid var(--line);padding:8px 10px;text-align:left}}
.disclosure{{font-size:13px;color:var(--muted);border-left:3px solid var(--line);padding-left:10px}}
</style>
</head>
<body><div class="wrap">
<nav><a href="/">{domain}</a> › <a href="/{blog}/">Blog</a></nav>
<p class="meta">Published {date} · {domain}</p>
<p class="disclosure">This post contains affiliate links. If you buy through them we may earn a commission at no extra cost to you.</p>
{body}
<p><a href="/{blog}/">← More guides</a></p>
</div></body></html>
"""


def render_page(site, post, filename):
    url = f"https://{site['domain']}/{site['blog_dir']}/{filename}"
    article_ld = {"@context": "https://schema.org", "@type": "Article", "headline": post["title"],
                  "description": post["description"], "datePublished": TODAY, "dateModified": TODAY,
                  "mainEntityOfPage": url,
                  "publisher": {"@type": "Organization", "name": site["domain"]}}
    faq = faq_jsonld(post["body"])
    esc = lambda s: htmllib.escape(s, quote=True)
    safe_json = lambda o: json.dumps(o).replace("</", "<\\/")
    faq_tag = f'<script type="application/ld+json">{safe_json(faq)}</script>\n' if faq else ""
    return PAGE.format(
        title=esc(post["title"]), desc=esc(post["description"]), url=url, domain=esc(site["domain"]),
        date=TODAY, body=post["body"], blog=site["blog_dir"],
        css=f'<link rel="stylesheet" href="{esc(site["stylesheet"])}">\n' if site.get("stylesheet") else "",
        article_ld=safe_json(article_ld),
        faq_ld=faq_tag,
    )


def render_index(site, posts):
    items = "\n".join(
        f'<li><a href="{htmllib.escape(p["file"])}">{htmllib.escape(p["title"])}</a>'
        f'<br><span class="meta">{p["date"]}</span> {htmllib.escape(p["description"])}</li>'
        for p in sorted(posts, key=lambda p: p["date"], reverse=True))
    post = {"title": f"Guides & buying advice | {site['domain']}",
            "description": f"Buying guides and tips about {site['niche']}.",
            "body": f"<h1>Guides &amp; buying advice</h1><ul>{items}</ul>"}
    page = render_page(site, post, "")
    page = re.sub(r'<script type="application/ld\+json">.*?</script>\n?', "", page, flags=re.S)
    return page.replace('<p class="disclosure">', '<p class="disclosure" hidden>')


def update_sitemap(root, site, urls):
    sm = root / "sitemap.xml"
    if not sm.exists():
        return
    xml = sm.read_text(encoding="utf-8")
    for u in urls:
        if f"<loc>{u}</loc>" not in xml:
            xml = xml.replace("</urlset>", f"  <url><loc>{u}</loc><lastmod>{TODAY}</lastmod></url>\n</urlset>")
    sm.write_text(xml, encoding="utf-8")


# ---------------------------------------------------------------- git
def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def process_site(site):
    repo = site["repo"]
    workdir = pathlib.Path(f"/tmp/sites/{repo}")
    subprocess.run(["rm", "-rf", str(workdir)], check=False)
    try:
        git("clone", "--depth", "1", f"https://x-access-token:{GH_TOKEN}@github.com/{ORG}/{repo}.git", str(workdir))
    except subprocess.CalledProcessError:
        raise RuntimeError(f"clone failed for {ORG}/{repo} (check repo name and GH_TOKEN access)")

    blog = workdir / site["blog_dir"]
    blog.mkdir(parents=True, exist_ok=True)
    manifest_path = blog / "posts.json"
    posts = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
    used = [p["keyword"] for p in posts]

    links = build_links(site)
    print(f"  {len(links)} affiliate deep links ready")
    keywords = get_keywords(site, used, POSTS_PER_SITE)
    print(f"  keywords: {keywords}")

    new_urls = []
    for kw in keywords:
        post = write_article(site, kw, links)
        post["body"], n_links = embed_links(post["body"], links)
        words = word_count(post["body"])
        if words < MIN_WORDS * 0.9:
            print(f"  ! skipped '{kw}': only {words} words")
            continue
        post["title"] = post["title"] or kw.title()
        post["description"] = post["description"] or f"A practical guide to {kw}."
        slug = re.sub(r"[^a-z0-9]+", "-", kw.lower()).strip("-")[:60]
        filename = f"{slug}.html"
        if (blog / filename).exists():
            filename = f"{slug}-{TODAY}.html"
        (blog / filename).write_text(render_page(site, post, filename), encoding="utf-8")
        posts.append({"keyword": kw, "title": post["title"], "description": post["description"],
                      "file": filename, "date": TODAY})
        new_urls.append(f"https://{site['domain']}/{site['blog_dir']}/{filename}")
        print(f"  + {filename} ({words} words, {n_links} affiliate links)")

    if not new_urls:
        raise RuntimeError("no posts generated")

    manifest_path.write_text(json.dumps(posts, indent=2), encoding="utf-8")
    (blog / "index.html").write_text(render_index(site, posts), encoding="utf-8")
    update_sitemap(workdir, site, [f"https://{site['domain']}/{site['blog_dir']}/", *new_urls])

    if DRY_RUN:
        print(f"  DRY_RUN: not pushing {repo}")
        return
    git("config", "user.email", "blog-bot@users.noreply.github.com", cwd=workdir)
    git("config", "user.name", "Blog Bot", cwd=workdir)
    git("add", "-A", cwd=workdir)
    git("commit", "-m", f"Blog: {len(new_urls)} new posts {TODAY}", cwd=workdir)
    git("push", cwd=workdir)
    print(f"  pushed {repo}")


def main():
    todays = pick_sites(load_sites())
    print(f"TODAY {TODAY}: {[s['repo'] for s in todays]}")
    failures = []
    for site in todays:
        print(f"--- {site['repo']} ---")
        try:
            process_site(site)
        except Exception as e:
            print(f"  FAILED: {e}")
            failures.append(site["repo"])
    if failures:
        sys.exit(f"Failed sites: {failures}")
    print("DONE")


if __name__ == "__main__":
    main()
