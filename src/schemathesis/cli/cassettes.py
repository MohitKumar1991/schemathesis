import datetime
from typing import Any, Dict

import attr
import click
import yaml

from ..runner import events
from .context import ExecutionContext
from .handlers import EventHandler

try:
    from yaml import CDumper as Dumper
except ImportError:
    # pylint: disable=unused-import
    from yaml import Loader, Dumper  # type: ignore


@attr.s(slots=True)
class CassetteWriter(EventHandler):
    """Write interactions in a YAML cassette."""

    file_handle: click.utils.LazyFile = attr.ib()
    data: Dict[str, Any] = attr.ib(factory=dict)

    def initialize(self, context: ExecutionContext) -> None:
        self.data["meta"] = {"start_time": datetime.datetime.now().isoformat()}
        self.data["interactions"] = []

    def handle_event(self, context: ExecutionContext, event: events.ExecutionEvent) -> None:
        if isinstance(event, events.AfterExecution):
            self._handle_event(context, event)

    def _handle_event(self, context: ExecutionContext, event: events.AfterExecution) -> None:
        status = event.status.name.upper()
        for (idx, interaction) in enumerate(event.result.interactions, len(self.data["interactions"])):
            dictionary = attr.asdict(interaction)
            dictionary["id"] = idx
            dictionary["status"] = status
            self.data["interactions"].append(dictionary)

    def finalize(self) -> None:
        with self.file_handle.open() as fd:
            yaml.dump(self.data, fd, Dumper=Dumper)
