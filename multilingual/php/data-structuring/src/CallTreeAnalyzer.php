<?php
declare(strict_types=1);

namespace App\Instrumentor\Data\Structuring;

class CallNode
{
    public string $signature;
    public ?string $source = null;
    public ?string $filePath = null;
    /** @var int[] */
    public array $executedBlocks = [];
    /** @var CallNode[] */
    public array $children = [];
    public ?CallNode $parent = null;

    public function __construct(string $signature)
    {
        $this->signature = $signature;
    }
}

class ThreadAnalysis
{
    public function __construct(
        public string   $name,
        public int      $order,
        public array    $blockTrace,
        public CallNode $callTree
    ) {}
}

class CallTreeAnalyzer
{
    public static function analyze(string $jsonInput, ?string $targetThread = null): string
    {
        try {
            $root = json_decode($jsonInput, true, 512, JSON_THROW_ON_ERROR);
            $threads = $root['threads'] ?? null;

            if (!is_array($threads) || count($threads) === 0) {
                fwrite(STDERR, "No threads data found\n");
                return $jsonInput;
            }

            $analyses = [];

            foreach ($threads as $td) {
                $name = self::getStr($td, 'name');
                if ($targetThread !== null && $targetThread !== $name) {
                    continue;
                }

                echo "[Analysis] Thread: {$name}\n";
                $order = self::getInt($td, 'order', 0);

                $trace = self::extractBlockTrace($td);

                $blockToSig  = [];
                $sigToSource = [];
                $sigToFile   = [];
                self::buildMappings($td, $blockToSig, $sigToSource, $sigToFile);

                $tree = self::buildCallTree($trace, $blockToSig, $sigToSource);
                self::attachMetadata($tree, $sigToSource, $sigToFile);

                $analyses[] = new ThreadAnalysis($name ?? '', $order, $trace, $tree);
            }

            return self::generateJson($analyses);
        } catch (\Throwable $e) {
            fwrite(STDERR, "Call tree analysis failed: " . $e->getMessage() . "\n");
            fwrite(STDERR, $e->getTraceAsString() . "\n");
            return $jsonInput;
        }
    }

    /** @return int[] */
    private static function extractBlockTrace(array $threadData): array
    {
        if (!isset($threadData['block_trace']) || !is_array($threadData['block_trace'])) {
            return self::extractBlockTraceFromSources($threadData);
        }
        $trace = [];
        foreach ($threadData['block_trace'] as $e) {
            if (is_int($e) || (is_string($e) && ctype_digit($e))) {
                $trace[] = (int)$e;
            }
        }
        return $trace;
    }

    /** @return int[] */
    private static function extractBlockTraceFromSources(array $threadData): array
    {
        $trace = [];
        if (!isset($threadData['files']) || !is_array($threadData['files'])) {
            return $trace;
        }
        foreach ($threadData['files'] as $file) {
            if (!isset($file['methods']) || !is_array($file['methods'])) continue;
            foreach ($file['methods'] as $method) {
                $source = $method['source'] ?? null;
                if (!is_string($source) || trim($source) === '') continue;
                if (preg_match_all('/\[Executed Block ID:\s*(\d+)/', $source, $m)) {
                    foreach ($m[1] as $id) $trace[] = (int)$id;
                }
            }
        }
        return $trace;
    }

    private static function buildMappings(
        array $threadData,
        array &$blockToSig,
        array &$sigToSource,
        array &$sigToFile
    ): void {
        if (!isset($threadData['files']) || !is_array($threadData['files'])) return;

        foreach ($threadData['files'] as $file) {
            $filePath = self::getStr($file, 'path');
            if (!isset($file['methods']) || !is_array($file['methods'])) continue;

            foreach ($file['methods'] as $method) {
                $source = $method['source'] ?? null;
                if (!is_string($source) || trim($source) === '') continue;

                $sig = self::extractSignature($source);

                if (preg_match_all('/\[Executed Block ID:\s*(\d+)/', $source, $m)) {
                    foreach ($m[1] as $id) {
                        $blockToSig[(int)$id] = $sig;
                    }
                }

                $sigToSource[$sig] = $source;
                $sigToFile[$sig]   = $filePath;
            }
        }
    }

    private static function extractSignature(string $source): string
    {
        if (trim($source) === '') return '<unknown>';

        $lines = preg_split('/\r?\n/', $source) ?: [];
        $parts = [];

        foreach ($lines as $line) {
            $cleaned = trim($line);
            $cleaned = preg_replace('~//\s*\[Executed Block ID:.*?\]~', '', $cleaned) ?? $cleaned;
            $cleaned = preg_replace('~//.*~', '', $cleaned) ?? $cleaned;
            $cleaned = trim($cleaned);
            if ($cleaned === '') continue;

            // PHP attributes #[...] or legacy doc-annotations @
            if (str_starts_with($cleaned, '#[') || str_starts_with($cleaned, '@')) {
                $parts[] = $cleaned;
                continue;
            }

            $decl = preg_replace('~\{.*~', '', $cleaned) ?? $cleaned;
            $decl = trim($decl);
            if ($decl !== '') $parts[] = $decl;
            break;
        }

        $sig = trim(implode(' ', $parts));
        if ($sig === '') return '<instance-initializer>';
        if ($sig === 'static') return '<static-initializer>';
        return $sig;
    }

