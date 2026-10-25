# 09. Автоматический аудит интерфейса mokaGram

Только спецификация. Код, сборка и запущенный клиент не тронуты. Номера строк
сняты с 7.3.3 в ~/dev/mokagram на 22.10.2026, после правок могут съехать
(ищи по имени функции).

## 0. Что уже есть и что из этого брать

- В дереве есть upstream-харнесс Telegram/SourceFiles/test/ (запуск `-testagent`,
  README на 1300 строк). Он целиком под `#ifdef _DEBUG` (test_agent.cpp:10 и 366),
  в релизной сборке пустышки, поэтому напрямую использовать его нельзя. Но
  полезные идеи, которые копируем (не линкуем):
  - `FindAll<T>` через RTTI вместо `findChildren<Ui::RpWidget*>` (test_widgets.h:23).
    README прямо запрещает `findChildren<Ui::CustomWidget*>`: у tdesktop-виджетов
    нет Q_OBJECT, Qt вернёт мусор. Значит обходим только `QObject::children()` и
    приводим `qobject_cast<QWidget*>` (он работает, т.к. QWidget имеет Q_OBJECT),
    а имя класса берём через `typeid(*w).name()` + demangle (как
    `WidgetDescription`, test/test_capture.cpp:258).
  - `Ui::GrabWidgetToImage(widget, QRect(), st::windowBg->c)` для снимка окна
    изнутри процесса (test_capture.cpp:265).
- Конвейер хоста плагинов: `Application::run()` (core/application.cpp:318) уже
  вызывает `Mokagram::Plugins::Start` (:331). Рядом добавляем один вызов
  `Mokagram::Audit::Start()` (после `Test::ApplyStartupOverrides()` на :337 или
  сразу после Plugins::Start). Один вызов, ничего больше в ядре.
- В CMake модули mokagram перечислены явно: Telegram/CMakeLists.txt:73-99
  (блок "mokagram: хост плагинов"). Новые файлы добавлять туда же.

## 1. Режим отладки в клиенте (C++)

Включение: `MOKAGRAM_UI_AUDIT=1` в окружении (`qEnvironmentVariableIntValue`,
как уже сделано через getenv в mokagram/plugins/mokagram_plugins.cpp:340).
Комбинацию клавиш не делаем на первом шаге (нужен глобальный eventFilter, лишний
риск); потом можно `Ctrl+Alt+Shift+A` через `qApp->installEventFilter` внутри
того же модуля. Без переменной модуль не создаёт ничего (нулевая цена).

### Какое окно и слой снимать

- Главное окно: `Core::App().activeWindow()` (core/application.cpp:1676, объявлен
  core/application.h:177) возвращает `Window::Controller*`. Если null, взять
  `Core::App().primaryWindow()` / первый из `windowFor`. Дальше:
  - `controller->widget()` даёт `::MainWindow*` (window/window_controller.h:54),
    это корень QWidget-дерева.
  - `controller->sessionController()` (window_controller.h:59) нужен для навигации.
- Профиль и настройки в tdesktop это НЕ отдельные окна, а секция Info внутри
  главного окна (или в слое-колонке): `SessionNavigation::showPeerInfo`
  (window/window_session_controller.cpp:1358, объявлено .h:264-270) и
  `showSettings` (.cpp:1499/1509, .h:299-302) делают `showSection(make_shared<
  Info::Memento>)`. Поэтому корнем обхода берём `mainWindow` целиком, а в
  результате помечаем поддерево профиля: ищем виджет, чей `typeid` содержит
  `Info::Profile::InnerWidget` (info/profile/info_profile_inner_widget.cpp:205
  строит `SectionStack`), и пишем его путь как `root_hint`.
- Приватный `MainWindow::_layer` (mainwindow.h:145, `Ui::LayerStackWidget`)
  снаружи недоступен. Не нужно: слой, коробки и главное меню являются
  дочерними виджетами `bodyWidget()` (window/main_window.h:118), значит обход
  через `children()` от `MainWindow` их захватит. Слой с боковым меню:
  `MainWindow::showMainMenu()` (mainwindow.cpp:406).
