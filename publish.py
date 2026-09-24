import os, json, datetime, subprocess, pathlib, anthropic, re

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
GH_TOKEN = os.getenv("GH_TOKEN")
ORG = "shaheenarifch-arch"
MODEL = "claude-3-5-haiku-20241022"  # FIXED: was claude-haiku-4-5-20251001 which doesn't exist

with open("sites.json") as f:
    all_sites = json.load(f)

today = datetime.date.today()
today_str = today.isoformat()  # e.g. 2026-09-24
year_str = today.strftime("%Y")

day_index = (today - datetime.date(2024,1,1)).days
start = (day_index * 2) % len(all_sites)
todays_sites = [all_sites[start], all_sites[(start+1) % len(all_sites)]]
print(f"TODAY: {todays_sites}")

def clean_html(raw: str) -> str:
    """Strip markdown fences and fix old year hardcode."""
    raw = raw.strip()
    # Handle full ```html block```
    m = re.search(r'```(?:html)?\s*(.*?)```', raw, re.DOTALL | re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
    # Fix any hardcoded 2024 publish dates
    raw = re.sub(r'Published:\s*2024', f'Published: {year_str}', raw)
    raw = re.sub(r'Published:\s*\d{4}\b', f'Published: {today_str}', raw, count=1)
    return raw

def ensure_cta(html: str, kw: str, site: str) -> str:
    """Inject CTA if Claude forgot to add one."""
    if '/contact' not in html.lower() and 'cta' not in html.lower():
        cta_block = f'''
<div style="margin:40px 0;padding:30px;background:#f8f9fa;border-radius:10px;text-align:center;border:1px solid #e9ecef">
  <h3 style="margin-top:0">Looking for {kw}?</h3>
  <p>At {site}, we offer top-quality products, fast shipping, and expert support.</p>
  <a href="/contact" style="display:inline-block;padding:14px 28px;background:#007bff;color:#fff;text-decoration:none;border-radius:6px;font-weight:bold;margin:10px">Get a Free Quote</a>
  <a href="/shop" style="display:inline-block;padding:14px 28px;background:#28a745;color:#fff;text-decoration:none;border-radius:6px;font-weight:bold;margin:10px">Shop Now</a>
</div>
'''
        # Insert before </body>
        if '</body>' in html:
            html = html.replace('</body>', f'{cta_block}</body>')
        else:
            html += cta_block
    return html

for site in todays_sites:
    print(f"--- {site} ---")
    try:
        r = client.messages.create(
            model=MODEL, 
            max_tokens=300, 
            messages=[{"role":"user","content": f"Give 3 SEO keywords for niche '{site}'. Just the keywords, one per line, no numbers or bullets."}]
        )
        kws = [re.sub(r'^[\-\*\d\.\s]+', '', l).strip() for l in r.content[0].text.split('\n') if len(l.strip())>2][:3]
    except Exception as e:
        kws = [f"{site} guide", f"best {site}", f"{site} tips"]
        print(f"kw error {e}")

    print(f"kws: {kws}")
    workdir = f"/tmp/{site}"
    subprocess.run(["rm","-rf", workdir], check=False)
    clone_url = f"https://{GH_TOKEN}@github.com/{ORG}/{site}.git"
    subprocess.run(["git","clone", clone_url, workdir], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    blog_dir = pathlib.Path(workdir) / "blog"
    blog_dir.mkdir(exist_ok=True)

    if not pathlib.Path(workdir).exists() or not blog_dir.exists():
        print(f"Clone failed for {site}, skipping")
        continue

    for kw in kws:
        try:
            prompt = f"""Write a 1200-1500 word SEO HTML article about '{kw}' for the website '{site}'.

Requirements:
- Full standalone HTML document with <html><head><title>...</title><meta name="description" content="..."></head><body>...</body></html>
- Use <h1> for main title, <h2> and <h3> for sections
- The FIRST line inside <body> must be: Published: {today_str} | {site}
- Do NOT use 2024 or any other year. Use {today_str} exactly.
- Do NOT wrap output in markdown code fences like ```html
- Include 2-3 natural CTAs with links:
  1. After intro paragraph: <a href="/contact" class="cta">Get a Free Quote for {kw}</a>
  2. Mid-article: <a href="/shop">Shop {site} Products</a>
  3. End: Final CTA box encouraging contact
- CTAs must use keyword '{kw}' naturally
- Links must be: /contact, /shop, /products, or /blog
- Write for SEO, natural, helpful content that converts
- Category: {kw}
"""
            r2 = client.messages.create(model=MODEL, max_tokens=4000, messages=[{"role":"user","content": prompt}])
            html = clean_html(r2.content[0].text)
            html = ensure_cta(html, kw, site)
        except Exception as e:
            print(f"article error for {kw}: {e}")
            html = f"""<html><head><title>{kw}</title></head><body>
<p>Published: {today_str} | {site}</p>
<h1>{kw}</h1>
<p>Content for {site} about {kw}.</p>
<div style="margin:40px 0;padding:30px;background:#f8f9fa;border-radius:10px;text-align:center">
  <h3>Looking for {kw}?</h3>
  <a href="/contact" style="padding:14px 28px;background:#007bff;color:#fff;text-decoration:none;border-radius:6px;font-weight:bold">Get a Free Quote</a>
</div>
</body></html>"""

        slug = re.sub(r'[^a-z0-9]+','-', kw.lower()).strip('-')[:50]
        (blog_dir / f"{today_str}-{slug}.html").write_text(html, encoding='utf-8')

    subprocess.run(["git","config","--global","user.email","bot@bot.com"], check=False)
    subprocess.run(["git","config","--global","user.name","Bot"], check=False)
    subprocess.run(["git","add","."], cwd=workdir, check=False)
    subprocess.run(["git","commit","-m", f"blogs {today_str}"], cwd=workdir, check=False)
    subprocess.run(["git","push"], cwd=workdir, check=False)
    print(f"Pushed {site}")

print("DONE")
