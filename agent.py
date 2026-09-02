"""
CRVTech Job Search Agent
v0.9.1 - Add ACP-120 certification to PM-track resume tailoring
"""

import os
import re
import json
import httpx
import anthropic
import subprocess
import tempfile
from datetime import datetime, date
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
PROFILE    = BASE_DIR / "profile.txt"
ENV_FILE   = BASE_DIR / "config" / ".env"
PROPOSALS  = BASE_DIR / "data" / "proposals"
RESUMES    = BASE_DIR / "data" / "resumes"
SKIP_LOG   = BASE_DIR / "data" / "skipped_jobs.log"
MANUAL_LOG = BASE_DIR / "data" / "manual_review.log"
USAGE_LOG  = BASE_DIR / "data" / "usage.log"
TAILOR_JS  = BASE_DIR / "tailor_resume.js"

# ── Pricing (Claude Sonnet 4.6 per million tokens) ────────────────────────────
INPUT_COST_PER_M  = 3.00   # $3.00 per million input tokens
OUTPUT_COST_PER_M = 15.00  # $15.00 per million output tokens

# ── Warning thresholds ─────────────────────────────────────────────────────────
SINGLE_RUN_WARN   = 0.25   # Warn + confirm if single run estimate exceeds $0.25
MONTHLY_WARN      = 20.00  # Warn if monthly pace exceeds $20.00

# ── Token cost calculator ──────────────────────────────────────────────────────
def calc_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000 * INPUT_COST_PER_M +
            output_tokens / 1_000_000 * OUTPUT_COST_PER_M)

