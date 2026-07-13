# Deploying Avocado to Railway

Avocado is two services — **API** (FastAPI) and **Web** (Next.js) — plus a
**Postgres** database. Both services have Dockerfiles and `railway.json`, so
Railway builds them directly from this repo.

## Architecture on Railway

```
[ Web service ]  --NEXT_PUBLIC_API_URL-->  [ API service ]  --DATABASE_URL-->  [ Postgres ]
   Next.js                                     FastAPI                            plugin
```

## One-time setup (GitHub-connected — recommended)

1. **Create a Railway project** → "Deploy from GitHub repo" → select
   `Zeivier1972/Avocado-Elementary`.
2. **Add Postgres:** in the project, *New → Database → PostgreSQL*. Railway
   creates a `DATABASE_URL` variable you can reference.
3. **API service:**
   - New → GitHub Repo → set **Root Directory** to `apps/api`.
   - Variables:
     - `DATABASE_URL` → reference the Postgres plugin's `DATABASE_URL`
       (Railway: `${{Postgres.DATABASE_URL}}`).
     - `SECRET_KEY` → a long random string (e.g. `openssl rand -hex 32`).
     - `CORS_ORIGINS` → the Web service's public URL (set after step 4).
     - `SEED_ON_START` → `true` for the first deploy to load demo data, then
       set back to `false`.
     - *(optional)* `AI_PROVIDER=anthropic`, `AI_API_KEY=…`, `AI_MODEL=claude-sonnet-5`.
   - Generate a public domain (Settings → Networking → Generate Domain).
4. **Web service:**
   - New → GitHub Repo → set **Root Directory** to `apps/web`.
   - Build variable `NEXT_PUBLIC_API_URL` → the **API** service's public URL.
     (This is baked in at build time, so redeploy Web if the API URL changes.)
   - Generate a public domain.
5. Back on the **API**, set `CORS_ORIGINS` to the Web public URL and redeploy.

Open the Web URL and log in with the demo accounts:
`teacher@avocado.edu` / `principal@avocado.edu`, password `demo1234`.

## Alternative: Railway CLI

```bash
railway login
railway link           # select the project
# From apps/api and apps/web respectively:
railway up
```

Set the same variables via `railway variables set KEY=value` or the dashboard.

## What I (Claude) need from you to deploy on your behalf

I can push code and open PRs, but I can't log into your Railway account. To let
me drive the deploy, provide **one** of:

- A **Railway project token** (Project Settings → Tokens) exposed to my
  environment as `RAILWAY_TOKEN` — then I can run `railway up` for each service; **or**
- Do the GitHub-connect steps above yourself (5 minutes) and paste me the two
  public URLs so I can wire `CORS_ORIGINS` / `NEXT_PUBLIC_API_URL` and verify.

Optional but recommended:
- An **LLM API key** (Anthropic) if you want live AI-generated DI plans instead
  of the structured template. Without it everything still works.

## Health checks
- API: `GET /health` and `GET /health/db`.
- Web: the root page.

## Production hardening (tracked in docs/10-development-roadmap.md, Phase 1)
This MVP creates tables on startup and uses SQLite locally. Before a live-data
pilot: switch to Alembic migrations, real district SSO, secrets management, and
the full compliance controls in [00-compliance-and-guardrails.md](00-compliance-and-guardrails.md).
