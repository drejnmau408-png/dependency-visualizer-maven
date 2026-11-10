import configparser #для чтения ini 
import sys #для завершения при ошибке 
import os #работа с файлами
import requests #получение данных

EXPECTED_TYPES = {
    "package_name": str, #название пакета 
    "repository_url": str, #url
    "test_mode": bool,#включение тестового режима
    "package_version": str, #версии пакета 
    "output_image_file": str, #имя файла графа 
    "ascii_tree": bool, #нужно ли выводить дерево
    "filter_substring": str, #подстрока для фильтрации
}

def load_config(path="config.ini"): #этап один загружает и проверяет настройки
    if not os.path.exists(path): # существует ли файл
        print(f"Error: config file {path} not found.")
        sys.exit(1) #если файла нет выводим ошибку 
    
    config = configparser.ConfigParser() #объект для чтения файла
    try:
        config.read(path, encoding="utf-8") #читаем настройки файла
    except configparser.Error as e:
        print(f"Error: invalid INI file.\n{e}")
        sys.exit(1) #если что то не так ошибка 
    
    if "settings" not in config: #есть ли сеттинг
        print("Error: INI file does not contain [settings] section.")
        sys.exit(1)
    
    result = {}
    for key, expected in EXPECTED_TYPES.items(): #перебираем параметры и их ожидаемые типы
        if not config.has_option("settings", key):
            print(f"Error: missing parameter {key}.")
            sys.exit(1)
        
        val = config.get("settings", key).strip() #получаем значения параметра и убираем пробелы
        
        if expected is bool:
            if val.lower() not in ("true", "false"): #должен ли параметр быть логическим
                print(f"Error: parameter {key} must be true or false.")
                sys.exit(1)
            result[key] = val.lower() == "true"
        else:
            if not val: #преобразуем в логичесуое значение
                print(f"Error: parameter {key} cannot be empty.")
                sys.exit(1)
            result[key] = val #сохраняем в словарь
    
    return result

def get_packages_data(config): #этап 2 получает данные из тестовой мавен
    url = config["repository_url"] #функция получения данных  ссылкой 
    if config["test_mode"]: #включен ли тестовый режим
        if not os.path.exists(url): #проверяем существование  файла
            print(f"Error: test file {url} not found.")
            sys.exit(1)
        with open(url, "r", encoding="utf-8") as f:
            return f.read()
    else:
        try:
            response = requests.get(url, timeout=10) #отправляем запрос к репозиторию если включен театовый режим
            response.raise_for_status() #нет лт ошибки
            return response.text #возвращаем текст 
        except Exception as e:
            print(f"Error downloading: {e}") #перехатыаем ошибку
            sys.exit(1)

def parse_packages(packages_text): #извлекает пакеты версии и зависимости
    packages = {} #словарь для хранения пакетов
    blocks = packages_text.strip().split("\n\n")
    for block in blocks: #разделяем текст на блоки и перебираем блок
        lines = block.strip().split("\n")
        pkg_name, pkg_version, depends_line = None, None, None
        for line in lines: #перебираем строки блока 
            if line.startswith("Package: "): pkg_name = line.replace("Package: ", "").strip() #ищем и извлекаем пакет  версию и зависимости
            elif line.startswith("Version: "): pkg_version = line.replace("Version: ", "").strip()
            elif line.startswith("Depends: "): depends_line = line.replace("Depends: ", "").strip()
        if pkg_name:
            deps = [] #создаем пустой список зависимостей
            if depends_line:
                for dep in depends_line.split(","): #разделяем зависимости запятыми 
                    dep = dep.strip() #убираем лишние пробелы 
                    if "(" in dep: dep = dep.split("(")[0].strip() #убираем информацию  об ограниченииверсии
                    if "|" in dep: dep = dep.split("|")[0].strip() # если указаны альтернативные оставляем первукю 
                    if dep: deps.append(dep)
            packages[pkg_name] = {"version": pkg_version, "depends": deps} #яохраняем в словарь
    return packages

