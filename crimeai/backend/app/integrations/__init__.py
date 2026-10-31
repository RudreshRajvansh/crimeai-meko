"""
Connections to India's existing criminal-justice systems.

CrimeAI is an analytics layer over the systems of record, not a replacement:
CCTNS holds FIRs and chargesheets, ICJS carries them to e-Courts, e-Prisons,
e-Forensics and e-Prosecution, I4C's NCRP and 1930 helpline hold cyber-fraud
complaints, and e-Sakshya holds search, seizure and scene recordings. CrimeAI
reads from them, adds analysis, and hands results back as drafts or exports a
person sends through the official channel.

Each system is reached first through files (the way state pilots start, before
API access is granted under the state's ICJS onboarding) and later through the
API the state provides. See docs/INTEGRATIONS.md.
"""
