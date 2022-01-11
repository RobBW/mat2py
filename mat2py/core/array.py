# type: ignore
import typing
from typing import Callable, Tuple, Union

import operator
from functools import reduce
from itertools import chain

import numpy as np

__all__ = ["end", "I", "colon", "M", "array"]


class End:
    def __init__(self, expr=None):
        self.expr = expr if expr is not None else [None]

    def __call__(self, length: int) -> int:
        if length is None:
            raise ValueError("length can not be None when evaluating End")
        tokens = [length if i is None else i for i in self.expr]

        stack = []
        for token in tokens:
            if type(token).__name__ != "builtin_function_or_method":
                stack.append(token)
            else:
                if token is operator.neg:
                    stack.append(-stack.pop())
                else:
                    rhs = stack.pop()
                    stack[-1] = token(stack[-1], rhs)

        assert len(stack) == 1
        return round(stack[0])

    def __binary_operator(self, other: Union[int, "End"], op: typing.Callable) -> "End":
        rhs = other.expr if isinstance(other, self.__class__) else [other]
        return self.__class__([*self.expr, *rhs, op])

    def __radd__(self, other: int) -> "End":
        return self.__class__([other, *self.expr, operator.add])

    def __rsub__(self, other: (int, "End")) -> "End":
        return self.__class__([other, *self.expr, operator.sub])

    def __add__(self, other: (int, "End")) -> "End":
        return self.__binary_operator(other, operator.add)

    def __sub__(self, other: (int, "End")) -> "End":
        return self.__binary_operator(other, operator.sub)

    def __mod__(self, other: (int, "End")) -> "End":
        return self.__binary_operator(other, operator.mod)

    def __mul__(self, other: (int, "End")) -> "End":
        return self.__binary_operator(other, operator.mul)

    def __pow__(self, other: (int, "End")) -> "End":
        return self.__binary_operator(other, operator.pow)

    def __floordiv__(self, other: (int, "End")) -> "End":
        return self.__binary_operator(other, operator.floordiv)

    def __truediv__(self, other: (int, "End")) -> "End":
        return self.__binary_operator(other, operator.truediv)

    def __pos__(self) -> "End":
        return self

    def __neg__(self) -> "End":
        return self.__class__([*self.expr, operator.neg])


end = End()


class MatIndex:
    def __init__(self, index):
        self.item = index.item if isinstance(index, MatIndex) else index

    @staticmethod
    def __getitem__(item):
        return MatIndex(item)

    @staticmethod
    def __convert(
        item: ("Colon", slice, End, "MatIndex", int, np.ndarray), length: int
    ):
        if isinstance(item, Colon):
            return item.to_index(length)
        elif isinstance(item, slice):
            return colon(item).to_index(length)
        elif isinstance(item, End):
            return item(length) - 1
        elif isinstance(item, MatIndex):
            return item((length,))
        else:
            return item - 1

    def __call__(self, shape: Tuple[int]):
        item = self.item if isinstance(self.item, tuple) else (self.item,)

        if len(item) == len(shape):
            return tuple(self.__convert(i, l) for i, l in zip(item, shape))
        if len(item) == 1:  # line index
            return ind2sub(shape, self.__convert(item[0], reduce(operator.mul, shape)))
        elif len(self.item) < len(shape):
            raise NotImplementedError

        raise ValueError("index exceed the Array dimention")


I = MatIndex(None)


def ind2sub(shape: tuple, index: (typing.Iterable[int], int, slice)):
    if len(shape) == 1:
        return index
    elif len(shape) == 2:
        d1, _ = shape
        index = (
            np.array(index).reshape(-1)
            if not isinstance(index, slice)
            else np.arange(index.start, index.stop, index.step)
        )
        return index % d1, index // d1
    else:
        # TODO: take care of fortran order
        raise NotImplementedError


class MatArray(np.ndarray):
    """https://numpy.org/doc/stable/user/basics.subclassing.html"""

    def __call__(self, item, *rest_item):
        # TODO: we can not differicate `a(1)` and `a(1,)` while `a[1]` and `a[1,]` have difference
        item = [item, *rest_item] if rest_item else item
        return super().__getitem__(MatIndex(item)(self.shape))

    def __getitem__(self, item):
        if isinstance(item, End):
            item = MatIndex(item)
        if isinstance(item, MatIndex):
            item = item(self.shape)
        return super().__getitem__(item)

    def __setitem__(self, key, value):
        if isinstance(key, End):
            key = MatIndex(key)
        if isinstance(key, MatIndex):
            key = key(self.shape)
        if isinstance(value, Colon):
            value = value.view(MatArray)

        return super().__setitem__(key, value)


class MatCreator(object):
    @staticmethod
    def __getitem__(args):
        non_empty = lambda i: not (
            isinstance(i, (list, np.ndarray, tuple)) and len(i) == 0
        )
        filter_row = lambda r: (
            tuple(i for i in r if non_empty(i))
            if isinstance(r, (tuple, list))
            else ((r,) if non_empty(r) else tuple())
        )

        rows = tuple(
            np.hstack(
                tuple(
                    np.squeeze(i, axis=0)
                    if isinstance(i, np.ndarray) and i.shape[0] == 1
                    else i
                    for i in r
                )
            )
            for r in map(filter_row, (args if isinstance(args, tuple) else (args,)))
            if non_empty(r)
        )
        if non_empty(rows):
            return np.vstack(rows).view(MatArray)
        else:
            return np.array([]).view(MatArray)


M = MatCreator()


def array(*args, **kwargs):
    return np.array(*args, **kwargs).view(MatArray)


