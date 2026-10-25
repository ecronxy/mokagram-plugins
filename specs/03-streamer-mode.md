# Режим стримера (спецификация 03)

Статус: анализ кода 7.3.3 от 22.10.2026, код не менялся, сборка не запускалась. Все пути относительно `~/dev/mokagram/Telegram/SourceFiles`. Номера строк по текущему дереву, после правок поплывут.

## 1. Что хотим

Один переключатель «Режим стримера» и набор отдельных галочек, что именно скрывать:

| Флаг | Что скрывает |
|---|---|
| `phone` | номер телефона (свой и чужих контактов) |
| `username` | `@username` |
| `links` | ссылки `t.me/...` (публичные, на себя, на юзернейм) |
| `id` | числовой ID пира |
| `name` | имя и фамилия (опционально) |
| `notifications` | содержимое уведомлений (заголовок и текст) |
| `clipboard` | что делать при копировании скрытого значения: `block` (не копировать, показать тост), `real` (копировать настоящее), `mask` (копировать маску). По умолчанию `real`, потому что владелец сам решает, что вставить, а на экран это не попадает |

Мастер-флаг `enabled` (общий выключатель, можно на хоткей) и по каждому полю свой флаг. Итог: `shown(field) = enabled && flag[field]`.

## 2. Единая точка: маскер

Новый модуль `mokagram/streamer/mokagram_streamer.{h,cpp}` (папка `mokagram/` уже есть, там `plugins/`). Он не зависит от `Main::Session`, чтобы его мог вызвать любой код и плагинный мост.

```cpp
namespace Mokagram::Streamer {

enum class Field { Phone, Username, Link, Id, Name, Notify };

struct Flags {            // хранится целиком, сравнивается ==
    bool enabled = false;
    bool phone = true, username = true, link = true;
    bool id = true, name = false, notify = false;
    enum class Copy { Real, Block, Mask } copy = Copy::Real;
};

[[nodiscard]] bool Active(Field f);                       // enabled && флаг поля
[[nodiscard]] rpl::producer<Flags> FlagsValue();          // .value() от rpl::variable<Flags>
[[nodiscard]] rpl::producer<bool> ActiveValue(Field f);   // map + distinct_until_changed

[[nodiscard]] QString Mask(Field f, const QString &real); // плоская строка
[[nodiscard]] TextWithEntities Mask(Field f, TextWithEntities real); // с сохранением entities
[[nodiscard]] QString MaskUrl(const QString &url);        // t.me/<x> -> t.me/••••
[[nodiscard]] QString ForCopy(Field f, const QString &real); // применяет Flags::copy

// Удобная обёртка для реактивных значений: подмешивает ActiveValue.
template <typename T>
[[nodiscard]] rpl::producer<T> Wrap(Field f, rpl::producer<T> real);
}
```

Правила маски (длина сохраняется, чтобы вёрстка не прыгала):
- телефон `+7 912 345 67 89` -> заменять каждую цифру на `•`, пробелы, `+`, `-`, скобки оставлять: `+• ••• ••• •• ••`. Код страны можно оставить (опция `keepCountryCode`, по умолчанию нет);
- `@username` -> `@` + `•` на каждый символ (минимум 5, максимум 16, чтобы не светить длину);
- ссылка `https://t.me/name` или `t.me/name` -> домен оставить, хвост после `/` заменить на `••••••`. Для `t.me/+hash` и `t.me/joinchat/...` так же;
- ID -> `•••••••••`;
- имя -> первая буква + `•••` (опционально, по умолчанию флаг выключен).
Символ `•` (U+2022) есть во всех шрифтах клиента; звёздочку не брать, она в Telegram-разметке даёт путаницу с `**`.

Реактивность без опроса. Хранилище флагов `rpl::variable<Flags>`; каждый producer значения (телефон, юзернейм) делает `rpl::combine(real, ActiveValue(field))` и мапит в `Active ? Mask(...) : real`. Тогда переключение галочки мгновенно перерисовывает все открытые экраны, а таймеров и перечитывания нет. Для кода без rpl (рисование через `Painter`, не-реактивные места) см. раздел 5: там ключ кэша текста включает `Flags` версию, а при смене флагов шлётся одно событие перерисовки (раздел 6).

## 3. Хранение флагов

