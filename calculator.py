"""Orion calculator - turns natural spoken maths into real answers.

Everything is parsed and evaluated safely (AST whitelist only),
so Orion can never execute arbitrary code through a voice command.
"""

import ast
import math
import re

# ------------------------------------------------------------------
# Spoken numbers -> digits
# ------------------------------------------------------------------

ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20
}

TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90
}

SCALES = {
    "hundred": 100, "thousand": 1000, "million": 1000000,
    "billion": 1000000000, "trillion": 1000000000000
}

WORD_NUMBERS = {}
WORD_NUMBERS.update(ONES)
WORD_NUMBERS.update(TENS)
WORD_NUMBERS.update(SCALES)


def words_to_number(phrase):
    """Convert an English number phrase like 'two hundred five' to int.

    Returns None when the phrase is not a valid number.
    """
    tokens = phrase.strip().lower().replace(" and ", " ").split()
    if not tokens:
        return None

    result = 0
    current = 0
    for token in tokens:
        if token in ONES:
            current += ONES[token]
        elif token in TENS:
            current += TENS[token]
        elif token in SCALES:
            scale = SCALES[token]
            if current == 0:
                current = 1
            current *= scale
            result += current
            current = 0
        else:
            # "percent" is a unit, not a number - drop the whole phrase.
            return None

    return result + current


def substitute_numbers(command):
    """Replace spoken number words with digit tokens so regex keeps working."""
    tokens = command.lower().split()
    output = []
    index = 0

    while index < len(tokens):
        # Greedily consume the longest phrase that is a number.
        best_end = index
        best_value = None
        for end in range(index + 1, min(index + 5, len(tokens)) + 1):
            value = words_to_number(" ".join(tokens[index:end]))
            if value is not None:
                best_end = end
                best_value = value

        if best_value is not None:
            output.append(str(best_value))
            index = best_end
        else:
            output.append(tokens[index])
            index += 1

    return " ".join(output)


def _extract_numbers(command):
    """All digit numbers in a command, in spoken order, as (value, position_start)."""
    numbers = []
    for match in re.finditer(r"[+-]?\d+(?:\.\d+)?", command):
        raw = match.group(0)
        numbers.append((float(raw) if "." in raw else int(raw), match.start()))
    return numbers


# ------------------------------------------------------------------
# Safe evaluation
# ------------------------------------------------------------------

def safe_eval(expression):
    """Evaluate a pure arithmetic expression using a whitelist AST."""
    expression = expression.replace("^", "**").replace("x", "*")
    expression = re.sub(r"([0-9])\s+([0-9])", r"\1*\2", expression)

    tree = ast.parse(expression, mode="eval")

    allowed = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
        ast.USub, ast.UAdd, ast.Call, ast.Name, ast.Load
    )

    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError("Unsupported expression")

    namespace = {
        "sqrt": math.sqrt, "abs": abs, "math": math,
        "pi": math.pi, "e": math.e
    }
    return eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}}, namespace)


def format_number(value):
    """Pretty-print a numeric answer for speech."""
    try:
        if value != value or value in (float("inf"), float("-inf")):
            return None
        if abs(value - round(value)) < 1e-9:
            return f"{int(round(value)):,}"
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError, OverflowError):
        return None


# ------------------------------------------------------------------
# Operation detection from language
# ------------------------------------------------------------------

def _detect_operation(command):
    if "square root" in command or re.search(r"\bsqrt\b", command):
        return "root"
    if "percent" in command or "%" in command:
        if re.search(r"percent\s*off", command):
            return "percent_off"
        return "percent_of"
    if "power" in command or "^" in command:
        return "power"
    if "divided" in command or "divide" in command or "divided by" in command or "over" in command:
        return "divide"
    if "multiply" in command or "multiplied" in command or "times" in command or "multiply" in command:
        return "multiply"
    if "minus" in command or "subtract" in command or "take away" in command:
        return "subtract"
    if "plus" in command or "add" in command or "sum" in command or "total of" in command:
        return "add"
    return None


