"""Execution-layer errors."""


class ExecutionError(ValueError):
    """Base error for paper execution safety violations."""


class ProfileBlocked(ExecutionError):
    """Simulation profile failed hard gates."""


class ActivationBlocked(ExecutionError):
    """Strategy cannot be activated."""


class DraftBlocked(ExecutionError):
    """Order draft cannot be built or submitted."""


class IdempotentReplay(ExecutionError):
    """Draft was already accepted; safe no-op replay."""

    def __init__(self, draft_id: str, execution_id: str) -> None:
        self.draft_id = draft_id
        self.execution_id = execution_id
        super().__init__(f"draft {draft_id} already executed as {execution_id}")


class BrokerConfigError(ExecutionError):
    """Broker selection / credentials / mode misconfiguration (fail-closed)."""


class BrokerTransportError(ExecutionError):
    """External SIMULATE transport failed (still not live trading)."""
