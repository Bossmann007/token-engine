"""Plugin registry for extensible components."""

from __future__ import annotations

from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


class PluginRegistry(Generic[T]):
    """Generic registry for compressors, tokenizers, rankers, etc."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._plugins: dict[str, T] = {}
        self._priority: list[str] = []

    def register(self, name: str, plugin: T, *, priority: int | None = None) -> None:
        self._plugins[name] = plugin
        if priority is not None:
            self._priority.insert(min(priority, len(self._priority)), name)
        elif name not in self._priority:
            self._priority.append(name)

    def get(self, name: str) -> T | None:
        return self._plugins.get(name)

    def all(self) -> dict[str, T]:
        return dict(self._plugins)

    @property
    def ordered(self) -> list[T]:
        return [self._plugins[n] for n in self._priority if n in self._plugins]

    def __len__(self) -> int:
        return len(self._plugins)


# Global registries
compressor_registry: PluginRegistry[Any] = PluginRegistry("compressors")
tokenizer_registry: PluginRegistry[Any] = PluginRegistry("tokenizers")
ranker_registry: PluginRegistry[Any] = PluginRegistry("rankers")
analyzer_registry: PluginRegistry[Any] = PluginRegistry("analyzers")


def register_compressor(name: str, priority: int | None = None) -> Callable[[T], T]:
    def decorator(cls: T) -> T:
        compressor_registry.register(name, cls(), priority=priority)
        return cls
    return decorator
