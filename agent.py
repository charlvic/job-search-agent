"""
CRVTech Job Search Agent
v0.4.0 - Fix manual review score display, MR filename flagging, resume tailor JSON hardening
"""

import os
import re
import json
import httpx
import anthropic
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
PROFILE    = BASE_DIR / "profile.txt"
ENV_FILE   = BASE_DIR / "config" / ".env"
PROPOSALS  = BASE_DIR / "data" / "proposals"
RESUMES    = BASE_DIR / "data" / "resumes"
SKIP_LOG   = BASE_DIR / "data" / "skipped_jobs.log"
MANUAL_LOG = BASE_DIR / "data" / "manual_review.log"
TAILOR_JS  = BASE_DIR / "tailor_resume.js"

# ── Load API key from .env ─────────────────────────────────────────────────────
def load_api_key():
    if not ENV_FILE.exists():
        raise FileNotFoundError(f"No .env file found at {ENV_FILE}")
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise ValueError("ANTHROPIC_API_KEY not found in .env file")

# ── Load your profile ──────────────────────────────────────────────────────────
def load_profile():
    if not PROFILE.exists():
        raise FileNotFoundError(f"No profile.txt found at {PROFILE}")
    return PROFILE.read_text()

# ── Fetch the job posting ──────────────────────────────────────────────────────
def fetch_posting(url: str) -> str:
    print(f"\n📡 Fetching posting from: {url}")
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        response = httpx.get(url, headers=headers, follow_redirects=True, timeout=15)
        response.raise_for_status()
        text = re.sub(r"<[^>]+>", " ", response.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:6000]
    except Exception as e:
        raise RuntimeError(f"Could not fetch posting: {e}")

