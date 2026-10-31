# Meko feature proposal: projected memories

**One sentence:** let an agent publish a *projection* of a private memory into another datapack, with only the
fields a policy allows, kept verbatim, linked back to its source, and updated or forgotten when the source is.

## 1. The friction we hit

CrimeAI keeps each police agency's case memory in a private datapack and shares a minimised sighting on a grid
datapack. Building it on Meko, we ran into three problems with one root cause.

- **Two copies, no link between them.** Learnings and promotion never cross datapacks, so the intake agent writes
  the case twice: the full memory in the agency datapack and a hand-minimised sighting in the grid. Meko does not
  know they are the same fact.
- **Forgetting does not cascade.** When an officer forgets or corrects a case, the grid sighting stays as it was.
  Our workaround is a local `meko_memories` table recording every id we write, so `forget` can chase both copies by
  hand. Any agency that skips this leaves stale or wrongly linked identifiers on the shared grid.
- **Fields get paraphrased.** `memory_add` runs model-based extraction, which can reword or merge text. The fields
  linking depends on (fingerprints such as `UPI-7F3A9C21D0`, case refs, series ids) must survive exactly, so we
  phrase every memory around regex-parseable tokens and parse whatever Meko returns. There is no way to say "keep
  these fields verbatim".

## 2. The feature, in Meko's terms

A **projection** is a memory in a target datapack derived from a memory in a source datapack the caller can
write to. It carries:

- a **template** and a **field allowlist**: only listed fields (from the source memory's metadata) are rendered,
  verbatim, with no extraction;
- **lineage**: `source_datapack_id`, `source_memory_id`, and the policy used;
- **cascade rules**: when the source is updated, re-project; when it is forgotten, forget the projection;
- normal behaviour otherwise: the projection can be searched, recalled and promoted in the target datapack.

Readers of the target datapack see only the projection, never the source.

## 3. Interface

New MCP tool `memory_project`:

```json
{
  "tool": "memory_project",
  "arguments": {
    "source_datapack_id": "dp-dlp",
    "memory_id": "7f1c2a40-…",
    "target_datapack_id": "dp-grid",
    "template": "Sighting: case {case_ref} involved identifiers {tokens}. MO tags: {mo_tags}.",
    "fields": ["case_ref", "tokens", "mo_tags"],
    "verbatim": true,
    "on_source_update": "reproject",
    "on_source_forget": "cascade",
    "agent_id": "crimeai-dlp-intake"
  }
}
```

Response:

```json
{
  "projection_id": "pj_3b9e…",
  "target_memory_id": "c41d…",
  "stored_text": "Sighting: case DLP:FIR/101/2026 involved identifiers PH-1A2B3C4D5E, UPI-7F3A9C21D0. MO tags: courier-customs, upi.",
  "lineage": {"source_datapack_id": "dp-dlp", "source_memory_id": "7f1c2a40-…"},
  "policy": {"verbatim": true, "on_source_update": "reproject", "on_source_forget": "cascade"}
}
```

Companions: `memory_lineage(memory_id)` returns a memory's projections or source; `memory_search` results gain a
`projection_of` field so agents can tell first-hand memory from projected memory.

## 4. Scenario

**Before.** A Delhi officer forgets case DLP:FIR/101/2026 because the complainant withdrew it. The agency memory
goes, but its grid sighting keeps linking the case's UPI ID to Gurugram and Noida cases until someone notices.
Gurugram's intake agent keeps proposing a link that no longer exists.

**After.** The sighting is a projection with `on_source_forget: cascade`. Forgetting the agency memory removes the
sighting in the same call, the trace records both, and Gurugram's next recall no longer returns it. When an officer
corrects the method tags instead, the sighting is re-projected with the new tags, verbatim.

## 5. Why it is new

Context layers today share by copying, or by promoting within one scope. None offers a policy-limited, verbatim,
lineage-tracked projection across scopes with cascading forget. That is exactly what data-protection law asks of
shared records (purpose limitation, minimisation, and erasure that reaches every copy; India's DPDP Act 2023
among them), and it is what multi-organisation agent systems need: police agencies, hospital networks, banks
sharing fraud signals.

## 6. Risks and limits

| Risk | Mitigation |
|---|---|
| Leakage through the template (a free-text field slips a narrative onto the grid) | Field allowlists are set per target datapack by its maintainers; free-text fields need explicit opt-in; an optional PII scan on projected text |
| Inference across projections (re-identifying a person from many sightings) | Projections inherit the target's access roles; rate limits per source agent; aggregate-only views for viewers |
| Abuse: flooding a shared datapack | Quotas per source datapack, and target maintainers can suspend a source |
| Cost of cascades | Lineage is an index on the target memory; cascades are queued and appear in the trace |
| Stale projections when a source datapack is deleted | Source deletion cascades or orphans per policy; orphans are flagged in `memory_lineage` |

## Evidence

Our build datapack (`crimeai-build`) records the decisions this proposal grew from: the two-write intake, the
`meko_memories` index for manual cascades, and the token-based memory contract.
