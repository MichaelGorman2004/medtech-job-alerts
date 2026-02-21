# Progress — medtech-job-alerts

## Status: Built & Tested — Ready to Push

### Completed
- [x] Core script `job_alerts.py` with all features
  - [x] SerpAPI queries with `hl=en` / `gl=us` (English results)
  - [x] Entry-level filtering (exclude senior titles, 3+ YOE)
  - [x] Relevancy scoring + sorting (100+ known medtech companies boosted)
  - [x] Location bucketing (jobs sorted into correct metro by actual location)
  - [x] Deduplication via seen_jobs.json
  - [x] HTML email with purple gradient quote banner, TOP MATCH/GOOD FIT badges
  - [x] Motivational Quote of the Day from 158-quote pool
  - [x] `--dry-run` flag with console summary + HTML preview
  - [x] `.env` loading for local dev
- [x] `config.json` — 5 search terms, 10 secondary metros, Chicago priority
- [x] `quotes.json` — 158 cliche motivational quotes
- [x] `.github/workflows/daily_alerts.yml` — Mon + Thu at 7am CT
- [x] `README.md` with full setup instructions
- [x] `.gitignore` (excludes .env, preview_email.html, __pycache__)
- [x] Dry-run tested successfully (70 jobs, 45 filtered, 25 API queries)

### To Do (You)
- [ ] Push repo to GitHub
- [ ] Create Gmail app password
- [ ] Add 4 secrets: `SERPAPI_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `RECIPIENT_EMAIL`
- [ ] Trigger workflow manually to test real email delivery
- [ ] Tune search terms after first few runs based on Sean's feedback

### Design Decisions
- **Twice a week (Mon + Thu)** instead of daily — hits ALL metros every run (25 queries × ~8 runs/month = 200 of 250 budget)
- Chicago: 5 queries/run (all search terms), secondary metros: 2 queries each
- Entry-level filter: excludes senior/manager/director titles + jobs requiring 3+ YOE
- Relevancy scoring: boosts 100+ known medtech companies, entry-level keywords, penalizes staffing agencies
- Location bucketing: maps job's actual location to correct metro, "Other" catch-all at bottom
- Recipient: Seancarr2022@gmail.com
