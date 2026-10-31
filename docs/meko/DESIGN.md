# CrimeAI on Meko: design note

## The problem Meko solves here

CrimeAI already links FIRs inside one police agency: its YugabyteDB records join every case that shares a phone,
UPI ID, bank account or vehicle. But a courier-fraud ring in the NCR works across Delhi, Gurugram and Noida, and
those are three agencies with three separate record systems. No agency's database can see the others', and none
should hold the others' complainants. What gets lost between them is exactly what Meko is built to carry: what
each agency has seen, and what officers have learned and decided.

## Who does what

| Actor | Kind | Reads | Writes | Decides |
|---|---|---|---|---|
| Intake agent (`dlp-intake`) | agent | agency datapack (similar local cases, officer notes) | agency case memory, intake conversation, grid sighting | nothing |
| Linker | agent | grid by identifier fingerprint and by method | nothing | nothing: proposes links |
| Briefer | agent | grid knowledge base (SOP documents) | nothing | nothing |
| Curator | agent | – | series, attachments and exclusions to the grid, then `memory_promote` | nothing: acts on an officer's decision |
| Officer (police role) | person | the Meko panel on the FIR page | confirm series, exclude identifier, correct or forget memory | **every link** |
| Partner agencies (Gurugram, Noida) | other CrimeAI deployments | the same grid | their own sightings | their own links |

## Datapacks

| Datapack | Scope | Holds | Why a separate scope |
|---|---|---|---|
| `crimeai-dlp` | Delhi Police only | case memories (redacted summary, method, fingerprints), intake conversations, Meko-extracted facts | complainant narratives never leave the agency |
| `crimeai-grid` | every agency | sightings (fingerprints + method tags + case ref, no narrative), promoted series and exclusions, SOP documents | the only thing agencies share is what linking needs |
| `crimeai-ggm`, `crimeai-noi` | each partner | the partners' own case memories | demo partners behave like real separate deployments |

## Where Meko is used, and why (requirement A2)

| Meko use | Where | Why it is needed |
|---|---|---|
| Datapacks as scopes | agency vs grid | data minimisation between agencies; each agency's narrative stays private |
| Recall before reasoning | `memory_search` per fingerprint + `context_search` by method, before any link is shown | links come only from what Meko returns, so nothing is invented |
| Extracted memories | `conversation_add_message` on intake | Meko extracts durable facts from the redacted FIR into the agency's memory |
| Promotion to shared knowledge | `memory_promote` after an officer confirms a series or an exclusion | an officer's judgement becomes institutional knowledge for every agency |
| Sharing across agencies and agents | the grid | Gurugram's sighting reaches Delhi's intake agent |
| Documents | SOPs in the grid knowledge base, `knowledgebase_search` | next steps cite procedure, not model guesses |

## Meko on and off (requirement A1)

| Same FIR | Meko off | Meko on |
|---|---|---|
| Delhi courier-fraud FIR | "Not seen in any other case": Delhi's records have never seen the number | linked to Gurugram GGM-2026-0412 (same caller and UPI) and Noida NOI-2026-0377 (same UPI) |
| The bank customer-care number in it | would link two unrelated KYC frauds; locally it raises a link alert | after one officer excludes it, every agency's agents ignore it and the local link alert is not raised |
| A later FIR with a new SIM and UPI ID | a standalone case | matched to confirmed series SR-DLP-01 by method, with the lead agency and the officer's note |

## Privacy (requirement A5)

- Raw identifiers never reach Meko. Agencies share HMAC fingerprints keyed with a grid key (`MEKO_GRID_KEY`);
  the same phone fingerprints identically everywhere, and the number cannot be read back.
- The grid holds no narrative. Agency datapacks hold only redacted text (CrimeAI masks phones, Aadhaar, PAN,
  bank and UPI numbers before storage).
- Officer notes and corrections are redacted before they are sent.
- Everything shown as shared context is an item Meko returned, cited by reference (M1, K1), and every Meko call
  is stored in YugabyteDB (`meko_calls`) and viewable on the Shared Memory page.
- Every officer decision, correction and forget also goes to CrimeAI's append-only audit log.

## Visible and correctable context (requirement A4)

The FIR page shows, per scan: the agent trace with each Meko call, what Meko returned (with memory ids and
scores), and what was concluded from it. The Shared Memory page lists what each datapack holds (live
`memory_get_all`) with **Correct** (`memory_update`) and **Forget** (`memory_delete_by_id`), and every call.