def build_graph_recursive(packages, target, filter_substring, visited=None, graph=None): #этап 4 строит граф ищет обратные зависимости 
    if visited is None: #если множество не создано создаем
        visited = set()
    if graph is None: # если граф не создан создаем 
        graph = {}
    
    if target in visited: #проверка на посещение пакета 
        return graph
    
    visited.add(target) #добавляем в множество посещенных
    
    if target not in packages: #cуществукет ли пакет
        return graph
    
    deps = packages[target]["depends"] #получаем список прямых зависимостей 
    filtered = [d for d in deps if not (filter_substring and filter_substring in d)]
    
    graph[target] = filtered
    
    for d in filtered:
        build_graph_recursive(packages, d, filter_substring, visited, graph) #рекупрсивно вызываем функцию чтобы найти зависимости у пакета
    
    return graph

def find_reverse_deps(packages, target, filter_substring):
    rev_graph = {}
    for pkg, data in packages.items():
        for dep in data["depends"]:
            if filter_substring and filter_substring in dep: continue
            rev_graph.setdefault(dep, []).append(pkg)
    result, stack, visited = set(), [target], set() #стек для обхода и множества посещенных вещей
    while stack:
        node = stack.pop() #извлекаем последний добавленный элемент сте5ка
        if node in visited: continue # пропускаем если посещали 
        visited.add(node) #отмечаем пакет как посещенный 
        for parent in rev_graph.get(node, []): #получаем пакеты которые зависят
            result.add(parent); stack.append(parent) #добавляем найденный пакет 
    return sorted(result)

def generate_graphviz(graph, filename): 
    lines = ["digraph dependencies {", "    rankdir=LR;"] #список строк 
    for pkg, deps in graph.items(): #перебираем па5кеты и зависимости 
        if not deps: lines.append(f'    "{pkg}";') #если нет добавляем как отдельную вершмину
        for dep in deps: lines.append(f'    "{pkg}" -> "{dep}";')
    lines.append("}")#перебираем зависимости текущего пакета и соединяем
    dot_code = "\n".join(lines)
    with open(filename + ".dot", "w", encoding="utf-8") as f: #файл для записи
        f.write(dot_code)
    return dot_code

# ???????? ??????? ?? ASCII
def print_ascii_tree(packages, pkg, filter_substr, prefix="", is_last=True, visited=None):
    if visited is None: visited = set() #создаем множество пакетов
    if pkg in visited: #встречался ли пакет ранее
        print(f"{prefix}{'\\-- ' if is_last else '|-- '}{pkg} (cycle)")
        return
    visited.add(pkg) #добавляем в множество посещенных 
    if pkg not in packages:
        print(f"{prefix}{'\\-- ' if is_last else '|-- '}{pkg} (not found)")
        return
    print(f"{prefix}{'\\-- ' if is_last else '|-- '}{pkg}" if prefix else pkg)
    deps = [d for d in packages[pkg]["depends"] if not (filter_substr and filter_substr in d)] #зависимости с учетом фильтра
    for i, d in enumerate(deps): #зависимости с их порядковыми номерами
        is_l = (i == len(deps) - 1) #является ли текущая запись последней 
        new_p = prefix + ("    " if is_last else "|   ") #отступ
        print_ascii_tree(packages, d, filter_substr, new_p, is_l, visited) #рекурсивно вывдим запись

def main():
    config = load_config()
    print("Configuration loaded:")
    for k, v in config.items(): print(f"  {k}: {v}")
    
    print("\n--- Data collection ---")
    text = get_packages_data(config)
    packages = parse_packages(text)
    target = config["package_name"]
    
    if target not in packages:
        print(f"Error: package {target} not found.")
        sys.exit(1)
    
    print(f"Direct dependencies of {target}: {packages[target]['depends']}") #вывод прямых зависимостей
    
    print("\n--- Dependency graph (DFS with recursion) ---") #посроение этап 3
    graph = build_graph_recursive(packages, target, config["filter_substring"])
    for k, v in graph.items(): print(f"  {k} -> {v}")
    
    print("\n--- Reverse dependencies ---") #Этап 4 вывод обратные зависимости
    rev = find_reverse_deps(packages, target, config["filter_substring"])
    print(f"Packages depending on {target}: {rev if rev else 'none'}")
    
    print("\n--- Visualization ---") #этап 5 визуализация
    dot = generate_graphviz(graph, config["output_image_file"])
    print(f"Graphviz code (saved to {config['output_image_file']}.dot):")
    print(dot)
    
    if config["ascii_tree"]:
        print("\nASCII tree:")
        print_ascii_tree(packages, target, config["filter_substring"])

if __name__ == "__main__":
    main()
