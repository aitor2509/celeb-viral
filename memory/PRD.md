# CelebTrack - PRD

## Original Problem Statement
App para Meta Buster (agencia mexicana de social media) que rastrea celebridades (Franco Escamilla, Don Cheto, El Potro, Said el Interrogatorio, Rica Famosa Latina) y muestra: videos recientes de YouTube, contenido viral/funas, notificaciones in-app, color personalizado por personaje, agregar más personajes via búsqueda YouTube, opción de teléfono para alertas.

## Architecture
- **Backend**: FastAPI + MongoDB + YouTube Data API v3 (google-api-python-client)
- **Frontend**: React 19 + React Router + Tailwind + Shadcn UI + sonner + lucide-react
- **Design**: Neon-Brutalist dark dashboard with dynamic celebrity color theming via CSS variables

## User Personas
- Community Manager / Meta Buster agency owner (sin login - app interna)

## Core Requirements (Static)
- Dashboard with all tracked celebrities
- Per-celebrity detail with YouTube feed (latest), top virales (by views), funas/virales manuales
- Add new celebrity via YouTube channel search
- Custom color per celebrity (applied dynamically to UI accents)
- In-app notifications when new video appears or viral added
- Contact subscription form (phone) per celebrity

## Implemented (2026-02)
- 5 celebrities auto-seeded on startup with real YouTube data
- Endpoints: CRUD celebrities, videos, virals, notifications, contacts, refresh-all
- YouTube search to add any new celebrity (Luis Fonsi etc.)
- Frontend: Dashboard, Detail (Tabs: Reciente / Top virales / Funas), Add Celebrity Dialog (2-step), Add Viral Dialog, Add Contact Dialog, Notifications popover, Command-K search
- Dynamic celebrity color theming via --celebrity-color CSS var
- Cabinet Grotesk + Outfit fonts (Fontshare)

## Backlog (P1/P2)
- P1: SMS notifications real (Twilio) for phone subscriptions
- P1: Web scraper for "funas" automáticas (Twitter/news)
- P2: AI integration to detect old viral collaborations resurfacing
- P2: Cron job (APScheduler) to auto-refresh videos every X hours
- P2: Multi-platform (TikTok, Instagram) tracking
- P2: Analytics dashboard (growth charts per celebrity)

## Next Tasks
- Optional: hourly cron to auto-detect new videos
- Optional: Twilio SMS integration
- Optional: News scraper for "funas"

## Implemented (Iteration 2 · 2026-02)
- ✅ Videos vs Shorts split (auto-detect via duration ≤ 60s)
- ✅ 3 sub-tabs per kind: Más recientes / Más virales del canal / Recomendados Facebook
- ✅ AI recommendations powered by Claude Sonnet 4.5 (Emergent LLM key)
- ✅ User-editable "trending context" textarea, persisted per celebrity
- ✅ Auto-scraped Google News tab (México, español, 1h cache)
- ✅ Multi-channel support: secondary YouTube channels per celebrity
- ✅ Delete celebrity confirmed working
