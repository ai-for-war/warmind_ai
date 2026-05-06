from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType


PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)


cloudinary_module = ModuleType("cloudinary")
cloudinary_module.config = lambda **_kwargs: None
cloudinary_uploader_module = ModuleType("cloudinary.uploader")
cloudinary_uploader_module.upload = lambda *_args, **_kwargs: {}
cloudinary_uploader_module.destroy = lambda *_args, **_kwargs: {}
cloudinary_utils_module = ModuleType("cloudinary.utils")
cloudinary_utils_module.cloudinary_url = lambda *_args, **_kwargs: ("", {})
cloudinary_module.uploader = cloudinary_uploader_module
sys.modules.setdefault("cloudinary", cloudinary_module)
sys.modules.setdefault("cloudinary.uploader", cloudinary_uploader_module)
sys.modules.setdefault("cloudinary.utils", cloudinary_utils_module)

deepgram_module = ModuleType("deepgram")
deepgram_module.AsyncDeepgramClient = object
deepgram_core_events_module = ModuleType("deepgram.core.events")
deepgram_core_events_module.EventType = object
deepgram_close_module = ModuleType("deepgram.listen.v1.types.listen_v1close_stream")
deepgram_close_module.ListenV1CloseStream = object
deepgram_finalize_module = ModuleType("deepgram.listen.v1.types.listen_v1finalize")
deepgram_finalize_module.ListenV1Finalize = object
deepgram_keep_alive_module = ModuleType("deepgram.listen.v1.types.listen_v1keep_alive")
deepgram_keep_alive_module.ListenV1KeepAlive = object
sys.modules.setdefault("deepgram", deepgram_module)
sys.modules.setdefault("deepgram.core.events", deepgram_core_events_module)
sys.modules.setdefault(
    "deepgram.listen.v1.types.listen_v1close_stream",
    deepgram_close_module,
)
sys.modules.setdefault(
    "deepgram.listen.v1.types.listen_v1finalize",
    deepgram_finalize_module,
)
sys.modules.setdefault(
    "deepgram.listen.v1.types.listen_v1keep_alive",
    deepgram_keep_alive_module,
)

magic_module = ModuleType("magic")
magic_module.from_buffer = lambda *_args, **_kwargs: "application/octet-stream"
sys.modules.setdefault("magic", magic_module)

mongodb_checkpoint_module = ModuleType("langgraph.checkpoint.mongodb")


class _MongoDBSaver:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)

    def close(self) -> None:
        return None


mongodb_checkpoint_module.MongoDBSaver = _MongoDBSaver
sys.modules.setdefault("langgraph.checkpoint.mongodb", mongodb_checkpoint_module)

import app.infrastructure.langgraph.checkpointer  # noqa: E402,F401

service_module = ModuleType("app.common.service")


def _make_service_provider(name: str):
    def _provider():
        raise RuntimeError(f"{name} should be overridden in this test")

    _provider.__name__ = name
    return _provider


def _service_module_getattr(name: str):
    if not name.startswith("get_"):
        raise AttributeError(name)
    provider = _make_service_provider(name)
    setattr(service_module, name, provider)
    return provider


service_module.__getattr__ = _service_module_getattr  # type: ignore[attr-defined]
for _provider_name in [
    "get_analytics_service",
    "get_auth_service",
    "get_backtest_service",
    "get_chat_service",
    "get_image_generation_service",
    "get_image_service",
    "get_lead_agent_service",
    "get_lead_agent_skill_service",
    "get_meeting_management_service",
    "get_notification_service",
    "get_org_service",
    "get_redis_queue",
    "get_sheet_crawler_service",
    "get_sheet_data_service",
    "get_stock_agent_service",
    "get_stock_agent_skill_service",
    "get_stock_catalog_service",
    "get_stock_company_service",
    "get_stock_financial_report_service",
    "get_stock_price_service",
    "get_stock_research_queue_service",
    "get_stock_research_schedule_service",
    "get_stock_research_service",
    "get_stock_watchlist_service",
    "get_tts_service",
    "get_user_service",
    "get_voice_service",
]:
    setattr(service_module, _provider_name, _make_service_provider(_provider_name))

sys.modules.setdefault("app.common.service", service_module)
