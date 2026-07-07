"""
CRVTech Job Search Agent
v0.5.2 - Patch: LinkedIn fetch fallback to manual paste when blocked
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

# ── Load API key ───────────────────────────────────────────────────────────────
def load_api_key():
    if not ENV_FILE.exists():
        raise FileNotFoundError(f"No .env file found at {ENV_FILE}")
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise ValueError("ANTHROPIC_API_KEY not found in .env file")

# ── Load profile ───────────────────────────────────────────────────────────────
def load_profile():
    if not PROFILE.exists():
        raise FileNotFoundError(f"No profile.txt found at {PROFILE}")
    return PROFILE.read_text()

# ── Detect LinkedIn URL ────────────────────────────────────────────────────────
def is_linkedin_url(url: str) -> bool:
    return "linkedin.com" in url.lower()

# ── Fetch the job posting ──────────────────────────────────────────────────────
def fetch_posting(url: str) -> str:
    print(f"\n📡 Fetching posting from: {url}")
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        response = httpx.get(url, headers=headers, follow_redirects=True, timeout=15)

        # Detect login wall or block
        if response.status_code in (403, 401, 429):
            return ""

        text = re.sub(r"<[^>]+>", " ", response.text)
        text = re.sub(r"\s+", " ", text).strip()

        # Detect LinkedIn login wall in body
        login_signals = [
            "join now to see", "sign in", "authwall",
            "join linkedin", "please log in", "create an account"
        ]
        if any(signal in text.lower()[:500] for signal in login_signals):
            return ""

        return text[:6000]
    except Exception as e:
        raise RuntimeError(f"Could not fetch posting: {e}")

# ── Prompt for manual paste when fetch is blocked ─────────────────────────────
def prompt_for_paste() -> str:
    print("\n🔒 LinkedIn requires login to view this posting.")
    print("   The agent can't fetch it automatically.")
    print("\n   Please do the following:")
    print("   1. Open the LinkedIn posting in your browser")
    print("   2. Select all the job description text")
    print("   3. Paste it below, then type END on a new line and hit Enter\n")

    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line)

    text = "\n".join(lines).strip()
    if not text:
        raise ValueError("No job description text was entered.")
    return text[:6000]

# ── Score the fit ──────────────────────────────────────────────────────────────
def score_fit(client: anthropic.Anthropic, posting_text: str, profile: str) -> dict:
    print("🧠 Scoring fit against your profile...")

    prompt = f"""
You are evaluating a job posting for Charles Vickers of CRVTech LLC.

Here is Charles's profile:
{profile}

Here is the job posting text:
{posting_text}

IMPORTANT SCORING RULES — follow these exactly and show your math:

════════════════════════════════════════
HARD SKIPS — score 0, manual_review must be false:
════════════════════════════════════════
- Posting says applications are closed
- Domain is crypto, blockchain, stock trading, or speculation (NOT general fintech/banking)
- Hourly rate below $50/hr or fixed price below $500
- Applicant count over 500
- On-site + far outside NJ/NYC (Austin, Chicago, LA, Seattle etc.) + no exceptional factors

════════════════════════════════════════
MANUAL REVIEW — set manual_review: true when:
════════════════════════════════════════
- Hard skip would apply BUT exceptional factors present
- On-site only BUT exceptional factors present
- Outside NJ/NYC BUT exceptional factors present
- Work/life balance red flags detected (always-on culture, 24/7 language, no flexibility signals)
ALWAYS return the real calculated score when manual_review is true. Never return 0.

════════════════════════════════════════
LOCATION:
════════════════════════════════════════
Remote:                        +1
Hybrid in NJ or NYC, ≤2 days: +0
Hybrid >2 days or outside NJ/NYC: -1
On-site:                       -2 (not a hard skip if compensating factors exist)
Outside NJ/NYC tri-state:      -1 additional
Unknown/not stated:            +0, set location_stated: false

════════════════════════════════════════
W2 SCORING — follow this math precisely:
════════════════════════════════════════
Step 1: Apply base W2 penalty: -1
Step 2: Apply salary tier offset:
  $185k–$249k → +0 additional (floor met, no boost)
  $250k–$299k → +1 (partially offsets W2 penalty)
  $300k+      → +2 (fully offsets and exceeds W2 penalty)
Step 3: Benefits:
  Unlimited PTO on W2: +1
  Both $300k+ AND Unlimited PTO: +2 total (not stacked)

