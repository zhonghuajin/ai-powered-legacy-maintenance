<?php

require __DIR__ . '/../vendor/autoload.php';

use PhpParser\Error;
use PhpParser\Node;
use PhpParser\NodeTraverser;
use PhpParser\NodeVisitorAbstract;
use PhpParser\ParserFactory;
use PhpParser\PrettyPrinter;

/**
 * AST Traverser: Insert instrumentation comment at the beginning of executable blocks
 */
class BlockInstrumentorVisitor extends NodeVisitorAbstract {
    private $filePath;

    public function __construct(string $filePath) {
        $this->filePath = $filePath;
    }

    public function beforeTraverse(array $nodes): ?array {
        $hasNamespace = false;
        $safeInsertIndex = 0;

        foreach ($nodes as $index => $node) {
            if ($node instanceof Node\Stmt\Namespace_) {
                $hasNamespace = true;
                break;
            }

            if ($node instanceof Node\Stmt\Declare_) {
                $safeInsertIndex = $index + 1;
            }
        }

        if (!$hasNamespace && !empty($nodes)) {

            if (isset($nodes[$safeInsertIndex])) {
                $line = $nodes[$safeInsertIndex]->getStartLine();
                if ($line > 0) {
                    $nop = $this->createInstrumentationNop($line);

                    array_splice($nodes, $safeInsertIndex, 0, [$nop]);
                    return $nodes;
                }
            }
        }

        return null;
    }

    public function leaveNode(Node $node) {
        $isExecutableBlock =
            $node instanceof Node\Stmt\Function_ ||
            $node instanceof Node\Stmt\ClassMethod ||
            $node instanceof Node\Expr\Closure ||
            $node instanceof Node\Stmt\If_ ||
            $node instanceof Node\Stmt\ElseIf_ ||
            $node instanceof Node\Stmt\Else_ ||
            $node instanceof Node\Stmt\For_ ||
            $node instanceof Node\Stmt\Foreach_ ||
            $node instanceof Node\Stmt\While_ ||
            $node instanceof Node\Stmt\Do_ ||
            $node instanceof Node\Stmt\TryCatch ||
            $node instanceof Node\Stmt\Catch_ ||
            $node instanceof Node\Stmt\Finally_ ||
            $node instanceof Node\Stmt\Case_;

        if (!$isExecutableBlock) {
            return null;
        }

        if (isset($node->stmts) && is_array($node->stmts)) {
            $line = $node->getStartLine();
            if ($line > 0) {
                $nop = $this->createInstrumentationNop($line);
                array_unshift($node->stmts, $nop);
            }
        }

        return null;
    }

    private function createInstrumentationNop(int $line): Node\Stmt\Nop {
        $commentText = "// " . $this->filePath . ":" . $line;
        $nop = new Node\Stmt\Nop();
        $nop->setAttribute('comments', [new \PhpParser\Comment($commentText)]);
        return $nop;
    }
}

/**
 * AST Traverser: Collect line ranges of all functions and class methods
 */
class MethodRangeVisitor extends NodeVisitorAbstract {
    private $namespace = '';
    private $classStack = [];
    private $ranges = [];

    public function enterNode(Node $node) {
        if ($node instanceof Node\Stmt\Namespace_) {
            $this->namespace = $node->name ? $node->name->toString() : '';
        } elseif (
            $node instanceof Node\Stmt\Class_ || 
            $node instanceof Node\Stmt\Interface_ || 
            $node instanceof Node\Stmt\Trait_
        ) {
            $className = $node->name ? $node->name->toString() : 'anonymous';
            $this->classStack[] = $className;
        }
        return null;
    }

