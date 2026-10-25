# 07. Аккаунты без лимита, инструменты стикеров и эмодзи, ребрендинг в mokaGram

Статус: анализ 22.10.2026 по коду ~/dev/mokagram (Telegram Desktop 7.3.3). Код не правился, сборка не запускалась.
Пути относительно `Telegram/SourceFiles`. Всё, что помечено «предложение», нужно проверить на сборке. Замеров нагрузки нет, цифры по памяти не выдумываю.

---------------------------------------------------------------

## 1. Снятие лимита аккаунтов

### 1.1 Где живёт лимит

| Место | Что там |
|---|---|
| main/main_domain.h:39-40 | `kMaxAccounts = 3`, `kPremiumMaxAccounts = 6` |
| main/main_domain.cpp:614-622 | `Domain::maxAccounts()`: `min(числоПремиумАккаунтов + 3, 6)`; тест-режим считается премиумом |
| main/main_domain.cpp:330 | `Expects(_accounts.size() < kPremiumMaxAccounts)` в `Domain::add` (в релизе Expects не срабатывает, но в дебаге упадёт) |
| main/main_domain.cpp:387 | `addActivated`: добавляет новый аккаунт только если `size < maxAccounts()` |
| main/main_domain.cpp:413 | `_lastMaxAccounts` обновляется при смене премиума, от него идёт `maxAccountsChanges()` (main_domain.h:69, :163) |
| storage/storage_domain.cpp:629 | при чтении tdata: `count > kPremiumMaxAccounts` = «bad accounts count», запуск падает |
| storage/storage_domain.cpp:643 | индекс аккаунта `< kPremiumMaxAccounts`, иначе аккаунт молча не читается (ТЕРЯЕТСЯ) |
| core/application.cpp:418 | подписка: если аккаунтов больше `kMaxAccounts`, при активации аккаунта вне лимита (:427) показывается `AccountsLimitBox` |
| settings/sections/settings_information.cpp:1067 | кнопка «Добавить аккаунт»: при `size >= maxAccounts()` открывает `AccountsLimitBox` |
| settings/sections/settings_information.cpp:1142, 1148 | `premiumLimit = maxAccounts()`: аккаунты после этого индекса получают замок (`nextIsLocked`) |
| settings/sections/settings_information.cpp:1189-1190 | `addPinnedInterval(premiumLimit, ...)`: аккаунты сверх лимита нельзя перетаскивать выше лимита |
| settings/sections/settings_information.cpp:1200 | кнопка «Добавить» скрывается при `count >= kPremiumMaxAccounts` |
| settings/sections/settings_information.cpp:1027 | перестройка списка по `maxAccountsChanges()` |
| settings/sections/settings_main.cpp:710 | пункт «Добавить аккаунт» в меню настроек |
| boxes/premium_limits_box.cpp:1067-1135 | `AccountsLimitBox` (окно «лимит аккаунтов» с предложением Premium) |
| boxes/premium_preview_box.cpp:1669-1680 | строка «x2 лимиты» в превью Premium: «3 до 6» |

Остальные места работают по `accounts()` / `orderedAccounts()` без привязки к числу и лимит не знают: tray_accounts_menu.cpp:28,47 (меню трея), menu/menu_dock.cpp:31 (dock macOS), window/window_main_menu.cpp:618 (список в боковом меню лежит в `_scroll`, прокручивается), core/local_url_handlers.cpp:196 (`tg://...?account=N`), boxes/url_auth_box.cpp, core/application.cpp:255,1184,1243,1473,2027, settings_local_passcode.cpp:1187 и т.д. Это цикл по N, на 50 безопасно.

Хранение: каждый аккаунт это папка данных с суффиксом `#N+1` (main/main_account.cpp:36-41, `ComposeDataString`), индекс `Domain::add` берёт первый свободный (main_domain.cpp:353-355). Индексы пишутся как `qint32`, ограничение только проверки из storage_domain.cpp.

Горячие клавиши: `ShowAccount1..6` (core/shortcuts.cpp:110-115, обработка window/window_session_controller.cpp:2009 и shortcuts.cpp:604). Остаются на 6, выше только мышью или `tg://...account=N`. Это не поломка, можно оставить.

