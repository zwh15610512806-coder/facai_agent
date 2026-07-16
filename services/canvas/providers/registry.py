"""Process-local registry for vetted image Provider adapters."""
from __future__ import annotations

from collections.abc import Callable
from threading import RLock

from services.canvas.providers.base import ImageProviderAdapter
from services.canvas.provider_schemas import ModelCapabilities


AdapterFactory = Callable[..., ImageProviderAdapter]


class ProviderRegistry:
    def __init__(self) -> None:
        self._lock = RLock()
        self._adapters: dict[str, ImageProviderAdapter] = {}
        self._factories: dict[str, AdapterFactory] = {}

    def register(self, adapter: ImageProviderAdapter) -> None:
        adapter_type = str(getattr(adapter, "adapter_type", "")).strip()
        if not adapter_type:
            raise ValueError("Provider adapter_type is required")
        with self._lock:
            self._adapters[adapter_type] = adapter

    def register_factory(self, adapter_type: str, factory: AdapterFactory) -> None:
        normalized = str(adapter_type).strip()
        if not normalized or not callable(factory):
            raise ValueError("Provider adapter factory is invalid")
        with self._lock:
            self._factories[normalized] = factory

    def build(
        self,
        adapter_type: str,
        *,
        model_id: str,
        capabilities: ModelCapabilities,
        configuration: object | None = None,
    ) -> ImageProviderAdapter:
        with self._lock:
            factory = self._factories.get(adapter_type)
            if factory is None:
                return self.get(adapter_type)
        return factory(model_id, capabilities, configuration)

    def get(self, adapter_type: str) -> ImageProviderAdapter:
        with self._lock:
            try:
                return self._adapters[adapter_type]
            except KeyError as exc:
                raise LookupError("Image Provider adapter is not registered") from exc

    def adapter_types(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(set(self._adapters) | set(self._factories)))


provider_registry = ProviderRegistry()


def _openai_images_factory(model_id: str, capabilities: ModelCapabilities, _configuration: object | None = None) -> ImageProviderAdapter:
    from services.canvas.providers.openai_images import OpenAIImagesAdapter

    return OpenAIImagesAdapter(model_id=model_id, capabilities=capabilities)


provider_registry.register_factory("openai_images", _openai_images_factory)


def _declarative_http_factory(
    model_id: str,
    capabilities: ModelCapabilities,
    configuration: object | None = None,
) -> ImageProviderAdapter:
    from services.canvas.providers.declarative_http import DeclarativeHttpAdapter

    return DeclarativeHttpAdapter(
        model_id=model_id,
        capabilities=capabilities,
        configuration=configuration if configuration is not None else {},
    )


provider_registry.register_factory("declarative_http", _declarative_http_factory)


__all__ = ["ProviderRegistry", "provider_registry"]