# ── Score the fit ──────────────────────────────────────────────────────────────
def score_fit(client: anthropic.Anthropic, posting_text: str, profile: str) -> dict:
    print("🧠 Scoring fit against your profile...")

    prompt = f"""
You are evaluating a job posting for Charles Vickers of CRVTech LLC.

Here is Charles's profile:
{profile}

Here is the job posting text:
{posting_text}

Evaluate this posting using ALL of the following criteria carefully and precisely.

════════════════════════════════════════
HARD SKIPS — return score of 0 if ANY apply (and manual_review must be false):
════════════════════════════════════════
- Posting explicitly says applications are closed or no longer being accepted
- Domain is crypto, blockchain, stock trading, or adjacent financial speculation
- Hourly rate below $50/hr or fixed price below $500
- Applicant count exceeds 500
- Location is far outside NJ/NYC (e.g. Austin, Chicago, LA, Seattle) AND on-site required AND no exceptional compensating factors

════════════════════════════════════════
MANUAL REVIEW TRIGGERS — set manual_review: true when:
════════════════════════════════════════
A hard skip rule would normally apply BUT exceptional compensating factors are present:
- Salary $250k+ or $300k+
- Equity or stock options mentioned
- Unlimited PTO mentioned
- Near-perfect skills match (9+/10)
- Highly prestigious or strategically valuable company

Also trigger manual review for:
- On-site only BUT exceptional compensating factors present
- Location outside NJ/NYC/tri-state BUT exceptional compensating factors present

IMPORTANT: When manual_review is true, always calculate and return the REAL
underlying score (1-10) as if the hard skip did not apply. Never return 0
when manual_review is true. The real score helps Charles make an informed decision.

════════════════════════════════════════
LOCATION SCORING:
════════════════════════════════════════
Remote: +1 fully preferred
Hybrid:
  +0 acceptable, no penalty when office is in NJ or NYC
  -1 when office days exceed 2 per week
  -1 when office location is outside NJ/NYC (CT, PA, or other states)
On-site:
  -2 meaningful reduction, never a hard skip if compensating factors exist
  -1 additional if location is CT, PA, or outside NJ/NYC tri-state
  Trigger manual review if exceptional compensating factors present
Unknown/not stated:
  +0 neutral, do not assume on-site, do not penalize
  Set location_stated: false

Geography hard skip (only when ALL true and manual_review is false):
  - Location far outside NJ/NYC (Austin, Chicago, LA, Seattle etc.)
  - AND on-site required
  - AND no exceptional compensating factors

════════════════════════════════════════
W2 TRADITIONAL ROLE SCORING:
════════════════════════════════════════
Base W2: -1

Salary tiers (offset the base W2 penalty):
  $185k–$249k: meets floor, no additional adjustment
  $250k–$299k: +1
  $300k+:      +2

Benefits boosters (W2 only):
  Unlimited PTO: +1
  Both $300k+ salary AND Unlimited PTO: +2 total (not stacked separately)

W2 rules:
  - NEVER penalize W2 for lacking fractional option
  - Score W2 on traditional employment criteria only
  - Fractional fit only relevant when posting explicitly mentions it

════════════════════════════════════════
SCORE BOOSTERS:
════════════════════════════════════════
+3  Core role match: CPO / Head of Product / VP Product / CQO / CDO / Jira Admin / Product Director
+2  Rate at or above floor, or salary meets $185k+ threshold
+2  Industry in Charles's client history (tech, pharma, media, travel, luxury, retail)
+1  Startup or VC-backed company
+1  Mentions specific pain Charles solves (QA, SDLC, product ops, accessibility, Atlassian)
+1  Remote-friendly or location flexible

════════════════════════════════════════
APPLICANT COUNT:
════════════════════════════════════════
250–500: -2
500+: hard skip (score 0), unless manual_review triggered by exceptional factors

════════════════════════════════════════
THRESHOLD:
════════════════════════════════════════
7+  = auto-proceed
4–6 = skip and log
0–3 = hard skip and log
manual_review = true always pauses for Charles regardless of score

Return JSON only — no preamble, no markdown fences, no commentary:
{{
  "score": <number 1-10, always the real calculated score — never 0 when manual_review is true>,
  "reason": "<two to three sentences explaining the score factor by factor>",
  "tone": "<one of: direct_confident, formal_polished, conversational_authoritative>",
  "key_focus": "<the single most important thing the proposal should lead with>",
  "location_type": "<one of: remote, hybrid, onsite, unknown>",
  "location_stated": <true or false>,
  "job_track": "<one of: traditional, fractional, freelance>",
  "skip_reason": "<if hard skip, brief reason — otherwise empty string>",
  "manual_review": <true or false>,
  "manual_review_reason": "<if manual review, explain the conflict and exceptional factors — otherwise empty string>",
  "exceptional_factors": ["<list any: salary tier, equity, unlimited PTO, skills match strength, company prestige>"]
}}
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    raw = re.sub(r"```json|```", "", raw).strip()
    return json.loads(raw)

# ── Manual review prompt ───────────────────────────────────────────────────────
def prompt_manual_review(score_data: dict, url: str) -> bool:
    print(f"\n{'='*60}")
    print("⚠️  MANUAL REVIEW REQUIRED")
    print(f"{'='*60}")
    print(f"   Score:          {score_data['score']}/10 (Manual Review)")
    print(f"   Conflict:       {score_data['manual_review_reason']}")

    factors = score_data.get("exceptional_factors", [])
    if factors:
        print(f"   Exceptional:    {', '.join(factors)}")

    print(f"   Location:       {score_data['location_type']}")
    print(f"   Track:          {score_data['job_track']}")
    print(f"{'='*60}")
    print("\nProceed with proposal and resume? (yes / no / skip):")

    while True:
        choice = input("> ").strip().lower()
        if choice in ("yes", "y"):
            log_manual_review(url, score_data, "APPROVED")
            return True
        elif choice in ("no", "n", "skip", "s"):
            log_manual_review(url, score_data, "REJECTED")
            return False
        else:
            print("Please type yes, no, or skip:")

# ── Log manual review decision ─────────────────────────────────────────────────
def log_manual_review(url: str, score_data: dict, decision: str):
    MANUAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"[{timestamp}] {decision} | "
        f"SCORE {score_data['score']}/10 (MR) | "
        f"{score_data['manual_review_reason']} | "
        f"FACTORS: {', '.join(score_data.get('exceptional_factors', []))} | "
        f"{url}\n"
    )
    with open(MANUAL_LOG, "a") as f:
        f.write(entry)

# ── Write the proposal ─────────────────────────────────────────────────────────
def write_proposal(client: anthropic.Anthropic, posting_text: str, profile: str, score_data: dict) -> str:
    print("✍️  Writing tailored proposal...")

    tone_instructions = {
        "direct_confident":             "Direct and confident. Short declarative sentences. Lead with results. No hedging.",
        "formal_polished":              "Formal and polished. Structured paragraphs. Professional vocabulary. Authoritative.",
        "conversational_authoritative": "Conversational but authoritative. Warm opener. Slightly shorter paragraphs. Still results-driven."
    }

    tone       = score_data.get("tone", "direct_confident")
    tone_instr = tone_instructions.get(tone, tone_instructions["direct_confident"])
    key_focus  = score_data.get("key_focus", "")

    prompt = f"""
