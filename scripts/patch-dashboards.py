#!/usr/bin/env python3
"""Patch all dashboard JSONs to use correct Grafana datasource UIDs.
Replaces hardcoded UIDs from grafana.com with our provisioned UIDs.
"""
import json, glob, os, re

DASHBOARD_DIR = "/opt/monitoring/grafana/dashboards"
UID_MAP = {
    "prometheus": "prometheus",
    "loki": "loki",
    "grafana": "grafana",
}

def fix_datasource(obj, path=""):
    """Recursively walk JSON tree and fix datasource UIDs."""
    if isinstance(obj, dict):
        # If this is a datasource block with uid and type
        if "datasource" in obj:
            ds = obj["datasource"]
            if isinstance(ds, dict):
                dtype = ds.get("type", "").lower()
                duid = ds.get("uid", "")
                if dtype in UID_MAP and duid != UID_MAP[dtype]:
                    old_uid = duid
                    ds["uid"] = UID_MAP[dtype]
                    print(f"    [patch] {path}.datasource.uid: {old_uid} -> {UID_MAP[dtype]}")
            elif isinstance(ds, str):
                # Old-style datasource: just a name string
                ds_lower = ds.lower()
                if ds_lower in UID_MAP:
                    obj["datasource"] = {"type": ds_lower, "uid": UID_MAP[ds_lower]}
                    print(f"    [upgrade] {path}.datasource: \"{ds}\" -> {{type: {ds_lower}, uid: {UID_MAP[ds_lower]}}}")
        
        # Recurse into all values
        for k, v in obj.items():
            new_path = f"{path}.{k}" if path else k
            fix_datasource(v, new_path)
    
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            new_path = f"{path}[{i}]"
            fix_datasource(item, new_path)
    
    return obj

def find_ds_variables(dashboard):
    """Find and report ${DS_*} template variables in the dashboard."""
    s = json.dumps(dashboard)
    vars = re.findall(r'\$\{DS_([^}]+)\}', s)
    if vars:
        print(f"    [templates] found DS template variables: {set(vars)}")
    return vars

def main():
    files = sorted(glob.glob(os.path.join(DASHBOARD_DIR, "*.json")))
    print(f"Found {str(len(files))} dashboard files")
    total_patches = 0
    
    for fpath in files:
        name = os.path.basename(fpath)
        print(f"\n--- {name} ---")
        
        with open(fpath) as f:
            dashboard = json.load(f)
        
        # Backup original if not already backed up
        bak_path = fpath + ".bak"
        if not os.path.exists(bak_path):
            with open(bak_path, "w") as f:
                json.dump(dashboard, f, indent=2)
            print(f"    [backup] created {bak_path}")
        
        find_ds_variables(dashboard)
        fix_datasource(dashboard)
        
        with open(fpath, "w") as f:
            json.dump(dashboard, f, indent=2)
        
        # Verify JSON is still valid
        with open(fpath) as f:
            json.load(f)
        
        print(f"    [done] {name}")
        total_patches += 1
    
    print(f"\n=== Done: {total_patches} dashboards patched ===")

if __name__ == "__main__":
    main()
