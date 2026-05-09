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

    /**
     * Handle file root scope (top-level statements without namespace)
     */
    public function beforeTraverse(array $nodes): ?array {
        $hasNamespace = false;
        foreach ($nodes as $node) {
            if ($node instanceof Node\Stmt\Namespace_) {
                $hasNamespace = true;
                break;
            }
        }

        if (!$hasNamespace && !empty($nodes)) {
            $line = $nodes[0]->getStartLine();
            if ($line > 0) {
                $nop = $this->createInstrumentationNop($line);
                array_unshift($nodes, $nop);
                return $nodes;
            }
        }

        return null;
    }

    public function leaveNode(Node $node) {
        // 1. Only instrument executable blocks
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

        // 2. Ensure the node has stmts and is an array
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
 * Core Pipeline Class
 */
class InstrumentationPipeline {
    private $mappingFile;
    private $isIncremental;

    public function __construct(bool $isIncremental, string $mappingFile) {
        $this->isIncremental = $isIncremental;
        $this->mappingFile = $mappingFile;
    }

    public function run(array $targets) {
        echo "=== PHP Instrumentation Pipeline ===\n";

        $files = $this->collectPhpFiles($targets);
        if (empty($files)) {
            die("No PHP files found.\n");
        }

        // Step 1: Instrument (AST parse and comment injection)
        echo ">> Step: Code Instrumentation\n";
        $this->instrumentFiles($files);

        // Step 2: Encoding (generate ID mapping)
        echo ">> Step: Encoding Mapping\n";
        $this->encodeMapping($files);

        // Step 3: Activation (replace comments with function calls)
        echo ">> Step: Activation\n";
        $this->activate($files);

        echo "=== Pipeline complete ===\n";
    }

    private function instrumentFiles(array $files) {
        $parser = (new ParserFactory)->createForNewestSupportedVersion();
        $printer = new PrettyPrinter\Standard();

        foreach ($files as $file) {
            $code = file_get_contents($file);
            try {
                $ast = $parser->parse($code);
                $traverser = new NodeTraverser();
                $traverser->addVisitor(new BlockInstrumentorVisitor($file));
                
                $modifiedAst = $traverser->traverse($ast);
                $newCode = $printer->prettyPrintFile($modifiedAst);
                
                file_put_contents($file, $newCode);
            } catch (Error $error) {
                echo "Parse error in {$file}: {$error->getMessage()}\n";
            }
        }
    }

    private function encodeMapping(array $files) {
        $idToComment = [];
        $commentToId = [];
        $nextId = 1;

        $pattern = '/^(\s*)\/\/\s*(.+\.php:\d+)\s*$/m';

        foreach ($files as $file) {
            $content = file_get_contents($file);
            if (preg_match_all($pattern, $content, $matches, PREG_SET_ORDER)) {
                foreach ($matches as $match) {
                    $originalComment = $match[2];
                    if (!isset($commentToId[$originalComment])) {
                        $commentToId[$originalComment] = $nextId;
                        $idToComment[$nextId] = $originalComment;
                        $nextId++;
                    }
                }
            }
        }

        // Replace original comments with INST#ID in source
        foreach ($files as $file) {
            $content = file_get_contents($file);
            $newContent = preg_replace_callback($pattern, function($matches) use ($commentToId) {
                $indent = $matches[1];
                $originalComment = $matches[2];
                $id = $commentToId[$originalComment] ?? null;
                if ($id) {
                    return $indent . "// INST#" . $id;
                }
                return $matches[0];
            }, $content);
            file_put_contents($file, $newContent);
        }

        // Save mapping file
        $mappingContent = "# Instrumentation Mapping\n";
        foreach ($idToComment as $id => $comment) {
            $mappingContent .= "{$id} = {$comment}\n";
        }
        file_put_contents($this->mappingFile, $mappingContent);
        echo "   Mapping saved to {$this->mappingFile} (Total: " . count($idToComment) . ")\n";
    }

    private function activate(array $files) {
        $pattern = '/^(\s*)\/\/\s*INST#(\d+)\s*$/m';
        $callTemplate = "%s\\App\\Instrumentation\\InstrumentLog::staining(%d);";

        $totalActivated = 0;
        foreach ($files as $file) {
            $content = file_get_contents($file);
            $fileActivatedCount = 0;
            
            $newContent = preg_replace_callback($pattern, function($matches) use ($callTemplate, &$totalActivated, &$fileActivatedCount) {
                $indent = $matches[1];
                $id = $matches[2];
                $totalActivated++;
                $fileActivatedCount++;
                return sprintf($callTemplate, $indent, $id);
            }, $content);
            
            if ($fileActivatedCount > 0) {
                file_put_contents($file, $newContent);
            }
        }
        echo "   Activated {$totalActivated} instrumentation points.\n";
    }

    private function collectPhpFiles(array $targets): array {
        $files = [];
        foreach ($targets as $target) {
            $target = realpath($target);
            if (is_file($target) && pathinfo($target, PATHINFO_EXTENSION) === 'php') {
                $files[] = $target;
            } elseif (is_dir($target)) {
                $iterator = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($target));
                foreach ($iterator as $fileInfo) {
                    if ($fileInfo->isFile() && $fileInfo->getExtension() === 'php') {
                        $files[] = $fileInfo->getRealPath();
                    }
                }
            }
        }
        return array_unique($files);
    }
}

// CLI entry point
if (php_sapi_name() === 'cli') {
    $options = getopt("m:", ["incremental"]);
    $incremental = isset($options['incremental']);
    $mappingFile = $options['m'] ?? 'comment-mapping.txt';

    $targets = [];
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
        if ($arg === '-m') {
            $skipNext = true;
            continue;
        }
        $targets[] = $arg;
    }

    if (empty($targets)) {
        die("Usage: php InstrumentorPipeline.php [--incremental] [-m mappingFile] <target1> [target2 ...]\n");
    }

    $pipeline = new InstrumentationPipeline($incremental, $mappingFile);
    $pipeline->run($targets);
}