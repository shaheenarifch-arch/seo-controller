import os, json, datetime, subprocess, pathlib, anthropic, re, time

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
GH_TOKEN = os.getenv("GH_TOKEN")
ORG = "shaheenarifch-arch"
SITES_FILE = "sites.json"

if not ANTHROPIC_KEY or not GH_TOKEN:
    print("ERROR: Secrets missing!")
    exit(1)

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# This model works on ALL accounts and is cheapest
MODEL = "claude-3-5-haiku-20241022"

with open(SITES_FILE) as f:
    all_sites = json.load(f)

# Clean list (remove duplicates, empty)
all_sites = list(dict.fromkeys([s.strip() for s in all_sites if s.strip()]))

today = datetime.date.today()
day_index = (today - datetime.date(2024,1,1)).days
start = (day_index * 2) % len(all_sites)
todays_sites = [all_sites[start], all_sites[(start+1) % len(all_sites)]]

print(f"Date: {today} | Total sites: {len(all_sites)} | Today: {todays_sites}")

def generate_keywords(site_name):
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[{"role":"user","content": f"Give 3 SEO long-tail keywords for website niche: {site_name}. Only 3 lines, one keyword per line, no numbers or bullets."}]
        )
        kws = [l.strip('-.0123456789').strip() for l in resp.content[0].text.split('\n') if len(l.strip())>3]
        return kws[:3] if len(kws)>=2 else [f"{site_name} guide", f"best {site_name}", f"{site_name} tips"]
    except Exception as e:
        print(f"Keyword error for {site_name}: {e}")
        return [f"{site_name} guide", f"best {site_name}", f"{site_name} tips 2026"]

def generate_article(site_name, keyword):
    prompt = f"""You are an SEO blog writer. Write a full 2000-word HTML article.

Website niche: {site_name}
Target keyword: {keyword}

OUTPUT RULES:
- Output ONLY complete HTML document, starting with <!DOCTYPE html>
- Include <title> with keyword, <meta name="description" content="... 155 chars">
- Body: <h1> with keyword, then intro 150 words with keyword in first 100 words
- Then 4-5 H2 sections, each 350+ words, with H3 where needed
- 2000 words total minimum
- FAQ section at end with 4 questions using keyword
- Add JSON-LD FAQ schema script tag
- No markdown, only HTML
- Add footer link <a href="/blog/">More Articles</a>
"""
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            messages=[{"role":"user","content": prompt}]
        )
        html = resp.content[0].text
        # Ensure HTML
        if "<!DOCTYPE" not in html and "<html" not in html:
            html = f"<!DOCTYPE html><html><head><title>{keyword}</title></head><body><h1>{keyword}</h1>{html}</body></html>"
        return html
    except Exception as e:
        print(f"Article error {keyword}: {e}")
        return f"<!DOCTYPE html><html><head><title>{keyword}</title></head><body><h1>{keyword}</h1><p>Article for {site_name} about {keyword}. Coming soon with 2000 words content about {keyword} in {site_name} niche.</p></body></html>"

for site in todays_sites:
    print(f"\n=== {site} ===")
    # Fix case sensitivity - use exact name from your list
    site = site.strip()
    if not site:
        continue

    keywords = generate_keywords(site)
    print(f"Keywords: {keywords}")

    workdir = f"/tmp/{site}"
    subprocess.run(["rm","-rf", workdir], check=False)

    repo_url = f"https://{GH_TOKEN}@github.com/{ORG}/{site}.git"
    print(f"Cloning {repo_url.replace(GH_TOKEN, '***')}")
    result = subprocess.run(["git","clone", repo_url, workdir], capture_output=True, text=True)

    if result.returncode!= 0:
        print(f"Clone failed for {site}: {result.stderr}")
        # Try lower case version
        site_lower = site.lower()
        repo_url2 = f"https://{GH_TOKEN}@github.com/{ORG}/{site_lower}.git"
        subprocess.run(["git","clone", repo_url2, workdir], check=False)

    blog_dir = pathlib.Path(workdir) / "blog"
    blog_dir.mkdir(exist_ok=True)

    # Create index if not exists
    index_file = blog_dir / "index.html"
    if not index_file.exists():
        index_file.write_text(f"<!DOCTYPE html><html><head><title>{site} Blog</title></head><body><h1>{site} Blog</h1><ul id='posts'></ul></body></html>")

    for kw in keywords:
        slug = re.sub(r'[^a-z0-9]+','-', kw.lower()).strip('-')[:60]
        filename = f"{today}-{slug}.html"
        print(f"Generating {filename}...")
        html = generate_article(site, kw)
        (blog_dir / filename).write_text(html, encoding='utf-8')
        time.sleep(2) # Avoid rate limit

    # Git push
    subprocess.run(["git","config","--global","user.email","bot@seo-controller.com"], check=False)
    subprocess.run(["git","config","--global","user.name","SEO Bot"], check=False)
    subprocess.run(["git","add","."], cwd=workdir, check=False)
    subprocess.run(["git","commit","-m", f"SEO: add 3 articles {today} for {site}"], cwd=workdir, check=False)
    push = subprocess.run(["git","push"], cwd=workdir, capture_output=True, text=True)
    print(f"Push result for {site}: {push.returncode} {push.stdout} {push.stderr}")

print("\n=== ALL DONE ===")
