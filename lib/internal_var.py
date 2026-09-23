from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

if TYPE_CHECKING:
    from .models import Field_device, Queued_service_call


ha: HomeAssistant | None = None
configuration: ConfigType | None = None
unprocessed_requests: "asyncio.Queue[Queued_service_call]" = asyncio.Queue(maxsize=100)
field_dev_list: list["Field_device"] = []
