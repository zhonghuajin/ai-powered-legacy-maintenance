<?php
declare(strict_types=1);

namespace App\Instrumentor\Data\Structuring;

use PhpParser\ParserFactory;
use PhpParser\Node;
use PhpParser\Node\Stmt\ClassMethod;
use PhpParser\Node\Stmt\Function_;
use PhpParser\Node\Expr\MethodCall;
use PhpParser\Node\Expr\StaticCall;
use PhpParser\Node\Expr\FuncCall;
use PhpParser\NodeTraverser;
use PhpParser\NodeVisitorAbstract;

class MethodNode
{
    public string $signature;
    public string $className;
    public string $methodName;
    public int $paramCount;
    public string $sourceCode;
    public ?string $filePath;
    public int $startLine;

    public array $calls = [];

    public function __construct(
        string $signature,
        string $className,
        string $methodName,
        int $paramCount,
        string $sourceCode,
        ?string $filePath,
        int $startLine
    ) {
        $this->signature = $signature;
        $this->className = $className;
        $this->methodName = $methodName;
        $this->paramCount = $paramCount;
        $this->sourceCode = $sourceCode;
        $this->filePath = $filePath;
        $this->startLine = $startLine;
    }
}

class MethodCallInfo
{
    public ?string $scope;
    public string $name;
    public int $argCount;

    public function __construct(?string $scope, string $name, int $argCount)
    {
        $this->scope = $scope;
        $this->name = $name;
        $this->argCount = $argCount;
    }
}

class MethodCollectorVisitor extends NodeVisitorAbstract
{
    private string $namespace = '';
    private array $classStack = [];

    public array $methods = [];
    private string $filePath;
    private string $fileContent;

    public function __construct(string $filePath, string $fileContent)
    {
        $this->filePath = $filePath;
        $this->fileContent = $fileContent;
    }

    private function getOriginalLine(Node $node): int
    {
        $comments = $node->getComments();
        if (!empty($comments)) {
            foreach ($comments as $comment) {
                if (preg_match('/line:\s*(\d+)/', $comment->getText(), $matches)) {
                    return (int)$matches[1];
                }
            }
        }
        return $node->getStartLine();
    }

    public function enterNode(Node $node)
    {
        if ($node instanceof Node\Stmt\Namespace_) {
            $this->namespace = $node->name ? $node->name->toString() : '';
        }
        elseif (
            $node instanceof Node\Stmt\Class_ ||
            $node instanceof Node\Stmt\Interface_ ||
            $node instanceof Node\Stmt\Trait_
        ) {
            $className = $node->name ? $node->name->toString() : 'anonymous';
            $this->classStack[] = $className;
        }

        if ($node instanceof ClassMethod || $node instanceof Function_) {
            if ($this->isEmptyMethod($node)) {
                return null;
            }

            $methodName = $node->name->toString();

            if (strcasecmp($methodName, '__construct') === 0 || strcasecmp($methodName, '__destruct') === 0) {
                return null;
            }

            $paramCount = count($node->params);

            $startLine = $this->getOriginalLine($node);

            $startFilePos = $node->getStartFilePos();
            $endFilePos = $node->getEndFilePos();
            $sourceCode = '';
            if ($startFilePos !== -1 && $endFilePos !== -1) {
                $sourceCode = substr($this->fileContent, $startFilePos, $endFilePos - $startFilePos + 1);
            }

            if ($node instanceof Function_) {
                $fullName = $this->namespace ? $this->namespace . '\\' . $methodName : $methodName;

                $signature = $fullName . '@' . $startLine;
                $className = '<global>';
            } else {
                $currentClass = end($this->classStack) ?: '';
                if ($currentClass) {
                    $fullClassName = $this->namespace ? $this->namespace . '\\' . $currentClass : $currentClass;

                    $signature = $fullClassName . '::' . $methodName . '@' . $startLine;
                    $className = $fullClassName;
                } else {
                    $signature = $methodName . '@' . $startLine;
                    $className = '';
                }
            }

            $nodeObj = new MethodNode($signature, $className, $methodName, $paramCount, $sourceCode, $this->filePath, $startLine);

            $callsInMethod = [];
            $this->collectCalls($node, $callsInMethod);
            $nodeObj->calls = $callsInMethod;

            $this->methods[$signature] = $nodeObj;
        }
        return null;
    }

