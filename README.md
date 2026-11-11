# CrimeAI

© 2026 Rudresh Rajvansh and team. Licensed under [AGPL-3.0](LICENSE).

**CCTNS remembers cases. CrimeAI connects them.**

CrimeAI is an intelligence layer for Indian police stations. It reads FIRs in Indian languages, links cases that share a phone number, UPI ID, bank account or vehicle across stations, finds serial crimes by their method, forecasts risk for the next patrol shift, tracks the BNSS custody deadline for every accused, and simulates a gang's next move with and without police action. Identifiers are stored as keyed hashes and no face or biometric is ever used.

## hackCBS 9.0: shared memory between agencies, on Meko and YugabyteDB

> CrimeAI was first built at InnoHacks 4.0. **What was built at hackCBS 9.0** is everything in this section: the
> move from PostgreSQL to YugabyteDB, Meko shared memory between police agencies (`crimeai/backend/app/meko`, the
> Meko panel on the FIR page, the Shared Memory page), investigation intelligence on the case dossier
> (contradictions, timeline, officer review), and the sponsor integrations below (Gemini investigation review,
> Solana chain of custody, Tiger Cloud time series, DigitalOcean deployment), migrations 0010 to 0013.
> The git history shows the starting point.

**Live demo:** https://35-200-156-166.sslip.io (Google Cloud, Mumbai). Ask the team for the demo login.

CrimeAI links FIRs inside one agency's records. A courier-fraud ring in the NCR works across Delhi, Gurugram and
Noida: three agencies, three record systems that cannot see each other and should not hold each other's
complainants. **Meko is the memory between them.** Each agency keeps a private datapack; a shared grid datapack
carries keyed identifier fingerprints, officer-confirmed series and officers' exclusions, and every agency's
agents recall it before they link anything.

**Persona:** a police officer at a Delhi station registering a courier-customs fraud FIR, written in Hinglish.

| The same FIR | Meko off | Meko on |
|---|---|---|
| Caller phone and UPI ID | "Not seen in any other case" | Gurugram GGM-2026-0412 and Noida NOI-2026-0377 saw them; agents propose a series |
| Bank customer-care number in the FIR | Links two unrelated KYC frauds; raises a local link alert | One officer marks it not a suspect's; promoted to every agency; ignored from then on, and no local alert |
| A later FIR with a new SIM and UPI ID | Standalone case | Matched to confirmed series SR-DLP-01 by method, with the lead agency and the officer's note |

| Meko use | Why |
|---|---|
| **Datapacks as scopes** | Agency datapacks hold redacted case memory; the grid holds only fingerprints, method tags and case refs |
| **Recall before reasoning** | Intake, linker and briefer agents search the agency datapack and the grid before any link is shown; links are computed only from what Meko returns |
| **Extracted memories** | The intake conversation goes to Meko, which extracts durable facts into the agency's memory |
| **Promotion to shared knowledge** | An officer's confirmed series or exclusion is written by the curator agent and promoted with `memory_promote` |
| **Sharing across agencies and agents** | Gurugram's and Noida's sightings reach Delhi's agents through the grid |
| **Documents** | SOPs in the grid knowledge base; the briefer cites them as next steps |

### Investigation intelligence: from fragmented case records to connected leads

Investigators often have the information they need, spread across an FIR, witness statements, CCTV notes,
seizure memos, forensic and bank records. The case dossier now reads them together. Six agents each do one job,
and every lead names the document and quotes the sentence it came from:

| Agent | What it does |
|---|---|
| FIR intelligence | Reads the FIR in any of 13 languages (existing CrimeAI reader) |
| Evidence intelligence | Compares what each document says about the incident: time, date, vehicle number, amount. *"PW-1 says 8 PM; CCTV shows 21:04; difference 1 h 4 min"* |
| Case linking | Shared phones, UPI IDs, accounts and vehicles across cases, and across agencies through Meko |
| Timeline | One source-linked chronology from the case record, documents and e-Sakshya; flags stretches of 7+ days with no recorded step |
| Legal intelligence | IPC to BNS mapping and wrong-code warnings (existing) |
| Audit | Every decision and every Meko call is logged; findings cite their sources |

An officer **accepts**, **rejects** or marks a finding **needs investigation**. An accepted finding is written to
Meko as approved context, and the evidence agent recalls it on later cases that share a vehicle: accept a
transcription error on Saket case DL-INV-2026-001 and it appears on the Malviya Nagar case DL-INV-2026-002.
Findings are leads for human verification; a shared vehicle or witness never establishes the same offender.

