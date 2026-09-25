import numpy as np
import pytest

from core.safe_math import UnsafeExpressionError, safe_eval

X = np.linspace(-2, 2, 5)


@pytest.mark.parametrize(
    "expr, expected",
    [
        ("0.5*x**2 - 0.7", 0.5 * X**2 - 0.7),
        ("x^2 - 4*x + 3", X**2 - 4 * X + 3),
        ("-(x**2 - 1.4)**2 + 1.96", -((X**2 - 1.4) ** 2) + 1.96),
        ("sin(x) + np.cos(x) + math.exp(0)", np.sin(X) + np.cos(X) + 1),
        ("abs(x) * pi", np.abs(X) * np.pi),
        ("3", np.full_like(X, 3.0)),
    ],
)
def test_evaluates_math(expr, expected):
    np.testing.assert_allclose(safe_eval(expr, X), expected)


def test_log_of_negative_gives_nan_not_error():
    ys = safe_eval("ln(x)", X)
    assert np.isnan(ys[0]) and np.isclose(ys[-1], np.log(2))


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('echo hacked')",
        "().__class__.__bases__[0].__subclasses__()",
        "np.load('/etc/passwd')",
        "open('/etc/passwd')",
        "x.__class__",
        "[x for x in ()]",
        "lambda: 1",
        "y + 1",
        "sin(x, x)",
        "x" + "+x" * 400,
    ],
)
def test_rejects_unsafe_or_unknown(expr):
    with pytest.raises(UnsafeExpressionError):
        safe_eval(expr, X)


def test_huge_power_does_not_hang():
    ys = safe_eval("10**10**10", X)
    assert np.all(np.isinf(ys))
