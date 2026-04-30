import os
import json
from pathlib import Path
from graphify.detect import detect
from graphify.extract import collect_files, extract
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_json, to_html

# 1. Detect files
print("Detecting files...")
input_path = Path(".")
detect_res = detect(input_path)
os.makedirs("graphify-out", exist_ok=True)
Path("graphify-out/.graphify_detect.json").write_text(json.dumps(detect_res), encoding="utf-8")

# 2. Extract (AST)
print("Extracting architecture...")
code_files = []
for f in detect_res.get('files', {}).get('code', []):
    code_files.extend(collect_files(Path(f)) if Path(f).is_dir() else [Path(f)])

if code_files:
    # Use cache_root='.' to store extraction cache locally
    extraction = extract(code_files, cache_root=Path('.'))
else:
    extraction = {'nodes': [], 'edges': [], 'input_tokens': 0, 'output_tokens': 0}

# 3. Build & Cluster
print("Building graph and clustering...")
G = build_from_json(extraction)
communities = cluster(G)
cohesion = score_all(G, communities)
gods = god_nodes(G)
surprises = surprising_connections(G, communities)

# LABELS - mapped based on community content
labels = {
    0: "FastAPI Endpoints",
    1: "Database Models",
    7: "Desktop Automation",
    9: "AI & Memory Engine",
    2: "Time Utilities",
    3: "Planner Logic",
    16: "Frontend Navigation",
    8: "Voice & API Comms",
    5: "Session Management",
    10: "Chat Initialization",
    4: "Frontend Interaction"
}
# Fallback for any other communities
for cid in communities:
    if cid not in labels:
        labels[cid] = f"Community {cid}"

questions = suggest_questions(G, communities, labels)

# 4. Generate Outputs
print("Generating reports and visualization...")
report = generate(G, communities, cohesion, labels, gods, surprises, detect_res, 
                  {'input': 0, 'output': 0}, str(input_path.absolute()), 
                  suggested_questions=questions)

Path("graphify-out/GRAPH_REPORT.md").write_text(report, encoding="utf-8")
to_json(G, communities, 'graphify-out/graph.json')
to_html(G, communities, 'graphify-out/graph.html', community_labels=labels)

print("\nSuccess! Knowledge graph built in graphify-out/")
print("  - graph.html (Visual Graph)")
print("  - GRAPH_REPORT.md (Architecture Report)")
