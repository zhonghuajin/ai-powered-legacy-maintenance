from __future__ import absolute_import, \
    division

from __future__ import (
    print_function,
    unicode_literals
)

import os
import asyncio

GLOBAL_LAMBDA = lambda x: x ** 2 if x > 0 else -1

class ComplexClass:
    def __init__(self, value):

        self.value = value
        self.data = [1, 2, 3, 4, 5]

    @property
    def computed_value(self):

        if self.value > 100:
            return self.value * 2
        elif self.value < 0:
            return 0
        else:
            return self.value

    async def async_generator(self):

        async for i in self._mock_async_iter():
            if i % 2 == 0:
                yield i
            else:
                continue

    async def _mock_async_iter(self):
        for i in self.data:
            await asyncio.sleep(0.1)
            yield i

def deeply_nested_control_flow(x):

    result = []
    try:
        if x > 0:
            for i in range(x):
                while i > 0:
                    if i == 5:
                        result.append("five")
                        break
                    elif i == 3:
                        i -= 1
                        continue
                    else:
                        i -= 2
        else:
            pass
    except ValueError as ve:
        print(f"ValueError caught: {ve}")
    except Exception:

        pass
    finally:

        result.append("done")

    return result

def test_comprehensions():

    funcs = [lambda x=i: x*2 for i in range(10) if i % 2 == 0]
    return [f() for f in funcs]

def empty_function_with_docstring():
    """只有文档字符串的函数，测试 node.body 插入"""
    pass

async def main():

    obj = ComplexClass(50)

    try:
        async for val in obj.async_generator():
            if val > 2:
                print(f"Value: {val}")
    except StopAsyncIteration:
        pass

if __name__ == "__main__":

    if True:
        deeply_nested_control_flow(10)
        test_comprehensions()
        asyncio.run(main())