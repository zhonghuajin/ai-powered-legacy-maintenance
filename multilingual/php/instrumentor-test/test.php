<?php

declare(strict_types=1);

namespace App\StressTest;

use ArrayAccess;
use Countable;
use Iterator;
use JsonSerializable;
use Stringable;
use Fiber;
use WeakMap;

// ─────────────────────────────────────────────
// 1. Enums (Backed Enum + Interface + Methods)
// ─────────────────────────────────────────────
enum Priority: int implements JsonSerializable
{
    case Low    = 1;
    case Medium = 5;
    case High   = 10;
    case Ultra  = 100;

    public function label(): string
    {
        return match ($this) {
            self::Low    => 'low-priority',
            self::Medium => 'medium-priority',
            self::High   => 'high-priority',
            self::Ultra  => 'ULTRA ⚡',
        };
    }

    public function jsonSerialize(): mixed
    {
        return ['name' => $this->name, 'value' => $this->value, 'label' => $this->label()];
    }

    public static function fromLabel(string $label): self
    {
        foreach (self::cases() as $case)
            if ($case->label() === $label)
                return $case;

        throw new \InvalidArgumentException("Unknown label: {$label}");
    }
}

enum Suit: string
{
    case Hearts   = '♥';
    case Diamonds = '♦';
    case Clubs    = '♣';
    case Spades   = '♠';

    public function color(): string
    {
        return match ($this) {
            self::Hearts, self::Diamonds => 'red',
            self::Clubs, self::Spades    => 'black',
        };
    }
}

// ─────────────────────────────────────────────
// 2. Interfaces + Multi-interface Combination
// ─────────────────────────────────────────────
interface Identifiable
{
    public function getId(): string|int;
}

interface Cacheable extends JsonSerializable
{
    public function cacheKey(): string;
    public function ttl(): int;
}

interface Transformable
{
    public function toArray(): array;
    public function toJson(): string;
}

interface Pipeline
{
    public function pipe(callable ...$stages): mixed;
}

// ─────────────────────────────────────────────
// 3. Traits (Multiple Traits + Conflict Resolution)
// ─────────────────────────────────────────────
trait TimestampTrait
{
    private float $createdAt;
    private float $updatedAt;

    public function initTimestamps(): void
    {
        $this->createdAt = microtime(true);
        $this->updatedAt = $this->createdAt;
    }

    public function touch(): void
    {
        $this->updatedAt = microtime(true);
    }

    public function age(): float
    {
        return microtime(true) - $this->createdAt;
    }
}

trait SoftDeleteTrait
{
    private ?float $deletedAt = null;

    public function softDelete(): void
    {
        $this->deletedAt = microtime(true);
    }

    public function restore(): void
    {
        $this->deletedAt = null;
    }

    public function isTrashed(): bool
    {
        return $this->deletedAt !== null;
    }

    // Conflicting method name with TimestampTrait (intentionally created)
    public function touch(): void
    {
        $this->deletedAt = null;
    }
}

trait ObservableTrait
{
    private array $listeners = [];

    public function on(string $event, callable $callback): void
    {
        if (!isset($this->listeners[$event]))
            $this->listeners[$event] = [];

        $this->listeners[$event][] = $callback;
    }

    public function emit(string $event, mixed ...$args): void
    {
        if (!isset($this->listeners[$event]))
            return;

        foreach ($this->listeners[$event] as $listener)
            $listener(...$args);
    }

    public function clearListeners(?string $event = null): void
    {
        if ($event === null) {
            $this->listeners = [];
        } else {
            unset($this->listeners[$event]);
        }
    }
}

// ─────────────────────────────────────────────
// 4. Abstract Base Class (readonly properties + constructor promotion)
// ─────────────────────────────────────────────
abstract class Entity implements Identifiable, Transformable, Stringable
{
    use TimestampTrait;
    use SoftDeleteTrait {
        SoftDeleteTrait::touch insteadof TimestampTrait;
        TimestampTrait::touch as touchTimestamp;
    }
    use ObservableTrait;

    public function __construct(
        protected readonly string|int $id,
        protected string              $name,
        protected Priority            $priority = Priority::Medium,
        protected array               $metadata = [],
    ) {
        $this->initTimestamps();
    }

    public function getId(): string|int
    {
        return $this->id;
    }

    public function __toString(): string
    {
        return sprintf('[%s#%s] %s', static::class, $this->id, $this->name);
    }

    public function toJson(): string
    {
        return json_encode($this->toArray(), JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
    }

    abstract public function validate(): bool;

    // Template method pattern
    public function save(): bool
    {
        if (!$this->validate()) {
            $this->emit('validation_failed', $this);
            return false;
        }

        $this->touchTimestamp();
        $this->emit('before_save', $this);

        try {
            $result = $this->performSave();
            if ($result)
                $this->emit('after_save', $this);
            else
                $this->emit('save_failed', $this);
            return $result;
        } catch (\Throwable $e) {
            $this->emit('save_error', $this, $e);
            throw $e;
        } finally {
            $this->emit('save_complete', $this);
        }
    }

    protected function performSave(): bool
    {
        // Simulate I/O
        usleep(100);
        return true;
    }
}

// ─────────────────────────────────────────────
// 5. Concrete Class: Implements Highly Nested Logic
// ─────────────────────────────────────────────
class Task extends Entity implements Cacheable, Pipeline
{
    private array $subtasks = [];
    private array $tags     = [];
    private ?self $parent   = null;
    private int   $retries  = 0;
    private const MAX_RETRIES = 3;

