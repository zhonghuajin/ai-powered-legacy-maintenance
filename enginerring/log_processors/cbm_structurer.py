# -*- coding: utf-8 -*-
import os
import json
import glob
import shutil
import subprocess
from collections import defaultdict
from .parser_index import lookup_function, tree_sitter_languages

def _cbm_query(project_name, abs_path, cypher):
    """Execute a single Cypher query, return (columns, rows)."""
    args = json.dumps({"project": project_name, "query": cypher})
    cmd = ["codebase-memory-mcp", "cli", "query_graph", args, "--path", abs_path]
    r = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(r.stdout)
    return data.get("columns", []), data.get("rows", [])

def cleanup_stale_workspaces(project_keyword):
    cbm_root = os.path.expanduser(r"~\.cache\codebase-memory-mcp")
    if not os.path.isdir(cbm_root):
        return

    removed, failed = [], []
    for entry in os.listdir(cbm_root):
        full = os.path.join(cbm_root, entry)
        if not os.path.isdir(full):
            continue
        if project_keyword.lower() in entry.lower():
            try:
                shutil.rmtree(full)
                removed.append(entry)
            except Exception as e:
                failed.append((entry, str(e)))

    for pattern in ("*.lock", "*.wal", "*.shm", "*.db-journal"):
        for f in glob.glob(os.path.join(cbm_root, pattern)):
            try:
                os.remove(f)
            except Exception:
                pass

    if removed:
        print(f"[Cleanup] Removed {len(removed)} stale workspace(s):")
        for r in removed:
            print(f"   - {r}")
    if failed:
        print(f"[Cleanup] Could NOT remove {len(failed)} (likely locked by running MCP):")
        for name, err in failed:
            print(f"   - {name}: {err}")

