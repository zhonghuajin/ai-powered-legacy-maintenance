<?php

require_once __DIR__ . '/../vendor/autoload.php';

use PhpParser\ParserFactory;
use PhpParser\PrettyPrinter\Standard as PrettyPrinter;
use PhpParser\Node;
use PhpParser\Comment;

class BlockLocation
{
    public string $normalizedPath;
    public int $startLine;

    public function __construct(string $normalizedPath, int $startLine)
    {
        $this->normalizedPath = $normalizedPath;
        $this->startLine = $startLine;
    }
}

class BlockPruner
{

    public static function main(array $args): void
    {
        if (count($args) < 4) {
            fwrite(STDERR, "Usage: BlockPruner <Source Directories> <block-line-mapping file> <instrument-log file> <Output Directory> [<Base Reference Directory>]\n");
            fwrite(STDERR, "\n");
            fwrite(STDERR, "Parameter Description:\n");
            fwrite(STDERR, "  <Source Directories>       PHP source root directories, separated by ';' for multiple paths\n");
            fwrite(STDERR, "                             e.g. \"dir1;dir2;dir3\"\n");
            fwrite(STDERR, "  <block-line-mapping>          Instrumentation mapping file (format: ID = filePath:lineNo)\n");
            fwrite(STDERR, "  <instrument-log>           Runtime instrumentation log file\n");
            fwrite(STDERR, "  <Output Directory>         Output root directory for pruned source code\n");
            fwrite(STDERR, "  [Base Reference Directory] (Optional) Base directory to preserve relative directory structures\n");
            fwrite(STDERR, "                             e.g. \"C:\\Work\\HKT\\OPIOS\\a_this_folder_for_merge\\broadband-backend\"\n");
            exit(1);
        }

        $sourceDirs = [];
        foreach (explode(';', $args[0]) as $part) {
            $part = trim($part);
            if (!empty($part)) {
                $resolved = realpath($part);
                $sourceDirs[] = $resolved !== false ? $resolved : $part;
            }
        }
        if (empty($sourceDirs)) {
            fwrite(STDERR, "[Error] No valid source directory provided.\n");
            exit(1);
        }

        $mappingFile = $args[1];
        $logFile = $args[2];
        $outputDir = rtrim($args[3], '/\\');
        if (function_exists('realpath') && !is_dir($outputDir)) {
            @mkdir($outputDir, 0777, true);
        }
        $outputDir = realpath($outputDir) ?: $outputDir;

        $baseRefDir = null;
        if (isset($args[4])) {
            $resolvedBase = realpath(trim($args[4]));
            $baseRefDir = $resolvedBase !== false ? $resolvedBase : trim($args[4]);
        }

        echo "[BlockPruner] Source Directories:\n";
        foreach ($sourceDirs as $i => $dir) {
            printf("  [%d] %s\n", $i + 1, $dir);
        }
        echo "[BlockPruner] Mapping File: $mappingFile\n";
        echo "[BlockPruner] Log File: $logFile\n";
        echo "[BlockPruner] Output Directory: $outputDir\n";
        if ($baseRefDir !== null) {
            echo "[BlockPruner] Base Reference Directory: $baseRefDir\n";
        }
        echo "\n";

        $blockMap = self::parseCommentMapping($mappingFile);
        printf("[Step 1] Loaded %d block mappings\n", count($blockMap));

        $threadLogs = self::parseInstrumentLog($logFile);
        printf("[Step 2] Loaded execution logs for %d threads\n", count($threadLogs));

        $fileBlockIndex = self::buildFileBlockIndex($blockMap);
        printf("[Step 3] Involves %d source files\n", count($fileBlockIndex));

        $resolvedPaths = self::resolveSourceFiles(array_keys($fileBlockIndex), $sourceDirs);
        printf("[Step 4] Successfully located %d / %d source files\n",
            count($resolvedPaths), count($fileBlockIndex));

        $totalThreads = count($threadLogs);
        $idx = 0;
        foreach ($threadLogs as $threadName => $executedIds) {
            $idx++;
            printf("\n[%d/%d] ", $idx, $totalThreads);
            self::pruneForThread(
                $threadName, $executedIds, $blockMap, $fileBlockIndex,
                $resolvedPaths, $sourceDirs, $outputDir, $baseRefDir
            );
        }

        echo "\n[BlockPruner] All processing completed. Output Directory: $outputDir\n";
    }