    public function __construct(
        string|int $id,
        string     $name,
        Priority   $priority = Priority::Medium,
        private    readonly \DateTimeImmutable $deadline = new \DateTimeImmutable('+7 days'),
    ) {
        parent::__construct($id, $name, $priority);
    }

    public function validate(): bool
    {
        // Multi-level nested if
        if (empty($this->name)) {
            if ($this->priority === Priority::Ultra) {
                if ($this->retries < self::MAX_RETRIES) {
                    $this->retries++;
                    return false;
                } else {
                    throw new \RuntimeException("Max retries exceeded for ultra task");
                }
            }
            return false;
        }

        if ($this->deadline < new \DateTimeImmutable('now')) {
            if ($this->priority->value >= Priority::High->value)
                throw new \LogicException("High-priority task is past deadline");
            else
                return false;
        }

        // Validate subtasks (recursive)
        foreach ($this->subtasks as $idx => $subtask) {
            if (!$subtask->validate()) {
                for ($i = $idx; $i < count($this->subtasks); $i++) {
                    if ($this->subtasks[$i]->priority->value >= $this->priority->value) {
                        while ($this->subtasks[$i]->retries < self::MAX_RETRIES) {
                            $this->subtasks[$i]->retries++;
                            if ($this->subtasks[$i]->validate())
                                break;
                        }
                    }
                }
                return false;
            }
        }

        return true;
    }

    public function addSubtask(self $task): self
    {
        $task->parent = $this;
        $this->subtasks[] = $task;
        $this->emit('subtask_added', $task);
        return $this;
    }

    public function addTag(string ...$tags): self
    {
        foreach ($tags as $tag)
            if (!in_array($tag, $this->tags, true))
                $this->tags[] = $tag;
        return $this;
    }

    // Depth-first traversal – generator (yield from)
    public function walkDepthFirst(): \Generator
    {
        yield $this;
        foreach ($this->subtasks as $sub)
            yield from $sub->walkDepthFirst();
    }

    // Breadth-first traversal – generator
    public function walkBreadthFirst(): \Generator
    {
        $queue = new \SplQueue();
        $queue->enqueue($this);

        while (!$queue->isEmpty()) {
            $current = $queue->dequeue();
            yield $current;
            foreach ($current->subtasks as $sub)
                $queue->enqueue($sub);
        }
    }

    // Pipeline pattern
    public function pipe(callable ...$stages): mixed
    {
        $result = $this;
        foreach ($stages as $stage) {
            $result = $stage($result);
            if ($result === null)
                break;
        }
        return $result;
    }

    // Cacheable
    public function cacheKey(): string
    {
        return sprintf('task:%s:%s', $this->id, md5(serialize($this->tags)));
    }

    public function ttl(): int
    {
        return match (true) {
            $this->priority === Priority::Ultra  => 60,
            $this->priority === Priority::High   => 300,
            $this->priority === Priority::Medium => 3600,
            default                              => 86400,
        };
    }

    public function jsonSerialize(): mixed
    {
        return $this->toArray();
    }

    public function toArray(): array
    {
        return [
            'id'       => $this->id,
            'name'     => $this->name,
            'priority' => $this->priority->label(),
            'deadline' => $this->deadline->format('c'),
            'tags'     => $this->tags,
            'subtasks' => array_map(fn(self $s) => $s->toArray(), $this->subtasks),
            'trashed'  => $this->isTrashed(),
        ];
    }
}

// ─────────────────────────────────────────────
// 6. Generic-style collection class (ArrayAccess + Iterator + Countable)
// ─────────────────────────────────────────────
class TypedCollection implements ArrayAccess, Iterator, Countable, JsonSerializable
{
    private array $items = [];
    private int   $position = 0;
    private array $indices  = [];

    public function __construct(
        private readonly string $type,
        array                   $initial = [],
    ) {
        foreach ($initial as $item)
            $this->append($item);
    }

    public function append(mixed $item): void
    {
        if (!($item instanceof $this->type))
            throw new \InvalidArgumentException(
                sprintf("Expected %s, got %s", $this->type, get_debug_type($item))
            );

        $this->items[] = $item;
        $this->indices = array_keys($this->items);
    }

    // Higher-order methods: filter + map + reduce + each
    public function filter(callable $predicate): self
    {
        $new = new self($this->type);
        foreach ($this->items as $item)
            if ($predicate($item))
                $new->append($item);
        return $new;
    }

    public function map(callable $fn): array
    {
        $result = [];
        foreach ($this->items as $key => $item) {
            $mapped = $fn($item, $key);
            $result[] = $mapped;
        }
        return $result;
    }

