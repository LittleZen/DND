# Script per correggere selected_category
import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Sostituisci tutte le occorrenze
content = content.replace("selected_category = ft.Ref[str]()", "selected_category = [CATEGORIES[0]]  # Use list to allow modification")
content = content.replace("selected_category.current = CATEGORIES[0]", "# Already initialized above")
content = content.replace("selected_category.current = category", "selected_category[0] = category")
content = content.replace("selected_category.current = item[\"category\"]", "selected_category[0] = item[\"category\"]")
content = content.replace("cat == selected_category.current", "cat == selected_category[0]")
content = content.replace("not selected_category.current", "not selected_category[0]")
content = content.replace("selected_category.current,", "selected_category[0],")

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed!")
