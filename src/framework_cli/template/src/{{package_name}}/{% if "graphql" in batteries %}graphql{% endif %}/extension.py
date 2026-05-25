from __future__ import annotations

from collections.abc import Iterator

from strawberry.extensions import SchemaExtension

from .metrics import gql_metrics


class MetricsExtension(SchemaExtension):
    """Counts every GraphQL operation by type and outcome via the in-process singleton."""

    def on_operation(self) -> Iterator[None]:
        yield
        ec = self.execution_context
        op = ec.operation_type
        # OperationType.QUERY.value == "query"; default to "query" if undetermined.
        op_type = op.value if op is not None else "query"
        outcome = "error" if (ec.result is not None and ec.result.errors) else "success"
        gql_metrics.operation(op_type, outcome)
