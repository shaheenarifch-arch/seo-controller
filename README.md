# Affiliate data (Awin accounts 3067297 + 3075433)

This folder is the master database of every Awin merchant you're joined to, which of your websites promotes it, and its affiliate links. The daily blog bot (`blog_bot.py`) reads its links from `blog-deeplinks.json` here.

| File | What it is | Edit it? |
|---|---|---|
| `merchants.csv` | One row per merchant: ID, brand, website, category, accounts, stats | Yes, but only `primary_account`, `notes`, `status` |
| `sites.csv` | Your websites and the merchant IDs each one promotes (`advertiser_ids`, space-separated) | Yes |
| `affiliate-links.csv` | Every seller's affiliate link, HTML snippet, deep-link prefix, logo, Awin profile | No, it's generated |
| `pages.csv` | Each merchant's important pages: top products, best sellers, new arrivals, deals. Found automatically every day and checked to open; add your own rows with `source` = `manual` (they're always kept and used first) | Add manual rows |
| `creatives.csv` | Every vendor's creatives: Awin logo (automatic) + banners/text links you add (just `advertiser_id`, `creative_type`, `size`, `creative_id`, `group_id`) | Add rows; links fill in automatically |
| `blog-deeplinks.json` | Per-site merchant links for the blog bot | No, it's generated |
| `update_portfolio.py` | Rebuilds the generated files and syncs with Awin | |

## How it stays up to date
`.github/workflows/update-affiliate-data.yml` runs **every day at 5:45 AM New York**, just before the 6:00 AM blog run, whenever you edit `merchants.csv` or `sites.csv`, and on demand from **Actions → Update affiliate data → Run workflow**.

If the repo secret `AWIN_API_TOKEN` is set (you already use it for the blog bot), each run asks Awin for the programmes you're joined to on **both** accounts:
- new merchants are added automatically
- merchants you're no longer joined to are marked `status=left` and dropped from blog links
- your `primary_account` and `notes` are never overwritten

## Important pages
For every merchant used on a site, the daily job reads the store (Shopify-style stores: collections + best-selling products; other stores: menu links) and keeps up to 3 top products plus best-sellers / new / deals pages. If a store can't be read one day, yesterday's pages are kept. The blog bot links each merchant to 2 top products + 1 best-sellers page (change with `PAGES_PER_MERCHANT`).

## Deep links
`https://www.awin1.com/cread.php?awinmid={advertiser_id}&awinaffid={account}&ued={URL-encoded page}`

## Live copies
- Google Sheet: `=IMPORTDATA("https://raw.githubusercontent.com/shaheenarifch-arch/seo-controller/main/affiliate-data/affiliate-links.csv")`
- Creatives in Google Sheets: `=IMPORTDATA("https://raw.githubusercontent.com/shaheenarifch-arch/seo-controller/main/affiliate-data/creatives.csv")`
- Important pages in Google Sheets: `=IMPORTDATA("https://raw.githubusercontent.com/shaheenarifch-arch/seo-controller/main/affiliate-data/pages.csv")`
- Excel: Data → From Web → the same raw URL, then Refresh.
