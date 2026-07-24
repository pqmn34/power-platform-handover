import os
import json
import csv

BASE = os.path.join(os.path.dirname(__file__), "..", "solution-export")
WORKFLOWS_DIR = os.path.join(BASE, "Workflows", "Workflows")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "inventory")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Plain-English meaning of each Power Automate action "type"
ACTION_TYPE_DESCRIPTIONS = {
    "Http": "calls an external website or API",
    "ApiConnection": "uses a connector to do something",
    "OpenApiConnection": "uses a connector to do something",
    "ApiConnectionWebhook": "listens for real-time events",
    "Compose": "builds/holds data for later use",
    "InitializeVariable": "creates a variable",
    "SetVariable": "updates a variable",
    "AppendToArrayVariable": "adds an item to a list in memory",
    "If": "checks a condition and branches",
    "Switch": "checks a value and runs different logic",
    "Foreach": "repeats steps for each item in a list",
    "Until": "repeats steps until a condition is met",
    "Scope": "groups steps (often error handling)",
    "Query": "filters a list of records",
    "Select": "reshapes a list of records",
    "Table": "builds a CSV/HTML report",
    "ParseJson": "reads structured data from a previous step",
    "Workflow": "calls another (child) flow",
    "Response": "sends a response back to the caller",
    "Terminate": "stops the flow",
    "Wait": "pauses the flow",
}

# Plain-English label for common connectors
CONNECTOR_DESCRIPTIONS = {
    "office365": "Office 365 Outlook (email)",
    "sql": "SQL Server (database)",
    "sharepointonline": "SharePoint",
    "excelonlinebusiness": "Excel Online",
    "onedriveforbusiness": "OneDrive",
    "keyvault": "Azure Key Vault (secrets/passwords)",
    "azureblob": "Azure Blob Storage",
    "teams": "Microsoft Teams",
    "approvals": "Approvals",
    "commondataservice": "Dataverse",
    "flowmanagement": "Power Automate management",
    "powerbi": "Power BI",
}

def guess_connector_label(key):
    lower = key.lower()
    for k, v in CONNECTOR_DESCRIPTIONS.items():
        if k in lower:
            return v
    return key

def find_definition(data):
    if "properties" in data and "definition" in data["properties"]:
        return data["properties"]["definition"]
    return data.get("definition", {})

def find_connection_refs(data):
    if "properties" in data and "connectionReferences" in data["properties"]:
        return data["properties"]["connectionReferences"]
    return data.get("connectionReferences", {})

def collect_actions(actions_dict, collected):
    """Walk nested actions (inside If/Scope/Foreach/Switch) -> list of (name, type, full_details)."""
    for name, details in actions_dict.items():
        if not isinstance(details, dict):
            continue
        collected.append((name, details.get("type", "Unknown"), details))
        if isinstance(details.get("actions"), dict):
            collect_actions(details["actions"], collected)
        if isinstance(details.get("else"), dict) and isinstance(details["else"].get("actions"), dict):
            collect_actions(details["else"]["actions"], collected)
        if isinstance(details.get("cases"), dict):
            for case in details["cases"].values():
                if isinstance(case, dict) and isinstance(case.get("actions"), dict):
                    collect_actions(case["actions"], collected)

def extract_inputs_fields(inputs):
    """Pull out common identifying fields from an action's inputs, regardless of connector."""
    found = {}
    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (str, int, float)) and k in (
                    "dataset", "table", "id", "path", "folderPath", "server",
                    "database", "uri", "to", "subject", "groupId", "datasetId",
                    "siteUrl", "listId", "driveId"
                ):
                    found[k] = str(v)
                elif isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)
    walk(inputs)
    return found

def categorize_resource(fields):
    """Turn extracted fields into a labeled, readable string, or (None, None) if nothing useful."""
    if not fields:
        return None, None
    dataset = fields.get("dataset", "")
    item = fields.get("id") or fields.get("path") or fields.get("folderPath") or ""

    if "sharepoint.com" in dataset.lower():
        text = f"Site: {dataset}"
        if item:
            text += f" | Item/Folder: {item}"
        return "sharepoint", text

    if fields.get("server") or fields.get("database"):
        text = f"Server: {fields.get('server','?')} | Database: {fields.get('database','?')}"
        if fields.get("table"):
            text += f" | Table: {fields.get('table')}"
        return "sql", text

    if fields.get("uri"):
        return "http", fields["uri"]

    if fields.get("to"):
        text = f"To: {fields.get('to')}"
        if fields.get("subject"):
            text += f" | Subject: {fields.get('subject')}"
        return "email", text

    if fields.get("groupId") or fields.get("datasetId"):
        return "powerbi", f"Workspace: {fields.get('groupId','?')} | Dataset: {fields.get('datasetId','?')}"

    if dataset:
        text = f"Location: {dataset}"
        if item:
            text += f" | Item/Folder: {item}"
        return "file", text

    return None, None

