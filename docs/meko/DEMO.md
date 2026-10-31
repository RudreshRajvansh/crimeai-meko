# Five-minute demo

Setup before judging: `start.cmd` (or `./start.sh`) with `MEKO_API_KEY` in `crimeai/backend/.env`. Log in as
`police@crimeai.example` (police role: it can decide). Keep the **Shared Memory** page open in a second tab.

| Time | Do | Say |
|---|---|---|
| 0:00 | Shared Memory page | "Three agencies, three separate CrimeAI databases on YugabyteDB. Meko is the memory between them: a private datapack per agency, one shared grid." Point at the agents ↔ datapacks map and the call counters. |
| 0:40 | Demo FIRs → *Courier customs fraud* → **Scan on the FIR page**; switch Meko **OFF** | "Delhi's own records: never seen these numbers. As far as Delhi knows, a new case." |
| 1:10 | Switch Meko **ON** | "Before linking anything, the agents recall the grid." Open the agent trace: each Meko call. "Gurugram and Noida have both seen this caller and this UPI ID." Show *What Meko returned*: every link cites an item Meko returned. |
| 2:00 | The customer-care number also links two KYC frauds. Click **… is not a suspect's** → **Exclude everywhere** | "An agent would have joined unrelated cases. An officer decides it is a public number; the decision is promoted to every agency." |
| 2:40 | Lead *Gurugram Cyber PS*, note *Ring rotates SIMs weekly* → **Confirm series and promote** | "Agents propose, officers decide. This is now institutional knowledge on the grid." Shared Memory page: the promotion call, the promoted series in *promoted only*. |
| 3:20 | Demo FIRs → *Same ring, new SIM and UPI* → scan | "Nothing in common with any earlier case: new phone, new UPI ID. Meko on: matched to the confirmed series by method, with the lead and the officer's note. The customer-care number is ignored." Toggle OFF: "standalone again." |
| 3:50 | Cases → **DL-INV-2026-001** (Saket) | "The investigation agents read the FIR, a witness statement, a CCTV note, a seizure memo and a forensic report together: PW-1 says 8 PM, CCTV says 21:04; the seizure memo swaps two digits of the number plate; and the case went 11 days with no recorded step." **Accept** the plate finding. |
| 4:15 | Open **DL-INV-2026-002** (Malviya Nagar, Hindi) | "Same motorcycle. Meko recalls the approved finding from Saket before the officer reads a word; the Hindi witness's रात 9 बजे contradicts the FIR's शाम 7 बजे." |
| 4:30 | Shared Memory → *Grid* → **Correct** or **Forget** a memory | "Every item is visible and correctable; every call is logged in YugabyteDB." |
| 4:40 | Close | "What Meko should do next: projected memories, our feature proposal." |