    private static function pruneForThread(
        string $threadName,
        array  $executedIds,
        array  $blockMap,
        array  $fileBlockIndex,
        array  $resolvedPaths,
        array  $sourceDirs,
        string $outputDir,
        ?string $baseRefDir
    ): void {
        printf("===== Thread [%s]  Executed %d blocks =====\n", $threadName, count($executedIds));

        $involvedFiles = [];
        foreach ($executedIds as $id => $_) {
            if (isset($blockMap[$id])) {
                $involvedFiles[$blockMap[$id]->normalizedPath] = true;
            }
        }

        if (empty($involvedFiles)) {
            echo "  (No files involved for this thread, skipping)\n";
            return;
        }

        $safeDirName = self::sanitizeDirName($threadName);

        foreach (array_keys($involvedFiles) as $normalizedFile) {
            $lineToBlockId = $fileBlockIndex[$normalizedFile] ?? null;
            if ($lineToBlockId === null) continue;

            $unexecutedLines = [];
            $executedLineToId = [];
            foreach ($lineToBlockId as $line => $blockId) {
                if (isset($executedIds[$blockId])) {
                    $executedLineToId[$line] = $blockId;
                } else {
                    $unexecutedLines[$line] = true;
                }
            }

            $srcFile = $resolvedPaths[$normalizedFile] ?? null;
            if ($srcFile === null) {
                fprintf(STDERR, "  [Skip] Source file not found: %s\n", $normalizedFile);
                continue;
            }

            $code = file_get_contents($srcFile);
            if ($code === false) {
                fprintf(STDERR, "  [Skip] Cannot read file: %s\n", $srcFile);
                continue;
            }

            $parser = (new ParserFactory())->createForNewestSupportedVersion();
            try {
                $ast = $parser->parse($code);
            } catch (\Exception $ex) {
                fprintf(STDERR, "  [Skip] Parsing failed %s: %s\n", basename($srcFile), $ex->getMessage());
                continue;
            }

            if ($ast === null) {
                fprintf(STDERR, "  [Skip] Parsing returned null for %s\n", basename($srcFile));
                continue;
            }

            $prunedCount = self::pruneUnexecutedBlocks($ast, $unexecutedLines);

            $matchingSourceDir = self::findMatchingSourceDir($srcFile, $sourceDirs);
            $relativePathBase = ($baseRefDir !== null) ? $baseRefDir : $matchingSourceDir;
            $relativePath = self::getRelativePath($relativePathBase, $srcFile);

            $outFile = $outputDir . DIRECTORY_SEPARATOR . $safeDirName . DIRECTORY_SEPARATOR . $relativePath;

            $outDir = dirname($outFile);
            if (!is_dir($outDir)) {
                mkdir($outDir, 0777, true);
            }

            $printer = new PrettyPrinter();
            file_put_contents($outFile, $printer->prettyPrintFile($ast) . "\n");

            $clearedBlocks = count($unexecutedLines);
            printf("  %-55s  Cleared %3d unexecuted blocks", basename($srcFile), $clearedBlocks);

            if ($prunedCount !== $clearedBlocks) {
                printf("  ⚠ AST matched %d/%d", $prunedCount, $clearedBlocks);
            }
            echo "\n";
        }
    }

    private static function findMatchingSourceDir(string $srcFile, array $sourceDirs): string
    {
        $normalized = self::normalizePath(realpath($srcFile) ?: $srcFile);
        foreach ($sourceDirs as $sd) {
            $normalizedSd = self::normalizePath($sd);
            if (str_starts_with($normalized, $normalizedSd)) {
                return $sd;
            }
        }

        $best = $sourceDirs[0];
        $bestScore = -1;
        foreach ($sourceDirs as $sd) {
            $score = self::commonSuffixLength($normalized, self::normalizePath($sd));
            if ($score > $bestScore) {
                $bestScore = $score;
                $best = $sd;
            }
        }
        return $best;
    }

