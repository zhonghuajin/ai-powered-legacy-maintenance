# -*- coding: utf-8 -*-
import os
from functools import lru_cache

try:
    import tree_sitter_languages
except ImportError:
    tree_sitter_languages = None

# Per-language config:
#   (ts_lang, function_node_types, class_node_types, namespace_node_types,
#    class_separator, namespace_separator)
LANG_CONFIG = {
    ".php":  ("php",
              {"function_definition", "method_declaration"},
              {"class_declaration", "interface_declaration",
               "trait_declaration", "enum_declaration"},
              {"namespace_definition"},
              "::", "\\"),
    ".py":   ("python",
              {"function_definition"},
              {"class_definition"},
              set(),
              ".", "."),
    ".java": ("java",
              {"method_declaration", "constructor_declaration"},
              {"class_declaration", "interface_declaration",
               "enum_declaration", "record_declaration"},
              {"package_declaration"},
              ".", "."),
    ".go":   ("go",
              {"function_declaration", "method_declaration"},
              set(),
              {"package_clause"},
              ".", "."),
    ".js":   ("javascript",
              {"function_declaration", "method_definition",
               "function_expression", "arrow_function"},
              {"class_declaration"},
              set(),
              ".", "."),
    ".ts":   ("typescript",
              {"function_declaration", "method_definition",
               "function_signature"},
              {"class_declaration", "interface_declaration"},
              {"module"},
              ".", "."),
}

NAME_NODE_TYPES = ("name", "identifier", "field_identifier",
                   "type_identifier", "namespace_name", "scoped_identifier")
BODY_NODE_TYPES = ("block", "compound_statement", "function_body",
                   "statement_block", "class_body")


def _normalize_qname(qname):
    """
    Normalize a qualified name so that CBM's representation and
    tree-sitter's reconstructed name can be compared reliably.
    """
    if not qname:
        return ""
    s = qname.replace("::", "/").replace("\\", "/").replace(".", "/")
    s = s.strip("/")
    while "//" in s:
        s = s.replace("//", "/")
    return s


@lru_cache(maxsize=1024)
def build_function_index(file_path):
    """
    Parse `file_path` once and build:
        { normalized_qualified_name : entry  OR  [entry, entry, ...] }
    """
    if not tree_sitter_languages:
        return {}
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in LANG_CONFIG:
        return {}

    lang_name, func_types, class_types, ns_types, csep, nsep = LANG_CONFIG[ext]

    try:
        parser = tree_sitter_languages.get_parser(lang_name)
        with open(file_path, "rb") as f:
            src = f.read()
        tree = parser.parse(src)
    except Exception as e:
        print(f"[WARN] tree-sitter failed to parse {file_path}: {e}")
        return {}

    def text(node):
        return src[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")

    def get_name(node):
        n = node.child_by_field_name("name")
        if n is not None:
            return text(n)
        for c in node.children:
            if c.type in NAME_NODE_TYPES:
                return text(c)
        return None

    index = {}

    def add_entry(qname, entry):
        key = _normalize_qname(qname)
        if not key:
            return
        if key in index:
            existing = index[key]
            if isinstance(existing, list):
                existing.append(entry)
            else:
                index[key] = [existing, entry]
        else:
            index[key] = entry

    def walk(node, ns_path, class_path):
        t = node.type

        if t in ns_types:
            nm = get_name(node) or ""
            new_ns = (ns_path + nsep + nm) if (ns_path and nm) else (nm or ns_path)
            for c in node.children:
                walk(c, new_ns, class_path)
            return

        if t in class_types:
            nm = get_name(node) or "<anon>"
            new_cls = (class_path + csep + nm) if class_path else nm
            for c in node.children:
                walk(c, ns_path, new_cls)
            return

        if t in func_types:
            nm = get_name(node) or "<anon>"
            prefix = ""
            if ns_path:
                prefix += ns_path + nsep
            if class_path:
                prefix += class_path + csep
            qname = prefix + nm

            body_node = next(
                (c for c in node.children if c.type in BODY_NODE_TYPES), None)
            full = text(node)
            if body_node:
                sig = src[node.start_byte:body_node.start_byte].decode(
                    "utf-8", errors="ignore").strip()
            else:
                sig = full.splitlines()[0] if full else nm

            entry = {
                "name": nm,
                "qualified_name": qname,
                "signature": sig,
                "body": full,
                "start_line": node.start_point[0] + 1,
                "end_line":   node.end_point[0] + 1,
            }

            add_entry(qname, entry)
            add_entry(nm, entry)
            return

        for c in node.children:
            walk(c, ns_path, class_path)

    walk(tree.root_node, "", "")
    return index


def lookup_function(file_path, qualified_name=None, fallback_name=None, hint_line=None):
    """
    Locate a function entry in `file_path`.
    """
    idx = build_function_index(file_path)
    if not idx:
        return None

    def pick(entry_or_list):
        if isinstance(entry_or_list, list):
            if hint_line is not None:
                return min(entry_or_list, key=lambda it: abs(it["start_line"] - hint_line))
            return entry_or_list[0]
        return entry_or_list

    if qualified_name:
        norm = _normalize_qname(qualified_name)
        if norm in idx:
            return pick(idx[norm])

        suffix_hits = []
        for k, v in idx.items():
            if k.endswith("/" + norm) or norm.endswith("/" + k):
                items = v if isinstance(v, list) else [v]
                suffix_hits.extend(items)
        if len(suffix_hits) == 1:
            return suffix_hits[0]
        if len(suffix_hits) > 1:
            if fallback_name:
                name_hits = [it for it in suffix_hits if it["name"] == fallback_name]
                if name_hits:
                    suffix_hits = name_hits
            if hint_line is not None:
                return min(suffix_hits, key=lambda it: abs(it["start_line"] - hint_line))
            return suffix_hits[0]

    if fallback_name:
        norm_simple = _normalize_qname(fallback_name)
        if norm_simple in idx:
            entry = idx[norm_simple]
            items = entry if isinstance(entry, list) else [entry]
            items = [it for it in items if it["name"] == fallback_name]
            if len(items) == 1:
                return items[0]
            if len(items) > 1:
                if hint_line is not None:
                    return min(items, key=lambda it: abs(it["start_line"] - hint_line))
                return None

    return None