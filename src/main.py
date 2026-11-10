import configparser
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

def load_config(path="config.ini"): #этап один загружает и проверяет настройки
    if not os.path.exists(path):
        print(f"Error: config file {path} not found.")
        sys.exit(1)
    
    config = configparser.ConfigParser()
    try:
        config.read(path, encoding="utf-8")
    except configparser.Error as e:
        print(f"Error: invalid INI file.\n{e}")
        sys.exit(1)
    
    if "settings" not in config:
        print("Error: INI file does not contain [settings] section.")
        sys.exit(1)
    
    result = {}
    for key, expected in EXPECTED_TYPES.items():
        if not config.has_option("settings", key):
            print(f"Error: missing parameter {key}.")
            sys.exit(1)
        
        val = config.get("settings", key).strip()
        
        if expected is bool:
            if val.lower() not in ("true", "false"):
                print(f"Error: parameter {key} must be true or false.")
                sys.exit(1)
            result[key] = val.lower() == "true"
        else:
            if not val:
                print(f"Error: parameter {key} cannot be empty.")
                sys.exit(1)
            result[key] = val
    
    return result

def get_packages_data(config): #этап 2 получает данные из тестовой мавен
    url = config["repository_url"]
    if config["test_mode"]:
        if not os.path.exists(url):
            print(f"Error: test file {url} not found.")
            sys.exit(1)
        with open(url, "r", encoding="utf-8") as f:
            return f.read()
    else:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"Error downloading: {e}")
            sys.exit(1)

def parse_packages(packages_text): #извлекает пакеты версии и зависимости
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

def build_graph_recursive(packages, target, filter_substring, visited=None, graph=None): #этап 4 строит граф ищет обратные зависимости
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
    filtered = [d for d in deps if not (filter_substring and filter_substring in d)]
    
    graph[target] = filtered
    
    for d in filtered:
        build_graph_recursive(packages, d, filter_substring, visited, graph)
    
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

# ???????? ??????? ?? ASCII
def print_ascii_tree(packages, pkg, filter_substr, prefix="", is_last=True, visited=None):
    if visited is None: visited = set()
    if pkg in visited:
        print(f"{prefix}{'\\-- ' if is_last else '|-- '}{pkg} (cycle)")
        return
    visited.add(pkg)
    if pkg not in packages:
        print(f"{prefix}{'\\-- ' if is_last else '|-- '}{pkg} (not found)")
        return
    print(f"{prefix}{'\\-- ' if is_last else '|-- '}{pkg}" if prefix else pkg)
    deps = [d for d in packages[pkg]["depends"] if not (filter_substr and filter_substr in d)]
    for i, d in enumerate(deps):
        is_l = (i == len(deps) - 1)
        new_p = prefix + ("    " if is_last else "|   ")
        print_ascii_tree(packages, d, filter_substr, new_p, is_l, visited)

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
    
    print(f"Direct dependencies of {target}: {packages[target]['depends']}")
    
    print("\n--- Dependency graph (DFS with recursion) ---")
    graph = build_graph_recursive(packages, target, config["filter_substring"])
    for k, v in graph.items(): print(f"  {k} -> {v}")
    
    print("\n--- Reverse dependencies ---")
    rev = find_reverse_deps(packages, target, config["filter_substring"])
    print(f"Packages depending on {target}: {rev if rev else 'none'}")
    
    print("\n--- Visualization ---")
    dot = generate_graphviz(graph, config["output_image_file"])
    print(f"Graphviz code (saved to {config['output_image_file']}.dot):")
    print(dot)
    
    if config["ascii_tree"]:
        print("\nASCII tree:")
        print_ascii_tree(packages, target, config["filter_substring"])

if __name__ == "__main__":
    main()
