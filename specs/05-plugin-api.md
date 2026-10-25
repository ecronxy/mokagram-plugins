# 05. API плагинов: хуки, SDK, права, песочница

Статус: спецификация от 22.10.2026, код не менялся и не собирался. Всё, что про «сейчас», проверено по
~/dev/mokagram (tdesktop 7.3.3). Всё, что про «как делать», это предложение. Что я не проверял, помечено «проверить».

## 0. Что есть сейчас (точные места)

| Что | Где |
|---|---|
| Запуск Python | `Start()` в `Telegram/SourceFiles/mokagram/plugins/mokagram_plugins.cpp`, вызов из `core/application.cpp:320` |
| Вызов Python из C++ | `CallStr()` и `Gil` (RAII над `PyGILState_Ensure`) в том же файле, GIL берётся в потоке вызывающего |
| Хук-цепочка | `_moka_hook(name, params_json)` в `plugins/py/host.py:313`, порядок = порядок `_plugins` |
| Единственный живой хук | `RunSendMessageHook()` в `mokagram_plugin_install.cpp:526`, вызов `ApiWrap::sendMessage` (`apiwrap.cpp:4768`) |
| Меню сообщения | `AddMessageMenuItems` из `history/view/history_view_context_menu.cpp:1428` |
| Детектор возможностей | словарь `network: {requests, urllib, ...}` в `host.py:9`, `_moka_parse` (`host.py:15`) |
| Класс плагина и `HookResult` | `plugins/py/base_plugin.py`, копия SDK в `~/dev/mokagram-plugins/mokagram_sdk/` |
| Сборка | `Telegram/CMakeLists.txt:73-80`, `host.inc` и `base_plugin.inc` собирает `py/gen_inc.sh` |

Главные дыры текущего хоста: (а) хук идёт синхронно в главном потоке, плагин может заморозить клиент;
(б) `exec` плагина в том же процессе без ограничений, `import os` даёт всё; (в) прав нет, `__permissions__`
только показывается в окне установки; (г) в `on_update_hook`, `on_updates_hook`, `pre_request_hook`,
`post_request_hook` в C++ вообще нет вызовов, в SDK это пустые заглушки.

## 1. Хуки обновлений и запросов

### 1.1 Точки подключения

| Хук | Функция | Поток | Замечания |
|---|---|---|---|
| `on_updates_hook(updates)` | `Updates::applyUpdates` (`api/api_updates.cpp:1502`) и вход `mtpUpdateReceived` (`:898`) | главный | получает контейнер `Updates` (updates, updateShort, updateShortMessage, updatesTooLong). Звать один раз на контейнер, на самом внешнем вызове (флаг глубины: `applyUpdates` вызывается рекурсивно) |
| `on_update_hook(update)` | `Updates::feedUpdate` (`:1629`) | главный | вызывается и из `feedUpdateVector` (`:303`), и из разностей (`feedDifference`, `feedChannelDifference`), то есть видит и «живые», и догруженные обновления. Один хук на каждое одиночное `Update` |
| `pre_request_hook(req)` | `Instance::Private::sendRequest` (`mtproto/mtp_instance.cpp:1021`), ДО `storeRequest` | любой, проверить: у `Instance::send` есть вызовы не из главного потока (загрузка файлов) | в коде уже есть `SerializedRequest`, из него берём constructor id и байты |
| `post_request_hook(resp, err)` | `Instance::Private::processCallback` (`:1155`), до `handler.done`/`handleError` | поток, где разбирается ответ, проверить | `Response.reply` это `mtpBuffer`, ошибка определяется по `mtpc_rpc_error` |

Важно: `feedUpdate` вызывается ПОСЛЕ проверки pts в `updateAndApply` (`:596-610`, проверить порядок), то есть
отмена обновления на этом уровне не создаёт дыру в pts, но состояние UI расходится с сервером.
Поэтому правила в 1.4.

### 1.2 Как отдать данные плагину

Три варианта:
1. Сырые TL-байты и всё. Дёшево для C++, но каждый плагин пишет парсер. Не годится.
2. Разбор в C++ в dict через Python C API для всех типов. Слой 232 это 3269 строк схемы (`~/Загрузки/tg-diff/new.tl`), ручной код ломается на каждом слое.
3. **Выбрано:** C++ отдаёт сырые байты (`MTPUpdate::write(mtpBuffer&)`, `SerializedRequest` как есть; точную сигнатуру проверить в `mtproto/core_types.h`),
   а разбор делает Python-модуль `mokagram_sdk/tl.py`, **сгенерированный из api.tl** скриптом `gen_tl.py` рядом с `gen_inc.sh`.
   Схема одна на клиент и SDK, зашита в `tl_schema.inc` и обновляется вместе с `Telegram/SourceFiles/mtproto/scheme/api.tl` (тот же файл, из которого клиент генерирует `MTP*`).
   Плюс: версия слоя в SDK всегда равна версии клиента, плагин получает `tl.LAYER` и может проверить.

Формат на стороне Python (как Telethon/Pyrogram, привычно плагинописателям):

```python
{"_": "updateNewMessage", "message": {"_": "message", "id": 5, "peer_id": {"_": "peerUser", "user_id": 1}, "message": "текст", ...}, "pts": 10, "pts_count": 1}
```

