# type: ignore
import ast
import functools
import re
from inspect import stack
from pathlib import Path

from .array import M


@functools.lru_cache(maxsize=10)
def argout_wrapper_decorators(nargout: int = 1):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            obj = func(*args, **kwargs)
            if nargout == 1:
                return M[obj]
            else:
                assert isinstance(obj, tuple)
                return tuple(M[o] for o in obj)

        return wrapper

    return decorator


def special_variables(value: float, name: str = ""):
    return value


@functools.lru_cache(maxsize=50)
def nargout_from_ast(s: str, func_name: str, co_filename=None, f_lineno=None):
    try:
        if s is None:
            raise SyntaxError
        tree = ast.parse(s.strip()).body[0]
    except SyntaxError:
        # ToDo: use a new method as lib2to3 not supported in pyodide
        from .metacode import GetStatement

        s = str(GetStatement(Path(co_filename).read_text(), f_lineno))
        tree = ast.parse(s.strip()).body[0]

    if (
        isinstance(tree, ast.Assign)
        and isinstance(tree.value, ast.Call)
        and tree.value.func.id == func_name
        and isinstance(
            tree.targets[0], ast.Tuple
        )  # `a, = func()` not allowed in matlab
    ):
        return len(tree.targets[0].elts)
    else:
        return 1


def nargout_from_stack():
    try:
        current, caller = stack()[1:3]
        frame = caller.frame
        code_context = "\n".join(caller.code_context).strip()
        return nargout_from_ast(
            code_context
            if re.match(r'[^\'"]+\s*=\s*' + current.function, code_context)
            else None,
            current.function,
            frame.f_code.co_filename,
            frame.f_lineno,
        )
    except (AttributeError, IndexError):
        return 1