    public function leaveNode(Node $node) {
        if ($node instanceof Node\Stmt\Namespace_) {
            $this->namespace = '';
        } elseif (
            $node instanceof Node\Stmt\Class_ || 
            $node instanceof Node\Stmt\Interface_ || 
            $node instanceof Node\Stmt\Trait_
        ) {
            array_pop($this->classStack);
        }

        if ($node instanceof Node\Stmt\Function_) {
            $name = $node->name->toString();
            $fullName = $this->namespace ? "{$this->namespace}\\{$name}" : $name;
            $this->ranges[] = [
                'name'  => $fullName,
                'start' => $node->getStartLine(),
                'end'   => $node->getEndLine(),
            ];
        } elseif ($node instanceof Node\Stmt\ClassMethod) {
            $className = end($this->classStack) ?: '';
            $methodName = $node->name->toString();
            if ($className) {
                $fullClassName = $this->namespace ? "{$this->namespace}\\{$className}" : $className;
                $fullName = "{$fullClassName}::{$methodName}";
            } else {
                $fullName = $methodName;
            }
            $this->ranges[] = [
                'name'  => $fullName,
                'start' => $node->getStartLine(),
                'end'   => $node->getEndLine(),
            ];
        }
        return null;
    }

    public function getRanges(): array {
        return $this->ranges;
    }
}

/**
 * Core Pipeline Class
 */
class InstrumentationPipeline {
    private $mappingFile;
    private $rangeFile;
    private $isIncremental;

    /** Match original comments injected during instrumentation, e.g. // /abs/path/foo.php:123 */
    private const ORIGINAL_COMMENT_PATTERN = '/^(\s*)\/\/\s*(.+\.php:\d+)\s*$/m';
    /** Match already-mapped comments, e.g. // INST#42 */
    private const MAPPED_COMMENT_PATTERN   = '/^(\s*)\/\/\s*INST#(\d+)\s*$/m';

    public function __construct(bool $isIncremental, string $mappingFile, string $rangeFile) {
        $this->isIncremental = $isIncremental;
        $this->mappingFile   = $mappingFile;
        $this->rangeFile     = $rangeFile;
    }

    public function run(array $targets) {
        // Fall back to full mode if mapping file or range file is missing in incremental mode
        if ($this->isIncremental && (!file_exists($this->mappingFile) || !file_exists($this->rangeFile))) {
            echo "Warning: mapping or range file not found, falling back to full mode.\n";
            $this->isIncremental = false;
        }

        $mode = $this->isIncremental ? "Incremental" : "Full";
        echo "=== PHP Instrumentation Pipeline ({$mode} mode) ===\n";

        $files = $this->collectPhpFiles($targets);
        if (empty($files)) {
            die("No PHP files found.\n");
        }

        // Step 1: Instrument (AST parse, collect ranges, and comment injection)
        echo ">> Step: Code Instrumentation & Range Collection\n";
        $newRanges = $this->instrumentFiles($files);

        // Step 1.5: Update Method Ranges File
        echo ">> Step: Updating Method Ranges\n";
        $this->updateMethodRanges($files, $newRanges);

        // Step 2: Encoding (generate / update ID mapping)
        echo ">> Step: Encoding Mapping\n";
        $this->encodeMapping($files);

        // Step 3: Activation (replace comments with function calls)
        echo ">> Step: Activation\n";
        $this->activate($files);

        echo "=== Pipeline complete ===\n";
    }

    private function instrumentFiles(array $files): array {
        $parser  = (new ParserFactory)->createForNewestSupportedVersion();
        $printer = new PrettyPrinter\Standard();
        $allRanges = [];

        foreach ($files as $file) {
            $code = file_get_contents($file);
            try {
                $ast = $parser->parse($code);

                // 1. Collect original method ranges before modifying AST
                $rangeTraverser = new NodeTraverser();
                $rangeVisitor = new MethodRangeVisitor();
                $rangeTraverser->addVisitor($rangeVisitor);
                $rangeTraverser->traverse($ast);
                $allRanges[$file] = $rangeVisitor->getRanges();

                // 2. Perform instrumentation comment injection
                $traverser = new NodeTraverser();
                $traverser->addVisitor(new BlockInstrumentorVisitor($file));

                $modifiedAst = $traverser->traverse($ast);
                $newCode     = $printer->prettyPrintFile($modifiedAst);

                file_put_contents($file, $newCode);
            } catch (Error $error) {
                echo "Parse error in {$file}: {$error->getMessage()}\n";
            }
        }

        return $allRanges;
    }