Правила: `long` как int, `bytes` как bytes, флаги скрыты (поле есть, если не None), `Vector` как list, `true`-флаги как bool.
Обёртка `TLObject` с `.to_dict()`, `.to_bytes()`, `.constructor` и доступом по атрибутам. `HookResult.value` для MODIFY это
либо такой dict, либо `TLObject`; SDK сериализует обратно (`tl.serialize`) и C++ читает через `MTPUpdate::read()`. Если `read()` вернул false,
результат плагина отбрасывается, в журнал пишется «плагин вернул невалидный TL».

Быстрый путь: для хука, которому нужен один-два поля, не разбирать всё. SDK даёт ленивый разбор (`update.message.id` разбирает ровно путь до поля),
но в v1 достаточно полного разбора плюс фильтры (1.3).

### 1.3 Фильтры, чтобы не тормозить

`feedUpdate` и `sendRequest` это горячий путь (сотни вызовов в секунду при загрузке диалогов). Правила:

1. **Фильтр по constructor id в C++ до входа в Python.** Плагин объявляет `__hook_filters__ = {"on_update_hook": ["updateNewMessage", "updateEditMessage"], "pre_request_hook": ["messages.sendMessage"]}`.
   Хост на загрузке плагина превращает имена в `uint32` через таблицу схемы и кладёт в `std::unordered_set` на хук. Если никто не подписан на этот id, Python не трогается вообще (ноль накладных расходов у пользователей без таких плагинов).
   Хук без фильтра: `on_update_hook` запрещён в обычном режиме (только `"*"` в режиме доверия), чтобы плагин не подписался на всё случайно.
2. **Два вида хуков.** `observe` (по умолчанию): C++ копирует байты, кладёт в очередь, возвращает управление сразу, Python разбирает в своём потоке. Результат игнорируется.
   `intercept` (`@hook(..., intercept=True)` или стратегия не DEFAULT): синхронный, главный поток ждёт с таймаутом, см. 1.5.
3. **Свой поток Python.** Сейчас `Gil` берётся в вызывающем потоке. Добавить один рабочий поток хоста (`std::thread` в `mokagram_plugins.cpp`, очередь + `condition_variable`),
   все вызовы в Python идут только из него. Главный поток никогда не держит GIL и не выполняет Python-код.
4. **Лимит очереди:** 256 событий на плагин, при переполнении старые observe-события выбрасываются, счётчик `dropped` идёт в журнал и в карточку плагина.
5. **Склейка:** `on_updates_hook` и `on_update_hook` на один и тот же апдейт не вызывать дважды для одного плагина, если он подписан на оба (хост помечает контейнер ID и помнит, что он уже отдал).
6. **Свои запросы плагина** (из SDK, п. 2) помечаются в `RequestData` флагом `fromPlugin`, и `pre_request_hook` их пропускает (защита от рекурсии и бесконечных циклов `send_message` → хук → `send_message`).

### 1.4 Как вернуть изменение и отмену

Контракт тот же: `HookResult(strategy, value)`, цепочка по плагинам, `MODIFY_FINAL` обрывает. Ограничения по хуку:

| Хук | CANCEL | MODIFY |
|---|---|---|
| `send_message_hook` | да, `RunSendMessageHook` возвращает false | текст, entities, reply_to, silent |
| `pre_request_hook` | да: C++ возвращает `Error::Local("PLUGIN_CANCELLED")` в `handler.fail` через `crl::on_main` (колбэк обязан вызваться, иначе UI висит ждущим) | тело запроса того же constructor, поменять constructor нельзя. Запрещён для списка запретов (п. 3.6) |
| `on_update_hook` | только для обновлений без pts/qts/seq (typing, online, readHistory, userStatus и т.п.). Для `updateNewMessage`/`updateNewChannelMessage`/`updateEditMessage`/`updateDeleteMessages` CANCEL превращается в «скрыть» (см. ниже) | только текст, entities и медиа-подпись у `message`; ID, pts, peer менять нельзя |
| `on_updates_hook` | нет, только observe + MODIFY вложенных `updates` на тех же условиях | то же |
| `post_request_hook` | нет | v1: только observe. v2: замена `reply` того же constructor, потом `handler.done` разбирает уже новый буфер |

Отмена у pts-обновлений опасна: клиент считает pts применённым, сообщения не будет, при следующей разности оно вернётся.
Поэтому вместо отмены для сообщений вводим явный режим «скрыть»: хост кладёт id в `hiddenMessages` и на уровне `History::addNewMessage` (проверить точное место)
не показывает его и не уведомляет. Это нужно для плагинов-фильтров рекламы и спама. В v1 можно вообще не делать, только MODIFY текста.

Ошибка валидации (плагин отдал мусор, не тот тип, ID поменял): результат игнорируется, цепочка продолжает с прежним значением, запись в журнале, счётчик ошибок плагина.

### 1.5 Таймауты и защита от падений

Бюджеты на синхронный перехват в главном потоке: `send_message_hook` 150 мс, `on_update_hook` 20 мс, `pre_request_hook` 20 мс.
Реализация: главный поток кладёт задачу в очередь рабочего потока и ждёт `wait_for(budget)`. Не успел, то результат отбрасывается, исходные данные идут дальше без изменений.

