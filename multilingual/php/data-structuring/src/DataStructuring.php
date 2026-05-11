<?php
declare(strict_types=1);

namespace App\Instrumentor\Data\Structuring;

use PhpParser\Node;
use PhpParser\Node\Expr\ArrowFunction;
use PhpParser\Node\Expr\Closure;
use PhpParser\Node\Stmt\Class_;
use PhpParser\Node\Stmt\ClassMethod;
use PhpParser\Node\Stmt\Enum_;
use PhpParser\Node\Stmt\Function_;
use PhpParser\Node\Stmt\Interface_;
use PhpParser\Node\Stmt\Trait_;
use PhpParser\NodeTraverser;
use PhpParser\NodeVisitor\ParentConnectingVisitor;
use PhpParser\NodeVisitorAbstract;
use PhpParser\ParserFactory;

final class BlockInfo
{
    public function __construct(
        public readonly int    $id,
        public readonly string $filePath,
        public readonly int    $originalLine
    ) {}
}

final class MethodInfo
{
    public function __construct(
        public readonly string $className,
        public readonly string $fullSignature,
        public readonly int    $startLine,
        public readonly int    $endLine
    ) {}

    public function uniqueKey(): string
    {
        return $this->fullSignature . '@@' . $this->startLine;
    }
}

final class ThreadTrace
{
    /**
     * @param int[] $blockIds
     * @param string[]|null $mergedFrom
     */
    public function __construct(
        public readonly string  $name,
        public readonly int     $order,
        public readonly int     $blockCount,
        public readonly array   $blockIds,
        public readonly ?array  $mergedFrom
    ) {}
}

class DataStructuring
{
    /** @return array<int,BlockInfo> */
    public static function parseMappingFile(string $path): array
    {
        $map = [];
        $lines = @file($path, FILE_IGNORE_NEW_LINES);
        if ($lines === false) return $map;

        foreach ($lines as $line) {
            $line = trim($line);
            if ($line === '' || str_starts_with($line, '#')) continue;
            $eq = strpos($line, '=');
            if ($eq === false) continue;

            try {
                $id        = (int)trim(substr($line, 0, $eq));
                $value     = trim(substr($line, $eq + 1));
                $lastColon = strrpos($value, ':');
                if ($lastColon === false) continue;

                $filePath = trim(substr($value, 0, $lastColon));
                $lineNum  = (int)trim(substr($value, $lastColon + 1));
                $map[$id] = new BlockInfo($id, str_replace('\\', '/', $filePath), $lineNum);
            } catch (\Throwable) {
                // ignore malformed lines
            }
        }
        return $map;
    }

    /** @return ThreadTrace[] */
    public static function parseLogFile(string $path): array
    {
        $traces = [];
        $lines  = @file($path, FILE_IGNORE_NEW_LINES);
        if ($lines === false) return $traces;

        $headerPat = '/\[(.+?)\].*?#(\d+).*?count:\s*(\d+)/i';
        $mergedPat = '/[Mm]erged from\s+\d+\s+threads:\s*(.+?)$/';

        $i = 0;
        $n = count($lines);
        while ($i < $n) {
            $raw = trim($lines[$i]);
            if (preg_match($headerPat, $raw, $hm)) {
                $threadName = $hm[1];
                $order      = (int)$hm[2];
                $count      = (int)$hm[3];

                $mergedFrom = null;
                if (preg_match($mergedPat, $raw, $mm)) {
                    $mergedFrom = array_values(array_filter(
                        array_map('trim', explode(',', $mm[1])),
                        fn($s) => $s !== ''
                    ));
                }

                $buf = '';
                $i++;
                while ($i < $n) {
                    $l = trim($lines[$i]);
                    if ($l === '' || str_starts_with($l, '#') || str_starts_with($l, '[')) break;
                    $buf .= ' ' . $l;
                    $i++;
                }

                $ids = [];
                foreach (preg_split('/\s*->\s*/', trim($buf)) ?: [] as $part) {
                    $part = trim($part);
                    if ($part !== '' && is_numeric($part)) {
                        $ids[] = (int)$part;
                    }
                }
                $traces[] = new ThreadTrace($threadName, $order, $count, $ids, $mergedFrom);
            } else {
                $i++;
            }
        }
        return $traces;
    }

