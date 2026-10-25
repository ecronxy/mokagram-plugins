# Mokagram: система плагинов (черновик спецификации)

Статус: черновик 22.10.2026. Всё, что помечено «контракт», взято из открытого хоста exteraless (GPL-3.0,
github.com/exteraless/exteraless, папка app/exteraless/plugins). Всё, что помечено «предложение», это моё
решение для десктопа, его надо проверить на сборке.

## 1. Файл плагина

Расширение `.plugin`, это обычный Python-файл. Метаданные читаются БЕЗ запуска кода (разбор через `ast`):

| Поле | Смысл |
|---|---|
| `__id__` | уникальный id, 2..32 символа (контракт) |
| `__name__` | название |
| `__description__` | описание |
| `__author__` | автор |
| `__version__` | версия |
| `__icon__` | иконка (предложение: эмодзи или имя из набора) |
| `__min_version__` | минимальная версия клиента |
| `__permissions__` | список разрешений (см. п. 5); пустой список = «ничего не просит» |
| `__hook_filters__` | необязательно, фильтры хуков |

Класс плагина наследуется от `BasePlugin` (файл `mokagram_sdk/base_plugin.py`).

## 2. Жизненный цикл (контракт)

- `on_plugin_load()`: плагин загружен и включён.
- `on_plugin_unload()`: перед выгрузкой.
- `on_app_event(event)`: события приложения `app_start`, `app_stop`, `app_pause`, `app_resume`.
- `create_settings()`: возвращает список элементов настроек (п. 4).

## 3. Хуки и ответ (контракт)

Имена хуков: `send_message_hook`, `on_update_hook`, `on_updates_hook`, `pre_request_hook`, `post_request_hook`.

Каждый хук возвращает `HookResult(strategy, value)`:
- `DEFAULT`: ничего не менять;
- `CANCEL`: отменить действие;
- `MODIFY`: заменить значение (следующие плагины ещё могут менять);
- `MODIFY_FINAL`: заменить значение и остановить цепочку.

Точки подключения в клиенте (проверено по коду 7.3.3, предложение как и куда звать):
- `send_message_hook`: `ApiWrap::sendMessage` (apiwrap.cpp:4762), `ApiWrap::sendAction` (apiwrap.cpp:3842);
- `on_update_hook` / `on_updates_hook`: `Updates::feedUpdate` (api/api_updates.cpp:1629), `Updates::applyUpdates` (1502);
- `pre_request_hook` / `post_request_hook`: `Instance::Private::sendRequest` (mtproto/mtp_instance.cpp:1021).

Данные в хук (предложение): C++ отдаёт сырые TL-байты, Python-SDK разбирает их по схеме `api.tl` (слой 232).

## 4. Настройки плагина (контракт: модели из exteraless)

Switch, Selector, Input, EditText, Header, Divider, Text, Custom. Рисуются в Qt на экране настроек плагина.

## 5. Разрешения (контракт: ключи из exteraless)

`files`, `hooks`, `intents`, `messages.read`, `messages.send`, `native`, `network`, `settings`, `ui`.
Плагин объявляет, что ему нужно, и получает только это. Перед установкой клиент показывает окно со сводкой
и предупреждением «плагин это код с доступом к аккаунту». Статический анализ кода плагина показывает
реально используемые возможности и сверяет с объявленными (идея `scan_capabilities` из exteraless).

## 6. Меню и интерфейс (предложение)

- `add_menu_item(location, text, icon, condition, action)`: пункт в контекстное меню.
  Зоны: `message`, `sticker`, `chat`, `attach`. Контекстное меню сообщения строится в
  history/view/history_view_context_menu.cpp.
- Окно установки: клик по документу `.plugin` перехватывается в data/data_file_click_handler.cpp:70,
  окно на базе `Ui::GenericBox`: название, версия, автор, описание, разрешения, кнопки «Отмена» и «Установить».
- Экран «Плагины» в настройках и в быстром меню, как в exteraGram (скриншоты: ui-refs/).

## 7. Совместимость с плагинами exteraGram

Плагины exteraGram импортируют `android.*`, `java.*`, `org.telegram.*`, `find_class`. Это Android-классы,
на десктопе их нет. Заработают плагины, которые используют только `base_plugin` (хуки, сообщения, меню,
настройки). Долю таких плагинов надо измерить по каталогу @exteraplugins, пока числа нет.

## 8. Порядок работ

1. Хост: встроенный CPython, загрузчик, чтение метаданных, `load/unload`, изоляция ошибок.
2. Хуки в трёх точках и `HookResult`.
3. Окно установки и экран «Плагины».
4. Меню (`add_menu_item`), настройки плагина.
5. Разрешения и журнал действий.
6. Слой совместимости (измерить, потом решить).