    public function reduce(callable $fn, mixed $initial = null): mixed
    {
        $carry = $initial;
        foreach ($this->items as $item)
            $carry = $fn($carry, $item);
        return $carry;
    }

    public function each(callable $fn): self
    {
        foreach ($this->items as $key => $item) {
            $result = $fn($item, $key);
            if ($result === false)
                break;
        }
        return $this;
    }

    public function sortBy(callable $comparator): self
    {
        $sorted = $this->items;
        usort($sorted, $comparator);
        return new self($this->type, $sorted);
    }

    public function groupBy(callable $keyFn): array
    {
        $groups = [];
        foreach ($this->items as $item) {
            $key = $keyFn($item);
            if (!isset($groups[$key]))
                $groups[$key] = new self($this->type);
            $groups[$key]->append($item);
        }
        return $groups;
    }

    public function first(?callable $predicate = null): mixed
    {
        if ($predicate === null) {
            return $this->items[0] ?? null;
        }
        foreach ($this->items as $item) {
            if ($predicate($item))
                return $item;
        }
        return null;
    }

    public function chunk(int $size): array
    {
        $chunks = [];
        $buffer = [];
        $count  = 0;

        foreach ($this->items as $item) {
            $buffer[] = $item;
            $count++;

            if ($count >= $size) {
                $chunks[] = new self($this->type, $buffer);
                $buffer = [];
                $count  = 0;
            }
        }

        if (!empty($buffer))
            $chunks[] = new self($this->type, $buffer);

        return $chunks;
    }

    // ArrayAccess
    public function offsetExists(mixed $offset): bool { return isset($this->items[$offset]); }
    public function offsetGet(mixed $offset): mixed { return $this->items[$offset] ?? null; }
    public function offsetSet(mixed $offset, mixed $value): void
    {
        if ($offset === null)
            $this->append($value);
        else {
            if (!($value instanceof $this->type))
                throw new \InvalidArgumentException("Type mismatch");
            $this->items[$offset] = $value;
            $this->indices = array_keys($this->items);
        }
    }
    public function offsetUnset(mixed $offset): void
    {
        unset($this->items[$offset]);
        $this->items   = array_values($this->items);
        $this->indices = array_keys($this->items);
    }

    // Iterator
    public function current(): mixed  { return $this->items[$this->indices[$this->position]] ?? null; }
    public function key(): int        { return $this->position; }
    public function next(): void      { $this->position++; }
    public function rewind(): void    { $this->position = 0; }
    public function valid(): bool     { return isset($this->indices[$this->position]); }

    // Countable
    public function count(): int { return count($this->items); }

    // JsonSerializable
    public function jsonSerialize(): array
    {
        return $this->map(fn($item) => $item instanceof JsonSerializable ? $item->jsonSerialize() : (array)$item);
    }
}

// ─────────────────────────────────────────────
// 7. Async/Fiber Scheduler (PHP 8.1+)
// ─────────────────────────────────────────────
class MicroScheduler
{
    private \SplQueue $ready;
    private array     $sleeping = [];
    private int       $tickCount = 0;

    public function __construct()
    {
        $this->ready = new \SplQueue();
    }

    public function spawn(callable $task): void
    {
        $fiber = new Fiber($task);
        $this->ready->enqueue($fiber);
    }

    public function run(): void
    {
        while (!$this->ready->isEmpty() || !empty($this->sleeping)) {
            // Wake up due fibers
            $now = microtime(true);
            foreach ($this->sleeping as $idx => [$wakeTime, $fiber]) {
                if ($now >= $wakeTime) {
                    $this->ready->enqueue($fiber);
                    unset($this->sleeping[$idx]);
                }
            }
            $this->sleeping = array_values($this->sleeping);

            if ($this->ready->isEmpty()) {
                if (!empty($this->sleeping))
                    usleep(1000);
                continue;
            }

            /** @var Fiber $fiber */
            $fiber = $this->ready->dequeue();
            $this->tickCount++;

            try {
                if (!$fiber->isStarted()) {
                    $result = $fiber->start();
                } elseif ($fiber->isSuspended()) {
                    $result = $fiber->resume();
                } else {
                    continue;
                }

                // If fiber suspended and returned a sleep time
                if ($fiber->isSuspended()) {
                    if (is_float($result) || is_int($result)) {
                        $this->sleeping[] = [microtime(true) + $result, $fiber];
                    } else {
                        $this->ready->enqueue($fiber);
                    }
                }
            } catch (\Throwable $e) {
                fprintf(STDERR, "Fiber crashed: %s\n", $e->getMessage());
            }
        }
    }

    public function getTickCount(): int
    {
        return $this->tickCount;
    }
}

// ─────────────────────────────────────────────
// 8. Recursive data structure: binary tree + various traversals
// ─────────────────────────────────────────────
class BinaryTree
{
    public function __construct(
        public readonly mixed       $value,
        public ?self                $left = null,
        public ?self                $right = null,
    ) {}