    /** @return array<int,MethodInfo> */
    public static function mapBlocksToMethods(string $prunedFile): array
    {
        if (!is_file($prunedFile)) return [];

        try {
            $code = file_get_contents($prunedFile);
            if ($code === false) return [];

            $parser = (new ParserFactory())->createForHostVersion();
            $ast    = $parser->parse($code);
            if ($ast === null) return [];

            $visitor   = new BlockCommentVisitor();
            $traverser = new NodeTraverser();
            $traverser->addVisitor(new ParentConnectingVisitor());
            $traverser->addVisitor($visitor);
            $traverser->traverse($ast);

            return $visitor->blockToMethod;
        } catch (\Throwable $e) {
            fwrite(STDERR, "[WARN] Parsing failed: $prunedFile — " . $e->getMessage() . "\n");
            return [];
        }
    }

    public static function extractSource(string $filePath, int $startLine, int $endLine): string
    {
        if ($startLine <= 0 || $endLine <= 0) return '';
        $content = @file_get_contents($filePath);
        if ($content === false) return '';

        $lines = preg_split('/\r?\n/', $content) ?: [];
        if (empty($lines) || $startLine > count($lines)) return '';
        $endLine = min($endLine, count($lines));
        $slice   = array_slice($lines, $startLine - 1, $endLine - $startLine + 1);
        return self::dedent($slice);
    }

    /** @param string[] $lines */
    public static function dedent(array $lines): string
    {
        $minIndent = PHP_INT_MAX;
        foreach ($lines as $line) {
            if (trim($line) === '') continue;
            $spaces = 0;
            $len    = strlen($line);
            for ($i = 0; $i < $len; $i++) {
                $c = $line[$i];
                if ($c === ' ') $spaces++;
                elseif ($c === "\t") $spaces += 4;
                else break;
            }
            if ($spaces < $minIndent) $minIndent = $spaces;
        }
        if ($minIndent <= 0 || $minIndent === PHP_INT_MAX) {
            return implode("\n", $lines);
        }

        $strip  = $minIndent;
        $result = [];
        foreach ($lines as $line) {
            if (trim($line) === '') { $result[] = ''; continue; }
            $removed = 0; $pos = 0; $len = strlen($line);
            while ($pos < $len && $removed < $strip) {
                $c = $line[$pos];
                if ($c === ' ')       { $removed++;    $pos++; }
                elseif ($c === "\t")  { $removed += 4; $pos++; }
                else break;
            }
            $result[] = substr($line, $pos);
        }
        return implode("\n", $result);
    }

    public static function extractRelativePath(string $absolutePath): string
    {
        $norm = str_replace('\\', '/', $absolutePath);
        // PHP-ecosystem common project roots
        $markers = ['/src/', '/app/', '/lib/', '/tests/'];
        foreach ($markers as $marker) {
            $idx = strpos($norm, $marker);
            if ($idx !== false) {
                return substr($norm, $idx + strlen($marker));
            }
        }
        $lastSlash = strrpos($norm, '/');
        return $lastSlash !== false ? substr($norm, $lastSlash + 1) : $norm;
    }

    public static function resolvePrunedFilePath(string $prunedDir, string $threadName, string $originalPath): ?string
    {
        $fileName      = basename($originalPath);
        $baseThreadDir = $prunedDir . DIRECTORY_SEPARATOR . self::sanitizeDirName($threadName);
        if (!is_dir($baseThreadDir)) return null;

        $iter = new \RecursiveIteratorIterator(
            new \RecursiveDirectoryIterator($baseThreadDir, \FilesystemIterator::SKIP_DOTS)
        );
        foreach ($iter as $file) {
            /** @var \SplFileInfo $file */
            if ($file->isFile() && $file->getFilename() === $fileName) {
                return $file->getPathname();
            }
        }
        return null;
    }

    private static function sanitizeDirName(string $name): string
    {
        return preg_replace('/[^a-zA-Z0-9_\-.]/', '_', $name) ?? $name;
    }

    private static function compactIntegerArrays(string $json): string
    {
        return preg_replace_callback('/\[([\s\d,]+)\]/', function ($m) {
            $content = preg_replace('/\s+/', '', $m[1]) ?? $m[1];
            $content = str_replace(',', ', ', $content);
            return '[' . $content . ']';
        }, $json) ?? $json;
    }

