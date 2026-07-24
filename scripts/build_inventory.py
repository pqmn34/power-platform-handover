import os
import json
import csv

BASE = os.path.join(os.path.dirname(__file__), "..", "solution-export")
WORKFLOWS_DIR = os.path.join(BASE, "Workflows", "Workflows")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "inventory")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def find_definition(data):
    # Try common locations
    if "properties" in data and "definition" in data["properties"]:
        return data["properties"]["definition"]
    if "definition" in data:
        return data["definition"]
    return {}

def find_connection_refs(data):
    if "properties" in data and "connectionReferences" in data["properties"]:
        return data["properties"]["connectionReferences"]
    if "connectionReferences" in data:
        return data["connectionReferences"]
    return {}

rows = []

if os.path.isdir(WORKFLOWS_DIR):
    files = [f for f in os.listdir(WORKFLOWS_DIR) if f.endswith(".json")]
    print(f"Found {len(files)} JSON files in {WORKFLOWS_DIR}")

    for file in files:
        filepath = os.path.join(WORKFLOWS_DIR, file)
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Could not parse {file}: {e}")
            continue

        definition = find_definition(data)
        triggers = list(definition.get("triggers", {}).keys())
        actions = list(definition.get("actions", {}).keys())

        conn_refs = find_connection_refs(data)
        connectors = set()
        for ref in conn_refs.values():
            if isinstance(ref, dict):
                api_id = ref.get("api", {}).get("name", "")
                if api_id:
                    connectors.add(api_id)

        # Derive a friendly name: strip the trailing -GUID from filename
        raw_name = file.replace(".json", "")
        friendly_name = raw_name.rsplit("-", 5)[0] if len(raw_name.split("-")) > 5 else raw_name

        rows.append({
            "FlowName": friendly_name,
            "Trigger": ", ".join(triggers),
            "Actions": ", ".join(actions),
            "Connectors": ", ".join(connectors),
            "SourceFile": file
        })
else:
    print(f"WARNING: Workflows folder not found at {WORKFLOWS_DIR}")

output_path = os.path.join(OUTPUT_DIR, "flow_inventory.csv")
with open(output_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["FlowName","Trigger","Actions","Connectors","SourceFile"])
    writer.writeheader()
    writer.writerows(rows)

print(f"Done. Wrote {len(rows)} rows to {output_path}")