- Отдельные top-level окна (контекстные меню `Ui::PopupMenu`, тултипы, окна
  отдельных чатов): `QApplication::topLevelWidgets()`. Каждое пишем как
  отдельный корень в JSON (`windows[]`).

### Что обходить и что писать

Обход рекурсивный по `QObject::children()`; для каждого `QWidget *w`:

| поле JSON | откуда |
|---|---|
| `id` | порядковый номер, `parent` как id |
| `class` | demangle(`typeid(*w).name()`), плюс `meta` = `w->metaObject()->className()` |
| `path` | цепочка `Класс[индекс среди одинаковых братьев]` до корня, это и есть "путь до виджета" в нарушениях |
| `visible` | `w->isVisible()` (в обход пропускаем невидимых, но пишем флаг `hidden_by_parent`) |
| `geom` | `w->geometry()` (в системе родителя) |
| `win_geom` | `QRect(w->mapTo(w->window(), QPoint()), w->size())` (в системе окна) |
| `size`, `min`, `max` | `size()`, `minimumSize()`, `maximumSize()` |
| `dpr` | `w->devicePixelRatioF()` |
| `text` | для `Ui::RoundButton::text()`, `Ui::FlatLabel` (`accessibilityName()` публичен), `Ui::FlatButton`, `Ui::SettingsButton`; единый способ: `w->accessibleName()` / `accessibilityName()` у RpWidget (см. test_menu.h) |
| `enabled`, `has_mask` | `isEnabled()`, `!w->mask().isEmpty()` |
| `tag` | свой слой: `Audit::Tag(widget, "card"/"pill"/"btn")`, `QObject::setProperty("mokagram_audit", ...)` |

Только `Ui::RpWidget` отдельно ничего не умеет, чем QWidget, кроме
`paintRequest`/`sizeValue`, поэтому отдельного прохода "по RpWidget" не нужно:
хватает QWidget, а тип узнаём через RTTI.

Метки (tag) расставляются в трёх местах, где мы сами рисуем:
1. `MakeCard` (info/profile/info_profile_section_stack.cpp:70) в начале:
   `Mokagram::Audit::Tag(card, "profile.card", {{"radius", kCardRadius}})`.
2. Обёртка `Ui::SlideWrap<>(..., QMargins(14, 5, 14, 5))` там же (:268):
   тег `profile.card.wrap` с ожидаемыми полями `margins=14,5,14,5`.
3. Плашка поиска `pill->paintOn(... drawRoundedRect(pill->rect(), 18, 18))`
   (mokagram/plugins/mokagram_plugin_install.cpp:1017-1022, геометрия на :1040,
   высота 36) тег `install.search.pill`, radius 18.
Тег ставит нулевой по цене вызов (`if (!Active()) return;`), поэтому в
релизе остаётся безопасным. Теги заменяют хрупкие эвристики по классам и
дают скрипту явные ожидания (ожидаемый радиус, число карточек в группе).

### Формат вывода

`$XDG_RUNTIME_DIR/mokagram-audit/<ts>-<label>.json` (`label` = profile/settings/menu):

```json
{"version":1,"label":"profile","scale":1.0,"dpr":1.0,
 "window":{"w":1000,"h":700,"screen":"DP-1"},
 "tags":{"profile.card":{"radius":22}},
 "widgets":[{"id":12,"parent":3,"class":"Ui::RpWidget","path":"MainWindow/...",
  "visible":true,"geom":[14,120,372,56],"win_geom":[414,220,372,56],
  "text":"","tag":"profile.card"}]}
```

Пишем `QJsonDocument` атомарно (файл `.tmp` и rename). Весь обход идёт в GUI-потоке
из `QTimer::singleShot(0)` после выполнения команды (см. п. 4), чтобы виджеты
успели выложиться (`QCoreApplication::sendPostedEvents` + один кадр,
по аналогии с ожиданием стадий Runner в test_runner).