CRITICAL W2 RULES:
- NEVER mention fractional positioning as a negative for W2 roles
- NEVER reduce score because a W2 role lacks a fractional option
- NEVER say W2 is "outside Charles's primary positioning"
- Score W2 roles purely as traditional employment opportunities
- Fractional fit is ONLY relevant when a posting explicitly offers it

════════════════════════════════════════
INDUSTRY:
════════════════════════════════════════
ACCEPTABLE (score +2 for industry match):
  Tech, SaaS, healthcare, retail, ecommerce, luxury, media, travel,
  telecom, financial services, fintech, banking, insurance
  NOTE: Charles's QA governance and process/control skills map
  well to financial services. Score these roles normally.

HARD SKIP industries:
  Crypto, blockchain, stock trading, high-frequency trading, speculation

WORK/LIFE BALANCE FLAGS (trigger manual_review):
  Look for: "always on", "24/7", excessive on-call, no flexibility signals,
  "wear many hats" in intensity context, finance roles with no WLB mention.

════════════════════════════════════════
SCORE BOOSTERS:
════════════════════════════════════════
+3  Core role: CPO / Head of Product / VP Product / CQO / CDO /
    Jira Admin / Atlassian / Product Director
+2  Rate/salary meets floor ($50/hr, $500 fixed, or $185k+ W2)
+2  Industry match (see list above)
+1  Startup or VC-backed
+1  Mentions pain Charles solves: QA, SDLC, product ops, accessibility,
    Atlassian, governance, compliance
+1  Remote-friendly or flexible location
+1  Unlimited PTO (W2 traditional track only)

════════════════════════════════════════
APPLICANT COUNT:
════════════════════════════════════════
Under 250: no penalty
250–500:   -2
Over 500:  hard skip

════════════════════════════════════════
THRESHOLD:
════════════════════════════════════════
7+  = auto-proceed
4–6 = skip and log
0   = hard skip and log
manual_review = true always pauses for Charles

Show your scoring math clearly in the reason field.
Return JSON only — no preamble, no markdown, no commentary:
{{
  "score": <number 1-10, real calculated score — never 0 when manual_review is true>,
  "reason": "<factor by factor breakdown showing the math that led to the score>",
  "tone": "<one of: direct_confident, formal_polished, conversational_authoritative>",
  "key_focus": "<the single most important thing the proposal should lead with>",
  "location_type": "<one of: remote, hybrid, onsite, unknown>",
  "location_stated": <true or false>,
  "job_track": "<one of: traditional, fractional, freelance>",
  "skip_reason": "<if hard skip, brief reason — otherwise empty string>",
  "manual_review": <true or false>,
  "manual_review_reason": "<if manual review, explain the conflict and exceptional factors — otherwise empty string>",
  "exceptional_factors": ["<list any: salary tier, equity, unlimited PTO, skills match, company prestige, WLB flags>"],
  "wlb_flags": ["<list any work/life balance red flags detected — empty list if none>"]
}}
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=700,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    raw = re.sub(r"```json|```", "", raw).strip()
    # Extract JSON boundaries as safety net against trailing content
    start = raw.find("{")
    end   = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Claude did not return a valid JSON object in score_fit")
    raw = raw[start:end + 1]
    return json.loads(raw)

# ── Manual review prompt ───────────────────────────────────────────────────────
def prompt_manual_review(score_data: dict, url: str, is_linkedin: bool = False) -> bool:
    print(f"\n{'='*60}")
    print("⚠️  MANUAL REVIEW REQUIRED")
    print(f"{'='*60}")
    print(f"   Score:          {score_data['score']}/10 (Manual Review)")

    if is_linkedin:
        print(f"   ⚠️  Data note:   LinkedIn posting — agent working from limited")
        print(f"                   page view due to login wall. Full details may")
        print(f"                   differ from what was scored. Review the live")
        print(f"                   posting before deciding.")

    print(f"   Conflict:       {score_data['manual_review_reason']}")

    factors = score_data.get("exceptional_factors", [])
    if factors:
        print(f"   Exceptional:    {', '.join(factors)}")

    wlb = score_data.get("wlb_flags", [])
    if wlb:
        print(f"   ⚠️  WLB flags:   {', '.join(wlb)}")

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

# ── Log manual review ──────────────────────────────────────────────────────────
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

# ── Write proposal ─────────────────────────────────────────────────────────────
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

