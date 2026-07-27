from remy_api.planner.discover import _dedup
from remy_api.planner.schemas import Candidate, Origin


def test_saved_recipe_suppresses_web_result_with_same_canonical_url():
    saved = Candidate(
        id="saved:1",
        title="Blueberry Baked Oatmeal",
        source_domain="saved",
        dedupe_url="https://www.cookieandkate.com/baked-oatmeal-recipe/",
        saved_recipe_id="1",
        origin=Origin.SAVED,
    )
    web = Candidate(
        id="web:1",
        title="Baked Oatmeal Recipe with Blueberries",
        source_domain="cookieandkate.com",
        url="https://cookieandkate.com/baked-oatmeal-recipe?utm_source=search",
        origin=Origin.WEB,
    )

    assert _dedup([saved, web]) == [saved]


def test_saved_recipe_dedupe_url_is_not_exposed_in_plan_state():
    candidate = Candidate(
        id="saved:1",
        title="Blueberry Baked Oatmeal",
        source_domain="saved",
        dedupe_url="https://cookieandkate.com/baked-oatmeal-recipe/",
        saved_recipe_id="1",
        origin=Origin.SAVED,
    )

    assert "dedupe_url" not in candidate.model_dump()