    public static function fromSortedArray(array $arr): ?self
    {
        if (empty($arr))
            return null;

        $mid   = intdiv(count($arr), 2);
        $node  = new self($arr[$mid]);
        $node->left  = self::fromSortedArray(array_slice($arr, 0, $mid));
        $node->right = self::fromSortedArray(array_slice($arr, $mid + 1));
        return $node;
    }

    public function inOrder(): \Generator
    {
        if ($this->left !== null)
            yield from $this->left->inOrder();
        yield $this->value;
        if ($this->right !== null)
            yield from $this->right->inOrder();
    }

    public function preOrder(): \Generator
    {
        yield $this->value;
        if ($this->left !== null)
            yield from $this->left->preOrder();
        if ($this->right !== null)
            yield from $this->right->preOrder();
    }

    public function postOrder(): \Generator
    {
        if ($this->left !== null)
            yield from $this->left->postOrder();
        if ($this->right !== null)
            yield from $this->right->postOrder();
        yield $this->value;
    }

    public function levelOrder(): \Generator
    {
        $queue = new \SplQueue();
        $queue->enqueue($this);

        while (!$queue->isEmpty()) {
            $node = $queue->dequeue();
            yield $node->value;

            if ($node->left !== null)
                $queue->enqueue($node->left);
            if ($node->right !== null)
                $queue->enqueue($node->right);
        }
    }

    public function height(): int
    {
        $l = $this->left  ? $this->left->height()  : 0;
        $r = $this->right ? $this->right->height() : 0;
        return 1 + max($l, $r);
    }

    public function mirror(): self
    {
        $mirrored = new self($this->value);
        $mirrored->left  = $this->right?->mirror();
        $mirrored->right = $this->left?->mirror();
        return $mirrored;
    }

    public function find(mixed $target): ?self
    {
        if ($this->value === $target)
            return $this;

        $found = $this->left?->find($target);
        if ($found !== null)
            return $found;

        return $this->right?->find($target);
    }

    public function reduce(callable $fn, mixed $initial = null): mixed
    {
        $acc = $fn($initial, $this->value);
        if ($this->left !== null)
            $acc = $this->left->reduce($fn, $acc);
        if ($this->right !== null)
            $acc = $this->right->reduce($fn, $acc);
        return $acc;
    }
}

// ─────────────────────────────────────────────
// 9. Functional toolbox (closures, currying, composition, memoize)
// ─────────────────────────────────────────────
final class Fp
{
    // Currying
    public static function curry(callable $fn): \Closure
    {
        $arity = (new \ReflectionFunction($fn))->getNumberOfRequiredParameters();

        $accumulator = function (array $args) use ($fn, $arity, &$accumulator): mixed {
            if (count($args) >= $arity) {
                return $fn(...$args);
            }
            return function (mixed ...$more) use ($args, $accumulator): mixed {
                return $accumulator(array_merge($args, $more));
            };
        };

        return function (mixed ...$args) use ($accumulator): mixed {
            return $accumulator($args);
        };
    }

    // Function composition compose(f, g, h)(x) = f(g(h(x)))
    public static function compose(callable ...$fns): \Closure
    {
        return function (mixed $value) use ($fns): mixed {
            $result = $value;
            for ($i = count($fns) - 1; $i >= 0; $i--)
                $result = $fns[$i]($result);
            return $result;
        };
    }

    // Pipeline pipeline(f, g, h)(x) = h(g(f(x)))
    public static function pipeline(callable ...$fns): \Closure
    {
        return function (mixed $value) use ($fns): mixed {
            $result = $value;
            foreach ($fns as $fn)
                $result = $fn($result);
            return $result;
        };
    }

    // Memoization
    public static function memoize(callable $fn): \Closure
    {
        $cache = [];
        return function () use ($fn, &$cache): mixed {
            $key = serialize(func_get_args());
            if (!array_key_exists($key, $cache)) {
                $cache[$key] = $fn(...func_get_args());
            }
            return $cache[$key];
        };
    }

    // Trampoline for safe tail recursion
    public static function trampoline(callable $fn): \Closure
    {
        return function () use ($fn): mixed {
            $result = $fn(...func_get_args());
            while ($result instanceof \Closure)
                $result = $result();
            return $result;
        };
    }

    // Lazy evaluation sequence
    public static function lazyRange(int $start, int $end, int $step = 1): \Generator
    {
        if ($step > 0) {
            for ($i = $start; $i <= $end; $i += $step)
                yield $i;
        } else {
            for ($i = $start; $i >= $end; $i += $step)
                yield $i;
        }
    }

    // Infinite Fibonacci generator
    public static function fibonacci(): \Generator
    {
        [$a, $b] = [0, 1];
        while (true) {
            yield $a;
            [$a, $b] = [$b, $a + $b];
        }
    }

    // Take N items
    public static function take(\Generator $gen, int $n): array
    {
        $result = [];
        $count  = 0;
        foreach ($gen as $value) {
            if ($count >= $n)
                break;
            $result[] = $value;
            $count++;
        }
        return $result;
    }
}

// ─────────────────────────────────────────────
// 10. State machine
// ─────────────────────────────────────────────
class StateMachine
{
    private string $current;
    private array  $transitions = [];
    private array  $hooks       = [];