# ── Estimate tokens before a call ─────────────────────────────────────────────
def estimate_tokens(text: str) -> int:
    """Rough estimate: ~0.75 tokens per character / 4 chars per token."""
    return max(1, len(text) // 4)

# ── Pre-run cost estimate and confirmation ─────────────────────────────────────
def check_estimated_cost(profile: str, posting_text: str) -> bool:
    """
    Estimate total cost for a full run (score + proposal + resume tailor).
    Warn and ask for confirmation if estimate exceeds SINGLE_RUN_WARN.
    Returns True to proceed, False to abort.
    """
    # Rough token estimates for each call
    score_input    = estimate_tokens(profile + posting_text) + 500   # prompt overhead
    score_output   = 300
    proposal_input = estimate_tokens(profile + posting_text) + 300
    proposal_output= 600
    resume_input   = estimate_tokens(profile + posting_text) + 400
    resume_output  = 2000
    title_input    = 300
    title_output   = 20

    total_input  = score_input + proposal_input + resume_input + title_input
    total_output = score_output + proposal_output + resume_output + title_output
    est_cost     = calc_cost(total_input, total_output)

    print(f"\n💰 Estimated run cost: ${est_cost:.4f}  "
          f"(~{total_input:,} input + ~{total_output:,} output tokens)")

    if est_cost > SINGLE_RUN_WARN:
        print(f"\n⚠️  COST WARNING: This run may exceed ${SINGLE_RUN_WARN:.2f}")
        print(f"   Proceed anyway? (yes / no):")
        while True:
            choice = input("> ").strip().lower()
            if choice in ("yes", "y"):
                return True
            elif choice in ("no", "n"):
                print("   Run cancelled.")
                return False
            else:
                print("   Please type yes or no:")

    return True

# ── Log usage after a run ──────────────────────────────────────────────────────
def log_usage(url: str, input_tokens: int, output_tokens: int, action: str):
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    cost      = calc_cost(input_tokens, output_tokens)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry     = (
        f"[{timestamp}] {action} | "
        f"in={input_tokens} out={output_tokens} | "
        f"cost=${cost:.4f} | {url}\n"
    )
    with open(USAGE_LOG, "a") as f:
        f.write(entry)
    return cost

# ── Read usage log for daily/monthly totals ────────────────────────────────────
def read_usage_totals() -> dict:
    """Returns today's total cost and this month's total cost from usage.log."""
    if not USAGE_LOG.exists():
        return {"today": 0.0, "month": 0.0, "today_runs": 0, "month_runs": 0}

    today_str = date.today().strftime("%Y-%m-%d")
    month_str = date.today().strftime("%Y-%m")

    today_cost  = 0.0
    month_cost  = 0.0
    today_runs  = 0
    month_runs  = 0

    for line in USAGE_LOG.read_text().splitlines():
        if not line.strip():
            continue
        # Extract date and cost from log line format
        date_match = re.search(r"\[(\d{4}-\d{2}-\d{2})", line)
        cost_match = re.search(r"cost=\$([0-9.]+)", line)
        if not date_match or not cost_match:
            continue
        log_date = date_match.group(1)
        log_cost = float(cost_match.group(1))

        if log_date == today_str:
            today_cost += log_cost
            today_runs += 1
        if log_date.startswith(month_str):
            month_cost += log_cost
            month_runs += 1

    return {
        "today": today_cost,
        "month": month_cost,
        "today_runs": today_runs,
        "month_runs": month_runs
    }

# ── Print post-run usage summary ──────────────────────────────────────────────
def print_usage_summary(run_cost: float, totals: dict):
    days_in_month  = 30
    today_day      = date.today().day
    monthly_pace   = (totals["month"] / max(today_day, 1)) * days_in_month

    print(f"\n{'─'*60}")
    print(f"💰 This run:      ${run_cost:.4f}")
    print(f"   Today total:   ${totals['today']:.4f}  ({totals['today_runs']} run(s))")
    print(f"   Month total:   ${totals['month']:.4f}  ({totals['month_runs']} run(s))")
    print(f"   Monthly pace:  ${monthly_pace:.2f} / month")

    if monthly_pace > MONTHLY_WARN:
        print(f"\n⚠️  MONTHLY PACE WARNING: On track for ${monthly_pace:.2f} this month")
        print(f"   Budget threshold is ${MONTHLY_WARN:.2f}. Consider reducing run frequency.")

    print(f"{'─'*60}")

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

        if response.status_code in (403, 401, 429):
            return ""

        text = re.sub(r"<[^>]+>", " ", response.text)
        text = re.sub(r"\s+", " ", text).strip()

        login_signals = [
            "join now to see", "sign in", "authwall",
            "join linkedin", "please log in", "create an account"
        ]
        if any(signal in text.lower()[:500] for signal in login_signals):
            return ""

        js_signals = ["function ", "window.", "const ", "let ", "var ",
                      "getDfd()", "Promise(", "=>{"]
        js_count = sum(1 for signal in js_signals if signal in text[:500])
        if js_count >= 2:
            return ""

        return text[:6000]
    except Exception as e:
        raise RuntimeError(f"Could not fetch posting: {e}")

# ── Prompt for manual paste ────────────────────────────────────────────────────
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
def score_fit(client: anthropic.Anthropic, posting_text: str, profile: str) -> tuple[dict, int, int]:
    """Returns (score_data, input_tokens, output_tokens)"""
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
- Work/life balance red flags detected
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

HARD SKIP industries:
  Crypto, blockchain, stock trading, high-frequency trading, speculation

WORK/LIFE BALANCE FLAGS (trigger manual_review):
  Look for: "always on", "24/7", excessive on-call, no flexibility signals

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
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}]
    )

    input_tokens  = message.usage.input_tokens
    output_tokens = message.usage.output_tokens

    raw = message.content[0].text.strip()
    raw = re.sub(r"```json|```", "", raw).strip()
    start = raw.find("{")
    end   = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Claude did not return valid JSON in score_fit.\nRaw:\n{raw[:300]}")
    raw = raw[start:end + 1]
    return json.loads(raw), input_tokens, output_tokens

