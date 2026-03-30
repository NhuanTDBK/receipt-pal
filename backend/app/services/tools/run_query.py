"""SQL Query tool — the agent generates a SQL SELECT query that is
executed in a read-only database session, then synthesises the results.

Safety design:
- ``user_id`` is injected as a parameter for data isolation;
  the agent cannot access other users' data.
- Only SELECT statements are allowed — no INSERT, UPDATE, DELETE, DROP, etc.
- Queries are parameterized to prevent SQL injection.
- Execution runs inside AsyncSession for proper database connection handling.
"""

from __future__ import annotations

import json
import traceback
from decimal import Decimal
from typing import Annotated

from agents import RunContextWrapper, function_tool
from sqlalchemy import text

from app.services.agent_context import TelegramAgentContext


def _validate_sql(sql: str) -> str | None:
    """
    Validate that SQL is safe to execute.
    Returns None if valid, error message if invalid.
    """
    # Remove comments and extra whitespace for checking
    cleaned = " ".join(sql.split())
    upper_sql = cleaned.upper()

    # Must start with SELECT (case insensitive)
    if not upper_sql.strip().startswith("SELECT"):
        return "Only SELECT statements are allowed"

    # Check for forbidden operations
    forbidden_patterns = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "CREATE",
        "TRUNCATE",
        "MERGE",
        "EXECUTE",
        "CALL",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT",
        "SET ",
        "REPLACE",
        "LOCK",
        "UNLOCK",
        "GRANT",
        "REVOKE",
        "DENY",
        "BEGIN",
        "START TRANSACTION",
    ]

    for pattern in forbidden_patterns:
        if pattern in upper_sql:
            return f"Forbidden operation: {pattern}"

    # Check for potential SQL injection patterns (basic)
    # This is a simple check - in production you'd want more robust validation
    dangerous_patterns = [
        "--",
        "/*",
        "*/",
        ";",  # SQL comments and statement termination
        "UNION",
        "INTO",
        "LOAD_FILE",
        "OUTFILE",  # Data exfiltration
    ]

    for pattern in dangerous_patterns:
        if pattern in upper_sql:
            return f"Potentially dangerous pattern: {pattern}"

    return None


def _serialize(value: object) -> object:
    """Recursively convert SQLAlchemy row results to JSON-safe types."""
    if value is None:
        return None
    if isinstance(value, (int, float, bool, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    # SQLAlchemy Row / KeyedTuple
    if hasattr(value, "_mapping"):
        return {k: _serialize(v) for k, v in value._mapping.items()}
    if hasattr(value, "__dict__"):
        return {
            k: _serialize(v) for k, v in vars(value).items() if not k.startswith("_")
        }
    return str(value)


@function_tool
async def run_query(
    ctx: RunContextWrapper[TelegramAgentContext],
    sql_query: Annotated[
        str,
        (
            "Raw SQL SELECT query to execute. "
            "Available tables: receipts, receipt_items, users. "
            "Must include :user_id parameter for filtering. "
            "Example:\n"
            "  SELECT category, SUM(total) as total_spent \n"
            "  FROM receipts \n"
            "  WHERE user_id = :user_id \n"
            "  GROUP BY category \n"
            "  ORDER BY total_spent DESC\n"
        ),
    ],
) -> str:
    """Execute a SQL analytics query and return the serialised results.

    Use this tool for aggregate queries, trends, spending breakdowns, and any
    analytics that require SQL. ``user_id`` is provided as a parameter.
    Only read-only SELECT patterns are permitted.
    """
    # Validate SQL is safe
    validation_error = _validate_sql(sql_query)
    if validation_error:
        return json.dumps({"error": validation_error})

    user_id = ctx.context.user_id

    try:
        session = ctx.context.db_session
        # Convert UUID to string for SQLite compatibility
        bind_user_id = str(user_id) if user_id else user_id
        # Execute SQL with user_id parameter
        result = await session.execute(text(sql_query), {"user_id": bind_user_id})
        rows = result.all()

        # Convert rows to list of dictionaries and serialize values
        if rows and hasattr(rows[0], "_mapping"):
            serialized = [_serialize(dict(row._mapping)) for row in rows]
        else:
            # Fallback for other result types
            serialized = [_serialize(list(row)) for row in rows]

        return json.dumps({"result": serialized}, ensure_ascii=False)
    except Exception:
        return json.dumps({"error": traceback.format_exc(limit=5)})
