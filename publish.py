import os, json, datetime, subprocess, pathlib, anthropic, re
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
GH_TOKEN = os.getenv("GH_TOKEN")
ORG = "shaheenarifch-arch"

with open("sites.json") as f:
    all_sites = json.load(f)

today = datetime.date.today()
day_index = (today - datetime.date(2024,1,1)).days
start = (day_index * 2) % len(all_sites)
todays_sites = [all_sites[start], all_sites[(start+1) % len(all_sites)]]
print(f"TODAY SITES: {todays_sites}")

for site in todays_sites:
    try:
        # 1. Get keywords
        r = client.messages.create(model="claude-3-haiku-20240307", max_tokens=200, messages=[{"role":"user","content":f"Give 3 long-tail SEO keywords for {site} niche, one per line only"}])
        keywords = [l.strip('- ') for l in r.content[0].text.split('\n') if l.strip()][:3]
        print(f"{site} keywords: {keywords}")

        # 2. Clone
        workdir = f"/tmp/{site}"
        subprocess.run(["rm","-rf", workdir], check=False)
        repo_url = f"https://{GH_TOKEN}@github.com/{ORG}/{site}.git"
        subprocess.run(["git","clone", repo_url, workdir], check=True)
        blog_dir = pathlib.Path(workdir) / "blog"
        blog_dir.mkdir(exist_ok=True)

        # 3. Generate 3 articles
        for kw in keywords:
            print(f"Writing {kw}...")
            r2 = client.messages.create(model="claude-3-haiku-20240307", max_tokens=4000, messages=[{"role":"user","content":f"Write 1500 word SEO article about '{kw}' for site {site}. Return full HTML with <title> and <body> with H1 H2."}])
            html = r2.content[0].text
            slug = re.sub(r'[^a-z0-9]+','-', kw.lower()).strip('-')
            (blog_dir / f"{today}-{slug}.html").write_text(html)

        # 4. Push
        subprocess.run(["git","config","--global","user.email","bot@bot.com"], check=False)
        subprocess.run(["git","config","--global","user.name","Bot"], check=False)
        subprocess.run(["git","add","."], cwd=workdir, check=False)
        subprocess.run(["git","commit","-m", f"Add 3 blogs {today}"], cwd=workdir, check=False)
        subprocess.run(["git","push"], cwd=workdir, check=False)
        print(f"DONE {site}")
    except Exception as e:
        print(f"ERROR {site}: {e}")
        continue
print("ALL FINISHED")
