"""Python Query tool — the agent generates a SQLAlchemy expression that is
executed in a controlled namespace, then synthesises the results.

Safety design:
- ``user_id`` is injected as an immutable constant in the execution namespace;
  the model cannot override it.
- ``__builtins__`` is replaced with a strict allowlist.
- The generated code may only read data (SELECT patterns).  The namespace
  exposes no ``session.add``, ``session.delete``, ``session.commit``, or DDL.
- Execution runs inside ``AsyncSession.run_sync()`` so the sandbox code uses
  a regular sync ``Session`` while the outer call remains non-blocking.
"""

from __future__ import annotations

import json
import traceback
from typing import Annotated

from agents import RunContextWrapper, function_tool
from sqlalchemy import select, func, and_, or_, desc, asc, case, cast, Float, Integer

from app.database import async_session_factory
from app.models.receipt import Receipt, ReceiptItem
from app.services.agent_context import TelegramAgentContext

_SAFE_BUILTINS: dict = {
    "len": len,
    "sum": sum,
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "list": list,
    "dict": dict,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "sorted": sorted,
    "reversed": reversed,
    "print": print,
}

_WRITE_GUARDS = (
    "session.add",
    "session.delete",
    "session.commit",
    "session.rollback",
    "session.execute(text(",
    "drop",
    "delete",
    "insert",
    "update",
    "alter",
    "create",
    "truncate",
    "grant",
    "revoke",
    "__import__",
    "import ",
    "open(",
    "exec(",
    "eval(",
    "compile(",
    "os.",
    "sys.",
    "subprocess",
)


def _check_for_write_ops(code: str) -> str | None:
    """Return the offending keyword if code contains a disallowed operation."""
    lower = code.lower()
    for guard in _WRITE_GUARDS:
        if guard in lower:
            return guard
    return None


def _serialize(value: object) -> object:
    """Recursively convert SQLAlchemy row results to JSON-safe types."""
    if value is None:
        return None
    if isinstance(value, (int, float, bool, str)):
        return value
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
    query_code: Annotated[
        str,
        (
            "Python code using SQLAlchemy to query the user's receipts. "
            "Available names: session, select, func, and_, or_, desc, asc, "
            "case, cast, Float, Integer, Receipt, ReceiptItem, user_id. "
            "Assign the final result to a variable named `result`. "
            "Example:\n"
            "  stmt = select(Receipt.category, func.sum(Receipt.total).label('total'))"
            ".where(Receipt.user_id == user_id)"
            ".group_by(Receipt.category)"
            ".order_by(func.sum(Receipt.total).desc())\n"
            "  rows = session.execute(stmt).all()\n"
            "  result = [{'category': r.category, 'total': r.total} for r in rows]"
        ),
    ],
) -> str:
    """Execute a SQLAlchemy analytics query and return the serialised results.

    Use this tool for aggregate queries, trends, spending breakdowns, and any
    analytics that cannot be expressed as a simple keyword search.
    ``user_id`` is pre-injected — always filter ``Receipt.user_id == user_id``.
    Never write to the database; read-only SELECT patterns only.
    """
    offending = _check_for_write_ops(query_code)
    if offending:
        return json.dumps(
            {
                "error": f"Disallowed operation detected: '{offending}'. "
                "Only read-only SELECT patterns are permitted."
            }
        )

    user_id = ctx.context.user_id
    local_ns: dict = {}

    def _exec_in_sync(sync_session) -> None:
        """Run the sandbox code with a sync Session provided by run_sync()."""
        namespace = {
            "__builtins__": _SAFE_BUILTINS,
            "select": select,
            "func": func,
            "and_": and_,
            "or_": or_,
            "desc": desc,
            "asc": asc,
            "case": case,
            "cast": cast,
            "Float": Float,
            "Integer": Integer,
            "Receipt": Receipt,
            "ReceiptItem": ReceiptItem,
            "user_id": user_id,
            "session": sync_session,
        }
        exec(query_code, namespace, local_ns)  # noqa: S102

    try:
        async with async_session_factory() as session:
            await session.run_sync(lambda sync_session: _exec_in_sync(sync_session))
    except Exception:
        return json.dumps({"error": traceback.format_exc(limit=5)})

    if "result" not in local_ns:
        return json.dumps({"error": "Code did not assign to `result`."})

    try:
        serialized = _serialize(local_ns["result"])
        return json.dumps({"result": serialized}, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        return json.dumps({"error": f"Could not serialize result: {exc}"})
