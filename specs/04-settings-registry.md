# 04. Единый реестр настроек и экран «Кастомизация»

Статус: только спецификация, код в ~/dev/mokagram не менялся. Основа: исходники 7.3.3 и ayu_settings.h/.cpp (AyuGram, ветка dev, лежат в /tmp/claude-1000/ayu-d).

## 1. Что нашли в нашем коде

Разделы настроек (Telegram/SourceFiles/settings):
- Раздел это класс `Section<T>` (settings_common.h) со статическим `Id()`. Тип `Settings::Type` это `shared_ptr<AbstractSectionFactory>` (settings_type.h).
- Содержимое раздела строит `Builder::SectionBuilder` (settings_builder.h): `addButton`, `addControl`, `scope`, `add`. Один и тот же код вызывается в двух режимах через `BuildContext = variant<WidgetContext, SearchContext>`: рисует виджеты или собирает записи для поиска. Поэтому поиск по настройкам в клиенте уже есть и берёт данные из того же описания.
- Регистрация: статический `const auto kMeta = BuildHelper({.id, .parentId, .title, .icon}, method)` в каждом sections/settings_*.cpp (пример settings_chat.cpp:1253). `BuildHelper` кладёт раздел в `SearchRegistry::Instance()` (id, родитель, заголовок, индексатор поиска).
- Кнопка перехода в раздел: `builder.addSectionButton({.targetSection = ChatId(), ...})` в settings_main.cpp (около строки 397). Это единственное место, где раздел виден в главном списке.
- Ограничения: заголовки это `tr::lng_*` (строки в lang.strings, компилируются), иконки это `st::menuIcon*`. Для строк реестра нужны `rpl::single(QString)` и иконки из уже существующих `st::`.

Хранение:
- `Core::Settings` (core/core_settings.h): сотни полей, много `rpl::variable<T>`, `serialize()/addFromSerialized()` в бинарный QDataStream. Пишется `Local::writeSettings()` в зашифрованный tdata/settings_s. Формат строго позиционный: новое поле требует правки сериализатора и версии, плагин туда ничего не добавит. Для наших настроек не подходит.
- Настройки аккаунта (Main::Session) в базе аккаунта, тоже бинарные.

AyuGram (ayu_settings.h/.cpp):
- Синглтон `AyuSettings`, около 100 полей `rpl::variable<T>` с геттерами `x()`, `xValue()`, `xChanges()` и сеттерами. В каждом сеттере: если значение то же, выходим; присвоить; `save()`.
- Хранение: tdata/ayu_settings.json через nlohmann::json, `to_json/from_json` руками на каждую структуру, `j.value("ключ", умолчание)`. `save()` пишет весь файл с `dump(4)` синхронно на каждое изменение. Есть `load()`, `reset()` целиком, миграции вручную (пример: ghostModeSettings в формат по аккаунтам).
- Минусы, которых избегаем: каждое поле это 4 метода и 3 места в json (рукописная связка, легко рассинхронить), нет описаний и типов в данных, нет автоэкрана (экран рисуется руками), нет реестра для плагинов, сохранение на каждый чих, сброс только всего сразу, нет экспорта.
- Что берём: json-файл рядом с tdata, `rpl::variable` как источник реактивности, `j.value(key, default)` как терпимость к отсутствующим ключам.

## 2. Дизайн реестра

Новые файлы (namespace `Moka::Settings`), папка Telegram/SourceFiles/mokagram/settings/:
- `moka_settings_registry.h/.cpp` реестр и хранение;
- `moka_settings_screen.h/.cpp` экран «Кастомизация»;
- `moka_settings_builtin.cpp` встроенные записи (одна функция `RegisterBuiltin()` со списком).

### 2.1 Запись