def _build_expression(command, numbers):
    """Build a safe expression string from numbers + detected operation."""
    op = _detect_operation(command)
    if not op:
        return None
    if not numbers:
        return None

    first = numbers[0][0]
    second = numbers[1][0] if len(numbers) > 1 else None

    if op == "root":
        return f"sqrt({first})"
    if op == "percent_of":
        base = second if second is not None else first
        return f"({first}/100.0)*{base}"
    if op == "percent_off":
        base = second if second is not None else first
        return f"{base} - ({first}/100.0)*{base}"
    if op == "power":
        second = second if second is not None else 1
        return f"{first}**{second}"
    if second is None:
        return None
    if op == "divide":
        return f"{first}/{second}"
    if op == "multiply":
        return f"{first}*{second}"
    if op == "subtract":
        # "subtract 3 from 10" means 10 - 3
        if "from" in command and re.search(r"subtract\b", command):
            return f"{second} - {first}"
        return f"{first} - {second}"
    if op == "add":
        return f"{first} + {second}"
    return None


def try_calculate(command):
    """Return a spoken answer string if the command is maths, else None."""
    if not command:
        return None

    command = command.lower().strip()

    # Pure symbol expression like "5+3", "10/2", "2^3"
    plain = command
    for phrase in ("calculate", "compute", "what is", "what's", "solve",
                   "equals", "is equal to", "math", "please"):
        plain = plain.replace(phrase, "")
    plain = plain.strip()

    if re.fullmatch(r"[0-9+\-*/%^().\s]+", plain):
        try:
            value = safe_eval(plain)
            answer = format_number(value)
            return f"The answer is {answer}." if answer else None
        except Exception:
            pass

    substituted = substitute_numbers(command)

    # Longest phrase match of a two-number operation
    binary_patterns = [
        r"(\d+(?:\.\d+)?)\s*(?:divided\s*by|divide|over)\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*(?:multiplied\s*by|times|multiply)\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*(?:minus|subtract|take\s*away)\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*(?:plus|add|added\s*to)\s*(\d+(?:\.\d+)?)",
        r"(?:add|sum\s*of|total\s*of)\s*(\d+(?:\.\d+)?)\s*(?:and|to|plus)\s*(\d+(?:\.\d+)?)",
        r"(?:subtract)\s*(\d+(?:\.\d+)?)\s*from\s*(\d+(?:\.\d+)?)",
        r"(?:multiply)\s*(\d+(?:\.\d+)?)\s*by\s*(\d+(?:\.\d+)?)",
        r"(?:divide)\s*(\d+(?:\.\d+)?)\s*by\s*(\d+(?:\.\d+)?)",
        r"(?:square\s*root\s*of|sqrt\s*of|sqrt)\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*(?:to\s*the\s*power\s*of|power\s*of|\^)\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*percent\s*(?:off|of)\s*(\d+(?:\.\d+)?)",
    ]

    for pattern in binary_patterns:
        match = re.search(pattern, substituted)
        if match:
            groups = [float(g) if "." in g else int(g) for g in match.groups()]

            if "square root" in substituted or "sqrt" in substituted:
                expr = f"sqrt({groups[0]})"
            elif "percent" in substituted:
                if "off" in substituted:
                    expr = f"{groups[1]} - ({groups[0]}/100.0)*{groups[1]}"
                else:
                    expr = f"({groups[0]}/100.0)*{groups[1]}"
            elif "power" in substituted or "^" in substituted:
                expr = f"{groups[0]}**{groups[1]}"
            elif "divide" in substituted:
                expr = f"{groups[0]}/{groups[1]}"
            elif "times" in substituted or "multiply" in substituted:
                expr = f"{groups[0]}*{groups[1]}"
            elif "minus" in substituted or "take away" in substituted or "subtract" in substituted:
                if "subtract" in substituted and "from" in substituted:
                    expr = f"{groups[1]} - {groups[0]}"
                else:
                    expr = f"{groups[0]} - {groups[1]}"
            else:
                expr = f"{groups[0]} + {groups[1]}"

            try:
                value = safe_eval(expr)
                answer = format_number(value)
                return f"The answer is {answer}." if answer else None
            except (ValueError, ZeroDivisionError, OverflowError):
                return "That calculation is not something I can do."

    # Fall back to keyword detection for unusual phrasings
    numbers = _extract_numbers(substituted)
    expression = _build_expression(substituted, numbers)
    if expression:
        try:
            value = safe_eval(expression)
            answer = format_number(value)
            return f"The answer is {answer}." if answer else None
        except (ValueError, ZeroDivisionError, OverflowError):
            return "That calculation is not something I can do."

    return None