### 1.2 Можно ли сделать лимит настраиваемым

Да, технически ломать нечего: все циклы линейные, список в меню прокручивается, tdata хранит индекс как int.

План:
1. Новая настройка `Core::Settings::maxAccounts()` (core/core_settings.cpp/.h, рядом с `accountsOrder`, :288, :453, :849; по образцу как хранится `accountsOrder`, обновить размер буфера в :288). По умолчанию 10, диапазон 3..50.
2. В main_domain.h заменить константы: `kDefaultMaxAccounts = 3`, `kPremiumMaxAccounts = 6` оставить только для текста Premium; добавить `kHardMaxAccounts = 50` (верхняя планка для tdata).
3. `Domain::maxAccounts()` (main_domain.cpp:614): вернуть `Core::App().settings().maxAccounts()` и больше не считать премиум. Тогда `AccountsLimitBox` (premium_limits_box.cpp:1067, settings_information.cpp:1069, application.cpp:429) физически не покажется при лимите выше числа аккаунтов, но код пусть живёт.
4. Заменить `kPremiumMaxAccounts` на `kHardMaxAccounts` в main_domain.cpp:330, storage_domain.cpp:629 и :643, settings_information.cpp:1200.
5. core/application.cpp:418: `kMaxAccounts` заменить на `maxAccounts()`; без этого при лимите выше 3 условие ложно срабатывает и окно лимита покажется зря.
6. settings_information.cpp:1142-1148 и 1189: `premiumLimit` теперь равен лимиту, замков не будет. Блок с замком можно оставить как есть.
7. premium_preview_box.cpp:1669-1680: строка про «x2 лимиты аккаунтов» в рекламе Premium. Оставить с Premium-константами (это правда про Telegram Premium), либо скрыть строку (предложение: оставить).
8. Ползунок «Максимум аккаунтов» (3..50) в настройках mokaGram, подписанный `maxAccountsChanges` (main_domain.cpp:413 нужно звать и при смене настройки, не только при смене премиума).

Риски:
- Совместимость данных: tdata с более чем 6 аккаунтами официальный Telegram Desktop не прочтёт («bad accounts count»). Сказать пользователю, что обратного пути на официальный клиент нет (или делать копию tdata).
- Нагрузка: каждый аккаунт это своя MTProto-сессия, свои соединения, свои диалоги и кэш в памяти (ключи `Instance` в main_account). Сколько это в мегабайтах и в трафике на 20 и 50 аккаунтах, не измерено. Предложение: по умолчанию 10, замерить RSS и количество сокетов на 10, 20, 50 тестовых аккаунтах до того, как поднимать значение по умолчанию. Если лаги пойдут, нужна ленивая загрузка сессий (не поднимать `Main::Session` для неактивного аккаунта до первого открытия). Сейчас движок так не делает, и это отдельная большая задача.
- Серверные лимиты Telegram (FLOOD_WAIT при одновременном входе) не зависят от клиента.

---------------------------------------------------------------

## 2. Стикеры и эмодзи

### 2.1 Что уже есть в нашем форке (это важно, 7.3 уже умеет многое)

Модули есть, писать с нуля не надо:
- api/api_stickers_creator.cpp/.h: `StickerUpload` (загрузка файла, `messages.uploadMedia` на :539, `stickers.addStickerToSet` на :579 и :247), `DeleteStickerSet` (:369 `stickers.deleteStickerSet`), меню «добавить в мой пак» `AddAddToOwnedSetAction` (:346), `FillChooseOwnedSetMenu` (:163), только для паков с флагом `AmCreator` (:146). Лимиты: 120 стикеров, 200 эмодзи (api_stickers_creator.h:33-35), сторона эмодзи 100 (`kEmojiStickerSideMax`).
- boxes/sticker_creator_box.cpp/.h: `OpenCreateStickerFlow` (:799), `OpenCreateEmojiFlow` (:810), `AdaptStickerToEmoji` (:821), `AdaptGifToSet` (:887). Диалог выбора картинки `ChooseImageThenCreate` (:764), фото-редактор с маской `RunImageEditorAndCreate` (:741), `PrepareEditorState(image, 512)` (:107), видео `RunVideoEditorAndCreate` (:692) с редактором и пределами: `kStickerSide=512`, видео до 3 с, 30 fps, webm не больше 256 КБ для стикера и 64 КБ для эмодзи (:53-63).
- Кодирование VP9 с альфой уже подключено: media/media_video_encode.cpp:269 (`libvpx-vp9`), ffmpeg/ffmpeg_utility.cpp:457, опция `webmSticker` (editor/video/video_editor_common.cpp:64).
- boxes/sticker_set_box.cpp: плюс-ячейка «создать» только для своих паков (`hasAddCell` :2561, `startCreateNewStickerFlow` :2850, `amSetCreator` :497, :1240 `is_creator()`), контекстное меню по стикеру (:1775, :1825).
- Контекстное меню в чате: history/view/history_view_context_menu.cpp:477 (для стикера без пака), history/history_inner_widget.cpp:3611.
- ВАЖНО: `messages.createStickerSet` в клиенте нет вообще. Новый пак tdesktop не создаёт, только добавляет в уже существующий свой (создавать пак надо у @Stickers). Это дыра для «в один клик».