    public static function run(array $argv): int
    {
        if (count($argv) < 4) {
            echo "Usage: php bin/data-structuring.php <pruned_dir> <comment_mapping> <log_file>\n";
            return 1;
        }

        $prunedDir   = $argv[1];
        $mappingPath = $argv[2];
        $logPath     = $argv[3];

        $baseOutputName = 'final-output';

        echo "[1/2] Starting to parse logs and source code structure...\n";
        $blockMap = self::parseMappingFile($mappingPath);
        $traces   = self::parseLogFile($logPath);

        $fileBlockTotals = [];
        foreach ($blockMap as $bi) {
            $rel = self::extractRelativePath($bi->filePath);
            $fileBlockTotals[$rel] = ($fileBlockTotals[$rel] ?? 0) + 1;
        }

        $threadList = [];

        foreach ($traces as $trace) {
            $tObj = [
                'name'  => $trace->name,
                'order' => $trace->order,
            ];
            if ($trace->mergedFrom !== null) {
                $tObj['merged_from'] = $trace->mergedFrom;
            }
            $tObj['block_trace'] = $trace->blockIds;

            $fileOrder             = [];
            $methodOrderInFile     = [];
            $fileMethodBlocks      = [];
            $fileMethodInfos       = [];
            $fileToBlockMethodMap  = [];
            $resolvedFiles         = [];

            foreach ($trace->blockIds as $bid) {
                $bi = $blockMap[$bid] ?? null;
                if ($bi === null) continue;

                $relPath = self::extractRelativePath($bi->filePath);

                if (!in_array($relPath, $fileOrder, true)) {
                    $fileOrder[]                    = $relPath;
                    $methodOrderInFile[$relPath]    = [];
                    $fileMethodBlocks[$relPath]     = [];
                    $fileMethodInfos[$relPath]      = [];

                    $pFile = self::resolvePrunedFilePath($prunedDir, $trace->name, $bi->filePath);
                    if ($pFile !== null) {
                        $resolvedFiles[$relPath]        = $pFile;
                        $fileToBlockMethodMap[$relPath] = self::mapBlocksToMethods($pFile);
                    } else {
                        $fileToBlockMethodMap[$relPath] = [];
                    }
                }

                $mi        = $fileToBlockMethodMap[$relPath][$bid] ?? null;
                $methodKey = $mi !== null ? $mi->uniqueKey() : "<unknown>@@block:$bid";

                if (!in_array($methodKey, $methodOrderInFile[$relPath], true)) {
                    $methodOrderInFile[$relPath][] = $methodKey;
                }

                $fileMethodBlocks[$relPath][$methodKey] ??= [];
                $fileMethodBlocks[$relPath][$methodKey][] = $bid;

                if ($mi !== null && !isset($fileMethodInfos[$relPath][$methodKey])) {
                    $fileMethodInfos[$relPath][$methodKey] = $mi;
                }
            }

            $filesArray = [];
            foreach ($fileOrder as $relPath) {
                $fObj       = ['path' => $relPath];
                $actualFile = $resolvedFiles[$relPath] ?? null;

                if (isset($fileBlockTotals[$relPath])) {
                    $fObj['blocks_total'] = $fileBlockTotals[$relPath];
                }

                $methodsArray = [];
                foreach ($methodOrderInFile[$relPath] as $methodKey) {
                    $mi   = $fileMethodInfos[$relPath][$methodKey] ?? null;
                    $mObj = [];
                    if ($mi !== null) {
                        $mObj['line_start'] = $mi->startLine;
                        $mObj['source']     = $actualFile !== null
                            ? self::extractSource($actualFile, $mi->startLine, $mi->endLine)
                            : '';
                    } else {
                        $mObj['line_start'] = 0;
                        $mObj['source']     = '';
                    }
                    $methodsArray[] = $mObj;
                }

                $fObj['methods'] = $methodsArray;
                $filesArray[]    = $fObj;
            }

            $tObj['files'] = $filesArray;
            $threadList[]  = $tObj;
        }

        $root             = ['threads' => $threadList];
        $intermediateJson = json_encode(
            $root,
            JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE
        );
        $intermediateJson = self::compactIntegerArrays($intermediateJson);

        echo "[2/2] Generating standalone data files...\n";

        $callTreeOnlyOutput = CallTreeAnalyzer::analyze($intermediateJson, null);
        $ctPath   = $baseOutputName . '-calltree.json';
        file_put_contents($ctPath, $callTreeOnlyOutput);

        echo str_repeat('=', 50) . "\n";
        echo "All analysis tasks have been completed!\n";
        return 0;
    }
}

/**
 * Walks the AST, finds comments like "Executed Block ID: N" and maps them
 * to the enclosing function / method / closure / arrow function.
 */
class BlockCommentVisitor extends NodeVisitorAbstract
{
    /** @var array<int,MethodInfo> */
    public array $blockToMethod = [];

    public function enterNode(Node $node)
    {
        $comments = $node->getComments();
        if (empty($comments)) return null;

        foreach ($comments as $comment) {
            $text = $comment->getText();
            if (preg_match_all('/Executed Block ID:\s*(\d+)/', $text, $matches)) {
                $enclosing = $this->findEnclosingMethod($node);
                if ($enclosing !== null) {
                    foreach ($matches[1] as $id) {
                        $this->blockToMethod[(int)$id] = $enclosing;
                    }
                }
            }
        }
        return null;
    }