Проблема: в обычном CPython задачу в потоке принудительно не остановить (GIL, нет cancel). Варианты:
- в процессе: можно только «забыть результат» и отключить плагин после 3 просрочек подряд за минуту; зацикленный плагин при этом съест ядро и GIL, и остальные плагины встанут. Для режима доверия это допустимо, для обычного нет.
- в отдельном процессе (п. 4): главный процесс может убить процесс плагина по таймауту. **Поэтому перехватывающие хуки в обычном режиме разрешаем только после переезда в процесс** (этап P1). До этого обычные плагины получают только observe.
- частичная мера в процессе: `sys.setswitchinterval` и `sys.settrace`-сторож не используем (замедляет всё), вместо этого `PyThreadState_SetAsyncExc` на поток по таймауту: прервёт чистый Python-цикл, но не C-вызов и не `time.sleep` в расширении. Годится как мягкая мера, на неё нельзя полагаться.

Защита от падений:
1. Каждый вызов в Python в `try/except BaseException` (уже есть в `_moka_hook`, продублировать в `_moka_menu_click` и в таймерах). Плюс `catch (...)` вокруг `CallStr` на стороне C++.
2. Счётчик ошибок: 5 исключений подряд в хуке отключают хук, 20 за минуту отключают плагин (`state = error`, тост «Плагин X отключён»). Включить обратно может только пользователь.
3. `faulthandler.enable(file=...)` в `_moka_init` + запись «последний плагин/хук в работе» в `plugins_state.json` перед вызовом. После краха клиента при следующем запуске хост видит «в работе был плагин X» и стартует без него, показывая окно «клиент упал во время работы плагина X, он отключён».
4. Сбой разбора TL не должен ронять клиент: `read()` в C++ возвращает bool, исключений наружу нет.
5. Безопасный режим: запуск с `--no-plugins` или `MOKAGRAM_PLUGINS=0` (`EngineEnabled()` уже есть, добавить ключ окружения в `Start()`).
6. Ограничение размера: байты хука не больше 1 МБ, ответ плагина не больше 1 МБ.
7. Эксклюзивность: на время хука хост держит «изоляцию»: любые вызовы SDK, меняющие чат (send, delete), из синхронного хука складываются в очередь и выполняются ПОСЛЕ возврата хука (иначе реентерабельность в `ApiWrap::sendMessage`).

## 2. SDK для плагинов

Общий принцип: плагин вызывает `moka.*` (модуль `mokagram_sdk.api`, он же `ClientApi`), каждый вызов это сообщение хосту `{op, args}` → ответ.
В процессе (этап 1) это функции, дёргающие C++ через `crl::on_main`. В отдельном процессе (этап P1) те же функции пишут в сокет. **Для плагина это один и тот же код**,
различается только транспорт (`_transport.py`). Все вызовы возвращают данные (JSON-совместимые dict/list/int/str/bytes), никаких объектов Qt.
Блокирующие вызовы синхронны (простой код для автора), в потоке плагина; из хука тоже можно, см. 1.5 (7).

### 2.1 Список вызовов и нужное право

| Вызов | Что делает | Право | Где в C++ |
|---|---|---|---|
| `show_toast(text, icon=None, duration=2.5)` | тост Telegram | `ui` | `Ui::Toast::Show` (`ui/toast/toast.h`) на главном потоке; `text` обрезать до 200 знаков |
| `show_box(screen)` | декларативный экран (2.6) | `ui` | `Ui::GenericBox` / `Window::SessionController::show(Box(...))`, пример `PluginsBox` в `mokagram_plugin_install.cpp` |
| `send_message(peer, text, reply_to=None, silent=False)` | отправка | `messages.send` + подтверждение (3.3) | `Api::MessageToSend`, тот же путь, что `ApiWrap::sendMessage` (`apiwrap.cpp:4762`), с флагом `fromPlugin` |
| `edit_message`, `delete_messages`, `forward_messages` | правка/удаление/пересылка | `messages.send`, удаление ещё `messages.delete` + подтверждение | `ApiWrap::editMessage`, `Data::Histories::deleteMessages` (проверить имена) |
| `get_messages(peer, limit=50, offset_id=0)` | чтение истории | `messages.read` (область: «открытый чат» / «все») | `peer->owner().history(peer)->blocks`, только из локального кэша `Data::Session`, без сети (v1). Сетевая подгрузка отдельным `messages.read.remote` |
| `get_message(peer, id)` | одно сообщение | `messages.read` | `Data::Session::message(peerId, msgId)` |
| `get_dialogs(limit, folder=None)` | список диалогов | `dialogs.read` | `Data::Session::chatsList(folder)` |
| `get_peer(id)` / `get_me()` | краткие данные пользователя/чата (имя, username, тип) | `dialogs.read`; телефон отдаётся только по `account.phone` | `Data::Session::peer(id)` |
| `current_chat()` | какой чат открыт | `ui.read` | `Window::SessionController::activeChatCurrent()` |
| `storage.get/set/delete/keys` | своё хранилище плагина | без права, квота 1 МБ | JSON-файл `~/.local/share/mokagram/plugin_data/<id>.json` (3.5) |
| `get_settings()` / `set_setting(key, v)` | настройки самого плагина | без права | реестр настроек (2.3) |
| `timer.once(sec, fn)`, `timer.every(sec, fn)`, `timer.cancel(h)` | таймеры | `background` | реализуются в потоке хоста, не в Qt: `threading.Timer`-подобная очередь с одним планировщиком |
| `run_background(fn)` | своя фоновая задача | `background` | пул потоков хоста, максимум 2 потока на плагин |
| `http_request(method, url, ...)` | сеть | `network` + домен из списка (3.4) | **только через хост**, не через `urllib` плагина: хост проверяет домен, ставит таймаут, лимит ответа 5 МБ. Прямой `socket`/`urllib` в песочнице закрыт |
| `read_file(path)`, `write_file` | файлы | `files`, только папка плагина и выбранные пользователем | диалог выбора файла клиента, в обычном режиме писать вне папки плагина нельзя |
| `copy_to_clipboard(text)` | буфер | `ui` | `QGuiApplication::clipboard()` |
| `request(method, params)` | сырой MTProto | `raw_api` (только режим доверия) | `MTP::Instance::send` с флагом `fromPlugin`; список запретов 3.6 действует и тут |
| `open_url(url)` | открыть ссылку | `ui` + подтверждение для чужих доменов | `UrlClickHandler::Open` |
| `log(text)` | журнал плагина | без права | уже есть `Drain` / `_say` в `host.py` |

