#!/usr/bin/env node
/**
 * CRVTech Resume Tailor
 * Reads resume_canonical.docx, tailors content to a job posting,
 * and writes a new .docx file preserving all original formatting.
 *
 * Usage: node tailor_resume.js <job_posting_text> <output_filename>
 */

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, BorderStyle, WidthType, ShadingType,
  ExternalHyperlink, UnderlineType
} = require("docx");

const fs   = require("fs");
const path = require("path");
const http = require("https");

// ── Paths ─────────────────────────────────────────────────────────────────────
const BASE_DIR    = __dirname;
const ENV_FILE    = path.join(BASE_DIR, "config", ".env");
const PROFILE     = path.join(BASE_DIR, "profile.txt");
const OUTPUT_DIR  = path.join(BASE_DIR, "data", "resumes");

// ── Load API key ──────────────────────────────────────────────────────────────
function loadApiKey() {
  const env = fs.readFileSync(ENV_FILE, "utf8");
  const match = env.match(/ANTHROPIC_API_KEY=(.+)/);
  if (!match) throw new Error("ANTHROPIC_API_KEY not found in .env");
  return match[1].trim();
}

// ── Call Claude API ───────────────────────────────────────────────────────────
function callClaude(apiKey, prompt) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({
      model: "claude-sonnet-4-6",
      max_tokens: 4000,
      messages: [{ role: "user", content: prompt }]
    });

    const options = {
      hostname: "api.anthropic.com",
      path: "/v1/messages",
      method: "POST",
      headers: {
        "Content-Type":      "application/json",
        "x-api-key":         apiKey,
        "anthropic-version": "2023-06-01",
        "Content-Length":    Buffer.byteLength(body)
      }
    };

    const req = http.request(options, (res) => {
      let data = "";
      res.on("data", chunk => data += chunk);
      res.on("end", () => {
        try {
          const parsed = JSON.parse(data);
          if (parsed.error) return reject(new Error(parsed.error.message));
          resolve(parsed.content[0].text);
        } catch (e) {
          reject(new Error("Failed to parse Claude response: " + data));
        }
      });
    });

    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

