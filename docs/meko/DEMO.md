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
| 4:10 | Shared Memory → *Grid* → **Correct** or **Forget** a memory | "Every item is visible and correctable; every call is logged in YugabyteDB." |
| 4:40 | Close | "What Meko should do next: projected memories, our feature proposal." |
