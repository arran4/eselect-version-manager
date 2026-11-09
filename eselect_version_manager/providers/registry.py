"""Provider registry for eselect-version-manager."""

from typing import Dict, List, Optional
from .base import BaseProvider
from .go import GoProvider
from .fixture import FixtureProvider
from .unslotted import UnslottedFixtureProvider
from ..errors import UnknownToolError


class ProviderRegistry:
    """Registry managing available toolchain providers."""

    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}
        self._command_map: Dict[str, str] = {}  # command_name -> tool_name

    def register(self, provider: BaseProvider) -> None:
        self._providers[provider.name] = provider
        for cmd in provider.commands:
            self._command_map[cmd] = provider.name

    def get_provider(self, tool_or_command: str) -> BaseProvider:
        # Check by tool name first
        if tool_or_command in self._providers:
            return self._providers[tool_or_command]

        # Check by exposed command name
        tool_name = self._command_map.get(tool_or_command)
        if tool_name and tool_name in self._providers:
            return self._providers[tool_name]

        raise UnknownToolError(
            tool_or_command,
            details={
                "available_tools": ", ".join(sorted(self._providers.keys())),
                "available_commands": ", ".join(sorted(self._command_map.keys())),
            }
        )

    def find_provider_for_command(self, command: str) -> Optional[BaseProvider]:
        tool_name = self._command_map.get(command)
        if tool_name:
            return self._providers.get(tool_name)
        if command in self._providers:
            return self._providers[command]
        return None

    def list_providers(self) -> List[BaseProvider]:
        return list(self._providers.values())

    def list_tools(self) -> List[str]:
        return sorted(self._providers.keys())


def create_default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(GoProvider())
    registry.register(FixtureProvider())
    registry.register(UnslottedFixtureProvider())
    return registry


_DEFAULT_REGISTRY: Optional[ProviderRegistry] = None


def get_default_registry() -> ProviderRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = create_default_registry()
    return _DEFAULT_REGISTRY
