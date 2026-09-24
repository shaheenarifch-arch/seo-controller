import os, json, datetime, subprocess, pathlib, anthropic, re

# Config
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
GH_TOKEN = os.getenv("GH_TOKEN")
ORG = "shaheenarifch-arch"
SITES_FILE = "sites.json"

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# Load alphabetical list
with open(SITES_FILE) as f:
    all_sites = json.load(f)

# Rotation: 2 sites per day
today = datetime.date.today()
day_index = (today - datetime.date(2024,1,1)).days
start = (day_index * 2) % len(all_sites)
todays_sites = [all_sites[start], all_sites[(start+1) % len(all_sites)]]

print(f"Today {today} -> Publishing for: {todays_sites}")

def generate_keywords(site_name):
    prompt = f"Give me 3 SEO long-tail keywords for website niche: {site_name}. Return only 3 lines, one keyword per line, no numbers."
    resp = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=200,
        messages=[{"role":"user","content":prompt}]
    )
    kws = [l.strip('- ').strip() for l in resp.content[0].text.split('\n') if l.strip()]
    return kws[:3]

def generate_article(site_name, keyword):
    prompt = f"""Write a 2000-word SEO-optimized HTML article.

Website: {site_name}
Keyword: {keyword}

Requirements:
- Return ONLY valid HTML: <html><head><title>...</title><meta name='description'...></head><body>...<article>...
- Title must include keyword
- Use H1 for title, H2 and H3 for sections
- 2000 words minimum, human style, no AI mention
- Add intro with keyword in first 100 words
- Add FAQ section with 4 questions
- Add FAQ schema JSON-LD at bottom
- Internal link placeholder: <a href="/blog/">More articles</a>
"""
    resp = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=4096,
        messages=[{"role":"user","content":prompt}]
    )
    return resp.content[0].text

for site in todays_sites:
    print(f"\n--- Processing {site} ---")
    keywords = generate_keywords(site)
    print(f"Keywords: {keywords}")

    # Clone repo
    repo_url = f"https://{GH_TOKEN}@github.com/{ORG}/{site}.git"
    workdir = f"/tmp/{site}"
    subprocess.run(["rm","-rf", workdir], check=False)
    clone = subprocess.run(["git","clone", repo_url, workdir])
    if clone.returncode!= 0:
        print(f"Failed to clone {site}, maybe repo name case sensitive. Trying lowercase...")
        repo_url = f"https://{GH_TOKEN}@github.com/{ORG}/{site.lower()}.git"
        subprocess.run(["git","clone", repo_url, workdir])

    blog_dir = pathlib.Path(workdir) / "blog"
    blog_dir.mkdir(exist_ok=True)

    for kw in keywords:
        slug = re.sub(r'[^a-z0-9]+','-', kw.lower()).strip('-')
        filename = f"{today}-{slug}.html"
        html_content = generate_article(site, kw)

        (blog_dir / filename).write_text(html_content, encoding='utf-8')
        print(f"Created {filename} ({len(html_content)} chars)")

    # Commit & push
    subprocess.run(["git","config","--global","user.email","bot@seo-controller.com"], check=False)
    subprocess.run(["git","config","--global","user.name","SEO Bot"], check=False)
    subprocess.run(["git","add","."], cwd=workdir, check=False)
    subprocess.run(["git","commit","-m", f"SEO: add 3 articles for {today} - {site}"], cwd=workdir, check=False)
    push = subprocess.run(["git","push"], cwd=workdir)
    print(f"Pushed {site}: {push.returncode}")

print("\nAll done!")