def format_schedule(recurrence):
    if not recurrence:
        return ""
    freq = recurrence.get("frequency", "")
    interval = recurrence.get("interval", 1)
    schedule = recurrence.get("schedule", {})
    hours = schedule.get("hours", [])
    minutes = schedule.get("minutes", [0])
    weekdays = schedule.get("weekDays", [])
    timezone = recurrence.get("timeZone", "")
    start_time = recurrence.get("startTime", "")

    if freq == "Day":
        desc = f"Every {interval} day(s)"
    elif freq == "Week":
        desc = f"Every {interval} week(s)"
        if weekdays:
            desc += f" on {', '.join(weekdays)}"
    elif freq == "Month":
        desc = f"Every {interval} month(s)"
    elif freq == "Hour":
        desc = f"Every {interval} hour(s)"
    elif freq == "Minute":
        desc = f"Every {interval} minute(s)"
    else:
        desc = f"{freq} (interval {interval})" if freq else ""

    if hours:
        h = str(hours[0]).zfill(2)
        m = str(minutes[0]).zfill(2) if minutes else "00"
        desc += f" at {h}:{m}"
    if timezone:
        desc += f" ({timezone})"
    if start_time:
        desc += f" [Starts: {start_time}]"
    return desc

def build_summary(trigger_types, action_types_set, connector_labels):
    parts = []
    if "Recurrence" in trigger_types:
        parts.append("Runs automatically on a schedule.")
    elif "Request" in trigger_types:
        parts.append("Runs when called by another app, flow, or system.")
    elif any("Manual" in t or "Button" in t for t in trigger_types):
        parts.append("Runs manually when someone clicks a button (e.g. from a Power App).")
    elif trigger_types:
        parts.append(f"Trigger type: {', '.join(trigger_types)}.")

    if connector_labels:
        parts.append("Connects to: " + "; ".join(sorted(connector_labels)) + ".")

    notes = []
    if "Foreach" in action_types_set:
        notes.append("loops through a list of records")
    if "If" in action_types_set or "Switch" in action_types_set:
        notes.append("makes decisions based on conditions")
    if "Scope" in action_types_set:
        notes.append("has error-handling logic")
    if "Http" in action_types_set:
        notes.append("calls an external API/website")
    if "Workflow" in action_types_set:
        notes.append("calls another (child) flow")
    if "Table" in action_types_set:
        notes.append("builds a report (CSV/HTML table)")
    if notes:
        parts.append("This flow " + ", ".join(notes) + ".")

    return " ".join(parts) if parts else "No summary generated - please review manually."

rows = []

if os.path.isdir(WORKFLOWS_DIR):
    files = [f for f in os.listdir(WORKFLOWS_DIR) if f.endswith(".json")]
    print(f"Found {len(files)} JSON files")

    for file in files:
        try:
            with open(os.path.join(WORKFLOWS_DIR, file), encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Could not parse {file}: {e}")
            continue

        definition = find_definition(data)
        triggers = definition.get("triggers", {})
        trigger_types = [t.get("type", "Unknown") for t in triggers.values() if isinstance(t, dict)]

        schedule_text = ""
        for t in triggers.values():
            if isinstance(t, dict) and t.get("type") == "Recurrence":
                schedule_text = format_schedule(t.get("recurrence", {}))

        collected = []
        collect_actions(definition.get("actions", {}), collected)
        action_types_set = {t for _, t, _ in collected}

        step_descriptions = [f"{name} ({ACTION_TYPE_DESCRIPTIONS.get(atype, atype)})" for name, atype, _ in collected]

        sharepoint_locs, sql_locs, http_urls, emails, powerbi_locs, file_locs = set(), set(), set(), set(), set(), set()
        for name, atype, details in collected:
            inputs = details.get("inputs", {})
            if not isinstance(inputs, dict):
                continue
            fields = extract_inputs_fields(inputs)
            category, text = categorize_resource(fields)
            if not text:
                continue
            if category == "sharepoint":
                sharepoint_locs.add(text)
            elif category == "sql":
                sql_locs.add(text)
            elif category == "http":
                http_urls.add(text)
            elif category == "email":
                emails.add(text)
            elif category == "powerbi":
                powerbi_locs.add(text)
            elif category == "file":
                file_locs.add(text)

        connector_labels = set()
        for ref in find_connection_refs(data).values():
            if isinstance(ref, dict):
                api_id = ref.get("api", {}).get("name", "")
                if api_id:
                    connector_labels.add(guess_connector_label(api_id))

        summary = build_summary(trigger_types, action_types_set, connector_labels)

        raw_name = file.replace(".json", "")
        friendly_name = raw_name.rsplit("-", 5)[0] if len(raw_name.split("-")) > 5 else raw_name

        rows.append({
            "FlowName": friendly_name,
            "PlainEnglishSummary": summary,
            "TriggerType": ", ".join(trigger_types),
            "ScheduleDetails": schedule_text,
            "ConnectorsUsed": "; ".join(sorted(connector_labels)),
            "SharePointLocations": " || ".join(sorted(sharepoint_locs)),
            "SQLServerDatabase": " || ".join(sorted(sql_locs)),
            "ExcelOrOtherFileLocations": " || ".join(sorted(file_locs)),
            "PowerBIWorkspaceDataset": " || ".join(sorted(powerbi_locs)),
            "ExternalURLsCalled": " || ".join(sorted(http_urls)),
            "EmailRecipients": " || ".join(sorted(emails)),
            "StepByStepActions": " -> ".join(step_descriptions),
            "SourceFile": file
        })
else:
    print(f"WARNING: folder not found at {WORKFLOWS_DIR}")

output_path = os.path.join(OUTPUT_DIR, "flow_inventory.csv")
fieldnames = ["FlowName","PlainEnglishSummary","TriggerType","ScheduleDetails","ConnectorsUsed",
              "SharePointLocations","SQLServerDatabase","ExcelOrOtherFileLocations",
              "PowerBIWorkspaceDataset","ExternalURLsCalled","EmailRecipients",
              "StepByStepActions","SourceFile"]
with open(output_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Done. Wrote {len(rows)} rows to {output_path}")