    public function __construct(string $initial)
    {
        $this->current = $initial;
    }

    public function addTransition(string $from, string $event, string $to, ?callable $guard = null): self
    {
        $this->transitions[$from][$event][] = ['to' => $to, 'guard' => $guard];
        return $this;
    }

    public function onEnter(string $state, callable $hook): self
    {
        $this->hooks[$state]['enter'][] = $hook;
        return $this;
    }

    public function onExit(string $state, callable $hook): self
    {
        $this->hooks[$state]['exit'][] = $hook;
        return $this;
    }

    public function send(string $event, array $context = []): bool
    {
        if (!isset($this->transitions[$this->current][$event]))
            return false;

        foreach ($this->transitions[$this->current][$event] as $candidate) {
            if ($candidate['guard'] !== null && !$candidate['guard']($context))
                continue;

            $from = $this->current;
            $to   = $candidate['to'];

            // Trigger exit hooks
            if (isset($this->hooks[$from]['exit']))
                foreach ($this->hooks[$from]['exit'] as $hook)
                    $hook($from, $to, $event, $context);

            $this->current = $to;

            // Trigger enter hooks
            if (isset($this->hooks[$to]['enter']))
                foreach ($this->hooks[$to]['enter'] as $hook)
                    $hook($from, $to, $event, $context);

            return true;
        }

        return false;
    }

    public function getState(): string
    {
        return $this->current;
    }
}

// ─────────────────────────────────────────────
// 11. Reactive Observable (minimal Rx style)
// ─────────────────────────────────────────────
class Observable
{
    private \Closure $subscribeFn;

    public function __construct(callable $subscribeFn)
    {
        $this->subscribeFn = $subscribeFn(...);
    }

    public static function fromArray(array $items): self
    {
        return new self(function (callable $onNext, callable $onError, callable $onComplete) use ($items) {
            try {
                foreach ($items as $item)
                    $onNext($item);
                $onComplete();
            } catch (\Throwable $e) {
                $onError($e);
            }
        });
    }

    public static function fromGenerator(\Generator $gen): self
    {
        return new self(function (callable $onNext, callable $onError, callable $onComplete) use ($gen) {
            try {
                foreach ($gen as $value)
                    $onNext($value);
                $onComplete();
            } catch (\Throwable $e) {
                $onError($e);
            }
        });
    }

    public function map(callable $fn): self
    {
        $source = $this;
        return new self(function (callable $onNext, callable $onError, callable $onComplete) use ($source, $fn) {
            $source->subscribe(
                function ($value) use ($onNext, $fn) { $onNext($fn($value)); },
                $onError,
                $onComplete,
            );
        });
    }

    public function filter(callable $predicate): self
    {
        $source = $this;
        return new self(function (callable $onNext, callable $onError, callable $onComplete) use ($source, $predicate) {
            $source->subscribe(
                function ($value) use ($onNext, $predicate) {
                    if ($predicate($value))
                        $onNext($value);
                },
                $onError,
                $onComplete,
            );
        });
    }

    public function reduce(callable $fn, mixed $seed = null): self
    {
        $source = $this;
        return new self(function (callable $onNext, callable $onError, callable $onComplete) use ($source, $fn, $seed) {
            $acc = $seed;
            $source->subscribe(
                function ($value) use (&$acc, $fn) { $acc = $fn($acc, $value); },
                $onError,
                function () use (&$acc, $onNext, $onComplete) {
                    $onNext($acc);
                    $onComplete();
                },
            );
        });
    }

    public function take(int $n): self
    {
        $source = $this;
        return new self(function (callable $onNext, callable $onError, callable $onComplete) use ($source, $n) {
            $count = 0;
            $source->subscribe(
                function ($value) use ($onNext, &$count, $n, $onComplete) {
                    if ($count < $n) {
                        $onNext($value);
                        $count++;
                        if ($count >= $n)
                            $onComplete();
                    }
                },
                $onError,
                $onComplete,
            );
        });
    }

    public function subscribe(callable $onNext, ?callable $onError = null, ?callable $onComplete = null): void
    {
        ($this->subscribeFn)(
            $onNext,
            $onError ?? function (\Throwable $e) { throw $e; },
            $onComplete ?? function () {},
        );
    }

    public function toArray(): array
    {
        $result = [];
        $this->subscribe(
            function ($value) use (&$result) { $result[] = $value; },
            function (\Throwable $e) { throw $e; },
            function () {},
        );
        return $result;
    }
}

// ─────────────────────────────────────────────
// 12. WeakMap cache + magic methods
// ─────────────────────────────────────────────
class MetadataRegistry
{
    private static ?WeakMap $store = null;

    private static function store(): WeakMap
    {
        if (self::$store === null)
            self::$store = new WeakMap();
        return self::$store;
    }

    public static function attach(object $obj, string $key, mixed $value): void
    {
        $map = self::store();
        if (!isset($map[$obj]))
            $map[$obj] = [];

        $data = $map[$obj];
        $data[$key] = $value;
        $map[$obj] = $data;
    }

