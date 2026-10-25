# 11. Локальные закрепы, виртуальные папки, длинные списки стикеров и гифок

Статус: только спецификация. Код в ~/dev/mokagram не менялся, клиент не запускался. Все номера строк по исходникам 7.3.3 в Telegram/SourceFiles на сегодня, перед правкой сверять.

Общий принцип: серверное состояние (закрепы, папки, избранное) не трогаем и не шлём ничего лишнего. Локальное живёт в отдельных структурах, на экране сливается с серверным. Если сервер что-то перезапишет, наше остаётся.

## 0. Общее хранение и настройки

Файл: `tdata/moka_local_<userId>.json` (userId = `session->userId().bare`), рядом с `tdata/moka_settings.json` (его путь строит `cWorkingDir() + u"tdata/moka_settings.json"` в mokagram/settings/mokagram_settings.cpp:43). Привязка к аккаунту через userId, так как Account::_basePath приватный (storage_account.h:339). Один json на аккаунт, секции `pins`, `folders`, `faved`, `gifs`, `recent`. Запись откладывается на 1 с (таймер), атомарно через QSaveFile, чтение один раз при входе аккаунта. Ключи peer: `peerId.value` (число), документы: `id` + `accessHash` + `fileReference` не храним, берём `owner.document(id)` и, если нет в кэше, догружаем (см. раздел 3).

Новая папка: `Telegram/SourceFiles/mokagram/local/` (mokagram_local_store.h/.cpp: чтение/запись json по сессии; mokagram_local_pins.*; mokagram_local_folders.*; mokagram_local_media.*). Регистрация настроек в `Mokagram::Settings::Register` (mokagram_settings.h:44), вызов `Mokagram::Local::RegisterSettings()` в core/application.cpp рядом со строками 325 to 328 (до `Settings::Load()`).

Ключи реестра (Kind как в mokagram_settings.h:14):
- `local.pins.enabled` Bool, умолчание true. Раздел «Локальные закрепы».
- `local.pins.in_folders` Bool, умолчание true, dependsOn `local.pins.enabled`: показывать локальные закрепы и внутри папок.
- `local.pins.mark` Bool, умолчание true: маленький значок у локального закрепа.
- `local.folders.enabled` Bool, умолчание true. Раздел «Виртуальные папки».
- `local.folders.badge` Bool: счётчик непрочитанных на папке.
- `local.media.faved_limit` Int 5..2000, умолчание 200. Раздел «Стикеры и гифки».
- `local.media.gifs_limit` Int 200..5000, умолчание 1000.
- `local.media.recent_stickers` Int 20..1000, умолчание 100 (у AyuGram 100).
- `local.media.recent_display` Int 20..1000 (замена `kRecentDisplayLimit`).
Сами списки (закрепы, правила папок) в реестр не идут, это данные, они в moka_local json. В экране «Кастомизация» только переключатели и числа. Управление списками из контекстного меню чата и меню папок.

## 1. Локальные закрепы чатов

