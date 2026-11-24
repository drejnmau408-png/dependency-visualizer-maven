import configparser
import sys
import os
import argparse
import urllib.request
import xml.etree.ElementTree as ET
from urllib.error import URLError, HTTPError

# Namespace для XML POM-файлов Maven
NS = {"m": "http://maven.apache.org/POM/4.0.0"}

# Какие параметры обязательны в config.ini и какого они типа
EXPECTED_TYPES = {
    "package_name": str,
    "repository_url": str,
    "test_mode": bool,
    "package_version": str,
    "output_image_file": str,
    "ascii_tree": bool,
    "filter_substring": str,
}



# ЭТАП 1: загрузка конфигурации

def load_config(path="config.ini"):
    """
    читает config.ini и проверяет что все нужные параметры есть
    """
    # существут ли файл 
    #если нет ищем рядом со скриптом
    if not os.path.exists(path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        alt = os.path.join(script_dir, "..", "config.ini")
        alt = os.path.normpath(alt)
        if os.path.exists(alt):
            path = alt
        else:
            print(f"Error: config file {path} not found.")
            sys.exit(1)

    config = configparser.ConfigParser()
    try:
        config.read(path, encoding="utf-8")
    except configparser.Error as e:
        print(f"Error: invalid INI file.\n{e}")
        sys.exit(1)

    if "settings" not in config:
        print("Error: missing [settings] section.")
        sys.exit(1)
#создаем словарь и перебираем все парамеиры
    result = {}
    for key, expected in EXPECTED_TYPES.items():
        if not config.has_option("settings", key):
            print(f"Error: missing parameter {key}.")
            sys.exit(1)
        val = config.get("settings", key).strip()
        if expected is bool:
            if val.lower() not in ("true", "false"):
                print(f"Error: {key} must be true/false.")
                sys.exit(1)
            result[key] = val.lower() == "true"
        else:
            if not val:
                print(f"Error: {key} cannot be empty.")
                sys.exit(1)
            result[key] = val
    return result


#  разбор локального файла test_repo.txt


def parse_test_repo(text):
    """
    парсит тестовый репозиторий формат Package  Version  Depends
    используется только при test_mode = true.
    """
    packages = {}
    #записываем пакеты
    blocks = text.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        pkg_name = None
        pkg_version = None
        depends_line = None
        for line in lines:
            if line.startswith("Package: "):
                pkg_name = line.replace("Package: ", "").strip()
            elif line.startswith("Version: "):
                pkg_version = line.replace("Version: ", "").strip()
            elif line.startswith("Depends: "):
                depends_line = line.replace("Depends: ", "").strip()
        if pkg_name:
            deps = []
            if depends_line:
                for dep in depends_line.split(","):
                    dep = dep.strip()
                    if dep:
                        deps.append(dep)
            packages[pkg_name] = {"version": pkg_version, "depends": deps}
    return packages



#  Maven: скачивание и разбор POM

def maven_coords_to_path(group_id, artifact_id, version):
    """
    превращает groupId:artifactId:version в путь к POM в репозитории
    org.springframework / spring-core / 5.3.21 / ...
    """
    group_path = group_id.replace(".", "/")
    return f"{group_path}/{artifact_id}/{version}/{artifact_id}-{version}.pom"


def fetch_pom(repo_base, group_id, artifact_id, version):
    """
    Скачивает POM-файл по HTTP с Maven-репозитория.
    Менеджер пакетов (mvn) НЕ используется — только urllib.
    """
    path = maven_coords_to_path(group_id, artifact_id, version)
    url = repo_base.rstrip("/") + "/" + path
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return resp.read().decode("utf-8")
    #обпаботка ошибок
    except HTTPError as e:
        print(f"  [warn] HTTP {e.code} for {group_id}:{artifact_id}:{version}")
        return None
    except URLError as e:
        print(f"  [warn] Network error for {group_id}:{artifact_id}:{version}: {e.reason}")
        return None
    except Exception as e:
        print(f"  [warn] Failed to fetch {group_id}:{artifact_id}:{version}: {e}")
        return None


def parse_pom_dependencies(pom_text):
    """
    разбирает XML POM и достаёт прямые зависимости.
    берм только compile/runtime 
    """
    deps = []
    try:
        root = ET.fromstring(pom_text)
    except ET.ParseError:
        return deps

    # Пробуем разные варианты поиска тегов (с namespace и без)
    dep_elements = root.findall(".//m:dependencies/m:dependency", NS)
    if not dep_elements:
        dep_elements = root.findall(
            ".//{http://maven.apache.org/POM/4.0.0}dependencies/"
            "{http://maven.apache.org/POM/4.0.0}dependency"
        )
    if not dep_elements:
        dep_elements = root.findall(".//dependencies/dependency")

    for dep in dep_elements:
        def get_text(tag):
            el = dep.find(f"m:{tag}", NS)
            if el is None:
                el = dep.find(f"{{http://maven.apache.org/POM/4.0.0}}{tag}")
            if el is None:
                el = dep.find(tag)
            return el.text.strip() if el is not None and el.text else None

        group_id = get_text("groupId")
        artifact_id = get_text("artifactId")
        version = get_text("version")
        scope = get_text("scope") or "compile"

        # test / provided / system в граф не берём
        if scope in ("test", "provided", "system"):
            continue
        if not group_id or not artifact_id:
            continue

        deps.append((group_id, artifact_id, version))
    return deps


def resolve_maven_graph(repo_url, root_group, root_artifact, root_version, filter_sub, max_depth=6):
    """
    строит граф скачивая реальные POM (DFS).
    это основная логика для test_mode = false.
    """
    packages = {}  # ключ: "groupId:artifactId"
    visited = set()

    def dfs(group_id, artifact_id, version, depth):
        key = f"{group_id}:{artifact_id}"
        if key in visited or depth > max_depth:
            return
        visited.add(key)

        pom = fetch_pom(repo_url, group_id, artifact_id, version)
        if pom is None:
            packages[key] = {"version": version, "depends": []}
            return

        raw_deps = parse_pom_dependencies(pom)
        dep_keys = []
        for g, a, v in raw_deps:
            dep_key = f"{g}:{a}"
            # фильтр по подстроке (если задан)
            if filter_sub and filter_sub in dep_key:
                continue
            dep_keys.append(dep_key)
            if v:
                dfs(g, a, v, depth + 1)
            else:
                # версия не указана в POM просто запоминаем узел
                if dep_key not in packages:
                    packages[dep_key] = {"version": "?", "depends": []}

        packages[key] = {"version": version, "depends": dep_keys}

    dfs(root_group, root_artifact, root_version, 0)
    return packages


def parse_package_name(name):
    """Разбирает package_name вида groupId:artifactId."""
    if ":" in name:
        parts = name.split(":")
        if len(parts) >= 2:
            return parts[0], parts[1]
    return None, name


def get_packages_data(config):
    """
    получение данных о пакетах.
    test_mode=true  читаем test_repo.txt
    test_mode=false  качаем POM с Maven-репозитория
    """
    if config["test_mode"]:
        path = config["repository_url"]
        if not os.path.exists(path):
            print(f"Error: test file {path} not found.")
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            return parse_test_repo(f.read())
    else:
        group_id, artifact_id = parse_package_name(config["package_name"])
        if not group_id:
            print("Error: in real mode package_name must be groupId:artifactId")
            sys.exit(1)
        version = config["package_version"]
        repo = config["repository_url"]
        print(f"Fetching Maven POMs from {repo} ...")
        return resolve_maven_graph(
            repo, group_id, artifact_id, version, config["filter_substring"]
        )



#построение транзитивного графа (DFS)


def build_graph(packages, target, filter_sub, visited=None, graph=None):
    """
    Рекурсивный DFS: строим словарь {пакет: [его зависимости]}.
    Учитываем filter_substring и избегаем повторного обхода (циклы).
    """
    if visited is None:
        visited = set()
    if graph is None:
        graph = {}
    if target in visited:
        return graph
    visited.add(target)
    if target not in packages:
        return graph
    deps = packages[target]["depends"]
    filtered = [d for d in deps if not (filter_sub and filter_sub in d)]
    graph[target] = filtered
    for d in filtered:
        build_graph(packages, d, filter_sub, visited, graph)
    return graph



# ЭТАП 4: обратные зависимости


def find_reverse(packages, target, filter_sub):
   
    # Строим обратный граф: dep -> [кто от него зависит]
    rev_graph = {}
    for pkg, data in packages.items():
        for dep in data["depends"]:
            if filter_sub and filter_sub in dep:
                continue
            rev_graph.setdefault(dep, []).append(pkg)

    result = set()
    visited = set()

    def dfs(node):
        if node in visited:
            return
        visited.add(node)
        for parent in rev_graph.get(node, []):
            result.add(parent)
            dfs(parent)

    dfs(target)
    return sorted(result)



# ЭТАП 5: визуализация (DOT + ASCII)


def generate_graphviz(graph, filename):
    
    lines = ["digraph dependencies {", "    rankdir=LR;"]
    for pkg, deps in graph.items():
        if not deps:
            lines.append(f'    "{pkg}";')
        for dep in deps:
            lines.append(f'    "{pkg}" -> "{dep}";')
    lines.append("}")
    dot_code = "\n".join(lines)

    out_path = filename if filename.endswith(".dot") else filename + ".dot"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(dot_code)
    print(f"(DOT сохранён в файл: {out_path})")
    return dot_code


def print_tree(packages, pkg, filter_sub, prefix="", is_last=True, visited=None):
    
    if visited is None:
        visited = set()
    if pkg in visited:
        print(f"{prefix}{'\\-- ' if is_last else '|-- '}{pkg} (cycle)")
        return
    visited.add(pkg)
    if pkg not in packages:
        print(f"{prefix}{'\\-- ' if is_last else '|-- '}{pkg} (not found)")
        return
    print(f"{prefix}{'\\-- ' if is_last else '|-- '}{pkg}" if prefix else pkg)
    deps = [
        d for d in packages[pkg]["depends"]
        if not (filter_sub and filter_sub in d)
    ]
    for i, d in enumerate(deps):
        is_l = (i == len(deps) - 1)
        new_p = prefix + ("    " if is_last else "|   ")
        print_tree(packages, d, filter_sub, new_p, is_l, visited)



# main — запуск по этапам
def main():
    parser = argparse.ArgumentParser(
        description="Maven dependency graph visualizer (этапы 1–5)"
    )
    parser.add_argument(
        "--stage", type=int,
        help="Запустить только один этап (1, 2, 3, 4 или 5)"
    )
    args = parser.parse_args()

    # ----- ЭТАП 1: конфигурация -----
    config = load_config()
    if args.stage == 1 or not args.stage:
 
        print("ЭТАП 1: Конфигурация (config.ini)")

        for k, v in config.items():
            print(f"  {k}: {v}")
        if args.stage == 1:
            return

    # Получаем словарь пакетов (тест или реальный Maven)
    packages = get_packages_data(config)

    # Целевой пакет
    if config["test_mode"]:
        target = config["package_name"]
    else:
        group_id, artifact_id = parse_package_name(config["package_name"])
        target = f"{group_id}:{artifact_id}"

    # ----- ЭТАП 2: прямые зависимости -----
    if args.stage == 2 or not args.stage:
        print()
   
        print("ЭТАП 2: Прямые зависимости пакета")

        if target not in packages:
            print(f"Error: package {target} not found.")
            sys.exit(1)
        print(f"Пакет: {target}")
        print(f"Прямые зависимости: {packages[target]['depends']}")
        if args.stage == 2:
            return

    # ----- ЭТАП 3: транзитивный граф (DFS) -----
    if args.stage == 3 or not args.stage:
        print()
     
        print("ЭТАП 3: Транзитивный граф зависимостей (DFS)")

        graph = build_graph(packages, target, config["filter_substring"])
        print(f"Корневой пакет: {target}")
        print("Рёбра графа (пакет -> его зависимости):")
        for k, v in graph.items():
            print(f"  {k} -> {v}")
        if args.stage == 3:
            return

    # ----- ЭТАП 4: обратные зависимости -----
    if args.stage == 4 or not args.stage:
        print()

        print("ЭТАП 4: Обратные зависимости")
   
        print(f"Ищем пакеты, которые зависят от: {target}")
        rev = find_reverse(packages, target, config["filter_substring"])
        if rev:
            print("Найдены обратные зависимости:")
            for r in rev:
                print(f"  - {r}")
        else:
            print("Обратных зависимостей не найдено среди загруженных пакетов.")
        if args.stage == 4:
            return

    # ----- ЭТАП 5: визуализация -----
    if args.stage == 5 or not args.stage:
        print()
 
        print("ЭТАП 5: Визуализация (Graphviz DOT + ASCII-дерево)")

        graph = build_graph(packages, target, config["filter_substring"])

        print("\n--- Graphviz DOT ---")
        dot = generate_graphviz(graph, config["output_image_file"])
        print(dot)

        if config["ascii_tree"]:
            print("\n--- ASCII-дерево зависимостей ---")
            print_tree(packages, target, config["filter_substring"])
        else:
            print("\n(ASCII-дерево отключено: ascii_tree = false)")
        if args.stage == 5:
            return


if __name__ == "__main__":
    main()