    private static function pruneUnexecutedBlocks(array &$ast, array $unexecutedLines): int
    {
        self::walkAstWithDepth($ast, 0, function (Node $node) {
            $isAnyFunction = $node instanceof Node\Stmt\Function_
                || $node instanceof Node\Stmt\ClassMethod
                || $node instanceof Node\Expr\Closure
                || $node instanceof Node\Expr\ArrowFunction;

            if ($isAnyFunction) {
                $startLine = $node->getStartLine();
                if ($startLine >= 0) {
                    $commentText = " line: {$startLine} ";
                    $newComment = new Comment("//{$commentText}");

                    if ($node instanceof Node\Expr\ArrowFunction) {
                        $expr = $node->expr;
                        if ($expr instanceof Node) {
                            $existingComments = $expr->getAttribute('comments', []);
                            $hasLineComment = false;
                            foreach ($existingComments as $comment) {
                                if (trim($comment->getText()) === "line: {$startLine}" || trim($comment->getText()) === "// line: {$startLine}") {
                                    $hasLineComment = true;
                                    break;
                                }
                            }
                            if (!$hasLineComment) {
                                array_unshift($existingComments, $newComment);
                                $expr->setAttribute('comments', $existingComments);
                            }
                        }
                    }

                    elseif (property_exists($node, 'stmts') && is_array($node->stmts)) {
                        if (empty($node->stmts)) {

                            $nop = new Node\Stmt\Nop();
                            $nop->setAttribute('comments', [$newComment]);
                            $node->stmts = [$nop];
                        } else {

                            $firstStmt = $node->stmts[0];
                            $existingComments = $firstStmt->getAttribute('comments', []);

                            $hasLineComment = false;
                            foreach ($existingComments as $comment) {
                                if (trim($comment->getText()) === "line: {$startLine}" || trim($comment->getText()) === "// line: {$startLine}") {
                                    $hasLineComment = true;
                                    break;
                                }
                            }

                            if (!$hasLineComment) {
                                array_unshift($existingComments, $newComment);
                                $firstStmt->setAttribute('comments', $existingComments);
                            }
                        }
                    }
                }
            }
        });

        if (empty($unexecutedLines)) return 0;

        $unexecutedBlocks = [];

        self::walkAstWithDepth($ast, 0, function (Node $node, int $depth) use (
            $unexecutedLines, &$unexecutedBlocks
        ) {
            if (!self::isBlockNode($node)) return;

            $startLine = $node->getStartLine();
            if ($startLine < 0) return;

            $hasExecutedDescendant = false;
            self::walkAstWithDepth($node, 0, function (Node $subNode) use ($unexecutedLines, &$hasExecutedDescendant, $node) {

                if ($subNode === $node) return;

                if (self::isBlockNode($subNode)) {
                    $subStartLine = $subNode->getStartLine();
                    if ($subStartLine >= 0 && !isset($unexecutedLines[$subStartLine])) {
                        $hasExecutedDescendant = true;
                    }
                }
            });

            if (isset($unexecutedLines[$startLine]) && !$hasExecutedDescendant) {
                $node->setAttribute('_pruner_depth', $depth);
                $unexecutedBlocks[] = $node;
            }
        });

        usort($unexecutedBlocks, function (Node $a, Node $b) {
            $depthA = $a->getAttribute('_pruner_depth', 0);
            $depthB = $b->getAttribute('_pruner_depth', 0);
            return $depthB - $depthA;
        });

        $prunedCount = 0;
        foreach ($unexecutedBlocks as $block) {
            self::clearBlockStmts($block);
            $prunedCount++;
        }

        return $prunedCount;
    }

    private static function isBlockNode(Node $node): bool
    {
        return property_exists($node, 'stmts') && is_array($node->stmts);
    }

