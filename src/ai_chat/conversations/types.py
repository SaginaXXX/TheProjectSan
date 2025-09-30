from typing import List, Dict, Callable, Optional, TypedDict, Awaitable, ClassVar
from dataclasses import dataclass, field
from pydantic import BaseModel
from ..agent.output_types import Actions, DisplayText

# Type definitions
# send message
WebSocketSend = Callable[[str], Awaitable[None]]
# audio payload
class AudioPayload(TypedDict):
    """Type definition for audio payload"""

    type: str # type
    audio: Optional[str] # audio
    volumes: Optional[List[float]] # volumes
    slice_length: Optional[int] # slice length
    display_text: Optional[DisplayText] # display text
    actions: Optional[Actions] # actions
    forwarded: Optional[bool] # forwarded

# conversation config
class ConversationConfig(BaseModel):
    """Configuration for conversation chain"""

    conf_uid: str = ""
    history_uid: str = ""
    client_uid: str = ""
    character_name: str = "AI"