def process_single_thread(thread_dir, thread_name):
    abs_thread_path = os.path.abspath(thread_dir)
    print(f"\n--- Processing Thread: {thread_name} ---")

    # 1. Index
    cleanup_stale_workspaces("ai-powered-legacy-maintenance")
    print(f"Indexing repository at: {abs_thread_path} ...")
    idx_args = json.dumps({"repo_path": abs_thread_path})
    try:
        subprocess.run(["codebase-memory-mcp", "cli", "index_repository", idx_args],
                       check=True, capture_output=True, text=True)
        print("Indexing completed.")
    except subprocess.CalledProcessError as e:
        print(f"Error during indexing {thread_name}: {e.stderr}")
        return None

    # 2. Auto-detect project name
    project_name = "C-TechLearning-ai-powered-legacy-maintenance-pruned"
    try:
        r = subprocess.run(["codebase-memory-mcp", "cli", "list_projects", "{}"],
                           capture_output=True, text=True, check=True)
        d = json.loads(r.stdout)
        projs = d.get("projects", d) if isinstance(d, dict) else d
        for p in (projs or []):
            n = p.get("name") if isinstance(p, dict) else p
            if "pruned" in str(n):
                project_name = n
                break
    except Exception as e:
        print(f"Warning: project name autodetect failed: {e}")
    print(f"Project: {project_name}")

    # 3. Query CALLS edges and node properties
    nodes_info = {}
    edges = set()

    multi_col_query = (
        "MATCH (a)-[:CALLS]->(b) "
        "RETURN a.qualified_name, a.name, a.file_path, a.start_line, "
        "b.qualified_name, b.name, b.file_path, b.start_line"
    )
    try:
        cols, rows = _cbm_query(project_name, abs_thread_path, multi_col_query)
        if rows:
            for row in rows:
                if len(row) < 8:
                    continue
                a_qn, a_n, a_f, a_line, b_qn, b_n, b_f, b_line = row[:8]
                a_qn = a_qn or a_n
                b_qn = b_qn or b_n
                if not a_qn or not b_qn:
                    continue

                try:
                    a_line = int(a_line) if a_line is not None else 1
                except (ValueError, TypeError):
                    a_line = 1
                try:
                    b_line = int(b_line) if b_line is not None else 1
                except (ValueError, TypeError):
                    b_line = 1

                nodes_info.setdefault(a_qn, {"name": a_n, "qualified_name": a_qn, "file": a_f, "start_line": a_line})
                nodes_info.setdefault(b_qn, {"name": b_n, "qualified_name": b_qn, "file": b_f, "start_line": b_line})
                edges.add((a_qn, b_qn))
    except Exception as e:
        print(f"Multi-column query failed. Error: {e}")

    print(f"Collected {len(nodes_info)} nodes, {len(edges)} CALLS edges.")

    # 4. Use tree-sitter to extract signature and body
    print("Extracting function bodies from source files using tree-sitter (qname-keyed)...")
    miss_count = 0
    miss_samples = []
    for qn, info in nodes_info.items():
        rel = info.get("file") or ""
        abs_file = os.path.join(abs_thread_path, rel.replace("/", os.sep)) if rel else ""

        sig, body = "", ""
        if abs_file and os.path.isfile(abs_file):
            res = lookup_function(
                abs_file,
                qualified_name=info.get("qualified_name"),
                fallback_name=info.get("name"),
                hint_line=info.get("start_line"),
            )
            if res:
                sig = res["signature"]
                body = res["body"]
            else:
                miss_count += 1
                if len(miss_samples) < 5:
                    miss_samples.append(
                        f"{info.get('qualified_name') or info.get('name')} @ {abs_file}"
                    )

        info["signature"] = sig or info.get("name", "")
        info["body"] = body

        if abs_file and os.path.isfile(abs_file):
            info["file"] = os.path.relpath(abs_file, abs_thread_path).replace(os.sep, "/")
        else:
            info["file"] = rel

    if miss_count:
        print(f"[WARN] {miss_count} function(s) could not be located in source files.")
        for s in miss_samples:
            print(f"   - {s}")

    # 5. Build adjacency list and in-degree
    adj = defaultdict(set)
    in_deg = defaultdict(int)
    for a, b in edges:
        if b not in adj[a]:
            adj[a].add(b)
            in_deg[b] += 1
            in_deg.setdefault(a, 0)
    for qn in nodes_info:
        in_deg.setdefault(qn, 0)

    # 6. DFS to build tree
    def build(node_qn, on_path):
        info = nodes_info.get(node_qn, {"name": node_qn, "signature": node_qn, "file": "", "body": ""})
        nd = {
            "name": info["name"],
            "signature": info.get("signature", info["name"]),
            "file": info.get("file", ""),
            "body": info.get("body", ""),
            "children": []
        }
        if node_qn in on_path:
            nd["note"] = "Circular reference detected"
            return nd
        on_path = on_path | {node_qn}
        for child in sorted(adj.get(node_qn, [])):
            nd["children"].append(build(child, on_path))
        return nd

    # 7. In-degree 0 = root
    roots = sorted([q for q, d in in_deg.items() if d == 0 and q in nodes_info])
    if not roots and nodes_info:
        roots = sorted(nodes_info.keys())

    forest = [build(r, set()) for r in roots]

    return {
        "project": project_name,
        "total_nodes": len(nodes_info),
        "trees": forest
    }

def run_cbm_data_structuring(pruned_folder):
    print("Executing Unified Data Structuring via Codebase-Memory...")

    # 1. Check CLI
    try:
        subprocess.run(["codebase-memory-mcp", "--version"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError("codebase-memory-mcp CLI not installed. Run: npm install -g codebase-memory-mcp")

    if not tree_sitter_languages:
        raise RuntimeError("tree-sitter-languages is not installed. Run: pip install tree-sitter-languages")

    abs_pruned_path = os.path.abspath(pruned_folder)

    # 2. 遍历 pruned_folder 下的所有子目录（线程）
    if not os.path.isdir(abs_pruned_path):
        raise RuntimeError(f"Pruned folder does not exist: {abs_pruned_path}")

    all_threads_data = {}

    subdirs = [d for d in os.listdir(abs_pruned_path) if os.path.isdir(os.path.join(abs_pruned_path, d))]

    if not subdirs:
        print(f"[WARN] No subdirectories (threads) found in {abs_pruned_path}. Processing root folder instead.")
        root_name = os.path.basename(abs_pruned_path)
        thread_data = process_single_thread(abs_pruned_path, root_name)
        if thread_data:
            all_threads_data[root_name] = thread_data
    else:
        for thread_name in sorted(subdirs):
            thread_dir = os.path.join(abs_pruned_path, thread_name)
            thread_data = process_single_thread(thread_dir, thread_name)
            if thread_data:
                all_threads_data[thread_name] = thread_data

    output_file = "final-output-calltree.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_threads_data, f, indent=2, ensure_ascii=False)

    print(f"\nSaved combined threads data -> {output_file}")
    print(f"Processed {len(all_threads_data)} thread(s).")