## 2. Python-проверка геометрии: `tools/ui_audit/audit.py`

Только stdlib (numpy/PIL на системном python нет; есть в ~/.venvs/emoji, для
п. 3 используем его). Вход: JSON. Выход: список нарушений
`[ПРАВИЛО] путь: что не так (факт vs ожидание)` и код возврата 1 при нарушениях,
плюс `--json` для машинного разбора.

Правила (допуск `--tol 1` пиксель):

1. `margins_equal`: сгруппировать виджеты с одним тегом и одним родителем
   (карточки профиля, `profile.card`), взять `left = geom.x`,
   `right = parent.w - (x + w)`. Нарушение: у карточек группы разные left/right,
   либо left != right (профиль должен быть симметричен, ожидаем 14 из
   QMargins(14,5,14,5)).
2. `gap_equal`: сортировка карточек группы по y, промежутки
   `next.y - (prev.y + prev.h)` должны совпадать между собой (ожидание 10 =
   5+5 от SlideWrap).
3. `same_kind_same_size`: кнопки одного класса и одного ряда (общий родитель,
   `Ui::RoundButton`, `Ui::SettingsButton`) с одинаковой высотой; если ряд
   разделён поровну по ширине, и одинаковой шириной. Ряд = пересечение по
   вертикали >= 50%.
4. `center_h` / `center_v`: для плашки с одним ребёнком-текстом/значком
   (`tag` pill/btn): `|(child.cx - parent.cx)| <= tol`, то же по y. Для
   нескольких детей: центр объединённой рамки детей. Это ловит "текст не по
   центру" на уровне рамок. Предел: рамка метки это не нарисованный глиф, точное
   смещение текста видно только на п. 3.
5. `radius_expected`: `tag.radius` должен совпадать со справочной таблицей
   (`profile.card=22`, `install.search.pill=18`) и для низких карточек
   равен `min(22, h/2)` (так считает MakeCard, :84-117).
6. `overflow`: ребёнок выходит за рамки родителя без причины; `zero_size`;
   `overlap` между сиблингами одной группы.
7. `min_size_hit`: у видимых кнопок высота < 32 или ширина < 40 (тап-цель).

Таблица ожиданий лежит в `tools/ui_audit/rules.json` (радиусы, отступы), чтобы
правки дизайна не требовали менять код скрипта. Группы описаны селекторами
`class` + `tag` + `parent`, без жёсткой привязки к индексам.

## 3. Пиксельный уровень: `tools/ui_audit/pixels.py`

Нужен для того, чего нет в геометрии: нарисованные углы (MakeCard рисует углы
четырьмя дочерними RpWidget с вырезом эллипса, info_profile_section_stack.cpp:
89-104; MakePill делает то же в mokagram_plugin_install.cpp:1136-1182) и
центровка настоящего глифа.

Две ступени снимка:
- 3a, внутри клиента (предпочтительно, точно и без композитора):
  `Ui::GrabWidgetToImage(mainWindowBody, ...)` в PNG рядом с JSON, `*-shot.png`.
  Работает даже если окно перекрыто, не зависит от HiDPI-масштаба композитора.
- 3b, снаружи: `hyprctl clients -j` (поля `class`, `pid`, `at`, `size`,
  `workspace`, `monitor`), выбрать окно по `pid` клиента (pid пишем в JSON,
  `QCoreApplication::applicationPid()`), т.к. class у tdesktop зависит от
  desktop-файла. Затем `grim -g "X,Y WxH" out.png`. Масштаб монитора брать из
  `hyprctl monitors -j` (`scale`) и сравнивать с `dpr` из JSON. Окно должно быть
  на активном workspace и не перекрыто; скрипт сам проверяет `at/size` и
  отказывается, если окно вне экрана. Для боковых окон и меню 3b единственный
  вариант увидеть реальную композицию.

