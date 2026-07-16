# ApplyPilot — User Guide

Welcome to ApplyPilot! This guide walks you through every feature so you can get the most out of your AI-powered job search co-pilot.

## Table of Contents

- [Getting Started](#getting-started)
- [Profile Setup](#profile-setup)
- [Dashboard Overview](#dashboard-overview)
- [Creating Applications](#creating-applications)
- [Chrome Extension](#chrome-extension)
- [Interview Preparation](#interview-preparation)
- [Mock Session](#practice-interview)
- [Hiring Outreach](#hiring-outreach)
- [CV Optimization](#cv-optimization)
- [Career Tools](#career-tools)
- [Settings](#settings)
- [CLI](#cli)
- [FAQ](#faq)

---

## Getting Started

### Creating an Account

1. Navigate to the app homepage (`http://localhost:8000` for a local install)
2. Click **Try Free** in the top navigation
3. Choose your signup method:
   - **Email/Password** — enter your full name, email, and a password, then click **Create Account**
   - **Continue with Google** — one-click signup (only visible if Google OAuth is configured by the instance operator)

**Password Requirements:**
- Minimum 8 characters
- At least one uppercase letter, one lowercase letter, one number, one special character

### Email Verification

After creating an account, you may be asked to verify your email:

- If SMTP is configured, check your inbox for a **6-digit verification code**, enter it on the verification page, then click **Verify**. If you don't receive the code, click **Resend Code**.
- If email verification is disabled (the default for local installs), your account is verified automatically and you are redirected straight to profile setup.

### Signing In

1. Click **Sign In** in the top navigation
2. Enter your email and password, then click **Sign In** — or click **Continue with Google**
3. You'll be redirected to the dashboard (or profile setup if your profile isn't complete yet)

**Account Lockout:** After 5 failed login attempts your account is locked for 15 minutes.

---

## Profile Setup

Your profile is the foundation for all AI-generated content. The setup wizard has 5 steps.

### Quick Start: Resume Upload (Recommended)

1. Drag & drop your resume or click to browse
2. Supported formats: **PDF**, **DOCX**, **TXT**
3. The AI extracts your information and pre-fills all fields
4. Review and edit as needed, then click **Continue**

Click "Fill in manually" to skip the upload and enter everything by hand.

### Step 1: Basic Information

| Field | Required |
|-------|----------|
| City, State/Region, Country | Yes |
| Professional Title | Yes |
| Years of Experience | Yes |
| Professional Summary | Yes |
| Currently a Student | No |

**Years of experience** accepts **0** — use it if you are a student, changing careers, or have not yet worked in your field (the app stores this as a number; it is not treated as “empty”).

### Step 2: Work Experience

1. Click **Add Work Experience**
2. Enter company name, job title, and dates
3. Describe your responsibilities and achievements
4. Mark as current position if applicable
5. Add multiple roles as needed

**Either / or:**

- **You have experience:** leave the checkbox unchecked and add **at least one** role (company, job title, and start date are required per entry).
- **You do not have relevant experience yet:** check **"I don't have any relevant work experience yet"**. That saves your choice so this step counts as complete—you do not need to add a placeholder job. Leaving the step empty without checking the box is not valid.

The app stores an empty work history when that box is checked so **Complete Setup** and profile completion on the server can succeed.

### Step 3: Education

1. Click **Add Education** for each school or program
2. Enter institution, degree, field of study, and start date (month and year)
3. Add an end or graduation date, or mark **Currently enrolled** if you are still in school
4. Add multiple entries as needed

**Either / or:**

- **You have formal education:** add **at least one** complete entry (institution, degree, field of study, and start date are required; add an end date unless you mark **Currently enrolled**).
- **You have no formal education to list:** check **"I don't have formal education to add"**. That saves an empty education list so this step counts as complete—you do not need to add a placeholder school.

### Step 4: Skills

- Type a skill and press **Enter** to add it
- Add both technical skills (Python, SQL) and personal skills (Leadership, Communication)
- Aim for 5–10 relevant skills for better match accuracy
- Click the **×** to remove a skill

### Step 5: Career Preferences

| Field | Options |
|-------|---------|
| Salary | Minimum Salary and Maximum Salary (both optional) |
| Job Types | Full-time, Part-time, Contract, Freelance, Internship |
| Company Sizes | Startup (1–10), Small (11–50), Medium (51–200), Large (201–1000), Enterprise (1000+) |
| Work Arrangements | Onsite, Remote, Hybrid |
| Maximum Travel | No travel (0%), Minimal (up to 25%), Moderate (up to 50%), Frequent (up to 75%), Extensive (up to 100%) |
| Work authorization | Required — choose the status that applies to you today (used for screening questions on application forms) |
| Additional Options | Willing to relocate, Needs visa sponsorship, Has security clearance |

**Work authorization** and **visa sponsorship** drive how **Match Form To Profile** answers employer screening questions (for example “authorized to work” and “require sponsorship”). Set them accurately; the extension uses these values before any AI guess.

Your uploaded **resume** (PDF, DOCX, or TXT on the first setup step) can be attached automatically to resume file fields when you use the extension.

Click **Complete Setup** to finish.

---

## Dashboard Overview

The dashboard is your central hub for tracking applications and accessing all features.

### Statistics Cards

| Metric | Description |
|--------|-------------|
| Total Applications | All jobs added (visible on your dashboard) |
| Applied | Applications you've moved into the funnel — counts **Applied**, **Interview**, **Offer**, and **Rejected** tracking stages |
| Interviews | Applications where you've marked **Interview** |
| Response Rate | Share of tracked applications with an employer outcome: **(Interview + Offer + Rejected) ÷ (Applied + Interview + Offer + Rejected)**. Analysis-only cards (no tracking stage yet) are excluded. **Applied** is in the denominator but not the numerator. |

### Applications List

All your applications are listed here with company name, job title, match score, and status. Click any card to open the full application detail page.

**Unknown employer** — Some postings do not name a company (for example confidential or founding-team roles). If the AI cannot extract a real employer, or it only returns a placeholder such as a dash or “N/A”, the card and the application detail header show **Unknown** instead of punctuation. Analysis and company research still run using the job text and role context.

**Filter bar:**
- **Search** — filter by job title or company name
- **Date** — show applications from the last day, week, month, quarter, or year
- **Status** — filter by Applied, Interview, Offer, or Rejected
- **Sort** — order by newest, oldest, recently updated, company A–Z, or title A–Z

**On each card (3-row layout):**
- **Row 1** — job title (left) + AI analysis badge (right): `Analyzing…` while the AI works, `✓ Ready` when complete, `Failed` if something went wrong
- **Row 2** — company name
- **Row 3** — date and match score (left) + tracking stage buttons + trash icon (right)

**Tracking stage buttons** (Applied / Interview / Offer / Rejected):
- Click a button to mark where you are in the application process — it highlights immediately
- Click the **same button again** to undo it (clears the stage back to untracked)
- Only visible once the AI analysis is complete

**Trash icon** — always visible on the right side of the bottom row; click to delete the application (a confirmation dialog appears first)

**Analysis ready notification** — if an analysis completes while you're on another page (Career Tools, New Application, etc.), a small pulsing dot appears on the "← Back to Dashboard" button in the navbar. The dot disappears once you return to the dashboard.

---

## Creating Applications

### Starting a New Application

1. Click **New Application** from the dashboard
2. Provide the full job description using one of two methods:

| Method | How |
|--------|-----|
| **Paste Job Description** | Copy and paste the full job description text |
| **Upload File** | PDF, TXT, or Word (.docx) up to 5 MB |

The AI extracts the company name, job title, and all requirements from the text — you don't need to enter them manually. If the posting omits the employer, you may see **Unknown** as the company name after analysis; that is expected.

**Duplicate job** — If you already have an application for the same role at the same employer, the app will not add a second copy. You might see this immediately when submitting, or as a dashboard notification (**Duplicate job — not added**) if the overlap is detected after the job title and company are inferred from the description.

> **Tip:** The Chrome extension can **Analyze This Job** from a posting page (one click, no paste step) or **Match Form To Profile** on an application form. See the [Chrome Extension](#chrome-extension) section below.

### The Analysis Process

After submitting, five AI agents run across four steps with a gate check mid-way:

| Step | Agent |
|------|-------|
| 1 | **Job Analyzer** — extracts requirements, skills, qualifications |
| 2 | **Profile Matcher** — calculates match score, flags strengths and gaps |
| — | **Gate check** — if score < 50%, asks if you want to continue |
| 3 | **Company Research** — gathers company culture and hiring practices |
| 4 | **Resume Advisor + Cover Letter Writer** (run in parallel) |

**Total:** ~30 seconds

**Optional:** The **Interview Prep** agent runs separately, on demand from the Interview tab. It is not part of the main workflow and does not run automatically.

The **CV Optimizer** also runs on demand from the **Optimize CV** tab after the workflow completes. See [CV Optimization](#cv-optimization).

The **Mock Session** tab runs a timed conversational mock session (HR / Pro / Manager) using your API key. See [Mock Session](#practice-interview).

The **Outreach** tab finds hiring contacts from public web sources and drafts copy-ready outreach messages you send yourself. See [Hiring Outreach](#hiring-outreach).

### Viewing Results

The application details page opens with a **10-tab layout**. When a posting URL was saved (for example from the Chrome extension), the page header shows a **View posting** link that opens the original listing in a new tab. If the job lists multiple office locations, the header location line shows them separated by **|** (primary city first, then additional offices).

| Tab | Content |
|-----|---------|
| **Company** | Overview, culture, values, leadership, hiring practices |
| **Your Fit** | Match score, strengths, skill gaps, deal-breaker analysis |
| **Strategy** | Positioning strategy, key selling points to emphasize |
| **Job Details** | Extracted requirements, salary, work arrangement, and all listed office locations |
| **Cover Letter** | Personalized letter ready to copy |
| **Resume** | 4 sub-tabs: Overview, Experience, Keywords & ATS, Summary |
| **Interview** | 3 sub-tabs: Process, Questions, Preparation |
| **Optimize CV** | Iterative AI CV optimization loop — optimized CV, cover letter, gap analysis |
| **Mock Session** | Timed conversational practice (HR / Pro / Manager) with voice or typed answers |
| **Outreach** | Public web contact suggestions and copy-ready email / short-message drafts (no send integration) |

The **Cover Letter** tab has a **Copy** button. The Cover Letter, Resume, and Interview tabs each have a **Regenerate** button (rate limited to 5/hour).

> **Note:** If you turned off **Auto-generate documents** in Settings → Preferences before running this application, the Cover Letter and Resume tabs will show a **"Generate Cover Letter & Resume Tips"** button instead of content. Click it to run the generation on demand — it takes ~30 seconds and refreshes automatically when done.

### Managing Applications

**Stage tracking** — use the **Applied / Interview / Offer / Rejected** buttons in the bottom-right of each card to record where you are in the process. Click a highlighted button again to undo it. Changes take effect immediately.

**Deletion** — click the trash icon on the right side of any card's bottom row. A confirmation dialog appears before anything is deleted.

---

## Chrome Extension

The extension adds two actions from your toolbar: **Analyze This Job** sends the visible posting to your dashboard for the full AI workflow, and **Match Form To Profile** suggests values into open fields from your profile (you review before submitting). Both work while browsing job pages and company careers sites.

### Installation

The extension loads directly from this repository — no app store required.

1. Open `chrome://extensions` in Chrome
2. Enable **Developer Mode** (top-right toggle)
3. Click **Load unpacked** and select the `extension/` folder from the project directory
4. The ApplyPilot icon will appear in your toolbar

After any code change, click the ↺ refresh icon on the extension card.

### Using the Extension — Analyze This Job

1. Browse to a job posting page (detail view with the description visible)
2. Click the ApplyPilot icon in the toolbar
3. Click **Analyze This Job** — the page content is extracted and sent for analysis
4. When complete, use **Open Dashboard** in the popup to see the results

### Using the Extension — Match Form To Profile

1. Browse to an application form with visible fields (main page only in the current release)
2. Click the ApplyPilot icon in the toolbar
3. Click **Match Form To Profile** — the extension scrolls long forms to reveal hidden questions, scans labels and dropdown options, and sends them to the server with your profile
4. The server returns field assignments: an AI map merged with **deterministic profile rules** (name, contact, work authorization, visa sponsorship, country, location, education, and common screening questions). Values are written into the page for you to review and edit before you submit
5. Requires the same login, **completed profile** (including work authorization), and API access as dashboard analyses. If some fields fail, the popup shows how many succeeded and failed — always review before submitting

**Reliable without AI guesswork:** full name, email, phone, work authorization Yes/No, visa sponsorship Yes/No, country, and many acknowledgement dropdowns — when your profile has the matching data.

**Resume file fields:** if you uploaded a resume during Profile Setup, the extension attempts to attach it after text fields are filled.

### Supported Sites

The extension has optimized content selectors for many employer career sites and application platforms. For any unrecognized site it falls back to the page's main content area — this works on virtually any company careers page.

### Tips

- If extraction fails, try navigating directly to the job description page before clicking the icon
- You must be logged into the web app for the extension to work — it uses the same account
- Analyzed jobs appear in your dashboard immediately
- **Match Form To Profile** runs on the main document only; nested iframes are not scanned in the current release
- After updating the extension code, reload it at `chrome://extensions` before testing again
- Open DevTools on the application tab and filter the console for `ApplyPilot` to see scan/apply debug details when troubleshooting

---

## Interview Preparation

Interview prep is generated on demand and lives directly inside the application details page.

### Accessing Interview Prep

1. Open any completed application's detail page
2. Click the **Interview** tab
3. Click **Generate Interview Prep** (first time only)
4. Wait ~30–60 seconds for generation
5. Click **Regenerate** to refresh content (5/hour rate limit)

### What's Included

Content is organized across the three sub-tabs:

**Process** — typical interview rounds for this company, estimated timeline, and format prediction

**Questions** — behavioral questions with STAR answer frameworks built from your profile, technical and role-specific questions, company-specific questions, and smart questions to ask the interviewer

**Preparation** — quick reference card (elevator pitch, key selling points, salary discussion), how to address employer concerns, logistics (dress code, what to bring, virtual interview tips), a day-before checklist, and confidence boosters

---

## Mock Session

Practice a timed conversational mock interview grounded in this application's job analysis, company research, and your profile. Uses your own API key (Settings → AI Setup).

### Accessing Mock Session

1. Open a completed application's detail page
2. Click the **Mock Session** tab (after Interview)
3. Choose style (**HR — screening**, **Pro — peer technical**, or **Manager — hiring manager**) and length (**10**, **15**, or **20** minutes)
4. Click **Start mock session** (STAR follow-ups are always on)
5. Answer by typing (**Enter** to send, **Shift+Enter** for a new line) or using the mic (auto-sends after a short pause)
6. While the question is composing, you may see **Loading…** as it streams in; speech plays when the full line is ready
7. Use **Replay question** / **Mute this question** in the session bar; **More** holds **End early** (confirms then scores) and **Abort** (no score). If you End early while an answer is still processing, ApplyPilot waits for that answer, then scores.
8. Coaching tips appear under your answer box. Conversation can be hidden/shown. When time runs out (or you End early) with text still in the answer box, ApplyPilot includes that draft in your debrief. The debrief shows an overall summary, score dimensions with short explanations, strengths/improvements, and a stronger sample answer for each turn you gave (with Copy).

Optional interview prep content from the Interview tab is used when available to steer questions. Practice is a live conversation — different from the static **Interview** tab guide.

Voice uses free browser APIs (no audio uploaded to ApplyPilot). The mic pauses while the interviewer is speaking so it does not capture TTS. Typed answers always work if mic/speech is unavailable.

---

## Hiring Outreach

After you apply, the **Outreach** tab helps you find people who may be involved in hiring for this role and drafts personalized messages you can copy and send yourself. ApplyPilot searches **public web sources only** (company websites, news, team pages) — not professional networking profile sites.

### Accessing Outreach

1. Open a completed application's detail page (job analysis must be finished)
2. Click the **Outreach** tab (after Mock Session)
3. Confirm your API key is set in **Settings → AI Setup**
4. Click **Find contacts & draft messages**
5. Review contact cards (name, title, confidence) and copy email or short-message drafts with the **Copy** buttons

If no credible public contacts are found, ApplyPilot still provides generic outreach drafts you can adapt. Regenerate replaces the previous result (`regenerate=true`). Rate limit: **5 generations per hour**.

**Copy-only:** ApplyPilot does not send messages or open external apps — you paste drafts into your own email client or messaging tool.

---
## CV Optimization

The **CV Optimizer** runs an iterative AI loop tailored to a specific job application. An AI hiring manager scores your CV against the job description; an AI applicant revises it based on the feedback; the cycle repeats until the fit score converges. When the loop finishes, ApplyPilot generates a final optimized CV and a matching cover letter.

### Accessing CV Optimization

1. Open a **completed** application's detail page (the main workflow must be finished)
2. Click the **Optimize CV** tab — the setup screen matches the Cover Letter and Resume tabs (centered icon, description, and **Start Optimization** button)
3. Choose **Max Iterations** (2–7; default 5) and **Stop at score** (7.0–9.5; default 8.5)
4. Click **Start Optimization** — the setup panel hides and live progress appears
5. Watch each iteration — hiring-manager score and feedback update in real time
6. When complete, review the **Optimized CV**, **Cover Letter**, **Gap Analysis**, and **Iteration History**

If the loop stops early because of API quota, ApplyPilot saves the best CV reached so far. A notice banner explains what happened; if the cover letter could not be generated, that section shows a clear empty state instead of error text.

### Requirements

- A **provider + API key** in **Settings → AI Setup** (Gemini, OpenAI, or Anthropic), or **Ollama** with no key, or Vertex AI if your instance operator enabled it
- A **completed workflow** for that application — if document generation was skipped, finish the workflow from the Cover Letter or Resume tab first

### Output and actions

- **Copy** — optimized CV or cover letter to clipboard
- **Download CV** — formatted Word (``.docx``) or OpenDocument (``.odt`` when LibreOffice is on the server). Rate limits and API quota errors show as on-screen toasts (not a silent markdown download).

#### CV export — how it works

ApplyPilot converts your optimized CV markdown into a formatted document on the **server**. End users never install anything locally.

| Server setup | Export path | Quality |
|---|---|---|
| **LibreOffice installed** (Docker image, most production deploys) | Gemini HTML → HTML normalizer → LibreOffice → **`.odt`** | Best — full layout engine; bullets rendered as paragraph lines to avoid duplicate list items in LibreOffice |
| **No LibreOffice** (e.g. bare `make dev` on macOS) | Structured **Word `.docx`** (`python-docx`) | Real Word bullets — classic résumé layout |

**Docker / `docker compose up`:** LibreOffice is included automatically (`libreoffice-writer` in the Dockerfile). No extra setup.

**Local dev without Docker:** downloads are **`.docx`** (Word) — same structure as a professional résumé (section headers, title/company lines, bullet lists). For **`.odt`** locally, install LibreOffice:

```bash
brew install --cask libreoffice   # macOS
```

Then restart the dev server — downloads use the Gemini + HTML normalizer + LibreOffice path when `soffice` is detected.

- **Re-run** — clear the current result and start a fresh optimization (not available while a run is in progress)

Rate limits: **10 optimization runs per hour** per user, **10 CV downloads per hour**. The loop typically takes several minutes depending on iteration count and API latency.

### Generate Resume Tips (same application page)

From the **Resume** tab, **Generate Resume Tips** runs the Resume Advisor on demand. If generation fails (rate limit, quota, or other API error), ApplyPilot shows a toast and returns to the empty “Generate Resume Tips” screen — it does not display raw error JSON in the tab.


---

## Career Tools

Access six AI-powered tools at **Dashboard → Career Tools**.

### Thank You Note Generator

Generate professional post-interview thank-you emails.

**Input:** Interviewer name/role, interview type, company, job title, key discussion points (optional)  
**Output:** Subject line, email body, key points referenced

### Rejection Analysis

Turn rejection emails into learning opportunities.

**Input:** Rejection email text, job title/company (optional), interview stage reached  
**Output:** Likely rejection reasons, improvement suggestions, follow-up template, encouragement message

### Reference Request Generator

Create professional emails asking for references.

**Input:** Reference name/relationship, company you worked at together, target job (optional)  
**Output:** Subject line, email body, talking points reminder, follow-up timeline, tips

### Job Comparison Tool

Compare 2–3 job opportunities side by side.

**Input:** 2–3 job descriptions with details, your career priorities (optional)  
**Output:** Overall scores, category breakdown (compensation, growth, balance, culture, fit), pros/cons, recommendation

### Follow-up Email Generator

Generate follow-up emails for any application stage.

| Stage | When to use |
|-------|-------------|
| After Phone Screen | Thank you and reaffirm interest |
| After Interview | Strengthen your candidacy |
| After Final Round | Strong close |
| No Response | Gentle check-in |
| After Rejection | Maintain the relationship |

**Output:** Subject line, email body, timing advice, next steps

### Salary Negotiation Coach

Comprehensive preparation for salary negotiations.

**Input:** Job title/company, offered salary, your experience, current salary and competing offers (optional), target range  
**Output:** Market assessment, strategy overview, negotiation script, pushback responses, alternative asks (signing bonus, equity, PTO), email template, do's and don'ts

**Rate limit:** 5/hour (all other career tools are 10/hour)

---

## Settings

Access settings from the dashboard navigation. The settings page has five tabs.

### Profile

Edit your basic information, work experience, skills, and career preferences.

### AI Setup

Each user picks an AI provider and adds their own API key (bring-your-own-key). Local Ollama needs no key. Vertex AI is only available when the instance operator enables it server-side.

1. Go to **Settings → AI Setup**
2. Choose a provider: **Google Gemini**, **OpenAI**, **Anthropic**, or **Ollama (local)**
3. For cloud providers, open the linked **Get API Key** page, create a key, paste it, and click **Save**
4. Pick a preferred model (defaults to the recommended model for that provider)

Your keys are encrypted at rest and never logged or exposed. Switching provider clears any previously saved preferred model so you don’t keep a model id from another vendor.

**Model selection** — after a key is saved (or Ollama is selected), the recommended model is selected automatically. Defaults: Gemini `gemini-3.5-flash`, OpenAI `gpt-5.6-luna`, Anthropic `claude-sonnet-5`, Ollama `qwen3.6`. Only change this if you have a specific reason — different models have different speed, cost, and quality trade-offs.

**Key pages:** [Google AI Studio](https://aistudio.google.com/app/apikey) · [OpenAI API keys](https://platform.openai.com/api-keys) · [Anthropic console](https://console.anthropic.com/settings/keys) · Ollama: `ollama pull <model>` on the server.

### Preferences

All preferences auto-save — there is no Save button:

- **Minimum match threshold** — the score below which the gate check pauses the workflow (default: 50%)
- **Auto-generate documents** — toggle whether cover letter and resume tips generate automatically. When off, the workflow stops after job analysis and company research (faster). You can generate the documents later from the Cover Letter or Resume tab using the **"Generate Cover Letter & Resume Tips"** button.
- **Cover letter tone** — Professional, Conversational, or Enthusiastic
- **Resume advice style** — Concise or Detailed

### Privacy

- **Export Your Data** — download your profile, applications, and settings as JSON
- **Help & Support** — opens the help page or re-runs the onboarding tour

### Account

- **Password** — change your password (shown for email-registered users only)
- **Clear Applications** — delete all applications and AI results, keeping your account and profile
- **Delete Account** — permanently delete everything

---

## CLI

The **ApplyPilot CLI** (`applypilot`) talks to the same API as the web app and Chrome extension.

**Installed with the app:** `make setup`, `make start-local`, and `just setup` all run `pip install -e ".[cli]"` — no separate install step. Use `venv/bin/applypilot` or activate the venv (`source venv/bin/activate`).

### Setup

1. Start the server (`make start-local`, `make dev`, or Docker).
2. Run `applypilot doctor` to verify connectivity.
3. Log in: `applypilot auth login` — or paste a browser JWT with `applypilot auth token set` (Google OAuth users).
4. For automation, prefer a long-lived token: `applypilot auth token create --name "My script" --save` (requires an existing login).
5. Check profile completion: `applypilot profile status`.

Config is stored in `~/.applypilot/` (server URL in `config.toml`, credentials in `credentials.json` — JWT or personal access token).

Use `applypilot config` to view settings; `applypilot config set --base-url URL` to change the server. Long human output uses your `$PAGER`; pass `--no-pager` to print everything directly.

### Common tasks

| Task | Command |
|------|---------|
| Analyze a job posting | `applypilot workflow analyze posting.txt --wait` |
| Stream workflow progress | `applypilot workflow watch SESSION_ID` |
| Export cover letter to file | `applypilot workflow results SESSION_ID --section cover-letter --out letter.md` |
| List applications | `applypilot apps list` |
| Application summary + session link | `applypilot apps show APP_ID` |
| Interview prep | `applypilot interview generate SESSION_ID --wait` |
| Optimize CV | `applypilot cv start SESSION_ID --wait` |
| Thank-you email | `applypilot tools thank-you --file request.json` |
| Salary negotiation | `applypilot tools salary-coach --file offer.json` |
| Create automation token | `applypilot auth token create --name LABEL --save` |

Use `--format json` when piping output to scripts or AI tools. Global flags (`--base-url`, `--format`) go **before** the subcommand.

Full reference: **[docs/cli-reference.md](../docs/cli-reference.md)** (includes shell alias recipes)

---

## FAQ

### General

**Q: How accurate is the profile match score?**  
A: The match score is a useful signal, not a definitive verdict. It's calculated by the Profile Matcher agent, which compares your profile against the job's stated requirements across four dimensions:

- **Skills and technologies** — your listed skills are checked against what the job explicitly requires vs. what it lists as "nice to have." Required skills carry more weight. Gaps in required skills pull the score down more than gaps in preferred ones.
- **Years of experience** — your total career length and the tenure at your most recent role are compared against the job's stated minimums and preferred experience range.
- **Location and work arrangement** — your preferred arrangements (remote, hybrid, on-site) and location are compared to the job's stated requirements. A mismatch here can lower the score even if everything else aligns well.
- **Seniority alignment** — signals like "Senior," "Lead," "Staff," or "Entry-level" in the job title and description are compared against your years of experience and current professional title.

A high score (>75%) means you meet most stated requirements — worth applying confidently. A moderate score (50–75%) means gaps exist but the role may still be reachable — read the **Strategy** tab for how to address them. A low score (<50%) is a signal to reconsider whether the role is right for your current profile.

The score improves with a more complete profile — sparse profiles, especially those with no work experience or skills listed, produce less reliable matching. You can also configure the minimum threshold at which the workflow pauses and asks you to confirm in **Settings → Preferences** (default: 50%).

**Q: Can I apply to low-match jobs?**  
A: Yes. If the score is below 50% the gate decision appears, but you can always click "Continue Anyway." A low score just means you may need to address some gaps in your materials.

**Q: Why does the analysis take ~30 seconds?**  
A: Five AI agents run across four steps — the last two (Resume Advisor and Cover Letter Writer) run in parallel. Each makes an API call to your chosen provider. This is by design.

### API Keys

**Q: Do I need my own API key?**  
A: Yes for Gemini, OpenAI, and Anthropic — add it under **Settings → AI Setup**. Ollama needs no key. If the operator enabled **Vertex AI** on the server, you don’t need a personal key.

**Q: Is my API key secure?**  
A: Yes. Keys are encrypted at rest using Fernet symmetric encryption and are never logged or returned by the API.

**Q: Where do I get an API key?**  
A: Gemini — [Google AI Studio](https://aistudio.google.com/app/apikey). OpenAI — [platform.openai.com/api-keys](https://platform.openai.com/api-keys). Anthropic — [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys). Usage is billed to your provider account.

### Technical

**Q: What file formats are supported for resumes?**  
A: PDF, DOCX, and TXT files up to 10 MB.

**Q: How do I reset my password if email isn't configured?**  
A: On self-hosted instances without SMTP, the password reset page shows the reset link directly on screen after you submit your email — no email is sent. Copy the link, open it, and set your new password. If you are the operator and want to enable email delivery, configure the `SMTP_*` variables in your `.env` file.

**Q: Something looks broken — how do I report it?**  
A: Open an issue at `https://github.com/eliornl/applypilot/issues` with the steps to reproduce, what you expected, and what actually happened.
