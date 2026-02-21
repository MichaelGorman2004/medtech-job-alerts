# medtech-job-alerts

## Project Overview
Daily job alert system that scrapes Google Jobs via SerpAPI, deduplicates results, and emails a formatted digest to a single recipient via Gmail SMTP. Runs on GitHub Actions cron (7:00 AM CT / 13:00 UTC).

## Architecture
- **Scheduler:** GitHub Actions with daily cron + manual `workflow_dispatch`
- **Data Source:** SerpAPI Google Jobs Results API (`/search?engine=google_jobs`)
- **Email:** Gmail SMTP with app password
- **Dedup:** JSON file committed to repo tracking seen job IDs

## Repo Structure
```
medtech-job-alerts/
├── job_alerts.py          # Core script: API queries, dedup, email
├── config.json            # Search terms + target metros (user-editable)
├── seen_jobs.json         # Dedup tracking (auto-managed, committed by GHA)
├── .github/
│   └── workflows/
│       └── daily_alerts.yml
├── requirements.txt
├── README.md
└── CLAUDE.md
```

## Key Constraints
- SerpAPI free tier: 100 searches/month → ~10-15 queries per daily run
- Chicago is the priority market (listed first in email, most query coverage)
- Secondary metros: Cleveland, Greenville SC, Columbus OH, NYC, Dallas, Austin, Houston, Florida, Boston, Philadelphia
- Email is clean HTML, scannable format
- No email sent if zero new jobs found

## Secrets (GitHub Actions)
- `SERPAPI_KEY`
- `GMAIL_ADDRESS`
- `GMAIL_APP_PASSWORD`
- `RECIPIENT_EMAIL`

## Development Commands
```bash
# Run locally (requires env vars or .env)
python job_alerts.py

# Run with dry-run (no email sent)
python job_alerts.py --dry-run
```

## Style & Conventions
- Python 3.11+
- Keep it simple — this is a ~200 line script, not a framework
- Logging to stdout for GHA visibility
- Config changes (search terms, metros) go in config.json, not code
