
from dataclasses import dataclass

from pglast import parse_sql
from pglast.ast import SelectStmt
from pglast.visitors import Visitor


@dataclass(frozen=True, slots=True)
class ValidationResult:
    accepted: bool
    reason: str


class _RowLockVisitor(Visitor):
    """Find row-locking clauses anywhere in the SQL AST."""

    def __init__(self) -> None:
        self.found = False

    def visit_SelectStmt(self, ancestors, node: SelectStmt) -> None:
        if node.lockingClause:
            self.found = True


def validate_select(sql: str) -> ValidationResult:
    """Accept one SELECT statement with no row-level locking clauses."""
    try:
        statements = parse_sql(sql)
    except Exception:
        return ValidationResult(False, "SQL parsing failed.")

    if len(statements) != 1:
        return ValidationResult(
            False, "Exactly one SQL statement is required."
        )

    statement = statements[0].stmt

    if not isinstance(statement, SelectStmt):
        return ValidationResult(False, "Only SELECT statements are allowed.")

    visitor = _RowLockVisitor()
    visitor(statement)

    if visitor.found:
        return ValidationResult(
            False, "Row-locking SELECT statements are not allowed."
        )

    return ValidationResult(True, "Accepted SELECT statement.")


class _ParameterVisitor(Visitor):
    """Find actual PostgreSQL parameter references in an AST."""

    def __init__(self) -> None:
        self.found = False

    def visit_ParamRef(self, ancestors, node) -> None:
        self.found = True


def contains_parameter_reference(sql: str) -> bool:
    """Return True if SQL contains an actual parameter such as $1."""
    try:
        statements = parse_sql(sql)
    except Exception:
        # Fail closed if the SQL cannot be parsed.
        return True

    visitor = _ParameterVisitor()

    for statement in statements:
        visitor(statement.stmt)

    return visitor.found