События для плагина (колбэки в `BasePlugin`): `on_plugin_load/unload`, `on_app_event` (уже), плюс предложение `on_chat_open(peer)` и `on_settings_changed(key)`.

### 2.2 Хранилище

- Файл на плагин, JSON, атомарная запись (tmp + rename), квота 1 МБ, ключи строки до 128 знаков.
- Лежит отдельно от кода плагина: `plugin_data/<id>/store.json`. Удаление плагина спрашивает «удалить и данные?».
- Для режима «процесс» плагин сам файл не открывает, всё через `storage.*` (хост пишет).
- Секреты (токены): `storage.set_secret()` кладёт в libsecret/KWallet через `QKeychain`, если он есть в сборке (проверить `Telegram/ThirdParty`), иначе обычный файл с правами 0600.

### 2.3 `create_settings` и реестр настроек

Сейчас `create_settings()` возвращает `[]` (`base_plugin.py`). Предложение:

- Элементы: `Header`, `Divider`, `Text`, `Switch(key, text, default)`, `Selector(key, text, items, default)`, `Input(key, text, default, validator)`, `EditText`, `Custom` (только доверие, п. 2.6).
- **Реестр:** хост хранит `plugin_settings/<id>.json` (значения) и таблицу `key → {type, default, text}` из `create_settings()`. Плагин читает значение `get_setting(key, default)`, пишет `set_setting`. Изменение через UI вызывает `on_settings_changed(key, value)`.
- Рисуется в Qt на экране настроек плагина (шестерёнка в карточке плагина в `PluginsBox`, `mokagram_plugin_install.cpp:~1033`), собирается из `Settings::AddButton`/`Ui::Checkbox`/`Ui::InputField` в стиле остального клиента.
- Реестр нужен, чтобы настройки жили без запущенного Python: экран открывается даже у отключённого плагина (read-only значения), и для процесса-песочницы не нужен вызов в Python на каждое открытие.

### 2.4 Диалоги

`ui.confirm(title, text, ok="Ок", cancel="Отмена") -> bool`, `ui.alert(title, text)`, `ui.prompt(title, label, default) -> str|None`,
`ui.choose(title, items) -> index|None`. Рисуются на `Ui::GenericBox` (`Ui::MakeConfirmBox`, `Ui::MakeInformBox` из `ui/layers/generic_box.h`).
Окно всегда подписано «Плагин X» (имя из метаданных, не из строки плагина), иначе плагин может выдать окно за системное.
Блокирующий вызов: хост ждёт ответ, плагин спит. Не больше одного открытого диалога от плагина, 5 за минуту.

### 2.5 Таймеры и фоновые задачи

Планировщик в рабочем потоке хоста (1.3). `every(sec)` минимум 1 сек, максимум 20 активных таймеров на плагин. Исключение в колбэке не гасит таймер, но идёт в счётчик ошибок (1.5).
На выгрузке плагина все таймеры и задачи отменяются до вызова `on_plugin_unload`. `run_background` получает `cancel_token`, который плагин должен проверять.

### 2.6 Свой интерфейс: декларативные экраны

Плагин не создаёт виджеты. Он возвращает **описание** экрана (JSON), хост рисует его в стиле клиента:

```python
moka.show_box({
  "title": "Мой плагин",
  "items": [
    {"type": "text", "text": "Привет"},
    {"type": "switch", "key": "on", "text": "Включить"},
    {"type": "input", "key": "name", "text": "Имя"},
    {"type": "button", "id": "go", "text": "Сделать"},
    {"type": "list", "items": [{"id": 1, "text": "Пункт"}]},
  ],
  "buttons": [{"id": "ok", "text": "Готово", "primary": True}]
}, on_event=lambda ev: ...)  # ev = {"id": "go"} / {"key": "name", "value": "..."}
```

