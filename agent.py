"""
CRVTech Job Search Agent
Phase 1: Job Fit Scorer + Proposal Writer + Resume Tailor
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

Evaluate this posting using ALL of the following criteria:

HARD SKIPS (return score of 0 if any apply):
- Posting says applications are closed or no longer being accepted
- Domain is crypto, blockchain, stock trading, or adjacent speculation
- Rate is below $50/hr or $500 fixed price
- Requires full-time W2 AND salary is under $185,000
- Applicant count exceeds 500 (if mentioned in posting)
- On-site only with no remote or hybrid option

SCORE REDUCTIONS:
- Applicant count 250-500: reduce score by 2
- Hybrid with more than 2 days in office: reduce score by 1
- Hybrid but office is NOT in NJ or NYC: reduce score by 1
- Full-time W2 role (even if salary is over $185k): reduce score by 1

SCORE BOOSTERS:
+3  Core role match: CPO / CQO / CDO / Jira Admin / Atlassian / Product
+2  Rate is at or above floor ($50/hr or $500 fixed, or salary over $185k)
+2  Industry is in Charles's client history (tech, pharma, media, travel, luxury)
+1  Startup or VC-backed company
+1  Mentions specific pain Charles solves (QA, SDLC, product ops, accessibility)
+1  Remote-friendly or location flexible
+1  Mentions Unlimited PTO (traditional jobs only — boosts score for W2 roles)

Score 1-10. Only generate a proposal if score is 7 or above.

Return JSON only with this exact structure:
{{
  "score": <number 1-10>,
  "reason": "<one sentence explaining the score>",
  "tone": "<one of: direct_confident, formal_polished, conversational_authoritative>",
  "key_focus": "<the single most important thing the proposal should lead with>",
  "location_type": "<one of: remote, hybrid, onsite, unknown>",
  "job_track": "<one of: traditional, fractional, freelance>",
  "skip_reason": "<if hard skip, brief reason — otherwise empty string>"
}}

Return JSON only. No other text.
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    raw = re.sub(r"```json|```", "", raw).strip()
    return json.loads(raw)

# ── Write the proposal ─────────────────────────────────────────────────────────
def write_proposal(client: anthropic.Anthropic, posting_text: str, profile: str, score_data: dict) -> str:
    print("✍️  Writing tailored proposal...")

    tone_instructions = {
        "direct_confident":             "Direct and confident. Short declarative sentences. Lead with results. No hedging.",
        "formal_polished":              "Formal and polished. Structured paragraphs. Professional vocabulary. Authoritative.",
        "conversational_authoritative": "Conversational but authoritative. Warm opener. Slightly shorter paragraphs. Still results-driven."
    }

    tone        = score_data.get("tone", "direct_confident")
    tone_instr  = tone_instructions.get(tone, tone_instructions["direct_confident"])
    key_focus   = score_data.get("key_focus", "")

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
def save_proposal(proposal: str, url: str, score: int) -> Path:
    PROPOSALS.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    domain    = re.sub(r"https?://(www\.)?", "", url).split("/")[0]
    filename  = PROPOSALS / f"{timestamp}_{domain}_score{score}.txt"
    filename.write_text(
        f"URL: {url}\nScore: {score}/10\nGenerated: {timestamp}\n\n{'='*60}\n\n{proposal}"
    )
    return filename

# ── Log a skipped job ──────────────────────────────────────────────────────────
def log_skip(url: str, score: int, reason: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry     = f"[{timestamp}] SCORE {score}/10 | {reason} | {url}\n"
    with open(SKIP_LOG, "a") as f:
        f.write(entry)

# ── Tailor the resume ──────────────────────────────────────────────────────────
def tailor_resume(posting_text: str, job_title: str, score: int):
    print("📝 Tailoring resume to match posting...")

    RESUMES.mkdir(parents=True, exist_ok=True)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M")
    safe_title  = re.sub(r"[^a-zA-Z0-9_]", "_", job_title[:40])
    output_file = f"{timestamp}_{safe_title}_score{score}.docx"

    # Write posting text to a temp file to avoid shell escaping issues
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

# ── Get job title from posting ─────────────────────────────────────────────────
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

# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    print("\n" + "="*60)
    print("  CRVTech Job Search Agent")
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
            # Step 1: Fetch the posting
            posting_text = fetch_posting(url)

            # Step 2: Score the fit
            score_data  = score_fit(client, posting_text, profile)
            score       = score_data["score"]
            reason      = score_data["reason"]
            tone        = score_data.get("tone", "direct_confident")
            skip_reason = score_data.get("skip_reason", "")
            location    = score_data.get("location_type", "unknown")
            track       = score_data.get("job_track", "unknown")

            print(f"\n📊 Fit Score:    {score}/10")
            print(f"   Reason:      {reason}")
            print(f"   Tone:        {tone}")
            print(f"   Location:    {location}")
            print(f"   Track:       {track}")

            # Step 3: Decide
            if score < 7:
                log_reason = skip_reason if skip_reason else reason
                log_skip(url, score, log_reason)
                print(f"\n⏭️  Score below threshold. Skipped and logged.")
                print(f"   Reason: {log_reason}")

            else:
                # Step 4: Write the proposal
                proposal = write_proposal(client, posting_text, profile, score_data)

                # Step 5: Save proposal
                saved_path = save_proposal(proposal, url, score)

                print(f"\n{'='*60}")
                print("PROPOSAL")
                print(f"{'='*60}\n")
                print(proposal)
                print(f"\n{'='*60}")
                print(f"✅ Proposal saved to: {saved_path}")

                # Step 6: Tailor resume
                job_title = extract_job_title(client, posting_text)
                tailor_resume(posting_text, job_title, score)

        except Exception as e:
            print(f"\n❌ Something went wrong: {e}")
            print("   Check the URL and try again.")

        print("\n" + "-"*60)

if __name__ == "__main__":
    main()
