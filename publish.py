import os, json, datetime, subprocess, pathlib, anthropic, re

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
GH_TOKEN = os.getenv("GH_TOKEN")
ORG = "shaheenarifch-arch"
MODEL = "claude-haiku-4-5-20251001"

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
    # Remove ```html ... ``` fences Claude sometimes adds
    raw = re.sub(r'^```html\s*', '', raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r'^```\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw.strip())
    # Fix any hardcoded 2024 publish dates if they slip through
    raw = re.sub(r'Published:\s*2024', f'Published: {year_str}', raw)
    raw = re.sub(r'Published:\s*\d{4}', f'Published: {today_str}', raw)
    return raw

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
    # Use token safely - don't print it
    clone_url = f"https://{GH_TOKEN}@github.com/{ORG}/{site}.git"
    subprocess.run(["git","clone", clone_url, workdir], check=False)
    blog_dir = pathlib.Path(workdir) / "blog"
    blog_dir.mkdir(exist_ok=True)

    for kw in kws:
        try:
            prompt = f"""Write a 1200-1500 word SEO HTML article about '{kw}' for the website '{site}'.

Requirements:
- Full standalone HTML document with <html><head><title>...</title></head><body>...</body></html>
- Use <h1> for main title, <h2> and <h3> for sections
- The FIRST line inside <body> must be: Published: {today_str} | {site}
- Do NOT use 2024 or any other year. Use {today_str} exactly.
- Do NOT wrap output in markdown code fences like ```html
- Write for SEO, natural, helpful content
- Category: {kw}
"""
            r2 = client.messages.create(model=MODEL, max_tokens=4000, messages=[{"role":"user","content": prompt}])
            html = clean_html(r2.content[0].text)
        except Exception as e:
            print(f"article error for {kw}: {e}")
            html = f"<html><head><title>{kw}</title></head><body><p>Published: {today_str}</p><h1>{kw}</h1><p>Content for {site} about {kw}.</p></body></html>"

        slug = re.sub(r'[^a-z0-9]+','-', kw.lower()).strip('-')[:50]
        (blog_dir / f"{today_str}-{slug}.html").write_text(html, encoding='utf-8')

    subprocess.run(["git","config","--global","user.email","bot@bot.com"], check=False)
    subprocess.run(["git","config","--global","user.name","Bot"], check=False)
    subprocess.run(["git","add","."], cwd=workdir, check=False)
    subprocess.run(["git","commit","-m", f"blogs {today_str}"], cwd=workdir, check=False)
    subprocess.run(["git","push"], cwd=workdir, check=False)
    print(f"Pushed {site}")

print("DONE")
