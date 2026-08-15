import uuid
from datetime import date

from pydantic import BaseModel


class AgilityResponse(BaseModel):
    on_time: int
    late: int
    pending: int
    avg_days_to_complete: float | None
    avg_delay_days: float | None
    staleness_hint: str


class DelayedTaskItem(BaseModel):
    post_id: uuid.UUID
    task_type_name: str
    user_name: str
    lawsuit_folder: str | None
    deadline_date: date
    completed_at_date: date
    delay_days: int


class DelayedUserItem(BaseModel):
    user_id: uuid.UUID
    user_name: str
    late_count: int
    avg_delay_days: float


class MostDelayedResponse(BaseModel):
    tasks: list[DelayedTaskItem]
    users: list[DelayedUserItem]


class ProductivityResponse(BaseModel):
    assigned: int
    completed: int
    late: int
    due_in_5_days: int


class WeeklyChartPoint(BaseModel):
    label: str
    day: date
    assigned: int
    completed: int


class WeeklyChartResponse(BaseModel):
    days: list[WeeklyChartPoint]