You are writing a job application proposal on behalf of Charles Vickers of CRVTech LLC.

Here is Charles's full profile including voice rules, proof points, and proposal structure guidelines:
{profile}

Here is the job posting:
{posting_text}

Tone instruction: {tone_instr}
Lead with this focus: {key_focus}

Write a single complete proposal following these rules:
- Maximum 4,500 characters
- Never start with "I" — open with a result, client name, or bold claim
- Use specific proof points from the profile (numbers, client names, outcomes)
- No generic openers like "I am excited to apply"
- No passive voice
- No AI-sounding phrases
- End with forward momentum, not "I look forward to hearing from you"
- Write the proposal only — no preamble, no commentary, no labels

Write the proposal now:
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text.strip()

# ── Save proposal to file ──────────────────────────────────────────────────────
def save_proposal(proposal: str, url: str, score: int, is_manual_review: bool = False) -> Path:
    PROPOSALS.mkdir(parents=True, exist_ok=True)
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M")
    domain     = re.sub(r"https?://(www\.)?", "", url).split("/")[0]
    mr_flag    = "_MR" if is_manual_review else ""
    filename   = PROPOSALS / f"{timestamp}_{domain}_score{score}{mr_flag}.txt"
    label      = f"{score}/10 (Manual Review)" if is_manual_review else f"{score}/10"
    filename.write_text(
        f"URL: {url}\nScore: {label}\nGenerated: {timestamp}\n\n{'='*60}\n\n{proposal}"
    )
    return filename

# ── Log a skipped job ──────────────────────────────────────────────────────────
def log_skip(url: str, score: int, reason: str):
    SKIP_LOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry     = f"[{timestamp}] SCORE {score}/10 | {reason} | {url}\n"
    with open(SKIP_LOG, "a") as f:
        f.write(entry)

# ── Tailor the resume ──────────────────────────────────────────────────────────
def tailor_resume(posting_text: str, job_title: str, score: int, is_manual_review: bool = False):
    print("📝 Tailoring resume to match posting...")

    RESUMES.mkdir(parents=True, exist_ok=True)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M")
    safe_title  = re.sub(r"[^a-zA-Z0-9_]", "_", job_title[:40])
    mr_flag     = "_MR" if is_manual_review else ""
    output_file = f"{timestamp}_{safe_title}_score{score}{mr_flag}.docx"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp.write(posting_text)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["node", str(TAILOR_JS), tmp_path, output_file],
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR)
        )
        if result.returncode != 0:
            print(f"⚠️  Resume tailor error: {result.stderr}")
        else:
            print(result.stdout.strip())
    finally:
        os.unlink(tmp_path)