Типы: `text`, `header`, `divider`, `switch`, `selector`, `input`, `button`, `list`, `image` (только из папки плагина), `progress`.
Ограничения: до 200 элементов, текст до 4000 знаков, нет HTML, нет своих стилей и цветов (цвета только из токенов темы), так плагины не смогут нарисовать
поддельное окно «введите код из Telegram». Рендер на `Ui::GenericBox` с `Ui::VerticalLayout`. События идут колбэком в поток плагина.
Меню: `add_menu_item(location, ...)` уже есть (зоны `message`, `chat`, `profile`, `drawer`, `attach` из SPEC 6). Хост добавляет к пункту маленький значок «плагин» и название, чтобы пункт
нельзя было выдать за системный.
Режим доверия даёт `Custom` через `QWidget` (PySide/PyQt) только в процессе, это отдельный этап и в обычном режиме запрещён.

## 3. Права и защита от дрейнеров

Угроза: плагин это код с доступом к аккаунту. Реальный сценарий кражи: плагин читает сообщения от 777000 (код входа), вызывает `auth.exportAuthorization`, отправляет файлы сессии
(`tdata`) по сети, переводит звёзды и подарки (`payments.transferStarGift`), пересылает сообщения «себе», подписывается на 2FA. Цель защиты: даже вредоносный плагин
в обычном режиме не может этого сделать, а в режиме доверия пользователь явно принял риск.

### 3.1 Уровни прав

| Уровень | Права | Режим |
|---|---|---|
| L0 безопасный | `ui` (тост, диалоги, декларативные экраны), `storage`, `settings`, `background` | обычный, без вопроса при установке |
| L1 чтение | `dialogs.read`, `messages.read` (с областью: текущий чат / выбранные / все), `hooks.observe` | обычный, показывается при установке |
| L2 действия | `messages.send`, `messages.edit`, `messages.delete`, `hooks.intercept`, `clipboard` | обычный, каждое право отдельным переключателем, чувствительные действия с подтверждением (3.3) |
| L3 сеть и файлы | `network` (список доменов), `files` (папка плагина + выбранные) | обычный, домены явно, без «`*`» |
| L4 опасные | `raw_api`, `native`, `files.any`, `network.any`, `subprocess` | **только режим доверия** |

Хранение: `plugin_grants.json` (id, хеш кода, список выданных прав). Объявленные в `__permissions__` права это запрос; выдаёт пользователь в окне установки (окно уже есть: `OpenPluginDocument`, `mokagram_plugin_install.cpp`; сейчас там только показ, нужны переключатели).
Каждое право можно отозвать потом на карточке плагина. Вызов без права: исключение `PermissionDenied` в плагине и запись в журнале.

Сверка с кодом: `_moka_parse` уже определяет `detected` по импортам (`host.py:9`). Расширить словарь на SDK-вызовы: если плагин использует `moka.send_message`, но не объявил `messages.send`, окно установки красным показывает «использует, но не объявил». Статический анализ это подсказка, не защита (обходится `getattr`), защита это 3.7 и 4.

### 3.2 Хеш плагина и перезапрос

- При установке считаем SHA-256 содержимого файла `.plugin`. Запись в `plugin_grants.json`.
- При каждой загрузке (`_moka_load_file`, `host.py:183`) хеш считается заново. Не совпал: плагин НЕ запускается, состояние `needs_review`, в списке бейдж «изменён», по нажатию окно как при установке с различиями (diff метаданных, новые права). Права не наследуются.
- Автоправка файла плагином самим собой (запись в свой `.plugin`) закрыта: папка плагинов в песочнице read-only для самого плагина (4).
- Обновление из каталога: подпись и версия; обновление с расширением прав = перезапрос, без расширения = тихое, но с записью в журнал.

### 3.3 Подтверждение опасных действий окном клиента

Окно рисует клиент (`Ui::GenericBox`), его нельзя пропустить, оно приходит от хоста, а не из Python, и отображает **то, что реально уйдёт**, а не описание от плагина.

Всегда с подтверждением, даже при выданном праве, пока пользователь не нажал «больше не спрашивать» (кроме строки «всегда спрашивать»):
- первая отправка сообщения плагином в каждый новый чат (`peer`), и любая отправка не в текущий открытый чат;
- удаление сообщений, больше 1 штуки;
- пересылка в другой чат;
- любое действие, чей `peer` это пользователь, не бывший в диалогах (потенциальный спам/дрейн);
- любой запрос из списка запретов 3.6, если режим доверия включён;
- скачивание и запуск чего-либо.

Лимиты, даже при подтверждении: `send_message` не более 20 в минуту на плагин (затем автопауза с вопросом), не более 5 разных получателей за 10 минут.

### 3.4 Сеть по списку доменов

- Плагин объявляет `__network__ = ["api.example.com", "*.cdn.example.com"]`, окно установки показывает домены, пользователь принимает или нет.
- Вся сеть плагина идёт через `moka.http_request`, а не через `socket`/`urllib` (в песочнице они закрыты: у процесса нет сетевого неймспейса, 4.2). В процессе доверия сеть открыта.
- Хост проверяет: схема https, домен из списка (точное совпадение или `*.` на один уровень), редиректы только в пределах списка, **IP-адрес после DNS не приватный/локальный** (защита от обращений к `127.0.0.1`, `192.168.*`, `169.254.*`), лимит ответа 5 МБ, таймаут 15 сек, 60 запросов в минуту.
- Исходящее тело запроса на домены вне списка не уходит никогда. Чтобы плагин не смог слить сообщения даже на «разрешённый» домен, дополнительно: права `messages.read` и `network` вместе выдаются с предупреждением «этот плагин сможет отправлять ваши сообщения в интернет» (красное окно).
- Журнал каждого запроса: домен, путь, размер туда/обратно.

