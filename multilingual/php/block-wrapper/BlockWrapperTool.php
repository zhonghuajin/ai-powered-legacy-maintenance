<?php

require __DIR__ . '/vendor/autoload.php';

use PhpParser\Error;
use PhpParser\Lexer;
use PhpParser\Node;
use PhpParser\NodeTraverser;
use PhpParser\NodeVisitorAbstract;
use PhpParser\NodeVisitor\CloningVisitor;
use PhpParser\Parser\Php7;
use PhpParser\PrettyPrinter;

class AddBracesVisitor extends NodeVisitorAbstract
{
    private $tokens;

    public function __construct(array $tokens)
    {
        $this->tokens = $tokens;
    }

    public function enterNode(Node $node)
    {

        if ($node instanceof Node\Stmt\If_ ||
            $node instanceof Node\Stmt\ElseIf_ ||
            $node instanceof Node\Stmt\Else_ ||
            $node instanceof Node\Stmt\For_ ||
            $node instanceof Node\Stmt\Foreach_ ||
            $node instanceof Node\Stmt\While_ ||
            $node instanceof Node\Stmt\Do_
        ) {

            $stmts = $node->stmts ?? [];

            if (empty($stmts)) {
                return null;
            }

            $firstStmt = $stmts[0];
            $startTokenPos = $firstStmt->getStartTokenPos();

            $hasBrace = false;

            $searchStartPos = $startTokenPos - 1;
            $searchEndPos = $node->getStartTokenPos();

            for ($i = $searchStartPos; $i >= $searchEndPos; $i--) {
                if (!isset($this->tokens[$i])) {
                    continue;
                }
                $token = $this->tokens[$i];
                $tokenText = is_array($token) ? $token[1] : $token;

                if ($tokenText === '{') {
                    $hasBrace = true;
                    break;
                }

                if ($tokenText === ')') {
                    break;
                }
            }

            if (!$hasBrace) {

                $newNode = clone $node;
                return $newNode;
            }
        }

        return null;
    }
}

function processFile(string $filePath)
{
    echo "Processing: $filePath\n";
    $code = file_get_contents($filePath);

    $lexer = new PhpParser\Lexer\Emulative();

    $parser = new Php7($lexer);

    try {

        $oldStmts = $parser->parse($code);
        $oldTokens = $lexer->getTokens();

        $traverser = new NodeTraverser();
        $traverser->addVisitor(new CloningVisitor());
        $newStmts = $traverser->traverse($oldStmts);

        $traverser = new NodeTraverser();
        $traverser->addVisitor(new AddBracesVisitor($oldTokens));
        $newStmts = $traverser->traverse($newStmts);

        $printer = new PrettyPrinter\Standard();
        $newCode = $printer->printFormatPreserving($newStmts, $oldStmts, $oldTokens);

        if ($newCode !== $code) {
            file_put_contents($filePath, $newCode);
            echo " -> Updated!\n";
        }

    } catch (Error $e) {
        echo "Parse Error in $filePath: {$e->getMessage()}\n";
    }
}

function processDirectoryOrFile(string $path)
{
    if (is_file($path)) {
        if (pathinfo($path, PATHINFO_EXTENSION) === 'php') {
            processFile($path);
        }
        return;
    }

    if (is_dir($path)) {
        $iterator = new RecursiveIteratorIterator(
            new RecursiveDirectoryIterator($path, RecursiveDirectoryIterator::SKIP_DOTS)
        );

        foreach ($iterator as $file) {
            if ($file->isFile() && $file->getExtension() === 'php') {
                processFile($file->getPathname());
            }
        }
    } else {
        echo "Invalid path: $path\n";
    }
}

if ($argc < 2) {
    echo "Usage: php add_braces.php <file_or_directory_path>\n";
    exit(1);
}

$targetPath = $argv[1];
processDirectoryOrFile($targetPath);

echo "Done.\n";