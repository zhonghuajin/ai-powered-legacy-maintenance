<?php

require __DIR__ . '/../vendor/autoload.php';

use PhpParser\Error;
use PhpParser\Node;
use PhpParser\NodeTraverser;
use PhpParser\NodeVisitorAbstract;
use PhpParser\ParserFactory;
use PhpParser\PrettyPrinter;

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

class MethodRangeVisitor extends NodeVisitorAbstract {
    private $namespace = '';
    private $classStack = [];
    private $ranges = [];

    private $nodeStack = [];

    private $closureNames = [];

    public function enterNode(Node $node) {

        if ($node instanceof Node\Expr\Closure) {
            $this->closureNames[spl_object_id($node)] = $this->computeClosureName();
        }

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

        $this->nodeStack[] = $node;
        return null;
    }

    public function leaveNode(Node $node) {

        array_pop($this->nodeStack);

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
                'name'  => $fullName . '@' . $node->getStartLine(),
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
                'name'  => $fullName . '@' . $node->getStartLine(),
                'start' => $node->getStartLine(),
                'end'   => $node->getEndLine(),
            ];
        } elseif ($node instanceof Node\Expr\Closure) {
            $base = $this->closureNames[spl_object_id($node)] ?? 'closure';
            $this->ranges[] = [
                'name'  => $base . '@' . $node->getStartLine(),
                'start' => $node->getStartLine(),
                'end'   => $node->getEndLine(),
            ];
        }
        return null;
    }

    private function computeClosureName(): string {
        $n = count($this->nodeStack);
        $parent = $n >= 1 ? $this->nodeStack[$n - 1] : null;
        $grand  = $n >= 2 ? $this->nodeStack[$n - 2] : null;

        if ($parent instanceof Node\Expr\Assign) {
            $var = $parent->var;
            if ($var instanceof Node\Expr\Variable && is_string($var->name)) {
                return $var->name;
            }
            if ($var instanceof Node\Expr\PropertyFetch && $var->name instanceof Node\Identifier) {
                return $var->name->toString();
            }
            if ($var instanceof Node\Expr\StaticPropertyFetch && $var->name instanceof Node\VarLikeIdentifier) {
                return $var->name->toString();
            }
        }

        if ($parent instanceof Node\Arg) {
            $callee = 'callback';
            if ($grand instanceof Node\Expr\FuncCall && $grand->name instanceof Node\Name) {
                $callee = $grand->name->toString();
            } elseif ($grand instanceof Node\Expr\MethodCall && $grand->name instanceof Node\Identifier) {
                $callee = $grand->name->toString();
            } elseif ($grand instanceof Node\Expr\StaticCall && $grand->name instanceof Node\Identifier) {
                $callee = $grand->name->toString();
            }
            return $callee . '$cb';
        }

        return 'closure';
    }

    public function getRanges(): array {
        return $this->ranges;
    }
}

class InstrumentationPipeline {
    private $mappingFile;
    private $rangeFile;
    private $signatureFile;
    private $isIncremental;

    private $oldCommentMap = [];

    private const ORIGINAL_COMMENT_PATTERN = '/^(\s*)\/\/\s*(.+\.php:\d+)\s*$/m';

    private const MAPPED_COMMENT_PATTERN   = '/^(\s*)\/\/\s*INST#(\d+)\s*$/m';

    public function __construct(bool $isIncremental, string $mappingFile, string $rangeFile, string $signatureFile) {
        $this->isIncremental = $isIncremental;
        $this->mappingFile   = $mappingFile;
        $this->rangeFile     = $rangeFile;
        $this->signatureFile = $signatureFile;
    }

    private function getIncrementalPath(string $filePath): string {
        $dir = dirname($filePath);
        $filename = pathinfo($filePath, PATHINFO_FILENAME);
        $ext = pathinfo($filePath, PATHINFO_EXTENSION);
        return ($dir !== '.' ? $dir . DIRECTORY_SEPARATOR : '') . $filename . '.incremental.' . $ext;
    }