### 3.5 Данные плагина и доступ к файлам клиента

- Плагин никогда не видит `tdata`, `~/.local/share/TelegramDesktop` и т.п. (закрыто Landlock, 4.2). В режиме доверия видит всё, и это написано в окне.
- Сообщения от `777000` (служебный чат Telegram, там коды входа и уведомления о новых сессиях) и сообщения, содержащие код входа, **не отдаются** `get_messages` и хукам обычного режима (хост подменяет текст на «[скрыто]»). Фильтр в `Mokagram::Plugins` до сериализации. В режиме доверия отдаётся с красным предупреждением.
- Хранилище плагина изолировано по id: плагин A не читает данные плагина B.

### 3.6 Список запретов (методы MTProto, недоступны плагинам обычного режима ни через `request`, ни через `pre_request` MODIFY)

Сначала выделяем по схеме слоя 232 (`new.tl`, проверено, что методы существуют):
- вход и сессии: `auth.exportAuthorization`, `auth.importAuthorization`, `auth.exportLoginToken`, `auth.acceptLoginToken`, `auth.logOut`, `auth.resetAuthorizations`, `auth.checkPassword`, `auth.recoverPassword`;
- аккаунт: `account.deleteAccount`, `account.updatePasswordSettings`, `account.resetPassword`, `account.confirmPasswordEmail`, `account.resetAuthorization`, `account.resetWebAuthorization`, `account.changeAuthorizationSettings`, `account.invalidateSignInCodes`;
- деньги и подарки: `payments.sendStarsForm`, `payments.sendPaymentForm`, `payments.transferStarGift`, `payments.convertStarGift`, `payments.upgradeStarGift`, `payments.sendStarGiftOffer`, `payments.launchPrepaidGiveaway`;
- права и владение: `channels.deleteChannel`, `channels.editAdmin` (передача прав), `channels.editCreator` (передача владения, проверить имя в схеме);
- боты и веб-вью (кража токенов, автовход): `bots.exportBotToken`, `bots.sendCustomRequest`, `bots.invokeWebViewCustomMethod`, `messages.requestWebView`, `messages.acceptUrlAuth`, `messages.sendBotRequestedPeer`, `messages.startBot` (спам-реклама);
- пользователи: `contacts.block` и `account.updateProfile` массовые, остальные по списку 3.3.

Реализация: таблица `kDenied` (constructor id) в C++, проверяется в `sendRequest` для `fromPlugin` запросов и сверяется после MODIFY от `pre_request_hook` (если плагин попытался заменить тело на запрещённый метод, мы это видим, потому что constructor id меняться не может, а запрещённый метод поменять в разрешённый нельзя).
Таблица генерируется скриптом из `new.tl` по списку имён, чтобы не врать при смене слоя; при несовпадении имени сборка падает с предупреждением.

### 3.7 Журнал действий

- Файл `~/.local/share/mokagram/plugin_audit.log`, формат JSON-строка: время, плагин, id хеш, операция, цель (peer, домен, метод), решение (разрешено/запрещено/пользователь подтвердил/отказал), размер.
- Пишет только хост (C++), не плагин. Ротация 5 МБ × 3.
- Экран «Журнал» на карточке плагина: последние 200 записей, фильтр по плагину. Счётчики за сутки: сообщений отправлено, запросов в сеть, отказов.
- Подозрительное событие (отправка пользователю вне диалогов, запрещённый метод, всплеск сети) показывает тост «Плагин X пытался ...» и ставит его на паузу.

## 4. Перенос в отдельный процесс (один и тот же API)

### 4.1 Архитектура

```
mokagram (C++, главный процесс)
   |-- PluginHost (mokagram_plugins.cpp): реестр, права, журнал, подтверждения, UI
   |-- Transport: unix-сокет (SOCK_SEQPACKET), msgpack/JSON-кадры
   |
   +-- mokagram-pyhost (отдельный процесс, bwrap + Landlock)
          py/host.py + mokagram_sdk + плагины (по умолчанию один процесс на плагин)
```

- Протокол: `{id, op, args}` → `{id, ok, result|error}`, события от хоста в сторону плагина `{ev: "hook", name, tl_bytes}`.
- SDK в плагине это тот же `mokagram_sdk.api`, но функции вызывают `_transport.call(op, args)`. Код плагина не меняется: на этапе 1 `_transport` это прямой вызов C++ (`PyCFunction`), на этапе P1 это сокет.
- Зависимость от главного потока исчезает: хуки отправляются в процесс, главный поток ждёт ответ с таймаутом и при просрочке **убивает процесс** (`SIGKILL`), перезапускает без этого плагина, показывает тост.
- Падение процесса плагина = клиент жив. Это закрывает пункт 1.5 о зацикленных и падающих плагинах.
- Данные хуков: TL-байты и `tl.py` разбор в процессе плагина (не в клиенте), то есть код разбора не может уронить клиент.

### 4.2 Песочница на Linux