Рекомендация: отдельный файл `tdata/mokagram_streamer.json` (или ключ в уже существующем mokagram-хранилище настроек), НЕ в `Main::SessionSettings` и НЕ в `Core::Settings`. Причина: оба сериализуются бинарным потоком с фиксированной раскладкой (`main/main_session_settings.cpp:93,186,725`, `core/core_settings.cpp`), и добавление поля ломает совместимость с оригинальным Telegram при откате. Режим глобальный на приложение, а не на аккаунт (стример переключает аккаунты). Для быстрого переключения: пункт в главном меню (`window/window_main_menu.cpp`, там уже есть `Settings::SetupAccounts`, строка около 621) и хоткей. UI галочек: новая секция в `settings/sections/` по образцу `settings_experimental.cpp` (там уже есть переключатели через `base::options::toggle`).

Что уже есть и можно переиспользовать: `Main::SessionSettings::phoneNumberHidden()` и `phoneNumberHiddenValue()` (`main/main_session_settings.h:191-198`). Это штатная функция Telegram «скрыть номер под спойлером», работает только для своего номера и только в 3 местах (раздел 4.1). Стримерский флаг `phone` должен действовать поверх неё, а не заменять: спойлер можно открыть кликом, стримеру это не годится.

## 4. Где что показывается и как маскировать

### 4.1 Номер телефона

Корень: `UserData::phone()` (`data/data_user.cpp:810`), форматирование `Ui::FormatPhone`. Реактивная точка: `Info::Profile::PhoneValue` (`info/profile/info_profile_values.cpp:131-139`), её потребители уже общие, поэтому главный перехват один.

| Место | Файл:строка | Способ |
|---|---|---|
| `PhoneValue` (единая реактивная точка) | `info/profile/info_profile_values.cpp:131` | внутри `rpl::map` вместо `tr::marked(Ui::FormatPhone(...))` вернуть `Wrap(Phone, ...)`. Подмешать `ActiveValue(Phone)` в `rpl::merge` вместе с `Countries::updated()` |
| `PhoneOrHiddenValue` (профиль и инфо о пользователе) | `info_profile_values.cpp:143-165` | берёт `PhoneValue`, маска придёт сама. Внимание: условие `phone.text.isEmpty()` проверяется на уже замаскированном тексте, маска не пустая, логика «скрыт» не ломается. Для коллекционного номера ссылка `internal:collectible_phone/<phone>@<id>` (строка 161) содержит реальный номер в URL: при `Active(Phone)` строить ссылку без него или с маской, иначе он утечёт в статус-бар при наведении |
| Спойлер своего номера | `info_profile_values.cpp:170-184` (`PhoneWithSpoilerValue`) | при `Active(Phone)` не оборачивать в спойлер, а оставлять маску (клик не должен раскрывать) |
| Копирование номера | `info_profile_values.cpp:186-190` (`CopyPhoneToClipboard`) | читает `.current()` производителя, значит получает маску. Нужен отдельный путь: брать `user->phone()` и пропускать через `ForCopy(Phone, ...)` |
| Профиль чужого пользователя, строка «Мобильный» | `info/profile/info_profile_actions.cpp:1726-1760` | значение уже из `PhoneOrHiddenValue`, меню копирования (1735-1740) править на `ForCopy` |
| Меню телефона | `info/profile/info_profile_phone_menu.cpp:123,157,165` | там переключатель спойлера и действия с `user->phone()`; при `Active(Phone)` пункт «показать номер» скрыть |
| Обложка настроек (шапка своего профиля) | `settings/sections/settings_main.cpp:268-274, 325-336` (`Cover::initViewers`, `updatePhoneText`) | значение из `PhoneValue`, маска придёт сама; ветку спойлера в `updatePhoneText` сделать зависимой от `Active(Phone)` |
| Настройки, «Моя информация» | `settings/sections/settings_information.cpp:619-632` (`phoneButton`), копирование через `ShowMenu` `settings_information.cpp:372-388` | значение из `PhoneValue`; в `ShowMenu` (`QGuiApplication::clipboard()->setText(text)`) `text` берётся из показанного, то есть будет маска. Передавать реальную строку через `ForCopy` |
| Редактирование контакта | `boxes/peers/edit_contact_box.cpp:77, 307-312` | `rpl::single(Ui::FormatPhone(_phone))` заменить на `Wrap`. Поле номера внутри окна для ввода (`add_contact_box.cpp:300`, код страны из `session->user()->phone()`) не маскировать, это ввод, а не показ |
| Короткая карточка пира | `boxes/peers/prepare_short_info_box.cpp:232` (`.phone = Ui::FormatPhone(...)`), потребитель `peer_short_info_box.cpp:894-900` | маскировать в `prepare_short_info_box.cpp`, поток обновляется по `UpdateFlag::PhoneNumber`, добавить подписку на `ActiveValue(Phone)` в тот же `combine` |
| Сообщение-контакт в чате | `history/view/media/history_view_contact.cpp:71-73, 100-105, 181, 222` | маска в тексте и в `setDragText`; не блокировать клик «написать» |
| Копирование контакта из меню чата | `history/history_inner_widget.cpp:3640-3642`, `history/view/history_view_context_menu.cpp:1866` | `ForCopy(Phone, phone)` |
| Доступность | `history/history_inner_widget_accessibility.cpp:208-209, 891` | озвучка читает номер: отдать маску |
| Список общих контактов, подпись | `data/data_session.cpp:5445-5451` (`findContactPhone`) | маска на выходе функции (используется для показа) |
| Уведомление о смене номера | `api/api_updates.cpp:2194-2205` | заглушка текста в `Ui::FormatPhone` при показе |
| «Контакт добавлен» панель в чате | `history/view/history_view_contact_status.cpp:933` | номер своего аккаунта в тексте: маска |
| Подтверждение номера | `api/api_confirm_phone.cpp:127` | показывает номер из ссылки, маска |
| Поиск по номеру (ошибка) | `window/window_session_controller.cpp:504` | маска |
| Клик по номеру в тексте сообщения | `core/phone_click_handler.cpp:330` (копирование), `:340` | номера в тексте чужого сообщения не трогаем (это контент), только `ForCopy` не нужен |
| Блок «показать мой QR/номер» | `info/profile/info_profile_qr_link.cpp:115-118, 151` | подписка `PhoneValue` уже даст маску, в QR-картинке номер напрямую не кодируется (кодируется ссылка), см. 4.2 |
| Экспорт данных | `export/data/export_data_types.cpp:3549-3552` | не трогать, это осознанное действие владельца |

