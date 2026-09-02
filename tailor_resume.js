#!/usr/bin/env node
/**
 * CRVTech Resume Tailor v0.8.0
 * Fixes: 3-page enforcement, summary length, drop shadow, filename role extraction
 *
 * Usage: node tailor_resume.js <posting_file_path> <output_filename>
 */

const {
  Document, Packer, Paragraph, TextRun,
  AlignmentType, LevelFormat,
  ExternalHyperlink, UnderlineType,
  XmlComponent, XmlAttributeComponent
} = require("docx");

const fs   = require("fs");
const path = require("path");
const http = require("https");

// ── Paths ─────────────────────────────────────────────────────────────────────
const BASE_DIR   = __dirname;
const ENV_FILE   = path.join(BASE_DIR, "config", ".env");
const PROFILE    = path.join(BASE_DIR, "profile.txt");
const OUTPUT_DIR = path.join(BASE_DIR, "data", "resumes");

// ── Color constants ────────────────────────────────────────────────────────────
const BLUE       = "156082";
const DARK_GRAY  = "404040";
const HYPERLINK  = "467886";
const BODY_BLACK = "000000";

// ── DXA helpers ───────────────────────────────────────────────────────────────
const IN = (n) => Math.round(n * 1440);
const PT = (n) => Math.round(n * 20);

// ── Line spacing 115% ─────────────────────────────────────────────────────────
const LINE_115 = { line: 276, lineRule: "auto" };

// ── Drop shadow XML (extracted from canonical resume) ─────────────────────────
// w14:shadow blurRad=38100 dist=25400 dir=5400000 color=#6E747A alpha=57%
// This is injected as raw XML into run properties since docx-js doesn't
// support w14:textFx natively
const SHADOW_XML = `<w14:textFx xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"><w14:shadow w14:blurRad="38100" w14:dist="25400" w14:dir="5400000" w14:sx="100000" w14:sy="100000" w14:kx="0" w14:ky="0" w14:algn="ctr"><w14:srgbClr w14:val="6E747A"><w14:alpha w14:val="57000"/></w14:srgbClr></w14:shadow><w14:textOutline w14:w="0" w14:cap="flat" w14:cmpd="sng" w14:algn="ctr"><w14:noFill/><w14:miter w14:lim="800000"/></w14:textOutline><w14:textFill><w14:solidFill><w14:srgbClr w14:val="156082"/></w14:solidFill></w14:textFill></w14:textFx>`;

// ── Load API key ───────────────────────────────────────────────────────────────
function loadApiKey() {
  const env   = fs.readFileSync(ENV_FILE, "utf8");
  const match = env.match(/ANTHROPIC_API_KEY=(.+)/);
  if (!match) throw new Error("ANTHROPIC_API_KEY not found in .env");
  return match[1].trim();
}