    /**
     * Update the method-range.txt file.
     * Supports incremental mode by preserving ranges from non-target files.
     */
    private function updateMethodRanges(array $files, array $newRanges) {
        $mergedRanges = [];

        // ---- Step 1. Preserve non-target entries when incremental ----
        if ($this->isIncremental && file_exists($this->rangeFile)) {
            $existingRanges = $this->loadRawRanges($this->rangeFile);
            $targetFilePaths = array_fill_keys($files, true);

            foreach ($existingRanges as $entry) {
                if (isset($targetFilePaths[$entry['file']])) {
                    // Belongs to a re-instrumented target file: discard
                    continue;
                }
                $mergedRanges[] = $entry;
            }
        }

        // ---- Step 2. Merge newly collected ranges ----
        foreach ($newRanges as $file => $ranges) {
            foreach ($ranges as $range) {
                $mergedRanges[] = [
                    'file'  => $file,
                    'name'  => $range['name'],
                    'start' => $range['start'],
                    'end'   => $range['end']
                ];
            }
        }

        // ---- Step 3. Sort ranges by file path and start line for stability ----
        usort($mergedRanges, function ($a, $b) {
            $fileCmp = strcmp($a['file'], $b['file']);
            if ($fileCmp !== 0) {
                return $fileCmp;
            }
            return $a['start'] <=> $b['start'];
        });

        // ---- Step 4. Persist range file ----
        $this->writeRangeFile($mergedRanges);
        echo "   Method ranges saved to {$this->rangeFile} (Total: " . count($mergedRanges) . " entries)\n";
    }

    private function writeRangeFile(array $ranges): void {
        $lines   = [];
        $lines[] = "# ================================================";
        $lines[] = "# Method Line Range Mapping Table";
        $lines[] = "# Generation Time: " . date('Y-m-d H:i:s');
        $lines[] = "# Total Entries: " . count($ranges);
        $lines[] = "# ================================================";
        $lines[] = "# Format: File Absolute Path | Method Name = Start Line-End Line";
        $lines[] = "# Note: This mapping needs to be regenerated after source code modifications and re-instrumentation.";
        $lines[] = "";

        foreach ($ranges as $entry) {
            $lines[] = "{$entry['file']} | {$entry['name']} = {$entry['start']}-{$entry['end']}";
        }

        $dir = dirname($this->rangeFile);
        if ($dir !== '' && !is_dir($dir)) {
            mkdir($dir, 0777, true);
        }
        file_put_contents($this->rangeFile, implode("\n", $lines) . "\n");
    }

    /**
     * Read an existing range file.
     */
    private function loadRawRanges(string $rangeFile): array {
        $result = [];
        $lines  = @file($rangeFile, FILE_IGNORE_NEW_LINES);
        if ($lines === false) {
            return $result;
        }

        foreach ($lines as $line) {
            $trimmed = trim($line);
            if ($trimmed === '' || $trimmed[0] === '#') {
                continue;
            }
            // Format: File Absolute Path | Method Name = Start Line-End Line
            if (preg_match('/^(.+?)\s*\|\s*(.+?)\s*=\s*(\d+)-(\d+)$/', $trimmed, $m)) {
                $result[] = [
                    'file'  => trim($m[1]),
                    'name'  => trim($m[2]),
                    'start' => (int) $m[3],
                    'end'   => (int) $m[4]
                ];
            }
        }
        return $result;
    }