Список аккаунтов: в боковом меню (`window/window_main_menu.cpp:621`, `Settings::SetupAccounts`, `settings_information.cpp:1476`) строки показывают имя, телефона там нет. Шапка бокового меню рисуется в `MainMenu::drawName` (`window/window_main_menu.cpp:929-950`) только именем, без телефона и юзернейма. Телефон в шапке меню отсутствует, маскировать нечего; только флаг `name` (см. 4.4).

### 4.2 Юзернейм и ссылки

Корень: `PeerData::username()`/`UserData::username()` (`data/data_user.cpp:755`), `usernames()` (`:762`), реактивно `UsernameValue` (`info_profile_values.cpp:193-205`, обёртка над `PlainUsernameValue`/`PlainPrimaryUsernameValue`) и `UsernamesValue` (`data/data_peer_values.cpp:442`). Создание ссылок: `Main::Session::createInternalLink/Full` (`main/main_session.cpp:488-515`), его зовут десятки мест.

Единая точка для ссылок: сам `createInternalLinkFull(TextWithEntities)` (`main_session.cpp:512`). НО его результат нужен и для реальных действий (открыть, поделиться), поэтому маскировать там нельзя. Правило: маскируется то, что рисуется на экране и что попадает в буфер по правилу `clipboard`, а не то, что идёт в `UrlClickHandler::Open` или `FastShareLink`.