**Measured** on five labelled synthetic cases (Hindi and English, `python scripts/evaluate_investigation.py`):
5 of 5 planted contradictions and gaps found, 0 false alarms on the two consistent cases, about 6 ms per case.
It is a small, self-made set, so it shows the agents work as designed, not field accuracy.

### Built with our sponsors' platforms

YugabyteDB stays the system of record; each platform does one job it is good at.

| Platform | What it does in CrimeAI | Where |
|---|---|---|
| **Gemini API** | On the case dossier, **Explain with Gemini** reads the same documents as the agents (identifiers masked first) and, for every contradiction or gap, writes what disagrees, an honest likely cause, the record that would settle it (CCTV export, call records, RTO register) and one next step, plus a short plan and the documents missing from the file. It cannot add findings of its own; every request is audited. Also: English briefs and OCR of FIRs in 13 languages. | `app/nlp/gemini.py` |
| **Solana** | **Chain of custody.** *Seal case file* hashes every document and officer review, builds a Merkle root and anchors it in one Memo transaction (devnet). *Verify* recomputes the hashes from YugabyteDB, names any document changed, added or removed since the seal, and reads the root back from the chain, with an Explorer link. Only hashes go on chain. | `app/services/custody.py`, `app/integrations/solana.py`, migration 0013 |
| **Tiger Data** | Crimes are mirrored (time, type, district, severity, location only) into a **TimescaleDB hypertable on Tiger Cloud**, with hourly and daily **continuous aggregates** in Indian time and **compression** of chunks older than 90 days. The dashboard's *Time series · Tiger Cloud* card reads only the aggregates; a beat job syncs every five minutes. | `app/integrations/tiger.py`, `scripts/tiger_setup.py` |
| **DigitalOcean** | `python deploy/cloud.py up` creates a droplet in Bangalore with a cloud firewall, copies the code and keys over SSH and brings up the production stack with HTTPS. | `deploy/cloud.py` |

Setup: `GEMINI_API_KEY` and `TIGER_DATABASE_URL` go in `crimeai/backend/.env` (see
`.env.example`); `python scripts/solana_setup.py` creates the devnet sealing key, and `python scripts/tiger_setup.py`
creates the hypertable and backfills it.

Every Meko call is stored in YugabyteDB (`meko_calls`) and shown on the **Shared Memory** page, which also lists
what each datapack holds and lets an officer **Correct** or **Forget** any memory. Raw phone, UPI and account
numbers never reach Meko: agencies share HMAC fingerprints keyed with a common grid key.

**Run it (three steps):**

```bash
git clone <this repository> && cd <this repository>
echo MEKO_API_KEY=mko_tkn_your_key >> crimeai/backend/.env
./start.sh        # or start.cmd on Windows: YugabyteDB, demo data, Meko datapacks, SOPs and partner agencies
```

Then log in as `police@crimeai.example`, open **Shared Memory → Demo FIRs**, and follow [docs/meko/DEMO.md](docs/meko/DEMO.md).

More: [design note](docs/meko/DESIGN.md) · [Meko feature proposal: projected memories](docs/meko/FEATURE_PROPOSAL.md) ·
[how our coding agents worked on Meko](AGENTS.md).

## The problem

A gang uses one phone number to cheat people in five districts. Each victim files at a different station, in a different language. Every FIR is recorded, but nobody notices it is the same number five times. Meanwhile an accused in custody walks free on default bail because the 60-day chargesheet deadline slipped.

| Gap today | What CrimeAI does |
|---|---|
| The same phone, UPI ID or vehicle appears in FIRs at several stations, unnoticed | **Link graph** joins the cases and raises one alert per identifier, with a one-click freeze-request draft |
| Serial crimes with the same method look like separate cases | **Series detector** groups cases by place, time and method, even when one FIR is in Hindi and another in English |
| FIRs arrive in many languages | **FIR reader** handles English and 12 Indian languages; **Gemini** gives any officer an English brief |
| Patrols go where they went yesterday | **Hotspot forecaster** predicts risk per district for each 6-hour shift |
| Default bail after a missed deadline | **Custody clock** counts the BNSS s.187(3) 60/90-day limit from first remand |
| "What if we act?" is guesswork | **Swarm** runs 300 simulated futures with and without patrols or a freeze on the money trail |

## How it works