    /**
     * Build (or update) the comment -> ID mapping.
     */
    private function encodeMapping(array $files) {
        $idToComment = [];
        $commentToId = [];

        // ---- Step 1. Preserve non-target entries when incremental ----
        if ($this->isIncremental && file_exists($this->mappingFile)) {
            $existingMap = $this->loadRawMapping($this->mappingFile);

            // Build a set of target file absolute paths for fast lookup
            $targetFilePaths = [];
            foreach ($files as $file) {
                $targetFilePaths[$file] = true;
            }

            foreach ($existingMap as $id => $comment) {
                $filePath = $this->extractFilePathFromComment($comment);
                if ($filePath !== null && isset($targetFilePaths[$filePath])) {
                    // Belongs to a re-instrumented target file: discard
                    continue;
                }
                // Preserve this entry with its original ID
                $idToComment[$id]      = $comment;
                $commentToId[$comment] = $id;
            }
        }

        // ---- Step 2. Scan original comments from target files ----
        $newComments = [];
        $seen        = [];
        foreach ($files as $file) {
            $content = file_get_contents($file);
            if (preg_match_all(self::ORIGINAL_COMMENT_PATTERN, $content, $matches, PREG_SET_ORDER)) {
                foreach ($matches as $match) {
                    $comment = $match[2];
                    if (!isset($seen[$comment])) {
                        $seen[$comment]  = true;
                        $newComments[]   = $comment;
                    }
                }
            }
        }

        // Sort newly scanned comments by (path, line) for stable IDs
        $this->sortCommentsByPathAndLine($newComments);

        // ---- Step 3. Allocate IDs for new comments ----
        $nextId = empty($idToComment) ? 1 : (max(array_keys($idToComment)) + 1);
        foreach ($newComments as $comment) {
            if (!isset($commentToId[$comment])) {
                $idToComment[$nextId]  = $comment;
                $commentToId[$comment] = $nextId;
                $nextId++;
            }
        }

        if (empty($idToComment)) {
            echo "   No instrumentation points found.\n";
            return;
        }

        // ---- Step 4. Replace // path:line with // INST#ID in target sources ----
        foreach ($files as $file) {
            $content = file_get_contents($file);
            $newContent = preg_replace_callback(
                self::ORIGINAL_COMMENT_PATTERN,
                function ($matches) use ($commentToId) {
                    $indent          = $matches[1];
                    $originalComment = $matches[2];
                    $id              = $commentToId[$originalComment] ?? null;
                    if ($id !== null) {
                        return $indent . "// INST#" . $id;
                    }
                    return $matches[0];
                },
                $content
            );
            if ($newContent !== $content) {
                file_put_contents($file, $newContent);
            }
        }

        // ---- Step 5. Persist mapping file (sorted by ID) ----
        ksort($idToComment);
        $this->writeMappingFile($idToComment);
        echo "   Mapping saved to {$this->mappingFile} (Total: " . count($idToComment) . ")\n";
    }

    private function writeMappingFile(array $idToComment): void {
        $lines   = [];
        $lines[] = "# ================================================";
        $lines[] = "# Instrumentation Comment -> Integer ID Mapping Table";
        $lines[] = "# Generation Time: " . date('Y-m-d H:i:s');
        $lines[] = "# Total Entries: " . count($idToComment);
        $lines[] = "# ================================================";
        $lines[] = "# Format: Integer ID = File Absolute Path:Code Block Start Line Number";
        $lines[] = "# Note: This mapping needs to be regenerated after source code modifications and re-instrumentation.";
        $lines[] = "";

        foreach ($idToComment as $id => $comment) {
            $lines[] = "{$id} = {$comment}";
        }

        $dir = dirname($this->mappingFile);
        if ($dir !== '' && !is_dir($dir)) {
            mkdir($dir, 0777, true);
        }
        file_put_contents($this->mappingFile, implode("\n", $lines) . "\n");
    }

    /**
     * Read an existing mapping file. Lines starting with '#' or empty lines
     * are ignored. Each entry has the form "<id> = <comment>".
     */
    private function loadRawMapping(string $mappingFile): array {
        $result = [];
        $lines  = @file($mappingFile, FILE_IGNORE_NEW_LINES);
        if ($lines === false) {
            return $result;
        }

        foreach ($lines as $line) {
            $trimmed = trim($line);
            if ($trimmed === '' || $trimmed[0] === '#') {
                continue;
            }
            if (preg_match('/^(\d+)\s*=\s*(.+)$/', $trimmed, $m)) {
                $result[(int) $m[1]] = trim($m[2]);
            }
        }
        return $result;
    }

