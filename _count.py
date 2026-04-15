import os
root = r"e:\project\0414"
files = []
for dp, dn, fn in os.walk(root):
    if ".venv" in dp or "__pycache__" in dp or "examplepaper" in dp:
        continue
    for f in fn:
        if f.endswith(".py"):
            files.append(os.path.join(dp, f))
files.sort()
total = 0
for f in files:
    c = sum(1 for _ in open(f, encoding="utf-8"))
    total += c
    print(f"{os.path.relpath(f, root):55s} {c:>5d} lines")
print(f"\nTotal: {len(files)} .py files,  {total} lines")