Rules:
- Maximum 4,500 characters
- Never start with "I" — open with a result, client name, or bold claim
- Use specific proof points (numbers, client names, outcomes)
- No generic openers, no passive voice, no AI-sounding phrases
- End with forward momentum, not "I look forward to hearing from you"
- Write the proposal only — no preamble, no labels

Write the proposal now:
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text.strip()

# ── Save proposal ──────────────────────────────────────────────────────────────
def save_proposal(proposal: str, url: str, score: int, is_mr: bool = False) -> Path:
    PROPOSALS.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    domain    = re.sub(r"https?://(www\.)?", "", url).split("/")[0]
    mr_flag   = "_MR" if is_mr else ""
    filename  = PROPOSALS / f"{timestamp}_{domain}_score{score}{mr_flag}.txt"
    label     = f"{score}/10 (Manual Review)" if is_mr else f"{score}/10"
    filename.write_text(
        f"URL: {url}\nScore: {label}\nGenerated: {timestamp}\n\n{'='*60}\n\n{proposal}"
    )
    return filename

# ── Log skip ───────────────────────────────────────────────────────────────────
def log_skip(url: str, score: int, reason: str):
    SKIP_LOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(SKIP_LOG, "a") as f:
        f.write(f"[{timestamp}] SCORE {score}/10 | {reason} | {url}\n")

# ── Tailor resume ──────────────────────────────────────────────────────────────
def tailor_resume(posting_text: str, job_title: str, score: int, is_mr: bool = False):
    print("📝 Tailoring resume to match posting...")
    RESUMES.mkdir(parents=True, exist_ok=True)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M")
    safe_title  = re.sub(r"[^a-zA-Z0-9_]", "_", job_title[:40])
    mr_flag     = "_MR" if is_mr else ""
    output_file = f"{timestamp}_{safe_title}_score{score}{mr_flag}.docx"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp.write(posting_text)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["node", str(TAILOR_JS), tmp_path, output_file],
            capture_output=True, text=True, cwd=str(BASE_DIR)
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
            "content": f"Extract only the job title from this posting. Return the title only:\n\n{posting_text[:1000]}"
        }]
    )
    return message.content[0].text.strip()

# ── Process qualifying posting ─────────────────────────────────────────────────
def process_qualifying_posting(client, posting_text, profile, score_data, url, is_mr=False):
    score     = score_data["score"]
    proposal  = write_proposal(client, posting_text, profile, score_data)
    saved     = save_proposal(proposal, url, score, is_mr)
    label     = f"{score}/10 (Manual Review)" if is_mr else f"{score}/10"

    print(f"\n{'='*60}")
    print("PROPOSAL")
    print(f"{'='*60}\n")
    print(proposal)
    print(f"\n{'='*60}")
    print(f"✅ Proposal saved to: {saved}  [{label}]")

    job_title = extract_job_title(client, posting_text)
    tailor_resume(posting_text, job_title, score, is_mr)

# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    print("\n" + "="*60)
    print("  CRVTech Job Search Agent  v0.5.2")
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

        linkedin = is_linkedin_url(url)

        try:
            # Step 1: Fetch — fall back to manual paste if blocked
            posting_text = fetch_posting(url)
            if not posting_text:
                posting_text = prompt_for_paste()

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
            wlb_flags       = score_data.get("wlb_flags", [])

            # Force manual review for all LinkedIn URLs
            if linkedin and not manual_review:
                manual_review = True
                score_data["manual_review"] = True
                score_data["manual_review_reason"] = (
                    score_data.get("manual_review_reason") or
                    "LinkedIn posting — agent working from limited page view due to login wall. "
                    "Full posting details may differ from what was scored."
                )

            score_label = f"{score}/10 (Manual Review)" if manual_review else f"{score}/10"

            # ── Output ────────────────────────────────────────────────────────
            print(f"\n📊 Fit Score:    {score_label}")
            print(f"   Reason:      {reason}")
            print(f"   Tone:        {tone}")
            print(f"   Location:    {location}{' (not stated in posting)' if not location_stated else ''}")
            print(f"   Track:       {track}")
            if factors:
                print(f"   Exceptional: {', '.join(factors)}")
            if wlb_flags:
                print(f"   ⚠️  WLB flags: {', '.join(wlb_flags)}")

            # ── Routing ───────────────────────────────────────────────────────

            # Manual review always takes priority
            if manual_review:
                approved = prompt_manual_review(score_data, url, is_linkedin=linkedin)
                if approved:
                    print("\n✅ Approved. Proceeding...")
                    process_qualifying_posting(client, posting_text, profile, score_data, url, is_mr=True)
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
