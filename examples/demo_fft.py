# type: ignore
import mat2py as mp
from mat2py.core import *


# sinc belongs to the signal package
def sinc(x):
    i = find(x == 0)
    x[I[i]] = 1
    y = sin(pi @ M[x]) / (pi @ M[x])
    y[I[i]] = 1
    return y


def my_fft(x):
    N = numel(x)
    xp = x[I[1:2:end]]
    xpp = x[I[2:2:end]]
    if N >= 8:
        Xp = my_fft(xp)
        Xpp = my_fft(xpp)
        Wn = exp(mrdivide((((-1j) * 2) * pi) @ ((M[0 : ((N / 2) - 1)]).H), N))
        tmp = Wn * Xpp
        X = M[
            Xp + tmp,
            Xp - tmp,
        ]
    else:
        if N == 2:
            X = (
                M[
                    [1, 1],
                    [1, -1],
                ]
            ) @ x
        elif N == 4:
            X = (
                (
                    M[
                        [1, 0, 1, 0],
                        [0, 1, 0, -1j],
                        [1, 0, -1, 0],
                        [0, 1, 0, 1j],
                    ]
                )
                @ (
                    M[
                        [1, 0, 1, 0],
                        [1, 0, -1, 0],
                        [0, 1, 0, 1],
                        [0, 1, 0, -1],
                    ]
                )
            ) @ M[x]
        else:
            error("N not correct.")
    return X


def demo_fft():
    clear
    clc
    rng("default")
    t = M[1:10]
    x = randn(size(t)).H
    ts = linspace(-5, 15, 2 ** 9)
    Ts, T = ndgrid(ts, t)
    y = sinc(Ts - T) @ M[x]
    f = my_fft(y)
    disp(M[[y, f]])


if __name__ == "__main__":
    demo_fft()