    public function run(array $targets) {

        if ($this->isIncremental && (!file_exists($this->mappingFile) || !file_exists($this->rangeFile) || !file_exists($this->signatureFile))) {
            echo "Warning: mapping, range or signature file not found, falling back to full mode.\n";
            $this->isIncremental = false;
        }

        if ($this->isIncremental && file_exists($this->mappingFile)) {
            $this->oldCommentMap = $this->loadRawMapping($this->mappingFile);
        }

        $mode = $this->isIncremental ? "Incremental" : "Full";
        echo "=== PHP Instrumentation Pipeline ({$mode} mode) ===\n";

        $files = $this->collectPhpFiles($targets);
        if (empty($files)) {
            die("No PHP files found.\n");
        }

        echo ">> Step: Code Instrumentation & Range Collection\n";
        $newRanges = $this->instrumentFiles($files);

        echo ">> Step: Updating Method Ranges\n";
        $this->updateMethodRanges($files, $newRanges);

        echo ">> Step: Encoding Mapping\n";
        $this->encodeMapping($files);

        echo ">> Step: Generating Block to Signature Mapping\n";
        $this->generateBlockSignatures($files);

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

                $rangeTraverser = new NodeTraverser();
                $rangeVisitor = new MethodRangeVisitor();
                $rangeTraverser->addVisitor($rangeVisitor);
                $rangeTraverser->traverse($ast);
                $allRanges[$file] = $rangeVisitor->getRanges();

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

    private function updateMethodRanges(array $files, array $newRanges) {
        $targetRanges = [];

        foreach ($newRanges as $file => $ranges) {
            foreach ($ranges as $range) {
                $targetRanges[] = [
                    'file'  => $file,
                    'name'  => $range['name'],
                    'start' => $range['start'],
                    'end'   => $range['end']
                ];
            }
        }

        usort($targetRanges, function ($a, $b) {
            $fileCmp = strcmp($a['file'], $b['file']);
            if ($fileCmp !== 0) {
                return $fileCmp;
            }
            return $a['start'] <=> $b['start'];
        });

        if ($this->isIncremental) {
            $outputFile = $this->getIncrementalPath($this->rangeFile);
            $this->writeRangeFile($outputFile, $targetRanges);
            echo "   Incremental method ranges saved to {$outputFile} (Total: " . count($targetRanges) . " entries)\n";
        } else {
            $this->writeRangeFile($this->rangeFile, $targetRanges);
            echo "   Method ranges saved to {$this->rangeFile} (Total: " . count($targetRanges) . " entries)\n";
        }
    }

    private function writeRangeFile(string $filePath, array $ranges): void {
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

        $dir = dirname($filePath);
        if ($dir !== '' && !is_dir($dir)) {
            mkdir($dir, 0777, true);
        }
        file_put_contents($filePath, implode("\n", $lines) . "\n");
    }

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

    private function generateBlockSignatures(array $files) {
        $blockToSignature = [];

        if ($this->isIncremental) {
            $mappingToLoad = $this->getIncrementalPath($this->mappingFile);
            $rangesToLoad  = $this->getIncrementalPath($this->rangeFile);
        } else {
            $mappingToLoad = $this->mappingFile;
            $rangesToLoad  = $this->rangeFile;
        }

        $commentMap = $this->loadRawMapping($mappingToLoad);
        $ranges = $this->loadRawRanges($rangesToLoad);

        $rangesByFile = [];
        foreach ($ranges as $range) {
            $rangesByFile[$range['file']][] = $range;
        }

        foreach ($commentMap as $id => $comment) {
            $filePath = $this->extractFilePathFromComment($comment);
            if ($filePath === null) {
                continue;
            }

            $line = $this->extractLineFromComment($comment);
            if ($line === null) {
                continue;
            }

            $matchedSignature = '[Global]';
            if (isset($rangesByFile[$filePath])) {

                $best = null;
                foreach ($rangesByFile[$filePath] as $range) {
                    if ($line >= $range['start'] && $line <= $range['end']) {
                        if ($best === null
                            || $range['start'] > $best['start']
                            || ($range['start'] === $best['start'] && $range['end'] < $best['end'])) {
                            $best = $range;
                        }
                    }
                }
                if ($best !== null) {
                    $matchedSignature = $best['name'];
                }
            }
            $blockToSignature[$id] = $matchedSignature;
        }

        ksort($blockToSignature);
        if ($this->isIncremental) {
            $outputFile = $this->getIncrementalPath($this->signatureFile);
            $this->writeSignatureFile($outputFile, $blockToSignature);
            echo "   Incremental block signatures saved to {$outputFile} (Total: " . count($blockToSignature) . " entries)\n";
        } else {
            $this->writeSignatureFile($this->signatureFile, $blockToSignature);
            echo "   Block signatures saved to {$this->signatureFile} (Total: " . count($blockToSignature) . " entries)\n";
        }
    }

    private function writeSignatureFile(string $filePath, array $signatures): void {
        $lines   = [];
        $lines[] = "# ================================================";
        $lines[] = "# Block ID -> Method Signature Mapping Table";
        $lines[] = "# Generation Time: " . date('Y-m-d H:i:s');
        $lines[] = "# Total Entries: " . count($signatures);
        $lines[] = "# ================================================";
        $lines[] = "# Format: Block ID = Method Signature";
        $lines[] = "# Note: This mapping needs to be regenerated after source code modifications and re-instrumentation.";
        $lines[] = "";

        foreach ($signatures as $id => $sig) {
            $lines[] = "{$id} = {$sig}";
        }

        $dir = dirname($filePath);
        if ($dir !== '' && !is_dir($dir)) {
            mkdir($dir, 0777, true);
        }
        file_put_contents($filePath, implode("\n", $lines) . "\n");
    }

    private function loadRawSignatures(string $signatureFile): array {
        $result = [];
        $lines  = @file($signatureFile, FILE_IGNORE_NEW_LINES);
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

    private function extractLineFromComment(string $comment): ?int {
        $lastColon = strrpos($comment, ':');
        if ($lastColon === false || $lastColon === 0) {
            return null;
        }
        $afterColon = substr($comment, $lastColon + 1);
        return (int) $afterColon;
    }

    private function encodeMapping(array $files) {
        $nextId = 1;

        if ($this->isIncremental && file_exists($this->mappingFile)) {
            $existingMap = $this->loadRawMapping($this->mappingFile);
            if (!empty($existingMap)) {
                $nextId = max(array_keys($existingMap)) + 1;
            }
        }

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

        $this->sortCommentsByPathAndLine($newComments);

        $incrementalIdToComment = [];
        $commentToId = [];
        foreach ($newComments as $comment) {
            $incrementalIdToComment[$nextId]  = $comment;
            $commentToId[$comment] = $nextId;
            $nextId++;
        }

        if (empty($incrementalIdToComment)) {
            echo "   No new instrumentation points found.\n";
            return;
        }

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

        ksort($incrementalIdToComment);
        if ($this->isIncremental) {
            $outputFile = $this->getIncrementalPath($this->mappingFile);
            $this->writeMappingFile($outputFile, $incrementalIdToComment);
            echo "   Incremental mapping saved to {$outputFile} (Total: " . count($incrementalIdToComment) . ")\n";
        } else {
            $this->writeMappingFile($this->mappingFile, $incrementalIdToComment);
            echo "   Mapping saved to {$this->mappingFile} (Total: " . count($incrementalIdToComment) . ")\n";
        }
    }

    private function writeMappingFile(string $filePath, array $idToComment): void {
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

        $dir = dirname($filePath);
        if ($dir !== '' && !is_dir($dir)) {
            mkdir($dir, 0777, true);
        }
        file_put_contents($filePath, implode("\n", $lines) . "\n");
    }

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

if (php_sapi_name() === 'cli') {
    $options     = getopt("", ["incremental", "mapping:", "range:", "signature:"]);
    $incremental = isset($options['incremental']);
    $mappingFile = $options['mapping'] ?? 'block-line-mapping.txt';
    $rangeFile   = $options['range'] ?? 'method-range.txt';
    $signatureFile = $options['signature'] ?? 'block-signature.txt';

    if (!preg_match('#^(/|[A-Za-z]:[\\\\/])#', $mappingFile)) {
        $mappingFile = getcwd() . DIRECTORY_SEPARATOR . $mappingFile;
    }
    if (!preg_match('#^(/|[A-Za-z]:[\\\\/])#', $rangeFile)) {
        $rangeFile = getcwd() . DIRECTORY_SEPARATOR . $rangeFile;
    }
    if (!preg_match('#^(/|[A-Za-z]:[\\\\/])#', $signatureFile)) {
        $signatureFile = getcwd() . DIRECTORY_SEPARATOR . $signatureFile;
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
        if ($arg === '--mapping' || $arg === '--range' || $arg === '--signature') {
            $skipNext = true;
            continue;
        }
        if (strpos($arg, '--mapping=') === 0 || strpos($arg, '--range=') === 0 || strpos($arg, '--signature=') === 0) {
            continue;
        }

        $targets[] = $arg;
    }

    if (empty($targets)) {
        die("Usage: php InstrumentationPipeline.php [--incremental] [--mapping mappingFile] [--range rangeFile] [--signature signatureFile] <target1> [target2 ...]\n");
    }

    $pipeline = new InstrumentationPipeline($incremental, $mappingFile, $rangeFile, $signatureFile);
    $pipeline->run($targets);
}