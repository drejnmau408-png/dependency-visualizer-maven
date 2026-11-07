import xml.etree.ElementTree as ET
import sys
import os

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
        val = elem.text.strip() if elem.text else ""
        config[key] = val
    return config

def main():
    config = load_config()
    print("Параметры конфигурации:")
    for k, v in config.items(): print(f"  {k}: {v}")

if __name__ == "__main__":
    main()