    public static function get(object $obj, string $key, mixed $default = null): mixed
    {
        $map = self::store();
        if (!isset($map[$obj]))
            return $default;
        return $map[$obj][$key] ?? $default;
    }

    public static function all(object $obj): array
    {
        return self::store()[$obj] ?? [];
    }
}

// ─────────────────────────────────────────────
// 13. Dynamic proxy (__call / __get / __set / __isset / __unset)
// ─────────────────────────────────────────────
class DynamicProxy
{
    private array $data     = [];
    private array $methods  = [];
    private array $callLog  = [];

    public function bind(string $name, \Closure $fn): self
    {
        $this->methods[$name] = $fn->bindTo($this, static::class);
        return $this;
    }

    public function __call(string $name, array $arguments): mixed
    {
        $this->callLog[] = ['method' => $name, 'args' => $arguments, 'time' => microtime(true)];

        if (isset($this->methods[$name]))
            return ($this->methods[$name])(...$arguments);

        // Auto getter/setter
        if (str_starts_with($name, 'get')) {
            $prop = lcfirst(substr($name, 3));
            return $this->data[$prop] ?? null;
        } elseif (str_starts_with($name, 'set')) {
            $prop = lcfirst(substr($name, 3));
            $this->data[$prop] = $arguments[0] ?? null;
            return $this;
        }

        throw new \BadMethodCallException("Method {$name} not found");
    }

    public function __get(string $name): mixed       { return $this->data[$name] ?? null; }
    public function __set(string $name, mixed $value): void { $this->data[$name] = $value; }
    public function __isset(string $name): bool      { return isset($this->data[$name]); }
    public function __unset(string $name): void      { unset($this->data[$name]); }

    public function getCallLog(): array { return $this->callLog; }
}

// ─────────────────────────────────────────────
// 14. Super complex control flow function
// ─────────────────────────────────────────────
function complexControlFlow(int $n): array
{
    $results = [];

    // Nested for + while + do-while + switch + match + goto
    for ($i = 0; $i < $n; $i++) {
        $j = $i;
        while ($j > 0) {
            do {
                switch ($j % 5) {
                    case 0:
                        $results[] = "fizz-{$i}-{$j}";
                        break;
                    case 1:
                        if ($i % 2 === 0)
                            $results[] = "even-one-{$i}";
                        else
                            $results[] = "odd-one-{$i}";
                        break;
                    case 2:
                        for ($k = 0; $k < 3; $k++) {
                            if ($k === 1)
                                continue 2; // continue to do-while
                            $results[] = "inner-{$k}";
                        }
                        break;
                    case 3:
                        $val = match (true) {
                            $i > 10   => 'big',
                            $i > 5    => 'medium',
                            $i > 0    => 'small',
                            default   => 'zero',
                        };
                        $results[] = "{$val}-{$i}";
                        break;
                    default:
                        try {
                            if ($j === 4)
                                throw new \OverflowException("boom at {$j}");
                            $results[] = "default-{$j}";
                        } catch (\OverflowException $e) {
                            $results[] = "caught-{$e->getMessage()}";
                        } catch (\RuntimeException | \LogicException $e) {
                            $results[] = "multi-catch";
                        } finally {
                            $results[] = "finally-{$j}";
                        }
                }
                $j--;
            } while ($j > 0 && $j % 3 !== 0);

            if ($j <= 0)
                break;
            $j--;
        }
    }

    // Nested ternary + null coalesce + arrow function
    $transform = fn($x) => ($x > 50 ? 'high' : ($x > 25 ? 'mid' : 'low')) ?? 'none';
    $results[] = $transform(count($results));

    // Immediately invoked closure (IIFE)
    $results[] = (function () use ($n) {
        $sum = 0;
        for ($i = 1; $i <= $n; $i++) {
            $sum += $i;
            if ($sum > 1000) {
                return "overflow-at-{$i}";
            }
        }
        return "sum={$sum}";
    })();

    // Multi-level nested closure
    $builder = function (int $depth) use (&$builder): callable {
        if ($depth <= 0)
            return fn($x) => $x;

        return function ($x) use ($depth, $builder) {
            $inner = $builder($depth - 1);
            return $inner($x * 2 + $depth);
        };
    };
    $results[] = $builder(5)(1);

    return $results;
}

// ─────────────────────────────────────────────
// 15. Exception chain + custom exception hierarchy
// ─────────────────────────────────────────────
class AppException extends \RuntimeException
{
    private array $context;

    public function __construct(string $message, array $context = [], int $code = 0, ?\Throwable $previous = null)
    {
        parent::__construct($message, $code, $previous);
        $this->context = $context;
    }

