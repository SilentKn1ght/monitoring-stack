#!/usr/bin/env python3
import json, glob, os, re

DASHBOARD_DIR = "/opt/monitoring/grafana/dashboards"

# Map of DS_ template variable names to correct datasource UID
DS_MAP = {
    "PROMETHEUS": "prometheus",
    "PROMETHEUS_INFRASTRUCTURE": "prometheus",
    "SIGNCL-PROMETHEUS": "prometheus",
    "AXOOM_PROMETHEUS": "prometheus",
    "THEMIS": "prometheus",
    "LOKI": "loki",
}

def patch_file(fpath):
    name = os.path.basename(fpath)
    with open(fpath) as f:
        content = f.read()
    
    original = content
    replacements = [0]
    contexts = set()
    
    def _replace(match, kind, ds_var):
        uid = DS_MAP.get(ds_var, "prometheus")
        contexts.add(f"{kind}:{ds_var}->{uid}")
        replacements[0] += 1
        if kind == "string_datasource":
            return f'"datasource": {{"type": "prometheus", "uid": "{uid}"}}'
        elif kind == "uid_datasource":
            return f'"uid": "{uid}"'
        else:
            return uid
    
    # Strategy 1: "datasource": "${DS_...}" (string format) → object format
    def r1(m):
        return _replace(m, "string_datasource", m.group(1))
    content = re.sub(r'"datasource"\s*:\s*"\$\{DS_([^}]+)\}"', r1, content)
    
    # Strategy 2: "uid": "${DS_..."}" → "uid": "prometheus"
    def r2(m):
        return _replace(m, "uid_datasource", m.group(1))
    content = re.sub(r'"uid"\s*:\s*"\$\{DS_([^}]+)\}"', r2, content)
    
    # Strategy 3: Any remaining ${DS_...}
    def r3(m):
        return _replace(m, "other", m.group(1))
    content = re.sub(r'\$\{DS_([^}]+)\}', r3, content)
    
    if replacements[0] > 0:
        json.loads(content)
        with open(fpath, 'w') as f:
            f.write(content)
        for ctx in sorted(contexts):
            print(f"    {ctx}")
        print(f"    -> {replacements[0]} replacements")
        return replacements[0]
    else:
        print(f"    -> clean (no DS_ variables)")
        return 0

total = 0
for fpath in sorted(glob.glob(os.path.join(DASHBOARD_DIR, "*.json"))):
    if fpath.endswith(".bak"):
        continue
    name = os.path.basename(fpath)
    print(f"--- {name} ---")
    total += patch_file(fpath)

print(f"\nTotal: {total} replacements across all dashboards")