```cpp
enum class Kind { Bool, Int, Double, Choice, String, Color };

struct Entry {
    QString key;                 // "ghost.enabled", "plugin.<id>.<key>"; уникален
    QString section;             // id раздела: "ghost", "bubbles", "menus", "input", "fonts", "plugin.<id>"
    QString title;               // показываемое имя (для встроенных можно позже перевести через lang)
    QString description;         // одна строка под названием, участвует в поиске
    QStringList keywords;
    Kind kind;
    QJsonValue defaultValue;
    // ограничения по типу
    double min = 0, max = 0, step = 1;                 // Int, Double
    std::vector<std::pair<QString, QString>> choices;  // Choice: (значение, подпись)
    int maxLength = 0;                                 // String
    bool requiresRestart = false;
    QString dependsOn;           // ключ bool-записи, при false строка серая/скрыта
    QString owner;               // "core" или id плагина
};
```

### 2.2 Значения и подписки

```cpp
class Registry {
public:
    static Registry &Instance();
    void add(Entry entry);                      // повторный key = игнор + LOG
    void addAll(std::vector<Entry>, QString owner);
    void removeOwner(const QString &owner);     // при выгрузке плагина (значения остаются в файле)
    const Entry *find(const QString &key) const;
    std::vector<const Entry*> inSection(const QString &id) const;
    std::vector<SectionInfo> sections() const;  // порядок: core по списку, потом плагины по алфавиту

    QJsonValue get(const QString &key) const;   // значение или default
    bool       getBool(const QString &key) const;
    int        getInt(const QString &key) const;
    // ... getString, getColor (QColor из "#RRGGBB[AA]")
    void set(const QString &key, QJsonValue v); // валидация по Entry, no-op если то же, шлёт изменение, ставит отложенное сохранение
    void reset(const QString &key);
    void resetSection(const QString &id);
    void resetAll();

    rpl::producer<QJsonValue> value(const QString &key) const;    // текущее + изменения
    rpl::producer<QJsonValue> changes(const QString &key) const;
    rpl::producer<bool>    boolValue(const QString &key) const;   // обёртки с типом
    rpl::producer<int>     intValue(const QString &key) const;
    rpl::producer<QString> stringValue(const QString &key) const;
    rpl::producer<QColor>  colorValue(const QString &key) const;
    rpl::producer<Change>  anyChanges() const;                    // для экрана и экспорта
    rpl::producer<>        structureChanges() const;              // добавили/убрали записи (плагины)
};
```

Внутри: `base::flat_map<QString, Slot>`, где `Slot` держит `Entry` и `rpl::variable<QJsonValue>`. Ключи уникальны, значения хранятся как QJsonValue, поэтому один механизм для всех типов. Для горячих мест (отрисовка пузыря, список чатов) вызывающий код один раз берёт типизированный кэш: `static auto radius = Moka::Cached<int>("bubbles.radius");` (подписка внутри обновляет атомарное поле), чтобы не ходить в map на каждый кадр.

Тонкая обвязка для читаемости: `Moka::Opt::GhostMode()` возвращает `Registry::Instance().boolValue("ghost.enabled")`. Хуки в коде клиента вызывают только эти обёртки, ключи-строки не размазываются.

### 2.3 Хранение

- Один файл `tdata/moka_settings.json` (рядом лежит и сам ayu_settings.json у AyuGram, значит путь через `cWorkingDir() + u"tdata/"` проверен).
- Формат: `{"version": 1, "values": {"ghost.enabled": true, "bubbles.radius": 18, ...}}`. Пишутся только значения, отличные от умолчания: файл маленький, и смена умолчания в новой версии доходит до тех, кто ничего не трогал.
- Неизвестные ключи (плагин не загружен, запись удалена) сохраняются как есть и не теряются. Значение неверного типа или вне диапазона при загрузке заменяется умолчанием, в лог пишется предупреждение.
- Запись: сначала в `moka_settings.json.tmp`, затем `rename` (атомарно, без битого файла при падении). Сохранение отложенное: таймер 300 мс (`base::Timer`), несколько правок = одна запись; принудительная запись при выходе (подписка на `Core::App().quitting`/деструктор) и при экспорте.
- Миграции: поле `version` плюс таблица переименований ключей `{"старый": "новый"}` в одном месте.
- Плагины хранят значения в том же файле под ключами `plugin.<id>.<key>`; плагин получает через SDK только свой префикс (требует разрешение `settings`, см. SPEC.md п. 5).
- Для настроек, которые должны быть разными по аккаунтам (как GhostModeAccountSettings у AyuGram), v1 так не делаем: всё глобально. Если понадобится, ключ вида `acc.<id>.ghost.enabled` с флагом `perAccount` в Entry, без смены формата.