    public function getContext(): array { return $this->context; }
}

class ValidationException extends AppException {}
class AuthorizationException extends AppException {}
class NotFoundException extends AppException
{
    public static function forEntity(string $type, string|int $id): self
    {
        return new self("{$type} not found", ['entity' => $type, 'id' => $id], 404);
    }
}

function exceptionChainDemo(): void
{
    try {
        try {
            try {
                throw new \InvalidArgumentException("root cause");
            } catch (\InvalidArgumentException $e) {
                throw new ValidationException("validation failed", ['field' => 'email'], 422, $e);
            }
        } catch (ValidationException $e) {
            throw new AppException("request failed", ['request_id' => uniqid()], 500, $e);
        }
    } catch (AppException $e) {
        $chain = [];
        $current = $e;
        while ($current !== null) {
            $chain[] = [
                'class'   => get_class($current),
                'message' => $current->getMessage(),
                'code'    => $current->getCode(),
            ];
            $current = $current->getPrevious();
        }
        // Traverse exception chain
        foreach ($chain as $idx => $info) {
            if ($idx === 0)
                continue;
            if ($info['code'] >= 500)
                throw $e;  // rethrow
        }
    }
}

// ─────────────────────────────────────────────
// 16. Main entry point – integrates all tests
// ─────────────────────────────────────────────
function main(): void
{
    echo "=== Stress Test Start ===\n\n";

    // --- Enum test ---
    echo "[Enums]\n";
    foreach (Priority::cases() as $p) {
        $json = json_encode($p);
        echo "  {$p->name} => {$json}\n";
    }
    echo "  fromLabel: " . Priority::fromLabel('ULTRA ⚡')->name . "\n";
    echo "  Suit color: " . Suit::Hearts->color() . "\n\n";

    // --- Task + Collection ---
    echo "[Tasks & Collection]\n";
    $root = new Task('root', 'Root Task', Priority::High);
    for ($i = 1; $i <= 5; $i++) {
        $sub = new Task("sub-{$i}", "Subtask {$i}", Priority::cases()[array_rand(Priority::cases())]);
        $sub->addTag('auto', "tag-{$i}");
        $root->addSubtask($sub);
    }

    // Depth-first
    echo "  DFS: ";
    foreach ($root->walkDepthFirst() as $task)
        echo $task->getId() . " ";
    echo "\n";

    // Breadth-first
    echo "  BFS: ";
    foreach ($root->walkBreadthFirst() as $task)
        echo $task->getId() . " ";
    echo "\n";

    // Pipeline
    $result = $root->pipe(
        fn(Task $t) => ['name' => (string)$t, 'tags' => $t->toArray()['tags']],
        fn(array $data) => array_merge($data, ['processed' => true]),
        fn(array $data) => json_encode($data),
    );
    echo "  Pipeline result: {$result}\n";

    // TypedCollection
    $collection = new TypedCollection(Task::class);
    foreach ($root->walkDepthFirst() as $task)
        $collection->append($task);

    $highPriority = $collection->filter(fn(Task $t) => $t->toArray()['priority'] === 'high-priority');
    echo "  High priority count: " . count($highPriority) . "\n";

    $names = $collection->map(fn(Task $t) => $t->toArray()['name']);
    echo "  Names: " . implode(', ', $names) . "\n";

    $grouped = $collection->groupBy(fn(Task $t) => $t->toArray()['priority']);
    foreach ($grouped as $priority => $group)
        echo "  Group [{$priority}]: " . count($group) . " tasks\n";

    $chunks = $collection->chunk(2);
    echo "  Chunks: " . count($chunks) . "\n\n";

    // --- Binary tree ---
    echo "[BinaryTree]\n";
    $tree = BinaryTree::fromSortedArray(range(1, 15));
    echo "  Height: " . $tree->height() . "\n";
    echo "  InOrder:    " . implode(' ', iterator_to_array($tree->inOrder())) . "\n";
    echo "  PreOrder:   " . implode(' ', iterator_to_array($tree->preOrder())) . "\n";
    echo "  PostOrder:  " . implode(' ', iterator_to_array($tree->postOrder())) . "\n";
    echo "  LevelOrder: " . implode(' ', iterator_to_array($tree->levelOrder())) . "\n";

    $sum = $tree->reduce(fn($acc, $val) => $acc + $val, 0);
    echo "  Sum: {$sum}\n";

    $mirrored = $tree->mirror();
    echo "  Mirrored InOrder: " . implode(' ', iterator_to_array($mirrored->inOrder())) . "\n\n";

    // --- Functional tools ---
    echo "[Functional]\n";
    $add = Fp::curry(fn($a, $b, $c) => $a + $b + $c);
    echo "  Curried add: " . $add(1)(2)(3) . "\n";

    $transform = Fp::compose(
        fn($x) => $x * 2,
        fn($x) => $x + 10,
        fn($x) => $x ** 2,
    );
    echo "  compose(3): " . $transform(3) . "\n";

    $pipe = Fp::pipeline(
        fn($x) => $x ** 2,
        fn($x) => $x + 10,
        fn($x) => $x * 2,
    );
    echo "  pipeline(3): " . $pipe(3) . "\n";

    $memoFib = Fp::memoize(function (int $n) use (&$memoFib): int {
        if ($n <= 1) return $n;
        return $memoFib($n - 1) + $memoFib($n - 2);
    });
    echo "  memoFib(20): " . $memoFib(20) . "\n";

    echo "  Fib first 10: " . implode(', ', Fp::take(Fp::fibonacci(), 10)) . "\n";

    $factorial = Fp::trampoline(function (int $n, int $acc = 1) use (&$factorial) {
        if ($n <= 1) return $acc;
        return fn() => $factorial($n - 1, $n * $acc);
    });
    echo "  Trampoline factorial(10): " . $factorial(10) . "\n\n";

    // --- State machine ---
    echo "[StateMachine]\n";
    $sm = new StateMachine('idle');
    $sm->addTransition('idle', 'start', 'running')
       ->addTransition('running', 'pause', 'paused')
       ->addTransition('paused', 'resume', 'running')
       ->addTransition('running', 'complete', 'done', fn($ctx) => ($ctx['progress'] ?? 0) >= 100)
       ->addTransition('running', 'error', 'failed')
       ->onEnter('running', fn($from, $to, $event) => null)
       ->onExit('running', fn($from, $to, $event) => null);

    $sm->send('start');
    echo "  After start: {$sm->getState()}\n";
    $sm->send('pause');
    echo "  After pause: {$sm->getState()}\n";
    $sm->send('resume');
    echo "  After resume: {$sm->getState()}\n";
    $ok = $sm->send('complete', ['progress' => 100]);
    echo "  After complete (100%): {$sm->getState()} (success={$ok})\n\n";

    // --- Observable ---
    echo "[Observable]\n";
    $obs = Observable::fromArray(range(1, 20))
        ->filter(fn($x) => $x % 2 === 0)
        ->map(fn($x) => $x ** 2)
        ->take(5);
    echo "  Even squares (first 5): " . implode(', ', $obs->toArray()) . "\n";

    $sum = Observable::fromGenerator(Fp::lazyRange(1, 100))
        ->reduce(fn($acc, $x) => $acc + $x, 0)
        ->toArray();
    echo "  Sum 1-100: " . ($sum[0] ?? '?') . "\n\n";

    // --- Dynamic proxy ---
    echo "[DynamicProxy]\n";
    $proxy = new DynamicProxy();
    $proxy->bind('greet', function (string $name): string {
        return "Hello, {$name}!";
    });
    echo "  " . $proxy->greet('World') . "\n";
    $proxy->setFoo('bar');
    echo "  getFoo: " . $proxy->getFoo() . "\n";
    $proxy->magic = 42;
    echo "  magic: " . $proxy->magic . "\n";
    echo "  isset magic: " . (isset($proxy->magic) ? 'true' : 'false') . "\n";
    unset($proxy->magic);
    echo "  after unset magic: " . ($proxy->magic ?? 'null') . "\n\n";

    // --- WeakMap metadata ---
    echo "[MetadataRegistry]\n";
    $obj = new \stdClass();
    MetadataRegistry::attach($obj, 'created_by', 'stress_test');
    MetadataRegistry::attach($obj, 'version', 42);
    echo "  created_by: " . MetadataRegistry::get($obj, 'created_by') . "\n";
    echo "  all: " . json_encode(MetadataRegistry::all($obj)) . "\n\n";

    // --- Complex control flow ---
    echo "[Complex Control Flow]\n";
    $flowResults = complexControlFlow(8);
    echo "  Results count: " . count($flowResults) . "\n";
    echo "  First 5: " . implode(', ', array_slice($flowResults, 0, 5)) . "\n";
    echo "  Last: " . end($flowResults) . "\n\n";

    // --- Exception chain ---
    echo "[Exception Chain]\n";
    try {
        exceptionChainDemo();
        echo "  Exception chain handled gracefully.\n";
    } catch (\Throwable $e) {
        echo "  Propagated: {$e->getMessage()}\n";
    }
    echo "\n";

    // --- Fiber scheduler ---
    echo "[Fiber Scheduler]\n";
    $scheduler = new MicroScheduler();
    $log = [];

    $scheduler->spawn(function () use (&$log) {
        $log[] = 'A-start';
        Fiber::suspend(0.001); // sleep 1ms
        $log[] = 'A-resume';
        Fiber::suspend();
        $log[] = 'A-done';
    });

    $scheduler->spawn(function () use (&$log) {
        $log[] = 'B-start';
        for ($i = 0; $i < 3; $i++) {
            Fiber::suspend();
            $log[] = "B-tick-{$i}";
        }
        $log[] = 'B-done';
    });

    $scheduler->spawn(function () use (&$log) {
        $log[] = 'C-start';
        try {
            Fiber::suspend();
            $log[] = 'C-after-suspend';
            if (count($log) > 5)
                throw new \RuntimeException("C exploded");
            $log[] = 'C-ok';
        } catch (\RuntimeException $e) {
            $log[] = "C-caught-{$e->getMessage()}";
        } finally {
            $log[] = 'C-finally';
        }
    });

    $scheduler->run();
    echo "  Schedule log: " . implode(' → ', $log) . "\n";
    echo "  Total ticks: " . $scheduler->getTickCount() . "\n\n";

    echo "=== Stress Test Complete ===\n";
}

// Run
main();