    private static function clearBlockStmts(Node $node): void
    {
        if (property_exists($node, 'stmts') && is_array($node->stmts)) {
            $node->stmts = [];
        }
    }

    private static function walkAstWithDepth($nodes, int $depth, callable $callback): void
    {
        if (!is_array($nodes)) {
            if ($nodes instanceof Node) {
                $nodes = [$nodes];
            } else {
                return;
            }
        }

        foreach ($nodes as $node) {
            if (!($node instanceof Node)) continue;

            $callback($node, $depth);

            foreach ($node->getSubNodeNames() as $name) {
                $subNode = $node->{$name};
                if ($subNode instanceof Node) {
                    self::walkAstWithDepth([$subNode], $depth + 1, $callback);
                } elseif (is_array($subNode)) {
                    self::walkAstWithDepth($subNode, $depth + 1, $callback);
                }
            }
        }
    }

    private static function parseCommentMapping(string $file): array
    {
        $map = [];
        $lines = file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
        if ($lines === false) {
            fprintf(STDERR, "[Error] Cannot read mapping file: %s\n", $file);
            exit(1);
        }

        foreach ($lines as $line) {
            $line = trim($line);
            if (empty($line) || $line[0] === '#') continue;

            $eqIdx = strpos($line, '=');
            if ($eqIdx === false) continue;

            $idPart = trim(substr($line, 0, $eqIdx));
            $pathAndLine = trim(substr($line, $eqIdx + 1));

            $lastColon = strrpos($pathAndLine, ':');
            if ($lastColon === false || $lastColon === 0) continue;

            $id = filter_var($idPart, FILTER_VALIDATE_INT);
            if ($id === false) {
                fprintf(STDERR, "[Warning] Unable to parse mapping line: %s\n", $line);
                continue;
            }

            $filePath = trim(substr($pathAndLine, 0, $lastColon));
            $startLine = filter_var(trim(substr($pathAndLine, $lastColon + 1)), FILTER_VALIDATE_INT);
            if ($startLine === false) {
                fprintf(STDERR, "[Warning] Unable to parse mapping line: %s\n", $line);
                continue;
            }

            $map[$id] = new BlockLocation(self::normalizePath($filePath), $startLine);
        }

        return $map;
    }

    private static function parseInstrumentLog(string $file): array
    {
        $result = [];
        $lines = file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
        if ($lines === false) {
            fprintf(STDERR, "[Error] Cannot read log file: %s\n", $file);
            exit(1);
        }

        $currentThread = null;

        foreach ($lines as $line) {
            $line = trim($line);
            if (empty($line) || $line[0] === '#') continue;

            if (preg_match('/^\[(.+?)\]/', $line, $matches)) {
                $currentThread = $matches[1];
                if (!isset($result[$currentThread])) {
                    $result[$currentThread] = [];
                }
            } elseif ($currentThread !== null) {

                $parts = explode('->', $line);
                foreach ($parts as $part) {
                    $part = trim($part);
                    if ($part !== '') {
                        $id = filter_var($part, FILTER_VALIDATE_INT);
                        if ($id !== false) {
                            $result[$currentThread][$id] = true;
                        }
                    }
                }
            }
        }

        return $result;
    }

    private static function buildFileBlockIndex(array $blockMap): array
    {
        $index = [];
        foreach ($blockMap as $id => $loc) {
            if (!isset($index[$loc->normalizedPath])) {
                $index[$loc->normalizedPath] = [];
            }
            $index[$loc->normalizedPath][$loc->startLine] = $id;
        }
        return $index;
    }

    private static function resolveSourceFiles(array $normalizedPaths, array $sourceDirs): array
    {
        $resolved = [];

        $nameIndex = [];
        foreach ($sourceDirs as $sourceDir) {
            if (!is_dir($sourceDir)) {
                fprintf(STDERR, "[Warning] Source directory does not exist or is not a directory: %s\n", $sourceDir);
                continue;
            }
            self::indexDirectory($sourceDir, $nameIndex);
        }

        foreach ($normalizedPaths as $np) {
            $found = self::tryResolveDirect($np);
            if ($found === null) {
                foreach ($sourceDirs as $sourceDir) {
                    $found = self::tryResolveByMarker($np, $sourceDir);
                    if ($found !== null) break;
                }
            }
            if ($found === null) {
                $found = self::tryResolveByName($np, $nameIndex);
            }

            if ($found !== null) {
                $resolved[$np] = $found;
            } else {
                fprintf(STDERR, "[Warning] Unable to locate source file: %s\n", $np);
            }
        }

        return $resolved;
    }