### Что есть сейчас
- Лимиты: data/data_premium_limits.cpp:110-148 (`dialogsPinnedDefault/Premium` 5/10, `dialogsFolderPinned*` 100/200, `topicsPinnedCurrent` 5, `savedSublistsPinned*` 5/100). Единственные потребители `pinnedChatsLimit`: data/data_session.cpp:2913-2936, 2938-2985 (producer максимума для MainList), data/data_chat_filters.cpp:405-410, 843.
- Закрепление: `Window::TogglePinnedThread` window/window_peer_menu.cpp:433-496 (главный список) и :4635-4671 (папка). Проверка лимита `PinnedLimitReached` :389-431 (там же трюк `FindWastedPin`), `Session::pinnedCanPin` data/data_session.cpp:2885-2910. Запрос на сервер `MTPmessages_ToggleDialogPin` window_peer_menu.cpp:455.
- Порядок в списке: `Entry::updateChatListSortPosition` dialogs/dialogs_entry.cpp:209-234, `computeSortPosition` :248-251, константы позиций :44-50. Иерархия ключей: `FixedOnTopDialogPos` (0xFFFFFFFFFFFF000F - index, сейчас используют архив и промо-чат, `kArchiveFixOnTopIndex=1`, `kTopPromotionFixOnTopIndex=2`, dialogs_entry.h:141-142) выше `PinnedDialogPos` (0xFFFFFFFF000000FF - index, серверные закрепы) выше даты. `sortKeyInChatList(filterId)` dialogs_entry.h:129-133: для папки (filterId != 0) вызывает `computeSortPosition` напрямую, `fixedOnTopIndex` не учитывает.
- Виртуальный `fixedOnTopIndex()`: History history/history.cpp:3451, Folder data/data_folder.cpp:373, ForumTopic и SavedSublist возвращают 0.
- Перетаскивание закрепов: dialogs/dialogs_inner_widget.cpp:141-153 (`PinnedDialogsCount`), :2740-2870 (`startReorderPinned`, `countPinnedIndex`, `savePinnedOrder`). Везде в начале списка строки с `fixedOnTopIndex()` пропускаются (:133, :146, :723, :2784). Отправка порядка `ApiWrap::savePinnedOrder` apiwrap.cpp:413.

### Решение (рекомендую)
Локально закреплённый чат получает `fixedOnTopIndex() = kLocalPinBase + позиция` (kLocalPinBase = 100, чтобы не пересекаться с 1 и 2). Тогда:
- сортировка наверх уже работает (FixedOnTopDialogPos), выше серверных закрепов, ниже архива (архив index 1, а наши от 100; чем меньше индекс, тем выше, значит порядок владельца сохраняется);
- вся логика перетаскивания серверных закрепов их пропускает бесплатно (`row->entry()->fixedOnTopIndex()` continue), `isPinnedDialog(filter 0)` остаётся только для серверных, ничего в PinnedList/MainList не трогаем;
- лимит не нужен вообще, в json любое число.

Врезка:
1. history/history.cpp:3451: `return useTopPromotion() ? kTopPromotionFixOnTopIndex : Mokagram::Local::Pins::IndexFor(this);` (0 если не закреплён). Для `ForumTopic` и `SavedSublist` локальные закрепы не делаем в первой версии.
2. После изменения набора: `history->updateChatListSortPosition()` для затронутых чатов (он перечитает `fixedOnTopIndex`, dialogs_entry.cpp:225) и `owner->notifyPinnedDialogsOrderUpdated()`. Подписку на события хранилища ведёт Local::Pins (event_stream `changed(History*)`).
3. Меню: window/window_peer_menu.cpp около :576 (где вызывается `TogglePinnedThread` из Filler). Добавить пункт «Закрепить локально» / «Открепить локально» рядом, и сам пункт «Закрепить» оставить как есть. Альтернатива по настройке: если сервер ответил отказом по лимиту (в `PinnedLimitReached` :389-418, ветка «PinsLimitBox») предложить вместо бокса «Закрепить локально». Это самое естественное место: вместо `controller->show(Box(PinsLimitBox...))` в :415 показать подтверждение и добавить в локальные.
4. Порядок владельца: перетаскивание локальных закрепов. Своё мини-перетаскивание не делаем в шаге 1. В шаге 3 работ: пункты меню «Выше / Ниже / В начало» (как `IndexedList::movePinned`, dialogs/dialogs_indexed_list.cpp:75).
5. Значок: dialogs/ui/dialogs_layout.cpp:628, 676, 774, 814, 1168 условия `(context.filter || !entry->fixedOnTopIndex())` скрывают значок закрепа для fixed. Для локального показать маленький значок (существующий `st::dialogsPinnedIcon` в другом цвете или с точкой) при `Local::Pins::Has(entry)`; настройка `local.pins.mark`.
6. В папках: `sortKeyInChatList(filterId)` (dialogs_entry.h:129): при `filterId != 0` и `local.pins.in_folders` вернуть `FixedOnTopDialogPos(localIndex)`, если чат локально закреплён и серверно в папке не закреплён. `Row::sortKey` dialogs_row.cpp:435 уже ходит туда.

