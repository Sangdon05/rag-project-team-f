from typing import Literal

from pydantic import BaseModel, Field


class HealthData(BaseModel):
    status: Literal["ok"] = Field("ok", description="항상 ok")
