"""Factory that turns config (app.core.config.Settings) into concrete provider
instances. This is the ONLY place that should know provider names like
"mock"/"claude"/"noaa" -- everything else depends on the abstract interfaces
in app/providers/base.py.
"""
from functools import lru_cache

from app.core.config import get_settings
from app.providers.base import ImageryProvider, PropertyDataProvider, StormDataProvider, VisionProvider
from app.providers.imagery.mock import MockImageryProvider
from app.providers.imagery.nearmap import NearmapImageryProvider
from app.providers.property.mock import MockPropertyProvider
from app.providers.property.regrid import RegridPropertyProvider
from app.providers.storm.mock import MockStormProvider
from app.providers.storm.noaa import NoaaStormProvider
from app.providers.vision.stub import StubVisionProvider

_STORM_PROVIDERS = {"mock": MockStormProvider, "noaa": NoaaStormProvider}
_PROPERTY_PROVIDERS = {"mock": MockPropertyProvider, "regrid": RegridPropertyProvider}
_IMAGERY_PROVIDERS = {"mock": MockImageryProvider, "nearmap": NearmapImageryProvider}


def _vision_providers() -> dict:
    # Imported lazily: ClaudeVisionProvider requires the anthropic SDK and
    # constructs a client at instantiation time, which needs an API key.
    from app.providers.vision.claude import ClaudeVisionProvider

    return {"stub": StubVisionProvider, "claude": ClaudeVisionProvider}


@lru_cache
def get_storm_provider() -> StormDataProvider:
    settings = get_settings()
    return _STORM_PROVIDERS[settings.storm_provider]()


@lru_cache
def get_property_provider() -> PropertyDataProvider:
    settings = get_settings()
    return _PROPERTY_PROVIDERS[settings.property_provider]()


@lru_cache
def get_imagery_provider() -> ImageryProvider:
    settings = get_settings()
    return _IMAGERY_PROVIDERS[settings.imagery_provider]()


@lru_cache
def get_vision_provider() -> VisionProvider:
    settings = get_settings()
    return _vision_providers()[settings.vision_provider]()