### 2.2 «Создать стикер или эмодзи из любого фото или видео в один клик»

Что нет: пункта в меню по фото. history/view/history_view_context_menu.cpp:366-398 (`AddPhotoActions`) даёт только «сохранить», «копировать», «стикеры на фото». Для видео и гифок: ветка около :455-483 (для документа).

План:
1. В `AddPhotoActions` (history_view_context_menu.cpp:366) добавить пункты «Стикер из фото» и «Эмодзи из фото». Они берут `photo->activeMediaView()->image(Large)->original()` (как это уже делает `CopyImage`, :345-360) и зовут новую функцию `Api::CreateFromImage(show, QImage, type)`.
2. Для видео и гифок в ветке документа (рядом с :465 `lng_context_save_gif`) добавить то же, через `Api::AdaptGifToSet` (sticker_creator_box.cpp:887), он уже принимает video/animation и сам идёт в видео-редактор с ограничениями (512, и 100 для эмодзи).
3. Новая функция в boxes/sticker_creator_box.cpp рядом с `RunImageEditorAndCreate` (:741): вход QImage, шаг «вырезать фон», затем обычный путь `PrepareEditorState` (:107) и выбор пака. Если у пользователя ровно один подходящий свой пак, добавлять сразу без вопросов (`EnumerateOwnedSets`, api_stickers_creator.cpp:146), иначе меню выбора (`FillChooseOwnedSetMenu` :163). Это и есть «один клик».
4. Если своих паков нет, показать подсказку «создай пак у @Stickers» (как сейчас). Предложение следующего шага: `messages.createStickerSet` + `stickers.checkShortName` / `suggestShortName` (в клиенте их нет, схема слой 232 их содержит; уточнить по api.tl). Пока не делать, это отдельный этап.

Размеры (подтверждены кодом): стикер 512 по большей стороне, PNG/WebP; видеостикер webm VP9 с альфой, 512, до 3 с, до 256 КБ; видео-эмодзи 100x100, webm, до 64 КБ. Проверку размера файла и усечение по размеру уже делает `VideoStickerEditorData` (:348-366), для новой ветки лишь передать тип `Emoji`.

### 2.3 Вырезание фона локально, без API и ИИ-сервисов

В репозитории нет OpenCV, ONNX и ничего про сегментацию (искал: segment, grabcut, onnx, rembg, remove background: пусто). Варианты по возрастанию стоимости:

A. Простой режим на чистом Qt (рекомендую как первый этап, ноль зависимостей): сегментация по цвету фона. Берём цвета по периметру картинки, заливкой (flood fill) от краёв с допуском стираем фон, затем размытие маски 1-2 px и убираем одиночные островки. Работает для фото на однотонном фоне, логотипов, рисунков. Реализация: новый файл `editor/editor_cutout.cpp/.h` (в CMake добавить в список `editor/`, смотреть как подключены `editor_crop.cpp`). Ручка допуска и кнопка «кисть вернуть/стереть» (в фото-редакторе уже есть кисть `editor_paint.cpp`, можно использовать его слой маски).
B. Ручное выделение: пользователь обводит объект лассо (`QPainterPath`), всё вне пути становится прозрачным. Тоже чистый Qt, делается как режим в фото-редакторе поверх `ApplyShapeMask` (sticker_creator_box.cpp:211).
C. Готовая локальная модель (это единственный путь к автовырезанию людей и предметов на сложном фоне): U2-Net / ISNet / BiRefNet через ONNX Runtime. Минусы: тянуть onnxruntime в сборку (десятки МБ) и скачивать модель (от 5 до 170 МБ) при первом запуске; в Linux-сборке lib нет. Альтернатива без новых зависимостей в клиенте: через Python-плагин mokagram (см. SPEC.md) вызывать установленный у пользователя `rembg`; клиент сам ничего не тянет. Предложение: A + B внутри клиента, C как плагин.

