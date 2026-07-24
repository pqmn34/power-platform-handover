import os, json

WORKFLOWS_DIR = os.path.join(os.path.dirname(__file__), "..", "solution-export", "Workflows", "Workflows")

files = [f for f in os.listdir(WORKFLOWS_DIR) if f.endswith(".json")]
print(f"Found {len(files)} json files")

for f in files[:2]:
    path = os.path.join(WORKFLOWS_DIR, f)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    print(f"\n--- {f} ---")
    print("Top-level keys:", list(data.keys()))
    if "properties" in data:
        print("properties keys:", list(data["properties"].keys()))