Анализ (numpy+PIL из `~/.venvs/emoji/bin/python`):
1. Для каждого виджета с тегом card/pill берём его `win_geom` * dpr.
2. Границы: сканируем горизонтальную линию через центр карточки и ищем
   переходы цвета фона страницы (`st::windowBg`) и цвета карточки
   (`st::dialogsBg`, цвета пишем в JSON из палитры `st::`). Получаем реальные
   left/right и сравниваем с геометрией и между карточками (ловит
   прозрачные/наложенные края, которых нет в geometry).
3. Скругления: по четырём углам считаем число пикселей фона вне кривой и
   сравниваем с эталоном круга радиуса r (`r=min(22,h/2)`). Допуск 1 px
   по радиусу. Ловит случай, когда `corner->raise()` перекрыт чужим дочерним
   виджетом или радиус не пересчитался после resize.
4. Центровка глифа: в рамке плашки найти bounding box пикселей, отличных от
   фона плашки; `|bbox.cx - rect.cx| <= 1`, `|bbox.cy - rect.cy| <= 1` (у
   текста по вертикали сравнивать с поправкой на высоту строчных, поэтому для
   текста мерить по x и по cap-height, для иконок по обоим осям).
5. Режим `--diff ref.png`: сравнение со снимком из ~/dev/mokagram-plugins/ui-refs.
Результат в том же формате нарушений, плюс `*-overlay.png` с красными
рамками проблемных мест (проверять глазами одним взглядом).

## 4. Автоматическое открытие экранов: команды

Транспорт (без новых зависимостей, только QtCore, чтобы не тянуть QtNetwork,
которого нет в явных зависимостях CMake, см. строки 137-138 и 2933):

- Основной: Unix-сокет `$XDG_RUNTIME_DIR/mokagram-audit.sock` на голых
  POSIX-вызовах (`socket(AF_UNIX, SOCK_STREAM)`, `bind`, `listen`) + `QSocketNotifier`.
  Одна строка = одна команда, ответ одна строка JSON `{"ok":true,"file":"..."}`.
  Права 0600. Слушает только когда `MOKAGRAM_UI_AUDIT=1`.
- Запасной: каталог `$XDG_RUNTIME_DIR/mokagram-audit/cmd/`, `QFileSystemWatcher`
  берёт новые файлы `*.cmd`, исполняет, пишет `*.res`. Нужен, если сокет
  по какой-то причине не поднялся.
- Все команды исполняются в GUI-потоке (`crl::on_main` / `QMetaObject::invokeMethod`
  с `Qt::QueuedConnection`), сокет-поток никакие виджеты не трогает.

Команды:

| команда | что вызываем |
|---|---|
| `open_profile self` | `controller->showPeerInfo(controller->session().user(), SectionShow())` (window_session_controller.h:267; свой профиль, чат не нужен) |
| `open_profile <peer_id>` | `showPeerInfo(PeerId(id))` (.h:264), peer должен быть в кэше `session().data().peerLoaded()` |
| `open_settings [type]` | `showSettings()` (.h:302) или `showSettings(Settings::Type)` (.h:299), типы `Settings::MainId()`, `PrivacySecurityId()` (см. использование в window_session_controller.cpp:1869) |
| `open_main_menu` | `window->widget()->showMainMenu()` (mainwindow.cpp:406) |
| `open_context_menu <path>` | найти виджет по `path` и послать `QContextMenuEvent` (`QCoreApplication::sendEvent`) |
| `click <path>` | `QTest`-подобно: `QMouseEvent` Press+Release в центр виджета (шаблон `Test::Click`, test_widgets.h:149) |
| `close_layers` | `controller->hideLayer()` / `clearSectionStack()` (.h:~280) |
| `audit [label]` | дождаться кадра, обойти дерево, записать JSON и PNG, ответить путём |
| `open_and_audit profile self` | комбинация: команда, затем ожидание готовности, затем `audit` |