### Риски
- Конфликт с серверным порядком: нет, разные уровни ключей. Если чат закреплён и серверно, и локально, показывать как локальный (выше), серверный не трогать. При откреплении серверно остаётся локальный.
- Синхронизации нет, на втором устройстве не будет. Это ожидаемо, написать в описании настройки.
- Поиск: локальные закрепы в результатах поиска не мешают, порядок поиска отдельный. Проверить, что `PinnedDialogsCount` (:141-153) в `dialogs_inner_widget.cpp:6364` корректно считает только серверные (он их и считает, fixed пропускаются).
- Архив: чат в архиве имеет свой `chatsListFor(entry)` (data_session.cpp:5677), в списке архива локальный закреп работает так же через fixedOnTopIndex. В главном списке архивные чаты не показываются, значит и локальный закреп. Если юзер закрепил чат и убрал в архив, в архиве он будет сверху. Допустимо.
- `unreadOnTop` (`UnreadOnTopDialogPos`, dialogs_entry.cpp:222-224) сочетается нормально: fixed имеет приоритет.
- Режим support (`supportFixChatsOrder`) отдельная ветка, не трогаем.
- Удалён/покинут чат: при `removeChatListEntry` не удалять из хранилища сразу, чистить по `peerIsGone`.
- `fixedOnTopIndex` вызывается часто (отрисовка), реализовать через `flat_map<PeerId,int>` O(log n), не json.

### Порядок работ (малые шаги)
1. mokagram_local_store и Pins: хранилище `std::vector<PeerId>`, загрузка/сохранение, `Has`, `IndexFor`, event `changed`. Без UI.
2. `History::fixedOnTopIndex` + пересортировка. Проверка: добавить 3 id из json руками, увидеть наверху.
3. Пункт меню «Закрепить локально» в Filler (window_peer_menu.cpp ~:576), вызов `updateChatListSortPosition`.
4. Предложение локального закрепа вместо PinsLimitBox (:415).
5. Значок `local.pins.mark`.
6. В папках (`sortKeyInChatList`, настройка `in_folders`).
7. Пункты «Выше/Ниже/В начало».
8. Регистрация настроек и текст в «Кастомизации».

## 2. Виртуальные папки (только в клиенте, правила, без лимитов)

### Что есть сейчас
- `Data::ChatFilter` data/data_chat_filters.cpp:56-388. Правила: `Flag` (Contacts, NonContacts, Groups, Channels, Bots, NoMuted, NoRead, NoArchived), `always`, `never`, `pinned`. Проверка `ChatFilter::contains` :339-388. Серверный формат `tl()` :228.
- `Data::ChatFilters` :390-1160. Список `_list` (data_chat_filters.h:239), `list()` :900, `received()` :491 (синхронизирует `_list` с сервером: удаляет всё, чего нет в ответе, :515-518), `applyOrder` :799 (сверяет размер `_list`), `saveOrder` :869 (шлёт id на сервер), `chatsList(filterId)` :399 (MainList папки), `lookupId` :908 (логика премиума).
- Наполнение списков папок: `Session::refreshChatListEntry` data/data_session.cpp:5694-5715, цикл `for (filter : _chatsFilters->list())` и `filter.contains(history)`. Если локальная папка лежит в `_list`, то чаты в неё попадают без новой логики.
- UI: боковая панель `Window::FiltersMenu` window/window_filters_menu.cpp (список :275-317, меню :736-790, перетаскивание порядка `applyReorder` :791-822), верхние вкладки `ui/widgets/chat_filters_tabs_strip.cpp:151, 414`. Все берут `chatsFilters().list()` (всего 66 обращений в 30 файлах).
- Лимиты: `dialogFiltersCurrent` (10/30): choose_filter_box.cpp:356, settings_folders.cpp:375, 784, window_filters_menu.cpp:362, chat_filters_tabs_strip.cpp:151, 414, window_session_controller.cpp:4175. Лимит чатов в папке `dialogFiltersChatsCurrent` (100/200): edit_filter_box.cpp:147, data_session.cpp:2920-2923, choose_filter_box.cpp:262.

