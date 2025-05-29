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

    public array $calls = [];

    public array $externalCalls = [];

    public function __construct(string $signature, string $className, string $methodName, int $paramCount, string $sourceCode, ?string $filePath)
    {
        $this->signature = $signature;
        $this->className = $className;
        $this->methodName = $methodName;
        $this->paramCount = $paramCount;
        $this->sourceCode = $sourceCode;
        $this->filePath = $filePath;
    }

    public function getFullSignature(): string
    {
        return $this->signature;
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
    public array $rawCalls = [];
    private string $filePath;
    private string $fileContent;

    public function __construct(string $filePath, string $fileContent)
    {
        $this->filePath = $filePath;
        $this->fileContent = $fileContent;
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

            $startFilePos = $node->getStartFilePos();
            $endFilePos = $node->getEndFilePos();
            $sourceCode = '';
            if ($startFilePos !== -1 && $endFilePos !== -1) {
                $sourceCode = substr($this->fileContent, $startFilePos, $endFilePos - $startFilePos + 1);
            }

            if ($node instanceof Function_) {
                $fullName = $this->namespace ? "{$this->namespace}\\{$methodName}" : $methodName;
                $className = '<global>';
            } else {
                $currentClass = end($this->classStack) ?: '';
                if ($currentClass) {
                    $fullClassName = $this->namespace ? "{$this->namespace}\\{$currentClass}" : $currentClass;
                    $fullName = "{$fullClassName}::{$methodName}";
                    $className = $fullClassName;
                } else {
                    $fullName = $methodName;
                    $className = '';
                }
            }

            $nodeObj = new MethodNode($fullName, $className, $methodName, $paramCount, $sourceCode, $this->filePath);

            $this->methods[$fullName] = $nodeObj;

            $callsInMethod = [];
            $this->collectCalls($node, $callsInMethod);
            $this->rawCalls[spl_object_hash($nodeObj)] = $callsInMethod;
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

        $md = "# File-Internal Call Trees\n\n";
        $md .= "> **Description & Legend:**\n";
        $md .= "> This document presents precise **intra-file function/method call trees** based on AST analysis.\n";
        $md .= "> - Only explicit calls within the current file/class (such as `\$this->foo()` or `self::bar()`) are expanded in the tree.\n";
        $md .= "> - External calls or calls that cannot be statically determined are listed as `[External/Unknown]` to avoid cross-file misidentification.\n\n";

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

                    $calledNodesHashes = [];
                    foreach ($visitor->methods as $caller) {
                        $hash = spl_object_hash($caller);
                        $calls = $visitor->rawCalls[$hash] ?? [];

                        foreach ($calls as $call) {
                            $callee = self::findMatchingMethodInFile($call, $visitor->methods, $caller->className);
                            if ($callee !== null && $callee !== $caller) {
                                $caller->calls[] = $callee;
                                $calledNodesHashes[spl_object_hash($callee)] = true;
                            } else {
                                $scopeStr = $call->scope ? $call->scope . '->' : '';
                                $caller->externalCalls[] = "{$scopeStr}{$call->name}({$call->argCount} args)";
                            }
                        }
                    }

                    $entryPoints = [];
                    foreach ($visitor->methods as $node) {
                        if (!isset($calledNodesHashes[spl_object_hash($node)])) {
                            $entryPoints[] = $node;
                        }
                    }

                    if (empty($entryPoints)) {
                        $entryPoints = array_values($visitor->methods);
                    }

                    foreach ($entryPoints as $rootNode) {
                        self::renderCallNode($rootNode, $md, 0);
                    }

                    $md .= "\n---\n\n";

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

    private static function findMatchingMethodInFile(MethodCallInfo $call, array $fileMethodMap, string $callerClassName): ?MethodNode
    {
        if (strcasecmp($call->name, '__construct') === 0 || strcasecmp($call->name, '__destruct') === 0) {
            return null;
        }

        if ($call->scope === null || $call->scope === 'this' || $call->scope === 'self' || $call->scope === 'static' || strcasecmp($call->scope, $callerClassName) === 0) {
            $key = $callerClassName . "::" . $call->name;
            if (isset($fileMethodMap[$key])) {
                return $fileMethodMap[$key];
            }

            if ($call->scope === null) {
                $namespacePrefix = '';
                $lastBackslash = strrpos($callerClassName, '\\');
                if ($lastBackslash !== false) {
                    $namespacePrefix = substr($callerClassName, 0, $lastBackslash);
                }

                $globalKey = $namespacePrefix ? "{$namespacePrefix}\\{$call->name}" : $call->name;
                if (isset($fileMethodMap[$globalKey])) {
                    return $fileMethodMap[$globalKey];
                }
            }
        }

        return null;
    }

    private static function renderCallNode(MethodNode $node, string &$md, int $level): void
    {
        $indent = str_repeat("    ", $level);
        $contentIndent = $indent . "    ";

        $md .= $indent . "- **Method:** `" . $node->signature . "` (Params: " . $node->paramCount . ")\n";

        if ($node->sourceCode !== '') {
            $source = trim($node->sourceCode);
            $md .= $contentIndent . "```php\n";
            $lines = explode("\n", $source);
            foreach ($lines as $line) {
                $md .= $contentIndent . $line . "\n";
            }
            $md .= $contentIndent . "```\n";
        }

        if (!empty($node->calls) || !empty($node->externalCalls)) {
            $md .= $contentIndent . "*Calls:*\n";

            foreach ($node->calls as $child) {
                self::renderCallNode($child, $md, $level + 1);
            }

            foreach ($node->externalCalls as $extCall) {
                $md .= $contentIndent . "    - *[External/Unknown]* `{$extCall}`\n";
            }
        }
    }
}