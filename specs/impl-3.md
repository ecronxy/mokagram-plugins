# Реализация №3: история, анти-удаление, фильтры

Все файлы проходят `moka-syntax.sh` без ошибок. Сборку не запускал.

## Сделано
1. Хранилище `Store` (SQLite C API, `<sqlite3.h>`): одна БД на аккаунт `tdata/mokagram/<uniqueId>/history.sqlite`, WAL, схема по спеке (индекс (peer,kind,event,id)), user_version=1, повреждённая БД уходит в `.bad`. Писатель и читатель это два фоновых потока с отдельными соединениями, запись пачками до 256 в одной транзакции, потоки спят на condvar (без таймеров). Счётчики и подсказка «есть правки» живут в памяти, наполняются одним запросом в фоне. Страницы читаются keyset-ом по 50. Очистка по дням/МБ/записям на чат каждые 500 записей, auto_vacuum incremental.
2. Запись снимков: `OnServerDeleted` (до `notifyItemsAboutToBeDestroyed`, обе функции удаления) и `OnBeforeEdit` (перед `applyEdition`, пропускает «правки» без смены текста и edit_date). Поведение клиента не меняется. Секретных чатов в tdesktop нет. Боты пишутся только при history.save_for_bots.
3. Экран истории: `ShowHistoryBox` (удалённые/правки по чату, кнопка «Ещё», переключатель), `ShowChatsBox` (чаты по убыванию записей), оба в `mokagram_history_ui.cpp`.
4. Фильтры: `QRegularExpression`, компиляция один раз в иммутабельный набор, простые паттерны склеиваются, кэш результата по FullMsgId с версией набора (лимит 20000), лимиты 500 символов паттерна и 4096 текста, свои сообщения и сервисные не скрываются. Хранятся в `tdata/mokagram_filters.json`. Подключено к `Element::isHidden()`. Есть history.hide_blocked и переключатель «показать скрытое» в памяти. Редактор: `ShowFiltersBox(controller, peerId)` с проверкой вживую.
5. `RegisterSettings()`: раздел «История и фильтры», ключи history.save_deleted, save_edited, save_for_bots, filters_enabled, hide_blocked, mark (🧹), keep_days (30), keep_mb (256), keep_per_chat (5000). Всё приватное по умолчанию выключено.

## Новые файлы (в cmake)
mokagram/history/mokagram_history.{h,cpp}
mokagram/history/mokagram_history_store.{h,cpp}
mokagram/history/mokagram_history_filters.{h,cpp}
mokagram/history/mokagram_history_ui.cpp

## Изменённые существующие
- data/data_session.cpp: include, `OnServerDeleted(toDestroy)` в `processMessagesDeleted` и `processNonChannelMessagesDeleted`, `OnBeforeEdit(...)` в `updateEditedMessage`.
- history/history_item.cpp: include, `ForgetFilterResult(this)` в начале `applyEdition`.
- history/view/history_view_element.cpp: include, `isHidden()` = `isHiddenByGroup() || FilterHidden(data())`.

## Не сделано
- «Призрак» удалённого сообщения в ленте и метка «удалено» в `drawInfo`: нужны живая вставка локального item и правки history_view_message.cpp; без призрака метка бессмысленна, поэтому файл не трогал. Сейчас удалённое видно только в экране истории.
- Плашка «изменено» кликабельной, пункты контекстного меню (history_inner_widget.cpp не мой файл), вход в меню чата: не делал.
- Предикаты в списке чатов, уведомлениях, поиске (п. 3.4 и 6.6), пока скрытие только в ленте.
- Сущности (ents) пока не сохраняются, только plain-текст и подпись медиа. LRU страниц, FTS5, экспорт, копия медиа, кнопки очистки в настройках: нет. Dim-действие фильтра не сделано (только скрытие).
- Таймаута match limit нет (в Qt 6 нет API), защита лимитами длины.
- Флаш очереди при выходе: сделан в деструкторе Store (при закрытии сессии), отдельного хука на Quit нет.

## Проверка глазами
Включить history.save_deleted/save_edited, со второго аккаунта изменить и удалить сообщение, открыть `ShowChatsBox`/`ShowHistoryBox` (пока нужна точка входа, см. ниже). Фильтры: включить history.filters_enabled, добавить в `ShowFiltersBox` паттерн, сообщение исчезает из ленты.

## Нужно от интегратора
1. В cmake: добавить 4 новых файла и слинковать sqlite3 (в Arch `/usr/include/sqlite3.h`, `find_package(SQLite3)` и `SQLite::SQLite3` в target_link_libraries Telegram; в самих исходниках tdesktop sqlite не используется).
2. Вызвать `Mokagram::History::RegisterSettings()` при старте, после `Settings::Load()`/до построения экрана настроек.
3. Точки входа: кнопки в разделе настроек и меню чата на `ShowChatsBox`, `ShowHistoryBox(controller, peerId, Kind)`, `ShowFiltersBox(controller, peerId)`; в меню чата также «показать скрытое» через `SetShowHiddenInChat(peerId, bool)`.
