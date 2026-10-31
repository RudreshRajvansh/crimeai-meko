"""
Meko shared memory for CrimeAI.

Each CrimeAI deployment (one police agency) keeps its own YugabyteDB records. Meko is the layer between
agencies: a private datapack per agency for its own case memory, and one shared grid datapack where
agencies post keyed identifier fingerprints and where officer-confirmed series and exclusions are promoted
as institutional knowledge every agency's agents recall before they reason.
"""
