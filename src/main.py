import configparser
import sys
import os
import requests
import argparse

EXPECTED_TYPES = {
    "package_name": str,
    "repository_url": str,
    "test_mode": bool,
    "package_version": str,
    "output_image_file": str,
    "ascii_tree": bool,
    "filter_substring": str,
}

def load_config(path="config.ini"):
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
        print("Error: missing [settings] section.")
        sys.exit(1)
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

def get_packages_data(config):
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

def parse_packages(packages_text):
    packages = {}
    blocks = packages_text.strip().split("\n\n")
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
                    if "(" in dep:
                        dep = dep.split("(")[0].strip()
                    if "|" in dep:
                        dep = dep.split("|")[0].strip()
                    if dep:
                        deps.append(dep)
            packages[pkg_name] = {"version": pkg_version, "depends": deps}
    return packages

def build_graph(packages, target, filter_sub, visited=None, graph=None):
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

def find_reverse(packages, target, filter_sub):
    rev_graph = {}
    for pkg, data in packages.items():
        for dep in data["depends"]:
            if filter_sub and filter_sub in dep:
                continue
            rev_graph.setdefault(dep, []).append(pkg)
    result, visited = set(), set()

    def dfs(node):
        if node in visited:
            return
        visited.add(node)
        for parent in rev_graph.get(node, []):
            result.add(parent)
            dfs(parent)

    dfs(target)
    return sorted(result)

def generate_graphviz(graph, filename):
    lines = ["digraph dependencies {", "    rankdir=LR;"]
    for pkg, deps in graph.items():
        if not deps:
            lines.append(f'    "{pkg}";')
        for dep in deps:
            lines.append(f'    "{pkg}" -> "{dep}";')
    lines.append("}")
    dot_code = "\n".join(lines)
    with open(filename + ".dot", "w", encoding="utf-8") as f:
        f.write(dot_code)
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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=int)
    args = parser.parse_args()
    config = load_config()

    if args.stage == 1 or not args.stage:
        print("--- STAGE 1: Configuration ---")
        for k, v in config.items():
            print(f"  {k}: {v}")
        if args.stage == 1:
            return

    text = get_packages_data(config)
    packages = parse_packages(text)
    target = config["package_name"]

    if args.stage == 2 or not args.stage:
        print("\n--- STAGE 2: Data Collection ---")
        if target not in packages:
            print(f"Error: package {target} not found.")
            sys.exit(1)
        print(f"Direct dependencies: {packages[target]['depends']}")
        if args.stage == 2:
            return

    if args.stage == 3 or not args.stage:
        print("\n--- STAGE 3: Dependency Graph ---")
        graph = build_graph(packages, target, config["filter_substring"])
        for k, v in graph.items():
            print(f"  {k} -> {v}")
        if args.stage == 3:
            return

    if args.stage == 4 or not args.stage:
        print("\n--- STAGE 4: Reverse Dependencies ---")
        rev = find_reverse(packages, target, config["filter_substring"])
        print(f"Depends on {target}: {rev if rev else 'none'}")
        if args.stage == 4:
            return

    if args.stage == 5 or not args.stage:
        print("\n--- STAGE 5: Visualization ---")
        graph = build_graph(packages, target, config["filter_substring"])
        dot = generate_graphviz(graph, config["output_image_file"])
        print(dot)
        if config["ascii_tree"]:
            print("\nASCII tree:")
            print_tree(packages, target, config["filter_substring"])
        if args.stage == 5:
            return

if __name__ == "__main__":
    main()