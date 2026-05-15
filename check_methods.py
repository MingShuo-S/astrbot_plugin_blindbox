import ast
import os

# 提取 commands 模块中需要的方法
commands_methods = set()
for f in os.listdir('commands'):
    if f.endswith('.py'):
        try:
            tree = ast.parse(open(os.path.join('commands', f), encoding='utf-8').read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'plugin':
                    commands_methods.add(node.attr)
        except Exception as e:
            print(f"Error parsing {f}: {e}")

# 提取 main.py 中的方法
main_methods = set()
tree = ast.parse(open('main.py', encoding='utf-8').read())
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and hasattr(node, 'name') and node.name.startswith('_'):
        main_methods.add(node.name)

# 找出缺失的方法
missing = commands_methods - main_methods

print("Commands 模块需要的方法:")
print('\n'.join(sorted(commands_methods)))
print("\nMain.py 中已有的方法:")
print('\n'.join(sorted(main_methods)))
print("\n缺失的方法:")
if missing:
    print('\n'.join(sorted(missing)))
else:
    print("None")