from recipebox.domain.schemas import RecipeCreate


def minimal_recipe(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "title": "Pasta",
        "description": "Simple pasta dish",
        "ingredients": [{"name": "pasta", "amount": 200, "unit": "grams"}],
        "steps": ["Boil water", "Cook pasta"],
        "servings": 2,
    }
    return {**base, **overrides}


class TestTagsValidator:
    def test_tags_are_lowercased(self) -> None:
        recipe = RecipeCreate.model_validate(minimal_recipe(tags=["Italian", "VEGAN"]))
        assert recipe.tags == ["italian", "vegan"]

    def test_tags_are_stripped(self) -> None:
        recipe = RecipeCreate.model_validate(minimal_recipe(tags=["  pasta  ", " dinner"]))
        assert recipe.tags == ["pasta", "dinner"]

    def test_blank_tags_are_removed(self) -> None:
        recipe = RecipeCreate.model_validate(minimal_recipe(tags=["italian", "", "   "]))
        assert recipe.tags == ["italian"]

    def test_empty_tags_list_is_valid(self) -> None:
        recipe = RecipeCreate.model_validate(minimal_recipe(tags=[]))
        assert recipe.tags == []


class TestToolsValidator:
    def test_tools_are_lowercased(self) -> None:
        recipe = RecipeCreate.model_validate(minimal_recipe(tools=["Large Pot", "COLANDER"]))
        assert recipe.tools == ["large pot", "colander"]

    def test_tools_are_stripped(self) -> None:
        recipe = RecipeCreate.model_validate(minimal_recipe(tools=["  wooden spoon  "]))
        assert recipe.tools == ["wooden spoon"]

    def test_blank_tools_are_removed(self) -> None:
        recipe = RecipeCreate.model_validate(minimal_recipe(tools=["pan", "   ", ""]))
        assert recipe.tools == ["pan"]


class TestTotalTimeComputed:
    def test_total_is_sum_of_prep_and_cook(self) -> None:
        recipe = RecipeCreate.model_validate(minimal_recipe(prep_time_minutes=10, cook_time_minutes=20))
        assert recipe.total_time_minutes == 30

    def test_total_when_both_zero(self) -> None:
        recipe = RecipeCreate.model_validate(minimal_recipe(prep_time_minutes=0, cook_time_minutes=0))
        assert recipe.total_time_minutes == 0
