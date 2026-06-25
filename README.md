# LolSuit ⚖️ — The Court of Funny Lawsuits

A satirical social network where users file humorous "lawsuits" against one another.
Mid-semester project — Full Stack course, Reichman University (RUNI) 2026.

## Architecture (3 tiers)

| Tier | Technology | Location |
|---|---|---|
| Frontend | React 18 + TypeScript + Vite + MUI 5 | [`client/`](client/) |
| Backend | Python + Flask + raw PyMySQL (no ORM) | [`server/`](server/) |
| Database | MySQL 8 (Amazon RDS in production) | [`database/init.sql`](database/init.sql) |

The frontend talks to the backend through `/api`. In development, the Vite dev server (port 5173) proxies all `/api` requests to Flask (port 5001) — see [`client/vite.config.ts`](client/vite.config.ts).

## Prerequisites

- **Node.js** 18+ and **npm**
- **Python** 3.10+
- **MySQL** 8 — either a local server/container or an Amazon RDS endpoint

The server reads its connection from the environment (defaults in parentheses):
`DB_HOST` (`localhost`), `DB_PORT` (`3306`), `DB_USER` (`root`), `DB_PASSWORD` (empty),
`DB_NAME` (`lolsuit`). It creates the database/schema and seeds it on first run.

## Running locally

You need to run two processes in parallel — start the server first, then the client.

### 1. Server (Flask) — port 5001

```bash
cd server
python -m venv .venv                 # first time only
source .venv/bin/activate            # on Windows: .venv\Scripts\activate
pip install -r requirements.txt      # first time only
python run.py
```

The server starts at http://localhost:5001 and automatically creates + seeds the database on first run.

### 2. Client (React) — port 5173

In a separate terminal:

```bash
cd client
npm install                          # first time only
npm run dev
```

Open the printed URL (usually http://localhost:5173/intuit-runi-fullstack-2026/).

> **Note:** routing uses `HashRouter`, so routes live after the `#` in the URL (e.g. `#/users`, `#/user-posts/8`).

## Demo users (seed)

On first run, 12 sample users are created. They all share the same password:

| Email | Password |
|---|---|
| `dana@example.com` (and the rest of the seed users) | `demo123` |

> Password-strength rules (8+ chars, a letter + a digit) are enforced on the signup form only; seed users are created directly in the DB and therefore still log in with `demo123`.

## Resetting the database

The schema uses `CREATE TABLE IF NOT EXISTS`, so to apply schema changes you must drop the
database and restart the server (it will recreate and reseed it):

```bash
mysql -h "$DB_HOST" -u "$DB_USER" -p -e "DROP DATABASE lolsuit;"
cd server && python run.py
```

With Docker, `docker compose down -v` removes the MySQL data volume and forces a fresh seed on
the next `up`.

## Production build (Frontend)

```bash
cd client
npm run build      # compiles TypeScript + produces an optimized dist/ folder
npm run preview    # preview the local production build
```

## Tests (Frontend)

```bash
cd client
npm test           # run the Vitest suite
```

## Running with Docker (server + MySQL)

```bash
docker compose up --build    # brings up MySQL + the Flask server on port 5001
```

Compose starts a `mysql:8.0` service and waits for it to be healthy before launching the server.

## Key features

- **User authentication** — sign-up / login / logout, with **bcrypt** password hashing and cookie-based sessions (httpOnly).
- **Password-strength enforcement** at signup (minimum length + a letter-and-digit mix) with a live strength meter.
- **User profiles** — name, bio, profile picture, and a list of the user's lawsuits.
- **Social interactions** — user search, follow/unfollow, and relative timestamps ("2 hours ago").
- **Feed** — a global feed plus a "following" feed, with lazy loading (infinite scroll) and pagination.
- **Post creation** — text + image, with a rich-text (WYSIWYG) editor supporting bold, italics, lists, and links.

## Database schema

A full ER diagram and an explanation of how the entities relate live in [`database/schema.md`](database/schema.md).

## Project structure

```
.
├── client/              # React + TypeScript app
│   └── src/
│       ├── api.ts       # API layer (every fetch goes through here)
│       ├── components/  # UI components
│       ├── pages/       # route-level screens
│       ├── hooks/       # custom React hooks
│       └── utils/       # helpers (dates, validation, sanitization)
├── server/              # Flask server
│   └── app/
│       ├── __init__.py  # application factory
│       ├── routes.py    # REST API routes
│       ├── services.py  # business logic + parameterized SQL queries
│       ├── models.py    # DB access layer + seed data
│       └── utils.py     # password hashing + session helpers
└── database/
    ├── init.sql         # schema definition
    └── schema.md        # ER diagram
```
