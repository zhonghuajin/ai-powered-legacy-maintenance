import os
import sys
import re
import json
import subprocess
from typing import List, Dict, Optional, Set, Any

class BlockLocation:
    def __init__(self, normalized_path: str, start_line: int):
        self.normalized_path = normalized_path
        self.start_line = start_line

class BlockPruner:
    @staticmethod
    def main(args: List[str]) -> None:
        if len(args) < 4:
            sys.stderr.write("Usage: python block_pruner.py <Source Directories> <block-line-mapping file> <instrument-log file> <Output Directory> [<Base Reference Directory>]\n\n")
            sys.stderr.write("Parameter Description:\n")
            sys.stderr.write("  <Source Directories>       PHP source root directories, separated by ';' for multiple paths\n")
            sys.stderr.write("                             e.g. \"dir1;dir2;dir3\"\n")
            sys.stderr.write("  <block-line-mapping>          Instrumentation mapping file (format: ID = filePath:lineNo)\n")
            sys.stderr.write("  <instrument-log>           Runtime instrumentation log file\n")
            sys.stderr.write("  <Output Directory>         Output root directory for pruned source code\n")
            sys.stderr.write("  [Base Reference Directory] (Optional) Base directory to preserve relative directory structures\n")
            sys.stderr.write("                             e.g. \"C:\\Work\\HKT\\OPIOS\\a_this_folder_for_merge\\broadband-backend\"\n")
            sys.exit(1)

        source_dirs = []
        for part in args[0].split(';'):
            part = part.strip()
            if part:
                resolved = os.path.realpath(part)
                source_dirs.append(resolved if os.path.exists(resolved) else part)

        if not source_dirs:
            sys.stderr.write("[Error] No valid source directory provided.\n")
            sys.exit(1)

        mapping_file = args[1]
        log_file = args[2]
        output_dir = args[3].rstrip('/\\')

        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception:
            pass
        output_dir = os.path.realpath(output_dir) if os.path.exists(output_dir) else output_dir

        base_ref_dir = None
        if len(args) >= 5:
            resolved_base = os.path.realpath(args[4].strip())
            base_ref_dir = resolved_base if os.path.exists(resolved_base) else args[4].strip()

        print("[BlockPruner] Source Directories:")
        for i, d in enumerate(source_dirs):
            print(f"  [{i + 1}] {d}")
        print(f"[BlockPruner] Mapping File: {mapping_file}")
        print(f"[BlockPruner] Log File: {log_file}")
        print(f"[BlockPruner] Output Directory: {output_dir}")
        if base_ref_dir is not None:
            print(f"[BlockPruner] Base Reference Directory: {base_ref_dir}")
        print()

        block_map = BlockPruner.parse_comment_mapping(mapping_file)
        print(f"[Step 1] Loaded {len(block_map)} block mappings")

        thread_logs = BlockPruner.parse_instrument_log(log_file)
        print(f"[Step 2] Loaded execution logs for {len(thread_logs)} threads")

        file_block_index = BlockPruner.build_file_block_index(block_map)
        print(f"[Step 3] Involves {len(file_block_index)} source files")

        resolved_paths = BlockPruner.resolve_source_files(list(file_block_index.keys()), source_dirs)
        print(f"[Step 4] Successfully located {len(resolved_paths)} / {len(file_block_index)} source files")

        total_threads = len(thread_logs)
        idx = 0
        for thread_name, executed_ids in thread_logs.items():
            idx += 1
            print(f"\n[{idx}/{total_threads}] ", end="")
            BlockPruner.prune_for_thread(
                thread_name, executed_ids, block_map, file_block_index,
                resolved_paths, source_dirs, output_dir, base_ref_dir
            )

        print(f"\n[BlockPruner] All processing completed. Output Directory: {output_dir}")

    @staticmethod
    def prune_for_thread(
        thread_name: str,
        executed_ids: Dict[int, bool],
        block_map: Dict[int, BlockLocation],
        file_block_index: Dict[str, Dict[int, int]],
        resolved_paths: Dict[str, str],
        source_dirs: List[str],
        output_dir: str,
        base_ref_dir: Optional[str]
    ) -> None:
        print(f"===== Thread [{thread_name}]  Executed {len(executed_ids)} blocks =====")

        involved_files = {}
        for block_id in executed_ids:
            if block_id in block_map:
                involved_files[block_map[block_id].normalized_path] = True

        if not involved_files:
            print("  (No files involved for this thread, skipping)")
            return

        safe_dir_name = BlockPruner.sanitize_dir_name(thread_name)

        for normalized_file in involved_files:
            line_to_block_id = file_block_index.get(normalized_file)
            if line_to_block_id is None:
                continue

            unexecuted_lines = {}
            executed_line_to_id = {}
            for line, block_id in line_to_block_id.items():
                if block_id in executed_ids:
                    executed_line_to_id[line] = block_id
                else:
                    unexecuted_lines[line] = True

            src_file = resolved_paths.get(normalized_file)
            if src_file is None:
                sys.stderr.write(f"  [Skip] Source file not found: {normalized_file}\n")
                continue

            success, pruned_count, output_code = BlockPruner.call_php_ast_processor(src_file, unexecuted_lines)
            if not success:
                sys.stderr.write(f"  [Skip] AST Processing failed for {os.path.basename(src_file)}\n")
                continue

            matching_source_dir = BlockPruner.find_matching_source_dir(src_file, source_dirs)
            relative_path_base = base_ref_dir if base_ref_dir is not None else matching_source_dir
            relative_path = BlockPruner.get_relative_path(relative_path_base, src_file)

            out_file = os.path.join(output_dir, safe_dir_name, relative_path)
            out_dir = os.path.dirname(out_file)
            os.makedirs(out_dir, exist_ok=True)

            with open(out_file, 'w', encoding='utf-8', errors='ignore') as f:
                f.write(output_code + "\n")

            cleared_blocks = len(unexecuted_lines)
            print(f"  {os.path.basename(src_file):<55}  Cleared {cleared_blocks:>3} unexecuted blocks", end="")

            if pruned_count != cleared_blocks:
                print(f"  ⚠ AST matched {pruned_count}/{cleared_blocks}", end="")
            print()

    @staticmethod
    def call_php_ast_processor(src_file: str, unexecuted_lines: Dict[int, bool]) -> tuple:
        """
        通过临时 PHP 脚本调用 php-parser 进行 AST 裁剪，保证与原 PHP 逻辑 100% 一致。
        """

        unexecuted_json = json.dumps(list(unexecuted_lines.keys()))

        php_code = f"""<?php
require_once __DIR__ . '/vendor/autoload.php';
use PhpParser\\ParserFactory;
use PhpParser\\PrettyPrinter\\Standard as PrettyPrinter;
use PhpParser\\Node;
use PhpParser\\Comment;

$srcFile = {repr(src_file)};
$unexecutedLines = array_fill_keys(json_decode({repr(unexecuted_json)}, true), true);

$code = file_get_contents($srcFile);
$parser = (new ParserFactory())->createForNewestSupportedVersion();
try {{
    $ast = $parser->parse($code);
}} catch (\\Exception $ex) {{
    echo json_encode(["success" => false, "error" => $ex->getMessage()]);
    exit(1);
}}

function walkAstWithDepth($nodes, int $depth, callable $callback): void {{
    if (!is_array($nodes)) {{
        if ($nodes instanceof Node) {{
            $nodes = [$nodes];
        }} else {{
            return;
        }}
    }}
    foreach ($nodes as $node) {{
        if (!($node instanceof Node)) continue;
        $callback($node, $depth);
        foreach ($node->getSubNodeNames() as $name) {{
            $subNode = $node->{{$name}};
            if ($subNode instanceof Node) {{
                walkAstWithDepth([$subNode], $depth + 1, $callback);
            }} elseif (is_array($subNode)) {{
                walkAstWithDepth($subNode, $depth + 1, $callback);
            }}
        }}
    }}
}}

function isBlockNode(Node $node): bool {{
    return property_exists($node, 'stmts') && is_array($node->stmts);
}}

// 1. 添加 line 注释
walkAstWithDepth($ast, 0, function (Node $node) {{
    $isAnyFunction = $node instanceof Node\\Stmt\\Function_
        || $node instanceof Node\\Stmt\\ClassMethod
        || $node instanceof Node\\Expr\\Closure
        || $node instanceof Node\\Expr\\ArrowFunction;

    if ($isAnyFunction) {{
        $startLine = $node->getStartLine();
        if ($startLine >= 0) {{
            $commentText = " line: {{$startLine}} ";
            $newComment = new Comment("//{{$commentText}}");

            if ($node instanceof Node\\Expr\\ArrowFunction) {{
                $expr = $node->expr;
                if ($expr instanceof Node) {{
                    $existingComments = $expr->getAttribute('comments', []);
                    $hasLineComment = false;
                    foreach ($existingComments as $comment) {{
                        if (trim($comment->getText()) === "line: {{$startLine}}" || trim($comment->getText()) === "// line: {{$startLine}}") {{
                            $hasLineComment = true;
                            break;
                        }}
                    }}
                    if (!$hasLineComment) {{
                        array_unshift($existingComments, $newComment);
                        $expr->setAttribute('comments', $existingComments);
                    }}
                }}
            }} elseif (property_exists($node, 'stmts') && is_array($node->stmts)) {{
                if (empty($node->stmts)) {{
                    $nop = new Node\\Stmt\\Nop();
                    $nop->setAttribute('comments', [$newComment]);
                    $node->stmts = [$nop];
                }} else {{
                    $firstStmt = $node->stmts[0];
                    $existingComments = $firstStmt->getAttribute('comments', []);
                    $hasLineComment = false;
                    foreach ($existingComments as $comment) {{
                        if (trim($comment->getText()) === "line: {{$startLine}}" || trim($comment->getText()) === "// line: {{$startLine}}") {{
                            $hasLineComment = true;
                            break;
                        }}
                    }}
                    if (!$hasLineComment) {{
                        array_unshift($existingComments, $newComment);
                        $firstStmt->setAttribute('comments', $existingComments);
                    }}
                }}
            }}
        }}
    }}
}});

$prunedCount = 0;
if (!empty($unexecutedLines)) {{
    $unexecutedBlocks = [];
    walkAstWithDepth($ast, 0, function (Node $node, int $depth) use ($unexecutedLines, &$unexecutedBlocks) {{
        if (!isBlockNode($node)) return;
        $startLine = $node->getStartLine();
        if ($startLine < 0) return;

        $hasExecutedDescendant = false;
        walkAstWithDepth($node, 0, function (Node $subNode) use ($unexecutedLines, &$hasExecutedDescendant, $node) {{
            if ($subNode === $node) return;
            if (isBlockNode($subNode)) {{
                $subStartLine = $subNode->getStartLine();
                if ($subStartLine >= 0 && !isset($unexecutedLines[$subStartLine])) {{
                    $hasExecutedDescendant = true;
                }}
            }}
        }});

        if (isset($unexecutedLines[$startLine]) && !$hasExecutedDescendant) {{
            $node->setAttribute('_pruner_depth', $depth);
            $unexecutedBlocks[] = $node;
        }}
    }});

    usort($unexecutedBlocks, function (Node $a, Node $b) {{
        $depthA = $a->getAttribute('_pruner_depth', 0);
        $depthB = $b->getAttribute('_pruner_depth', 0);
        return $depthB - $depthA;
    }});

    foreach ($unexecutedBlocks as $block) {{
        if (property_exists($block, 'stmts') && is_array($block->stmts)) {{
            $block->stmts = [];
        }}
        $prunedCount++;
    }}
}}

$printer = new PrettyPrinter();
$newCode = $printer->prettyPrintFile($ast);

echo json_encode([
    "success" => true,
    "prunedCount" => $prunedCount,
    "code" => $newCode
]);
"""
        try:

            process = subprocess.Popen(
                ['php'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )
            stdout, stderr = process.communicate(input=php_code)
            if process.returncode != 0 or not stdout.strip():
                return False, 0, ""

            result = json.loads(stdout.strip())
            if result.get("success"):
                return True, result.get("prunedCount", 0), result.get("code", "")
        except Exception as e:
            sys.stderr.write(f"  [Error] Failed to run PHP parser: {str(e)}\n")

        return False, 0, ""

    @staticmethod
    def find_matching_source_dir(src_file: str, source_dirs: List[str]) -> str:
        normalized = BlockPruner.normalize_path(os.path.realpath(src_file) if os.path.exists(src_file) else src_file)
        for sd in source_dirs:
            normalized_sd = BlockPruner.normalize_path(sd)
            if normalized.startswith(normalized_sd):
                return sd

        best = source_dirs[0]
        best_score = -1
        for sd in source_dirs:
            score = BlockPruner.common_suffix_length(normalized, BlockPruner.normalize_path(sd))
            if score > best_score:
                best_score = score
                best = sd
        return best

    @staticmethod
    def parse_comment_mapping(file_path: str) -> Dict[int, BlockLocation]:
        mapping = {}
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            sys.stderr.write(f"[Error] Cannot read mapping file: {file_path}\n")
            sys.exit(1)

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            eq_idx = line.find('=')
            if eq_idx == -1:
                continue

            id_part = line[:eq_idx].strip()
            path_and_line = line[eq_idx + 1:].strip()

            last_colon = path_and_line.rfind(':')
            if last_colon <= 0:
                continue

            try:
                block_id = int(id_part)
            except ValueError:
                sys.stderr.write(f"[Warning] Unable to parse mapping line: {line}\n")
                continue

            file_path_part = path_and_line[:last_colon].strip()
            try:
                start_line = int(path_and_line[last_colon + 1:].strip())
            except ValueError:
                sys.stderr.write(f"[Warning] Unable to parse mapping line: {line}\n")
                continue

            mapping[block_id] = BlockLocation(BlockPruner.normalize_path(file_path_part), start_line)

        return mapping

    @staticmethod
    def parse_instrument_log(file_path: str) -> Dict[str, Dict[int, bool]]:
        result = {}
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            sys.stderr.write(f"[Error] Cannot read log file: {file_path}\n")
            sys.exit(1)

        current_thread = None

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            match = re.match(r'^\[(.+?)\]', line)
            if match:
                current_thread = match.group(1)
                if current_thread not in result:
                    result[current_thread] = {}
            elif current_thread is not None:
                parts = line.split('->')
                for part in parts:
                    part = part.strip()
                    if part:
                        try:
                            block_id = int(part)
                            result[current_thread][block_id] = True
                        except ValueError:
                            pass
        return result

    @staticmethod
    def build_file_block_index(block_map: Dict[int, BlockLocation]) -> Dict[str, Dict[int, int]]:
        index = {}
        for block_id, loc in block_map.items():
            if loc.normalized_path not in index:
                index[loc.normalized_path] = {}
            index[loc.normalized_path][loc.start_line] = block_id
        return index

    @staticmethod
    def resolve_source_files(normalized_paths: List[str], source_dirs: List[str]) -> Dict[str, str]:
        resolved = {}
        name_index = {}
        for source_dir in source_dirs:
            if not os.path.isdir(source_dir):
                sys.stderr.write(f"[Warning] Source directory does not exist or is not a directory: {source_dir}\n")
                continue
            BlockPruner.index_directory(source_dir, name_index)

        for np in normalized_paths:
            found = BlockPruner.try_resolve_direct(np)
            if found is None:
                for source_dir in source_dirs:
                    found = BlockPruner.try_resolve_by_marker(np, source_dir)
                    if found is not None:
                        break
            if found is None:
                found = BlockPruner.try_resolve_by_name(np, name_index)

            if found is not None:
                resolved[np] = found
            else:
                sys.stderr.write(f"[Warning] Unable to locate source file: {np}\n")

        return resolved

    @staticmethod
    def index_directory(directory: str, name_index: Dict[str, List[str]]) -> None:
        for root, _, files in os.walk(directory):
            for file in files:
                if file.lower().endswith('.php'):
                    abs_path = os.path.realpath(os.path.join(root, file))
                    if file not in name_index:
                        name_index[file] = []
                    name_index[file].append(abs_path)

    @staticmethod
    def try_resolve_direct(normalized_path: str) -> Optional[str]:
        os_path = normalized_path.replace('/', os.sep)
        if os.path.isfile(os_path):
            return os.path.realpath(os_path)
        return None

    @staticmethod
    def try_resolve_by_marker(normalized_path: str, source_dir: str) -> Optional[str]:
        markers = ['src/', 'app/', 'lib/', 'includes/', 'modules/']
        for marker in markers:
            idx = normalized_path.find(marker)
            if idx != -1:
                relative = normalized_path[idx + len(marker):]
                candidate = os.path.join(source_dir, relative.replace('/', os.sep))
                if os.path.isfile(candidate):
                    return os.path.realpath(candidate)

                with_marker = normalized_path[idx:]
                candidate2 = os.path.join(source_dir, with_marker.replace('/', os.sep))
                if os.path.isfile(candidate2):
                    return os.path.realpath(candidate2)
        return None

    @staticmethod
    def try_resolve_by_name(normalized_path: str, name_index: Dict[str, List[str]]) -> Optional[str]:
        last_slash = normalized_path.rfind('/')
        file_name = normalized_path[last_slash + 1:] if last_slash != -1 else normalized_path

        candidates = name_index.get(file_name, [])
        if len(candidates) == 1:
            return candidates[0]

        if len(candidates) > 1:
            best = None
            best_score = -1
            for c in candidates:
                score = BlockPruner.common_suffix_length(normalized_path, BlockPruner.normalize_path(c))
                if score > best_score:
                    best_score = score
                    best = c
            return best
        return None

    @staticmethod
    def normalize_path(path: str) -> str:
        return path.replace('\\', '/')

    @staticmethod
    def common_suffix_length(a: str, b: str) -> int:
        i = len(a) - 1
        j = len(b) - 1
        count = 0
        while i >= 0 and j >= 0 and a[i].lower() == b[j].lower():
            i -= 1
            j -= 1
            count += 1
        return count

    @staticmethod
    def sanitize_dir_name(name: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_\-.]', '_', name)

    @staticmethod
    def get_relative_path(base_dir: str, file_path: str) -> str:
        base = BlockPruner.normalize_path(os.path.realpath(base_dir) if os.path.exists(base_dir) else base_dir)
        file = BlockPruner.normalize_path(os.path.realpath(file_path) if os.path.exists(file_path) else file_path)

        if file.startswith(base):
            relative = file[len(base):].lstrip('/')
            return relative.replace('/', os.sep)
        return os.path.basename(file_path)

if __name__ == '__main__':
    BlockPruner.main(sys.argv[1:])