Запуск: `bwrap` (bubblewrap) если есть, иначе только Landlock+seccomp через `prctl` в самом `pyhost` (запасной вариант). Проверка наличия `bwrap` при старте, если нет, показываем «защита ограничена» в окне плагинов.

bwrap:
```
bwrap --unshare-all --die-with-parent --new-session \
  --ro-bind /usr /usr --ro-bind /lib /lib --ro-bind /lib64 /lib64 --ro-bind /etc/ssl /etc/ssl \
  --proc /proc --dev /dev --tmpfs /tmp \
  --ro-bind <install>/pyhost /app --ro-bind <plugins_dir>/<id>.plugin /plugin/code.plugin \
  --bind <plugin_data>/<id> /data --bind-try $XDG_RUNTIME_DIR/mokagram-<n>.sock /run/host.sock \
  --setenv HOME /data --clearenv ... python /app/host.py
```
- `--unshare-all` включая `--unshare-net`: у процесса нет сети, наружу только сокет к хосту. Вся сеть через `http_request`.
- Домашней папки, `tdata`, `~/.ssh`, `~/.config` процесс не видит вообще (не смонтировано).
- Landlock (ядро ≥ 5.13, у нас 7.2.5): запрет записи вне `/data` и `/tmp`, запрет `execve` кроме `python`; на случай без bwrap.
- seccomp: запрет `ptrace`, `mount`, `keyctl`, `bpf`, `io_uring_setup`, создания сокетов не `AF_UNIX`.
- cgroup/`prlimit`: `RLIMIT_AS` 512 МБ, `RLIMIT_CPU`, `RLIMIT_NPROC`; один плагин не съест память клиента.
- Python: `-I -S`, запрещённые модули (`ctypes`, `subprocess`, `socket`, `os.system`, `multiprocessing`, `_posixsubprocess`) блокируются `sys.meta_path`-запретом + `audit hook` (`sys.addaudithook` на `open`, `socket.connect`, `subprocess.Popen`, `ctypes.*`). Это второй рубеж, основной рубеж это ядро (bwrap/Landlock): Python-уровень обходится.
- Не-Linux (позже, если будет): macOS `sandbox-exec`, Windows AppContainer. Вне этой спецификации.

### 4.3 Этапы

| Этап | Что | Условие готовности |
|---|---|---|
| P0 | Всё в процессе. Рабочий поток хоста, фильтры, observe-хуки, SDK (2), права и журнал (3), `_transport` как прямой вызов | хук `on_update_hook` по фильтру не тормозит ленту (замер: накладные расходы на `feedUpdate` < 50 мкс без подписчиков) |
| P1 | `pyhost` в bwrap, сокетный транспорт, перехватывающие хуки с kill по таймауту | тот же `hello.plugin` работает без правки; `os.system("id")` и `open("tdata")` в песочнице падают; `time.sleep(100)` в хуке убивается |
| P2 | Один процесс на плагин, лимиты ресурсов, перезапуск при падении | падение одного не влияет на остальные |
| P3 | Режим доверия (4.4) как исключение: хост запускает плагин в процессе клиента | отдельный флаг и красное окно |

### 4.4 Файлы и функции для изменений (по этапам)

P0 (в нашем коде):
1. `mokagram/plugins/mokagram_plugins.{h,cpp}`: рабочий поток, очередь, `CallHook` переписать на `CallHookAsync(name, bytes)` + `CallHookSync(name, bytes, budgetMs)`; таблица фильтров constructor id; `Shutdown` дожидается потока.
2. `mokagram/plugins/py/host.py`: `_moka_hook` разделить на `_moka_hook_observe`/`_moka_hook_intercept`; счётчики ошибок; проверка хеша в `_moka_load_file`; применение прав (`_check(pid, perm)`) в SDK-вызовах.
3. `mokagram/plugins/py/base_plugin.py` и `~/dev/mokagram-plugins/mokagram_sdk/`: `HookResult`, `tl.py`, `api.py`, `storage.py`, `ui.py`; `gen_inc.sh` дополнить (`tl_schema.inc`, `api.inc`, `tl.inc`).
4. Новое `mokagram/plugins/mokagram_plugin_api.{h,cpp}`: реализация вызовов SDK на стороне C++ (toast, send, get_messages, dialogs, settings, audit) и очередь подтверждений.
5. `mokagram/plugins/mokagram_plugin_install.cpp`: переключатели прав в окне установки, `needs_review`, экран журнала и настроек плагина, `RunSendMessageHook` перевести на `CallHookSync` с бюджетом.
6. `api/api_updates.cpp`: вызов `Mokagram::Plugins::RunUpdateHook` в начале `Updates::feedUpdate` (`:1629`) и `RunUpdatesHook` в `Updates::applyUpdates` (`:1502`) и `mtpUpdateReceived` (`:898`). Минимально инвазивно: одна строка в начале функции + early return.
7. `mtproto/mtp_instance.cpp`: `RunPreRequestHook` в начале `Instance::Private::sendRequest` (`:1021`), `RunPostRequestHook` в `processCallback` (`:1155`), флаг `fromPlugin` в `mtproto/details/mtproto_serialized_request.h` (`SerializedRequest`/`RequestData`).
8. `apiwrap.cpp:4762`: `sendMessage` уже зовёт хук; добавить `sendAction` (`:3842`) для медиа/файлов (в SPEC так указано).
9. `Telegram/CMakeLists.txt:73-80`: добавить новые .cpp/.h и `.inc`.