| Место | Файл:строка | Способ |
|---|---|---|
| `UsernameValue` | `info/profile/info_profile_values.cpp:193-205` | в `rpl::map` после `tr::marked('@' + username)` вызвать `Mask(Username, ...)`. Вместо `rpl::map` взять `rpl::combine(PlainUsername, ActiveValue(Username))`. Ссылка-обёртка `UsernameUrl(...)` (`:207-`) строится от настоящего `username` (`u.text.mid(1)` в `info_profile_actions.cpp:1765`!). Это ломается: при маске `mid(1)` вернёт точки. Поэтому в `info_profile_actions.cpp:1762-1790` и `settings_main.cpp:276-295` брать реальный ник из `user->username()`, а не из показанного текста. Это единственное «хрупкое» место логики |
| Строка «Имя пользователя» в профиле | `info/profile/info_profile_actions.cpp:1762-1790` | значение через `UsernameValue`, `setLink(1, DraggableUrlClickHandler(UsernameUrl(...), createInternalLinkFull(username)))`: драг-текст (при перетаскивании) отдаёт реальную ссылку. Правка: `DraggableUrlClickHandler` второй параметр передать через `ForCopy(Link, ...)` |
| Меню копирования «mention / link / share» | `info_profile_actions.cpp:1645-1700` (`lnkHook`), разбор `internal:username_*` `:1690-1700` | `Copy mention/link` идут в `Core::App().openInternalUrl(...)` -> `core/local_url_handlers.cpp:1230-1285` (`ShowCollectibleUsername`, `CopyUsernameLink`, `CopyUsername`) |
| Копирование юзернейма и ссылки (3 функции) | `core/local_url_handlers.cpp:1240, 1262, 1281` | перед `SetClipboardText` пропустить через `ForCopy`. Тост «скопировано» оставить |
| Копирование в обложке настроек | `settings/sections/settings_main.cpp:286-296` | то же, `ForCopy(Link, createInternalLinkFull(username))`. Здесь `_user->username()` уже реальный, ломки нет |
| Строка «Имя пользователя» в «Моей информации» | `settings/sections/settings_information.cpp:637-700` | значение из `UsernameValue`, метка `t.me/username` для пустого ника не маскируется. Меню копирования `lng_context_copy_mention` (строка около 686) через `ShowMenu` -> `ForCopy` |
| Ссылка вида «Копировать ссылку» в профиле (`UsernamesLinkCallback`) | `info_profile_actions.cpp:195-220` | `link = createInternalLinkFull(...)`, затем `SetClipboardText` (212): `ForCopy(Link, link)` |
| Список юзернеймов и редактор | `boxes/peers/edit_peer_usernames_list.cpp:124, 269`, `boxes/username_box.cpp` | это экран управления, поля ввода не маскировать. Копирование (`:124`) через `ForCopy`. Сами строки с юзернеймами можно маскировать галочкой, по умолчанию нет: владельцу нужно видеть, что он редактирует |
| Короткая карточка, `.username`, `.usernameLink`, `.link`, `.channelLink` | `boxes/peers/prepare_short_info_box.cpp:215-240` | маска в одном месте при сборке `PeerShortInfoFields`, ключ `Username` и `Link`. Добавить `ActiveValue` в подписку (рядом с `UpdateFlag::Username`) |
| Строка поиска в списке чатов (`@username` под названием) | `dialogs/dialogs_inner_widget.cpp:1976-2000` | рисуется напрямую через `Painter` из `peer->username()`, реактивности нет. Маска при `Active(Username)` прямо перед `drawText`. Подсветка совпадения (`startsWith(_peerSearchQuery)`) отключить, иначе поиск «выдаёт» ник по буквам |
| Перетаскивание чата в поле ввода | `dialogs/dialogs_inner_widget.cpp:2127-2132` | `mimeData->setText(createInternalLinkFull(u))` и `'@'+u`: `ForCopy` |
| Подпись аккаунта в уведомлениях | `window/notifications_manager.cpp:1250-1266` (`addTargetAccountName`) | вместо `username()` подставляет ник, а если нет, то имя. Маскировать по `Username`/`Name`. Подробности в 4.5 |
| Баннер приложения и мини-аппа (`@bot`) | `inline_bots/bot_attach_web_view.cpp:1483,1514`, `boxes/star_gift_box.cpp:552` | это ботов, не своя личность. Не трогать |
| Ссылки приглашения и на каналы (`t.me/+...`) | `boxes/peers/edit_peer_invite_link.cpp:1350,1379`, `boxes/edit_privacy_box.cpp:1350-1360`, `boxes/add_contact_box.cpp:1018,1257`, `boxes/peers/edit_peer_type_box.cpp:628` | сюда попадает «ссылки» (`links`): маска в показе, `ForCopy` в копировании. Это ссылки владельца на свои каналы и группы, поэтому флаг `links` отдельный от `username` |
| Тексты в чате (ссылки и @упоминания внутри сообщений) | рендер `history/view/` | НЕ маскировать: это контент собеседников, ломает чтение, и без нужды |
| Подтверждение открытия ссылки | `core/click_handler_types.cpp:540-585` (`displayUrl`, копирование 566-577) | ссылка из текста сообщения чужая; не трогать |
| Системные тексты о смене юзернейма | `history/admin_log/history_admin_log_item.cpp:595, 993-997, 1794`, `history/history_item.cpp:6456` | журнал админа, редкий экран; оставить на втором этапе |

### 4.3 Числовой ID

В штатном клиенте ID виден в одном месте, и только по экспериментальной опции `ShowPeerIdBelowAbout`.

