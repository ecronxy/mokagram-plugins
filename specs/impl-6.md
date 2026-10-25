# impl-6: режим призрака и скрытие заблокированных

Код написан, сборка не запускалась. Синтаксис проверен moka-syntax.sh (результат внизу).

## Новые файлы (добавить в Telegram/CMakeLists.txt)
- mokagram/ghost/mokagram_ghost.h
- mokagram/ghost/mokagram_ghost.cpp

API модуля (namespace Mokagram::Ghost): RegisterSettings(), ShouldSendRead(), ShouldSendOnline(), ShouldSendTyping(), ShouldSendStoryView(), HideBlockedEnabled(), HidesBlocked(item).
Флаги кэшируются в bool, пересчитываются по Settings::Changed() (ключи ghost.* и filters.hide_blocked). Кэш читается лениво при первом вызове и заново в RegisterSettings, поэтому Settings::Load() надо вызвать до первого использования (до создания сессий), иначе кэш возьмёт умолчания до первого изменения.
Настройки: ghost.enabled (мастер), ghost.read, ghost.online, ghost.typing, ghost.stories (умолчание true, зависят от ghost.enabled), ghost.offline_on_enable (true), filters.hide_blocked (false, раздел «Фильтры»). Мастер выключен: все ShouldSend* дают true, поведение клиента прежнее.
Одноразовый offline: при включении (ghost.enabled && ghost.online стало true) и offline_on_enable, для всех аккаунтов шлётся account.updateStatus(offline=true) и updates().updateOnline(). Таймеров нет. При выключении вызывается updateOnline() (онлайн вернётся штатно по таймеру tdesktop).

## Изменённые файлы
- data/data_histories.cpp: Histories::sendReadRequests, при ShouldSendRead()==false отменяет таймер, обнуляет willReadTill/willReadWhen, вызывает checkEmptyState по вектору историй, выходит.
- data/data_replies_list.cpp: RepliesList::sendReadTillRequest, ранний выход перед ReadDiscussion (после отмены таймера).
- apiwrap.cpp: оба markContentsRead: локальная пометка остаётся, запрос на сервер не уходит. «Проходной» случай (упоминание/реакция) НЕ сделан: в ядре 7.3.3 в этих функциях его нет, нужен отдельный разбор.
- api/api_send_progress.cpp: SendProgressManager::update, ранний выход при progress>=0 и type!=Speaking. Отмену (progress<0) пропускаем.
- data/data_stories.cpp: markAsRead, sendMarkAsReadRequests (чистит очередь), sendIncrementViewsRequests (чистит очередь и таймер), isQuitPrevent.
- history/view/history_view_list_widget.cpp: подписка на PeerUpdate::Flag::IsBlocked (только при включённом hide_blocked) и на смену filters.hide_blocked; в обработчике через crl::on_main: setPendingResize у всех _items и refreshRows(копия _slice). Заголовок .h не менялся (всё в лямбде конструктора).

Побочные каналы печати (emoji_interactions, history_streamed_drafts) не трогал: не мои файлы.

## Патчи для чужих файлов

### api/api_updates.cpp (Updates::updateOnline, ~строка 1024)
Добавить `#include "mokagram/ghost/mokagram_ghost.h"`. Было:
```
		_lastWasOnline = isOnline;
		_lastSetOnline = ms;
		if (!Core::Quitting()) {
			_onlineRequest = api().request(MTPaccount_UpdateStatus(
				MTP_bool(!isOnline)
			)).send();
		} else {
			_onlineRequest = api().request(MTPaccount_UpdateStatus(
				MTP_bool(!isOnline)
			)).done([=] {
```
Стало:
```
		_lastWasOnline = isOnline;
		_lastSetOnline = ms;
		if (!Core::Quitting()) {
			if (Mokagram::Ghost::ShouldSendOnline()) {
				_onlineRequest = api().request(MTPaccount_UpdateStatus(
					MTP_bool(!isOnline)
				)).send();
			}
		} else {
			// При выходе всегда шлём offline, иначе quitPreventFinished не вызовется.
			const auto offline = !isOnline
				|| !Mokagram::Ghost::ShouldSendOnline();
			_onlineRequest = api().request(MTPaccount_UpdateStatus(
				MTP_bool(offline)
			)).done([=] {
```
(остальное тело ветки Quitting без изменений). _lastWasOnline и локальный lastseen остаются реальными, чтобы не сломать задержку уведомлений и isQuitPrevent.

### history/history_item.cpp
Добавить `#include "mokagram/ghost/mokagram_ghost.h"`. HistoryItem::isEmpty (:4864), было:
```
bool HistoryItem::isEmpty() const {
	return _text.empty()
```
стало:
```
bool HistoryItem::isEmpty() const {
	if (Mokagram::Ghost::HidesBlocked(this)) {
		return true;
	}
	return _text.empty()
```
HidesBlocked первым делом читает кэшированный bool, при выключенной настройке стоит одну проверку.
HistoryItem::toPreview (:4959), в самое начало:
```
	if (Mokagram::Ghost::HidesBlocked(this)) {
		return {};
	}
```
Для превью в списке чатов после смены флага перерисовку чатов даст пересчёт Dialogs при IsBlocked (в HistoryWidget уже есть PeerUpdateFlag::IsBlocked); отдельного обхода всех историй не делал, это за исполнителем истории. Для HistoryWidget/HistoryInner (основная лента, не ListWidget): в history_widget.cpp на IsBlocked вызвать forceFullResize() у _history и _migrated (файл не мой).

## Не доделано
- Проходной случай markContentsRead (упоминания/реакции).
- Скрытие индикатора «печатает», реакций, комментаторов от заблокированных (этап B спеки 2).
- Вызов Mokagram::Ghost::RegisterSettings() интегратором рядом с остальными RegisterSettings (после Settings::Load не нужен, до сессий).
- Побочные каналы печати (emoji_interactions, streamed drafts).
- Возврат «в сети» после выключения режима приходит с ближайшим штатным тиком updateOnline (до onlineUpdatePeriod), форсировать нельзя без правки api_updates (_lastWasOnline приватный).

## Как проверить глазами
Включить ghost.enabled: второй аккаунт не видит «прочитано», «печатает», «в сети»; историй не отмечает просмотренными. Выйти из клиента: статус offline уходит, выход не зависает. hide_blocked: в группе сообщение заблокированного исчезает без дыр (после патча history_item.cpp), разблокировка возвращает его без перезахода (в ListWidget чатов-обсуждений).

## Что нужно от интегратора
CMake (2 файла), вызов RegisterSettings, патчи выше, Settings::Load до сессий.
