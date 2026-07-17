"""
Calculator Tool - Perform mathematical calculations
"""

from typing import Any

from .base import BaseTool


class CalculatorTool(BaseTool):
    """Tool for mathematical calculations"""

    # Allowed characters in math expressions
    ALLOWED_CHARS = set('0123456789+-*/().% ')

    async def execute(self, expression: str, **kwargs) -> dict[str, Any]:
        """
        Calculate mathematical expression

        Args:
            expression: Mathematical expression string

        Returns:
            Dictionary with calculation result
        """
        # Validate expression
        if not expression or not expression.strip():
            return {"error": "表达式不能为空"}

        # Check for allowed characters only
        cleaned = expression.replace(" ", "")
        if not all(c in self.ALLOWED_CHARS for c in cleaned):
            return {"error": "表达式包含不允许的字符"}

        try:
            # Safe evaluation using ast.literal_eval for simple expressions
            # For complex math, we use a restricted eval
            import ast
            import operator

            # Supported operators
            ops = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.Mod: operator.mod,
                ast.Pow: operator.pow,
                ast.USub: operator.neg,
            }

            def safe_eval(node):
                if isinstance(node, ast.Expression):
                    return safe_eval(node.body)
                elif isinstance(node, ast.Constant):
                    return node.value
                elif isinstance(node, ast.BinOp):
                    left = safe_eval(node.left)
                    right = safe_eval(node.right)
                    return ops[type(node.op)](left, right)
                elif isinstance(node, ast.UnaryOp):
                    operand = safe_eval(node.operand)
                    return ops[type(node.op)](operand)
                else:
                    raise ValueError(f"不支持的表达式类型: {type(node)}")

            # Parse and evaluate
            tree = ast.parse(expression, mode='eval')
            result = safe_eval(tree)

            return {
                "expression": expression,
                "result": result
            }

        except ZeroDivisionError:
            return {"error": "除数不能为零"}
        except Exception as e:
            return {"error": f"计算错误: {str(e)}"}