```mermaid
flowchart TD
    S["Sources<br/>CCTNS exports · NCRP 1930 · e-Sakshya · typed or scanned FIRs"] --> R["FIR reader<br/>language · BNS sections · phones, UPI, vehicles · PII masked · embedding"]
    R --> L["Link graph<br/>same phone, UPI, car"]
    R --> SD["Series detector<br/>same method, 3 km, 21 days"]
    R --> H["Hotspot forecaster<br/>risk per district per shift"]
    R --> C["Custody clock<br/>BNSS 60 / 90 days"]
    L --> W["Swarm simulator<br/>300 futures"]
    SD --> W
    L --> A["Alerts · dossier · daily briefing"]
    SD --> A
    H --> A
    C --> A
    W --> O(["Officer decides and acts"])
    A --> O
```

| Engine | How it decides |
|---|---|
| **FIR reader** | Detects the script, then the language (marker words split Hindi from Marathi). Normalises Indic digits, finds crime, weapon, place and legal terms with lexicons, extracts vehicle numbers, phones, UPI IDs, bank accounts and amounts, maps IPC to BNS and warns when an old IPC section is cited for an incident after 1 July 2024. Aadhaar (Verhoeff-checked), phone, PAN, bank and UPI numbers are masked before any text reaches a model. Scanned FIRs are read with Tesseract OCR. |
| **Embeddings** | `intfloat/multilingual-e5-small` turns each narrative into 384 numbers, so the same method lands close together in any language. Place names are removed first; location is compared separately. Stored in YugabyteDB with pgvector (a distributed HNSW index). |
| **Link graph** | Every identifier becomes a node; two or more cases sharing one are joined, and chains of shared identifiers form a network. Phones, UPI IDs and accounts are stored only as an HMAC-SHA256 keyed hash. A match is a fact, not a prediction. |
| **Series detector** | Links two cases when they are the same crime type, within 3 km and 21 days, and their narratives are unusually similar for that crime type. The bar is measured on pairs that cannot share a series, and a Hindi-English pair is judged against other cross-language pairs, so a Hindi FIR can join an English series. Linked pairs are merged and pruned until every member fits. |
| **Hotspot forecaster** | A scikit-learn gradient-boosted model, the one model trained here. It predicts whether a district records a crime in each 6-hour shift from 11 inputs (recent counts, the district's usual rate, shift, weekday, month). Split by time, tested on the newest 20%, compared with a 28-day-average baseline and retrained nightly. Last run: ROC-AUC 0.645 vs 0.622 for the baseline. |
| **Risk index** | 0–100 per district from harm-weighted, recency-weighted crimes over 90 days; alerts only when a district rises to high or critical. |
| **Custody clock** | 90 days for offences punishable with death, life or 10+ years (BNS 103, 64, 70, 310 …), otherwise 60, counted from first remand in IST. Ambiguous sections are flagged "verify", never guessed. |
| **Swarm** | Gathers a case's linked network, learns its tempo, hours and places, spawns one agent per shared identifier and patrol units where they cover the most incidents, then plays 300 futures with the same random draws with and without action. It forecasts places and time windows, never people. |
| **Gemini case brief** | Google Gemini returns an English translation, summary, method, key facts, missing details and section suggestions for redacted FIR text. Each suggestion is checked against the IPC-BNS crosswalk and flagged when its reason contradicts the section's official title. |

## Screens

| Page | What it is for |
|---|---|
| Dashboard | Counts, trend, district risk and the next-24-hour shift forecast |
| Crime Map | Every incident with heat map, markers and clusters; click for crimes within 1.5 km |
| Intelligence | Crime series with the next likely window; custody deadlines; daily PDF briefing |
| Link Analysis | Network, timeline and map of cases joined by shared identifiers; freeze-request draft |
| FIR Analysis | Submit or preview an FIR; highlighted narrative, sections, identifiers, Gemini brief |
| Alerts | Link, series, risk and custody alerts, live over WebSocket |
| Patrol Routes | Risk-weighted, coverage or shortest routes on real roads (OSRM) |
| Swarm | Simulated futures of a network, with patrol and freeze levers |
| Simulation | District-level what-if for patrols, CCTV, curfew |
| Integrations | How CrimeAI connects to CCTNS, NCRP, e-Sakshya and ICJS; file import |
| Shared Memory | Meko: what each datapack holds (correct or forget), agents ↔ datapacks map, every Meko call, demo FIRs |
| Case Dossier | Investigation intelligence (documents, contradictions, timeline, officer review), custody countdown, linked identifiers, similar cases in any language, e-Sakshya evidence |
| Admin | Access requests, users, audit log, model training, system health |

## Run it locally

One command installs Docker if needed, builds everything, loads demo data, trains the models and opens the app:

```bash
start.cmd        # Windows
./start.sh       # macOS / Linux
```

It prints `http://localhost:5173` and the demo login (`admin@crimeai.example`; the password is saved in `crimeai/backend/var/demo-credentials.txt`). Other roles: `analyst@`, `police@`, `readonly@crimeai.example`. The first run downloads about 3 GB.

**Gemini (optional):** create `crimeai/backend/.env` with `GEMINI_API_KEY=your-key` from [Google AI Studio](https://aistudio.google.com/apikey) and run `start.cmd` again. Without a key the feature is hidden and nothing leaves the server.

## Deploy on DigitalOcean

```bash
DIGITALOCEAN_TOKEN=... python deploy/cloud.py up   # 4 vCPU / 8 GB droplet in blr1, cloud firewall
python deploy/cloud.py ship <ip>                   # redeploy the committed code to an existing droplet
```

`up` creates a billable droplet with your SSH key, copies the committed code (without the sample FIR images), the
service keys from `crimeai/backend/.env` and the Solana sealing key, and runs [`deploy/deploy.sh`](deploy/deploy.sh).
It prints `https://<ip>.sslip.io` and the demo login when done (15–25 minutes the first time). A production server
is its own agency on the Meko grid (datapacks `crimeai-prod-*`, its own grid key) and labels its Tiger rows with
its domain. To run two servers at once, ship the second with `MEKO_DATAPACK_PREFIX=...` so they never share
datapacks (Meko's free plan caps how many datapacks an account can create).

## Deploy on Google Cloud from your machine

The hackCBS demo server runs this way: a Compute Engine VM in Mumbai, shipped with the same `cloud.py ship`.

```bash
gcloud compute firewall-rules create crimeai-web --allow tcp:80,tcp:443 --target-tags http-server,https-server  # once
gcloud compute instances create crimeai-meko --zone asia-south1-a --machine-type e2-standard-4 \
  --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud --boot-disk-size 60GB \
  --tags http-server,https-server --scopes cloud-platform \
  --metadata ssh-keys="deployer:$(cut -d' ' -f1,2 ~/.ssh/id_ed25519.pub) deployer"
python deploy/cloud.py ship deployer@<external-ip>
```

`ship` logs in as `deployer` and runs everything through `sudo`. The `cloud-platform` scope lets the VM's service
account call Vertex AI, which `deploy/deploy.sh` sets up as the backup for the Gemini API key.

## Deploy on Google Cloud (GitHub Actions)

Every push to `main` deploys the app to a Compute Engine VM through [`.github/workflows/deploy-gcp.yml`](.github/workflows/deploy-gcp.yml). One-time setup in **Settings → Secrets and variables → Actions**:

| Name | Type | Value |
|---|---|---|
| `GCP_PROJECT_ID` | Variable | Your GCP project id (deploys are skipped until it is set) |
| `GCP_SA_KEY` | Secret | JSON key of a service account with **Compute Admin** and **Service Account User** roles |
| `GEMINI_API_KEY` | Secret | Optional: turns on Gemini case briefs |

Then run the workflow (Actions → Deploy to GCP → Run workflow, or push to `main`). The first run creates the VM (`e2-standard-4`, `asia-south1-a`) and firewall, installs Docker, builds the stack, loads the demo data and prints the live URL, `https://<external-ip>.sslip.io`, with a Let's Encrypt certificate. It takes 15–25 minutes; later runs only rebuild what changed. The demo login is printed in the workflow log.

**Using Google Cloud Build instead:** in Cloud Build → Triggers, connect this repository with event "Push to branch" `main` and configuration file [`cloudbuild.yaml`](cloudbuild.yaml). Give the trigger's service account **Compute Admin**, **Service Account User** and **Compute OS Admin Login**, and optionally set the substitution `_GEMINI_API_KEY`. It does the same as the workflow; use one or the other.

The workflow runs [`deploy/deploy.sh`](deploy/deploy.sh) on the VM, which can also be run by hand on any Ubuntu server (`GEMINI_API_KEY=... bash deploy/deploy.sh`). The production stack (`crimeai/docker-compose.prod.yml`) runs Caddy with the built frontend, the API, a Celery worker and scheduler, YugabyteDB (YSQL + pgvector, password authentication on) and Redis.

## Privacy, law and safety

- No face recognition or biometrics; forecasts describe places and shifts, never people.
- Phone, UPI and account numbers are stored only as keyed hashes; PII is masked before any model or Gemini sees text.
- Every sensitive read (full identifier, proof file, Gemini call, admin action) goes to an audit log the database refuses to edit or truncate.
- Roles (read-only < analyst < police < admin) are checked on the server; sessions use short-lived tokens with rotating, revocable refresh cookies.
- Follows BNS 2023 (IPC mapping), BNSS s.187(3) (default bail) and s.105 (e-Sakshya recordings).
- Every link, series and letter is a proposal; an officer confirms and acts.

## Data

The app runs on synthetic data: 18 months of Delhi incidents across 9 districts with real-world time patterns, plus hidden scenarios the engines find without being told (a three-cell cyber-fraud syndicate, a burglary gang tied by one car, a two-wheeler theft ring, a chain-snatching pair reported in Hindi and English, trader extortion, and custody cases on both deadline tracks). FIRs are written in 13 languages.

`FIR_Organized_5Languages/` holds real-format FIR sample images in Bengali, English, Hindi, Marathi and Tamil, used to test and improve the OCR and FIR reader.

## Tech stack

FastAPI (async Python) · SQLAlchemy 2 · YugabyteDB 2026.1 (YSQL, PostgreSQL 15 compatible) + pgvector · Meko · Tiger Cloud (TimescaleDB) · Solana · Redis · Celery · scikit-learn · sentence-transformers (multilingual-e5) · Google Gemini · spaCy · Tesseract · React 18 + TypeScript + Vite + Tailwind · Leaflet · force-directed graph · Docker Compose · Caddy

## Tests

```bash
cd crimeai/backend
pip install -r requirements-dev.txt
pytest tests/unit            # no services needed
pytest tests/integration     # needs YugabyteDB and Redis; DATABASE_URL must name a *_test database
```

A throwaway YugabyteDB for the integration tests (YSQL on 5433; the bootstrap creates the role, databases and extensions):

```bash
docker run -d --name yb -p 5433:5433 yugabytedb/yugabyte:2026.1.1.2-b9 bin/yugabyted start --background=false --base_dir=/home/yugabyte/yb_data --master_flags=max_clock_skew_usec=10000000 --tserver_flags=max_clock_skew_usec=10000000
YB_APP_ROLE_SUPERUSER=true DATABASE_URL_SYNC=postgresql://crimeai:crimeai_dev_password@localhost:5433/crimeai_test python scripts/yb_bootstrap.py
DATABASE_URL_SYNC=postgresql://crimeai:crimeai_dev_password@localhost:5433/crimeai_test alembic upgrade head
```

### Why YugabyteDB, and what changed

CrimeAI's records now live in YugabyteDB, a distributed, PostgreSQL-compatible database, so one deployment can grow from a single district server to a multi-node cluster spanning a state without changing the application.

| PostgreSQL feature | YugabyteDB version |
|---|---|
| PostGIS `ST_DWithin` radius search | Latitude/longitude bounding box on a range index, then exact haversine distance in SQL (`crime_repository.within_m`) |
| GiST spatial indexes | `(latitude ASC, longitude ASC)` range index |
| pgvector HNSW | `ybhnsw`, YugabyteDB's distributed HNSW (same `USING hnsw` DDL) |
| pg_trgm GIN | `ybgin` (same `USING GIN` DDL) |
| btree time indexes | Range indexes (`created_at DESC`, `district HASH, occurred_at DESC`) so "newest first" reads scan in order instead of across hash shards (migration 0010) |
| `POSTGRES_USER` superuser from the image | `scripts/yb_bootstrap.py` creates the role, databases and extensions as the `yugabyte` admin |

CI runs linting, 330+ backend tests, migrations up and down, the frontend type-check, lint and build, and dependency audits.

## Repository layout

```
crimeai/
  backend/       FastAPI app: api, services, ml (forecast, risk, clustering, similarity, series),
                 nlp (multilingual reader, IPC-BNS crosswalk, redaction, Gemini), workers, migrations, tests
  frontend/      React app, production Dockerfile and Caddyfile
  docker-compose.dev.yml    local stack (YugabyteDB, Redis, API, worker, beat, frontend)
  docker-compose.prod.yml   production stack
deploy/deploy.sh            one-command VM deployment
FIR_Organized_5Languages/   FIR sample images in 5 languages
start.cmd / start.sh        one-command local start
```
