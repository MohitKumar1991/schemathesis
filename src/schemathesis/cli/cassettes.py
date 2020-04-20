import datetime
from contextlib import contextmanager
from typing import Any, Dict, Generator

import attr
import click
import yaml
from yaml.serializer import Serializer

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
    """Write interactions in a YAML cassette.

    A low-level interface is used to write data to YAML file during the test run and reduce the delay at
    the end of the test run.
    """

    file_handle: click.utils.LazyFile = attr.ib()
    data: Dict[str, Any] = attr.ib(factory=dict)
    dumper: Dumper = attr.ib(init=False)
    current_id: int = attr.ib(init=False)

    def __attrs_post_init__(self) -> None:
        stream = self.file_handle.open()
        self.dumper = Dumper(stream, sort_keys=False)  # type: ignore
        # should work only for CDumper
        Serializer.__init__(self.dumper)  # type: ignore
        self.dumper.open()  # type: ignore
        self.current_id = 0

    def _emit(self, *yaml_events: yaml.Event) -> None:
        for event in yaml_events:
            self.dumper.emit(event)  # type: ignore

    @contextmanager
    def mapping(self) -> Generator[None, None, None]:
        self._emit(yaml.MappingStartEvent(anchor=None, tag=None, implicit=True))
        yield
        self._emit(yaml.MappingEndEvent())

    def serialize_mapping(self, name: str, data: Dict[str, Any]) -> None:
        self._emit(yaml.ScalarEvent(anchor=None, tag=None, implicit=(True, True), value=name))
        node = self.dumper.represent_data(data)  # type: ignore
        # C-extension is not introspectable
        self.dumper.anchor_node(node)  # type: ignore
        self.dumper.serialize_node(node, None, 0)  # type: ignore

    def initialize(self, context: ExecutionContext) -> None:
        """In the beginning we write metadata and start `interactions` list."""
        self._emit(
            yaml.DocumentStartEvent(),
            yaml.MappingStartEvent(anchor=None, tag=None, implicit=True),
            yaml.ScalarEvent(anchor=None, tag=None, implicit=(True, True), value="meta"),
        )
        with self.mapping():
            self._emit(
                yaml.ScalarEvent(anchor=None, tag=None, implicit=(True, True), value="start_time"),
                yaml.ScalarEvent(
                    anchor=None, tag=None, implicit=(True, True), value=datetime.datetime.now().isoformat()
                ),
            )
        self._emit(
            yaml.ScalarEvent(anchor=None, tag=None, implicit=(True, True), value="interactions"),
            yaml.SequenceStartEvent(anchor=None, tag=None, implicit=True),
        )

    def handle_event(self, context: ExecutionContext, event: events.ExecutionEvent) -> None:
        if isinstance(event, events.AfterExecution):
            self._handle_event(context, event)

    def _handle_event(self, context: ExecutionContext, event: events.AfterExecution) -> None:
        status = event.status.name.upper()
        for interaction in event.result.interactions:
            with self.mapping():
                self._emit(
                    yaml.ScalarEvent(anchor=None, tag=None, implicit=(True, True), value="id"),
                    yaml.ScalarEvent(anchor=None, tag=None, implicit=(False, True), value=str(self.current_id)),
                    yaml.ScalarEvent(anchor=None, tag=None, implicit=(True, True), value="status"),
                    yaml.ScalarEvent(anchor=None, tag=None, implicit=(False, True), value=status),
                )
                dictionary = attr.asdict(interaction)
                # These mappings should be also handled more strictly
                self.serialize_mapping("request", dictionary["request"])
                self.serialize_mapping("response", dictionary["response"])
            self.current_id += 1

    def finalize(self) -> None:
        self._emit(
            yaml.SequenceEndEvent(), yaml.MappingEndEvent(), yaml.DocumentEndEvent(),
        )
        # C-extension is not introspectable
        self.dumper.close()  # type: ignore
        self.dumper.dispose()  # type: ignore