// ── Call Claude API ────────────────────────────────────────────────────────────
function callClaude(apiKey, systemPrompt, userPrompt) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({
      model:      "claude-sonnet-4-6",
      max_tokens: 4000,
      system:     systemPrompt,
      messages:   [{ role: "user", content: userPrompt }]
    });
    const options = {
      hostname: "api.anthropic.com",
      path:     "/v1/messages",
      method:   "POST",
      headers:  {
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

// ── Generate tailored content ──────────────────────────────────────────────────
async function getTailoredContent(apiKey, jobPosting, profile) {
  console.log("🧠 Generating tailored resume content...");

  const systemPrompt = `You are a resume tailoring engine. You output ONLY valid JSON.
You never explain yourself. You never ask questions. You never add commentary.
Your entire response must be a single valid JSON object and nothing else.
No markdown. No backticks. No preamble. No postamble. JSON only.`;

  const userPrompt = `Tailor Charles Vickers' resume for this job posting.

CHARLES'S PROFILE AND BACKSTORY:
${profile}

CANONICAL RESUME CONTENT:
Name: CHARLES VICKERS
Current Headline: Senior Product Manager / Product Director – CRM, CMS, Mobile & Commerce

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
- Acted as Atlassian Product Owner and SuperAdmin (ACP-120 Certified), standardizing Jira/Confluence projects, workflows and dashboards for visibility into roadmap, delivery, and risk
- Integrated AI tools into discovery, design, and testing workflows to improve team throughput by ~30%
- Partnered with account and sales leadership to craft product visions and ROI-backed roadmaps that helped secure $155M+ in new business
- Collaborated with engineering leads to shape technical approaches, sequence dependencies, and manage functional & non-functional requirements
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
- ACP-120: Jira Administration for Cloud – Atlassian Certified Professional | 2026
- Accessibility Fundamentals Certificate – International Association of Accessibility Professionals (IAAP) | Expected 2026

CORE COMPETENCIES & SKILLS:
Product Strategy & Discovery: Product Vision • North Star framework • GIST planning • 4 Big Risks • Customer discovery & user research • JTBD • Road mapping • Prioritization (RICE, MoSCoW) • Business Model Canvas • Design Sprints • Customer Journey Mapping • AARRR & growth metrics • OKRs
Execution & Product Operations: Backlog management & release planning • Agile/Scrum product ownership • Cross-functional team leadership • Product Operations & Governance • Go-to-market strategy • Experimentation & A/B testing • Stakeholder management & executive communication • Vendor/partner management • P&L awareness
Tools & Technology: Jira (ACP-120 Certified Administrator) • Confluence • Loom • Bitrix • ServiceNow • Figma • Miro • SmartSheets • Trello • GA/Adobe Analytics • SurveyMonkey • CI/CD-aware workflows • HTML/CSS/JS, React • Headless CMS • Email/martech tooling • AWS/Azure • Jenkins • Git • Bitbucket
Accessibility, Quality & AI (Superpowers): Accessible product design (WCAG 2.0/2.1/2.2, POUR) • Automated ADA Testing (AQA) • Screen readers (JAWS, NVDA, VoiceOver, TalkBack) • QA strategy & risk mitigation • Selenium • Cypress • Playwright • Postman • JMeter/BlazeMeter • ChatGPT • Claude • Perplexity • Copilot • Gemini • Midjourney • Rovo • Agentic AI & AI-assisted test design

JOB POSTING TO TAILOR FOR:
${jobPosting}

STRICT LENGTH RULES — these are hard constraints, not guidelines:
1. HEADLINE: One line only. Max 100 characters.
2. SUMMARY: MAX 3 SENTENCES. MAX 600 CHARACTERS TOTAL. Count carefully before submitting.
   Do not exceed this under any circumstances. Tight, punchy, no filler.
3. HIGHLIGHTS: Exactly 4 bullets. Each bullet max 120 characters.
4. KEY DELIVERIES: Exactly 6 bullets. Each delivery max 160 characters total (title + description).
5. CRVTECH BULLETS: Exactly 5 bullets. Each max 150 characters.
6. PUBLICIS BULLETS: Exactly 8 bullets. Each max 150 characters.
7. VALTECH BULLETS: Exactly 7 bullets. Each max 150 characters.
8. COMPETENCIES: Each competency string max 400 characters.
9. 3-PAGE HARD RULE: These limits exist to ensure the resume fits in 3 pages at 12pt Aptos
   with 0.5in margins. Do not exceed any limit above.

TAILORING RULES:
1. HEADLINE: Adjust to mirror the job title/seniority in the posting
2. SUMMARY: Full rewrite per length rules above. Lead with most relevant identity.
   Mirror posting's priority language. Never start with "I".
3. HIGHLIGHTS: Reorder most relevant first. Mirror posting language, keep same facts.
4. KEY DELIVERIES: Reorder most relevant first. Mirror posting vocabulary. Keep outcomes/numbers.
5. WORK HISTORY: Same facts and outcomes, mirror posting language. Keep company names, titles, dates.
6. CORE COMPETENCIES: Reorder to front-load skills the posting calls out.

Return a single valid JSON object:
{
  "headline": "string — max 100 chars",
  "summary": "string — max 3 sentences, max 600 chars total",
  "highlights": ["string max 120 chars", "string max 120 chars", "string max 120 chars", "string max 120 chars"],
  "key_deliveries": [
    {"title": "string", "description": "string — title+description max 160 chars total"},
    {"title": "string", "description": "string"},
    {"title": "string", "description": "string"},
    {"title": "string", "description": "string"},
    {"title": "string", "description": "string"},
    {"title": "string", "description": "string"}
  ],
  "crvtech_bullets": ["string max 150 chars", "string", "string", "string", "string"],
  "publicis_bullets": ["string max 150 chars", "string", "string", "string", "string", "string", "string", "string"],
  "valtech_bullets": ["string max 150 chars", "string", "string", "string", "string", "string", "string"],
  "competencies": {
    "strategy": "string max 400 chars",
    "execution": "string max 400 chars",
    "tools": "string max 400 chars",
    "accessibility": "string max 400 chars"
  }
}`;

  const raw = await callClaude(apiKey, systemPrompt, userPrompt);
  let clean = raw.trim()
    .replace(/^```json\s*/i, "").replace(/^```\s*/i, "").replace(/\s*```$/i, "");
  const start = clean.indexOf("{");
  const end   = clean.lastIndexOf("}");
  if (start === -1 || end === -1) {
    throw new Error("Claude did not return valid JSON. Raw: " + raw.substring(0, 200));
  }
  return JSON.parse(clean.substring(start, end + 1));
}

// ── Build the Word document ────────────────────────────────────────────────────
async function buildDocument(content, outputPath) {
  console.log("📄 Building Word document...");

  // ── Run builders ────────────────────────────────────────────────────────────

  // Name: 18pt, Aptos, #156082, not bold — with drop shadow via XML
  const nameRun = (text) => {
    const run = new TextRun({
      text,
      font:  "Aptos",
      size:  36,         // 18pt = 36 half-points
      color: BLUE,
      bold:  false
    });
    // Inject shadow XML into run properties
    run.properties = run.properties || {};
    const origPrepareXml = run.prepareXml ? run.prepareXml.bind(run) : null;
    run._shadow = true;
    return run;
  };

  // Section header: 12pt, Aptos, #156082, not bold — with drop shadow
  const headerTextRun = (text) => new TextRun({
    text,
    font:  "Aptos",
    size:  24,
    color: BLUE,
    bold:  false
  });

  // Body: 12pt, Aptos, black
  const bodyRun = (text, opts = {}) => new TextRun({
    text,
    font:    "Aptos",
    size:    24,
    bold:    opts.bold   || false,
    italics: opts.italic || false,
    color:   opts.color  || BODY_BLACK
  });

  // Contact: 11pt
  const smallRun = (text) => new TextRun({
    text, font: "Aptos", size: 22, color: BODY_BLACK
  });

  // Hyperlink
  const hyperlinkRun = (text, href) => new ExternalHyperlink({
    link: href,
    children: [new TextRun({
      text, font: "Aptos", size: 22, color: HYPERLINK,
      underline: { type: UnderlineType.SINGLE }
    })]
  });

  // Blank spacer
  const blankLine = () => new Paragraph({
    children: [new TextRun({ text: "", font: "Aptos", size: 24 })],
    spacing:  { after: 0, ...LINE_115 }
  });

  // Section header paragraph (no border, not bold, #156082)
  const sectionHeader = (text) => new Paragraph({
    children: [headerTextRun(text)],
    spacing:  { after: 0, ...LINE_115 }
  });

  // Bullet
  const bulletPara = (text) => new Paragraph({
    children: [bodyRun(text)],
    spacing:  { after: 0, ...LINE_115 },
    numbering: { reference: "bullets", level: 0 }
  });

  // Experience heading: bold, #404040, 6pt after
  const experienceHeading = (company, rest) => new Paragraph({
    children: [
      new TextRun({ text: company, font: "Aptos", size: 24, bold: true, color: DARK_GRAY }),
      new TextRun({ text: rest,    font: "Aptos", size: 24, bold: true, color: DARK_GRAY })
    ],
    spacing: { after: PT(6), ...LINE_115 }
  });

  // Competency label: 12pt, #156082, not bold
  const competencyLabel = (text) => new Paragraph({
    children: [new TextRun({ text, font: "Aptos", size: 24, color: BLUE, bold: false })],
    spacing:  { after: 0, ...LINE_115 }
  });

  // ── Build children array ───────────────────────────────────────────────────
  const children = [];

  // Name
  children.push(new Paragraph({
    children: [new TextRun({ text: "CHARLES VICKERS", font: "Aptos", size: 36, color: BLUE, bold: false })],
    spacing:  { after: 0, ...LINE_115 }
  }));

  // Headline
  children.push(new Paragraph({
    children: [bodyRun(content.headline)],
    spacing:  { after: 0, ...LINE_115 }
  }));

  // Contact
  children.push(new Paragraph({
    children: [
      smallRun("Bloomfield, NJ | 973.698.6714 | "),
      hyperlinkRun("charlesvickers.2019@gmail.com", "mailto:charlesvickers.2019@gmail.com"),
      smallRun(" | "),
      hyperlinkRun("www.linkedin.com/in/vickerscharles", "http://www.linkedin.com/in/vickerscharles")
    ],
    spacing: { after: 0, ...LINE_115 }
  }));

  children.push(blankLine());

  // SUMMARY
  children.push(sectionHeader("SUMMARY"));
  children.push(new Paragraph({
    children: [bodyRun(content.summary)],
    spacing:  { after: 0, ...LINE_115 }
  }));
  children.push(blankLine());

  // HIGHLIGHTS
  children.push(sectionHeader("HIGHLIGHTS"));
  content.highlights.forEach(h => children.push(bulletPara(h)));
  children.push(blankLine());

  // KEY PRODUCT DELIVERIES & IMPACT
  children.push(sectionHeader("KEY PRODUCT DELIVERIES & IMPACT"));
  content.key_deliveries.forEach(d => {
    children.push(new Paragraph({
      children: [bodyRun(d.title + " – "), bodyRun(d.description)],
      spacing:  { after: 0, ...LINE_115 },
      numbering: { reference: "bullets", level: 0 }
    }));
  });
  children.push(blankLine());

  // PROFESSIONAL EXPERIENCE
  children.push(sectionHeader("PROFESSIONAL EXPERIENCE"));
  children.push(blankLine());

  children.push(experienceHeading("CRVTech LLC", " - Founder & Principal Consultant, Bloomfield, NJ | Sept 2025 – Present"));
  content.crvtech_bullets.forEach(b => children.push(bulletPara(b)));
  children.push(blankLine());

  children.push(experienceHeading("Publicis Groupe (Rauxa / Razorfish)", " - Product Director, New York, NY | Sept 2019 – Sept 2025"));
  content.publicis_bullets.forEach(b => children.push(bulletPara(b)));
  children.push(blankLine());

  children.push(experienceHeading("Valtech", " - Product Lead & Technology Director, New York, NY | March 2014 – August 2019"));
  content.valtech_bullets.forEach(b => children.push(bulletPara(b)));
  children.push(blankLine());

  // EDUCATION
  children.push(sectionHeader("EDUCATION"));
  children.push(bulletPara("Bachelor's Coursework in Computer Science – Bloomfield College, NJ | 2001"));
  children.push(bulletPara("Certified Cisco Networking Associate Program"));
  children.push(blankLine());

  // CERTIFICATIONS
  children.push(sectionHeader("CERTIFICATIONS"));
  children.push(bulletPara("ACP-120: Jira Administration for Cloud – Atlassian Certified Professional | 2026"));
  children.push(bulletPara("Accessibility Fundamentals Certificate – International Association of Accessibility Professionals (IAAP) | Expected 2026"));
  children.push(blankLine());

  // CORE COMPETENCIES
  children.push(sectionHeader("CORE COMPETENCIES & SKILLS"));
  children.push(blankLine());

  const competencyBlock = (label, text) => [
    competencyLabel(label + ":"),
    new Paragraph({ children: [bodyRun(text)], spacing: { after: 0, ...LINE_115 } }),
    blankLine()
  ];

  competencyBlock("Product Strategy & Discovery",              content.competencies.strategy).forEach(p => children.push(p));
  competencyBlock("Execution & Product Operations",            content.competencies.execution).forEach(p => children.push(p));
  competencyBlock("Tools & Technology",                        content.competencies.tools).forEach(p => children.push(p));
  competencyBlock("Accessibility, Quality & AI (Superpowers)", content.competencies.accessibility).forEach(p => children.push(p));

  // ── Assemble ───────────────────────────────────────────────────────────────
  const doc = new Document({
    numbering: {
      config: [{
        reference: "bullets",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "\u2022",
          alignment: AlignmentType.LEFT,
          style: {
            paragraph: { indent: { left: 720, hanging: 360 }, spacing: { after: 0, ...LINE_115 } }
          }
        }]
      }]
    },
    styles: {
      default: {
        document: { run: { font: "Aptos", size: 24, color: BODY_BLACK } }
      }
    },
    sections: [{
      properties: {
        page: {
          size:   { width: IN(8.5), height: IN(11) },
          margin: { top: IN(0.5), right: IN(0.5), bottom: IN(0.5), left: IN(0.5) }
        }
      },
      children
    }]
  });

  // ── Inject drop shadow XML via post-processing ─────────────────────────────
  // Pack to buffer first, then inject shadow into name + section header runs
  const buffer = await Packer.toBuffer(doc);

  // Write to temp file, unzip, inject, rezip
  const tmpDir  = path.join(OUTPUT_DIR, "_tmp_build");
  const tmpDocx = path.join(OUTPUT_DIR, "_tmp.docx");
  fs.writeFileSync(tmpDocx, buffer);

  const { execSync } = require("child_process");

  // Unzip
  if (fs.existsSync(tmpDir)) execSync(`rm -rf "${tmpDir}"`);
  fs.mkdirSync(tmpDir, { recursive: true });
  execSync(`cd "${tmpDir}" && unzip -q "${tmpDocx}"`);

  // Read document.xml
  const docXmlPath = path.join(tmpDir, "word", "document.xml");
  let docXml = fs.readFileSync(docXmlPath, "utf8");

  // Add w14 namespace to root element if not present
  if (!docXml.includes("xmlns:w14=")) {
    docXml = docXml.replace(
      '<w:document ',
      '<w:document xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
    );
  }

  // Inject shadow into runs that have color 156082 (name + section headers)
  // We target <w:color w:val="156082"/> and add the w14:textFx right after the rPr closing tag
  // Strategy: find each <w:rPr>...</w:rPr> that contains color 156082 and inject shadow
  docXml = docXml.replace(
    /(<w:rPr>(?:(?!<\/w:rPr>)[\s\S])*?<w:color w:val="156082"\/>(?:(?!<\/w:rPr>)[\s\S])*?<\/w:rPr>)/g,
    (match) => {
      // Only add if not already present
      if (match.includes("w14:textFx")) return match;
      return match.replace(
        "</w:rPr>",
        `</w:rPr><w14:textFx><w14:shadow w14:blurRad="38100" w14:dist="25400" w14:dir="5400000" w14:sx="100000" w14:sy="100000" w14:kx="0" w14:ky="0" w14:algn="ctr"><w14:srgbClr w14:val="6E747A"><w14:alpha w14:val="57000"/></w14:srgbClr></w14:shadow><w14:textOutline w14:w="0" w14:cap="flat" w14:cmpd="sng" w14:algn="ctr"><w14:noFill/><w14:miter w14:lim="800000"/></w14:textOutline><w14:textFill><w14:solidFill><w14:srgbClr w14:val="156082"/></w14:solidFill></w14:textFill></w14:textFx>`
      );
    }
  );

  fs.writeFileSync(docXmlPath, docXml);

  // Rezip
  fs.unlinkSync(tmpDocx);
  execSync(`cd "${tmpDir}" && zip -qr "${outputPath}" .`);

  // Cleanup
  execSync(`rm -rf "${tmpDir}"`);

  console.log(`✅ Resume saved to: ${outputPath}`);
}

// ── Main ───────────────────────────────────────────────────────────────────────
async function main() {
  const postingFile = process.argv[2];
  const outputFile  = process.argv[3];

  if (!postingFile || !outputFile) {
    console.error("Usage: node tailor_resume.js <posting_file_path> <output_filename>");
    process.exit(1);
  }

  if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  const outputPath = path.join(OUTPUT_DIR, outputFile);
  const apiKey     = loadApiKey();
  const profile    = fs.readFileSync(PROFILE, "utf8");
  const jobPosting = fs.readFileSync(postingFile, "utf8");

  try {
    const content = await getTailoredContent(apiKey, jobPosting, profile);

    // Log lengths for debugging
    console.log(`📏 Summary: ${content.summary.length} chars`);
    console.log(`📏 Bullets: CRVTech=${content.crvtech_bullets.length} Publicis=${content.publicis_bullets.length} Valtech=${content.valtech_bullets.length}`);

    await buildDocument(content, outputPath);
  } catch (err) {
    console.error("❌ Error:", err.message);
    process.exit(1);
  }
}

main();
