"""Mokagram SDK: базовые классы плагина (скелет, 22.10.2026).

Имена хуков и стратегий повторяют контракт exteraless (GPL-3.0). Реализация своя.
Хост на C++ вызывает методы этого класса; сейчас это заглушки, чтобы спецификация была исполняемой.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class HookStrategy(str, Enum):
    DEFAULT = "DEFAULT"          # ничего не менять
    CANCEL = "CANCEL"            # отменить действие
    MODIFY = "MODIFY"            # заменить значение, следующие плагины ещё видят его
    MODIFY_FINAL = "MODIFY_FINAL"  # заменить и остановить цепочку


@dataclass
class HookResult:
    strategy: HookStrategy = HookStrategy.DEFAULT
    value: Any = None


@dataclass
class MenuItem:
    location: str                      # "message" | "sticker" | "chat" | "attach"
    text: str
    icon: Optional[str] = None
    condition: Optional[Callable[[Any], bool]] = None
    action: Optional[Callable[[Any], None]] = None


class BasePlugin:
    """Наследуйте и переопределяйте нужные методы. Метаданные задаются переменными модуля:
    __id__, __name__, __description__, __author__, __version__, __icon__, __min_version__, __permissions__.
    """

    def __init__(self) -> None:
        self._menu_items: list[MenuItem] = []

    # жизненный цикл
    def on_plugin_load(self) -> None: ...
    def on_plugin_unload(self) -> None: ...
    def on_app_event(self, event: str) -> None: ...   # app_start, app_stop, app_pause, app_resume
    def create_settings(self) -> list: return []

    # хуки: возвращайте HookResult
    def send_message_hook(self, params: dict) -> HookResult: return HookResult()
    def on_update_hook(self, update: Any) -> HookResult: return HookResult()
    def on_updates_hook(self, updates: Any) -> HookResult: return HookResult()
    def pre_request_hook(self, request: Any) -> HookResult: return HookResult()
    def post_request_hook(self, response: Any, error: Any = None) -> HookResult: return HookResult()

    # интерфейс
    def add_menu_item(self, item: MenuItem) -> None:
        self._menu_items.append(item)
