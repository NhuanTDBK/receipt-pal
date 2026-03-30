"""Dynamic schema generator for SQLAlchemy models.

Generates markdown table documentation from SQLAlchemy models
to inject into the analytics system prompt.
"""

from __future__ import annotations

from typing import Any, Type

from sqlalchemy.orm import DeclarativeBase, class_mapper

from app.models import Receipt, ReceiptItem, User


def _get_foreign_key_ref(column: Any) -> str | None:
    """Get the foreign key reference if present."""
    if column.foreign_keys:
        fk = list(column.foreign_keys)[0]
        return f" → {fk.target_fullname}"
    return None


def generate_model_schema(model_class: Type[DeclarativeBase]) -> str:
    """Generate markdown table documentation for a SQLAlchemy model.

    Args:
        model_class: A SQLAlchemy declarative model class

    Returns:
        Markdown formatted table row string for the model
    """
    mapper = class_mapper(model_class)

    lines = []
    lines.append("| Column | Type | Description |")
    lines.append("|--------|------|-------------|")

    for column in mapper.columns:
        col_name = column.name
        col_type = str(column.type)

        # Build description
        descriptions = []

        # Check for foreign keys
        fk_ref = _get_foreign_key_ref(column)
        if fk_ref:
            descriptions.append(f"FK{fk_ref}")

        # Check for primary key
        if column.primary_key:
            descriptions.append("PK")

        # Check for index
        if column.index:
            descriptions.append("indexed")

        # Check for nullable
        if not column.nullable:
            descriptions.append("required")
        else:
            descriptions.append("nullable")

        # Check for default
        if column.default is not None:
            if hasattr(column.default, "arg"):
                default_val = column.default.arg
                if callable(default_val):
                    descriptions.append(f"default: {default_val.__name__}()")
                else:
                    descriptions.append(f"default: {default_val}")

        description = ", ".join(descriptions)
        lines.append(f"| `{col_name}` | {col_type} | {description} |")

    return "\n".join(lines)


def generate_all_schemas() -> str:
    """Generate schema documentation for all analytics-relevant models.

    Returns:
        Markdown formatted schema documentation
    """
    sections = []

    sections.append("## Database Schema (Auto-Generated from Models)")
    sections.append("")
    sections.append("The following tables are available for SQL queries:")
    sections.append("")

    # Generate schemas for each model
    models = [
        ("receipts", Receipt),
        ("receipt_items", ReceiptItem),
        ("users", User),
    ]

    for table_name, model_class in models:
        sections.append(f"### `{table_name}`")
        sections.append("")
        sections.append(generate_model_schema(model_class))
        sections.append("")

    return "\n".join(sections)


def build_analytics_prompt(base_prompt_path: str) -> str:
    """Build the full analytics prompt with dynamic schema.

    Args:
        base_prompt_path: Path to the base system prompt markdown file

    Returns:
        Complete prompt with base content + dynamic schema
    """
    from pathlib import Path

    base_prompt = Path(base_prompt_path).read_text(encoding="utf-8")
    dynamic_schema = generate_all_schemas()

    return f"{base_prompt}\n\n---\n\n{dynamic_schema}"