### 2.4 Экспорт и импорт

- Экспорт: файл `*.mokaset` (это тот же json: `{"format":"mokaset","version":1,"app":"7.3.3-moka","values":{...}, "plugins":[ids]}`). Экспортируются только изменённые значения. Выбор: «всё» или по разделам (чекбоксы разделов). Диалог через `FileDialog::GetWritePath`.
- Импорт: читаем, показываем окно-сводку («будет изменено 14 настроек, из них 3 плагина, неизвестных 2»), кнопка «Применить». Ключи плагинов, которых нет, записываются в файл и ждут. Неверные значения пропускаются со списком. Перед импортом автоматически копия `moka_settings.json.bak`.
- Системные поля (пути, токены, всё что `Entry.secret = true`) в экспорт не попадают. Рекомендуем завести этот флаг сразу.

## 3. Экран «Кастомизация» из реестра

Экран это обычный раздел `Settings::Customize : Section<Customize>` с `BuildHelper({.id, .parentId = MainId(), .title, .icon}, ...)`. Строить его не руками, а циклом по `Registry::sections()`.

- Верх: поле поиска (`Ui::InputField`), подписка на текст. Фильтр по `title`, `description`, `keywords`, названию раздела, без учёта регистра. При непустом запросе показываем плоский список совпадений с подписью раздела; при пустом разделы свёрнуты в карточки.
- Раздел (карточка) открывается подсекцией через `showOther`, как sections/*. Для динамических разделов (один на плагин) нужен один общий `Type` с параметром (id раздела хранится в состоянии), иначе придётся плодить классы. Это единственное место, где реестр упирается в статичность `Section<T>::Id()`. Решение: один класс `Customize` и один `CustomizeSection` с аргументом `sectionId`, открывается через `showOther(CustomizeSectionId())` после записи выбранного id в контроллер экрана.
- Виджеты по типу: Bool это `SettingsButton` с переключателем (`SectionBuilder::addButton` с `.toggled`), Int/Double это слайдер (`Ui::MediaSlider`) с подписью значения, Choice это кнопка со значением и меню/окно выбора, String это `Ui::InputField`, Color это кнопка с плашкой и окно выбора цвета (есть в клиенте для тем чата).
- `dependsOn`: строка подписана на `boolValue(dependsOn)` и прячется/гасится через `shown`.
- Сброс: у каждой изменённой записи значок «вернуть» (виден, только если значение != умолчание, подписка на `value(key)`); в шапке раздела пункт меню «Сбросить раздел» (через `fillTopBarMenu`, как в Chat); внизу экрана «Сбросить всё» с подтверждением (`Ui::MakeConfirmBox`). Плюс «Экспорт» и «Импорт» в том же меню.
- Бейдж «Требует перезапуска» для `requiresRestart`, после изменения показать плашку «Перезапустить».
- Плагины: подписка на `structureChanges()` перестраивает список разделов; раздел плагина показывается с его именем, иконка плагина или общая.
- Поиск клиента: чтобы настройки «Кастомизации» находились и в глобальном поиске настроек, зарегистрировать индексатор в `SearchRegistry` (`SearchEntriesIndexer` возвращает по `SearchEntry` на запись реестра: id = key, title, keywords, section = Customize, deeplink = key). Это бесплатно даёт переход и подсветку.

## 4. Плагины

- `create_settings()` в `mokagram/plugins/py/base_plugin.py` (строка 47) уже есть и возвращает список. Контракт SPEC.md п. 4 (Switch, Selector, Input, EditText, Header, Divider, Text, Custom) отображаем на реестр так:
  - Switch: Bool; Selector: Choice; Input: String или Int/Double (по `type`); EditText: String с `multiline`;
  - Header, Divider, Text: не значения, а оформительские элементы раздела. В реестр они не попадают, хранятся в `SectionInfo.layout` (упорядоченный список ключей и декоративных элементов).
  - Custom (плагин рисует виджет): на v1 не поддерживаем (Qt-виджеты из Python опасны); показываем кнопку, по клику вызывается callback.
- Хост (`mokagram_plugins.cpp`) после `on_plugin_load()` вызывает `create_settings()`, превращает результат в `Entry` с `owner = id плагина`, ключ `plugin.<id>.<key>`, и вызывает `Registry::addAll`. При выгрузке `removeOwner(id)`.
- Python-API: `self.get_setting("key", default)`, `self.set_setting(key, value)`, `self.on_setting_change(key, callback)` (внутри подписка rpl, живёт на `rpl::lifetime` плагина, снимается при выгрузке). Любой доступ идёт через GIL и в главном потоке Qt (иначе падения).
- Исполняет запись только ключи своего префикса, чужие и core только читает, если есть разрешение `settings`.
- Конфликты: повторный `key` игнорируется с записью в лог.

## 5. Встроенные записи, первый набор

Начальные разделы и ключи (всё по умолчанию соответствует стоковому клиенту, т.е. выключено/как было):
- Призрак: `ghost.enabled`, `ghost.send_read`, `ghost.send_online`, `ghost.send_typing`, `ghost.read_after_send` (по образцу полей GhostModeAccountSettings).
- Фильтры: `hide.blocked` (Bool), и т.п.
- Пузыри: `bubbles.radius` (Int 0..30, умолчание = текущий радиус стиля), `bubbles.tail` (Bool).
- Меню: `menu.msg.<действие>` (Bool, показывать ли пункт), `menu.main.<пункт>`.
- Поле ввода: `input.btn.<имя>` (Bool).
- Шрифты: `font.family` (String/Choice), `font.scale` (Double).
Использование: в точках клиента заменить жёсткое условие на `Moka::Opt::...()` или подписку. Это и есть основная работа, сам реестр маленький.

## 6. Как добавить файлы и обойтись без полной пересборки

CMake:
- Файлы клиента перечислены явными списками в Telegram/CMakeLists.txt (`nice_target_sources(Telegram ${src_loc} PRIVATE ...)`). Автосбора по маске нет, новые .cpp/.h надо вписать руками. Наш блок уже есть, строки 73-85 («mokagram: хост плагинов»): сюда добавить
  ```
  mokagram/settings/moka_settings_registry.cpp
  mokagram/settings/moka_settings_registry.h
  mokagram/settings/moka_settings_screen.cpp
  mokagram/settings/moka_settings_screen.h
  mokagram/settings/moka_settings_builtin.cpp
  ```
  в тот же `nice_target_sources` (хедеры нужны для AUTOMOC, если в них Q_OBJECT; у нас rpl, Q_OBJECT почти не нужен).
- Python.h подключён к одному файлу через `set_source_files_properties`, реестр его не использует. Python-часть (`create_settings`) остаётся в mokagram_plugins.cpp, туда достаточно `#include "mokagram/settings/moka_settings_registry.h"`.
- nlohmann::json тянуть не надо, хватает `QJsonDocument` (Qt уже есть, зависимость не растёт). AyuGram ставит json.hpp, нам незачем.
- Регистрацию раздела (`BuildHelper`) надо подключить в окно: добавить кнопку `addSectionButton` в settings_main.cpp (один изменённый существующий .cpp) и вызвать `Moka::RegisterBuiltin()` из `Core::Application::run()` (или из хоста плагинов, он уже стартует там) до открытия настроек.

Пересборка:
- Полная пересборка не нужна. Чтобы добавить файлы, нужен ровно один шаг `cmake` в ~/dev/mokagram-build (перегенерировать build.ninja, флаги компиляции не меняются, значит остальные объекты остаются свежими). Опасность: ninja после повреждённого журнала считает всё устаревшим, поэтому `cmake`/`ninja` без явных целей запускать нельзя (это и есть «пересобрать всё»).
- Скрипт ~/dev/moka-build.sh берёт список объектов для линкера из `build.ninja` (`build bin/Telegram:`), компилирует только перечисленные ему файлы и «недостающие» `.o`, затем линкует вручную. Значит: (1) добавить файлы в CMakeLists, (2) один раз выполнить `cmake .` в ~/dev/mokagram-build (только перегенерация; убедиться, что команда не запускает компиляцию), (3) вызвать `moka-build.sh mokagram/settings/moka_settings_registry.cpp mokagram/settings/moka_settings_screen.cpp mokagram/settings/moka_settings_builtin.cpp settings/sections/settings_main.cpp mokagram/plugins/mokagram_plugins.cpp ...` плюс каждый .cpp, который правим для хуков. Новые .o попадут в список линкера уже из свежего build.ninja, а шаг «докомпиляция недостающих» подстрахует.
- Если `cmake .` не хочется запускать (риск инвалидации), запасной путь: компилировать новые .cpp командой из build.ninja вручную и добавить их .o в `CMakeFiles/Telegram.rsp`, но скрипт перезаписывает rsp из build.ninja, поэтому придётся править и скрипт (добавить переменную EXTRA_OBJS). Это хуже, рекомендуем первый путь.
- Что не тянет за собой лавину: правки в .cpp (точки хуков) это один файл на правку. Что тянет: правка заголовков, которые включают многие (core/core_settings.h, settings_common.h). Для реестра их менять не нужно: `Moka::Opt` лежит в своём заголовке, который включаем только в файлах-потребителях. Следить, чтобы `moka_settings_registry.h` был лёгким (forward declarations, без включения Qt Widgets и rpl-тяжёлого кода лишний раз).
- AUTOMOC: если в новых заголовках нет Q_OBJECT, moc не требуется. Если появится, добавится `mocs_compilation.cpp`, который собирается заново целиком (дорого). Поэтому в новом коде Q_OBJECT не использовать (rpl + лямбды хватает).
- Проверка перед тем как говорить «готово»: запустить Telegram.new, открыть Настройки, Кастомизация, найти настройку поиском, изменить, перезапустить и убедиться, что значение вернулось из moka_settings.json; сброс, экспорт и импорт на второй копии файла.

## 7. Порядок работ

1. `Registry` без UI: Entry, get/set/reset, rpl, хранение json, отложенное сохранение (проверка: один json, правка вручную подхватывается при старте).
2. 5-6 встроенных записей и их подключение в клиенте (ghost, hide.blocked, bubbles.radius).
3. Экран `Customize`: разделы, поиск, виджеты по типам, сброс.
4. Экспорт и импорт со сводкой.
5. `create_settings()` плагинов и Python-API.
6. Индексатор для глобального поиска настроек.

## 8. Открытые вопросы

- Нужен ли `perAccount` в v1 (AyuGram делает призрак по аккаунтам)? Предлагаем нет.
- Строки на русском зашиты в реестре или идут через lang.strings? Предлагаем зашить на русском/английском двумя полями и не трогать lang.strings (его правка пересоберёт много файлов).
- Секреты в экспорте: решено исключать флагом `secret`.
