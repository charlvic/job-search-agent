Job Search Agent (JSA)
A personal AI-powered job search agent built with Python and Node.js, using the Claude API to automate job fit scoring, proposal writing, and resume tailoring.
What It Does
The JSA processes job postings from a URL or pasted text and runs them through a multi-step pipeline:
	•	Fit Scoring — scores each posting 1–10 against a personal profile using weighted criteria including role match, location, compensation, industry, and work/life balance signals
	•	Hard Skip Logic — automatically rejects postings that don't meet minimum criteria (crypto/blockchain, <$50/hr, 500+ applicants, closed postings)
	•	Manual Review Lane — pauses for human approval when exceptional factors conflict with a skip rule
	•	Proposal Generation — optionally writes a cover letter/proposal in a natural, human voice calibrated to the tone of the posting
	•	Resume Tailoring — always generates a tailored Word document resume matched to the role, formatted to spec
	•	Cost Tracking — estimates and logs API token usage per run with monthly pace warnings
Tech Stack
	•	Python 3.9+ — main agent loop, scoring engine, proposal writer, token tracker
	•	Node.js — resume tailor (tailor_resume.js) using the docx npm library
	•	Claude API — claude-sonnet-4-6 for all AI operations
	•	Anthropic SDK — Python client for API calls
Project Management
This project is tracked in Jira under the JSA project at crvtech.atlassian.net. All epics, stories, and bugs follow a structured workflow from definition through UAT.
Setup
1. Clone the repo

bash
git clone https://github.com/charlvic/job-search-agent.git
cd job-search-agent
2. Install Python dependencies

bash
pip install anthropic httpx
3. Install Node dependencies

bash
npm install
4. Add your API key

bash
mkdir config
echo "ANTHROPIC_API_KEY=your-key-here" > config/.env
5. Run the agent

bash
python3 agent.py
Project Structure

job-search-agent/
├── agent.py              # Main agent loop
├── tailor_resume.js      # Resume tailor (Node.js)
├── profile.txt           # Personal profile and scoring rules
├── package.json          # Node dependencies
├── config/
│   └── .env              # API key (gitignored)
└── data/                 # Runtime output (gitignored)
    ├── proposals/        # Generated proposals (.txt)
    ├── resumes/          # Tailored resumes (.docx)
    ├── skipped_jobs.log  # Skip log
    ├── manual_review.log # Manual review decisions
    └── usage.log         # Token usage and cost tracking
Status
Currently at v0.9.0 — MVP feature complete. Phase 2 development (LinkedIn API, Excel tracker, cloud hosting) in planning.

Built by Charles Vickers / CRVTech LLC
