# Aria Solutions — funnel site (`ariasolutions.org`)

A single, fast, **static** landing site — no WordPress, no server, no database.
Its whole job is a funnel: **explain the shop → join the Discord → buy via Stripe → read Terms/Privacy.**

## Files
| File | What it is |
|---|---|
| `index.html` | The landing page (hero, plans, individual bots, Scout platform, tip jar, footer). Self-contained — all CSS is inline. Dark/light aware, mobile responsive. |
| `terms.html` | Terms of Service — rendered from `../legal/TERMS_OF_SERVICE.md`. |
| `privacy.html` | Privacy Policy — rendered from `../legal/PRIVACY_POLICY.md`. |

## Status — ready to host
- **Discord invite:** ✅ wired — `https://discord.gg/5xm44GRfmG` (permanent) in all 4 "Join" buttons.
- **Prices/links:** ✅ all 10 Stripe Payment Links + 7 tip links wired from the live shop catalog
  (`sov shop list`). If you change a price/link in Stripe, update it here too.
- **Contact email:** ✅ admin@ariasolutions.org everywhere.

Nothing left to fill in — deploy whenever you're ready (hosting steps below).

## Preview it locally (no hosting needed)
Open the file in any browser:
```bash
xdg-open site/index.html      # Linux
```
All internal links (Terms / Privacy) resolve when the three files sit in the same folder.

## Hosting — pick one (recommended: Cloudflare Pages)

### Option A — Cloudflare Pages (free, HTTPS, fastest) ✅ recommended
1. Create a free Cloudflare account → **Workers & Pages → Create → Pages → Upload assets**.
2. Upload the `site/` folder (or connect the GitHub repo and set the build output dir to `site`).
3. **Custom domains → Set up a custom domain → `ariasolutions.org`.**
4. In **Northwest's DNS** for ariasolutions.org, add the CNAME/records Cloudflare shows you
   (or move the domain's nameservers to Cloudflare — the wizard walks it).
5. Done: `https://ariasolutions.org`, `/terms`, `/privacy` all live over HTTPS.

### Option B — Netlify (also free)
Drag-and-drop the `site/` folder onto app.netlify.com → add the custom domain → point DNS.

### Option C — Northwest's own hosting
If your Northwest plan includes static website hosting, upload `index.html`, `terms.html`, `privacy.html`
there. Zero DNS changes — but confirm it serves plain static HTML (not locked to their WordPress builder).

> **Skip WordPress.** For a one-page funnel it's overkill, needs constant security updates + plugins,
> and is a bigger attack surface than the value it adds.

## After hosting — wire it into Stripe
Paste the public URLs into your Stripe business settings:
- Terms of Service URL → `https://ariasolutions.org/terms`
- Privacy Policy URL → `https://ariasolutions.org/privacy`

## Contact email
Everything — the site, the web legal pages, and the source `../legal/*.md` — uses the business
mailbox **admin@ariasolutions.org** (webmail at https://mail.ariasolutions.org). Consistent across the board.