| Место | Файл:строка | Способ |
|---|---|---|
| Строка «id: ...» под «О себе» | `info/profile/info_profile_actions.cpp:233-246` (`AboutWithAdvancedValue`) | при `Active(Id)` вместо `Lang::FormatCountDecimal(raw)` писать маску; значение `AboutWithAdvancedValue` реактивно по `AboutValue`, добавить `ActiveValue(Id)` в `combine`. Опция `ShowPeerIdBelowAbout` читается как `base::options::toggle` через `.value()`, не реактивно, поэтому правка `combine` нужна именно ради `Id` |
| Драг/копирование ID | `info_profile_actions.cpp:272-288` (`SetupAboutPeerIdDrag`: `internal:~peer_id~:copy:<id>` и `id` в `DraggableUrlClickHandler`) | `ForCopy(Id, id)`, текст драга замаскировать |
| Меню «Copy ID» | `info_profile_actions.cpp:1521-1530` + обработчик `internal:~peer_id~:copy:` (искать в `core/local_url_handlers.cpp`) | `ForCopy(Id, ...)` перед `SetClipboardText` |
| Реальный ID в URL внутренних ссылок | `info_profile_values.cpp:161`, `info_profile_actions.cpp:1658` (`peerIdRaw`, `fullname = username@peerId` в `internal:username_*`) | это внутренние схемы (`internal:`), на экране не видны, но по hover в статус-баре Qt не показывает. Оставить как есть |
| Прочие `peer->id.value` | `settings_credits_graphics.cpp:2872,3167`, `create_giveaway_box.cpp:80` | это логика, не показ. Не трогать |

Все прочие места `id.value` и `userId.bare` (десятки) используются как ключи списков и в API, маскировать там нельзя.

### 4.4 Имя

Источники: `PeerData::name()`; реактивно `Info::Profile::NameValue` (`info_profile_values.cpp:99-106`). Места: `MainMenu::drawName` (`window/window_main_menu.cpp:929-950`, берёт `user->name()` и кэширует по `nameVersion()`), обложка настроек (`settings_main.cpp:260-264`), «Моя информация» (`settings_information.cpp:335, 345, 606`), заголовки диалогов, профиль, шапки чатов, аватарки без фото (инициалы).
- Реактивные места получают маску в одном `NameValue` через `Wrap(Name, ...)`.
- `MainMenu::drawName` рисует из `user->name()` без rpl: добавить подписку `ActiveValue(Name)` в конструкторе меню, при событии сбросить кэш (`_nameVersion = 0`) и `update()`. Это без опроса, одна подписка на жизнь окна.
- Заголовки диалогов и чат (`Dialogs::Ui`, `HistoryView::TopBar`) берут `peer->name()` из разных кэшей; полное покрытие имён это самая объёмная часть и должна идти отдельным этапом. На первом этапе флаг `name` покрывает только собственный профиль (меню, настройки, «Моя информация»).

### 4.5 Уведомления

Решение уже принимается в одной функции: `Manager::getNotificationOptions` (`window/notifications_manager.cpp:1085-1110`), поля `hideNameAndPhoto`, `hideMessageText` выставляются из `Core::App().settings().notifyView()`. Пользователь сам выбирает «показывать имя / превью», а для режима стримера нужно лишь принудительно поднять эти флаги. Правка в одну строку:

```cpp
const auto streamer = Mokagram::Streamer::Active(Field::Notify);
result.hideNameAndPhoto = hideEverything || streamer || (view > ShowName);
result.hideMessageText  = hideEverything || streamer || (view > ShowPreview);
```

Тогда заголовок заменится на `AppName` (`notifications_manager.cpp:1575`), текст скрывается штатно, кнопка «прочитано» тоже (1099). Это использует уже отлаженный путь и не требует новой логики. Подпись аккаунта в заголовке (`addTargetAccountName`, `:1250-1266`) нужно отдельно скрыть, если включены `username` или `name`. Дефолтный (внутренний) вид уведомлений: `window/notifications_manager_default.cpp:105, 1017` читает `name()` сам: проверять, что оно вызывается после `getNotificationOptions` (по коду `hideNameAndPhoto` там учитывается, но это надо подтвердить на сборке).
Реактивности не нужно: уведомление строится в момент показа, флаг читается через `Active(...)` синхронно.

### 4.6 Буфер обмена: сводка

