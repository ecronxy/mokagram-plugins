# impl-05: аккаунты, стикер из фото, владелец пака, ребрендинг

Проверка синтаксиса (moka-syntax.sh) без ошибок для: mokagram/misc/mokagram_misc.cpp, main/main_domain.cpp, storage/storage_domain.cpp, history/view/history_view_context_menu.cpp, boxes/sticker_set_box.cpp, boxes/about_box.cpp, lang/lang_instance.cpp.
(mokagram_misc.cpp проверен с временным lang_subsets-заголовком, который я удалил; настоящий создаст cmake.)

## Сделано
1. Лимит аккаунтов: `Domain::maxAccounts()` = clamp(Settings::Int("misc.max_accounts"), 3, 50), Premium не влияет. В main_domain.h добавлена `kHardMaxAccounts = 50` (kMaxAccounts=3 и kPremiumMaxAccounts=6 оставлены для текстов Premium). В конструкторе Domain подписка на `IntValue("misc.max_accounts")` обновляет `_lastMaxAccounts` (перестройка списка в настройках). `Expects` в `Domain::add` и проверки чтения tdata в storage_domain.cpp (count и index) переведены на kHardMaxAccounts. Настройка регистрируется в `Mokagram::Misc::RegisterSettings()` (раздел «Аккаунты», Int, 10, 3..50).
2. «Сделать стикер или эмодзи» в `AddPhotoActions` (только если нет запрета копирования медиа): пункт с подменю, внутри «Стикер: <пак>» и «Эмодзи: <пак>» для своих паков (AmCreator). Нет своих паков: пункт показывает тост «создай пак у @Stickers». Фон не вырезается, берётся Large-версия фото.
3. «Владелец пака»: `OwnerIdFromStickerSetId(uint64)` в mokagram_misc.h (формула из спеки), пункт в меню набора (после «Копировать ссылку», только если набор не твой). Профиль в кэше: открывается; нет: окно с ID, кнопка «Копировать ID» и пояснение про tg://user?id=. Показано как «вероятный владелец» (эвристика).
4. Ребрендинг: заголовок «О программе» = «mokaGram»; в Resources/langs/lang.strings все «Telegram Desktop» в значениях строк заменены на «mokaGram» (осталось только в шапке-лицензии); серверные и кэшированные строки: `BrandRewrite` вызывается в одной точке, `Instance::applyValue` (lang_instance.cpp), через неё идут разница с сервера, кэш и файл языка. Замена идемпотентна, трогает только «Telegram Desktop».

## Новые файлы (для cmake)
- Telegram/SourceFiles/mokagram/misc/mokagram_misc.h
- Telegram/SourceFiles/mokagram/misc/mokagram_misc.cpp

## Изменённые существующие
- main/main_domain.h: kHardMaxAccounts.
- main/main_domain.cpp: include настроек, подписка в ctor, maxAccounts() по настройке, Expects.
- storage/storage_domain.cpp: два места kPremiumMaxAccounts -> kHardMaxAccounts.
- history/view/history_view_context_menu.cpp: include + вызов `Mokagram::Misc::AddPhotoToSetActions` в конце AddPhotoActions. Вставку Plugins не трогал.
- boxes/sticker_set_box.cpp: include + пункт «Владелец пака».
- boxes/about_box.cpp: заголовок.
- lang/lang_instance.cpp: include + BrandRewrite в applyValue.
- Resources/langs/lang.strings: 17 строк.

## Что нужно от интегратора (ВАЖНО)
1. cmake: добавить два новых файла.
2. Вызвать `Mokagram::Misc::RegisterSettings();` при старте рядом с остальными Register (до Settings::Load).
3. ОБЯЗАТЕЛЬНО (иначе ошибка линковки): mokagram_misc.cpp объявляет `Api::OpenCreateFromImageFlow`, его надо дописать в boxes/sticker_creator_box.cpp (вне моего списка). Тело, после OpenCreateEmojiFlow:
```
void OpenCreateFromImageFlow(
		std::shared_ptr<ChatHelpers::Show> show,
		StickerSetIdentifier set,
		QImage image,
		Data::StickersType type,
		Fn<void(MTPmessages_StickerSet)> done) {
	RunImageEditorAndCreate(
		std::move(show),
		std::move(set),
		std::move(image),
		type,
		std::move(done));
}
```
и то же объявление в sticker_creator_box.h (в namespace Api, нужен `#include <QImage>`).
4. Кнопка «Добавить аккаунт» скрывается при `count >= kPremiumMaxAccounts` (settings/sections/settings_information.cpp:1200, чужой файл): заменить на `kHardMaxAccounts`, иначе выше 6 аккаунтов добавить из настроек нельзя. Также там `premiumLimit = maxAccounts()` теперь = лимиту настройки, замков не будет (нормально).
5. core/application.cpp:418 сравнивает с kMaxAccounts=3, но окно лимита показывается только если индекс аккаунта >= maxAccounts(), т.е. не при лимите >= числа аккаунтов. Правка не обязательна.
6. Горячие клавиши ShowAccount1..6 остались на шести, остальные аккаунты только мышью.

## Не сделано
- Вырезание фона (по условию первого этапа), видео и гифки в меню (только фото).
- Ребрендинг AppName/AppFile/org.telegram.desktop/tdata/.desktop/иконки не трогал. Риски: смена `AppName` и пути данных = потеря сессий и поломка апдейтера/DBus; безопасно только вместе с миграцией. Текст about (lng_about_text1..3, «Official...») не менял, нужен честный текст и «основано на Telegram Desktop» (GPL).
- Названия вида «Telegram Desktop» в серверных переводах со склонением («Telegram Desktop-а») не обработаны.
- Дочерний риск: tdata с >6 аккаунтами официальный клиент не прочтёт.

## Как проверить глазами
- Настройки mokaGram, раздел «Аккаунты»: ползунок, добавить 4-й аккаунт без окна Premium (после правки п.4).
- ПКМ по фото в чате: «Сделать стикер или эмодзи» -> выбрать свой пак -> открывается редактор.
- Открыть чужой пак стикеров, меню «...»: «Владелец пака».
- Меню «О программе»: заголовок mokaGram; экран приветствия/passcode: строки с mokaGram.