### Решение (рекомендую)
Локальные папки лежат в том же `_list` (чтобы боковая панель, вкладки, пул чатов и обновления списков работали сами), но помечены:
- id из зарезервированного диапазона `>= 0x40000000` (серверные 2..255), функция `IsLocalFilter(id)`.
- Новое поле `ChatFilter::_local` (не уходит в `tl()`), и расширение `contains` дополнительными правилами: `Rules` = набор флагов и условий (бот; личный чат с человеком; группа; канал; непрочитанные; с упоминанием; есть реакции; архивные; закреплённые; контакт/не контакт; по подстроке имени; последняя активность старше N дней; только чаты с премиум-собеседником; конкретные peer всегда/никогда). Хранить в json, парсить в `Local::Folders::Rule`.
- `contains` для локальной вызывает `Local::Folders::Match(rule, history)`, серверная ветка не меняется.
- Права владельца: ни одного вызова MTP для локальных id.

Охранные точки, где локальную папку надо обойти (иначе уйдёт на сервер или сотрётся):
1. `ChatFilters::received` :491-526: слияние делать только по серверным элементам. Перед циклом вытащить локальные из `_list` и после цикла вставить обратно на сохранённые позиции (или в конец). Убрать их из подсчёта `applyRemove` (:515).
2. `applyOrder` :799: сравнение `order.size() != _list.size()` заменить на сравнение с числом серверных; локальные сохраняют позицию относительного порядка (хранится в json `order` отдельно).
3. `saveOrder` :869 и `FiltersMenu::applyReorder` window_filters_menu.cpp:791-822: в запрос на сервер отправлять только серверные id; порядок локальных сохранять в json. Для смешанного перетаскивания хранить единый порядок локально (список id) и применять после ответа.
4. `add/edit/destroy` :547-625, `Api::SaveNewFilterPinned` (api/api_chat_filters.cpp:873), `moreChats*`, `chatlistLinks`: для локальных id возвращаться раньше без запросов.
5. Меню папки window_filters_menu.cpp:736-790: пункты «Изменить» (`EditExistingFilter`, :746), «Удалить», «Прочитать всё» для локальной вести на свой `EditLocalFolderBox` (новый box по образцу edit_filter_box, боксы `boxes/filters/edit_filter_box.cpp`) и локальное удаление.
6. Новая папка: пункт «Создать виртуальную папку» в settings/sections/settings_folders.cpp (около :375 и :784 где считается лимит `dialogFiltersCurrent`) и пункт в меню панели папок. Лимит числа папок для локальных не применять: в местах из списка выше считать `serverCount` без локальных (`list().size()` там, где сравнивается с лимитом, заменить на `Local::Folders::ServerCount()`).
7. `ChatFilters::lookupId` :908: логика «не премиум» двигает индексы. Не ломать: локальные считаются как серверные.
8. Лимит чатов в папке (100/200): для локальной папки не применять, потому что список строится правилами. Явные `always` без ограничения: в `EditLocalFolderBox` не использовать `dialogFiltersChatsCurrent`. `Session::pinnedCanPin(filterId, …)` data_session.cpp:2901-2910 для локальных всегда true, но закрепы внутри локальной папки хранить локально: `Entry::_pinnedIndex` для filterId локальной, не слать `SaveNewFilterPinned`. Первая версия: закрепов внутри локальных папок нет (скрыть пункт), сортировка по дате.
9. Пересчёт при изменениях: правила, зависящие от прочитанности/архива/реакций, уже триггерятся через `refreshChatListEntry`; для правил «давно не было активности» и «имя» добавить пересчёт при старте и по таймеру раз в минуту (`ChatFilters::refreshHistory`, :992).
10. Счётчики: `data/data_unread_value.cpp` и `chatsList(id)->unreadState()` считают по MainList, для локальных заработают сами.