Ни одного централизованного вызова нет: используются `QGuiApplication::clipboard()->setText` и `TextUtilities::SetClipboardText` в 60+ местах. Для режима стримера значимы лишь те, что копируют СВОИ данные. Список в 4.1, 4.2, 4.3, плюс: `info/profile/info_profile_actions.cpp:212, 1545, 1555, 1669`, `core/local_url_handlers.cpp:942, 964, 1240, 1262, 1281`, `settings/sections/settings_main.cpp:293`, `settings/sections/settings_information.cpp:383`, `info/profile/info_profile_values.cpp:188`, `dialogs/dialogs_inner_widget.cpp:2127`, `boxes/peers/edit_peer_usernames_list.cpp:124`, `boxes/peers/edit_peer_invite_link.cpp:1350,1379`, `boxes/edit_privacy_box.cpp:1360`, `history/history_inner_widget.cpp:3642`. Все они получают `ForCopy(field, real)`.

Чтобы не охотиться за каждым и не пропустить новые при обновлении апстрима, добавить тонкую обёртку `Mokagram::Streamer::SetClipboard(Field, QString)` и заменять вызовы только в перечисленных местах. Перехват на уровне самого буфера (глобально, по совпадению с номером или ником владельца) НЕ делать: это ломает обычное копирование.

## 5. Реактивность и нереактивные места

1. Реактивные потребители (`PhoneValue`, `UsernameValue`, `NameValue`, `PhoneOrHiddenValue`, `PeerShortInfoFields`): добавить `ActiveValue(field)` в существующий `rpl::combine`/`rpl::merge` и применять маску в `rpl::map`. Дополнительно `rpl::distinct_until_changed`, чтобы смена не связанных флагов не перерисовывала. Подписки живут на `lifetime()` виджета, утечек нет.
2. Нереактивное рисование (`dialogs_inner_widget.cpp:1982`, `MainMenu::drawName`): при смене флагов шлётся один сигнал `Streamer::Changed()` (`rpl::event_stream<>`), окна подписаны один раз и вызывают `update()` или сбрасывают кэш текста.
3. Копирование и уведомления: читают `Active(...)` по месту, подписки не нужны.
4. Опрос и таймеры не используются нигде.

## 6. Порядок работ

1. Модуль `mokagram_streamer` с `Flags`, `Mask`, `ForCopy`, `ActiveValue`, хранение в json. Проверка: юнит-проверка масок на строках `+7 912 345-67-89`, `@a`, `https://t.me/name`, `t.me/+AbC`.
2. Реактивное ядро: `PhoneValue`, `UsernameValue`, `NameValue`, `PhoneWithSpoilerValue`, `PhoneOrHiddenValue` (`info_profile_values.cpp`). Это закрывает профиль, настройки и обложку.
3. Исправить хрупкое место: везде, где ник берётся из показанного текста через `mid(1)` (`info_profile_actions.cpp:1765`, `:1789` и аналоги), брать `user->username()`.
4. Копирование: заменить вызовы из 4.6 на `ForCopy`/`SetClipboard`, в `ShowMenu` (`settings_information.cpp:372`) передавать реальный текст.
5. Короткая карточка (`prepare_short_info_box.cpp`), список чатов (`dialogs_inner_widget.cpp`), меню `drawName`.
6. Уведомления: правка в `getNotificationOptions` и `addTargetAccountName`.
7. Экран настроек с галочками и пункт в главном меню (по образцу `settings_experimental.cpp`), хоткей.
8. Второй этап: имена в чужих диалогах и чате, журнал админа, ID в прочих местах.

## 7. Как проверять (на сборке)

- Включить режим, открыть: настройки (обложка, «Моя информация»), свой профиль, профиль контакта, карточку с короткой информацией, чат с контактом (карточка контакта), поиск в списке чатов, всплывающее уведомление, редактирование контакта.
- Переключить галочку при открытом экране: текст должен обновиться без перезахода.
- Скопировать номер, ник, ссылку при `copy=Real/Block/Mask` и убедиться по содержимому буфера.
- Убедиться, что клик по ссылке ника и «написать» продолжают работать (ссылка строится из реального ника).
- Скриншоты и запись экрана: исходные значения не должны остаться ни в tooltip, ни в accessibility-дереве (`history_inner_widget_accessibility.cpp`).

## 8. Риски

- Хрупкие места: код, который разбирает показанный текст (`mid(1)`, сравнения с пустотой). Список в п. 3 порядка работ.
- Обновление апстрима: правки точечные (около 20 мест), основная логика в новом модуле, конфликты ожидаются в `info_profile_values.cpp`, `info_profile_actions.cpp`, `notifications_manager.cpp`.
- Полное скрытие имён в чужих чатах не входит в первый этап.
- Номера строк надо перепроверить перед правкой, спецификация писалась без сборки.
