from ..runner import events
from .context import ExecutionContext


class EventHandler:
    def initialize(self, context: ExecutionContext) -> None:
        pass

    def handle_event(self, context: ExecutionContext, event: events.ExecutionEvent) -> None:
        raise NotImplementedError

    def finalize(self) -> None:
        pass