class ColonMeta(type):
    @staticmethod
    def method_wrapper(func, base):
        def f(self, *args, **kwargs):
            return func(self.view(base), *args, **kwargs)

        return f

    @staticmethod
    def property_wrapper(name, base):
        def get(self):
            return self.view(base).__getattribute__(name)

        def forbidden(*_, **__):
            raise NotImplementedError(f"can not set {name} directly")

        return property(fget=get, fset=forbidden, fdel=forbidden)

    @staticmethod
    def is_descriptor(obj):
        """obj can be instance of descriptor or the descriptor class"""
        return bool(set(["__get__", "__set__", "__delete__"]).intersection(dir(obj)))

    @staticmethod
    def is_data_descriptor(attr):
        return bool(set(["__set__", "__delete__"]) & set(dir(attr)))

    def __new__(mcs, name, bases, dct):
        base = bases[0]
        assert issubclass(base, np.ndarray)
        for key, value in chain.from_iterable(b.__dict__.items() for b in base.__mro__):

            if (
                key not in dct
                and (
                    not (key.startswith("__") and key.endswith("__"))
                    or key
                    in (
                        "__iter__",
                        "__getitem__",
                        "__setitem__",
                        "__call__",
                        "__repr__",
                        "__str__",
                        "__index__",
                    )
                )
                and (key not in ("dtype",))
            ):
                if mcs.is_data_descriptor(value):
                    dct[key] = mcs.property_wrapper(key, base)
                elif isinstance(value, Callable):
                    dct[key] = mcs.method_wrapper(value, base)

        return super().__new__(mcs, name, bases, dct)


class Colon(MatArray, metaclass=ColonMeta):
    """colon equivelent in Matlab"""

    """ It should be (start, stop) format or (start, step, stop) format. """
    """ Colon used for array indexing (1-based Matlab format) will be converted to slice (0-based Python format); """
    """ Colon used for generating sequence will be converted to np.arange while keeping the right end point."""

    def __new__(
        cls, start: (float, End), stop: (float, End), step: (float, End) = None
    ):
        assert start is not None and stop is not None
        __slice_expr = (  # in (start, stop, step) order
            start,
            stop,
            1 if step is None else step,
        )
        has_end = any(isinstance(expr, End) for expr in __slice_expr)

        obj = np.ndarray.__new__(
            Colon,
            (0,),  # lazy evaluation
            dtype=int if has_end else np.array(__slice_expr).dtype,
        )
        obj.__slice_expr = __slice_expr
        return obj

    def __array_finalize__(self, obj):
        # __new__ way
        if obj is None:
            return

        # slice or view way
        self.__slice_expr = None

    @property
    def size(self):
        if self.__slice_expr is not None:
            start, stop, step = self.__convert_to_slice()
            return np.floor((stop - start) / step).astype(int)
        else:
            return super().size

    def __contains_end(self):
        return self.__slice_expr is not None and any(
            isinstance(expr, End) for expr in self.__slice_expr
        )

    def __sub__(self, i: int):
        if self.__slice_expr is not None:
            start, stop, step = self.__slice_expr
            return self.__class__(start - i, stop - i, step)
        else:
            return self.view(MatArray).__sub__(i)

    def __convert_to_slice(self, length=None, eps=None) -> tuple:
        start, stop, step = self.__slice_expr
        has_end = self.__contains_end()

        if length is None and has_end:
            raise ValueError(
                "range can not contain end expression when length not provided"
            )

        elif has_end:
            start, stop, step = (
                expr(length) if isinstance(expr, End) else expr
                for expr in self.__slice_expr
            )

        stop += (
            (
                1
                if has_end or np.issubdtype(self.dtype, np.integer)
                else np.finfo(float).eps * 10.0
            )
            if eps is None
            else eps
        )

        return start, stop, step

    def to_index(self, length=None) -> slice:
        if self.__slice_expr is not None:
            start, stop, step = map(
                round, self.__convert_to_slice(length=length, eps=1)
            )
            start -= 1
            stop -= 1
            # TODO: validation on [1, length]
            if stop > length:
                raise ValueError(f"out of the dimension")
            if start < 0:
                raise ValueError(f"index must be positive integer")

            return slice(
                start,
                max(stop, start) if step > 0 else min(stop, start),
                step,
            )
        else:
            return np.round(super().view(MatArray)).astype(int) - 1

    def view(self, dtype=None, *args, **kwargs) -> MatArray:
        if self.__slice_expr is not None:
            start, stop, step = self.__convert_to_slice()

            obj = np.arange(start, stop, step)
            super().resize(obj.size, refcheck=False)
            super().view(obj.__class__).__setitem__(slice(None, None), obj)
            self.__slice_expr = None

        return super().view(MatArray).view(dtype, *args, **kwargs)

    def __array_ufunc__(self, ufunc, method, *inputs, out=None, **kwargs):
        new_inputs = tuple(
            i.view(MatArray) if isinstance(i, Colon) else i for i in inputs
        )
        new_out = tuple(i.view(MatArray) if isinstance(i, Colon) else i for i in out)
        return self.view(MatArray).__array_ufunc__(
            ufunc, method, *new_inputs, out=new_out, **kwargs
        )


def colon(*args):
    if len(args) == 2:
        return Colon(*args, 1)
    elif len(args) == 3:
        return Colon(args[0], args[2], args[1])
    if len(args) == 1 and isinstance(args[0], slice):
        item = args[0]
        if item.step is not None:
            return Colon(item.start, item.step, item.stop)
        else:
            return Colon(
                item.start if item.start is not None else 1,
                item.stop if item.stop is not None else end,
                1,
            )
    else:
        raise ValueError("colon can only accept i:k or i:j:k format")
