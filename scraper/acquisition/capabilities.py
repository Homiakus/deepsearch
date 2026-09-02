"""Browser and Execution Capabilities Model (§4, DS-RB03, DS-RB04)."""

from enum import Enum
from typing import Union

from pydantic import BaseModel


class CapabilityLevel(str, Enum):
    UNSUPPORTED = "unsupported"
    PARTIAL = "partial"
    SUPPORTED = "supported"

    @classmethod
    def from_value(cls, val: Union[bool, str, "CapabilityLevel"]) -> "CapabilityLevel":
        if isinstance(val, CapabilityLevel):
            return val
        if isinstance(val, bool):
            return cls.SUPPORTED if val else cls.UNSUPPORTED
        val_str = str(val).lower()
        if val_str in ("supported", "true", "1", "yes"):
            return cls.SUPPORTED
        if val_str in ("partial", "partially"):
            return cls.PARTIAL
        return cls.UNSUPPORTED

    def is_satisfied_by(self, required: "CapabilityLevel") -> bool:
        if required == CapabilityLevel.UNSUPPORTED:
            return True
        if required == CapabilityLevel.PARTIAL:
            return self in (CapabilityLevel.PARTIAL, CapabilityLevel.SUPPORTED)
        return self == CapabilityLevel.SUPPORTED


class BrowserCapabilities(BaseModel):
    """Capabilities provided by a specific execution engine or required by a request."""

    html: CapabilityLevel = CapabilityLevel.SUPPORTED
    javascript: CapabilityLevel = CapabilityLevel.UNSUPPORTED
    dom_mutation: CapabilityLevel = CapabilityLevel.UNSUPPORTED
    css_layout: CapabilityLevel = CapabilityLevel.UNSUPPORTED
    screenshot: CapabilityLevel = CapabilityLevel.UNSUPPORTED
    network_capture: CapabilityLevel = CapabilityLevel.UNSUPPORTED
    cookies: CapabilityLevel = CapabilityLevel.UNSUPPORTED
    local_storage: CapabilityLevel = CapabilityLevel.UNSUPPORTED
    session_persistence: CapabilityLevel = CapabilityLevel.UNSUPPORTED
    iframe: CapabilityLevel = CapabilityLevel.UNSUPPORTED
    shadow_dom: CapabilityLevel = CapabilityLevel.UNSUPPORTED
    websocket: CapabilityLevel = CapabilityLevel.UNSUPPORTED
    service_worker: CapabilityLevel = CapabilityLevel.UNSUPPORTED
    canvas: CapabilityLevel = CapabilityLevel.UNSUPPORTED
    webgl: CapabilityLevel = CapabilityLevel.UNSUPPORTED
    pdf_print: CapabilityLevel = CapabilityLevel.UNSUPPORTED
    file_download: CapabilityLevel = CapabilityLevel.UNSUPPORTED
    user_interaction: CapabilityLevel = CapabilityLevel.UNSUPPORTED

    @classmethod
    def create_minimal(cls) -> "BrowserCapabilities":
        return cls(html=CapabilityLevel.SUPPORTED)

    @classmethod
    def create_full_browser(cls) -> "BrowserCapabilities":
        return cls(
            html=CapabilityLevel.SUPPORTED,
            javascript=CapabilityLevel.SUPPORTED,
            dom_mutation=CapabilityLevel.SUPPORTED,
            css_layout=CapabilityLevel.SUPPORTED,
            screenshot=CapabilityLevel.SUPPORTED,
            network_capture=CapabilityLevel.SUPPORTED,
            cookies=CapabilityLevel.SUPPORTED,
            local_storage=CapabilityLevel.SUPPORTED,
            session_persistence=CapabilityLevel.SUPPORTED,
            iframe=CapabilityLevel.SUPPORTED,
            shadow_dom=CapabilityLevel.SUPPORTED,
            websocket=CapabilityLevel.SUPPORTED,
            service_worker=CapabilityLevel.SUPPORTED,
            canvas=CapabilityLevel.SUPPORTED,
            webgl=CapabilityLevel.SUPPORTED,
            pdf_print=CapabilityLevel.SUPPORTED,
            file_download=CapabilityLevel.SUPPORTED,
            user_interaction=CapabilityLevel.SUPPORTED,
        )

    def satisfies(self, required: "BrowserCapabilities") -> bool:
        for field_name in type(self).model_fields:
            prov_lvl = getattr(self, field_name)
            req_lvl = getattr(required, field_name)
            if not prov_lvl.is_satisfied_by(req_lvl):
                return False
        return True


class BackendDescriptor(BaseModel):
    """Metadata and capability envelope of an acquisition backend."""

    name: str
    version: str = "1.0.0"
    engine_family: str  # "http", "servo", "chromium", "browseroxide", "blitz"
    capabilities: BrowserCapabilities
    experimental: bool = False
    base_cost: float = 1.0
    startup_cost: float = 0.0
    memory_class: str = "low"  # "low", "medium", "high"
    concurrency_class: str = "high"  # "very_low", "low", "medium", "high"
    security_profile: str = "standard"
    max_concurrency: int = 16
