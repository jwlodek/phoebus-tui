import pytest

from phoebus_tui.rules import RuleError, evaluate


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("!(pv0==0)", True),
        ("!(pv0!=0)", False),
        ("pv0 > 0 && pvStr0 == \"Done\"", True),
        ("pv0 == 0 || pvSev0 >= 1", False),
        ("pv0 === 1", True),
        ("pv0 !== 1", False),
        ("true && !false", True),
        ("null == null", True),
        ("pv0 * 2 + 1", 3),
        ("-pv0 < 0 && +pv0 > 0", True),
        ("pv0 % 2 == 1 && pv0 / 2 == 0.5", True),
        ("0 < pv0 < 2", True),
        ("0 < pv0 < 1", False),
        ("'a' == \"a\"", True),
    ],
)
def test_evaluate(expression, expected):
    assert evaluate(expression, {"pv0": 1, "pvStr0": "Done", "pvSev0": 0}) == expected


def test_operators_inside_strings_are_not_translated():
    assert evaluate('pvStr0 == "a && !b"', {"pvStr0": "a && !b"})


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os')",
        "pv0.__class__",
        "open('x')",
        "[x for x in ()]",
        "lambda: 1",
        "pv0 if pv0 else 0",
        "pv0 is None",
        "(",
    ],
)
def test_unsafe_or_invalid_expressions_are_rejected(expression):
    with pytest.raises(RuleError):
        evaluate(expression, {"pv0": 1})


def test_unknown_variable():
    with pytest.raises(RuleError, match="Unknown variable"):
        evaluate("pv1 == 0", {"pv0": 1})


def test_runtime_errors_become_rule_errors():
    with pytest.raises(RuleError):
        evaluate("pv0 / 0", {"pv0": 1})
    with pytest.raises(RuleError):
        evaluate("pvStr0 > 1", {"pvStr0": "x"})
