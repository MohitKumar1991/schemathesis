import datetime
import threading
from contextlib import contextmanager
from queue import Queue
from typing import Any, Dict, Generator, List

import attr
import click
import yaml
from yaml.serializer import Serializer

from ..models import Interaction
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
    queue: Queue = attr.ib(factory=Queue)
    worker: threading.Thread = attr.ib(init=False)

    def __attrs_post_init__(self) -> None:
        self.worker = threading.Thread(target=worker, kwargs={"file_handle": self.file_handle, "queue": self.queue})
        self.worker.start()

    def initialize(self, context: ExecutionContext) -> None:
        """In the beginning we write metadata and start `interactions` list."""
        self.queue.put(Initialize())

    def handle_event(self, context: ExecutionContext, event: events.ExecutionEvent) -> None:
        if isinstance(event, events.AfterExecution):
            self.queue.put(Process(status=event.status.name.upper(), interactions=event.result.interactions))

    def finalize(self) -> None:
        self.queue.put(Finalize())
        self.worker.join(1)


@attr.s(slots=True)
class Initialize:
    pass


@attr.s(slots=True)
class Process:
    status: str = attr.ib()
    interactions: List[Interaction] = attr.ib()


@attr.s(slots=True)
class Finalize:
    pass


def worker(file_handle: click.utils.LazyFile, queue: Queue) -> None:
    current_id = 0
    stream = file_handle.open()
    dumper = Dumper(stream, sort_keys=False)  # type: ignore
    # should work only for CDumper
    Serializer.__init__(dumper)  # type: ignore
    dumper.open()  # type: ignore

    def emit(*yaml_events: yaml.Event) -> None:
        for event in yaml_events:
            dumper.emit(event)  # type: ignore

    @contextmanager
    def mapping() -> Generator[None, None, None]:
        emit(yaml.MappingStartEvent(anchor=None, tag=None, implicit=True))
        yield
        emit(yaml.MappingEndEvent())

    def serialize_mapping(name: str, data: Dict[str, Any]) -> None:
        emit(yaml.ScalarEvent(anchor=None, tag=None, implicit=(True, True), value=name))
        node = dumper.represent_data(data)  # type: ignore
        # C-extension is not introspectable
        dumper.anchor_node(node)  # type: ignore
        dumper.serialize_node(node, None, 0)  # type: ignore

    while True:
        item = queue.get()
        if isinstance(item, Initialize):
            emit(
                yaml.DocumentStartEvent(),
                yaml.MappingStartEvent(anchor=None, tag=None, implicit=True),
                yaml.ScalarEvent(anchor=None, tag=None, implicit=(True, True), value="meta"),
            )
            with mapping():
                emit(
                    yaml.ScalarEvent(anchor=None, tag=None, implicit=(True, True), value="start_time"),
                    yaml.ScalarEvent(
                        anchor=None, tag=None, implicit=(True, True), value=datetime.datetime.now().isoformat()
                    ),
                )
            emit(
                yaml.ScalarEvent(anchor=None, tag=None, implicit=(True, True), value="interactions"),
                yaml.SequenceStartEvent(anchor=None, tag=None, implicit=True),
            )
        elif isinstance(item, Process):
            for interaction in item.interactions:
                with mapping():
                    emit(
                        yaml.ScalarEvent(anchor=None, tag=None, implicit=(True, True), value="id"),
                        yaml.ScalarEvent(anchor=None, tag=None, implicit=(False, True), value=str(current_id)),
                        yaml.ScalarEvent(anchor=None, tag=None, implicit=(True, True), value="status"),
                        yaml.ScalarEvent(anchor=None, tag=None, implicit=(False, True), value=item.status),
                    )
                    dictionary = attr.asdict(interaction)
                    # These mappings should be also handled more strictly
                    serialize_mapping("request", dictionary["request"])
                    serialize_mapping("response", dictionary["response"])
                current_id += 1
        elif isinstance(item, Finalize):
            emit(
                yaml.SequenceEndEvent(), yaml.MappingEndEvent(), yaml.DocumentEndEvent(),
            )
            # C-extension is not introspectable
            dumper.close()  # type: ignore
            dumper.dispose()  # type: ignore
            break