    public function leaveNode(Node $node)
    {
        if ($node instanceof Node\Stmt\Namespace_) {
            $this->namespace = '';
        } elseif (
            $node instanceof Node\Stmt\Class_ ||
            $node instanceof Node\Stmt\Interface_ ||
            $node instanceof Node\Stmt\Trait_
        ) {
            array_pop($this->classStack);
        }
        return null;
    }

    private function isEmptyMethod(Node $node): bool
    {
        if (!isset($node->stmts) || $node->stmts === null) {
            return true;
        }
        return count($node->stmts) === 0;
    }

    private function collectCalls(Node $parentNode, array &$calls): void
    {
        $traverser = new NodeTraverser();
        $visitor = new class($calls) extends NodeVisitorAbstract {
            private array $callsRef;
            public function __construct(array &$callsRef) {
                $this->callsRef = &$callsRef;
            }
            public function enterNode(Node $node) {

                if ($node instanceof ClassMethod || $node instanceof Function_) {
                    return NodeTraverser::DONT_TRAVERSE_CHILDREN;
                }

                if ($node instanceof MethodCall) {
                    if ($node->name instanceof Node\Identifier) {
                        $scope = null;
                        if ($node->var instanceof Node\Expr\Variable && is_string($node->var->name)) {
                            $scope = $node->var->name;
                        }
                        $this->callsRef[] = new MethodCallInfo($scope, $node->name->toString(), count($node->args));
                    }
                }
                elseif ($node instanceof StaticCall) {
                    if ($node->name instanceof Node\Identifier) {
                        $scope = null;
                        if ($node->class instanceof Node\Name) {
                            $scope = $node->class->toString();
                        }
                        $this->callsRef[] = new MethodCallInfo($scope, $node->name->toString(), count($node->args));
                    }
                }
                elseif ($node instanceof FuncCall) {
                    if ($node->name instanceof Node\Name) {
                        $this->callsRef[] = new MethodCallInfo(null, $node->name->toString(), count($node->args));
                    }
                }
                return null;
            }
        };
        $traverser->addVisitor($visitor);
        $traverser->traverse($parentNode->stmts ?? []);
    }
}

class DataStructuring
{
    public static function run(array $argv): int
    {
        if (count($argv) < 2) {
            fwrite(STDERR, "Usage: php bin/data-structuring.php <pruned_directory_path>\n");
            fwrite(STDERR, "Example: php bin/data-structuring.php ./pruned\n");
            return 1;
        }

        $prunedDirPath = $argv[1];
        $outputFilePath = "final-output-calltree.md";

        if (!is_dir($prunedDirPath)) {
            fwrite(STDERR, "[ERROR] The directory does not exist: {$prunedDirPath}\n");
            return 1;
        }

        $md = "# File-Internal Method Index (Call Tree View)\n\n";
        $md .= "> **Description & Legend:**\n";
        $md .= "> This document lists every function/method extracted via AST analysis, organized as a Call Tree.\n";
        $md .= "> - Indentation represents the file-internal calling hierarchy.\n";
        $md .= "> - Each method is emitted with a signature identical to the instrumentation pipeline (`name@line`, or `Class::method@line`).\n";
        $md .= "> - The line numbers and signatures are mapped back to the **original source code** using the injected comments.\n";
        $md .= "> - `*Calls:*` lists direct call expressions for reference only; it does not affect signature matching.\n\n";

        $threadDirs = glob($prunedDirPath . '/*', GLOB_ONLYDIR);
        if ($threadDirs === false) {
            $threadDirs = [];
        }
        sort($threadDirs);

        $parser = (new ParserFactory())->createForNewestSupportedVersion();
        $order = 0;

        foreach ($threadDirs as $threadPath) {
            $threadName = basename($threadPath);
            echo "Processing thread: {$threadName}\n";

            $md .= "# Thread: " . $threadName . " (Order: " . ($order++) . ")\n\n";

            $phpFiles = self::getPhpFiles($threadPath);

            foreach ($phpFiles as $phpFile) {
                try {
                    $code = file_get_contents($phpFile);
                    if ($code === false) continue;

                    $ast = $parser->parse($code);
                    if ($ast === null) continue;

                    $relativePath = str_replace('\\', '/', substr($phpFile, strlen($prunedDirPath) + 1));
                    $parts = explode('/', $relativePath);
                    if (count($parts) > 1) {
                        array_shift($parts);
                        $relativePath = implode('/', $parts);
                    }

                    $visitor = new MethodCollectorVisitor($relativePath, $code);
                    $traverser = new NodeTraverser();
                    $traverser->addVisitor($visitor);
                    $traverser->traverse($ast);

                    if (empty($visitor->methods)) {
                        continue;
                    }

                    $md .= "## File: `{$relativePath}`\n\n";

                    $md .= self::renderCallTree($visitor->methods);

                } catch (\Throwable $e) {
                    fwrite(STDERR, "Warning: Failed to parse file {$phpFile} : " . $e->getMessage() . "\n");
                }
            }
        }

        file_put_contents($outputFilePath, $md);
        echo "[SUCCESS] Markdown generated at: {$outputFilePath}\n";

        return 0;
    }