Для видео фон не вырезаем в первой версии (покадровая сегментация дорогая и дрожит); только готовая альфа (уже есть `keepAlpha`, video_editor.cpp:185).

### 2.4 «Показать владельца пака»

Формула из задачи, как её реализовать по коду:

```
uint64 id = set.id;
uint64 owner = id >> 32;
if (((id >> 16) & 0xff) == 0x3f) owner |= 0x80000000;
if ((id >> 24) & 0xff)           owner += 0x100000000;
```

Оценка: это эвристика, а не контракт Telegram (разметка id набора не документирована). Показывать результат как «вероятный владелец», у пользователя проверять существование.

Где подключить:
- boxes/sticker_set_box.cpp: в меню набора (`copyLink` :872, пункты собираются около :1098-1101 вместе с `fillSetCreatorMenu` :883) добавить пункт «Владелец пака» для паков, где `!amSetCreator()`. `_setId` есть в :1232 (`_setId = setData.vid().v`), у `Inner::setId()` :465.
- По клику: `session->data().peerLoaded(peerFromUser(UserId(owner)))`. Если пользователь в кэше, открыть профиль (`controller->showPeerInfo`). Если нет, у MTP нет access hash, надёжно открыть нельзя: показать тост с числом id, кнопку «копировать id» и ссылку `tg://user?id=N` (клиент сам попробует). Запрос `users.getUsers` с `inputUser(id, access_hash=0)` вернёт данные только если пользователь «известен» серверу по контакту или общему чату, это просто попробовать и перейти на запасной вариант.
- Чистая функция `OwnerIdFromStickerSetId(uint64)` рядом в api/api_stickers_creator.h, тест на паре известных наборов.

---------------------------------------------------------------

## 3. Ребрендинг в mokaGram

### 3.1 Где встречается название

Менять (внешний вид, видят пользователи):

