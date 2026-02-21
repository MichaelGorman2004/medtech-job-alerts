#!/usr/bin/env python3
"""Daily med-tech job alert system. Queries SerpAPI Google Jobs, deduplicates, and emails a digest."""

import argparse
import datetime
import hashlib
import json
import logging
import os
import random
import re
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = REPO_ROOT / "config.json"
SEEN_JOBS_PATH = REPO_ROOT / "seen_jobs.json"
QUOTES_PATH = REPO_ROOT / "quotes.json"
ENV_PATH = REPO_ROOT / ".env"


def load_dotenv():
    """Load .env file into os.environ if it exists (for local dev)."""
    if not ENV_PATH.exists():
        return
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_daily_quote():
    """Pick a random motivational quote for the day."""
    with open(QUOTES_PATH) as f:
        data = json.load(f)
    return random.choice(data["quotes"])


def load_seen_jobs():
    if SEEN_JOBS_PATH.exists():
        with open(SEEN_JOBS_PATH) as f:
            return json.load(f)
    return {"seen_ids": [], "last_run": None}


def save_seen_jobs(data):
    data["last_run"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(SEEN_JOBS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def make_job_id(job):
    """Create a stable ID from job title + company + location."""
    raw = f"{job.get('title', '')}-{job.get('company_name', '')}-{job.get('location', '')}".lower()
    return hashlib.md5(raw.encode()).hexdigest()


# ── Entry-level filtering ──────────────────────────────────────────

EXCLUDE_TITLE_KEYWORDS = [
    "senior", "sr.", "sr ", "director", "vp ", "vice president", "principal",
    "manager", "lead", "head of", "chief", "executive", "staff",
]

REQUIRE_TITLE_KEYWORDS = [
    "sales", "clinical", "account", "representative", "rep",
    "medical", "surgical", "med ", "associate", "device",
]

# Matches patterns like "3+ years", "4 years", "3-5 years" etc.
YOE_PATTERN = re.compile(r"(\d+)\+?\s*(?:-\s*\d+\s*)?years?", re.IGNORECASE)
MAX_YOE = 2  # Exclude jobs requiring more than this


def is_entry_level_relevant(job):
    """Filter out senior roles, non-sales noise, and 3+ YOE requirements."""
    title = job.get("title", "").lower()
    description = job.get("description", "").lower()

    # Exclude senior titles
    for kw in EXCLUDE_TITLE_KEYWORDS:
        if kw in title:
            log.debug(f"  Filtered out (senior title): {job.get('title')}")
            return False

    # Must be sales/clinical related
    if not any(kw in title for kw in REQUIRE_TITLE_KEYWORDS):
        log.debug(f"  Filtered out (not relevant): {job.get('title')}")
        return False

    # Check description for YOE requirements > 2
    for match in YOE_PATTERN.finditer(description):
        years = int(match.group(1))
        if years > MAX_YOE:
            log.debug(f"  Filtered out ({years}+ YOE): {job.get('title')}")
            return False

    return True


# ── Relevancy scoring ──────────────────────────────────────────────

# Higher score = more relevant to entry-level med device sales
HIGH_RELEVANCE_KEYWORDS = [
    "associate", "entry level", "entry-level", "junior", "trainee",
    "medical device", "med device", "surgical", "clinical sales",
    "orthopedic", "orthopaedic", "endoscopy", "cardiovascular",
    "spine", "trauma", "implant",
]

MED_RELEVANCE_KEYWORDS = [
    "medical sales", "clinical", "healthcare sales", "hospital",
    "territory", "field sales",
]


def relevancy_score(job):
    """Score a job 0-100 for relevancy. Higher = better match."""
    title = job.get("title", "").lower()
    company = job.get("company_name", "").lower()
    description = job.get("description", "").lower()
    text = f"{title} {company} {description}"

    score = 50  # baseline

    for kw in HIGH_RELEVANCE_KEYWORDS:
        if kw in text:
            score += 10
    for kw in MED_RELEVANCE_KEYWORDS:
        if kw in text:
            score += 5

    # Boost for "associate" or "entry" in title specifically
    if "associate" in title or "entry" in title or "junior" in title:
        score += 15

    # Penalize if it smells like a staffing/recruiting farm
    if any(x in company for x in ["staffing", "recruiting", "placement"]):
        score -= 10

    # Boost well-known med device / medtech / medical companies
    known_companies = [
        # Big medtech / diversified
        "stryker", "medtronic", "johnson & johnson", "j&j", "johnson johnson",
        "abbott", "baxter", "becton dickinson", "bd ", "boston scientific",
        "ge healthcare", "siemens healthineers", "philips", "cardinal health",
        "edwards lifesciences", "danaher", "hologic",
        # Orthopedics / spine / trauma
        "arthrex", "zimmer biomet", "zimmer", "smith+nephew", "smith & nephew",
        "depuy", "synthes", "depuy synthes", "nuvasive", "globus medical",
        "alphatec", "orthofix", "wright medical", "exactech", "anika",
        "conformis", "medacta", "paragon 28", "treace",
        # Surgical / robotics
        "intuitive", "intuitive surgical", "mako", "mazor",
        "think surgical", "vicarious surgical",
        # Cardiovascular / interventional
        "edwards", "abiomed", "shockwave", "penumbra", "silk road medical",
        "teleflex", "merit medical", "cordis", "spectranetics", "aortica",
        "atricure", "cardiovascular systems", "inari medical",
        # Endoscopy / visualization
        "ambu", "karl storz", "olympus", "conmed", "artivion",
        "applied medical", "richard wolf",
        # Neuro / cranial
        "natus medical", "integra lifesciences", "integra", "nevro",
        "axonics", "nuvectra", "bioventus",
        # Wound care / tissue
        "acelity", "kinetic concepts", "solventum", "3m health",
        "mimedx", "organogenesis", "polynovo", "derma sciences",
        # Dental / ENT
        "align technology", "dentsply sirona", "dentsply", "envista",
        "straumann", "henry schein", "patterson",
        # Diabetes / monitoring
        "dexcom", "insulet", "tandem diabetes", "senseonics",
        "medela", "masimo",
        # Diagnostics / imaging
        "hologic", "exact sciences", "caris life sciences",
        "guardant health", "natera", "veracyte",
        # General med / surgical supply
        "medline", "owens & minor", "molnlycke", "halyard",
        "teleflex", "icad", "merit medical", "haemonetics",
        # Ophthalmology
        "alcon", "bausch", "cooper surgical", "coopersurgical",
        "johnson vision", "amo ",
        # Contract / specialized
        "tela bio", "cirtec medical", "integer holdings",
        "natus", "cantel medical", "steris", "getinge",
        # Other notable
        "resmed", "hill-rom", "hillrom", "livanova", "bioatla",
        "procept biorobotics", "transmedics", "inspire medical",
        "acutus medical", "zynex medical", "surmodics",
        "cardiovascular systems", "repligen",
    ]
    for co in known_companies:
        if co in company:
            score += 15
            break

    return min(score, 100)


def sort_by_relevancy(jobs):
    """Sort jobs by relevancy score, highest first."""
    return sorted(jobs, key=relevancy_score, reverse=True)


# ── SerpAPI ────────────────────────────────────────────────────────

def query_serpapi(term, location, api_key, max_results=10):
    """Query SerpAPI Google Jobs and return a list of job dicts."""
    params = {
        "engine": "google_jobs",
        "q": term,
        "location": location,
        "api_key": api_key,
        "num": max_results,
        "hl": "en",       # Force English results
        "gl": "us",       # Force US geo
    }
    log.info(f"Querying: '{term}' in {location}")
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        jobs = data.get("jobs_results", [])
        log.info(f"  -> {len(jobs)} results")
        return jobs
    except requests.RequestException as e:
        log.error(f"  -> API error: {e}")
        return []


# ── Query strategy ─────────────────────────────────────────────────

def pick_search_terms(config, count):
    """Rotate through search terms based on the day."""
    terms = config["search_terms"]
    day = datetime.datetime.now(datetime.timezone.utc).timetuple().tm_yday
    start = day % len(terms)
    picked = []
    for i in range(count):
        picked.append(terms[(start + i) % len(terms)])
    return picked


# Map job locations back to the correct metro bucket.
# Order matters — more specific aliases checked first via the matching logic.
METRO_ALIASES = {
    "Chicago, IL": ["chicago", "naperville", "oak park", "evanston", "schaumburg",
                     "oak lawn", "elmhurst", "joliet", "aurora, il", "lincolnshire, il"],
    "Cleveland, OH": ["cleveland", "akron, oh", "akron, ohio"],
    "Columbus, OH": ["columbus, oh", "columbus, ohio"],
    "Greenville, SC": ["greenville, sc", "spartanburg, sc"],
    "New York, NY": ["new york", "nyc", "manhattan", "brooklyn", "queens",
                      "long island", "newark, nj", "jersey city", "new hyde park"],
    "Dallas, TX": ["dallas", "fort worth", "dfw", "plano, tx", "irving, tx", "arlington, tx"],
    "Austin, TX": ["austin, tx", "austin, texas", "round rock, tx", "san marcos, tx"],
    "Houston, TX": ["houston", "sugar land", "the woodlands", "katy, tx"],
    "Florida": ["florida", "miami", "orlando", "tampa", "jacksonville, fl",
                "fort lauderdale", "tallahassee", "gainesville, fl", "ocala, fl",
                "st. petersburg", "sarasota"],
    "Boston, MA": ["boston", "cambridge, ma", "worcester, ma"],
    "Philadelphia, PA": ["philadelphia", "philly", "harrisburg, pa", "pittsburgh",
                          "allentown, pa", "king of prussia"],
}


def bucket_job_to_metro(job, queried_metro):
    """Determine which metro a job actually belongs to based on its location field."""
    location = job.get("location", "").lower()

    # Check if it matches the metro we queried for
    if queried_metro in METRO_ALIASES:
        for alias in METRO_ALIASES[queried_metro]:
            if alias in location:
                return queried_metro

    # Check all other metros in case it's a better fit
    for metro, aliases in METRO_ALIASES.items():
        for alias in aliases:
            if alias in location:
                return metro

    # If "anywhere" or "remote" or "united states", bucket under queried metro
    if any(x in location for x in ["remote", "anywhere", "united states"]):
        return queried_metro

    # Doesn't match any known metro — put in "Other"
    return "Other"


def collect_jobs(config, api_key):
    """Run all queries and return {metro: [job, ...]} with dedup, filtering, and correct bucketing."""
    seen = load_seen_jobs()
    seen_ids = set(seen["seen_ids"])
    all_new_jobs = {}  # metro -> list of jobs
    filtered_count = 0

    def process_job(job, queried_metro):
        nonlocal filtered_count
        jid = make_job_id(job)
        if jid in seen_ids:
            return
        seen_ids.add(jid)
        if not is_entry_level_relevant(job):
            filtered_count += 1
            return
        actual_metro = bucket_job_to_metro(job, queried_metro)
        all_new_jobs.setdefault(actual_metro, []).append(job)

    # Priority metro: Chicago gets all search terms
    priority = config["priority_metro"]
    priority_terms = pick_search_terms(config, priority["queries_per_run"])
    for term in priority_terms:
        for job in query_serpapi(term, priority["name"], api_key, config["max_results_per_query"]):
            process_job(job, priority["name"])

    # Secondary metros: ALL of them, with rotated search terms
    terms_per_metro = config.get("secondary_terms_per_metro", 2)
    for metro in config["secondary_metros"]:
        metro_terms = pick_search_terms(config, terms_per_metro)
        for term in metro_terms:
            for job in query_serpapi(term, metro, api_key, config["max_results_per_query"]):
                process_job(job, metro)

    total_queries = priority["queries_per_run"] + len(config["secondary_metros"]) * terms_per_metro
    log.info(f"Used {total_queries} API queries this run")
    log.info(f"Filtered out {filtered_count} jobs (senior/irrelevant/high YOE)")

    # Sort each metro's jobs by relevancy
    for metro in all_new_jobs:
        all_new_jobs[metro] = sort_by_relevancy(all_new_jobs[metro])

    # Save updated seen list
    seen["seen_ids"] = list(seen_ids)
    save_seen_jobs(seen)

    return all_new_jobs


# ── Email formatting ───────────────────────────────────────────────

def build_email_html(jobs_by_metro, config):
    """Build a clean HTML email body."""
    today = datetime.date.today().strftime("%B %d, %Y")
    total = sum(len(jobs) for jobs in jobs_by_metro.values())
    quote = get_daily_quote()

    html_parts = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'></head>",
        "<body style='font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; "
        "max-width: 640px; margin: 0 auto; padding: 20px; color: #1a1a1a; background: #ffffff;'>",

        # Quote banner
        "<div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); "
        "border-radius: 12px; padding: 24px; margin-bottom: 24px;'>",
        "<p style='font-size: 13px; color: rgba(255,255,255,0.8); margin: 0 0 8px 0; "
        "text-transform: uppercase; letter-spacing: 1px;'>"
        "Motivational Quote of the Day <span style='font-style:normal;'>&#128521;</span></p>",
        f"<p style='font-size: 18px; color: #ffffff; margin: 0; font-style: italic; "
        f"line-height: 1.4;'>&ldquo;{quote}&rdquo;</p>",
        "</div>",

        # Header
        f"<h1 style='font-size: 22px; color: #1a1a1a; margin: 0 0 4px 0;'>"
        f"Med Device Sales Jobs</h1>",
        f"<p style='font-size: 14px; color: #888; margin: 0 0 20px 0;'>"
        f"{today} &mdash; {total} new entry-level listing{'s' if total != 1 else ''}</p>",
    ]

    # Chicago first
    priority_name = config["priority_metro"]["name"]
    if priority_name in jobs_by_metro:
        html_parts.append(render_metro_section(priority_name, jobs_by_metro[priority_name], is_priority=True))

    # Other metros alphabetically (except "Other" which goes last)
    for metro in sorted(jobs_by_metro.keys()):
        if metro == priority_name or metro == "Other":
            continue
        html_parts.append(render_metro_section(metro, jobs_by_metro[metro]))

    # "Other" catch-all at the bottom
    if "Other" in jobs_by_metro:
        html_parts.append(render_metro_section("Other", jobs_by_metro["Other"]))

    html_parts.append(
        "<div style='border-top: 1px solid #eee; margin-top: 32px; padding-top: 16px;'>"
        "<p style='color: #aaa; font-size: 11px; margin: 0;'>"
        "Powered by Google Jobs data &bull; Auto-sent daily &bull; Entry-level roles only"
        "</p></div>"
        "</body></html>"
    )
    return "\n".join(html_parts)


def render_metro_section(metro, jobs, is_priority=False):
    """Render one city's job listings as HTML."""
    if is_priority:
        header = (
            f"<div style='background: #f0f7ff; border-radius: 8px; padding: 12px 16px; "
            f"margin: 24px 0 16px 0;'>"
            f"<h2 style='font-size: 18px; color: #0066cc; margin: 0;'>"
            f"&#11088; {metro} ({len(jobs)})</h2></div>"
        )
    else:
        header = (
            f"<h3 style='font-size: 16px; color: #444; margin: 28px 0 12px 0; "
            f"padding-bottom: 8px; border-bottom: 2px solid #eee;'>"
            f"{metro} ({len(jobs)})</h3>"
        )

    parts = [header]

    for i, job in enumerate(jobs):
        title = job.get("title", "Unknown Title")
        company = job.get("company_name", "Unknown Company")
        location = job.get("location", metro)
        posted = job.get("detected_extensions", {}).get("posted_at", "Recently")
        apply_link = extract_apply_link(job)

        # Relevancy badge for top 3
        badge = ""
        if i == 0:
            badge = "<span style='background:#22c55e;color:#fff;font-size:10px;padding:2px 6px;border-radius:4px;margin-left:8px;'>TOP MATCH</span>"
        elif i <= 2:
            badge = "<span style='background:#3b82f6;color:#fff;font-size:10px;padding:2px 6px;border-radius:4px;margin-left:8px;'>GOOD FIT</span>"

        if apply_link:
            title_html = f'<a href="{apply_link}" style="color: #0066cc; text-decoration: none;">{title}</a>'
        else:
            title_html = title

        bg = "#fafafa" if i % 2 == 0 else "#ffffff"
        parts.append(
            f"<div style='padding: 12px 14px; background: {bg}; border-radius: 6px; margin-bottom: 4px;'>"
            f"<div style='font-size: 15px; font-weight: 600;'>{title_html}{badge}</div>"
            f"<div style='font-size: 13px; color: #555; margin-top: 4px;'>"
            f"{company} &bull; {location}</div>"
            f"<div style='font-size: 12px; color: #999; margin-top: 2px;'>{posted}</div>"
            f"</div>"
        )
    return "\n".join(parts)


def extract_apply_link(job):
    """Get the best apply link from a SerpAPI job result."""
    for option in job.get("apply_options", []):
        link = option.get("link")
        if link:
            return link
    if job.get("job_id"):
        title = job.get("title", "")
        return f"https://www.google.com/search?ibp=htl;jobs&q={title}&htidocid={job['job_id']}"
    return None


# ── Email sending ──────────────────────────────────────────────────

def send_email(html_body, total_jobs, config):
    """Send the digest email via Gmail SMTP."""
    gmail_address = os.environ["GMAIL_ADDRESS"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ.get("RECIPIENT_EMAIL", config["recipient_email"])

    today = datetime.date.today().strftime("%b %d, %Y")
    subject = f"Med Device Sales Jobs - {today} ({total_jobs} new)"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = recipient
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    log.info(f"Sending email to {recipient} ({total_jobs} jobs)")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, gmail_password)
        server.sendmail(gmail_address, recipient, msg.as_string())
    log.info("Email sent successfully")


# ── Main ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Med-tech job alerts")
    parser.add_argument("--dry-run", action="store_true", help="Collect jobs and print email, but don't send")
    args = parser.parse_args()

    load_dotenv()
    config = load_config()

    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        log.error("SERPAPI_KEY environment variable is required")
        sys.exit(1)

    jobs_by_metro = collect_jobs(config, api_key)
    total = sum(len(jobs) for jobs in jobs_by_metro.values())

    if total == 0:
        log.info("No new jobs found. Skipping email.")
        return

    html = build_email_html(jobs_by_metro, config)

    if args.dry_run:
        log.info(f"[DRY RUN] Would send email with {total} jobs")
        for metro, jobs in jobs_by_metro.items():
            print(f"\n{'='*60}")
            print(f"  {metro} ({len(jobs)} jobs)")
            print(f"{'='*60}")
            for i, job in enumerate(jobs):
                score = relevancy_score(job)
                tag = " [TOP MATCH]" if i == 0 else (" [GOOD FIT]" if i <= 2 else "")
                print(f"  {score:3d}pts | {job.get('title', '?')} @ {job.get('company_name', '?')}{tag}")
        out = REPO_ROOT / "preview_email.html"
        out.write_text(html, encoding="utf-8")
        log.info(f"Email preview written to {out}")
        return

    send_email(html, total, config)


if __name__ == "__main__":
    main()