# ── Manual review prompt ───────────────────────────────────────────────────────
def prompt_manual_review(score_data: dict, url: str, is_linkedin: bool = False) -> bool:
    print(f"\n{'='*60}")
    print("⚠️  MANUAL REVIEW REQUIRED")
    print(f"{'='*60}")
    print(f"   Score:          {score_data['score']}/10 (Manual Review)")

    if is_linkedin:
        print(f"   ⚠️  Data note:   LinkedIn posting — agent working from limited")
        print(f"                   page view. Review the live posting before deciding.")

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
def write_proposal(client: anthropic.Anthropic, posting_text: str, profile: str, score_data: dict) -> tuple[str, int, int]:
    """Returns (proposal_text, input_tokens, output_tokens)"""
    print("✍️  Writing tailored proposal...")

    tone_instructions = {
        "direct_confident":             "Direct and confident. Mix short punchy sentences with longer ones. Lead with results.",
        "formal_polished":              "Formal but still human. Structured paragraphs. Never stiff or robotic. Authoritative.",
        "conversational_authoritative": "Conversational and warm. Write the way a confident person actually talks. Still results-driven."
    }

    tone       = score_data.get("tone", "direct_confident")
    tone_instr = tone_instructions.get(tone, tone_instructions["direct_confident"])
    key_focus  = score_data.get("key_focus", "")

    prompt = f"""
You are writing a job application proposal on behalf of Charles Vickers of CRVTech LLC.
Your job is to write something that sounds like a real, confident human being wrote it —
not like a cover letter template, not like an AI, not like corporate marketing copy.

CHARLES'S PROFILE:
{profile}

JOB POSTING:
{posting_text}

TONE: {tone_instr}
LEAD WITH: {key_focus}

══════════════════════════════════════════
VOICE RULES — READ CAREFULLY
══════════════════════════════════════════

WHAT MAKES IT SOUND HUMAN:
- Vary sentence length intentionally. Short sentences hit hard. Longer ones carry the detail.
- Use contractions naturally where they fit (don't, it's, that's, you're).
- Occasionally start a sentence mid-thought — the way a person would in conversation.
- Let confidence come through in what you don't say as much as what you do.
- Reference specific proof points (numbers, client names, outcomes) without over-explaining them.
- Write the closing like someone who knows they're the right person — not like someone hoping.

WHAT TO NEVER DO:
- Never use: "I am passionate about", "I am excited to", "I would love to", "leverage",
  "synergies", "track record of success", "detail-oriented", "team player",
  "results-driven", "I am confident that", "I believe I would be", "please find",
  "I look forward to hearing from you", "thank you for your consideration"
- Never start with "I" — open with a result, a client name, or a direct statement
- Never write three sentences in a row with the same structure
- Never use the passive voice
- Never pad — every sentence must earn its place
- Never sound like you're filling out a form

STRUCTURAL RULES:
- Maximum 4,500 characters
- End with forward momentum — write like someone who expects the call, not hopes for it
- Write the proposal only — no subject line, no label, no preamble

══════════════════════════════════════════
EXAMPLE OF THE RIGHT VOICE (study this):
══════════════════════════════════════════

EXAMPLE OPENER (direct_confident):
"Four consecutive years. Zero production incidents. Fifty million users on the platform
the whole time. That doesn't happen by accident — it happens when the product leader
running the show treats quality as a feature, not an afterthought.

That's the standard I bring to every engagement."

EXAMPLE OPENER (conversational_authoritative):
"Brigit's mission resonates with me because I've spent the last decade building
products for people who can't afford for them to fail. The Verizon platform I ran
served 50M+ customers. Four years, zero incidents. The work has to be that tight
when the stakes are that real."

EXAMPLE CLOSING (all tones):
"When you're ready to talk through what this could look like, I'm ready for that
conversation."

══════════════════════════════════════════
Now write the full proposal. Match the posting's energy. Use Charles's proof points
specifically. Make it read like a real person wrote it at 11pm because they actually
want this role — not like something generated from a template.
══════════════════════════════════════════
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text.strip(), message.usage.input_tokens, message.usage.output_tokens

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
def tailor_resume(posting_text: str, job_title: str, company: str, score: int, is_mr: bool = False):
    print("📝 Tailoring resume to match posting...")
    RESUMES.mkdir(parents=True, exist_ok=True)
    date_str    = datetime.now().strftime("%Y-%m-%d")
    safe_title  = re.sub(r"[^a-zA-Z0-9]", "_", job_title[:30]).strip("_")
    safe_co     = re.sub(r"[^a-zA-Z0-9]", "_", company[:20]).strip("_")
    mr_flag     = "_MR" if is_mr else ""
    output_file = f"{safe_title}_{safe_co}_{date_str}{mr_flag}.docx"

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

# ── Extract job title and company ─────────────────────────────────────────────
def extract_job_title(client: anthropic.Anthropic, posting_text: str) -> tuple[str, str, int, int]:
    """Returns (title, company, input_tokens, output_tokens)"""
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=80,
        messages=[{
            "role": "user",
            "content": (
                "Extract the job title and company name from this job posting text. "
                "The job title is the specific role being hired for (e.g. VP of Product, "
                "Senior Software Engineer, Head of Product). The company is the organization doing the hiring. "
                "Look carefully through the full text — the title and company may appear anywhere. "
                "Return ONLY these two lines and nothing else:\n"
                "Title: <job title here>\n"
                "Company: <company name here>\n\n"
                f"{posting_text[:2000]}"
            )
        }]
    )
    raw = message.content[0].text.strip()
    title   = "Role"
    company = "Company"
    for line in raw.splitlines():
        line = line.strip()
        if line.lower().startswith("title:"):
            val = line.split(":", 1)[1].strip()
            if val and val.lower() not in ("not specified", "not found", "unknown", "n/a"):
                title = val
        elif line.lower().startswith("company:"):
            val = line.split(":", 1)[1].strip()
            if val and val.lower() not in ("not specified", "not found", "unknown", "n/a"):
                company = val
    return title, company, message.usage.input_tokens, message.usage.output_tokens

# ── Prompt for proposal generation ────────────────────────────────────────────
def prompt_for_proposal() -> bool:
    """Ask whether to generate a proposal. Defaults to No."""
    print("\nGenerate proposal? (yes / no — default is no):")
    choice = input("> ").strip().lower()
    return choice in ("yes", "y")

# ── Process qualifying posting ─────────────────────────────────────────────────
def process_qualifying_posting(client, posting_text, profile, score_data, url, is_mr=False) -> tuple[int, int]:
    """Returns (total_input_tokens, total_output_tokens) for this processing run."""
    score = score_data["score"]

    total_in  = 0
    total_out = 0

    # ── Proposal (optional, defaults to No) ───────────────────────────────────
    if prompt_for_proposal():
        proposal, p_in, p_out = write_proposal(client, posting_text, profile, score_data)
        total_in  += p_in
        total_out += p_out

        saved = save_proposal(proposal, url, score, is_mr)
        label = f"{score}/10 (Manual Review)" if is_mr else f"{score}/10"

        print(f"\n{'='*60}")
        print("PROPOSAL")
        print(f"{'='*60}\n")
        print(proposal)
        print(f"\n{'='*60}")
        print(f"✅ Proposal saved to: {saved}  [{label}]")
    else:
        print("\n⏭️  Proposal skipped.")

    # ── Resume (always generated) ─────────────────────────────────────────────
    job_title, company, t_in, t_out = extract_job_title(client, posting_text)
    total_in  += t_in
    total_out += t_out

    tailor_resume(posting_text, job_title, company, score, is_mr)

    return total_in, total_out

# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    print("\n" + "="*60)
    print("  CRVTech Job Search Agent  v0.9.1")
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

            # Step 2: Pre-run cost estimate + confirmation
            proceed = check_estimated_cost(profile, posting_text)
            if not proceed:
                continue

            # Step 3: Score — track tokens
            total_in  = 0
            total_out = 0

            score_data, s_in, s_out = score_fit(client, posting_text, profile)
            total_in  += s_in
            total_out += s_out

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

            # Force manual review for LinkedIn URLs
            if linkedin and not manual_review:
                manual_review = True
                score_data["manual_review"] = True
                score_data["manual_review_reason"] = (
                    score_data.get("manual_review_reason") or
                    "LinkedIn posting — agent working from limited page view. "
                    "Review the live posting before deciding."
                )

            score_label = f"{score}/10 (Manual Review)" if manual_review else f"{score}/10"

            # ── Score output ───────────────────────────────────────────────────
            print(f"\n📊 Fit Score:    {score_label}")
            print(f"   Reason:      {reason}")
            print(f"   Tone:        {tone}")
            print(f"   Location:    {location}{' (not stated in posting)' if not location_stated else ''}")
            print(f"   Track:       {track}")
            if factors:
                print(f"   Exceptional: {', '.join(factors)}")
            if wlb_flags:
                print(f"   ⚠️  WLB flags: {', '.join(wlb_flags)}")

            # ── Routing ────────────────────────────────────────────────────────
            action = "score_only"

            if manual_review:
                approved = prompt_manual_review(score_data, url, is_linkedin=linkedin)
                if approved:
                    print("\n✅ Approved. Proceeding...")
                    p_in, p_out = process_qualifying_posting(
                        client, posting_text, profile, score_data, url, is_mr=True
                    )
                    total_in  += p_in
                    total_out += p_out
                    action = "manual_review_approved"
                else:
                    print("\n⏭️  Rejected. Logged to manual_review.log.")
                    action = "manual_review_rejected"

            elif score == 0:
                log_skip(url, score, skip_reason or reason)
                print(f"\n🚫 Hard skip. Logged.")
                print(f"   Reason: {skip_reason or reason}")
                action = "hard_skip"

            elif score >= 7:
                p_in, p_out = process_qualifying_posting(
                    client, posting_text, profile, score_data, url
                )
                total_in  += p_in
                total_out += p_out
                action = "auto_proceed"

            else:
                log_skip(url, score, reason)
                print(f"\n⏭️  Score below threshold. Skipped and logged.")
                print(f"   Reason: {reason}")
                action = "skip"

            # ── Post-run usage summary ─────────────────────────────────────────
            run_cost = log_usage(url, total_in, total_out, action)
            totals   = read_usage_totals()
            print_usage_summary(run_cost, totals)

        except Exception as e:
            print(f"\n❌ Something went wrong: {e}")
            print("   Check the URL and try again.")

        print("\n" + "-"*60)

if __name__ == "__main__":
    main()
