"""Base class every model adapter implements.

The FastAPI app loads exactly one model per process, once, at startup (see
`app_factory.create_service_app`). Adapters own weight loading and inference;
the web layer stays thin.
"""

from __future__ import annotations

import abc

from .config import Settings, resolve_device


class BasePerceptionModel(abc.ABC):
    name: str = "base"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._loaded = False
        self._device: str | None = None
        self._model = None

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def device(self) -> str:
        return self._device or self.settings.device

    def _resolve_device(self) -> str:
        self._device = resolve_device(self.settings.device)
        return self._device

    @abc.abstractmethod
    def load(self) -> None:
        """Load weights onto the target device. Sets `self._loaded = True`."""

    def unload(self) -> None:
        self._model = None
        self._loaded = False
