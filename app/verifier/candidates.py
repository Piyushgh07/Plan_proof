"""Validate structured index candidates before database verification."""

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IndexCandidate:
    """An index proposal expressed as data, not executable SQL."""

    table_name: str
    columns: tuple[str, ...]
    operator_classes: tuple[str | None, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """The outcome of candidate validation."""

    accepted: bool
    reason: str


# Explicit allowlist based on docker/benchmark/schema.sql.
ALLOWED_SCHEMA: dict[str, frozenset[str]] = {
    "users": frozenset({
        "id", "email", "country", "is_active", "created_at",
    }),
    "products": frozenset({
        "id", "category", "name", "price",
        "stock_quantity", "created_at",
    }),
    "orders": frozenset({
        "id", "user_id", "status", "total_amount", "created_at",
    }),
    "order_items": frozenset({
        "id", "order_id", "product_id", "quantity", "unit_price",
    }),
    "events": frozenset({
        "id", "user_id", "event_type", "occurred_at", "payload",
    }),
}

_IDENTIFIER_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

# Only explicitly supported PostgreSQL operator classes.
ALLOWED_OPERATOR_CLASSES: dict[str, frozenset[str]] = {
    "text": frozenset({"text_pattern_ops"}),
    "varchar": frozenset({"varchar_pattern_ops"}),
}


def validate_index_candidate(
    candidate: IndexCandidate,
) -> ValidationResult:
    """Reject malformed candidates and unknown tables or columns."""

    if not isinstance(candidate, IndexCandidate):
        return ValidationResult(False, "Invalid candidate type.")

    table = candidate.table_name

    if not isinstance(table, str) or not _IDENTIFIER_PATTERN.fullmatch(table):
        return ValidationResult(False, "Invalid table identifier.")

    if table not in ALLOWED_SCHEMA:
        return ValidationResult(False, "Table is not allowlisted.")

    columns = candidate.columns

    if not isinstance(columns, tuple) or not columns:
        return ValidationResult(
            False, "At least one index column is required."
        )

    for column in columns:
        if not isinstance(column, str):
            return ValidationResult(False, "Invalid column identifier.")

        if not _IDENTIFIER_PATTERN.fullmatch(column):
            return ValidationResult(False, "Invalid column identifier.")

        if column not in ALLOWED_SCHEMA[table]:
            return ValidationResult(
                False, f"Column is not allowlisted for table '{table}'."
            )

    if len(columns) != len(set(columns)):
        return ValidationResult(False, "Duplicate columns are not allowed.")

    operator_classes = candidate.operator_classes

    # An empty tuple preserves compatibility with existing candidates.
    if not operator_classes:
        return ValidationResult(True, "Accepted index candidate.")

    if not isinstance(operator_classes, tuple):
        return ValidationResult(
            False, "Operator classes must be a tuple."
        )

    if len(operator_classes) != len(columns):
        return ValidationResult(
            False, "Operator classes must match the number of columns."
        )

    for column, operator_class in zip(columns, operator_classes):
        if operator_class is None:
            continue

        if not isinstance(operator_class, str):
            return ValidationResult(False, "Invalid operator class.")

        if not _IDENTIFIER_PATTERN.fullmatch(operator_class):
            return ValidationResult(False, "Invalid operator class.")

        if column == "name" and table == "products":
            if operator_class not in ALLOWED_OPERATOR_CLASSES["text"]:
                return ValidationResult(
                    False,
                    "Operator class is not allowlisted for products.name.",
                )
        else:
            return ValidationResult(
                False,
                f"Operator classes are not supported for "
                f"'{table}.{column}'.",
            )

    return ValidationResult(True, "Accepted index candidate.")
