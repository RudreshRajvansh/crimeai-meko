"""API v1 router."""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    alerts,
    analytics,
    auth,
    crimes,
    fir,
    graph,
    hotspots,
    integrations,
    intel,
    ml,
    nlp,
    patrol,
    reports,
    simulation,
    system,
    users,
    websockets,
)

router = APIRouter()

router.include_router(auth.router,        prefix="/auth",       tags=["Authentication"])
router.include_router(users.router,       prefix="/users",      tags=["Users"])
router.include_router(crimes.router,      prefix="/crimes",     tags=["Crimes"])
router.include_router(alerts.router,      prefix="/alerts",     tags=["Alerts"])
router.include_router(analytics.router,   prefix="/analytics",  tags=["Analytics"])
router.include_router(fir.router,         prefix="/fir",        tags=["FIR Analysis"])
router.include_router(graph.router,       prefix="/graph",      tags=["Link Analysis"])
router.include_router(hotspots.router,    prefix="/hotspots",   tags=["Hotspots"])
router.include_router(integrations.router, prefix="/integrations", tags=["Integrations"])
router.include_router(intel.router,       prefix="/intel",      tags=["Investigative Intelligence"])
router.include_router(ml.router,          prefix="/ml",         tags=["ML Services"])
router.include_router(nlp.router,         prefix="/nlp",        tags=["NLP Services"])
router.include_router(patrol.router,      prefix="/patrol",     tags=["Patrol Optimization"])
router.include_router(reports.router,     prefix="/reports",    tags=["Reports"])
router.include_router(simulation.router,  prefix="/simulation", tags=["What-If Simulation"])
router.include_router(system.router,      prefix="/system",     tags=["System"])
router.include_router(websockets.router,  prefix="/ws",         tags=["WebSockets"])