P1: новое `mokagram/plugins/mokagram_plugin_process.{h,cpp}` (`QProcess`/`posix_spawn`, bwrap, сокет `QLocalServer`), `py/pyhost.py`, `py/_transport.py`.

## 5. Режим доверия и обычный

| | Обычный (по умолчанию) | Доверие |
|---|---|---|
| Где выполняется | процесс `pyhost` в песочнице (P1); до P1 в процессе клиента, но без перехватывающих хуков | в процессе клиента, прямой вызов C++ |
| Права | только выданные (L0..L3) | любые, включая L4 (`raw_api`, `native`, `files.any`, `network.any`) |
| Сеть | только через `http_request` по списку доменов | открыта |
| Перехватывающие хуки | да, после P1, с таймаутом и kill | да, с таймаутом без kill (мягкая мера 1.5) |
| Список запретов 3.6 | жёсткий отказ | подтверждение окном для каждого вызова |
| Подтверждения 3.3 | да | да (запрещённые методы), остальное можно выключить |
| Чтение служебных чатов (777000) | скрыто | отдаётся с предупреждением |
| Включение | по умолчанию | флажок на карточке плагина + красное окно «этот плагин получит полный доступ к вашему аккаунту и файлам», ввод слова-подтверждения (имя плагина), права = хеш; при изменении хеша слетает |
| Источник | любой | рекомендуется только свой код или подписанный каталог |

Режим доверия включается только для конкретного плагина и конкретного хеша, а не глобально. Глобального переключателя «разрешить всё» нет.
В списке плагинов доверенные имеют красный бейдж. В журнале 3.7 доверенные действия помечены.

## 6. Совместимость с exteraGram

Мера в SPEC.md п. 7 остаётся. Уточнения:
- Плагины, которые используют `android.*`, `java.*`, `org.telegram.*`, `find_class`, `AndroidUtilities`, `run_on_ui_thread`, `ApplicationLoader`, `XposedHook`/`MethodHook`/`MethodReplacement` (hook метода Java) **не заработают на десктопе**: там нет JVM и классов Android. Это нельзя починить слоем совместимости без реализации Android API, делать не будем.
- Заработают плагины, у которых вся логика в `BasePlugin`, `HookResult`, `send_message_hook`, `on_update_hook`, `add_menu_item`/`MenuItemData`, `create_settings` и стандартная библиотека (`json`, `re`, `datetime`, `requests` через замену).
- Что делаем:
  1. Статический анализ при установке (`_moka_parse`, `host.py:15`) добавляет класс `android` в `detected` и красным пишет «плагин использует Android API, на десктопе не заработает», кнопка «Установить» неактивна (в режиме доверия можно поставить «как есть»).
  2. Заглушки `base_plugin.MethodHook` и т.п. уже есть (`base_plugin.py`), они нужны, чтобы импорт не падал, а вызов `hook_method(...)` бросал понятную `UnsupportedOnDesktop("Android API")`.
  3. Нужные для обычных плагинов функции exteraGram имеют алиасы в SDK: `send_message` (там `send_message(params)` с dict) принимаем в двух формах; `run_on_ui_thread(fn)` реализуем (вызов в главном потоке хоста через `crl::on_main`), `get_last_fragment()`/`BulletinHelper.show_info()` как `show_toast`, `log()`, `requests` перенаправить на `http_request` с тем же списком доменов.
  4. **Измерить долю.** Скачать каталог @exteraplugins (через Telethon-сессию из памяти, не отсюда), прогнать `_moka_parse`, посчитать: сколько плагинов импортируют только `base_plugin`/`ui.*`/stdlib, а сколько `android`/`java`. До замера цифру не называть.

## 7. Порядок работ (предложение)

1. P0.1 рабочий поток + `CallHook` через очередь + таймаут для `send_message_hook` (самое видимое, ломается меньше всего).
2. P0.2 `tl.py` из схемы + хуки `on_update_hook`/`on_updates_hook` как observe с фильтрами (одна строка в `feedUpdate`).
3. P0.3 SDK: `show_toast`, `storage`, `get_setting`, `create_settings` + реестр, `ui.confirm`.
4. P0.4 права, хеш, журнал, окно установки с переключателями, домены `http_request`.
5. P0.5 `pre_request_hook`/`post_request_hook` (observe, потом MODIFY), `kDenied`.
6. P1 процесс + bwrap/Landlock, перенос перехватывающих хуков в процесс.
7. P0/P1.x `send_message`, `get_messages`, `get_dialogs`, `show_box` (декларативные экраны).
8. Режим доверия после P1.

## 8. Что не проверено

- Потоки, из которых реально вызываются `Instance::Private::sendRequest` и `processCallback` (нужно проверить по `mtp_instance.cpp` и `mtproto/session.cpp`).
- Сигнатуры `MTPUpdate::write/read` и порядок `updateAndApply` → `feedUpdate` (для 1.4).
- Есть ли `libsecret`/`QKeychain` в сборке.
- Имена `channels.editCreator` и функций удаления сообщений в `Data`/`ApiWrap` (помечено «проверить»).
- Реальную цену `feedUpdate` с хуком: замерить, после P0.2.
