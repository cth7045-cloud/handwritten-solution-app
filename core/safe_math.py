"""
AI가 생성한 함수식(예: "0.5*x**2 - 0.7", "sin(x) + ln(x)")을 안전하게 계산하는 모듈.

AI 응답은 업로드된 이미지 속 글자에 의해 조작될 수 있으므로(프롬프트 인젝션),
파이썬 eval()로 실행하면 서버 코드 실행 취약점이 됩니다.
여기서는 AST를 직접 해석하여 사칙연산/거듭제곱/허용된 수학 함수만 계산합니다.
"""
import ast
import math
from typing import Callable, Dict, Union

import numpy as np

MAX_EXPR_LEN = 300
MAX_NODES = 200

_FUNCS: Dict[str, Callable] = {
    "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "arcsin": np.arcsin, "arccos": np.arccos, "arctan": np.arctan,
    "asin": np.arcsin, "acos": np.arccos, "atan": np.arctan,
    "sinh": np.sinh, "cosh": np.cosh, "tanh": np.tanh,
    "sqrt": np.sqrt, "exp": np.exp, "abs": np.abs, "fabs": np.abs,
    "log": np.log, "ln": np.log, "log10": np.log10, "log2": np.log2,
    "floor": np.floor, "ceil": np.ceil, "sign": np.sign,
}
_CONSTS = {"pi": math.pi, "e": math.e}
# "np.sin(x)", "math.log(x)" 처럼 모듈 접두어를 붙인 표현도 허용
_MODULE_PREFIXES = {"np", "numpy", "math"}

_BINOPS = {
    ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply,
    ast.Div: np.divide, ast.Pow: np.power, ast.Mod: np.mod,
}
_UNARYOPS = {ast.USub: np.negative, ast.UAdd: np.positive}

Number = Union[float, np.ndarray]


class UnsafeExpressionError(ValueError):
    pass


def _func_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in _MODULE_PREFIXES
    ):
        return node.attr
    raise UnsafeExpressionError("허용되지 않은 함수 호출")


def _eval(node: ast.AST, x: np.ndarray) -> Number:
    if isinstance(node, ast.Expression):
        return _eval(node.body, x)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        # 정수 거듭제곱 폭주(10**10**10)를 막기 위해 항상 float로 계산
        return np.float64(node.value)
    if isinstance(node, ast.Name):
        if node.id == "x":
            return x
        if node.id in _CONSTS:
            return np.float64(_CONSTS[node.id])
        raise UnsafeExpressionError(f"허용되지 않은 이름: {node.id}")
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id in _MODULE_PREFIXES and node.attr in _CONSTS:
            return np.float64(_CONSTS[node.attr])
        raise UnsafeExpressionError("허용되지 않은 속성 접근")
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval(node.left, x), _eval(node.right, x))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
        return _UNARYOPS[type(node.op)](_eval(node.operand, x))
    if isinstance(node, ast.Call) and not node.keywords and len(node.args) == 1:
        name = _func_name(node.func)
        if name not in _FUNCS:
            raise UnsafeExpressionError(f"허용되지 않은 함수: {name}")
        return _FUNCS[name](_eval(node.args[0], x))
    raise UnsafeExpressionError(f"허용되지 않은 구문: {type(node).__name__}")


def safe_eval(expr: str, x: np.ndarray) -> np.ndarray:
    """함수식을 x 배열에 대해 계산하여 같은 길이의 배열을 반환합니다."""
    s = str(expr or "").strip().replace("^", "**")
    if not s or len(s) > MAX_EXPR_LEN:
        raise UnsafeExpressionError("수식이 비어 있거나 너무 깁니다")
    try:
        tree = ast.parse(s, mode="eval")
    except SyntaxError as e:
        raise UnsafeExpressionError(f"수식 구문 오류: {e}") from e
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise UnsafeExpressionError("수식이 너무 복잡합니다")
    with np.errstate(all="ignore"):
        result = _eval(tree, np.asarray(x, dtype=np.float64))
    return np.broadcast_to(np.asarray(result, dtype=np.float64), np.shape(x)).copy()
