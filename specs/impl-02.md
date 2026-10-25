# impl-02: режим стримера

## Сделано
- Модуль mokagram/streamer: Field, Active, ActiveValue (distinct), Changed (фильтр ключей streamer.*), Mask (телефон `+• ••• ••• •• ••`, `@•••••` 5..16, `t.me/••••••`, ID `•••••••••`, имя `А•••`), MaskUrl, ForCopy, CopyBlocked (с тостом), SetClipboard, Wrap. Флаги хранятся в реестре настроек (без своего json): streamer.enabled, phone, username, link, id, name, notify, copy (Choice: 0 настоящее, 1 не копировать, 2 маска). Дефолты как в спеке.
- info_profile_values.cpp: PhoneValue, UsernameValue, NameValue (маска только на своё имя), PhoneWithSpoilerValue (без спойлера при маске), PhoneOrHiddenValue (без ссылки с реальным номером), CopyPhoneToClipboard(+перегрузка с UserData).
- info_profile_actions.cpp: ник берётся из данных (PrimaryUsername), а не из mid(1); ID в «О себе» маскируется и реактивен; драг-текст ID и ника через ForCopy; копирование ссылок и номера.
- notifications_manager.cpp: Notify поднимает hideEverything; подпись аккаунта маскируется по Username/Name.
- dialogs_inner_widget.cpp: ник в поиске маскируется, подсветка совпадения отключена, подписка на Changed(), драг чата через ForCopy.
- window_main_menu.cpp: имя в шапке меню, подписка на Changed() сбрасывает кэш.
- settings_information.cpp: копирование имени, номера, ника через хук (AddRow/ShowMenu получили необязательный параметр copyAction), копирование номера аккаунта в списке.
- core/local_url_handlers.cpp: ShowInviteLink, CopyPeerId, ShowCollectibleUsername, CopyUsernameLink, CopyUsername.
- Копирование ссылок/номера: edit_privacy_box.cpp, edit_peer_usernames_list.cpp, edit_peer_invite_link.cpp (2 места), history_inner_widget.cpp (контакт).
- Выключенный режим: везде отдаётся исходное значение, вызовы буфера те же.

## Новые файлы (в cmake)
- mokagram/streamer/mokagram_streamer.h
- mokagram/streamer/mokagram_streamer.cpp

## Изменённые существующие
info/profile/info_profile_values.cpp и .h (добавлена перегрузка CopyPhoneToClipboard(not_null<UserData*>), .h не был в списке, правка одна строка), info/profile/info_profile_actions.cpp, window/notifications_manager.cpp, dialogs/dialogs_inner_widget.cpp, window/window_main_menu.cpp, settings/sections/settings_information.cpp, core/local_url_handlers.cpp, boxes/edit_privacy_box.cpp, boxes/peers/edit_peer_usernames_list.cpp, boxes/peers/edit_peer_invite_link.cpp, history/history_inner_widget.cpp.

## Не сделано
- settings/sections/settings_main.cpp (не мой файл): строка около 183 зовёт CopyPhoneToClipboard(PhoneValue) и ветка спойлера в updatePhoneText, копирование ника около 286. Нужно: при Active(Phone) звать CopyPhoneToClipboard(user), ник и ссылку копировать через SetClipboard. Показ номера и имени в обложке маска покрывает сама (PhoneValue, NameValue).
- info_profile_phone_menu.cpp (пункт «показать номер» при Active(Phone) скрыть), prepare_short_info_box.cpp, edit_contact_box.cpp, history_view_contact.cpp, accessibility, data_session findContactPhone, api_updates, confirm_phone и прочие показы номера из 4.1: не в моём списке.
- Показ ссылки канала (LinkValue) в профиле канала и список юзернеймов не маскируются.
- Имена в чужих диалогах и чатах (второй этап спеки).
- Хоткей и пункт в главном меню, экран с галочками (его рисует реестр настроек по записям).
- Тост «скопировано» в местах без проверки возврата показывается и при запрете копирования (рядом с тостом запрета).

## Нужно от интегратора
- Вписать 2 файла в cmake; вызвать Mokagram::Streamer::RegisterSettings() при старте до Settings::Load(); при необходимости пункт «Режим стримера» в главном меню: Settings::SetBool("streamer.enabled", ...).
- Зависимость: Settings::Changed() должен отдавать ключ изменённой записи.

## Как проверить
Включить streamer.enabled: настройки (обложка, «Моя информация»), свой профиль, поиск по @нику в списке чатов, уведомление, контекстное меню копирования ника/номера при copy=0/1/2 (содержимое буфера), переключить галочку при открытом экране (обновление без перезахода), клик по нику открывает настоящий профиль.