    /**
     * Extract the file path part from a comment like "/abs/path/foo.php:123".
     * Returns null if the suffix after the last colon is not numeric.
     */
    private function extractFilePathFromComment(string $comment): ?string {
        $lastColon = strrpos($comment, ':');
        if ($lastColon === false || $lastColon === 0) {
            return null;
        }
        $afterColon = substr($comment, $lastColon + 1);
        if ($afterColon === '' || !ctype_digit($afterColon)) {
            return null;
        }
        return substr($comment, 0, $lastColon);
    }

    private function sortCommentsByPathAndLine(array &$comments): void {
        usort($comments, function ($a, $b) {
            $colA = strrpos($a, ':');
            $colB = strrpos($b, ':');
            $pathA = substr($a, 0, $colA);
            $pathB = substr($b, 0, $colB);
            $cmp = strcmp($pathA, $pathB);
            if ($cmp !== 0) return $cmp;
            $lineA = (int) substr($a, $colA + 1);
            $lineB = (int) substr($b, $colB + 1);
            return $lineA <=> $lineB;
        });
    }

    private function activate(array $files) {
        $callTemplate = "%s\\App\\Instrumentation\\InstrumentLog::staining(%d);";

        $totalActivated = 0;
        foreach ($files as $file) {
            $content            = file_get_contents($file);
            $fileActivatedCount = 0;

            $newContent = preg_replace_callback(
                self::MAPPED_COMMENT_PATTERN,
                function ($matches) use ($callTemplate, &$totalActivated, &$fileActivatedCount) {
                    $indent = $matches[1];
                    $id     = $matches[2];
                    $totalActivated++;
                    $fileActivatedCount++;
                    return sprintf($callTemplate, $indent, $id);
                },
                $content
            );

            if ($fileActivatedCount > 0) {
                file_put_contents($file, $newContent);
            }
        }
        echo "   Activated {$totalActivated} instrumentation points.\n";
    }

    private function collectPhpFiles(array $targets): array {
        $files = [];
        foreach ($targets as $target) {
            $real = realpath($target);
            if ($real === false) continue;

            if (is_file($real) && pathinfo($real, PATHINFO_EXTENSION) === 'php') {
                $files[] = $real;
            } elseif (is_dir($real)) {
                $iterator = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($real));
                foreach ($iterator as $fileInfo) {
                    if ($fileInfo->isFile() && $fileInfo->getExtension() === 'php') {
                        $files[] = $fileInfo->getRealPath();
                    }
                }
            }
        }
        return array_values(array_unique($files));
    }
}

// CLI entry point
if (php_sapi_name() === 'cli') {
    $options     = getopt("", ["incremental", "mapping:", "range:"]);
    $incremental = isset($options['incremental']);
    $mappingFile = $options['mapping'] ?? 'block-line-mapping.txt';
    $rangeFile   = $options['range'] ?? 'method-range.txt';

    if (!preg_match('#^(/|[A-Za-z]:[\\\\/])#', $mappingFile)) {
        $mappingFile = getcwd() . DIRECTORY_SEPARATOR . $mappingFile;
    }
    if (!preg_match('#^(/|[A-Za-z]:[\\\\/])#', $rangeFile)) {
        $rangeFile = getcwd() . DIRECTORY_SEPARATOR . $rangeFile;
    }

    $targets  = [];
    $skipNext = false;
    for ($i = 1; $i < count($argv); $i++) {
        if ($skipNext) {
            $skipNext = false;
            continue;
        }
        $arg = $argv[$i];

        if ($arg === '--incremental') {
            continue;
        }
        if ($arg === '--mapping' || $arg === '--range') {
            $skipNext = true;
            continue;
        }
        if (strpos($arg, '--mapping=') === 0 || strpos($arg, '--range=') === 0) {
            continue;
        }

        $targets[] = $arg;
    }

    if (empty($targets)) {
        die("Usage: php InstrumentationPipeline.php [--incremental] [--mapping mappingFile] [--range rangeFile] <target1> [target2 ...]\n");
    }

    $pipeline = new InstrumentationPipeline($incremental, $mappingFile, $rangeFile);
    $pipeline->run($targets);
}