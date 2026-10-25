# Реализация №7: призраки удалённых, «изменено», входы в историю

Сборку не запускал. `moka-syntax.sh`: 0 ошибок для mokagram_history.cpp, _store.cpp, _ui.cpp, history_view_message.cpp, history_widget.cpp, window_peer_menu.cpp.

## Способ вставки призрака и почему
Призрак это локальный HistoryItem (MessageFlag::Local | HasFromId, id = nextLocalMessageId(), дата и автор из снимка, текст «🧹 текст», для медиа «[Фото]»). Создаётся через `History::makeMessage` без addNewItem, поэтому нет ни уведомлений, ни непрочитанного, ни отправки на сервер. В ленту его кладёт уже существующий механизм клиентских сообщений: `registerClientSideMessage` (в конструкторе) + `History::checkLocalMessages()` вставляет такие item по дате в нужное место блоков (тот же путь, что у «присоединился» и сервисных плашек), и повторно вставляет их после каждого загруженного среза. История и shared media не затронуты. Отвергнуты: живой удалённый item (сломает счётчики и _messages), отдельный Element (нужны правки HistoryInner/блоков, не мои файлы). Призрак опознаётся реестром в mokagram_history.cpp (`IsGhost`), рисование и логика не лезут в ядро.

## Что сделано
1. Призраки: при серверном удалении `OnServerDeleted` кроме записи в БД ставит в главный цикл создание призрака (оригинал к этому моменту уже уничтожен). Чужие сообщения только (свои удаления не показываются), без форумов/монофорумов/топиков. При открытии чата и на каждом скролле `OnChatShown` (вызов в `HistoryWidget::preloadHistoryIfNeeded`) одним запросом в фоне берёт удалённые с id >= минимального загруженного, создаёт призраков, повторный запрос только если диапазон вырос вверх. Условие: history.save_deleted && history.show_ghosts. Выключили настройку: все призраки уничтожаются.
2. Приглушение: `Message::draw`, opacity x0.55 при history.dim_deleted, восстановление через gsl::finally.
3. «Изменено»: клик по плашке времени с «изменено» (`Message::bottomInfoTextState`) открывает `ShowRevisionsBox` (прежние версии одного сообщения, новый экран на HistoryBox + PageQuery.minId/id). Работает при history.save_edited и наличии версий (`ensureRevisionsLoaded` зовётся из OnChatShown).
4. Вход: пункт «История удалённых и правок» (иконка menuIconRestore) в меню чата и в меню профиля (window_peer_menu.cpp), виден только при включённом save_deleted или save_edited.
5. Настройки: history.show_ghosts (по умолчанию true, зависит от save_deleted), history.dim_deleted (true, зависит от show_ghosts); живая реакция на смену (уничтожение призраков, перерисовка).

## Изменённые файлы
mokagram/history/mokagram_history.{h,cpp}, mokagram_history_store.{h,cpp} (PageQuery.minId), mokagram_history_ui.cpp (ShowRevisionsBox), history/view/history_view_message.cpp, history/history_widget.cpp, window/window_peer_menu.cpp. data_session.cpp, history_item.cpp, element/list_widget не трогал (не понадобилось).

## Не сделано, нужно от интегратора
- Экран из «Кастомизации»: mokagram_settings_box.cpp не мой. Нужна кнопка/строка, вызывающая `Mokagram::History::ShowChatsBox(controller)`.
- Пункт «Прежние версии» в контекстном меню сообщения (history_view_context_menu.cpp не мой): в точку рядом с `Plugins::AddMessageMenuItems` добавить `if (Mokagram::History::HasRevisions(item)) menu->addAction(u"Прежние версии"_q, [=]{ Mokagram::History::ShowRevisions(controller, item); })`.
- Строки «в профиле» (info/profile/*) нет, только пункт в меню профиля.
- Призрак без форматирования (ents не сохраняются), без превью медиа, только подпись «[Фото]».
- Известные эффекты: призрак с самой свежей датой становится превью в списке чатов (штатная логика insertMessageToBlocks); среди сообщений с той же секундой призрак встаёт после них; после «очистить историю» призраки вернутся при следующем запуске (в БД остаются); в ленте тредов/форумов призраков нет.

## Как проверить глазами
Включить history.save_deleted (show_ghosts и dim по умолчанию). Со второго аккаунта отправить и удалить сообщение в личке и в группе: оно остаётся полупрозрачным с 🧹. Перезайти в чат: призрак на месте. Выключить show_ghosts: пропадают сразу. Включить save_edited, изменить сообщение, кликнуть по «изменено»: окно с прежней версией. Три точки в чате и в профиле: «История удалённых и правок».
