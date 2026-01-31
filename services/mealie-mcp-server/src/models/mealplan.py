from pydantic import BaseModel


class MealPlanEntry(BaseModel):
    date: str
    recipe_id: str | None = None
    title: str | None = None
    entry_type: str = "breakfast"
