"""Import every model module so app.core.db.Base.metadata sees all tables
before init_db()/create_all() runs. Nothing here needs to be imported
directly elsewhere -- `import app.models` is enough.
"""
from app.models.damage_assessment import DamageAssessment
from app.models.imagery import ImageryAsset
from app.models.job import Job
from app.models.lead import Lead
from app.models.property import Property
from app.models.storm_event import StormEvent
from app.models.tenant import Tenant
from app.models.territory import Territory

__all__ = [
    "DamageAssessment",
    "ImageryAsset",
    "Job",
    "Lead",
    "Property",
    "StormEvent",
    "Tenant",
    "Territory",
]
