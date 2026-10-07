# Postulare — Backend

[🇪🇸 Español](README.md) · 🇬🇧 English

REST API for **Postulare**, an app that helps you organise your job hunt: it keeps track of your applications, finds job offers that fit your profile, scores how well each one matches you, and helps you write the cover letter.

- 🌐 Live demo: <https://postulare.vercel.app> (click **"Try the demo"**, no sign-up needed)
- 📖 Interactive API docs (Swagger): <https://postulare-backend.onrender.com/docs>
- 🖥️ Frontend (Angular 18): [postulare-frontend](https://github.com/costanna/postulare-frontend)

> The API runs on Render's free plan, which puts the service to sleep after a while without traffic: the first request may take ~30 s to wake it up.

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL (Neon) · JWT · pytest

## What is Postulare?

Job hunting is noisy: dozens of applications in spreadsheets, repeated job postings, no idea who you should write to again. Postulare puts it all in one place:

| | |
|---|---|
| **Applications** | Kanban board and filterable table. Every status change (saved → applied → interview → offer…) leaves a trace in a timeline. |
| **Recommended offers** | Searches [Adzuna](https://developer.adzuna.com/) (and [InfoJobs](https://developer.infojobs.net/), if enabled) using your position and skills, drops offers for another seniority level and repeated ones (and, if you want, filters by companies that mention disability or by work mode: remote, hybrid or on-site), and scores each from 0 to 100. |
| **Cover letters** | Per offer, written by AI (Claude) when enabled, or from a free template in Catalan, Spanish and English. |
| **CV import** | Upload your CV as a PDF and your profile is filled in (position, location, level, skills, summary). The PDF is never stored. |
| **Follow-ups** | Flags applications that have had no news for days. |
| **Export** | All your applications as CSV. |
| **No-sign-up demo** | A temporary account with sample data to try the app. |

## Screenshots

<p>
  <img src="https://raw.githubusercontent.com/costanna/postulare-frontend/main/docs/screenshots/dashboard.png" alt="Dashboard with pending follow-ups" width="49%">
  <img src="https://raw.githubusercontent.com/costanna/postulare-frontend/main/docs/screenshots/matches.png" alt="Recommended offers" width="49%">
  <img src="https://raw.githubusercontent.com/costanna/postulare-frontend/main/docs/screenshots/cover-letter.png" alt="Cover letter" width="49%">
  <img src="https://raw.githubusercontent.com/costanna/postulare-frontend/main/docs/screenshots/profile-cv-import.png" alt="CV import" width="49%">
</p>

## Architecture

```mermaid
flowchart LR
    U[Browser] --> V[Angular frontend<br/>Vercel]
    V -->|HTTPS + JWT| R[FastAPI API<br/>Render]
    R --> N[(PostgreSQL<br/>Neon)]
    R -->|job offers| A[Adzuna API]
    R -.->|cover letters, optional| C[Anthropic API]
```

The backend is the only piece that talks to third-party services: the browser never sees the Adzuna or Anthropic keys.

## Main endpoints

Everything except `/auth/*` and `/health` requires `Authorization: Bearer <token>` and only returns the authenticated user's data. Full details are in `/docs`.

| Resource | Endpoints |
|---|---|
| Authentication | `POST /auth/register` · `/auth/login` · `/auth/refresh` · `/auth/forgot-password` · `/auth/reset-password` · `/auth/demo` · `GET /auth/me` |
| Profile | `GET/PATCH /profile` · `POST /profile/import-cv` |
| Applications | `GET/POST /applications` · `GET/PATCH/DELETE /applications/{id}` · `GET /applications/follow-ups` · `GET /applications/export` |
| Events | `GET/POST /applications/{id}/events` · `DELETE /events/{id}` |
| Offers | `GET/PUT /matches/filters` · `POST /matches/search` · `GET /matches` · `POST /matches/{id}/convert` · `POST /matches/convert-bulk` · `/dismiss` · `/cover-letter` · `/{id}/apply-pack` · `/{id}/auto-apply` · `/{id}/send-email` |
| Spontaneous | `GET/POST /targets` · `PATCH/DELETE /targets/{id}` · `POST /targets/{id}/send` · `/send-bulk` · `/autopilot` · `/suggestions` · `/import` · `/quota` · `GET/PUT /profile/cvs/{es,ca,en}` |
| Statistics | `GET /stats/summary` · `/by-status` · `/timeline` · `/by-source` |

## Running locally

Requirements: Python 3.12+ and PostgreSQL 16 (or Docker).

```bash
python -m venv .venv
source .venv/Scripts/activate        # Windows (Git Bash); on Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env                 # fill in DATABASE_URL, SECRET_KEY and, to search offers, ADZUNA_APP_ID/KEY
docker compose up -d db              # local PostgreSQL (or point DATABASE_URL at your own database)
alembic upgrade head
uvicorn app.main:app --reload
```

- API: <http://localhost:8000> · Swagger: <http://localhost:8000/docs>
- Everything in Docker (database + API, migrations applied automatically): `docker compose up --build`

### Environment variables

The full, commented list is in [`.env.example`](.env.example). Never commit a real `.env` (it is already in `.gitignore`).

| Variable | Required? | What it is for |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection (with Neon, the "direct" string plus `?sslmode=require`) |
| `SECRET_KEY` | Yes | Signs the JWTs. Use a long random value |
| `CORS_ORIGINS`, `FRONTEND_URL` | Yes in production | Frontend URL, no trailing slash. `FRONTEND_URL` is used in the password-reset email link |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | To search offers | Free keys from [developer.adzuna.com](https://developer.adzuna.com/) |
| `INFOJOBS_CLIENT_ID`, `INFOJOBS_CLIENT_SECRET` | No | Enable InfoJobs as a second offer source (see below) |
| `FREE_BOARDS_ENABLED`, `FREE_BOARDS_MAX_RESULTS` | No | Free keyless boards (Remotive, RemoteOK, Arbeitnow) |
| `EURES_ENABLED`, `EURES_MAX_RESULTS` | No | EURES portal filtered to Spain, keyless |
| `HN_HIRING_ENABLED` | No | Monthly "Ask HN: Who is hiring?" thread, keyless |
| `SEND_EMAIL_DAILY_LIMIT_PER_USER` / `OFFER_RESEND_DAYS` / `SPONTANEOUS_RESEND_DAYS` | No | `5` / `15` / `30`: sending caps and re-send cooldowns |
| `ALLOWED_REGISTRATION_EMAILS` | No | If set (comma-separated), only those emails can register |
| `ANTHROPIC_API_KEY` | No | Enables AI cover letters. Without it the free template is used |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | No | Actually sends the password-reset email. Without SMTP the link is only written to the log |

## Tests

```bash
pytest
```

275 tests on in-memory SQLite: they touch neither PostgreSQL, nor Alembic, nor the real APIs (Adzuna and Anthropic are simulated).

## Deployment: Neon + Render

### 1. Database on Neon

1. Create a project at [neon.tech](https://neon.tech) (free tier that does not expire).
2. Copy the **"direct"** connection string (not the "pooled" one): `postgresql://user:password@ep-xxxx.aws.neon.tech/postulare?sslmode=require`.

### 2. Web service on Render

1. On Render: **New +** → **Blueprint** and pick this repository. [`render.yaml`](render.yaml) describes the service built from the `Dockerfile`.
2. Fill in the values marked as pending (table below). `SECRET_KEY` is generated automatically.
3. Every deploy runs `alembic upgrade head` before starting, so migrations are applied to Neon automatically. The health check is `GET /health`.

### What to configure on Render

Variables of an already-created service are **not synced automatically** from `render.yaml`: add them by hand in *Dashboard → your service → Environment*.

| Variable | Value | Notes |
|---|---|---|
| `DATABASE_URL` | Neon connection string | Required |
| `SECRET_KEY` | Long and random | Required. Changing it logs everyone out |
| `CORS_ORIGINS` | `https://postulare.vercel.app` | No trailing slash |
| `FRONTEND_URL` | `https://postulare.vercel.app` | Must be exact: the reset email links to `FRONTEND_URL/auth/reset-password` |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Your Adzuna keys | Without them (and without InfoJobs) "Search offers" returns 502 |
| `INFOJOBS_CLIENT_ID`, `INFOJOBS_CLIENT_SECRET` | Your InfoJobs keys | **Optional**: enables InfoJobs as a second source |
| `FREE_BOARDS_ENABLED`, `EURES_ENABLED`, `HN_HIRING_ENABLED` | `"true"` | Free keyless sources (remote boards, EURES-Spain, HN hiring) |
| `ANTHROPIC_API_KEY` | Your Anthropic key | **Optional**: enables AI cover letters |
| `ANTHROPIC_MODEL` | `claude-opus-5` (default) | `claude-haiku-4-5` is much cheaper |
| `LLM_DAILY_LIMIT` / `COVER_LETTER_DAILY_LIMIT_PER_USER` | `20` / `5` | Daily spending caps (global and per user) |
| `DEMO_ENABLED`, `DEMO_TTL_HOURS` | `true`, `24` | Temporary demo accounts |
| `SMTP_*` | Your mail provider | **Optional**, but without it no password-reset email is ever delivered |

## Job offers: which APIs can be used

- **Adzuna** (in use): official, free API that aggregates offers from many websites.
- **InfoJobs** (optional): [official API](https://developer.infojobs.net/) (`GET /api/9/offer`). Enabled by setting `INFOJOBS_CLIENT_ID` and `INFOJOBS_CLIENT_SECRET`. To get them: sign in at <https://developer.infojobs.net/> with your InfoJobs account (create one on infojobs.net if needed) and register an application at <https://developer.infojobs.net/app/manage-app/create.xhtml>; it gives you both keys. **Note: new app registration is currently closed** ("The registration of new apps is currently unavailable"): until then, EURES-Spain covers national offers with no key. Results are merged with Adzuna's, repeats are removed, and it has its own daily cap (`INFOJOBS_DAILY_LIMIT`). If one source fails, the search carries on with the other. InfoJobs' listing has no full description, so those offers are scored from the title, the minimum requirement and the category.
- **Free keyless sources** (`FREE_BOARDS_ENABLED=true`): Remotive, RemoteOK and Arbeitnow. Remote/Europe only, used when the filter is remote/hybrid or there is no location. No quota or signup.
- **EURES-Spain** (`EURES_ENABLED=true`): European employment portal filtered with `locationCodes=["es"]`, free and keyless. Covers offers across Spain and includes Empléate/SEPE ones. Used when the location is Spain or empty; skipped for foreign locations.
- **Spain-only mode**: the `spain_only` search filter drops offers with a concrete non-Spain location (remote or location-less ones are kept).
- **LinkedIn**: there is **no** public API to search job offers; its jobs API is only for partners who *post* jobs and is not accepting new ones. Scraping breaks their terms and risks getting the account banned, so this project does not do it.

## Free sending automation

No free API lets you press "apply" on someone else's portal: they only return the URL. Postulare automates everything else, free and locally:

- `GET /matches/{id}/apply-pack`: template letter + CV in markdown + email subject/body + `mailto:` + checklist. `POST` to the same path rebuilds the kit with your edited letter (for mailto and copying too).
- `POST /matches/{id}/auto-apply`: prepares the application as saved (or applied with `applied: true`), generates the letter if missing and returns the kit. Never marks "applied" by default: the app always asks first.
- `POST /matches/auto-apply-bulk` (`{min_score, limit}`): converts the best new ones in bulk.
- `POST /matches/convert-bulk` (`{match_ids}`): saves several offers as applications at once.
- `GET /profile/cv-document?format=markdown|text|html&lang=es|ca|en`: CV generated from the profile to paste or print to PDF.

**Language adapted to each company:** the kit detects the offer's language (Catalan, Spanish or English) and generates the letter, the email subject and body, the CV labels and the checklist in that language; otherwise it uses your preferred language. Your own content (summary, skills) is never translated: only Postulare's templates. In the frontend, the **"Send CV"** button shows the kit with copy and **"Open in my email"** (mailto, all filled in).

**ATS-friendly email:** the body is plain text (what parsers handle best) with a `Re: {position} — {company}` line, a `Key matches:` line with your real skills mentioned in the offer (never invented, in order of appearance, max 12) and a `Profile:` line. The subject carries the exact job title.

**Direct email sending** (`POST /matches/{id}/send-email`): if the offer has a contact email, it sends from your SMTP (e.g. your Gmail with an app password) in the offer's language with the CV attached as **PDF** (your uploaded original or a generated one), leaving the application as "applied". Accepts an edited `cover_letter`, which is then saved. **Real accounts only**: demo answers 403 (and the "Send now" button does not even appear).

**Anti-spam limits (offers + spontaneous):** 5 sends/day to different companies, 15 days before re-sending to the same company in offers and 30 in spontaneous ones (`Acme SL` = `ACME S.A.`). See `POST /targets/*`.

**My CVs per language** (`GET/PUT /profile/cvs/{es,ca,en}`, `POST .../file`, `DELETE .../file`): paste your CV or **upload the PDF** in each language from the profile. The original PDF is stored and attached as-is when sending (with the extracted text for display/pasting); pasting text afterwards replaces the PDF. Without PDF or text, one is generated from your profile.

**Spontaneous applications** (`/targets`): your own directory of consultancies and tech companies (name + email + language + tags), single or bulk sending (`POST /targets/send-bulk`), with a spontaneous letter in their language. Each send creates its "applied" application and respects the same limits.

**Autopilot** (`POST /targets/autopilot`): sends up to 5 with no offers involved, only to companies whose tags match your CV (tags vs skills/position, with visible score), skipping those contacted less than 30 days ago. Paused and resumed with `PATCH /profile {auto_outreach_paused}` (button on the page).

**Discovery without adding by hand** (`GET /targets/suggestions`, `POST /targets/import`): companies with real emails aggregated from your offers + the monthly "Ask HN: Who is hiring?" thread (Spain/remote filter and your skills). The autopilot imports them on its own (`include_suggestions`, on by default); the page lists them under "Auto-discovered" to add by hand if you prefer.

**Email from the company name:** when viewing an offer without email, the domain is looked up (Clearbit, no key) and its home and contact pages are scanned for own-domain mailboxes (`jobs@`, `rrhh@`...). Own domains only, with cache; the kit tells whether the email came from the offer or the website.

Clicking the final button on the portal stays manual (and must: auto-apply bots break the ToS).

## Quota and spending protection

A public demo must not drain your quotas or your balance. Every paid resource has its own cap, and the one that matters does not depend on who calls or from where.

**Adzuna (free, but with a quota):**

1. Per-user wait between searches (`MATCH_SEARCH_COOLDOWN_MINUTES`, 10 min).
2. Cache for identical searches (`ADZUNA_CACHE_MINUTES`, 6 h).
3. Per-IP limit on register, login and password reset. The IP comes from `X-Forwarded-For`, which can be spoofed: that is why there is a fourth layer.
4. **Global daily cap** (`ADZUNA_DAILY_LIMIT`, 50), counted in the `adzuna_usage` table. When reached, search answers `503` and the rest of the app keeps working.

**AI cover letters (each letter costs money):**

- Without `ANTHROPIC_API_KEY` nothing is spent: the free template is returned.
- Global daily cap (`LLM_DAILY_LIMIT`) and per-user cap (`COVER_LETTER_DAILY_LIMIT_PER_USER`), stored in the `llm_usage` table. When exhausted the template keeps coming back, never an error.
- If the AI fails, the template is returned and the cap reservation is **given back**.
- The job description is third-party text: it is delimited and the prompt tells the model not to obey any instructions inside it.

## Demo accounts

`POST /auth/demo` instantly creates a user with fictional data, with no email or password. It cannot search real offers (403), send emails or use Spontaneous ones (403, section hidden in the app), its letters always use the template, it expires after `DEMO_TTL_HOURS` hours and expired ones are deleted, with all their data, automatically. There is a per-IP limit and a global cap of demos per day.

**Restricted registration (personal use):** with `ALLOWED_REGISTRATION_EMAILS=costanna.bcn@gmail.com` only that email can register (403 for everyone else).

## Security

- Passwords hashed with `bcrypt`; access JWT of 15 min and refresh token of 7 days.
- Every endpoint filters by the token's `user_id`: nobody can see or modify another user's data (someone else's resource answers 404, not 403).
- Emails are case-insensitive; "forgot password" answers the same whether the account exists or not.
- CORS restricted to `CORS_ORIGINS`. The exported CSV neutralises spreadsheet formulas.
- The CV is processed in memory and discarded.

## Project structure

```text
app/
├── main.py        FastAPI, CORS and routers
├── core/          configuration, security (JWT, hashing) and per-IP limits
├── db/            engine, session and portable PostgreSQL/SQLite types
├── models/        SQLAlchemy models
├── schemas/       Pydantic schemas (input/output)
├── routers/       endpoints per resource
└── services/      business logic: offer search and scoring, cover letters,
                   CV importer, duplicates, demo, AI quotas, statistics
alembic/           migrations
tests/             pytest
```

## Ideas for what comes next

- AI-reasoned offer scoring (today it is keyword-based).
- Email reminders for pending follow-ups.

## License

[MIT](LICENSE) © 2026 Anna Costa
