# impl-4: расширение API плагинов (спека 05)

Состояние: все затронутые .cpp проходят проверку синтаксиса без ошибок. Для mokagram_plugins.cpp проверка шла с `-I/usr/include/python3.14` (штатный moka-syntax.sh не знает путь к Python.h). Python-хост прогнан отдельно через `python3 -I` (установка, хеш, права, хуки, хранилище).

## Что сделано
1. SDK (`py/sdk_api.py`, модуль `mokagram_sdk.api`, он же `moka`): `show_toast`, `send_message`, `storage.get/set/delete/keys` (plugin_data/<id>/store.json, атомарная запись, квота 1 МБ, ключ до 128), `get_setting/set_setting`, `log`. Кто вызывает, определяется по файлу плагина в стеке (по `__name__` нельзя: плагины сами задают `__name__` в метаданных).
2. `create_settings()`: в `base_plugin.py` добавлены `Header, Divider, Text, Switch, Selector, Input, EditText`, `on_settings_changed`. Хост регистрирует Switch/Selector/Input в реестре `Mokagram::Settings::Register` с ключами `plugin.<id>.<key>`, раздел = имя плагина. Изменение в реестре доходит до плагина как `on_settings_changed(key, value)`.
3. Хуки: `on_update_hook` (в начале `Updates::feedUpdate`), `on_updates_hook` (в `Updates::applyUpdates`, один раз на самый внешний вызов), `pre_request_hook` (начало `Instance::Private::sendRequest`), `post_request_hook` (начало `processCallback`, фильтр по методу запроса). Все наблюдающие: C++ копирует TL-байты в очередь (256, старые выбрасываются), один рабочий `std::thread` исполняет Python, главный поток Python не трогает. Фильтр по constructor id в C++ (`__hook_filters__` с именами, имя в id через таблицу из api.tl); без подписчиков в горячем пути один атомарный счётчик. Подписка на всё (`"*"`) запрещена, нужно право `hooks.observe` (или `hooks`).
4. Защита от падений: `try/except BaseException` на всех вызовах, 5 ошибок подряд выключают хук, 20 ошибок за минуту отключают плагин (тост), просрочка бюджета (send_message_hook 150 мс, observe 200 мс) 3 раза за минуту выключает хук, результат просроченного `send_message_hook` отбрасывается. `MOKAGRAM_PLUGINS=0` запускает клиент без плагинов.
5. Права: `plugin_grants.json` (id, sha256, список прав) рядом с plugins_state.json. Уровни L0 (ui, storage, settings, background) всегда; L1..L3 по выданному; L4 (`native, raw_api, files.any, network.any, subprocess`) не выдаётся никогда. Выдаётся при установке то, что запрошено в `__permissions__` без L4. Нет права: запись в журнал и `None`, плагин не падает. Лимиты `send_message`: 20 в минуту, 5 получателей за 10 минут, только в чаты из загруженных диалогов, текст до 4096.
6. Журнал действий: `~/.local/share/mokagram/plugin_audit.log` (JSON-строки, ротация 5 МБ x 3), пишет C++ (`plugin_audit`, операция `audit`), не плагин. Пишутся отказы, отправки, тосты, подписки на хуки, отключения, ревью.
7. Модель защиты по хешу: при установке из окна клиента `RecordInstall` сохраняет sha256 и права; при каждой загрузке хеш считается заново, не совпал: состояние `needs_review`, плагин не запускается, в карточке «Плагины» текст и переключатель открывает окно подтверждения, `Approve` пересчитывает хеш и права и запускает. Плагины, установленные до этого, при первой загрузке записываются по текущему файлу (иначе все бы встали). Удаление плагина стирает его запись прав.
8. Рекурсия: SDK-отправка помечается `MarkFromPlugin`, `RunSendMessageHook` и хуки запросов на время плагинной отправки пропускаются; сама отправка уходит из главного потока отложенно (`crl::on_main`), а не из стека хука.

## Новые файлы (в cmake)
- `Telegram/SourceFiles/mokagram/plugins/mokagram_plugin_api.cpp` и `mokagram_plugin_api.h`
- `mokagram/plugins/py/sdk_api.py`, `py/gen_tl.py`, `py/tl_names.py` (генерируется), и включаемые `py/sdk_api.inc`, `py/tl_names.inc` (их генерирует `py/gen_inc.sh`, он теперь сам вызывает gen_tl.py). Для cmake нужны только `mokagram_plugin_api.cpp/.h`; `.inc` по тому же правилу, что `host.inc` (зависимость от них у mokagram_plugins.cpp, если она есть у `host.inc`).

