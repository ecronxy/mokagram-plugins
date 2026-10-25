# 08. Дизайн-система mokaGram: Material Design 3 + macOS

Только спецификация. Код, сборка и клиент не тронуты. Номера строк сняты с
`~/dev/mokagram` (7.3.3) 22.10.2026, после правок могут съехать (ищи по имени).
Эталон: окна 28, карточки 22, кнопки и поля пилюлями. Палитра уже в
`Resources/night.tdesktop-theme` (windowBg #282828 = карточки, boxBg и
dialogsBg #1c1c1c = фон страниц, акцент #0a84ff), здесь она не обсуждается.

## 0. Что важно знать до начала

1. `Telegram/lib_ui` это подмодуль (github.com/desktop-app/lib_ui), а не наш код.
   Все базовые константы (`boxRadius`, `buttonRadius`, `roundRadius*`, Menu,
   PopupMenu, InputField, кнопки) лежат в нём. Править напрямую нельзя без
   форка. Решение: форк `ecronxy/lib_ui`, смена url в `.gitmodules`, ветка
   `mokagram`. Запасной вариант: патч `mokagram/patches/lib_ui-md3.patch`,
   применяемый скриптом сборки. Токены обязаны жить в lib_ui (`ui/basic.style`),
   потому что lib_ui-стили не могут сделать `using` на SourceFiles-стили.
2. Значения констант хранятся в сгенерированном `style_X.cpp`, а `style_X.h`
   содержит только `extern const int &boxRadius;`. Проверено в
   `~/dev/mokagram-build/Telegram/lib_ui/gen/styles/style_layers.{h,cpp}`:
   `_boxRadius = px8;` стоит в `.cpp`. Генератор не перезаписывает файл с тем же
   содержимым (`Telegram/codegen/codegen/common/cpp_file.cpp:92`), у кастомных
   команд в `build.ninja` стоит `restat = 1`. Итог: смена ЗНАЧЕНИЯ константы
   перекомпилирует один `style_X.cpp` и линкует. Добавление/переименование
   имени меняет `.h` и пересобирает всех его включателей (цифры в разделе 4).
   Поэтому все новые токены добавляются одним коммитом первым (участок A0), а
   дальше все правят только значения.
3. `style_basic.h` подключён в PCH (`SourceFiles/stdafx.h:136`, `lib_ui/ui/painter.h:9`).
   Новое имя в `basic.style` = пересборка PCH и всех 1664 объектов. Это
   единственная «дорогая» правка, делается один раз.
4. В рабочем дереве уже есть чужие правки стилей (git status на момент среза):
   `info/info.style` (отступы infoProfileButton 10/8 -> 14/14,
   infoSharedMediaButtonIconPosition, infoGroupMembersIconPosition) и
   `info/profile/info_profile_actions.style` (infoProfileLabeledPadding и ещё две,
   9/7 -> 12/10). Эти значения совпадают с предлагаемой ниже шкалой (строка 48).
   Участок «настройки/профиль» продолжает их, не откатывает.
5. Коллизия смыслов: `boxRadius` в upstream означает и «радиус окна-бокса», и
   «радиус карточки/подложки» (57 файлов, 128 использований, перечень в 1.12).
   Просто поставить 28 нельзя: карточки в настройках, QR, галереях подарков и
   пикерах тоже станут 28. Решение: `boxRadius` становится 22 (карточка), а для
   слоёв вводится `mokaRadiusWindow` 28 и подставляется в ~13 файлах по списку
   из 1.12.
6. В upstream уже есть наши значения: `aiComposeCardRadius: 22px`
   (boxes/compose_ai_box.style:176), `aiTonePreviewExampleCardRadius: 22px` (155),
   `callRateRadius: 28px` (calls/calls.style:460), `stickersAddCellBgRadius: 28px`
   (chat_helpers.style:493), `storiesComposeRadius: 21px` (media_view.style:778,
   готовый пример скруглённого composer через `ComposeControls.radius`).
7. Что НЕ трогаем в первой фазе (наследуют кнопки и радиусы по цепочке, свои
   радиусы оставить): calls, media_view (кроме примера выше), iv, wallet, editor,
   passport, statistics, premium, credits, payments, export, intro. Радиусы блобов
   (`*BlobMinRadius`, `*BlobMaxRadius`), `blurRadius`, `*ShadowRadius`,
   `reactionCorner*`, `replyCorner*` это не скругления, их не менять.
8. Окно приложения целиком (рамка 28) вне задачи: на Linux это рамка
   композитора/Qt, на macOS `macWindowRoundRadius: 10` (window/window.style:408)
   системное. «Окна 28» в спеке = боксы, слои, спец-слои (настройки/профиль в
   слое), панель главного меню.

## 1. Инвентаризация

Колонки: константа, файл:строка, сейчас, станет. «Т» = только значение, «К» =
нужен код (см. раздел 4).

### 1.1 Базовые радиусы (lib_ui)

| Константа | Файл:строка | Было | Станет | Где живёт в коде |
|---|---|---|---|---|
| roundRadiusLarge | lib_ui/ui/basic.style:107 | 6px | 12px (= новый mokaRadiusSmall 8 для мелких карточек; см. 2.2) | 31 файл, 49 использований: CornersMaskLarge, ForwardCorners, опросы, стикеры, превью |
| roundRadiusSmall | lib_ui/ui/basic.style:108 | 3px | 6px | 20 файлов, 52 использования: Doc1-4Corners, StickerHover, inline-результаты, тултип, чекбокс |
| dateRadius | lib_ui/ui/basic.style:110 | = roundRadiusLarge | 8px явно (плашка даты на медиа) | cached_round_corners.cpp:82 |
| buttonRadius | lib_ui/ui/widgets/widgets.style:716 | 4px | 20px (для h40; реально кнопки идут через fullRadius, см. 1.2) | 9 файлов, 19 использований; RoundButton: `st.radius ? st.radius : st::buttonRadius` (buttons.cpp:306,307,509,609), RippleButton mask buttons.cpp:56 |
| boxRadius | lib_ui/ui/layers/layers.style:38 | 8px | 22px (карточка) | см. 1.12 |
| mokaRadiusWindow (НОВАЯ) | lib_ui/ui/basic.style | нет | 28px | только слои, 13 файлов из 1.12 |
| innerDropdownRadius | lib_ui/ui/widgets/widgets.style:1255 | 8px | 22px (MenuCorners, cached_round_corners.cpp:79) | InnerDropdown, MenuCorners |
| defaultPopupMenu.radius | lib_ui/ui/widgets/widgets.style:995 | 8px | 22px | popup_menu.cpp:110,124,270,901,903 |
| dialogsSearchInMenu.radius | SourceFiles/dialogs/dialogs.style:484 | 8px | 22px (наследуется по смыслу, прописан явно) | |
| previewMenu.radius | SourceFiles/ui/chat/chat.style:987 | boxRadius | 22px (через boxRadius, менять не надо) | |
| defaultToast.radius | lib_ui/ui/widgets/widgets.style:1556 | 8px | 22px (тост 44 высотой = пилюля) | toast |
| defaultImportantTooltip.radius | lib_ui/ui/widgets/widgets.style:1294 | 4px | 8px | |
| defaultTooltip | lib_ui/ui/widgets/widgets.style:1276 | через roundRadiusSmall (tooltip.cpp) | 6px через roundRadiusSmall | |
| defaultTable.radius | lib_ui/ui/widgets/widgets.style:800 | 6px | 16px (mokaRadiusItem) | |
| defaultTableSmallButton | lib_ui/ui/widgets/widgets.style:780-787 | h18, radius 9 | h24, radius 12 (мелкая пилюля; вне шкалы 40/44/48, оставить как «чип») | |
| customEmojiTextBadge | lib_ui/ui/widgets/widgets.style:742-745 | h16, radius 4 | не менять (бейдж) | |
| defaultScrollArea.round | lib_ui/ui/widgets/widgets.style:813 | 2px | не менять | |
| defaultPeerListCheckbox | lib_ui/ui/widgets/widgets.style:1247-1248 | imageRadius 21 / small 18 | не менять (аватар круглый) | |

### 1.2 Кнопки (RoundButton / FlatButton)

Главное: в `RoundButton` уже есть `fullRadius: bool` (widgets.style:103,
buttons.cpp:308,488-493,590). `fullRadius: true` рисует настоящую пилюлю с
радиусом `height/2`. Достаточно поставить его в базовых `defaultActiveButton`
(widgets.style:718), и наследники (`defaultLightButton`, `defaultBoxButton`,
`attentionBoxButton`, ~70 кнопок в разных .style) станут пилюлями. Кнопки с
явным `radius:` ниже перечислены отдельно: у них `fullRadius` надо тоже
наследовать (он наследуется по цепочке стилей, `radius` перекрывается только
если fullRadius выключен).

| Константа | Файл:строка | Было | Станет |
|---|---|---|---|
| defaultActiveButton.height / textTop / width | lib_ui/ui/widgets/widgets.style:718-735 | h34, textTop 8, width -34 | h40 (mokaButtonS), textTop 11, width -32; + `fullRadius: true` |
| defaultLightButton | widgets.style:753 | наследует | наследует |
| defaultBoxButton | lib_ui/ui/layers/layers.style:44-49 | h34, textTop 7, width -30 | h44 (M), textTop 13, width -32 |
| Box.buttonHeight | layers.style:124-132 (defaultBox) | 34px | 44px |
| Box.buttonPadding | layers.style:125 | margins(6,10,10,10) | margins(8,12,16,16) (4/8/12/16) |
| Box.buttonWide | layers.style:27 (поле), :124 (defaultBox) | false | true: кнопки на всю ширину и по центру (value-only, код есть: box_layer_widget.cpp:346,358) |
| webviewDialogSubmit | layers.style:229 | h34 | h44 |
| backgroundConfirm, ...Cancel | boxes/background_preview_box.style:36,41 | h44 | оставить 44 |
| proxyApplyBoxButton | boxes/boxes.style:285 | h38 | h44 |
| sponsoredUrlButton | boxes/boxes.style:414 | h32, radius roundRadiusLarge | h40, fullRadius |
| requestsAcceptButton / requestsRejectButton | boxes/boxes.style:447,452 | h28 | h40 (в списках) или 32 как чип |
| collectibleCopy | boxes/boxes.style:518 | h36, radius 6 | h40, fullRadius |
| peerQrGiftsBrowse | boxes/boxes.style:677 | h34 | h40 |
| aiComposeBoxButton, aiToneDeleteButton | boxes/boxes.style:744, compose_ai_box.style:112 | h42 | h44 |
| aiTonePreviewAnotherExampleButton | compose_ai_box.style:161 | h26, radius 8 | h32 чип, радиус 16 |
| urlAuthCodesButton | boxes/url_auth_box_content.style:33 | h58 | h48 |
| introNextButton | intro/intro.style:79 | h42, radius 6 | h48, fullRadius (первый экран входа) |
| passportPasswordSubmit | passport/passport.style:48 | h44 | оставить |
| infoOpenApp | info/info.style:584 | h40 | оставить 40 |
| inviteLinkButton | info/info.style:1027 | h36, radius 6 | h40, fullRadius |
| similarChannelsLock | info/info.style:1224 | h44 | оставить |
| dialogsTopBarRightButton | dialogs/dialogs.style:172 | h22 | h28 чип (внутри строки) |
| dialogsUnconfirmedAuthButton | dialogs/dialogs.style:934-938 | h26, radius 10 | h32, fullRadius |
| postsSearchIntroButton | dialogs/dialogs.style:898 | h42 | h44 |
| dialogsUpdateButton (FlatButton) | dialogs/dialogs.style:453 | h46 | h48 |
| dialogsLoadMoreButton (FlatButton) | dialogs/dialogs_widget.style:42 | h36 | h40 |
| historyComposeButton (FlatButton) | chat_helpers/chat_helpers.style:1044 | h46, textTop 14 | h48 (L), textTop 15 |
| historyContactStatusButton | chat_helpers/chat_helpers.style:1082 | h49 | h48 |
| switchPmButton | chat_helpers/chat_helpers.style:346 | h34 | h40 |
| stickerSetBoxRemoveButton | chat_helpers/chat_helpers.style:474 | h42 | h44 |
| historyPinnedBotButton | chat_helpers/chat_helpers.style:1182 | h30 | h32 |
| historyBotMenuButton | ui/chat/chat.style:254 | h30 | h32 |
| historyPremiumViewSet | ui/chat/chat.style:212 | h44 | оставить |
| previewMarkRead | ui/chat/chat.style:996 | h39 | наследует historyComposeButton (h48) |
| settingsFilterAddRecommended, settingsChatbotsAddButton | settings/settings.style:338,669 | h26 | h32 чип |
| requestsAddAllButton/DeclineAll | info/community_requests/info_community_requests_widget.style:37,41 | h32 | h40 |
| channelEarnHistoryRecipientButton | info/channel_statistics/earn/channel_earn.style:73 | h34, radius 8 | h40, fullRadius |
| giveawayGiftCodeStartButton / BoxButton | info/channel_statistics/boosts/giveaway/giveaway.style:49,164 | h42, radius 6 | h44, fullRadius |
| pickLocationChooseOnMap | ui/controls/location_picker.style:60 | h44 | оставить |

Чипы (внутристрочные мелкие пилюли 24/28/32) в шкалу «40/44/48» не входят: это
отдельный класс `mokaChip*` (24, 28, 32), радиус = h/2, всегда `fullRadius`.

Формула вертикали текста: шрифт кнопки 14px semibold ≈ 18px высотой, поэтому
`textTop = (height - 18) / 2` (40 -> 11, 44 -> 13, 48 -> 15, 32 -> 7, 28 -> 5).
Значения для кнопок, где textTop зашит руками, пересчитать по формуле и сверить
на экране.

### 1.3 Поля ввода

`InputField` (widgets.style:278-330) уже умеет скруглённую плашку: при
`borderRadius > 0` рисуется заливка `textBg` + рамка `border` с этим радиусом
(lib_ui/ui/widgets/fields/input_field.cpp:2871-2899). Радиус не авто-пилюля, надо
ставить `height/2` руками.

| Константа | Файл:строка | Было | Станет |
|---|---|---|---|
| defaultInputField (поля в боксах, подчёркивание) | lib_ui/ui/widgets/widgets.style:1028-1060 | borderRadius 0, border 1, heightMin 55, textMargins(0,28,0,4) | borderRadius 22, border 1, heightMin 44, textMargins(16,0,16,0) (плавающий плейсхолдер выключить: `placeholderScale 0`, `placeholderShift -50px`, как у historyComposeField); К: у подчёркнутых полей с плавающим лейблом ломается анимация, проверять каждое |
| dialogsFilter (поиск чатов) | dialogs/dialogs.style:314-345 | borderRadius 18, heightMin 35 | borderRadius 22, heightMin 44 (+ найти места, где высота 35 зашита в коде: dialogs_widget.cpp) |
| historyComposeField | chat_helpers/chat_helpers.style:1307-1326 | heightMin 36, heightMax 72, border 0 | heightMin 44, textMargins(0,0,0,0) |
| defaultComposeControls.radius | chat_helpers/chat_helpers.style:1653-1655 | 0px | 22px (К: см. 1.7) |
| storiesComposeControls.radius | media_view/media_view.style:778-781 | storiesComposeRadius 21 | не менять (вне фазы) |

### 1.4 Размеры строк, отступы (общее)

| Константа | Файл:строка | Было | Станет |
|---|---|---|---|
| boxTitleHeight | layers.style:82 | 48 | 56 (радиус 28 = центр дуги на отметке 28; заголовок высотой 56 целиком лежит в зоне углов) |
| boxTitlePosition | layers.style:81 | point(24,13) | point(28,18) (текст не касается дуги); центрирование заголовка К |
| boxRowPadding | layers.style:87 | margins(24,0,24,0) | margins(24,0,24,0) (шкала 24, оставить) |
| boxPadding | layers.style:119 | margins(24,14,24,8) | margins(24,16,24,8) |
| boxTopMargin | layers.style:89 | 8 | 16 |
| boxLittleSkip, boxMediumSkip | layers.style:121,122 | 10, 20 | 8, 16 |
| defaultBox.margin | layers.style:124-132 | margins(0,10,0,10) | margins(0,16,0,16) (защита углов при 28, см. раздел 5) |
| boxWidth, boxWideWidth | layers.style:117,118 | 320, 364 | 360, 400 (поля 24 + кнопки 44 в ряд) |
| boxDividerHeight | widgets.style:677 | 8 | 8 (оставить; зазор между секциями-карточками) |
| defaultBoxDividerLabelPadding | widgets.style:690 | margins(22,8,22,16) | margins(24,8,24,16) |
| defaultMenu.itemPadding | widgets.style:969 | margins(17,8,17,7) | margins(16,10,16,10) (высота пункта ≈ 17+20 = 37 -> 40 с шрифтом 13) |
| menuWithIcons.itemPadding / itemIconPosition | widgets.style:1695-1697 | margins(54,8,17,8), point(15,5) | margins(52,10,16,10), point(16,8) |
| defaultPopupMenu.scrollPadding | widgets.style:990 | margins(0,8,0,8) | margins(8,8,8,8) (поля вокруг пилюль-пунктов) |
| popupMenuWithIcons.scrollPadding | widgets.style:1710 | margins(0,5,0,5) | margins(8,8,8,8) |
| defaultSettingsButton | widgets.style:1510-1527 | h20, padding(22,10,22,8) | h20, padding(24,14,24,14) = строка 48 |
| settingsButton / NoIcon | settings/settings.style:13,25 | padding(60,10,22,10) / (22,10,22,8) | padding(64,14,24,14) / (24,14,24,14); iconLeft 20 -> 24 |
| infoProfileButton | info/info.style:618 | padding(79,10,8,8) -> УЖЕ правится: (79,14,8,14) | (80,14,16,14) |
| infoMainButton | info/info.style:629 | padding(23,10,8,8) -> УЖЕ (23,14,8,14) | (24,14,16,14) |
| defaultPeerListItem | widgets.style:1409-1417 | h58, photoSize 46, photoPosition(12,6), name(68,11), status(68,31) | h64, photoSize 48, photoPosition(16,8), name(76,13), status(76,34) |
| infoProfileLabeledPadding и 2 соседних | info/profile/info_profile_actions.style:10-12 | УЖЕ (23,12,20,10) | margins(24,12,24,12) |
| scrollBarMin, scroll width | widgets.style:813-815 | 10px | оставить |

### 1.5 Список чатов и папки (dialogs, window)

| Константа | Файл:строка | Было | Станет |
|---|---|---|---|
| dialogsRowHeight | dialogs/dialogs.style:91 | 62 | 68 |
| defaultDialogRow.height, padding, photoSize, nameLeft, nameTop, textLeft, textTop | dialogs.style:95-103 | 62, margins(10,8,10,8), 46, 68, 10, 68, 34 | 68, margins(12,10,12,10), 48, 76, 12, 76, 36 |
| communityRequestableListItem | dialogs.style:104-110 | зеркало defaultDialogRow (62, 46, (10,8), (68,10), (68,34)) | то же что строка выше (68, 48, (12,10), (76,12), (76,36)); эти 5 строк синхронизировать вручную |
| taggedDialogRow | dialogs.style:114-118 | h72, textTop 30, tagTop 52 | h78, textTop 33, tagTop 56 |
| forumDialogRow | dialogs.style:119-125 | h80, textTop 32 | h86, textTop 34 |
| taggedForumDialogRow | dialogs.style:126-129 | h96, tagTop 77 | h102, tagTop 81 |
| communityInfoDialogRow | dialogs.style:130-134 | padding(22,8,18,8), name/text 80 | padding(24,10,20,10), 88 |
| dialogsUnreadHeight / Padding | dialogs.style:79,80 | 19 / 5 | 20 / 6 (бейдж пилюля) |
| dialogsFilterPadding / Skip | dialogs.style:92,93 | point(7,7) / 4 | point(8,8) / 4 |
| dialogsFilter (поиск) | dialogs.style:314-345 | см. 1.3 | |
| dialogsSearchInHeight, PhotoSize, PhotoPadding, Skip | dialogs.style:474-477 | 38, 28, 10, 10 | 44, 32, 12, 8 |
| dialogsImportantBarHeight | dialogs.style:215 | 37 | 40 |
| dialogsSearchTabs / chatsFiltersTabs | dialogs.style:760-787 | padding 9, h33, barTop 30, barStroke 6, barRadius 2, barFg transparent | пилюля под активным ярлыком: height 40, barTop 4, barStroke 32, barRadius 16, barFg lightButtonBg, padding 12, strictSkip 12; Т по замыслу, ПРОВЕРИТЬ: порядок рисования плашки и подписи в ui/widgets/discrete_sliders.cpp:438-523 (barSnapToLabel рисует плашку по ширине ярлыка), если плашка рисуется поверх текста, то К |
| dialogsTopBarRightButton, dialogsCommunityRequestsBubbleHeight/Radius | dialogs.style:172; dialogs_widget.style:62-66 | h22; 44 / 11 | h28; 44 / 22 |
| windowFiltersWidth | window/window.style:229 | 72 | 80 (пилюли 64 + поля 8) |
| windowFiltersButton | window.style:230-246 | minHeight 62, textTop 40, textSkip 6, badgeHeight 17, badgePosition(3,7), iconPosition(-1,6) | minHeight 64, textTop 40, badgeHeight 18; К: плашка 64x56 радиус 16 (side_bar_button.cpp:170 заливает прямоугольник) |
| windowFiltersButtonTextOnly | window.style:247-251 | minHeight 44 | 48 |
| windowFiltersButtonIconsOnly | window.style:252-255 | minHeight 54 | 56 |
| windowScreenReaderButtonRadius | window.style:197 | 14 | не менять |
| mainMenuCoverHeight | window/window_main_menu.style:11 | 134 | не менять |
| main menu item (itemPadding) | window_main_menu.style:40 | margins(76,13,28,13) | margins(76,14,24,14) |
| columnMinimalWidthLeft / MaximalWidthLeft | window.style:34,35 | 260 / 540 | не менять |
| macWindowRoundRadius | window.style:408 | 10 | не менять (системное) |

### 1.6 Окно чата, верхняя панель

| Константа | Файл:строка | Было | Станет |
|---|---|---|---|
| topBarHeight | info/info.style:923 | 54 | 56 (шапка чата и инфо-панелей) |
| topBarActionButtonLargeRadius | info/info.style:977 | 8 | 16 |
| topBarInfoButtonSize | info/info.style:979 | size(52, topBarHeight) | size(56, topBarHeight) |
| infoLayerTopBar.radius | info/info.style:377 | boxRadius | boxRadius (станет 22; для слоя нужен 28, К: info_layer_widget.cpp:310,364) |
| historyToDown (кнопка вниз) | chat_helpers/chat_helpers.style:1207-1227 | круг ~46 | оставить (уже круг) |
| historyToDownBadgeSize | chat_helpers.style:1224 | 22 | оставить |
| historyReplyHeight | chat_helpers.style:1146 | 49 | 56 (панель ответа/правки над полем) |
| historyReplySkip / IconPosition | chat_helpers.style:1144,1147 | 53 / point(7,7) | 56 / point(8,12) |
| moreChatsBarHeight и др. «bars» | chat_helpers.style:1675 | 48 | 48 |

### 1.7 Поле ввода (composer)

| Константа | Файл:строка | Было | Станет |
|---|---|---|---|
| defaultComposeControls.bg / radius / padding | chat_helpers/chat_helpers.style:1653-1656 | historyComposeAreaBg / 0 / (2, 9, 2, 9) | #282828-подложка (цвет в теме) / 22 / margins(8, 8, 8, 8) |
| historyComposeField | chat_helpers.style:1307 | heightMin 36 | 44 (мин. высота пилюли поля 44, радиус composer 22) |
| historyAttach | chat_helpers.style:1333-1342 | 44x46, rippleArea 40 @(2,3) | 44x44, rippleArea 40 @(2,2) |
| historySendRight / historySendPadding | chat_helpers.style:1329-1330 | 2 / 9 | 8 / 8 |
| historySend (inner, recordSize, stopRadius) | chat_helpers.style:1523-1540 | recordSize 26, stopRadius 3 | recordSize 28, stopRadius 4 |
| historyAiComposeButton | chat_helpers.style:1541 | 28x28 | 32x32 |
| historyComposeFieldMaxHeight | chat_helpers.style:1327 | 224 | не менять |

Код К: composer в upstream это одна полоса во всю ширину. `ComposeControls`
уже имеет `radius` (history_view_compose_controls.cpp:1301-1302,5718-5730:
при radius > 0 рисует `drawRoundedRect(full, r, r)`), то есть закругление фона
значением. Но внешние поля вокруг пилюли (8 слева/справа/снизу) и прозрачность
области вне пилюли надо делать кодом в `HistoryWidget::updateControlsGeometry`
(history/history_widget.cpp:8241) и в моменте раскладки поля (:7569
`_field->moveToLeft`), плюс убрать заливку `historyComposeAreaBg` под композером
(history_view_compose_controls.cpp:398) и в барах `ui/chat/group_call_bar.cpp:276`,
`more_chats_bar.cpp:114`, `requests_bar.cpp:138`, `chat_helpers/bot_keyboard.cpp:205`.

### 1.8 Пузыри сообщений

| Константа | Файл:строка | Было | Станет |
|---|---|---|---|
| bubbleRadiusLarge | ui/chat/chat.style:327 | 16px | 18px |
| bubbleRadiusSmall | ui/chat/chat.style:326 | roundRadiusLarge (6px) | 6px явно (развязать от roundRadiusLarge, который растёт до 12) |
| msgPadding | chat.style:25 | margins(11,8,11,8) | margins(12,8,12,8) |
| msgMargin | chat.style:52 | margins(16,6,56,2) | margins(16,4,56,4) |
| msgServicePadding / Margin | chat.style:95,96 | margins(12,3,12,4) / (10,10,10,2) | margins(12,4,12,4) / (8,8,8,4) |
| msgDateImgPadding | chat.style:103 | point(8,2) | point(8,3) |
| msgFileThumbRadiusSmall / Large | chat.style:378,379 | 4 / 12 | 8 / 16 |
| tagInfoPreviewBubbleRadius / PreviewRadius | chat.style:33,37 | 8 / 8 | 16 / 16 |
| chatUniqueMessageBubble.radius | chat.style:1139 | 10 | 16 |
| msgServiceGiftBoxRadius | chat.style:741 | 20 | 22 |
| unsupportedNoticeRadius | chat.style:763 | 10 | 16 |
| historyPageEnlargeRadius | chat.style:554 | 8 | 12 |
| historyTranscribeRadius | chat.style:442 | 4 | 8 |

Код: `BubbleRadiusLarge()/BubbleRadiusSmall()` (ui/chat/chat_style_radius.cpp:28-42)
читают эти константы; углы кэшируются `Images::CornersMask(r)`
(message_bubble.cpp:101,102,304,305). Предел радиуса: однострочный пузырь
≈ 8+8+~20 = 36px, поэтому `bubbleRadiusLarge` не больше 18 (половина высоты),
иначе верхние и нижние углы наложатся. Хвост и склейка соседних пузырей уже
считают `Small` для внутренних углов, значит схема «18 снаружи, 6 внутри»
сохраняется без кода. Опция `use-small-msg-bubble-radius`
(chat_style_radius.cpp:16) оставить.

### 1.9 Боксы, слои, диалоги

| Константа | Файл:строка | Было | Станет |
|---|---|---|---|
| boxRadius | lib_ui/ui/layers/layers.style:38 | 8 | 22 |
| mokaRadiusWindow (НОВАЯ) | lib_ui/ui/basic.style | нет | 28, К: подставить в 13 файлах (1.12) |
| boxRoundShadow | layers.style:71 | roundShadowRadius8px (иконки round_shadow_box_* 23x23, 10x1, 1x10 запечены под радиус 8) | К: новая тень, см. раздел 5 п.2 |
| boxDuration | layers.style:37 | 200 | не менять |
| localStorageIslandRadius | boxes/boxes.style:113 | 12 | 22 (карточки настроек хранилища) |
| peerQrPanelRadius / peerQrGiftRadius | boxes/boxes.style:630,660 | 24 / 14 | 22 / 16 |
| aiToneFieldRadius | boxes/compose_ai_box.style:94 | 12 | 22 (поле) |
| aiComposeTabsRadius | compose_ai_box.style:13 | 29 | 22 (h44) |
| aiComposeStyleTabsRadius | ui/controls/labeled_emoji_tabs.style:12 | 14 | 16 |
| keysLegendCapRadius | boxes/keys_legend.style:44 | 4 | 8 |
| pollOpenLinkUrlRadius, pollAttachRadius, historyPollAnswerThumbRadius | boxes/polls.style:163,150,151 | 16, 7, 9 | 22, 8, 12 |
| historyPollFillingRadius, historyPollCheckboxRadius | polls.style:37,52 | 2, 3 | не менять (микро) |
| scheduleRepeatRadius | ui/boxes/choose_date_time.style:51 | 14 | 16 |
| filterLinkPreviewRadius | ui/controls/filter_link_header.style:27 | 13 | 16 |
| collectibleMore | ui/boxes/collectible_info_box.style:23-26 | h36, radius 6 | h44, fullRadius |
| calendarBox rounds | ui/boxes/calendar_box.style:17 | round 1 | не менять |
| stickersAddCellBgRadius | chat_helpers/chat_helpers.style:493 | 28 | 22 (карточка набора) |
| emojiSetAddCellBgRadius | chat_helpers.style:495 | 16 | 16 |
| emojiPanRadius | chat_helpers.style:523 | 8 | 22 (панель эмодзи/стикеров, tabbed_panel.cpp:78,251,389,390,514,516; tabbed_selector.cpp:385; 11 файлов, 40 использований, включая внутренние ячейки: ПРОВЕРИТЬ, внутренние hover-ячейки лучше оставить 8, значит заводить `emojiPanCellRadius` 8 К) |
| emojiPanEmojiPreviewRadius | chat_helpers.style:526 | 8+8+4 | 20 |
| stickersEmojiPickerExpandedRadius | chat_helpers/emoji_picker_overlay.style:10 | 20 | 22 |
| stickersPhotoButtonRadius | chat_helpers.style:641 | 8 | 8 |

### 1.10 Настройки

| Константа | Файл:строка | Было | Станет |
|---|---|---|---|
| settingsButton | settings/settings.style:13-17 | см. 1.4 | см. 1.4 |
| settingsCheckboxPadding | settings.style:173 | margins(22,10,10,10) | margins(24,12,12,12) |
| settingsCheckboxesSkip | settings.style:175 | 12 | 12 |
| settingsScalePadding / BigScalePadding | settings.style:90,91 | (60,7,22,4) / (21,7,21,4) | (64,8,24,4) / (24,8,24,4) |
| settingsExperimentalTitle/AboutPadding | settings.style:76,77 | (22,9,66,1) / (22,0,66,9) | (24,12,66,4) / (24,0,66,12) |
| settingsIconRadius | settings.style:444 | 6 | 8 (цветные иконки пунктов) |
| iconRadius (settings) | settings.style:764 | 10 | 12 |
| settingsThemeBubbleRadius | settings.style:290 | 2 | не менять |
| chatThemeBubbleRadius | settings.style:303 | 10 | 16 |
| settingsFilterAddRecommended | settings.style:338 | h26 | h32 чип |
| settings_local_storage | settings/sections/settings_local_storage.style | см. localStorageIslandRadius | |

Карточный вид секций (секция = строки в одной подложке, между секциями
зазор 8) делается в одном месте: `Ui::BoxContentDivider::paintTop/paintBottom`
(lib_ui/ui/widgets/box_content_divider.cpp:29-57). Сейчас делитель заливает
прямоугольник цвета `boxDividerBg` и рисует полосы `box_divider_top/bottom`
(PNG 1x5). Все секции настроек, профиля и боксов разделены именно им. К:
рисовать на делителе вогнутые скруглённые углы соседних секций радиусом 22
(цвет карточки windowBg, маски `Images::CornersMask`) и боковые зазоры 16.
Боковые зазоры требуют обёртки вокруг секций (settings_common.cpp, info_section_widget.cpp,
info/info_wrap_widget.cpp): два уровня реализации, см. раздел 4.

### 1.11 Профиль (info)

| Константа | Файл:строка | Было | Станет |
|---|---|---|---|
| infoProfileTopBarPhotoSize | info/profile/info_profile_top_bar.style:61 | 80 | 96 |
| infoProfileTopBarTopicStatusButton.radius | info_profile_top_bar.style:89-91 | 4 | fullRadius, h24 |
| infoProfileTopBarShowLastSeen | info_profile_top_bar.style:92 | h18 | h24 чип, fullRadius |
| infoProfileTopBarActionButtonsSpace | info_profile_top_bar.style:75 | 10 | 8 |
| infoProfileTopBarActionMenuSkip | info_profile_top_bar.style:76 | 10 | 8 |
| inviteLinkFieldRadius | info/info.style:1003 | 5 | 16 |
| shortInfoCover.radius | info/info.style:1196 | boxRadius | 22 через boxRadius (без правки) |
| infoLayerTopBar.radius | info/info.style:377 | boxRadius | см. 1.6 |
| infoHoursOuterMargin | info_profile_actions.style (infoHoursOuter) | margins(8,4,8,4) | margins(8,4,8,4) |
| infoBlockButtonSkip | info_profile_actions.style | 8 | 8 |
| infoOpenAppMargin | info_profile_actions.style | margins(16,12,16,12) | оставить |

### 1.12 boxRadius в коде: что слой, что карточка

Слой-окно (получает `mokaRadiusWindow` 28, это ~13 файлов, ~30 мест):
`lib_ui/ui/layers/box_layer_widget.cpp:45,137,141,148`,
`lib_ui/ui/layers/layer_widget.cpp:288,382,385`,
`lib_ui/ui/cached_special_layer_shadow_corners.cpp:19,20,23`,
`SourceFiles/ui/effects/layer_backdrop.cpp:75,76`,
`SourceFiles/ui/cached_round_corners.cpp:80` (BoxCorners),
`info/info_layer_widget.cpp:310,364`, `info/info_wrap_widget.cpp:1022,1032`,
`info/info_section_widget.cpp:55,56`, `dialogs/ui/dialogs_suggestions.cpp:2390,2391`,
`window/window_chat_switch_process.cpp:193,224`, `history/history_drag_area.cpp:559,560`,
`ui/top_background_gradient.cpp:88` (шапка бокса с градиентом).

Остальное (остаётся `boxRadius`, становится 22 как карточка): settings/sections/settings_chat.cpp
(12 использований), calls/group/calls_group_panel.cpp (7), info/profile/info_profile_top_bar.cpp (6),
ui/effects/peer_qr_surface.cpp (5), boxes/reactions_settings_box.cpp (5),
ui/controls/subsection_tabs_slider.cpp (4), settings/settings_intro.cpp (4),
info/peer_gifts/info_peer_gifts_widget.cpp (4), boxes/star_gift_craft_animation.cpp (4)
и ещё ~40 файлов по 1-3 использования (wallet, statistics, boxes/star_gift_*,
settings/business/*, boxes/premium_preview_box.cpp, boxes/stickers_box.cpp и др.).

## 2. Единая таблица токенов

Все токены добавляются одним блоком в `lib_ui/ui/basic.style` (после строки 108),
то есть одна пересборка PCH. Имена с префиксом `moka`, чтобы не конфликтовать с
upstream при обновлениях.

### 2.1 Радиусы

| Токен | Значение | Для чего |
|---|---|---|
| mokaRadiusWindow | 28 | боксы, слои, спец-слои, панель главного меню |
| mokaRadiusCard | 22 | карточки/секции, плавающие колонки, меню, поповеры, тост, композер, панель эмодзи |
| mokaRadiusItem | 16 | подложки строк (чат, пункт меню, ячейка), мелкие карточки, превью, поля с 2 строками |
| mokaRadiusSmall | 8 | миниатюры, плашки, подсказки, ячейки сетки, иконки-плитки |
| mokaRadiusMicro | 4 | индикаторы, чекбоксы, прогресс (не менять существующее 2-4) |
| mokaRadiusPill40 / 44 / 48 | 20 / 22 / 24 | поля и объекты, где радиус задаётся числом (кнопки через `fullRadius`) |
| mokaRadiusChip24/28/32 | 12 / 14 / 16 | мелкие внутристрочные пилюли |

Тонкость: в Qt `drawRoundedRect` с радиусом больше половины стороны
ограничивается, а кэш углов (`PrepareCorners`, `Images::CornersMask`) растёт
квадратично, поэтому «бесконечный» радиус (999) НЕ использовать, радиус
считается как `height / 2`.

### 2.2 Карта «старая константа -> токен»

| Старая | Станет | Токен |
|---|---|---|
| boxRadius (8) | 22 (карточка) | mokaRadiusCard |
| boxRadius в слоях (код) | 28 | mokaRadiusWindow |
| roundRadiusLarge (6) | 12 | между Small и Item: значение 12, отдельного токена нет, оставить имя |
| roundRadiusSmall (3) | 6 | значение 6, оставить имя |
| buttonRadius (4) | 20 | mokaRadiusPill40 (фоллбэк; основной путь fullRadius) |
| innerDropdownRadius (8) | 22 | mokaRadiusCard |
| defaultPopupMenu.radius (8) | 22 | mokaRadiusCard |
| defaultToast.radius (8) | 22 | mokaRadiusCard (тост ≥ 44 высотой) |
| emojiPanRadius (8) | 22 | mokaRadiusCard |
| bubbleRadiusLarge (16) | 18 | не токен, ограничение высотой пузыря |
| bubbleRadiusSmall (= roundRadiusLarge 6) | 6 | развязка |
| dialogsFilter.borderRadius (18) | 22 | mokaRadiusPill44 |
| aiComposeCardRadius, aiTonePreviewExampleCardRadius (22) | 22 | mokaRadiusCard (уже) |
| callRateRadius, stickersAddCellBgRadius (28) | 28 / 22 | Window / Card |
| peerQrPanelRadius (24) | 22 | mokaRadiusCard |
| localStorageIslandRadius (12) | 22 | mokaRadiusCard |
| defaultTable.radius, inviteLinkFieldRadius, previewRadius и т.п. (5..12) | 16 | mokaRadiusItem |
| keysLegendCapRadius, historyTranscribeRadius, topPeersRadius (4) | 8 | mokaRadiusSmall |

### 2.3 Шкала отступов

Базовая сетка 4: `mokaSkip4/8/12/16/24` = 4, 8, 12, 16, 24 (плюс 2 для микро).

| Где | Токен |
|---|---|
| внутри иконок и бейджей, зазор между чипами | 4 |
| зазор между пилюлями, поля карточек в колонках, поля вокруг пунктов меню | 8 |
| вертикаль в строках (меню 10, настройки 14: см. таблицу), внутр. поля поля ввода | 12 |
| боковые поля строк, зазор между секциями-карточками, поля боксов нижней панели | 16 |
| поля боксов (boxRowPadding), горизонт. поля строк настроек, группы | 24 |

Строки со значением 10 и 14 (меню, настройки) это сумма 4+... вынужденные
отступы по высоте текста (17..20px); в шкалу они не входят, а подбираются под
высоту строки (см. ниже), поэтому в таблицах они помечены «по высоте строки».

### 2.4 Высоты

| Токен | Значение | Где |
|---|---|---|
| mokaButtonS | 40 | кнопки в списках, карточках, инфо; поля меню |
| mokaButtonM | 44 | кнопки боксов, поля ввода, поиск, composer |
| mokaButtonL | 48 | главные кнопки экранов (composer-кнопки, вход, нижние CTA) |
| mokaChip24/28/32 | 24 / 28 / 32 | мелкие пилюли в строках |
| mokaRowMenu | 40 | пункт меню |
| mokaRowSettings | 48 | строка настроек и профиля (20 текст + 14 + 14) |
| mokaRowList | 64 | строки пир-листов (контакты, поделиться), фото 48 |
| mokaRowChat | 68 | строка списка чатов (фото 48, поля 10/12) |
| mokaTopBar | 56 | шапка чата и инфо |
| mokaBoxTitle | 56 | заголовок бокса |
| mokaComposer | 44 | минимум высоты пилюли ввода |

Для 40/44/48 значение `textTop` у RoundButton = `(h - 18) / 2` (11/13/15).

## 3. Независимые участки работы

Правило: участок правит только свои файлы/диапазоны строк. Общие файлы
разделены по диапазонам, git сливает такие правки без конфликта, потому что
правятся разные блоки. Порядок: A0 первым (один коммит, одна полная пересборка),
остальные A1-A8 параллельно после слияния A0, дальше правят только значения.

| # | Участок | Владеет файлами (диапазоны) | Кодовые задачи (К) | Параллельно с |
|---|---|---|---|---|
| A0 | Фундамент: токены | `lib_ui/ui/basic.style` (после :108, блок moka*; roundRadiusLarge/Small :107,108; dateRadius :110), `lib_ui/ui/layers/layers.style` ТОЛЬКО :38 и :71 | форк lib_ui или патч; замена `boxRadius` на `mokaRadiusWindow` в 13 файлах слоёв (1.12), код из C-7 | никем (первым) |
| A1 | Папки и боковая панель | `window/window.style` :190-410 (windowFilters*, sideBar*), `window/window_main_menu.style`, `dialogs/dialogs.style` :745-800 (вкладки папок) | К: пилюли в `lib_ui/ui/widgets/side_bar_button.cpp:170,239` (плашка активной папки 64x56 r16, ripple RoundRectMask), раскладка в `window/window_filters_menu.cpp`; вкладки SettingsSlider `ui/widgets/discrete_sliders.cpp:438-523` если плашка не получается значениями | A2-A8 |
| A2 | Список чатов | `dialogs/dialogs.style` (кроме :745-800), `dialogs/ui/dialogs_layout.style`, `dialogs/dialogs_widget.style` | К: скруглённая подложка строки и боковой отступ 8: `dialogs/ui/dialogs_layout.cpp:487` (`p.fillRect(geometry, bg)`), ripple `dialogs/dialogs_row.cpp:344` (RectMask -> RoundRectMask), ширина строки в `dialogs_inner_widget.cpp:1060-1351` (все `fillRect`), строки результатов поиска там же; `dialogs/ui/dialogs_suggestions.cpp:403` уже RoundRectMask | A1, A3-A8 |
| A3 | Окно чата и composer | `chat_helpers/chat_helpers.style` :1044-1180 (кнопки/панели), :1300-1560 (composer, send, attach), :1653-1656; `info/info.style` :923-993 (topBar* шапка чата) | К: поля вокруг composer и прозрачная область: `history/history_widget.cpp:7569,8241`, `history/view/controls/history_view_compose_controls.cpp:398,1301,5718-5730`; бары `ui/chat/group_call_bar.cpp:276`, `more_chats_bar.cpp:114`, `requests_bar.cpp:138`; плавающие колонки (C-4): `mainwidget.cpp:2657` `MainWidget::updateControlsGeometry`, `_sideShadow`/`_thirdShadow` (mainwidget.cpp:283,2087-2090) | A1, A2, A4-A8 (info.style: только :923-993) |
| A4 | Пузыри | `ui/chat/chat.style` :14-120, :320-380, :430-770, :1130-1240; `ui/chat/chat_style.style`; `boxes/polls.style` | нет кода (значения); проверить min. высоту пузыря после 18 | A1-A3, A5-A8 |
| A5 | Меню и попапы | `lib_ui/ui/widgets/widgets.style` :957-1030 (Menu/PopupMenu/PillTabs), :1250-1300 (InnerDropdown, Tooltip), :1550-1560 (Toast), :1695-1730 (menuWithIcons), `ui/menu_icons.style` (только позиции иконок) | К: пилюля-подсветка пункта и боковой отступ: `lib_ui/ui/widgets/menu/menu_action.cpp:100-102` (fillRect), ripple-маска там же, `menu/menu.cpp:57`, `popup_menu.cpp:964,1270,1273,1471` (заливки itemBg) | A1-A4, A6-A8 |
| A6 | Боксы и диалоги | `lib_ui/ui/layers/layers.style` (кроме :38, :71), `lib_ui/ui/widgets/widgets.style` :716-830 (кнопки), :1028-1062 (InputField), :1409-1500 (PeerList), `boxes/boxes.style`, `boxes/*.style`, `ui/boxes/*.style`, `chat_helpers.style` :346-500 (стикерные боксы), :1631+ | К: C-7 тень слоя `layer_widget.cpp:272-331,560-574`, `cached_special_layer_shadow_corners.cpp:15-60`; центрирование заголовка бокса и кнопок (`box_layer_widget.cpp`, `box_content.cpp`); подложка hover строк peer list (`boxes/peer_list_box.cpp`) | A1-A5, A7, A8 |
| A7 | Настройки | `settings/settings.style`, `settings/sections/*.style`, `info/info.style` :600-660 (infoProfileButton, infoMainButton: от них наследуется settingsButton, отдать этому участку) | К: карточный вид секций через `lib_ui/ui/widgets/box_content_divider.cpp:29-57` (общее с A8), обёртка с боковыми зазорами в `settings/settings_common.cpp` | A1-A6, A8 |
| A8 | Профиль | `info/info.style` (остальное, кроме :600-660 и :923-993), `info/profile/*.style` (info_profile_top_bar, info_profile_actions, info_levels), `info/userpic/info_userpic_builder.style` | К: карточки блоков профиля: `info/info_section_widget.cpp:55,56`, `info/info_wrap_widget.cpp:1022,1032`; `info_layer_widget.cpp:310,364` (радиус слоя = Window) | A1-A7 |

Файлы с общим владением (поэтому важно держаться диапазонов): `info/info.style`
(A3, A7, A8), `lib_ui/ui/widgets/widgets.style` (A5, A6), `dialogs/dialogs.style`
(A1, A2), `chat_helpers/chat_helpers.style` (A3, A6), `ui/chat/chat.style`
(A4 и пара блоков в A3: previewMenu :980-1000 это A5). Общий `box_content_divider.cpp`
делает один исполнитель (A7), A8 только использует.

Зависимости между участками: A7 -> A8 (наследование infoProfileButton), A0 -> все,
A6 -> A5 (Box тень и меню не пересекаются, но кнопки A6 используются в меню). Если
исполнителей меньше, склеить: A1+A2, A5+A6, A7+A8.

## 4. Значениями или кодом, пересборка

### 4.1 Только значения констант (.style)

| Что | Как |
|---|---|
| Все радиусы из раздела 1 (кроме 1.12 слоёв) | числа в .style |
| Пилюли кнопок | `fullRadius: true` в `defaultActiveButton` (widgets.style:718) и в кнопках с явным `radius:`; у `RoundButton` код есть (buttons.cpp:488-493,590) |
| Высоты кнопок 40/44/48, textTop | числа в .style, формула `(h-18)/2` |
| Высоты строк (чат, пир-лист, настройки, меню) и внутренние отступы | числа в .style |
| Ширина/полнопоточная кнопка бокса | `Box.buttonWide: true` в defaultBox (код есть: box_layer_widget.cpp:346,358) |
| Скруглённая плашка поиска и полей | `InputField.borderRadius` > 0 (input_field.cpp:2871) |
| Скруглённый фон composer (сам прямоугольник) | `defaultComposeControls.radius: 22px` (код есть, как у stories) |
| Радиусы пузырей | bubbleRadiusLarge/Small |
| Шапки, панели, ширины боксов | числа |
| Вкладки папок как пилюли | ВЕРОЯТНО значениями (barTop/barStroke/barRadius/barFg), проверить на экране |

### 4.2 Нужен код

| # | Что | Где |
|---|---|---|
| C-1 | Скруглённая подложка строки чата с боковым отступом | dialogs/ui/dialogs_layout.cpp:487, dialogs/dialogs_row.cpp:344, dialogs/dialogs_inner_widget.cpp:1060-1351 |
| C-2 | Пилюли папок в боковой панели | lib_ui/ui/widgets/side_bar_button.cpp:170,239; window/window_filters_menu.cpp |
| C-3 | Пилюля-подсветка пункта меню, отступ 8 | lib_ui/ui/widgets/menu/menu_action.cpp:100-102, menu/menu.cpp:57, popup_menu.cpp |
| C-4 | Плавающие колонки: зазоры 8 между списком/чатом/инфо, углы 22 | mainwidget.cpp:2657 (раскладка), :283,2087-2090 (PlainShadow заменить зазором); углы рисовать накладкой из 4 углов цвета страницы (#1c1c1c): для колонок это работает, потому что зазор залит ровным цветом (в отличие от боксов) |
| C-5 | Composer как плавающая пилюля: внешние поля, прозрачность области | history/history_widget.cpp:7569,8241; history_view_compose_controls.cpp:398 |
| C-6 | Карточки секций (делитель с вогнутыми углами) | lib_ui/ui/widgets/box_content_divider.cpp:29-57 (уровень 1), обёртки с боковыми зазорами в settings/settings_common.cpp, info/info_section_widget.cpp (уровень 2) |
| C-7 | Тень бокса под радиус 28 | lib_ui/ui/layers/layer_widget.cpp:272-331,560-574; cached_special_layer_shadow_corners.cpp:15-60; новые иконки round_shadow_box28_* или `Ui::BoxShadow` |
| C-8 | `mokaRadiusWindow` вместо `boxRadius` в слоях | 13 файлов, список в 1.12 |
| C-9 | Подложка hover строк peer list с инсетом | boxes/peer_list_box.cpp (+ ripple RoundRectMask) |
| C-10 | Центрирование заголовка бокса | lib_ui/ui/layers/box_content.cpp, box_layer_widget.cpp (позиция `boxTitlePosition`) |
| C-11 | Разделение `emojiPanRadius` на панель (22) и ячейку (8) | chat_helpers/tabbed_panel.cpp:78,251,389,390,514; tabbed_selector.cpp:385; остальные 40 использований остаются 8 через новую `emojiPanCellRadius` |
| C-12 | Развязка `bubbleRadiusSmall` от `roundRadiusLarge` | только .style (поэтому в 4.1), код не нужен; пункт для напоминания |

### 4.3 Пересборка: сколько объектов затрагивает каждый style_*.h

Считано `ninja -t deps` по `~/dev/mokagram-build/.ninja_deps` (транзитивные
включения, 1664 объекта SourceFiles + lib_ui); «напрямую» = `#include
"styles/style_X.h"` в .cpp. Нужно только когда в этом `.style` появляется или
исчезает ИМЯ; смена значения пересобирает один `style_X.cpp`.

| Заголовок | Из какого .style | Напрямую .cpp | Транзитивно (объектов) | Комментарий |
|---|---|---|---|---|
| style_basic.h | lib_ui/ui/basic.style | 47 (+3 .h, PCH) | все 1664 (PCH) | A0, один раз |
| style_widgets.h | lib_ui/ui/widgets/widgets.style | 144 (+20 .h) | 925 | включается из buttons.h, labels.h, checkbox.h, popup_menu.h |
| style_layers.h | lib_ui/ui/layers/layers.style | 296 | 291 | |
| style_chat.h | ui/chat/chat.style | 241 | 241 | |
| style_chat_helpers.h | chat_helpers/chat_helpers.style | 212 | 211 | |
| style_boxes.h | boxes/boxes.style | 159 (+1 .h) | 166 | |
| style_info.h | info/info.style | 143 | 143 | |
| style_settings.h | settings/settings.style | 128 (+1 .h) | 129 | |
| style_dialogs.h | dialogs/dialogs.style | 91 (+1 .h) | 90 | |
| style_window.h | window/window.style | 71 | 67 | |
| style_chat_style.h | ui/chat/chat_style.style | 23 | 23 | |
| style_polls.h | boxes/polls.style | 21 | 21 | |
| style_dialogs_layout.h | dialogs/ui/dialogs_layout.style | 1 | 1 | |
| style_window_main_menu.h | window/window_main_menu.style | 1 | 1 | |
| style_info_profile_actions.h | info/profile/info_profile_actions.style | 1 | 1 | |
| style_info_profile_top_bar.h | info/profile/info_profile_top_bar.style | 2 | 2 | |
| style_compose_ai_box.h | boxes/compose_ai_box.style | 5 | 5 | |
| style_menu_icons.h | ui/menu_icons.style | 168 | 167 | только позиции |
| style_calls / media_view / iv / premium / credits | вне фазы | 53 / 36 / 34(186 транз.) / 41 / 54 | 53 / 36 / 186 / 41 / 54 | не трогаем |

Практика: заводить ВСЕ новые имена (moka*, emojiPanCellRadius, mokaRadius*,
mokaRow*, mokaButton*, mokaChip*) в A0 одним коммитом и использовать их в
остальных `.style`. Тогда A1-A8 меняют значения, и после A0 каждая правка это
пересборка одного `style_X.cpp` и линковка. Если исполнитель вынужден добавить
новое имя, он делает это в `basic.style` через A0-коммит, а не в своём файле
(иначе пересборка 925-1664 объектов на каждую его правку).

Сгенерированные файлы лежат в `~/dev/mokagram-build/Telegram/gen/styles` и
`.../lib_ui/gen/styles`. Генерация одной командой на все style таргета
(`lib_ui_style.timestamp`, `td_ui_style.timestamp`), но `restat` отсекает
пересборку у файлов, чьё содержимое не изменилось.

Подмодуль: после правок lib_ui обновлённый `.gitmodules` и новый sha подмодуля
коммитятся в mokagram, сборочный скрипт `~/dev/build-mokagram.sh` делает
`git submodule update --init --recursive --depth 1`, значит форк надо запушить
до этого (иначе `--depth 1` не найдёт коммит).

Новый .style файл (если понадобится вне lib_ui, например
`SourceFiles/mokagram/moka_ui.style`) надо внести в `Telegram/cmake/td_ui.cmake`
(список стилей, строки 15-80, формат `ui/chat/chat.style`) и подключить `using`,
но токены из него будут недоступны lib_ui-стилям, поэтому токены остаются в basic.style.

## 5. Риски: радиус 28 у боксов и как обойти

1. `boxRadius` общий. Поставить 28 = все карточки станут 28 (settings_chat 12
   мест, QR, пикеры, галереи подарков, subsection tabs). Обход: `boxRadius` = 22,
   новый `mokaRadiusWindow` = 28 только в слоях (1.12). Проверка: grep
   `st::boxRadius` в 13 файлах слоёв после замены не находит старое.
2. Тени. `boxRoundShadow` (layers.style:71) собран из PNG-иконок
   `round_shadow_box_*` (угол 23x23, края 10x1/1x10) под радиус 8. С 28 тень на
   углах выглядит квадратной, а `cached_special_layer_shadow_corners.cpp:15-23`
   вычитает маску радиуса `boxRadius*2 + extend` (66px), то есть логика есть, но
   исходная тень остаётся 8-пиксельной. Обход: (a) сгенерировать
   `round_shadow_box28_*` (углы 51x51, шаблон тот же) и подключить новым
   `roundShadowRadius28px` в widgets.style рядом с :918; (b) или рисовать
   `Ui::BoxShadow` (как у PopupMenu, popup_menu.cpp:270 `_boxShadow.paint(p, _inner, _st.radius)`)
   в `layer_widget.cpp:272-331,560-574` вместо иконочной.
   Выбор (b) дешевле (нет ассетов), (a) ближе к upstream.
3. Обрезка содержимого. `BoxLayerWidget::paintEvent` (box_layer_widget.cpp:134-148)
   красит скруглённый прямоугольник, но ДЕТИ рисуются поверх и не обрезаются
   (QWidget без path-clip): всё, что красит прямоугольник в зоне углов 28x28
   (hover строк списка, ripple строки, полоса `boxDivider`, фон картинки-шапки,
   полоса прокрутки, верхняя/нижняя тень скролла `_topShadow/_bottomShadow`
   в box_content.cpp:433-441), вылезет квадратным углом на затемнённый
   фон. В upstream при радиусе 8 это почти незаметно. Обход:
   - не помещать контент в углы: `defaultBox.margin` 10 -> 16 сверху и снизу,
     `boxTopMargin` 8 -> 16, заголовок 56 (углы целиком в зоне заголовка), нижняя
     полоса кнопок 44+12+16 = 72 > 28 (углы закрыты кнопочной зоной);
   - боксы без кнопок и без заголовка (списки, галереи): добавить `addSkip(28)`
     сверху и снизу внутри бокса или поле `Box.shadowIgnore*Skip` (layers.style:30,31);
   - полноширинные картинки-шапки уже маскируются `Images::CornersMask(boxRadius)`
     (`ui/top_background_gradient.cpp:88`, `boxes/premium_preview_box.cpp:1486`,
     `boxes/star_gift_cover_box.cpp:1393`), эти места заменить на `mokaRadiusWindow`;
   - hover строк peer list: скругление и инсет (C-9);
   - накладка из четырёх углов цвета фона для боксов НЕ годится: фон под слоем
     это затемнённое содержимое окна, а не ровный цвет (для колонок C-4 годится).
4. Шапки. Заголовок бокса (24,13) и иконка-закрытие (rippleArea 40 в (4,4), круг
   радиуса 20 с центром (24,24), самая дальняя точка 25.7 от центра дуги 28, то
   есть остаётся внутри). Текст заголовка при x=24 y=13 ближе к дуге: расстояние
   до центра дуги sqrt(16^2+15^2) = 22 < 28, но при длинных и крупных шрифтах уже
   рискованно. Обход: `boxTitlePosition` (28, 18), высота заголовка 56.
5. Кеши и анимации. `BoxCorners`, `MenuCorners` (cached_round_corners.cpp:79,80),
   RoundRect-ы на радиус 28 увеличивают растровые кэши (угол 28x28 вместо 8x8, x
   DPR 3), для боксов это пара сотен КБ, но при пересборке палитры
   (`style::PaletteChanged`, cached_round_corners.cpp:109-112) пересоздаются все
   кэши; для ночной темы, которая переключается редко, это нормально. Анимация
   появления бокса (`PanelAnimation`, `setCornerMasks(CornersMask(radius))`,
   popup_menu.cpp:901-903, tabbed_panel.cpp:389-390) требует маски нужного
   радиуса, они берут радиус из стиля, значит работают.
6. Высота. Боксы ниже 2*28 = 56 px (редкие диалоги подтверждения без заголовка)
   получат пересечение дуг: дуга ограничивается Qt, но видно «бочку». Обход:
   минимальная высота бокса 96 (заголовок 56 + 8 + кнопки) уже выполняется, но
   `Ui::MakeInformBox` без заголовка проверить вручную.
7. Спец-слои (настройки и профиль как слой). `layer_widget.cpp:288` вычитает из
   региона зоны радиуса, `:382,385` проверки попадания. Все три места на
   `mokaRadiusWindow`; `info_layer_widget.cpp:310,364` и `info_wrap_widget.cpp:1022,1032`
   тоже (иначе у слоя профиля углы 22, у бокса 28).
8. Пузыри. 18 и не больше: однострочный пузырь ≈ 36px (8+8+~20), иначе верх и
   низ углов наезжают. Небольшие медиа-пузыри (стикер-подпись, дата-плашка) берут
   `roundRadiusLarge` (после замены 12) и `dateRadius`, их проверять на заполненном экране.
9. Побочное наследование. `roundRadiusLarge` 6 -> 12 меняет углы фото/видео
   в превью, документов, форвард-выбор (`ForwardCorners`), инлайн-результатов.
   Если выглядит слишком круто, оставить 8, это одно значение (basic.style:107).
10. Старая `ConnectionBox`, `intro`, `passport`, `export`, `payments` используют
    собственные кнопки/поля; они унаследуют пилюли `fullRadius` автоматически, но
    их фиксированные высоты (36, 42, 44, 49) надо проходить на экране.
11. Скриншотное сравнение. Перед слиянием каждого участка снимать эталоны
    заполненного экрана (скилл: проверка результата глазами владельца, не пустой
    экран). Сборку и запуск делает владелец, из этой спеки ничего не запускалось.

## 6. Порядок работы

1. A0: форк/патч lib_ui, блок токенов в basic.style, `mokaRadiusWindow` в 13
   файлах слоёв, замена `boxRadius` на 22, тень (C-7). Одна полная пересборка.
2. Параллельно A1-A8, только значения (раздел 4.1) + свои К-задачи (4.2).
3. На каждый участок: пересобрать (один `style_X.cpp` и линковка), открыть на
   заполненном экране, сверить с таблицей «станет».
4. В конце сквозная проверка единообразия: радиусы 28/22/16/8, кнопки 40/44/48
   и пилюли, строки 40/48/64/68, отступы 4/8/12/16/24.
