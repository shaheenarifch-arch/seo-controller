import os, json, datetime, subprocess, pathlib, anthropic, re
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
GH_TOKEN = os.getenv("GH_TOKEN")
ORG = "shaheenarifch-arch"
MODEL = "claude-3-5-haiku-latest"

with open("sites.json") as f:
    all_sites = json.load(f)

today = datetime.date.today()
day_index = (today - datetime.date(2024,1,1)).days
start = (day_index * 2) % len(all_sites)
todays_sites = [all_sites[start], all_sites[(start+1) % len(all_sites)]]
print(f"TODAY: {todays_sites}")

for site in todays_sites:
    print(f"--- {site} ---")
    try:
        r = client.messages.create(model=MODEL, max_tokens=200, messages=[{"role":"user","content": f"Give 3 SEO keywords for niche {site}, one per line"}])
        kws = [l.strip('-.123') for l in r.content[0].text.split('\n') if len(l.strip())>2][:3]
    except Exception as e:
        kws = [f"{site} guide", f"best {site}", f"{site} tips"]
        print(f"kw error {e}")

    print(f"kws: {kws}")
    workdir = f"/tmp/{site}"
    subprocess.run(["rm","-rf", workdir], check=False)
    subprocess.run(["git","clone", f"https://{GH_TOKEN}@github.com/{ORG}/{site}.git", workdir], check=False)
    blog_dir = pathlib.Path(workdir) / "blog"
    blog_dir.mkdir(exist_ok=True)

    for kw in kws:
        try:
            r2 = client.messages.create(model=MODEL, max_tokens=4000, messages=[{"role":"user","content": f"Write 1500 word SEO HTML article about '{kw}' for {site}. Full HTML with title and H1 H2."}])
            html = r2.content[0].text
        except Exception as e:
            html = f"<html><head><title>{kw}</title></head><body><h1>{kw}</h1><p>Content for {site}</p></body></html>"
        slug = re.sub(r'[^a-z0-9]+','-', kw.lower()).strip('-')[:50]
        (blog_dir / f"{today}-{slug}.html").write_text(html, encoding='utf-8')

    subprocess.run(["git","config","--global","user.email","bot@bot.com"], check=False)
    subprocess.run(["git","config","--global","user.name","Bot"], check=False)
    subprocess.run(["git","add","."], cwd=workdir, check=False)
    subprocess.run(["git","commit","-m", f"blogs {today}"], cwd=workdir, check=False)
    subprocess.run(["git","push"], cwd=workdir, check=False)
    print(f"Pushed {site}")
print("DONE")