## Изменённые существующие
- `mokagram/plugins/mokagram_plugins.{h,cpp}`: рабочий поток и очередь, фильтры, мост `SetBridge`/`InstallBridge`, нативная функция `_moka_native` для Python, аудит, `RecordInstall/Approve/NotifySettingChanged/HookActive/HookWanted/QueueHook/MarkFromPlugin`, `Drain` переписан на одну строку (безопасно из двух потоков), `Shutdown` сначала останавливает рабочий поток.
- `mokagram/plugins/py/host.py`: права, хеш, needs_review, аудит, регистрация настроек и фильтров, счётчики ошибок/просрочек, `_moka_hook_observe`, `_moka_record_install`, `_moka_approve`, `_moka_settings_changed`, `_moka_install_api`; `_moka_init` теперь принимает третий аргумент (SDK API).
- `mokagram/plugins/py/base_plugin.py`: классы настроек.
- `mokagram/plugins/mokagram_plugin_install.cpp`: `RecordInstall` до `LoadFile`, пропуск `send_message_hook` для плагинных сообщений, карточка `needs_review` с подтверждением, названия новых прав.
- `api/api_updates.cpp`: include и два вызова (`RunUpdateHook`, `RunUpdatesHook`).
- `mtproto/mtp_instance.cpp`: include и два блока (pre в `sendRequest`, post в `processCallback`).

## Не сделано
- Перехватывающие хуки (CANCEL/MODIFY для on_update/pre_request/post_request): по спеке в обычном режиме только после переезда в процесс (P1). Сейчас всё observe, результат плагина игнорируется. Поэтому `kDenied` (список запретов 3.6) не нужен и не сделан.
- Разбор TL в dict (`tl.py`): плагин получает `_TLRaw` (`.name`, `.constructor`, `.to_bytes()`, `.to_dict()` с hex). Таблица имён -> id создана (обновления и методы), полного разбора полей нет.
- Склейка `on_updates_hook` и `on_update_hook` для одного плагина не сделана (хуки независимы).
- Подтверждение окном клиента для первой отправки в новый чат (3.3): вместо него отправка разрешена только в загруженные диалоги плюс лимиты. Остальные подтверждения 3.3 не делались.
- Переключатели прав в окне установки, экран «Журнал» и шестерёнка настроек на карточке: нет (права выдаются как запрошено, журнал читается файлом).
- `get_messages/get_dialogs/http_request/read_file/timer/run_background/ui.*/show_box` не делались (вне заданного минимума).
- Статический анализ «использует, но не объявил» для SDK-вызовов расширен не был.
- Реестр настроек не умеет удалять записи: настройки выгруженного/удалённого плагина остаются в экране до перезапуска.
- Список в `~/dev/mokagram-plugins/mokagram_sdk/` (копия SDK) не трогал: вне владения; туда нужно перенести `Header...EditText`, `on_settings_changed` и api.
- Режим «отдельный процесс» (P1) не делался. Описание в spec 05 п.4: pyhost в bwrap, сокет, kill по таймауту, тот же `moka.*` через `_transport`. Нативный мост `_moka_native` сделан так, что транспорт заменяется одной функцией.

## Как проверить глазами
1. Собрать, положить плагин с `__permissions__ = ["messages.send"]` и вызовом `moka.show_toast("hi")` в `on_plugin_load`: тост появится при запуске. Тот же плагин с `send_message(peer, "x")` отправит сообщение в чат с таким id (id как в `params['peer']` из send_message_hook).
2. Убрать право из `__permissions__` и перезапустить: в логе клиента `нет права messages.send`, в `~/.local/share/mokagram/plugin_audit.log` запись `denied`.
3. Подписка: `__hook_filters__ = {"on_update_hook": ["updateUserTyping"]}`, `__permissions__ = ["hooks"]`, метод `on_update_hook(self, u): print(u.name)`: при наборе текста собеседником в логе `plugin: ...`.
4. Хеш: дописать строку в файл установленного плагина, перезапустить: карточка в «Плагины» с пометкой «изменился», переключатель открывает окно «Подтвердить».
5. Настройки: плагин с `create_settings` из `Switch(key="on", text="...")` появляется в экране «Кастомизация» (после задачи 1) в разделе с его именем.

## Что нужно от интегратора
- Вписать `mokagram/plugins/mokagram_plugin_api.cpp/.h` в Telegram/CMakeLists.txt (рядом с остальными plugins/*.cpp; mokagram_plugin_api.cpp не требует Python.h).
- Убедиться, что `mokagram_settings.cpp` (задача 1) реализует `Register`, `Entries`, `Changed`, `Bool/Int/String`, `SetBool/SetInt/SetString`, они вызываются из моста.
- `Settings::Load()` должен выполняться до первых `Register` плагинов (плагины стартуют в `Application::run`) либо `Register` должен подхватывать значения из файла позже.
- Для проверки синтаксиса `mokagram_plugins.cpp` штатным `moka-syntax.sh` нужен `-I/usr/include/python3.14` (в cmake он уже есть).
- Дымовой тест после сборки: два пункта из «как проверить», особенно закрытие клиента (`Shutdown` теперь джойнит рабочий поток: проверить, что выход не зависает).
