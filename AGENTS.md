# How coding agents work on this repository

hackCBS 9.0, Meko challenge. Every teammate's coding agent is connected to Meko and shares one **build datapack**:
`crimeai-build`. It holds the team's decisions, API contracts, schemas, datapack names and gotchas.

The product's own datapacks (`crimeai-dlp`, `crimeai-grid`, `crimeai-ggm`, `crimeai-noi`) belong to the running app.
Coding agents never read or write them, and the app never reads the build datapack.

## Protocol for every task

1. **Recall first.** Before starting, `context_search` the build datapack for the task's topic and follow every
   promoted decision you find.
2. **Save when done.** When the task ends, `memory_add` a one to three line summary to the build datapack: what
   changed, which files, and `decided by <teammate name>`.
3. **Promote what others must follow.** API shapes, table or column names, memory text formats, env vars and
   datapack names are written as `DECISION (<teammate name>): ...`. Show it to your teammate; once they agree,
   `memory_promote` it. Only promoted rows reach the rest of the team.
4. **Never** put keys, tokens, `.env` contents or personal data into Meko.

## Project facts

- Backend: `crimeai/backend` (FastAPI, async SQLAlchemy, Alembic, Celery). Frontend: `crimeai/frontend` (React, Vite).
- Database: **YugabyteDB** (YSQL, PostgreSQL 15 compatible, port 5433). There is no PostGIS and no GiST:
  radius queries go through `crime_repository.within_m`; time-ordered indexes must be range indexes
  (`created_at DESC`), see migration `0010`. `scripts/yb_bootstrap.py` prepares roles, databases and extensions.
  On Docker Desktop, start YugabyteDB with `max_clock_skew_usec=10000000` on master and tserver (the dev compose
  file does): otherwise the VM's clock drift crashes the tserver every 30 seconds and connections drop.
  Alembic runs one transaction per migration, because YugabyteDB does not roll back a failed batch of DDL.
- Meko code: `crimeai/backend/app/meko`
  - `client.py`: MCP session per agent run, every call logged to the `meko_calls` table.
  - `contract.py`: how memories are phrased and parsed. Meko rewrites memory text, so everything the linker needs
    is carried as tokens: identifier fingerprints `UPI-…`/`PH-…`/`AC-…`/`VH-…`, case refs `AGENCY:case_number`,
    series ids `SR-AGENCY-NN`, method tags.
  - `service.py`: the agents (intake, linker, briefer, curator). Agents propose; officers decide.
- Meko UI: `crimeai/frontend/src/components/fir/MekoPanel.tsx` and `src/pages/meko/MekoPage.tsx`.
- Tests: `pytest tests/unit` (no services), `pytest tests/integration` (YugabyteDB + Redis).