// ── Generate tailored content via Claude ──────────────────────────────────────
async function getTailoredContent(apiKey, jobPosting, profile) {
  console.log("🧠 Generating tailored resume content...");

  const prompt = `
You are tailoring Charles Vickers' resume for a specific job posting.

CHARLES'S PROFILE AND BACKSTORY:
${profile}

CANONICAL RESUME CONTENT:
Name: CHARLES VICKERS
Current Headline: Senior Product Manager / Product Director – CRM, CMS, Mobile & Commerce
Contact: Bloomfield, NJ | 973.698.6714 | charlesvickers.2019@gmail.com | www.linkedin.com/in/vickerscharles

SUMMARY:
Product Leader with 12+ years owning products for Fortune 500 clients across telecommunications, healthcare, retail, auto, and air travel. Combines deep customer discovery, technical fluency, and an accessibility/QA background to ship scalable, inclusive digital experiences. Uses modern product approaches like North Star, RICE & JTBD to align strategy, prioritization, and Product-Market Fit.

HIGHLIGHTS:
- End-to-end ownership of multi-channel products: discovery → roadmap → launch → iteration
- Deep experience integrating ADA best practices, AI-powered workflows, and Quality-first thinking
- Specialization in Martech, Digital Health, and Web/Mobile commerce CX & platforms
- Drove accessible, incident-free products netting $200M in new revenue

KEY PRODUCT DELIVERIES & IMPACT:
- Verizon Martech Platform – 4-year product ownership for 50M+ customers; maintained 100% uptime w/ zero incidents, faster release cycles & higher adoption netting $140M in new rev
- Audible Email Marketing Platform – Custom accessibly compliant omni-channel Martech system; achieved 44% open rate (13% above benchmark)
- CityMD Digital Health Platform – HIPAA & WCAG 2.2 compliant patient experience that increased online appointment bookings by 30%
- Alaska Airlines Mobile Commerce – Mobile commerce features and journeys generating $5M+ incremental revenue in year one
- Chanel Interactive Retail Studio – (Rescued) Omnichannel microsite + in-store beacons + ecommerce; turned 800+ pre-launch defects into a successful flagship launch + follow-on work
- Bristol-Myers Squibb CMS Platform – Separate CMS experiences for doctors and patients, driving 25%+ engagement improvement

PROFESSIONAL EXPERIENCE:

CRVTech LLC - Founder & Principal Consultant, Bloomfield, NJ | Sept 2025 – Present
- Provide Product Strategy, Quality Assurance, and Technical Operations consulting to early-stage 0->1 technology startups
- Define product vision and roadmaps, translating founder ideas and market data into prioritized backlogs using frameworks such as North Star, GIST, and the 4 Big Risks
- Guide feature prioritization, MVP definition, and go-to-market strategies using RICE, MoSCoW, and AARRR where appropriate
- Advise on WCAG 2.x accessibility and AI-driven product workflows to ensure new products launch inclusive and resilient from day one
- Architected rollout of Atlassian Suite (Jira, Confluence, Loom, Rovo AI) and established core product operating model leveraging frameworks tailored to startup growth and team topology

Publicis Groupe (Rauxa / Razorfish) - Product Director, New York, NY | Sept 2019 – Sept 2025
- Led end-to-end product lifecycle for multichannel CRM, CMS, mobile, and commerce initiatives across Verizon, Audible, Alaska Airlines, Bristol-Myers Squibb, Audi, Porsche, and CityMD
- Owned product strategy, discovery, and roadmap, running workshops, customer interviews, and prioritization sessions to translate insights into clear product outcomes
- Defined and managed product backlogs for 8+ concurrent teams, setting DoR/DoD standards, driving estimation, and making tradeoff decisions to keep delivery aligned with value
- Facilitated executive readouts, roadmap updates, sprint demos, and UAT/go-to-market reviews with C-level stakeholders and business unit leaders
- Scaled cross-functional product teams from 5 to 30+ across the Americas, EMEA, and APAC, establishing operating rituals and embedding accessibility and quality up front
- Acted as Atlassian Product Owner and SuperAdmin, standardizing Jira/Confluence projects, workflows and dashboards for visibility into roadmap, delivery, and risk
- Integrated AI tools into discovery, design, and testing workflows to improve team throughput by ~30%
- Partnered with account and sales leadership to craft product visions and ROI-backed roadmaps that helped secure $155M+ in new business
- Collaborated with engineering leads to shape technical approaches, sequence dependencies, and manage functional & non-functional requirements (performance, security, accessibility)
- Established outcome-oriented metrics and OKRs for key products and used analytics to inform roadmap adjustments and experiment design

Valtech - Product Lead & Technology Director, New York, NY | March 2014 – August 2019
- Led product and engineering teams delivering CMS platforms, DAM/PIM systems, and B2B/B2C ecommerce for clients including Chanel, L'Oréal, Hyatt, Dot Foods, Samsung, & Wolters Kluwer
- Defined product execution models and cross-functional ceremonies aligning product, BA, engineering, and QA around shared outcomes
- Established BA and QA Centers of Excellence, standardizing requirements, test strategy, and release governance across accounts
- Implemented quality and accessibility frameworks that reduced defects by ~80% and accelerated roadmap delivery
- Partnered with client and agency leadership to position accessibility, performance, and quality as product differentiators, contributing to $45M+ in new business
- Scaled distributed product and engineering teams to 40+ members across the Americas, EMEA, and APAC while maintaining delivery excellence
- Increased Jira/Confluence adoption to ~85% and introduced custom project configurations, standardized boards, workflows, and reporting for product delivery
- Mentored product, BA, and QA leads, building a bench of future product and quality leaders within the organization

EDUCATION:
- Bachelor's Coursework in Computer Science – Bloomfield College, NJ | 2001
- Certified Cisco Networking Associate Program

CERTIFICATIONS:
- Accessibility Fundamentals Certificate – International Association of Accessibility Professionals (IAAP) | Expected 2026

CORE COMPETENCIES & SKILLS:
Product Strategy & Discovery: Product Vision • North Star framework • GIST planning • 4 Big Risks • Customer discovery & user research • JTBD • Road mapping • Prioritization (RICE, MoSCoW) • Business Model Canvas • Design Sprints • Customer Journey Mapping • AARRR & growth metrics • OKRs
Execution & Product Operations: Backlog management & release planning • Agile/Scrum product ownership • Cross-functional team leadership • Product Operations & Governance • Go-to-market strategy • Experimentation & A/B testing • Stakeholder management & executive communication • Vendor/partner management • P&L awareness
Tools & Technology: Jira (Professional Admin) • Confluence • Loom • Bitrix • ServiceNow • Figma • Miro • SmartSheets • Trello • GA/Adobe Analytics • SurveyMonkey • CI/CD-aware workflows • HTML/CSS/JS, React • Headless CMS • Email/martech tooling • AWS/Azure • Jenkins • Git • Bitbucket
Accessibility, Quality & AI (Superpowers): Accessible product design (WCAG 2.0/2.1/2.2, POUR) • Automated ADA Testing (AQA) • Screen readers (JAWS, NVDA, VoiceOver, TalkBack) • QA strategy & risk mitigation • Selenium • Cypress • Playwright • Postman • JMeter/BlazeMeter • ChatGPT • Claude • Perplexity • Copilot • Gemini • Midjourney • Rovo • Agentic AI & AI-assisted test design

JOB POSTING TO TAILOR FOR:
${jobPosting}

TAILORING RULES:
1. HEADLINE: Adjust to mirror the job title/seniority in the posting
2. SUMMARY: Full rewrite. Max 4-5 lines. Lead with most relevant identity. Mirror posting's priority language. No filler. Must be tight and punchy.
3. HIGHLIGHTS: Reorder to surface most relevant first. You may rewrite highlight bullets to better mirror posting language while keeping the same spirit and facts.
4. KEY DELIVERIES: Reorder most relevant first. Mirror posting vocabulary where it naturally fits. Never change the actual outcomes or numbers.
5. WORK HISTORY BULLETS: Same facts and outcomes, but mirror the posting's language and priorities where applicable. Do not change company names, titles, dates, or actual results.
6. CORE COMPETENCIES: Reorder within each subsection to front-load skills the posting calls out. Add specific tools/frameworks from the posting if Charles genuinely has them.
7. 3-PAGE RULE: Budget copy length carefully. Summary must not exceed 5 lines. Tighten bullet language if needed. Never cut jobs, sections, education, or certifications.

Return ONLY a JSON object with this exact structure — no preamble, no markdown fences:
{
  "headline": "string",
  "summary": "string",
  "highlights": ["string", "string", "string", "string"],
  "key_deliveries": [
    {"title": "string", "description": "string"},
    {"title": "string", "description": "string"},
    {"title": "string", "description": "string"},
    {"title": "string", "description": "string"},
    {"title": "string", "description": "string"},
    {"title": "string", "description": "string"}
  ],
  "crvtech_bullets": ["string", "string", "string", "string", "string"],
  "publicis_bullets": ["string", "string", "string", "string", "string", "string", "string", "string", "string", "string"],
  "valtech_bullets": ["string", "string", "string", "string", "string", "string", "string", "string"],
  "competencies": {
    "strategy": "string",
    "execution": "string",
    "tools": "string",
    "accessibility": "string"
  }
}`;

  const raw = await callClaude(apiKey, prompt);
  // Strip markdown fences if present
  const clean = raw.replace(/```json|```/g, "").trim();
  return JSON.parse(clean);
}

