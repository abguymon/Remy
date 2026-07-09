from typing import Any

from pydantic import BaseModel, Field


class RecipeIngredient(BaseModel):
    quantity: float | None = None
    unit: str | None = None
    food: str | None = None
    note: str
    isFood: bool | None = True
    disableAmount: bool | None = False
    display: str | None = None
    title: str | None = None
    originalText: str | None = None
    referenceId: str | None = None


class RecipeInstruction(BaseModel):
    id: str | None = None
    title: str | None = None
    summary: str | None = None
    text: str
    ingredientReferences: list[str] = Field(default_factory=list)


class RecipeNutrition(BaseModel):
    calories: str | None = None
    carbohydrateContent: str | None = None
    cholesterolContent: str | None = None
    fatContent: str | None = None
    fiberContent: str | None = None
    proteinContent: str | None = None
    saturatedFatContent: str | None = None
    sodiumContent: str | None = None
    sugarContent: str | None = None
    transFatContent: str | None = None
    unsaturatedFatContent: str | None = None


class RecipeSettings(BaseModel):
    public: bool = False
    showNutrition: bool = False
    showAssets: bool = False
    landscapeView: bool = False
    disableComments: bool = False
    disableAmount: bool = False
    locked: bool = False


class Recipe(BaseModel):
    id: str
    userId: str
    householdId: str
    groupId: str
    name: str
    slug: str
    image: str | None = None
    recipeServings: int | None = None
    recipeYieldQuantity: int | None = 0
    recipeYield: str | None = None
    totalTime: int | None = None
    prepTime: int | None = None
    cookTime: int | None = None
    performTime: int | None = None
    description: str | None = None
    recipeCategory: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    rating: float | None = None
    orgURL: str | None = None
    dateAdded: str
    dateUpdated: str
    createdAt: str
    updatedAt: str
    lastMade: str | None = None
    recipeIngredient: list[RecipeIngredient] = Field(default_factory=list)
    recipeInstructions: list[RecipeInstruction] = Field(default_factory=list)
    nutrition: RecipeNutrition = Field(default_factory=RecipeNutrition)
    settings: RecipeSettings = Field(default_factory=RecipeSettings)
    assets: list[Any] = Field(default_factory=list)
    notes: list[Any] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)
    comments: list[Any] = Field(default_factory=list)
