# medtech-job-alerts

Daily email digest of medical device sales job listings, powered by GitHub Actions and SerpAPI.

Queries Google Jobs (which aggregates Indeed, ZipRecruiter, Glassdoor, and company career pages), deduplicates results, and sends a clean HTML email every morning at 7:00 AM CT.

## Setup

### 1. Get a SerpAPI Key

1. Sign up at [serpapi.com](https://serpapi.com/)
2. Free tier gives you 100 searches/month — plenty for this project
3. Copy your API key from the dashboard

### 2. Create a Gmail App Password

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. You need 2-Factor Authentication enabled on the Gmail account
3. Generate an app password for "Mail"
4. Copy the 16-character password (no spaces)

### 3. Configure GitHub Actions Secrets

In your repo, go to **Settings → Secrets and variables → Actions** and add:

| Secret | Description |
|--------|-------------|
| `SERPAPI_KEY` | Your SerpAPI API key |
| `GMAIL_ADDRESS` | Gmail address to send from |
| `GMAIL_APP_PASSWORD` | The 16-char app password from step 2 |
| `RECIPIENT_EMAIL` | Email address to send the digest to |

### 4. Customize Search Config

Edit `config.json` to adjust:
- **search_terms** — job title variations to search for
- **priority_metro** — main city (gets the most daily queries)
- **secondary_metros** — other cities to rotate through
- **max_results_per_query** — results per API call
- **days_lookback** — how recent listings should be

### 5. Test It

Trigger the workflow manually: go to **Actions → Daily Job Alerts → Run workflow**.

Or run locally:
```bash
pip install -r requirements.txt
SERPAPI_KEY=your_key GMAIL_ADDRESS=you@gmail.com GMAIL_APP_PASSWORD=xxxx python job_alerts.py --dry-run
```

## How It Works

- **Daily at 7:00 AM CT**, GitHub Actions runs `job_alerts.py`
- Queries SerpAPI Google Jobs for each search term × metro combination
- Chicago gets 3 queries/day (priority); secondary metros rotate (2/day)
- New jobs are compared against `seen_jobs.json` to avoid duplicates
- A formatted HTML email is sent with Chicago listings first, then other cities alphabetically
- `seen_jobs.json` is committed back to the repo to persist dedup state

## Project Structure

```
├── job_alerts.py           # Core script
├── config.json             # Search terms & metros (edit this)
├── seen_jobs.json          # Dedup tracking (auto-managed)
├── .github/workflows/
│   └── daily_alerts.yml    # GitHub Actions cron workflow
├── requirements.txt
└── README.md
```
