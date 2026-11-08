import xml.etree.ElementTree as ET
import sys
import os
import requests

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
    for key in ["package_name", "repository_url", "test_mode", "package_version", "output_image_file", "ascii_tree", "filter_substring"]:
        elem = root.find(key)
        if elem is None:
            print(f"Ошибка: отсутствует параметр {key}.")
            sys.exit(1)
        config[key] = elem.text.strip() if elem.text else ""
    return config

def get_packages_data(config):
    url = config["repository_url"]
    if config["test_mode"].lower() == "true":
        if not os.path.exists(url):
            print(f"Ошибка: тестовый файл {url} не найден.")
            sys.exit(1)
        with open(url, "r", encoding="utf-8") as f: return f.read()
    else:
        try:
            r = requests.get(url, timeout=10); r.raise_for_status(); return r.text
        except Exception as e:
            print(f"Ошибка: {e}"); sys.exit(1)

def parse_packages(text):
    packages = {}
    for block in text.strip().split("\n\n"):
        lines = block.strip().split("\n")
        name, ver, deps_line = None, None, None
        for l in lines:
            if l.startswith("Package: "): name = l.replace("Package: ", "").strip()
            elif l.startswith("Version: "): ver = l.replace("Version: ", "").strip()
            elif l.startswith("Depends: "): deps_line = l.replace("Depends: ", "").strip()
        if name:
            deps = [d.strip().split("(")[0].strip() for d in deps_line.split(",")] if deps_line else []
            packages[name] = {"version": ver, "depends": deps}
    return packages

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

if __name__ == "__main__":
    main()