    private function findEnclosingMethod(Node $node): ?MethodInfo
    {
        $current = $node;
        while ($current !== null) {
            if ($current instanceof ClassMethod)    return $this->createMethodInfo($current);
            if ($current instanceof Function_)      return $this->createMethodInfo($current);
            if ($current instanceof Closure)        return $this->createMethodInfo($current);
            if ($current instanceof ArrowFunction)  return $this->createMethodInfo($current);
            $current = $current->getAttribute('parent');
        }
        return null;
    }

    private function createMethodInfo(Node $node): MethodInfo
    {
        if ($node instanceof ClassMethod) {
            $signature = $this->buildMethodSignature($node);
        } elseif ($node instanceof Function_) {
            $signature = $this->buildFunctionSignature($node);
        } elseif ($node instanceof Closure) {
            $params = implode(', ', array_map(fn($p) => $this->paramToString($p), $node->params));
            $signature = 'Closure: function (' . $params . ') {...}';
        } elseif ($node instanceof ArrowFunction) {
            $params = implode(', ', array_map(fn($p) => $this->paramToString($p), $node->params));
            $signature = 'ArrowFunction: fn(' . $params . ') => ...';
        } else {
            $signature = '<unknown>';
        }

        $start = $node->getStartLine() ?: 0;
        $end   = $node->getEndLine()   ?: 0;
        return new MethodInfo($this->enclosingTypeName($node), $signature, $start, $end);
    }

    private function buildMethodSignature(ClassMethod $md): string
    {
        $mods = [];
        if ($md->isPublic())    $mods[] = 'public';
        if ($md->isProtected()) $mods[] = 'protected';
        if ($md->isPrivate())   $mods[] = 'private';
        if ($md->isStatic())    $mods[] = 'static';
        if ($md->isAbstract())  $mods[] = 'abstract';
        if ($md->isFinal())     $mods[] = 'final';

        $sb = '';
        if (!empty($mods)) $sb .= implode(' ', $mods) . ' ';
        $sb .= 'function ' . $md->name->toString() . '(';
        $sb .= implode(', ', array_map(fn($p) => $this->paramToString($p), $md->params));
        $sb .= ')';
        if ($md->returnType !== null) $sb .= ': ' . $this->typeToString($md->returnType);
        return $sb;
    }

    private function buildFunctionSignature(Function_ $fd): string
    {
        $sb  = 'function ' . $fd->name->toString() . '(';
        $sb .= implode(', ', array_map(fn($p) => $this->paramToString($p), $fd->params));
        $sb .= ')';
        if ($fd->returnType !== null) $sb .= ': ' . $this->typeToString($fd->returnType);
        return $sb;
    }

    private function paramToString(Node\Param $p): string
    {
        $s = '';
        if ($p->type !== null) $s .= $this->typeToString($p->type) . ' ';
        if ($p->byRef)    $s .= '&';
        if ($p->variadic) $s .= '...';
        $name = $p->var instanceof Node\Expr\Variable && is_string($p->var->name)
            ? $p->var->name : 'var';
        $s .= '$' . $name;
        return $s;
    }

    private function typeToString(Node $type): string
    {
        if ($type instanceof Node\Identifier)      return $type->name;
        if ($type instanceof Node\Name)            return $type->toString();
        if ($type instanceof Node\NullableType)    return '?' . $this->typeToString($type->type);
        if ($type instanceof Node\UnionType) {
            return implode('|', array_map(fn($t) => $this->typeToString($t), $type->types));
        }
        if ($type instanceof Node\IntersectionType) {
            return implode('&', array_map(fn($t) => $this->typeToString($t), $type->types));
        }
        return '';
    }

    private function enclosingTypeName(Node $node): string
    {
        $parts = [];
        $cur   = $node->getAttribute('parent');
        while ($cur !== null) {
            if ($cur instanceof Class_ && $cur->name !== null) {
                array_unshift($parts, $cur->name->toString());
            } elseif ($cur instanceof Interface_) {
                array_unshift($parts, $cur->name->toString());
            } elseif ($cur instanceof Trait_) {
                array_unshift($parts, $cur->name->toString());
            } elseif ($cur instanceof Enum_ && $cur->name !== null) {
                array_unshift($parts, $cur->name->toString());
            }
            $cur = $cur->getAttribute('parent');
        }
        return empty($parts) ? '<anonymous>' : implode('$', $parts);
    }
}