| Место | Что сейчас | Что делать |
|---|---|---|
| core/version.h:21-24 | `AppName = "Telegram Desktop"`, `AppFile = "Telegram"` | `AppName = "mokaGram"`, `AppFile = "mokaGram"`. `AppName` попадает в трей (tray.cpp:25-26), уведомления (platform/linux/notifications_manager_linux.cpp:819, window/notifications_manager.cpp:1576), заголовок группы в настройках уведомлений (settings_notifications.cpp:736), `PULSE_PROP` и GLib-имя (platform/linux/specific_linux.cpp:369,755,761), MPRIS (media/system_media_controls_manager.cpp:222), `file_utilities.cpp:174`, `application.cpp:2130-2155` (display name платформы). `AppFile` ещё идёт в имя словарей: chat_helpers/spellchecker_common.cpp:45, на Windows пути: platform/win/specific_win.cpp:200 |
| core/launcher.cpp:346 | `setApplicationName("TelegramDesktop")` | Это определяет пути данных (`~/.local/share/TelegramDesktop`, `StartupWMClass`). СМЕНА ПУТИ = ПОТЕРЯ СЕССИЙ у тех, кто ставит поверх. Решение: оставить `TelegramDesktop` для папки данных, либо добавить миграцию. Предложение: оставить пока, менять на `mokaGram` только вместе с миграцией (platform/linux/specific_linux.cpp:689 `psAppDataPath` уже содержит похожую логику для `.TelegramDesktop`) |
| boxes/about_box.cpp:68 | `box->setTitle("Telegram Desktop")` | `"mokaGram"`; текст о ссылке на альфу (:97-100) убрать или заменить |
| boxes/about_box.cpp:61-85 (+ lang `lng_about_text1..3`) | «Official free messaging app based on Telegram API ... GPL ... GitHub ... Telegram FAQ» | Нужен честный текст: «Неофициальный клиент mokaGram на основе Telegram Desktop», ссылка на свой GitHub, GPLv3 и исходники оставить обязательно |
| api/api_authorizations.cpp:41 | имя в списке «активные сеансы» берёт «Telegram Desktop» только для известных api_id (`DesktopApiId`, `SnapApiId`, test) | У нас свой api_id, имя придёт от сервера (поле `app_name` при регистрации приложения на my.telegram.org): задать там «mokaGram» |
| lib/xdg/org.telegram.desktop.desktop | `Name=Telegram`, `Exec=Telegram`, `Icon=org.telegram.desktop`, `StartupWMClass=TelegramDesktop` | Сменить `Name=mokaGram`, `Comment`, `Quit mokaGram`. `MimeType` с `x-scheme-handler/tg` ОСТАВИТЬ (см. ниже). Имя файла и `Icon`: если менять id на `app.mokagram.desktop`, поменять сразу во всех местах (список ниже), иначе иконка и DBus-активация пропадут |
| CMakeLists.txt:2685-2708 | `bundle_identifier org.telegram.desktop` / `com.tdesktop.Telegram`, `output_name Telegram` | Для Linux: `output_name mokaGram` (:2717). `bundle_identifier` менять, только если делаем macOS-сборку |
| CMakeLists.txt:2950-2973 | `install(...) RENAME org.telegram.desktop...` (иконки 16-512, symbolic, .desktop, .service, metainfo) | Переименовать вместе с файлами в lib/xdg/ |
| platform/linux/specific_linux.cpp:236, 375-384, 443, 741-745 | идентификатор приложения `org.telegram.desktop` (`QGuiApplication::desktopFileName`, удаление старых .desktop, DBus) | Менять строго совместно с lib/xdg и CMake (один идентификатор везде) |
| Resources/art/icon*.png, icon256.ico, icon_round512@2x.png, iconbig_green.png, icon_green.png, logo_256*.png, mac_setup.tiff | иконки Telegram | Заменить на логотип mokaGram, те же размеры и имена. Тоже Resources/icons/tray_monochrome*.svg (трей), Resources/winrc/Telegram.rc, Resources/uwp/AppX |
| Resources/langs/lang.strings (365 вхождений «Telegram») | «Telegram Desktop» в ~15 строках (напр. `lng_intro_about` :394, `lng_passcode_about*` :1220-1223, `lng_new_version_wrap` :6270, `lng_group_call_mac_*` :6666,6669, `lng_wallet_protection_open_warning_lock` :9089, `lng_outdated_*` :7873-7874) | Заменять только фразу «Telegram Desktop» на «mokaGram» |
| Telegram.plist, Resources/winrc/*.rc, snap/snapcraft.yaml, lib/xdg/*.metainfo.xml | имя, id | Если эти платформы собираем |
| core/update_checker.cpp:2186, about_box.cpp:97 | ссылки на flathub и tdesktop.com | Отключить автообновление официального (`DESKTOP_APP_DISABLE_AUTOUPDATE`) или завести свой канал |
| _other/updater_linux.cpp:295, 425, 459 | имена `Telegram` для апдейтера | Только если используем встроенный апдейтер, иначе не трогать |

Оставить как есть (трогать нельзя или не нужно):
- Схема `tg://` и `tonsite`/`ton`: `MimeType=x-scheme-handler/tg;...` в .desktop, обработчики core/local_url_handlers.cpp. Это протокол Telegram, ссылки из сайтов должны открываться нашим клиентом. Оставить.
- Названия функций Telegram: Telegram Premium, Stars, Business, Gifts, Wallet и т.д. в строках `lng_premium_*`, `lng_credits_*`, `lng_business_*`, `lng_gift_*`, `lng_wallet_*`. Это названия сервисов, не клиента; `lng_settings_color_link_name`, `lng_gift_unique_telegram`, `lng_wallet_row_telegram` = просто «Telegram» как сервис, оставить.
- Лицензия и юридическое: файл `LICENSE`, `LEGAL`, заголовки в исходниках («This file is part of Telegram Desktop ...»), упоминание GPLv3 с исключением OpenSSL и ссылка на исходники в about: ОБЯЗАТЕЛЬНО сохранить (GPL). В about добавить «основано на Telegram Desktop».
- Папка `tdata` (storage, logs.cpp:386, launcher.cpp, core/ui_integration.cpp, update_checker.cpp и 20 мест): формат и имя `tdata` оставить. Это совместимость хранилища с официальным клиентом, смена потребовала бы миграции и ломает `updater`.
- `CloudLangPackName() = "tdesktop"` (lang/lang_instance.cpp:26): имя серверного языкового пакета. Менять нельзя, иначе сервер не отдаст строки.
- `window.TelegramDesktopShell` (ui/chat/attach/attach_bot_webview_linux_shell.cpp:85-157, Resources/bot_webview_shell_html/page.js): интерфейс для мини-аппов, оставить.
- `AppId` GUID (version.h:21) для Windows оставить, `AppNameOld` не используется.
- `shortAppName = "tdesktop"` (core/application.cpp:2130-2152): техническое имя для платформы.

### 3.2 Как править строки языка с сервера на лету

Серверные строки приходят через `lang_cloud_manager.cpp:283` (`applyLangPackDifference`) → `lang::Instance::applyDifference` (lang_instance.cpp:668) → `applyDifferenceToMe` (:684) → `applyValue` (:731). Кроме того, кэш с диска читается в `fillFromSerialized` (:423, значения применяются в :545), и встроенные английские строки лежат в `_values` из `PrepareDefaultValues` (:30). Поэтому ловить надо в одном месте, где все пути сходятся: `applyValue`.

Предложение:
1. В `Instance::applyValue` (lang_instance.cpp:731) перед `ParseKeyValue` пропускать значение через `BrandRewrite(QByteArray)`: простая замена подстроки «Telegram Desktop» на «mokaGram» (и «Telegram Win (Unofficial)» если встретится). Больше ничего не заменять: «Telegram Premium», «Telegram Stars», «Telegram FAQ», «Telegram API» трогать нельзя.
2. Тот же вызов в `loadFromContent` (:553-555) и в ветке нестандартных строк `fillFromSerialized` (:545), чтобы закэшированные строки тоже переписались. Кэш хранит уже переписанные значения, поэтому повторно переписывать безопасно (замена идемпотентна).
3. Встроенные английские строки (lang.strings) править прямо в файле Resources/langs/lang.strings (как в таблице выше): они генерируются в код на сборке.
4. Для точных переопределений по ключам (например подменить `lng_about_text1` целиком) добавить таблицу `{ключ -> значение}` в новом `mokagram/branding/brand_strings.cpp` и применять после `applyDifferenceToMe` и перед `_updated.fire` (lang_instance.cpp:697-701), чтобы они всегда побеждали серверное значение. Править эту таблицу можно без пересборки, если читать из `tdata/mokagram_strings.json` (предложение).
5. Разные языки: замена по подстроке «Telegram Desktop» работает для английского; во многих переводах название не переводится и остаётся латиницей, но может быть склонено («Telegram Desktop-а»). Просмотреть выгрузку `lng_*` на русском, украинском, испанском после первого запуска и добавить исключения в таблицу п.4.

### 3.3 Порядок работ (предложение)

1. `version.h`, about_box, `lang.strings`, .desktop (Name), иконки: видимый ребрендинг без риска для данных.
2. Правка `applyValue` для серверных строк.
3. Отдельным шагом, с миграцией данных: app-id `org.telegram.desktop` → свой, путь данных, `output_name`.
4. Свой api_id с названием «mokaGram» на my.telegram.org.

---------------------------------------------------------------

## Приоритеты

1. Лимит аккаунтов: настройка 3..50, по умолчанию 10, замер памяти (п.1.2). Малые правки, высокий эффект.
2. Меню «Стикер/эмодзи из фото» + вырезание фона вариантом A/B (п.2.2, 2.3).
3. «Владелец пака» (п.2.4), быстро.
4. Ребрендинг видимой части (п.3.1) и серверных строк (п.3.2); смену идентификаторов и путей данных отложить.