Готовность перед `audit`: профиль подтягивается асинхронно, поэтому ждём
стабилизации (два подряд кадра с одинаковым числом виджетов и размером
InnerWidget, максимум 3 сек), по схеме `until`/`then` из test/README.md.
Нужна сессия: если `maybeSession()` пуст (экран входа), команда отвечает
`{"ok":false,"err":"no session"}`, а не падает.

Клиент: `tools/ui_audit/mg_audit` (Python, `socket`), пример:

```
MOKAGRAM_UI_AUDIT=1 ./mokagram &            # запускает владелец сам
mg_audit open_and_audit profile self        # одна команда
mg_audit --all                              # профиль, настройки, главное меню
```

Скрипт-обёртка `tools/ui_audit/run.sh` делает: команда, `audit.py`, `pixels.py`,
печатает сводку. Клиент не перезапускает и не гасит.

## 5. Файлы нового модуля

Telegram/SourceFiles/mokagram/audit/:

- `mokagram_audit.h/.cpp`: `Start()`, `Active()`, `Tag(widget, name, props)`,
  чтение env, регистрация в `Application::run()`.
- `mokagram_audit_dump.h/.cpp`: обход дерева, demangle, JSON, атомарная запись,
  выбор корней (`activeWindow` + topLevelWidgets).
- `mokagram_audit_grab.h/.cpp`: снимок `GrabWidgetToImage` в PNG.
- `mokagram_audit_commands.h/.cpp`: разбор команд, вызовы showPeerInfo /
  showSettings / showMainMenu, ожидание готовности, поиск виджета по path.
- `mokagram_audit_server.h/.cpp`: unix-сокет + QSocketNotifier, запасной
  вариант с каталогом команд.

Добавить 10 строк в Telegram/CMakeLists.txt рядом с :73-99, один вызов в
core/application.cpp рядом с :331, три тега (п. 1). Скрипты вне клиента:
`~/dev/mokagram-plugins/tools/ui_audit/{audit.py,pixels.py,mg_audit,run.sh,rules.json}`.

## 6. Порядок работ

1. Модуль-скелет: `Active()`, `Start()`, CMake, ничего не делает без env. Сборка
   проверяется владельцем (я не собираю).
2. `dump`: обход дерева и JSON, команда `audit` по файлу-команде (самый простой
   транспорт), проверка на профиле вручную открытом владельцем.
3. `audit.py` с правилами 1-4 и rules.json, прогон по реальному JSON профиля,
   калибровка допусков (ожидается, что первые прогоны выявят реальные
   расхождения, это и есть цель).
4. Теги в трёх местах (MakeCard, SlideWrap, pill), правило 5.
5. Команды `open_profile/open_settings/open_main_menu` и ожидание готовности,
   затем сокет.
6. Снимки 3a, затем `pixels.py` (границы, радиусы, центры), потом 3b через
   grim/hyprctl как независимая проверка.
7. `run.sh`, команда `--all`, прогон до и после каждой правки отступов (регресс).

## 7. Риски и заметки

- `MakePill` (mokagram_plugin_install.cpp:1136) в текущем коде нигде не вызывается
  (в файле встречается только определение). Либо мёртвый код (может давать
  предупреждение), либо вызов потерялся при правках. Аудит радиуса
  у `install.search.pill` идёт по реально рисуемому `drawRoundedRect(..., 18, 18)`
  (:1022), а не по MakePill. Стоит решить отдельно, не в этой задаче.
- Углы карточки MakeCard это дочерние виджеты поверх содержимого: в обходе они
  дадут шум (4 мелких RpWidget на карточку). Помечать их тегом `corner` и
  исключать из правил 3, 6.
- `SlideWrap` анимирует высоту: снимать только после `anim::type::instant`
  и готовности (иначе ложные нарушения gap).
- Поведение при HiDPI/масштабе: все сравнения в логических px, пиксельный
  анализ умножает на dpr; масштаб интерфейса писать в JSON.
- Сеть, систему, клиентские процессы аудит не трогает; hyprctl и grim только
  читают.
