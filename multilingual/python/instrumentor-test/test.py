

import asyncio

def empty_function():
    pass

def single_line_function(x): return x * 2

def my_decorator(func):
    def wrapper(*args, **kwargs):

        return func(*args, **kwargs)
    return wrapper

@my_decorator
def decorated_function(a, b=[]):
    if not b:
        b.append(a)
    return b

async def async_worker(items):
    async for item in items:
        if item % 2 == 0:
            await asyncio.sleep(0.01)
        else:
            continue

def deep_nested_control_flow(x, y):
    result = []
    if x > 0:
        if y > 0:
            for i in range(3):
                try:
                    val = x / (y - i)
                except ZeroDivisionError:

                    result.append("zero")
                except (TypeError, ValueError) as e:

                    result.append(f"err: {e}")
                else:

                    result.append(val)
                finally:

                    result.append("done_step")
            else:

                result.append("for_completed")
        elif y == 0:

            while x > 0:
                x -= 1
                if x == 2:
                    break
            else:

                result.append("while_completed")
        else:

            result.append("y_negative")
    else:

        result.append("x_non_positive")
    return result

class BaseClass:
    def __init__(self, val):
        self.val = val

class ComplexClass(BaseClass):
    class_var = "static"

    def __init__(self, val, name="test"):
        super().__init__(val)
        self.name = name

    @classmethod
    def class_method(cls):
        return cls.class_var

    @staticmethod
    def static_method():
        return "static_val"

    @property
    def info(self):

        if self.val > 10:
            return "high"
        return "low"

    def complex_generator(self):

        for i in range(self.val):
            yield i

def extreme_edge_cases():

    x = 1 if True else 0

    if x == 1:
        pass
    elif x == 2:
        pass
    else:
        pass

    try:
        raise ValueError()
    except ValueError:
        pass
    except KeyError:
        pass
    except:
        pass