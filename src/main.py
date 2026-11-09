import xml.etree.ElementTree as ET
import sys
import os
import requests

EXPECTED_TYPES = {
    "package_name": str,
    "repository_url": str,
    "test_mode": bool,
    "package_version": str,
    "output_image_file": str,
    "ascii_tree": bool,
    "filter_substring": str,
}

def load_config(path="config.xml"):
    if not os.path.exists(path):
        print(f"Ошибка: файл конфигурации {path} не найден.")
        sys.exit(1)
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"Ошибка: некорректный XML-файл.\n{e}")
        sys.exit(1)
    config = {}
    for key in EXPECTED_TYPES:
        elem = root.find(key)
        if elem is None:
            print(f"Ошибка: отсутствует параметр {key}.")
            sys.exit(1)
        val = elem.text.strip() if elem.text else ""
        expected = EXPECTED_TYPES[key]
        if expected is bool:
            if val.lower() not in ("true", "false"):
                print(f"Ошибка: параметр {key} должен быть true или false.")
                sys.exit(1)
            config[key] = val.lower() == "true"
        else:
            if not val:
                print(f"Ошибка: параметр {key} не может быть пустым.")
                sys.exit(1)
            config[key] = val
    return config

def get_packages_data(config):
    url = config["repository_url"]
    if config["test_mode"]:
        if not os.path.exists(url):
            print(f"Ошибка: тестовый файл {url} не найден.")
            sys.exit(1)
        with open(url, "r", encoding="utf-8") as f:
            return f.read()
    else:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"Ошибка при скачивании: {e}")
            sys.exit(1)

def parse_packages(packages_text):
    packages = {}
    blocks = packages_text.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        pkg_name, pkg_version, depends_line = None, None, None
        for line in lines:
            if line.startswith("Package: "): pkg_name = line.replace("Package: ", "").strip()
            elif line.startswith("Version: "): pkg_version = line.replace("Version: ", "").strip()
            elif line.startswith("Depends: "): depends_line = line.replace("Depends: ", "").strip()
        if pkg_name:
            deps = []
            if depends_line:
                for dep in depends_line.split(","):
                    dep = dep.strip()
                    if "(" in dep: dep = dep.split("(")[0].strip()
                    if "|" in dep: dep = dep.split("|")[0].strip()
                    if dep: deps.append(dep)
            packages[pkg_name] = {"version": pkg_version, "depends": deps}
    return packages

def build_graph_iterative(packages, target, filter_substring):
    graph = {}
    stack = [target]
    visited = set()
    while stack:
        current = stack.pop()
        if current in visited: continue
        visited.add(current)
        if current not in packages: continue
        deps = packages[current]["depends"]
        filtered = [d for d in deps if not (filter_substring and filter_substring in d)]
        graph[current] = filtered
        for d in filtered:
            if d not in visited: stack.append(d)
    return graph

def find_reverse_deps(packages, target, filter_substring):
    rev_graph = {}
    for pkg, data in packages.items():
        for dep in data["depends"]:
            if filter_substring and filter_substring in dep: continue
            rev_graph.setdefault(dep, []).append(pkg)
    result, stack, visited = set(), [target], set()
    while stack:
        node = stack.pop()
        if node in visited: continue
        visited.add(node)
        for parent in rev_graph.get(node, []):
            result.add(parent); stack.append(parent)
    return sorted(result)

def generate_graphviz(graph, filename):
    lines = ["digraph dependencies {", "    rankdir=LR;"]
    for pkg, deps in graph.items():
        if not deps: lines.append(f'    "{pkg}";')
        for dep in deps: lines.append(f'    "{pkg}" -> "{dep}";')
    lines.append("}")
    dot_code = "\n".join(lines)
    with open(filename + ".dot", "w", encoding="utf-8") as f:
        f.write(dot_code)
    return dot_code

def print_ascii_tree(packages, pkg, filter_substr, prefix="", is_last=True, visited=None):
    if visited is None: visited = set()
    if pkg in visited:
        print(f"{prefix}{'└── ' if is_last else '├── '}{pkg} (цикл)")
        return
    visited.add(pkg)
    if pkg not in packages:
        print(f"{prefix}{'└── ' if is_last else '├── '}{pkg} (нет)")
        return
    print(f"{prefix}{'└── ' if is_last else '├── '}{pkg}" if prefix else pkg)
    deps = [d for d in packages[pkg]["depends"] if not (filter_substr and filter_substr in d)]
    for i, d in enumerate(deps):
        is_l = (i == len(deps) - 1)
        new_p = prefix + ("    " if is_last else "│   ")
        print_ascii_tree(packages, d, filter_substr, new_p, is_l, visited)

def main():
    config = load_config()
    print("Параметры конфигурации:")
    for k, v in config.items(): print(f"  {k}: {v}")
    print("\n--- Этап 2: Сбор данных ---")
    text = get_packages_data(config)
    packages = parse_packages(text)
    target = config["package_name"]
    if target not in packages:
        print(f"Ошибка: пакет {target} не найден."); sys.exit(1)
    print(f"Прямые зависимости {target}: {packages[target]['depends']}")
    
    print("\n--- Этап 3: Граф (DFS без рекурсии) ---")
    graph = build_graph_iterative(packages, target, config["filter_substring"])
    for k, v in graph.items(): print(f"  {k} -> {v}")
    
    print("\n--- Этап 4: Обратные зависимости ---")
    rev = find_reverse_deps(packages, target, config["filter_substring"])
    print(f"Зависят от {target}: {rev if rev else 'нет'}")
    
    print("\n--- Этап 5: Визуализация ---")
    dot = generate_graphviz(graph, config["output_image_file"])
    print(f"Сгенерирован Graphviz-код:")
    print(dot)
    
    if config["ascii_tree"]:
        print("\nASCII-дерево:")
        print_ascii_tree(packages, target, config["filter_substring"])

if __name__ == "__main__":
    main()