### Риски
- Чужой код предполагает серверные id <= 255, например поля MTP `MTP_int(id)` и сериализацию в `tl()`. Любой путь, который доходит до `ChatFilter::tl()` для локального id, надо отсечь assert-ом в начале `tl()`.
- Размер `list()`, индекс, `lookupId(index)`: при `applyReorder` для не-премиума вызывается `moveAllToFront` (window_filters_menu.cpp:802-806), `_list.insert(begin, ChatFilter())`: у локальной пустой фильтр с id 0 не должен задваиваться. Проверить на пустой серверной и на премиум/не премиум.
- Поиск по чатам в папке: поиск использует `chatsList(filterId)`, должен работать.
- Конфликт имени: у локальной папки заголовок хранить `ChatFilterTitle` как у серверной, чтобы иконки/цвет/эмодзи работали; цвет `colorIndex` для тегов тоже локально.
- Нет синхронизации, при очистке tdata теряется. Дать экспорт в `.mokaset`-подобный json (кнопка «Экспорт папок» в экране «Кастомизация»).
- Список папок на двух клиентах разный: нормально, предупредить в описании.

### Порядок работ
1. `ChatFilter::_local` + `IsLocalFilter`, хранилище `Local::Folders` (id, title, icon, rules, order), загрузка. Без UI.
2. Вставка локальных в `_list` и слияние в `received`/`applyOrder`/`saveOrder` (охранные точки 1-3). Проверка: руками в json одна папка «Боты», видна в панели, чаты ботов в ней.
3. Правила `Match` (боты, личные, группы, каналы, непрочитанные, упоминания, архив, контакт, имя, давность).
4. Охранные точки 4-5 (меню папки, удаление, чтение всех).
5. `EditLocalFolderBox` и пункт создания, лимиты в точке 6.
6. Перетаскивание порядка (смешанное).
7. Счётчик, экспорт, настройки.

## 3. Локальные избранные стикеры, гифки и недавние стикеры

### Что есть сейчас
- Избранные стикеры: `Stickers::checkFavedLimit` data/stickers/data_stickers.cpp:524-549 (срезает по `stickersFavedCurrent`, показывает премиум-тост `FaveStickersToast`), `pushFavedToFront` :551-560, `setFaved` :671, набор `FavedSetId`, `isFaved` :508. Сервер перезаписывает набор: `ApiWrap::requestFavedStickers` apiwrap.cpp:3339-3370 → `Stickers::specialSetReceived` data_stickers.cpp:844. Мутация на сервер: `MTPmessages_FaveSticker`.
- Гифки: `Stickers::addSavedGif` data_stickers.cpp:320-345 (`gifsCurrent` срез :332), приём с сервера `gifsReceived` :1130, запрос `ApiWrap::requestSavedGifs` / `updateSavedGifs` apiwrap.cpp:3098, апдейт `updateSavedGifs` api/api_updates.cpp:2855.
- Недавние: `Stickers::incrementSticker` data_stickers.cpp:207-318. Облачные недавние (`CloudRecentSetId`) серверные. Уже есть локальный пакет `getRecentPack()` (:1834-1847, старый `cRecentStickers`, пишется `session().saveSettings()`, читается storage/storage_account.cpp:2605-2630). Лимит `serverConfig().stickersRecentLimit` (по умолчанию 30, mtproto/mtproto_config.h:31): data_stickers.cpp:286 и storage_account.cpp:2622. Отображение: `kRecentDisplayLimit = 20` и опция `OptionUnlimitedRecentStickers` chat_helpers/stickers_list_widget.cpp:78, 89-101, использование :3444. Сборка списка `StickersListWidget::collectRecentStickers` :3417-3477 (последовательность: облачные, локальный pack, custom).