    private static function buildCallTree(array $trace, array $blockToSig, array $sigToSource): CallNode
    {
        $root       = new CallNode('ROOT');
        $current    = $root;
        $currentSig = null;

        foreach ($trace as $blockId) {
            $targetSig = $blockToSig[$blockId] ?? null;
            if ($targetSig === null) continue;

            if ($currentSig === null) {
                $node = new CallNode($targetSig);
                $node->parent = $current;
                $current->children[] = $node;
                $current = $node;
                $currentSig = $targetSig;
                $current->executedBlocks[] = $blockId;
            } elseif ($currentSig === $targetSig) {
                $current->executedBlocks[] = $blockId;
            } else {
                $ancestor = self::findAncestor($current, $targetSig);
                if ($ancestor !== null) {
                    $current = $ancestor;
                    $currentSig = $targetSig;
                    $current->executedBlocks[] = $blockId;
                    continue;
                }

                $caller = self::findPlausibleCaller($current, $targetSig, $sigToSource);
                if ($caller !== null) {
                    $current = $caller;
                }

                $node = new CallNode($targetSig);
                $node->parent = $current;
                $current->children[] = $node;
                $current = $node;
                $currentSig = $targetSig;
                $current->executedBlocks[] = $blockId;
            }
        }
        return $root;
    }

    private static function findAncestor(CallNode $current, string $targetSig): ?CallNode
    {
        $node = $current->parent;
        while ($node !== null && $node->signature !== 'ROOT') {
            if ($node->signature === $targetSig) return $node;
            $node = $node->parent;
        }
        return null;
    }

    private static function findPlausibleCaller(CallNode $current, string $targetSig, array $sigToSource): ?CallNode
    {
        $targetName = self::extractCallableName($targetSig);
        if ($targetName === null) return null;

        $node = $current;
        while ($node !== null && $node->signature !== 'ROOT') {
            $src = $sigToSource[$node->signature] ?? null;
            if ($src !== null && str_contains($src, $targetName . '(')) {
                return $node;
            }
            $node = $node->parent;
        }
        return null;
    }

    private static function extractCallableName(string $signature): ?string
    {
        if (str_starts_with($signature, '<')) return null;

        // Strip PHP attributes and @annotations
        $clean = preg_replace('~#\[[^\]]*\]\s*~', '', $signature) ?? $signature;
        $clean = preg_replace('~@\w+\s*~', '', $clean) ?? $clean;
        $clean = trim($clean);

        $paren = strpos($clean, '(');
        if ($paren === false || $paren <= 0) return null;

        $before = trim(substr($clean, 0, $paren));
        $tokens = preg_split('/\s+/', $before) ?: [];
        if (empty($tokens)) return null;
        return (string)end($tokens);
    }

    private static function attachMetadata(CallNode $node, array $sigToSource, array $sigToFile): void
    {
        if ($node->signature !== 'ROOT') {
            $node->source   = $sigToSource[$node->signature] ?? null;
            $node->filePath = $sigToFile[$node->signature]   ?? null;
        }
        foreach ($node->children as $child) {
            self::attachMetadata($child, $sigToSource, $sigToFile);
        }
    }

    private static function generateJson(array $analyses): string
    {
        $threadList = [];

        foreach ($analyses as $ta) {
            /** @var ThreadAnalysis $ta */
            $threadMap = [
                'name'  => $ta->name,
                'order' => $ta->order,
            ];

            if (!empty($ta->blockTrace)) {
                $threadMap['block_trace'] = $ta->blockTrace;
            }

            $rootNode = $ta->callTree;
            if (count($rootNode->children) === 0) {
                $threadMap['call_tree'] = null;
            } elseif (count($rootNode->children) === 1) {
                $threadMap['call_tree'] = self::toArray($rootNode->children[0]);
            } else {
                $top = [];
                foreach ($rootNode->children as $child) {
                    $top[] = self::toArray($child);
                }
                $threadMap['call_tree'] = $top;
            }

            $threadList[] = $threadMap;
        }

        return json_encode(
            ['threads' => $threadList],
            JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE
        );
    }

    private static function toArray(CallNode $node): array
    {
        $map = ['method' => $node->signature];
        if ($node->filePath !== null) $map['file'] = $node->filePath;
        if (!empty($node->executedBlocks)) $map['executed_blocks'] = $node->executedBlocks;
        if ($node->source !== null) $map['source'] = $node->source;

        if (!empty($node->children)) {
            $calls = [];
            foreach ($node->children as $child) {
                $calls[] = self::toArray($child);
            }
            $map['calls'] = $calls;
        }
        return $map;
    }

    private static function getStr(array $arr, string $key): ?string
    {
        return isset($arr[$key]) && is_scalar($arr[$key]) ? (string)$arr[$key] : null;
    }

    private static function getInt(array $arr, string $key, int $default): int
    {
        if (!isset($arr[$key])) return $default;
        $v = $arr[$key];
        return is_numeric($v) ? (int)$v : $default;
    }
}