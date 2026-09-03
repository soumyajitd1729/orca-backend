from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class LayerOut(BaseModel):
    id: str
    name: str
    type: str
    source: str
    valid_time: Optional[str] = None
    visible_default: bool = True