    private static function indexDirectory(string $dir, array &$nameIndex): void
    {
        $iterator = new RecursiveIteratorIterator(
            new RecursiveDirectoryIterator($dir, RecursiveDirectoryIterator::SKIP_DOTS),
            RecursiveIteratorIterator::LEAVES_ONLY
        );

        foreach ($iterator as $file) {

            if ($file->isFile() && strtolower($file->getExtension()) === 'php') {
                $absPath = $file->getRealPath();
                $fileName = $file->getFilename();
                if (!isset($nameIndex[$fileName])) {
                    $nameIndex[$fileName] = [];
                }
                $nameIndex[$fileName][] = $absPath;
            }
        }
    }

    private static function tryResolveDirect(string $normalizedPath): ?string
    {
        $osPath = str_replace('/', DIRECTORY_SEPARATOR, $normalizedPath);
        if (is_file($osPath)) {
            return realpath($osPath) ?: $osPath;
        }
        return null;
    }

    private static function tryResolveByMarker(string $normalizedPath, string $sourceDir): ?string
    {
        $markers = ['src/', 'app/', 'lib/', 'includes/', 'modules/'];
        foreach ($markers as $marker) {
            $idx = strpos($normalizedPath, $marker);
            if ($idx !== false) {

                $relative = substr($normalizedPath, $idx + strlen($marker));
                $candidate = $sourceDir . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $relative);
                if (is_file($candidate)) {
                    return realpath($candidate) ?: $candidate;
                }

                $withMarker = substr($normalizedPath, $idx);
                $candidate2 = $sourceDir . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $withMarker);
                if (is_file($candidate2)) {
                    return realpath($candidate2) ?: $candidate2;
                }
            }
        }
        return null;
    }

    private static function tryResolveByName(string $normalizedPath, array $nameIndex): ?string
    {
        $lastSlash = strrpos($normalizedPath, '/');
        $fileName = ($lastSlash !== false) ? substr($normalizedPath, $lastSlash + 1) : $normalizedPath;

        $candidates = $nameIndex[$fileName] ?? [];

        if (count($candidates) === 1) {
            return $candidates[0];
        }

        if (count($candidates) > 1) {
            $best = null;
            $bestScore = -1;
            foreach ($candidates as $c) {
                $score = self::commonSuffixLength($normalizedPath, self::normalizePath($c));
                if ($score > $bestScore) {
                    $bestScore = $score;
                    $best = $c;
                }
            }
            return $best;
        }

        return null;
    }

    private static function normalizePath(string $path): string
    {
        return str_replace('\\', '/', $path);
    }

    private static function commonSuffixLength(string $a, string $b): int
    {
        $i = strlen($a) - 1;
        $j = strlen($b) - 1;
        $count = 0;
        while ($i >= 0 && $j >= 0 && strtolower($a[$i]) === strtolower($b[$j])) {
            $i--;
            $j--;
            $count++;
        }
        return $count;
    }

    private static function sanitizeDirName(string $name): string
    {
        return preg_replace('/[^a-zA-Z0-9_\-.]/', '_', $name);
    }

    private static function getRelativePath(string $baseDir, string $filePath): string
    {
        $base = self::normalizePath(realpath($baseDir) ?: $baseDir);
        $file = self::normalizePath(realpath($filePath) ?: $filePath);

        if (str_starts_with($file, $base)) {
            $relative = ltrim(substr($file, strlen($base)), '/');
            return str_replace('/', DIRECTORY_SEPARATOR, $relative);
        }

        return basename($filePath);
    }
}

$args = array_slice($argv, 1);
BlockPruner::main($args);