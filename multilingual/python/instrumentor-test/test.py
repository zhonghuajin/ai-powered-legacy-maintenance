#!/usr/bin/env python3
"""
test.py - Test file for Python instrumentation.

Contains various Python patterns to verify instrumentation correctness:
- Classes with methods
- Control flow (if/elif/else, for, while)
- Exception handling (try/except/finally)
- Async functions
- Decorators
- Context managers
- Generators
- List comprehensions
- Lambda functions
- Nested functions / closures
"""

import asyncio
import threading
from contextlib import contextmanager


# ─────────────────────────────────────────────
# 1. Basic class with various method types
# ─────────────────────────────────────────────
class MathProcessor:
    """Process numbers with various mathematical operations."""

    def __init__(self, numbers):
        self.numbers = numbers
        self._cache = {}

    def process(self):
        """Process numbers with if-elif-else and for loop."""
        result = []
        for num in self.numbers:
            if num % 2 == 0:
                result.append(num * 2)
            elif num % 3 == 0:
                result.append(num * 3)
            else:
                result.append(num)
        return result

    def sum_with_while(self):
        """Calculate sum using while loop."""
        total = 0
        index = 0
        while index < len(self.numbers):
            total += self.numbers[index]
            index += 1
        return total

    @staticmethod
    def factorial(n):
        """Recursive factorial calculation."""
        if n <= 1:
            return 1
        else:
            return n * MathProcessor.factorial(n - 1)

    @classmethod
    def from_range(cls, start, end):
        """Create from a range."""
        return cls(list(range(start, end)))


# ─────────────────────────────────────────────
# 2. Exception handling patterns
# ─────────────────────────────────────────────
class DataProcessor:
    """Demonstrates try/except/finally patterns."""

    def safe_divide(self, a, b):
        try:
            result = a / b
        except ZeroDivisionError:
            print("Division by zero!")
            result = 0
        except TypeError:
            print("Invalid types!")
            result = None
        else:
            print(f"Result: {result}")
        finally:
            print("Division operation complete.")
        return result

    def process_items(self, items):
        """Process with nested try-except."""
        results = []
        for item in items:
            try:
                if isinstance(item, str):
                    results.append(int(item))
                elif isinstance(item, (int, float)):
                    results.append(item * 2)
                else:
                    raise ValueError(f"Unsupported type: {type(item)}")
            except (ValueError, TypeError) as e:
                print(f"Error processing {item}: {e}")
                results.append(None)
        return results


# ─────────────────────────────────────────────
# 3. Generator and context manager patterns
# ─────────────────────────────────────────────
def fibonacci_generator(limit):
    """Generator function for Fibonacci sequence."""
    a, b = 0, 1
    while a < limit:
        yield a
        a, b = b, a + b


@contextmanager
def timer_context(label):
    """Context manager for timing operations."""
    import time
    start = time.time()
    try:
        yield
    finally:
        elapsed = time.time() - start
        print(f"[{label}] Elapsed: {elapsed:.4f}s")


# ─────────────────────────────────────────────
# 4. Decorator patterns
# ─────────────────────────────────────────────
def retry(max_attempts=3):
    """Decorator that retries a function on failure."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    print(f"Attempt {attempt + 1} failed: {e}")
        return wrapper
    return decorator


# ─────────────────────────────────────────────
# 5. Async patterns
# ─────────────────────────────────────────────
async def fetch_data(source):
    """Simulate async data fetching."""
    await asyncio.sleep(0.1)
    if source == "error":
        raise ConnectionError("Failed to connect")
    return [1, 2, 3, 4, 5]


async def process_async():
    """Async function with try-except and await."""
    try:
        data = await fetch_data("ok")
        if data:
            processor = MathProcessor(data)
            result = processor.process()
            print(f"Async result: {result}")
            return result
    except ConnectionError as e:
        print(f"Connection error: {e}")
        return []


# ─────────────────────────────────────────────
# 6. Threading patterns
# ─────────────────────────────────────────────
class WorkerThread(threading.Thread):
    """Thread subclass for parallel processing."""

    def __init__(self, name, data):
        super().__init__(name=name)
        self.data = data
        self.result = None

    def run(self):
        """Thread execution with synchronization."""
        processor = MathProcessor(self.data)
        self.result = processor.process()
        print(f"Thread {self.name} completed with {len(self.result)} results")


# ─────────────────────────────────────────────
# 7. Nested functions and closures
# ─────────────────────────────────────────────
def create_counter(initial=0):
    """Closure that creates a counter."""
    count = initial

    def increment(step=1):
        nonlocal count
        count += step
        return count

    def decrement(step=1):
        nonlocal count
        count -= step
        return count

    def get_value():
        return count

    return increment, decrement, get_value


# ─────────────────────────────────────────────
# 8. With statement patterns
# ─────────────────────────────────────────────
def read_and_process(filepath):
    """File handling with context manager."""
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
            result = []
            for line in lines:
                stripped = line.strip()
                if stripped:
                    result.append(stripped.upper())
            return result
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        return []
    except PermissionError:
        print(f"Permission denied: {filepath}")
        return []


# ─────────────────────────────────────────────
# Main execution
# ─────────────────────────────────────────────
def main():
    """Main entry point running all test patterns."""
    print("=" * 50)
    print("Python Instrumentation Test")
    print("=" * 50)

    # Test 1: Basic processing
    print("\n--- Test 1: MathProcessor ---")
    processor = MathProcessor([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    result = processor.process()
    print(f"Processed: {result}")
    print(f"Sum: {processor.sum_with_while()}")
    print(f"Factorial(5): {MathProcessor.factorial(5)}")

    # Test 2: Exception handling
    print("\n--- Test 2: DataProcessor ---")
    dp = DataProcessor()
    dp.safe_divide(10, 3)
    dp.safe_divide(10, 0)
    dp.process_items([1, "2", "abc", 3.5, None])

    # Test 3: Generator
    print("\n--- Test 3: Fibonacci Generator ---")
    fibs = list(fibonacci_generator(100))
    print(f"Fibonacci: {fibs}")

    # Test 4: Context manager
    print("\n--- Test 4: Timer Context ---")
    with timer_context("test"):
        total = sum(range(10000))
        print(f"Sum: {total}")

    # Test 5: Closures
    print("\n--- Test 5: Closures ---")
    inc, dec, get = create_counter(10)
    print(f"Initial: {get()}")
    print(f"After +5: {inc(5)}")
    print(f"After -3: {dec(3)}")

    # Test 6: Threading
    print("\n--- Test 6: Threading ---")
    threads = [
        WorkerThread("Worker-1", [1, 2, 3]),
        WorkerThread("Worker-2", [4, 5, 6]),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Test 7: Async
    print("\n--- Test 7: Async ---")
    asyncio.run(process_async())

    # Test 8: Range-based creation
    print("\n--- Test 8: Class Methods ---")
    mp = MathProcessor.from_range(1, 6)
    print(f"From range: {mp.process()}")

    print("\n" + "=" * 50)
    print("All tests completed!")
    print("=" * 50)


if __name__ == '__main__':
    main()