### Решение
Недавние (самое дешёвое, делаем первым):
- В `incrementSticker` :286 и storage_account.cpp:2622 заменить `serverConfig().stickersRecentLimit` на `max(server, Settings::Int("local.media.recent_stickers"))`. Локальный pack `getRecentPack` уже сохраняется локально и уже сливается в `collectRecentStickers`, поэтому ничего синхронизировать не надо.
- `kRecentDisplayLimit` :78 заменить на `Settings::Int("local.media.recent_display")`, а проверку :3444 оставить через `|| настройка > 20`. Опцию `OptionUnlimitedRecentStickers` оставить (она остаётся для обратной совместимости).
- Облачные недавние не пополнять сверх сервера. Так как у `incrementSticker` стикер сначала идёт в облачный set (:259), в локальный pack попадает то, что вытеснено; поведение уточнить: при `set->stickers.size() > серверный лимит` обрезанные стикеры перекладывать в локальный pack (иначе они потеряются при следующем `requestRecentStickers`).

Избранные стикеры (сервер лимит 5/10, сверх него сервер отвечает ошибкой):
- Серверный набор оставляем как есть, срезаем по серверному лимиту. Когда `checkFavedLimit` :524-549 вытесняет стикер, вместо потери (`set.stickers.pop_back`) отправлять в локальный список `Local::Media::LocalFaved` (json, id документа + порядок).
- Показ: в `StickersListWidget` (collectRecentStickers / ячейки «избранное», `_favedStickersMap`) в раздел «Избранное» добавлять локальные после серверных. Место: chat_helpers/stickers_list_widget.cpp, где собирается `_favedStickersMap` (искать `FavedSetId`, :3013 область). Локальный фав включается через пункт меню стикера «В избранное» (когда сервер полон, добавлять в локальный, тост «Сохранено локально»).
- Серверные `specialSetReceived` (:844, ветка `FavedSetId` :954) не трогаем, локальный список независим. `isFaved` (:508) расширить на локальный (иначе кнопка покажет «добавить»).
- Лимит `local.media.faved_limit`.

Гифки:
- Аналогично: `addSavedGif` :320-345 вместо `_savedGifs.pop_back()` (:333) складывать вытесненную в `Local::Media::LocalGifs`; сервер продолжает получать только до своего лимита.
- Показ: `GifsListWidget` (chat_helpers/gifs_list_widget.cpp) где берётся `savedGifs()`: после серверных дописывать локальные.
- Удаление гифки: из локального списка локально, из серверного через существующий путь.
- `gifsReceived` :1130 перезапишет серверный список, локальные остаются (хранятся отдельно).

Загрузка документов: храним `documentId`, `accessHash`, `dcId`, `fileReference`? File reference протухает. Надёжнее хранить `peer+msgId` недоступно. Реально: хранить `documentId` и пытаться `owner().document(id)`; если нет в кэше, документ попросит `Api::` через `messages.getDocumentByHash` (для гифок) или `messages.getCustomEmojiDocuments` (стикеры). Для стикеров из набора `inputStickerSetID` + `getStickerSet` кэш набора грузится. Риск: стикер удалён из набора или набор не установлен, тогда превью нет. Решение: хранить вместе с id `setId + setAccessHash`, при старте догружать наборы лениво.

### Порядок работ
1. `recent_stickers` и `recent_display` (две правки лимитов плюс настройки).
2. LocalFaved: хранилище + показ + пункт меню + `isFaved`.
3. LocalGifs: хранилище + показ.
4. Загрузка недостающих документов и очистка.
5. Экспорт/импорт в json.

## 4. Прочие лимиты, которые можно обойти только на клиенте