    private static function getPhpFiles(string $dir): array
    {
        $files = [];
        $iterator = new \RecursiveIteratorIterator(new \RecursiveDirectoryIterator($dir));
        foreach ($iterator as $file) {
            if ($file->isFile() && $file->getExtension() === 'php') {
                $files[] = $file->getPathname();
            }
        }
        return $files;
    }

    private static function renderCallTree(array $methods): string
    {
        $md = "";

        $calledSignatures = [];
        $adjacencyList = [];

        foreach ($methods as $sig => $node) {
            $adjacencyList[$sig] = [];
            foreach ($node->calls as $call) {

                foreach ($methods as $targetSig => $targetNode) {
                    if ($targetNode->methodName === $call->name) {
                        $isMatch = false;
                        if ($call->scope === null || in_array($call->scope, ['this', 'self', 'static', 'parent'])) {
                            $isMatch = true;
                        } elseif ($call->scope === $targetNode->className || str_ends_with($targetNode->className, '\\' . $call->scope)) {
                            $isMatch = true;
                        }

                        if ($isMatch) {
                            $adjacencyList[$sig][] = $targetSig;
                            $calledSignatures[$targetSig] = true;
                        }
                    }
                }
            }

            $adjacencyList[$sig] = array_unique($adjacencyList[$sig]);
        }

        $rootSignatures = [];
        foreach (array_keys($methods) as $sig) {
            if (!isset($calledSignatures[$sig])) {
                $rootSignatures[] = $sig;
            }
        }

        if (empty($rootSignatures)) {
            $rootSignatures = array_keys($methods);
        }

        $visited = [];
        foreach ($rootSignatures as $rootSig) {
            $md .= self::dfsRender($rootSig, $methods, $adjacencyList, 0, $visited);
        }

        foreach ($methods as $sig => $node) {
            if (!isset($visited[$sig])) {
                $md .= self::dfsRender($sig, $methods, $adjacencyList, 0, $visited);
            }
        }

        return $md;
    }

    private static function dfsRender(string $sig, array $methods, array $adjacencyList, int $depth, array &$visited): string
    {
        if (isset($visited[$sig])) {
            $node = $methods[$sig];
            $indent = str_repeat('    ', $depth);
            return $indent . '- **Method:** `' . $node->signature . "` *(See above)*\n" . $indent . "---\n\n";
        }

        $visited[$sig] = true;
        $node = $methods[$sig];
        $md = self::renderMethod($node, $depth);
        $md .= str_repeat('    ', $depth) . "---\n\n";

        if (isset($adjacencyList[$sig])) {
            foreach ($adjacencyList[$sig] as $childSig) {
                $md .= self::dfsRender($childSig, $methods, $adjacencyList, $depth + 1, $visited);
            }
        }

        return $md;
    }

    private static function renderMethod(MethodNode $node, int $depth = 0): string
    {
        $indent = str_repeat('    ', $depth);

        $md = $indent . '- **Method:** `' . $node->signature . '` (Params: ' . $node->paramCount . ")\n";
        $md .= $indent . '- **File Path:** `' . $node->filePath . "`\n";
        $md .= $indent . '- **Original Line:** `' . $node->startLine . "`\n\n";

        if ($node->sourceCode !== '') {
            $source = trim($node->sourceCode);

            $lines = explode("\n", $source);
            $indentedSource = implode("\n" . $indent, $lines);

            $md .= $indent . "```php\n";
            $md .= $indent . $indentedSource . "\n";
            $md .= $indent . "```\n";
        }

        if (!empty($node->calls)) {
            $md .= "\n" . $indent . "*Calls:*\n";
            foreach ($node->calls as $call) {
                $scopeStr = $call->scope ? $call->scope . '->' : '';

                if ($call->scope !== null && !in_array($call->scope, ['this', 'self', 'parent', 'static'])) {
                    $scopeStr = $call->scope . '::';
                }
                $md .= $indent . '    - `' . $scopeStr . $call->name . '(' . $call->argCount . " args)`\n";
            }
        }

        $md .= "\n";
        return $md;
    }
}