"""What CrimeAI exchanges with each external system, and how far each connection has got."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# Status values: "file" works today through file import/export; "manual" works through user entry;
# "planned" needs the access described in `onboarding` before it can be built against a real endpoint.


@dataclass(frozen=True, slots=True)
class Connector:
    id: str
    name: str
    owner: str
    status: str
    receives: tuple[str, ...]
    sends: tuple[str, ...]
    onboarding: str
    guardrail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CONNECTORS: tuple[Connector, ...] = (
    Connector(
        id="cctns",
        name="CCTNS (state Core Application Software)",
        owner="NCRB / State Crime Records Bureau",
        status="file",
        receives=("Registered FIRs: number, police station, sections, dates, place, brief facts",
                  "Arrest, first remand and chargesheet dates (stop and start the custody clock)"),
        sends=("Analysis write-back: BNS-mapped sections, extracted identifiers, linked cases, series, "
               "custody deadline (JSON for the SCRB to load as case notes)",),
        onboarding="SCRB shares a scheduled CCTNS export (JSON/CSV in docs/INTEGRATIONS.md) and the state "
                   "master codes for police stations, districts and acts; API access follows through ICJS.",
    ),
    Connector(
        id="ncrp",
        name="NCRP / 1930 helpline (I4C)",
        owner="Indian Cyber Crime Coordination Centre, MHA",
        status="file",
        receives=("Cyber-fraud complaints: acknowledgement number, amount, suspect UPI ID, phone, account",),
        sends=("Consolidated freeze/lien request per mule identifier, for the officer to file",),
        onboarding="State cyber cell exports complaints assigned to the state from the NCRP police login; "
                   "lien requests continue through the existing 1930/CFCFRMS workflow.",
    ),
    Connector(
        id="esakshya",
        name="e-Sakshya",
        owner="MHA / state police (BNSS s.105, s.176, s.185)",
        status="manual",
        receives=("Session id (SID) and packet hash of each recording, linked to the case",),
        sends=(),
        onboarding="Investigating officers enter the SID shown in the app; a state feed of SID-to-FIR links "
                   "can replace manual entry. CrimeAI never stores the recordings.",
        guardrail="Flags cases that record a seizure without a linked BNSS s.105 recording.",
    ),
    Connector(
        id="ecourts",
        name="e-Courts (through ICJS)",
        owner="eCommittee, Supreme Court of India",
        status="planned",
        receives=("CNR number, remand and extension orders, next hearing date",),
        sends=(),
        onboarding="State requests ICJS integration; the eCommittee has the ICJS team publish state-specific "
                   "APIs, piloted at one location, using shared act / police-station / district master codes.",
    ),
    Connector(
        id="eprisons",
        name="e-Prisons (through ICJS)",
        owner="MHA / state prison departments",
        status="planned",
        receives=("Undertrial custody periods, for the BNSS s.479 half-sentence flag on the investigation side",),
        sends=(),
        onboarding="Same ICJS onboarding as e-Courts; e-Prisons already flags s.479 eligibility for jails.",
    ),
    Connector(
        id="erss",
        name="ERSS / Dial 112",
        owner="State emergency response centres",
        status="planned",
        receives=("Call volumes by police station and hour (no caller details)",),
        sends=(),
        onboarding="Aggregated counts only, for the reporting-gap view; no caller identities are needed.",
        guardrail="Places and shifts, never people.",
    ),
    Connector(
        id="nafis",
        name="NAFIS / facial recognition",
        owner="NCRB",
        status="excluded",
        receives=(),
        sends=(),
        onboarding="Not integrated by design.",
        guardrail="No biometrics: CrimeAI analyses places, times and case documents, not people's bodies.",
    ),
)