// ── Drop shadow effect (matches original) ─────────────────────────────────────
// Note: docx-js doesn't support w14:shadow natively so we approximate
// with the accent color styling which is the dominant visual element

// ── Build the Word document ───────────────────────────────────────────────────
async function buildDocument(content, outputPath) {
  console.log("📄 Building Word document...");

  // ── Color constants (extracted from original XML) ──────────────────────────
  const ACCENT_BLUE  = "156082";  // Section headers and name
  const BODY_BLACK   = "000000";  // Body text

  // ── Reusable style builders ────────────────────────────────────────────────
  const headerRun = (text) => new TextRun({
    text,
    bold: true,
    color: ACCENT_BLUE,
    font: "Aptos Display",
    size: 24
  });

  const nameRun = (text) => new TextRun({
    text,
    bold: true,
    color: ACCENT_BLUE,
    font: "Aptos Display",
    size: 36
  });

  const bodyRun = (text, opts = {}) => new TextRun({
    text,
    font: "Aptos",
    size: 24,
    bold: opts.bold || false,
    italics: opts.italics || false,
    color: BODY_BLACK
  });

  const smallRun = (text) => new TextRun({
    text,
    font: "Aptos",
    size: 22,
    color: BODY_BLACK
  });

  const blankLine = () => new Paragraph({
    children: [new TextRun({ text: "", font: "Aptos", size: 24 })],
    spacing: { after: 0 }
  });

  const sectionHeader = (text) => new Paragraph({
    children: [headerRun(text)],
    spacing: { after: 0 },
    border: {
      bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT_BLUE, space: 1 }
    }
  });

  const bulletPara = (text) => new Paragraph({
    children: [bodyRun(text)],
    spacing: { after: 0 },
    numbering: { reference: "bullets", level: 0 }
  });

  // ── Document children ──────────────────────────────────────────────────────
  const children = [];

  // Name
  children.push(new Paragraph({
    children: [nameRun("CHARLES VICKERS")],
    spacing: { after: 0 }
  }));

  // Headline
  children.push(new Paragraph({
    children: [bodyRun(content.headline)],
    spacing: { after: 0 }
  }));

  // Contact line
  children.push(new Paragraph({
    children: [
      smallRun("Bloomfield, NJ | 973.698.6714 | "),
      new ExternalHyperlink({
        link: "mailto:charlesvickers.2019@gmail.com",
        children: [new TextRun({
          text: "charlesvickers.2019@gmail.com",
          font: "Aptos", size: 22,
          style: "Hyperlink",
          underline: { type: UnderlineType.SINGLE }
        })]
      }),
      smallRun(" | "),
      new ExternalHyperlink({
        link: "http://www.linkedin.com/in/vickerscharles",
        children: [new TextRun({
          text: "www.linkedin.com/in/vickerscharles",
          font: "Aptos", size: 22,
          style: "Hyperlink",
          underline: { type: UnderlineType.SINGLE }
        })]
      })
    ],
    spacing: { after: 0 }
  }));

  children.push(blankLine());

  // SUMMARY
  children.push(sectionHeader("SUMMARY"));
  children.push(new Paragraph({
    children: [bodyRun(content.summary)],
    spacing: { after: 0 }
  }));

  children.push(blankLine());

  // HIGHLIGHTS
  children.push(sectionHeader("HIGHLIGHTS"));
  content.highlights.forEach(h => children.push(bulletPara(h)));

  children.push(blankLine());

  // KEY PRODUCT DELIVERIES
  children.push(sectionHeader("KEY PRODUCT DELIVERIES & IMPACT"));
  content.key_deliveries.forEach(d => {
    children.push(new Paragraph({
      children: [
        bodyRun(d.title + " – ", { bold: false }),
        bodyRun(d.description)
      ],
      spacing: { after: 0 },
      numbering: { reference: "bullets", level: 0 }
    }));
  });

  children.push(blankLine());

  // PROFESSIONAL EXPERIENCE
  children.push(sectionHeader("PROFESSIONAL EXPERIENCE"));
  children.push(blankLine());

  // CRVTech
  children.push(new Paragraph({
    children: [
      bodyRun("CRVTech LLC", { bold: true }),
      bodyRun(" - ", { bold: true }),
      bodyRun("Founder & Principal Consultant", { bold: true }),
      bodyRun(", Bloomfield, NJ", { bold: true }),
      bodyRun(" | Sept 2025 – Present", { bold: true })
    ],
    spacing: { after: 0 }
  }));
  content.crvtech_bullets.forEach(b => children.push(bulletPara(b)));

  children.push(blankLine());

  // Publicis
  children.push(new Paragraph({
    children: [
      bodyRun("Publicis Groupe (Rauxa / Razorfish)", { bold: true }),
      bodyRun(" - ", { bold: true }),
      bodyRun("Product Director", { bold: true }),
      bodyRun(", New York, NY", { bold: true }),
      bodyRun(" | Sept 2019 – Sept 2025", { bold: true })
    ],
    spacing: { after: 0 }
  }));
  content.publicis_bullets.forEach(b => children.push(bulletPara(b)));

  children.push(blankLine());

  // Valtech
  children.push(new Paragraph({
    children: [
      bodyRun("Valtech", { bold: true }),
      bodyRun(" - ", { bold: true }),
      bodyRun("Product Lead & Technology Director", { bold: true }),
      bodyRun(", New York, NY", { bold: true }),
      bodyRun(" | March 2014 – August 2019", { bold: true })
    ],
    spacing: { after: 0 }
  }));
  content.valtech_bullets.forEach(b => children.push(bulletPara(b)));

  children.push(blankLine());

  // EDUCATION
  children.push(sectionHeader("EDUCATION"));
  children.push(bulletPara("Bachelor's Coursework in Computer Science – Bloomfield College, NJ | 2001"));
  children.push(bulletPara("Certified Cisco Networking Associate Program"));

  children.push(blankLine());

  // CERTIFICATIONS
  children.push(sectionHeader("CERTIFICATIONS"));
  children.push(bulletPara("Accessibility Fundamentals Certificate – International Association of Accessibility Professionals (IAAP) | Expected 2026"));

  children.push(blankLine());

  // CORE COMPETENCIES
  children.push(sectionHeader("CORE COMPETENCIES & SKILLS"));
  children.push(blankLine());

  const competencySection = (label, content_text) => [
    new Paragraph({
      children: [bodyRun(label + ":", { bold: true })],
      spacing: { after: 0 }
    }),
    new Paragraph({
      children: [bodyRun(content_text)],
      spacing: { after: 0 }
    }),
    blankLine()
  ];

  competencySection("Product Strategy & Discovery", content.competencies.strategy)
    .forEach(p => children.push(p));
  competencySection("Execution & Product Operations", content.competencies.execution)
    .forEach(p => children.push(p));
  competencySection("Tools & Technology", content.competencies.tools)
    .forEach(p => children.push(p));
  competencySection("Accessibility, Quality & AI (Superpowers)", content.competencies.accessibility)
    .forEach(p => children.push(p));

  // ── Assemble document ──────────────────────────────────────────────────────
  const doc = new Document({
    numbering: {
      config: [{
        reference: "bullets",
        levels: [{
          level: 0,
          format: LevelFormat.BULLET,
          text: "\u2022",
          alignment: AlignmentType.LEFT,
          style: {
            paragraph: {
              indent: { left: 720, hanging: 360 }
            }
          }
        }]
      }]
    },
    styles: {
      default: {
        document: {
          run: { font: "Aptos", size: 24, color: BODY_BLACK }
        }
      }
    },
    sections: [{
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 720, right: 1080, bottom: 720, left: 1080 }
        }
      },
      children
    }]
  });

  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outputPath, buffer);
  console.log(`✅ Resume saved to: ${outputPath}`);
}

// ── Main ──────────────────────────────────────────────────────────────────────
async function main() {
  const jobPosting  = process.argv[2];
  const outputFile  = process.argv[3];

  if (!jobPosting || !outputFile) {
    console.error("Usage: node tailor_resume.js <job_posting_text> <output_filename>");
    process.exit(1);
  }

  // Ensure output directory exists
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }

  const outputPath = path.join(OUTPUT_DIR, outputFile);
  const apiKey     = loadApiKey();
  const profile    = fs.readFileSync(PROFILE, "utf8");

  try {
    const content = await getTailoredContent(apiKey, jobPosting, profile);
    await buildDocument(content, outputPath);
  } catch (err) {
    console.error("❌ Error:", err.message);
    process.exit(1);
  }
}

main();
