# Инструмент визуализации графа зависимостей (Maven)

**Вариант №12**  
Дисциплина: Конфигурационное управление  
РТУ МИРЭА, 2026

## 1. Общее описание

CLI-инструмент для построения и визуализации графа зависимостей пакетов формата **Java (Maven)**.

Основные возможности:
- Загрузка параметров из конфигурационного файла формата **INI**
- Получение прямых зависимостей пакета указанной версии
- Построение транзитивного графа зависимостей алгоритмом **DFS с рекурсией**
- Корректная обработка циклических зависимостей
- Поиск **обратных зависимостей** (пакеты, которые зависят от заданного)
- Формирование текстового представления графа на языке **Graphviz (DOT)**
- Опциональный вывод зависимостей в виде **ASCII-дерева**
- Режим тестирования на локальном файле-репозитории
- Фильтрация зависимостей по подстроке

---

## 2. Описание всех функций и настроек

### 2.1. Параметры конфигурации (`config.ini`)

Файл должен содержать секцию `[settings]` со следующими параметрами:

| Параметр             | Тип    | Описание                                                                 | Пример                  |
|----------------------|--------|--------------------------------------------------------------------------|-------------------------|
| `package_name`       | строка | Имя анализируемого пакета                                                | `spring-core`           |
| `repository_url`     | строка | URL репозитория или путь к файлу тестового репозитория                   | `test_repo.txt`         |
| `test_mode`          | bool   | Режим работы с тестовым репозиторием (`true` / `false`)                  | `true`                  |
| `package_version`    | строка | Версия пакета                                                            | `5.3.20`                |
| `output_image_file`  | строка | Имя файла для сохранения DOT-описания                                    | `graph.svg`             |
| `ascii_tree`         | bool   | Выводить зависимости в формате ASCII-дерева (`true` / `false`)           | `true`                  |
| `filter_substring`   | строка | Подстрока, по которой исключаются зависимости из графа                   | `zzz`                   |

### 2.2. Основные функции программы

| Функция                  | Назначение                                              |
|--------------------------|---------------------------------------------------------|
| `load_config()`          | Чтение и валидация параметров из `config.ini`           |
| `get_packages_data()`    | Получение текста репозитория (локальный файл или HTTP)  |
| `parse_packages()`       | Разбор текста репозитория в словарь пакетов             |
| `build_graph()`          | Построение транзитивного графа зависимостей (DFS)       |
| `find_reverse()`         | Поиск обратных зависимостей                             |
| `generate_graphviz()`    | Генерация DOT-описания и сохранение в файл              |
| `print_tree()`           | Вывод ASCII-дерева зависимостей                         |

### 2.3. Этапы работы программы

Программа поддерживает пошаговый запуск через аргумент `--stage`:

| Этап | Что выполняется                                      |
|------|------------------------------------------------------|
| 1    | Чтение и вывод параметров конфигурации               |
| 2    | Получение и вывод прямых зависимостей                |
| 3    | Построение и вывод транзитивного графа               |
| 4    | Поиск и вывод обратных зависимостей                  |
| 5    | Генерация DOT-описания и ASCII-дерева                |

Без аргумента `--stage` выполняются все этапы подряд.

---

## 3. Команды запуска

```bash
./run.sh
# или
python3 src/main.py

# Запуск отдельного этапа:
python3 src/main.py --stage 1
python3 src/main.py --stage 2
python3 src/main.py --stage 3
python3 src/main.py --stage 4
python3 src/main.py --stage 5
```

---

## 4. Пример работы

### 4.1. Пример конфигурации

```ini
[settings]
package_name = spring-core
repository_url = test_repo.txt
test_mode = true
package_version = 5.3.20
output_image_file = graph.svg
ascii_tree = true
filter_substring = zzz
```

### 4.2. Формат тестового файла репозитория

```
Package: spring-core
Version: 5.3.20
Depends: spring-jcl, spring-beans

Package: spring-jcl
Version: 5.3.20
Depends: commons-logging

Package: commons-logging
Version: 1.2
Depends: 

Package: spring-beans
Version: 5.3.20
Depends: 
```

### 4.3. Пример вывода

```
--- STAGE 1: Configuration ---
  package_name: spring-core
  repository_url: test_repo.txt
  test_mode: True
  package_version: 5.3.20
  output_image_file: graph.svg
  ascii_tree: True
  filter_substring: zzz

--- STAGE 2: Data Collection ---
Direct dependencies: ['spring-jcl', 'spring-beans']

--- STAGE 3: Dependency Graph ---
  spring-core -> ['spring-jcl', 'spring-beans']
  spring-jcl -> ['commons-logging']
  commons-logging -> []
  spring-beans -> []

--- STAGE 4: Reverse Dependencies ---
Depends on spring-core: none

--- STAGE 5: Visualization ---
digraph dependencies {
    rankdir=LR;
    "spring-core" -> "spring-jcl";
    "spring-core" -> "spring-beans";
    "spring-jcl" -> "commons-logging";
    "commons-logging";
    "spring-beans";
}

ASCII tree:
spring-core
|-- spring-jcl
|   \-- commons-logging
\-- spring-beans
```

---

## 5. Структура репозитория

```
.
├── README.md
├── .gitignore
├── config.ini
├── run.sh
├── run.bat
├── test_repo.txt
├── src/
│   └── main.py
└── tests/
    └── test_main.py
```

---

## 6. Примечания по соответствию ТЗ

| Требование ТЗ                                      | Реализация                          |
|----------------------------------------------------|-------------------------------------|
| Конфигурация из INI                                | `load_config()` + `config.ini`      |
| Прямые зависимости                                 | `parse_packages()` + Stage 2        |
| Алгоритм DFS с рекурсией                           | `build_graph()`                     |
| Обработка циклических зависимостей                 | проверка `visited` в DFS и дереве   |
| Режим тестирования                                 | `test_mode = true` + локальный файл |
| Обратные зависимости                               | `find_reverse()`                    |
| Представление на языке Graphviz                    | `generate_graphviz()`               |
| ASCII-дерево                                       | `print_tree()` при `ascii_tree=true`|

---

## Автор

Студент группы ИКБО-51-25  
Лозан З.А.  
Практическая работа №2 по дисциплине «Конфигурационное управление»
