<?php
/**
 * BlockPruner for PHP
 *
 * Prunes unexecuted code blocks from PHP source files based on instrumentation logs.
 *
 * Usage: php BlockPruner.php <Source Directories> <comment-mapping file> <instrument-log file> <Output Directory>
 *
 * Requirements: nikic/php-parser ^5.0 (install via: composer require nikic/php-parser)
 */

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
    /**
     * Entry point.
     */
    public static function main(array $args): void
    {
        if (count($args) < 4) {
            fwrite(STDERR, "Usage: BlockPruner <Source Directories> <comment-mapping file> <instrument-log file> <Output Directory>\n");
            fwrite(STDERR, "\n");
            fwrite(STDERR, "Parameter Description:\n");
            fwrite(STDERR, "  <Source Directories>       PHP source root directories, separated by ';' for multiple paths\n");
            fwrite(STDERR, "                             e.g. \"dir1;dir2;dir3\"\n");
            fwrite(STDERR, "  <comment-mapping>          Instrumentation mapping file (format: ID = filePath:lineNo)\n");
            fwrite(STDERR, "  <instrument-log>           Runtime instrumentation log file\n");
            fwrite(STDERR, "  <Output Directory>         Output root directory for pruned source code\n");
            exit(1);
        }

        // Parse multiple source directories separated by ';'
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

        echo "[BlockPruner] Source Directories:\n";
        foreach ($sourceDirs as $i => $dir) {
            printf("  [%d] %s\n", $i + 1, $dir);
        }
        echo "[BlockPruner] Mapping File: $mappingFile\n";
        echo "[BlockPruner] Log File: $logFile\n";
        echo "[BlockPruner] Output Directory: $outputDir\n\n";

        // Step 1: Parse comment mapping
        $blockMap = self::parseCommentMapping($mappingFile);
        printf("[Step 1] Loaded %d block mappings\n", count($blockMap));

        // Step 2: Parse instrument log
        $threadLogs = self::parseInstrumentLog($logFile);
        printf("[Step 2] Loaded execution logs for %d threads\n", count($threadLogs));

        // Step 3: Build file block index
        $fileBlockIndex = self::buildFileBlockIndex($blockMap);
        printf("[Step 3] Involves %d source files\n", count($fileBlockIndex));

        // Step 4: Resolve source files
        $resolvedPaths = self::resolveSourceFiles(array_keys($fileBlockIndex), $sourceDirs);
        printf("[Step 4] Successfully located %d / %d source files\n",
            count($resolvedPaths), count($fileBlockIndex));

        // Step 5: Prune for each thread
        $totalThreads = count($threadLogs);
        $idx = 0;
        foreach ($threadLogs as $threadName => $executedIds) {
            $idx++;
            printf("\n[%d/%d] ", $idx, $totalThreads);
            self::pruneForThread(
                $threadName, $executedIds, $blockMap, $fileBlockIndex,
                $resolvedPaths, $sourceDirs, $outputDir
            );
        }

        echo "\n[BlockPruner] All processing completed. Output Directory: $outputDir\n";
    }

    // ==================== Pruning Logic ====================

    /**
     * Prune source files for a single thread's execution trace.
     */
    private static function pruneForThread(
        string $threadName,
        array  $executedIds,   // [id => true, ...]
        array  $blockMap,      // [id => BlockLocation, ...]
        array  $fileBlockIndex,// [normalizedPath => [line => blockId, ...], ...]
        array  $resolvedPaths, // [normalizedPath => absolutePath, ...]
        array  $sourceDirs,
        string $outputDir
    ): void {
        printf("===== Thread [%s]  Executed %d blocks =====\n", $threadName, count($executedIds));

        // Determine which files are involved
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

            // Classify blocks into executed/unexecuted
            $unexecutedLines = [];
            $executedLineToId = [];
            foreach ($lineToBlockId as $line => $blockId) {
                if (isset($executedIds[$blockId])) {
                    $executedLineToId[$line] = $blockId;
                } else {
                    $unexecutedLines[$line] = true;
                }
            }

            // Resolve source file path
            $srcFile = $resolvedPaths[$normalizedFile] ?? null;
            if ($srcFile === null) {
                fprintf(STDERR, "  [Skip] Source file not found: %s\n", $normalizedFile);
                continue;
            }

            // Parse PHP source file
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

            // Prune unexecuted blocks
            $prunedCount = self::pruneUnexecutedBlocks($ast, $unexecutedLines, $executedLineToId, $threadName);

            // Write output
            $matchingSourceDir = self::findMatchingSourceDir($srcFile, $sourceDirs);
            $relativePath = self::getRelativePath($matchingSourceDir, $srcFile);
            $outFile = $outputDir . DIRECTORY_SEPARATOR . $safeDirName . DIRECTORY_SEPARATOR . $relativePath;

            $outDir = dirname($outFile);
            if (!is_dir($outDir)) {
                mkdir($outDir, 0777, true);
            }

            $printer = new PrettyPrinter();
            file_put_contents($outFile, $printer->prettyPrintFile($ast) . "\n");

            $totalBlocks = count($lineToBlockId);
            $keptBlocks = count($executedLineToId);
            $clearedBlocks = count($unexecutedLines);
            printf("  %-55s  Kept %3d | Cleared %3d | Total %3d blocks",
                basename($srcFile), $keptBlocks, $clearedBlocks, $totalBlocks);

            if ($prunedCount !== $clearedBlocks) {
                printf("  ⚠ AST matched %d/%d", $prunedCount, $clearedBlocks);
            }
            echo "\n";
        }
    }

    /**
     * Find which source directory the given source file resides under.
     */
    private static function findMatchingSourceDir(string $srcFile, array $sourceDirs): string
    {
        $normalized = self::normalizePath(realpath($srcFile) ?: $srcFile);
        foreach ($sourceDirs as $sd) {
            $normalizedSd = self::normalizePath($sd);
            if (str_starts_with($normalized, $normalizedSd)) {
                return $sd;
            }
        }
        // Fallback: pick directory with longest common suffix
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

    // ==================== AST Pruning ====================

    /**
     * Prune unexecuted blocks from the AST.
     *
     * @param array $ast             The top-level AST nodes (modified in place)
     * @param array $unexecutedLines [line => true, ...] lines of unexecuted blocks
     * @param array $executedLineToId [line => blockId, ...] executed blocks
     * @param string $threadName     Thread name for comment annotation
     * @return int Number of blocks actually pruned
     */
    private static function pruneUnexecutedBlocks(
        array  &$ast,
        array  $unexecutedLines,
        array  $executedLineToId,
        string $threadName
    ): int {
        if (empty($unexecutedLines) && empty($executedLineToId)) return 0;

        // Collect all block nodes with their depths
        $unexecutedBlocks = [];

        self::walkAstWithDepth($ast, 0, function (Node $node, int $depth) use (
            $unexecutedLines, $executedLineToId, $threadName, &$unexecutedBlocks
        ) {
            if (!self::isBlockNode($node)) return;

            $startLine = $node->getStartLine();
            if ($startLine < 0) return;

            if (isset($unexecutedLines[$startLine])) {
                $node->setAttribute('_pruner_depth', $depth);
                $unexecutedBlocks[] = $node;
            } elseif (isset($executedLineToId[$startLine])) {
                // Mark executed block with a comment
                $blockId = $executedLineToId[$startLine];
                $commentText = " [Executed Block ID: $blockId, Thread: $threadName] ";
                $comment = new Comment("/* $commentText */");
                $existing = $node->getComments();
                $existing[] = $comment;
                $node->setAttribute('comments', $existing);
            }
        });

        // Sort by depth (deepest first) to handle nested blocks correctly
        usort($unexecutedBlocks, function (Node $a, Node $b) {
            $depthA = $a->getAttribute('_pruner_depth', 0);
            $depthB = $b->getAttribute('_pruner_depth', 0);
            return $depthB - $depthA; // Descending
        });

        $executedLineSet = $executedLineToId; // [line => blockId] - keys are executed lines

        $prunedCount = 0;
        foreach ($unexecutedBlocks as $block) {
            if (!self::containsExecutedBlock($block, $executedLineSet)) {
                // Clear all statements in this block
                self::clearBlockStmts($block);
            } else {
                // Remove only non-executed child statements
                self::removeNonExecutedChildren($block, $executedLineSet);
            }
            $prunedCount++;
        }

        return $prunedCount;
    }

    /**
     * Check if a node represents a "block" (has a stmts array property).
     */
    private static function isBlockNode(Node $node): bool
    {
        return property_exists($node, 'stmts') && is_array($node->stmts);
    }

    /**
     * Clear all statements in a block node.
     */
    private static function clearBlockStmts(Node $node): void
    {
        if (property_exists($node, 'stmts') && is_array($node->stmts)) {
            $node->stmts = [];
        }
    }

    /**
     * Remove child statements that don't contain any executed blocks.
     */
    private static function removeNonExecutedChildren(Node $block, array $executedLineSet): void
    {
        if (!property_exists($block, 'stmts') || !is_array($block->stmts)) return;

        $kept = [];
        foreach ($block->stmts as $stmt) {
            if ($stmt instanceof Node && self::containsExecutedBlock($stmt, $executedLineSet)) {
                $kept[] = $stmt;
            }
        }
        $block->stmts = $kept;
    }

    /**
     * Check if a node or any of its descendants contains an executed block.
     */
    private static function containsExecutedBlock(Node $node, array $executedLineSet): bool
    {
        // Check self
        if (self::isBlockNode($node)) {
            $startLine = $node->getStartLine();
            if ($startLine >= 0 && isset($executedLineSet[$startLine])) {
                return true;
            }
        }

        // Check descendants recursively
        foreach ($node->getSubNodeNames() as $name) {
            $subNode = $node->{$name};
            if ($subNode instanceof Node) {
                if (self::containsExecutedBlock($subNode, $executedLineSet)) {
                    return true;
                }
            } elseif (is_array($subNode)) {
                foreach ($subNode as $item) {
                    if ($item instanceof Node && self::containsExecutedBlock($item, $executedLineSet)) {
                        return true;
                    }
                }
            }
        }

        return false;
    }

    /**
     * Walk the AST recursively, tracking depth, and invoke callback for each node.
     */
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

    // ==================== File Parsing ====================

    /**
     * Parse the comment mapping file.
     * Format: ID = filePath:lineNo
     *
     * @return array<int, BlockLocation>
     */
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

            // Find last colon to separate path from line number
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

    /**
     * Parse the instrumentation log file.
     * Format:
     *   [ThreadName] ...
     *   id1->id2->id3->...
     *
     * @return array<string, array<int, true>>  threadName => [blockId => true, ...]
     */
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

            if (preg_match('/^\[(.+?)]/', $line, $matches)) {
                $currentThread = $matches[1];
                if (!isset($result[$currentThread])) {
                    $result[$currentThread] = [];
                }
            } elseif ($currentThread !== null) {
                // Parse block IDs separated by '->'
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

    // ==================== Index Building ====================

    /**
     * Build an index: normalizedFilePath => [startLine => blockId, ...]
     *
     * @param array<int, BlockLocation> $blockMap
     * @return array<string, array<int, int>>
     */
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

    // ==================== File Resolution ====================

    /**
     * Resolve normalized file paths to actual filesystem paths.
     *
     * @param array $normalizedPaths
     * @param array $sourceDirs
     * @return array<string, string>  normalizedPath => absolutePath
     */
    private static function resolveSourceFiles(array $normalizedPaths, array $sourceDirs): array
    {
        $resolved = [];

        // Build a name index: fileName => [absolutePath, ...]
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

    /**
     * Recursively index a directory, collecting all .php files by filename.
     */
    private static function indexDirectory(string $dir, array &$nameIndex): void
    {
        $iterator = new RecursiveIteratorIterator(
            new RecursiveDirectoryIterator($dir, RecursiveDirectoryIterator::SKIP_DOTS),
            RecursiveIteratorIterator::LEAVES_ONLY
        );

        foreach ($iterator as $file) {
            /** @var SplFileInfo $file */
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

    /**
     * Try to resolve the path directly.
     */
    private static function tryResolveDirect(string $normalizedPath): ?string
    {
        $osPath = str_replace('/', DIRECTORY_SEPARATOR, $normalizedPath);
        if (is_file($osPath)) {
            return realpath($osPath) ?: $osPath;
        }
        return null;
    }

    /**
     * Try to resolve by known directory markers (e.g., src/, app/, lib/).
     */
    private static function tryResolveByMarker(string $normalizedPath, string $sourceDir): ?string
    {
        $markers = ['src/', 'app/', 'lib/', 'includes/', 'modules/'];
        foreach ($markers as $marker) {
            $idx = strpos($normalizedPath, $marker);
            if ($idx !== false) {
                // Try without marker prefix
                $relative = substr($normalizedPath, $idx + strlen($marker));
                $candidate = $sourceDir . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $relative);
                if (is_file($candidate)) {
                    return realpath($candidate) ?: $candidate;
                }

                // Try with marker
                $withMarker = substr($normalizedPath, $idx);
                $candidate2 = $sourceDir . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $withMarker);
                if (is_file($candidate2)) {
                    return realpath($candidate2) ?: $candidate2;
                }
            }
        }
        return null;
    }

    /**
     * Try to resolve by filename matching.
     */
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

    // ==================== Utility Methods ====================

    /**
     * Normalize a file path to use forward slashes.
     */
    private static function normalizePath(string $path): string
    {
        return str_replace('\\', '/', $path);
    }

    /**
     * Calculate the common suffix length of two strings (case-insensitive).
     */
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

    /**
     * Sanitize a string for use as a directory name.
     */
    private static function sanitizeDirName(string $name): string
    {
        return preg_replace('/[^a-zA-Z0-9_\-.]/', '_', $name);
    }

    /**
     * Get the relative path from a base directory to a file.
     */
    private static function getRelativePath(string $baseDir, string $filePath): string
    {
        $base = self::normalizePath(realpath($baseDir) ?: $baseDir);
        $file = self::normalizePath(realpath($filePath) ?: $filePath);

        if (str_starts_with($file, $base)) {
            $relative = ltrim(substr($file, strlen($base)), '/');
            return str_replace('/', DIRECTORY_SEPARATOR, $relative);
        }

        // Fallback: just use the filename
        return basename($filePath);
    }
}

// ==================== Script Entry Point ====================

// Remove the script name from argv
$args = array_slice($argv, 1);
BlockPruner::main($args);