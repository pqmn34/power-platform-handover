import os
import json
import csv
import xml.etree.ElementTree as ET

BASE = os.path.join(os.path.dirname(__file__), "..", "solution-export")
WORKFLOWS_DIR = os.path.join(BASE, "Workflows", "Workflows")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "inventory")
os.makedirs(OUTPUT_DIR, exist_ok=True)

rows = []

# --- 1. Master component list from customizations.xml ---
customizations_path = os.path.join(BASE, "customizations.xml")
if os.path.exists(customizations_path):
    tree = ET.parse(customizations_path)
    root = tree.getroot()
    for wf in root.iter("Workflow"):
        name = wf.findtext("Name")
        category = wf.findtext("Category")
        rows.append({
            "FlowName": name,
            "Category": category,
            "Trigger": "",
            "Actions": "",
            "Connectors": "",
            "SourceFile": ""
        })

# --- 2. Detail from each Workflow JSON file ---
if os.path.isdir(WORKFLOWS_DIR):
    for file in os.listdir(WORKFLOWS_DIR):
        if not file.endswith(".json"):
            continue
        filepath = os.path.join(WORKFLOWS_DIR, file)
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Could not parse {file}: {e}")
            continue

        definition = data.get("properties", {}).get("definition", data.get("definition", {}))
        triggers = list(definition.get("triggers", {}).keys())
        actions = list(definition.get("actions", {}).keys())

        connectors = set()
        conn_refs = data.get("properties", {}).get("connectionReferences", {})
        for ref in conn_refs.values():
            api_id = ref.get("api", {}).get("name", "")
            if api_id:
                connectors.add(api_id)

        rows.append({
            "FlowName": file.replace(".json", ""),
            "Category": "",
            "Trigger": ", ".join(triggers),
            "Actions": ", ".join(actions),
            "Connectors": ", ".join(connectors),
            "SourceFile": file
        })

# --- 3. Write CSV ---
output_path = os.path.join(OUTPUT_DIR, "flow_inventory.csv")
with open(output_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["FlowName","Category","Trigger","Actions","Connectors","SourceFile"])
    writer.writeheader()
    writer.writerows(rows)

print(f"Done. Wrote {len(rows)} rows to {output_path}")
