"""Discovery Providers Package."""

from scraper.discovery.providers.base import (
    DiscoveryProvider,
    ProviderDescriptor,
    ProviderSearchRequest,
)
from scraper.discovery.providers.registry import ProviderRegistry, provider_registry

__all__ = [
    "DiscoveryProvider",
    "ProviderDescriptor",
    "ProviderSearchRequest",
    "ProviderRegistry",
    "provider_registry",
]
