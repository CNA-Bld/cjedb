from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar, Iterable, Mapping, Optional, Union

DESCRIPTOR: _descriptor.FileDescriptor

class Database(_message.Message):
    __slots__ = ["events"]
    EVENTS_FIELD_NUMBER: ClassVar[int]
    events: _containers.RepeatedCompositeFieldContainer[Event]
    def __init__(self, events: Optional[Iterable[Union[Event, Mapping]]] = ...) -> None: ...

class Event(_message.Message):
    __slots__ = ["choices", "story_id", "story_name"]
    class Choice(_message.Message):
        __slots__ = ["text", "title"]
        TEXT_FIELD_NUMBER: ClassVar[int]
        TITLE_FIELD_NUMBER: ClassVar[int]
        text: str
        title: str
        def __init__(self, title: Optional[str] = ..., text: Optional[str] = ...) -> None: ...
    CHOICES_FIELD_NUMBER: ClassVar[int]
    STORY_ID_FIELD_NUMBER: ClassVar[int]
    STORY_NAME_FIELD_NUMBER: ClassVar[int]
    choices: _containers.RepeatedCompositeFieldContainer[Event.Choice]
    story_id: int
    story_name: str
    def __init__(self, story_id: Optional[int] = ..., story_name: Optional[str] = ..., choices: Optional[Iterable[Union[Event.Choice, Mapping]]] = ...) -> None: ...