Просмотр data_premium_limits.cpp:15-230 и использований. Что реально сдвигается без ошибок сервера:
- Длина сообщения (`messageLengthCurrent` 4096/8192): уже режется на куски при отправке apiwrap.cpp:4825-4835 (`CutPart`). Можно поставить в настройку «Лимит куска» и отправлять без премиум-лимита (сервер всё равно примет 4096), т.е. ничего не нужно. Это уже работает.
- Длина подписи к медиа (`captionLengthCurrent` 1024/2048): места boxes/send_files_box.cpp:209-212, 2314, 2424, 2828, edit_caption_box.cpp:1271, send_gif_with_caption_box.cpp:127, 604, 748. Обход без ошибок сервера: «слишком длинную подпись» отправлять так: медиа с первыми 1024 символами и остаток следующим сообщением (или медиа без подписи и текстом ниже). Настройка `local.media.long_caption` Bool. Умеренно сложно (альбомы, превью), делать после остального.
- Лимит тулбара «быстрые тона ИИ», `aicompose_tone_saved_limit` (5/20), `bots_create_limit` (20/40), `channels_public_limit` (10/20), `channels_limit` (500/1000), `recommended_channels`, `about_length`, `contact_note_length`, `chatlists_joined`, `chatlist_invites`, `upload_max_fileparts` (4000/8000): серверные, обойти нельзя.
- Локальные заметки к контакту (`contact_note_length_limit` 128): сервер хранит заметку, лимит жёсткий, но можно вести локальные заметки к любому чату отдельным json (по вкусу, вне этого спека).
- Лимит аккаунтов уже снят в mokagram_misc.cpp (`misc.max_accounts`).
- Показ «похожих каналов» `similarChannelsCurrent` (10/100): только отображение, сервер отдаёт столько, сколько отдаёт; лимит применяется на клиенте при показе. Проверить места `similarChannelsCurrent` и срезать по настройке; но если сервер вернул лишь 10 для не премиума, дальше ничего не получить. Выгоды нет, пропустить.
- Закрепы в форумах (`topicsPinnedCurrent` 5) и в «Сохранённом» (`savedSublistsPinned*` 5/100): локальные закрепы по той же схеме, но через `ForumTopic::fixedOnTopIndex` data/data_forum_topic.cpp:734 и `SavedSublist::fixedOnTopIndex` data/data_saved_sublist.cpp:901. Вторая очередь, после раздела 1. Риск: список тем строится отдельным `Dialogs::MainList` форума (data_forum.cpp:51), `PinnedDialogsCount` для тем считается так же, проверить на заполненном форуме.
- Закрепы внутри папки (`dialogFiltersChatsCurrent`) см. раздел 1 пункт 6 (локальные закрепы в серверной папке показывать так же) и раздел 2.

## 5. Общие риски и проверки

- Любой путь, который строит MTP-запрос, обязан быть отсечён для локальных сущностей (локальный закреп не должен вызывать `ToggleDialogPin`, локальная папка не должна дойти до `UpdateDialogFilter`). Для этого `IsLocalFilter(id)` и `Pins::Has(history)` проверять в начале каждой функции с MTP.
- Не менять `PinnedList` и `MainList` (dialogs_pinned_list.h, dialogs_main_list.cpp:20-38): они зависят от серверного порядка и лимитов (`maxPinnedChatsLimitValue`), и они нужны нетронутыми, чтобы не было рассинхронизации.
- Скорость: `fixedOnTopIndex` и `Match` вызываются в горячих путях отрисовки и обновлений списка. Результаты кэшировать, пересчёт только по событиям.
- Тесты: аккаунт с 200 чатами, 12 локальных закрепов, 15 локальных папок; проверить смену аккаунта, архив, поиск, перетаскивание серверных закрепов (должно работать как раньше), премиум и не премиум (`lookupId`), перезапуск (порядок сохраняется).
- Если сервер вернёт старый порядок (`reloadPinnedDialogs`, data_session.cpp около 2880), локальные не меняются, потому что они не в `PinnedList`.

## 6. Рекомендуемая очередь

1. Недавние стикеры (раздел 3, шаг 1): 3 правки, видимый результат за час.
2. Локальные закрепы (раздел 1, шаги 1-5).
3. Избранные стикеры и гифки (раздел 3, шаги 2-4).
4. Виртуальные папки (раздел 2): самая рискованная часть, делать после закрепов, с отдельной веткой.
5. Закрепы тем/«Сохранённого», длинные подписи (раздел 4).
