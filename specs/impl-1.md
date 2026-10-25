# impl-1: реестр настроек и экран «Кастомизация»

## Сделано
- mokagram_settings.cpp: реестр по заголовку. Хранение tdata/moka_settings.json (только отличия от умолчаний, неизвестные ключи сохраняются, неверные значения при Register/Load заменяются умолчанием с записью в лог). Запись через QSaveFile (временный файл + rename), отложенная на 300 мс, принудительная при aboutToQuit. Bool/Int/Choice/String/Color (Color хранится строкой), Int и Choice проверяются по диапазону.
- Экспорт .mokaset (format, version, app, values), импорт с предпросмотром и копией moka_settings.json.bak, ключи отсутствующих плагинов ждут в файле.
- mokagram_settings_box.cpp/.h: окно «Кастомизация» в стиле окна «Плагины» (RoundedNoButtons, карточки 22, переключатель Material 3, шапка с поиском). Свёрнутые разделы по полю section, строки по виду значения (переключатель, ползунок MediaSlider, меню выбора, поле текста), значок сброса у изменённых, сброс раздела, нижняя карточка «Экспорт / Импорт / Сбросить всё» (подтверждения через ConfirmBox), dependsOn прячет строку, requiresRestart пишет «Нужен перезапуск» и показывает тост после изменения. Поиск по названию, описанию, разделу и ключу, при поиске разделы раскрыты.
- Расширен mokagram_settings.h (только добавления): ResetSection, IsChanged, ImportSummary, PreviewImport.

## Новые файлы (для cmake)
mokagram/settings/mokagram_settings.cpp, mokagram_settings.h, mokagram_settings_box.cpp, mokagram_settings_box.h

## Изменённые
- core/application.cpp: include и `Mokagram::Settings::Load()` перед `Plugins::Start`.
- settings/sections/settings_main.cpp: include и кнопка «Кастомизация» (иконка menuIconPalette) после «Плагины», вызывает ShowCustomizeBox(controller).

Синтаксис без ошибок: оба новых .cpp, settings_main.cpp, application.cpp.

## Не сделано
- Глобальный поиск настроек клиента (SearchRegistry) не подключён, нужен только внутренний поиск окна.
- Окно строится один раз при открытии: записи, добавленные плагинами позже, видны после переоткрытия.
- Color показывается обычным текстовым полем (окна выбора цвета нет).

## Проверить глазами
Настройки, «Кастомизация»: после Register() записей других модулей появятся разделы. Изменить значение, закрыть клиент, проверить tdata/moka_settings.json. Экспорт, правка, импорт, сброс.

## Интегратору
Добавить 4 файла в cmake; вызвать Register() своих модулей ПОСЛЕ Settings::Load() (оно в application.cpp, до Plugins::Start). Записи, зарегистрированные позже Load, подхватывают сохранённые значения сами.