# ── Extract job title ──────────────────────────────────────────────────────────
def extract_job_title(client: anthropic.Anthropic, posting_text: str) -> str:
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=50,
        messages=[{
            "role": "user",
            "content": f"Extract only the job title from this posting. Return the title only, nothing else:\n\n{posting_text[:1000]}"
        }]
    )
    return message.content[0].text.strip()

# ── Process a qualifying posting ───────────────────────────────────────────────
def process_qualifying_posting(client, posting_text, profile, score_data, url, is_manual_review=False):
    score = score_data["score"]

    proposal   = write_proposal(client, posting_text, profile, score_data)
    saved_path = save_proposal(proposal, url, score, is_manual_review)

    score_label = f"{score}/10 (Manual Review)" if is_manual_review else f"{score}/10"

    print(f"\n{'='*60}")
    print("PROPOSAL")
    print(f"{'='*60}\n")
    print(proposal)
    print(f"\n{'='*60}")
    print(f"✅ Proposal saved to: {saved_path}  [{score_label}]")

    job_title = extract_job_title(client, posting_text)
    tailor_resume(posting_text, job_title, score, is_manual_review)

# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    print("\n" + "="*60)
    print("  CRVTech Job Search Agent  v0.4.0")
    print("="*60)

    api_key = load_api_key()
    profile = load_profile()
    client  = anthropic.Anthropic(api_key=api_key)

    while True:
        print("\nPaste a job posting URL (or type 'quit' to exit):")
        url = input("> ").strip()

        if url.lower() in ("quit", "exit", "q"):
            print("\nAgent shutting down. Good luck out there.\n")
            break

        if not url.startswith("http"):
            print("⚠️  That doesn't look like a URL. Please paste the full link starting with https://")
            continue

        try:
            # Step 1: Fetch
            posting_text = fetch_posting(url)

            # Step 2: Score
            score_data      = score_fit(client, posting_text, profile)
            score           = score_data["score"]
            reason          = score_data["reason"]
            tone            = score_data.get("tone", "direct_confident")
            location        = score_data.get("location_type", "unknown")
            location_stated = score_data.get("location_stated", True)
            track           = score_data.get("job_track", "unknown")
            manual_review   = score_data.get("manual_review", False)
            skip_reason     = score_data.get("skip_reason", "")
            factors         = score_data.get("exceptional_factors", [])

            # ── Score display ──────────────────────────────────────────────────
            score_label = f"{score}/10 (Manual Review)" if manual_review else f"{score}/10"

            print(f"\n📊 Fit Score:    {score_label}")
            print(f"   Reason:      {reason}")
            print(f"   Tone:        {tone}")
            print(f"   Location:    {location}{' (not stated in posting)' if not location_stated else ''}")
            print(f"   Track:       {track}")
            if factors:
                print(f"   Exceptional: {', '.join(factors)}")

            # ── Routing ────────────────────────────────────────────────────────

            # Manual review lane — always takes priority
            if manual_review:
                approved = prompt_manual_review(score_data, url)
                if approved:
                    print("\n✅ Approved. Proceeding...")
                    process_qualifying_posting(client, posting_text, profile, score_data, url, is_manual_review=True)
                else:
                    print("\n⏭️  Rejected. Logged to manual_review.log.")

            # Hard skip
            elif score == 0:
                log_skip(url, score, skip_reason or reason)
                print(f"\n🚫 Hard skip. Logged.")
                print(f"   Reason: {skip_reason or reason}")

            # Auto-proceed
            elif score >= 7:
                process_qualifying_posting(client, posting_text, profile, score_data, url)

            # Standard skip
            else:
                log_skip(url, score, reason)
                print(f"\n⏭️  Score below threshold. Skipped and logged.")
                print(f"   Reason: {reason}")

        except Exception as e:
            print(f"\n❌ Something went wrong: {e}")
            print("   Check the URL and try again.")

        print("\n" + "-"*60)

if __name__ == "__main__":
    main()
