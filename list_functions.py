import ast
import sys
from pathlib import Path

def list_functions(file_path: str):
    source = Path(file_path).read_text(encoding="utf-8")
    tree = ast.parse(source)

    functions = []
    classes = {}

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            functions.append(node.name)

        elif isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.append(item.name)
            classes[node.name] = methods

    return functions, classes


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python list_functions.py <file.py>")
        sys.exit(1)

    file_path = sys.argv[1]
    funcs, classes = list_functions(file_path)

    print("\nTop-level functions:")
    for f in funcs:
        print(f"  - {f}")

    print("\nClasses and methods:")
    for cls, methods in classes.items():
        print(f"  {cls}:")
        for m in methods:
            print(f"    - {m}")

