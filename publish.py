import os, json, datetime, subprocess, pathlib, anthropic, re

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
GH_TOKEN = os.getenv("GH_TOKEN")
ORG = "shaheenarifch-arch"
SITES_FILE = "sites.json"

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

with open(SITES_FILE) as f:
    all_sites = json.load(f)

today = datetime.date.today()
day_index = (today - datetime.date(2024,1,1)).days
start = (day_index * 2) % len(all_sites)
todays_sites = [all_sites[start], all_sites[(start+1) % len(all_sites)]]

print(f"Today {today} -> {todays_sites}")

def generate_keywords(site_name):
    prompt = f"Give me 3 SEO long-tail keywords for niche: {site_name}. Return only 3 lines, one per line."
    resp = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=200,
        messages=[{"role":"user","content":prompt}]
    )
    kws = [l.strip('- ').strip() for l in resp.content[0].text.split('\n') if l.strip()]
    return kws[:3]

def generate_article(site_name, keyword):
    prompt = f"""Write a 2000-word SEO HTML article for Website: {site_name} Keyword: {keyword}. Return ONLY valid HTML with <title>, meta description, H1 H2 H3, 2000 words, FAQ section with JSON-LD."""
    resp = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=8000,
        messages=[{"role":"user","content":prompt}]
    )
    return resp.content[0].text

for site in todays_sites:
    print(f"--- {site} ---")
    keywords = generate_keywords(site)
    print(f"Keywords: {keywords}")
    repo_url = f"https://{GH_TOKEN}@github.com/{ORG}/{site}.git"
    workdir = f"/tmp/{site}"
    subprocess.run(["rm","-rf", workdir], check=False)
    subprocess.run(["git","clone", repo_url, workdir])
    blog_dir = pathlib.Path(workdir) / "blog"
    blog_dir.mkdir(exist_ok=True)
    for kw in keywords:
        slug = re.sub(r'[^a-z0-9]+','-', kw.lower()).strip('-')
        filename = f"{today}-{slug}.html"
        html = generate_article(site, kw)
        (blog_dir / filename).write_text(html, encoding='utf-8')
    subprocess.run(["git","config","--global","user.email","bot@seo.com"], check=False)
    subprocess.run(["git","config","--global","user.name","SEO Bot"], check=False)
    subprocess.run(["git","add","."], cwd=workdir, check=False)
    subprocess.run(["git","commit","-m", f"SEO: 3 articles for {today}"], cwd=workdir, check=False)
    subprocess.run(["git","push"], cwd=workdir)
print("Done!")
