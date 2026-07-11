"""RecipeBox agent eval suite (single-turn, traced).

Run it with DeepEval, not bare pytest, so scores + reasons are printed per span:

    uv run deepeval test run tests/evals/test_recipe_agent.py \
        --skip-on-missing-params --identifier round-1

Each golden's ``input`` is fed to the real traced agent; ``assert_test`` then
scores the trace with the end-to-end metrics. The retriever-span metric
(ContextualRelevancy) is attached inside recipe_agent_app.py and reported per
span. Goldens come from ``deepeval generate`` (see tests/evals/README.md).
"""

from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.dataset import EvaluationDataset, Golden

from tests.evals.metrics import SINGLE_TURN_TRACE_METRICS
from tests.evals.recipe_agent_app import citations_grounded, run_recipe_agent

_DATASET_PATH = Path(__file__).parent / "dataset.json"

dataset = EvaluationDataset()
if _DATASET_PATH.exists():
    dataset.add_goldens_from_json_file(file_path=str(_DATASET_PATH))


@pytest.mark.skipif(
    not dataset.goldens,
    reason="No goldens. Run `uv run deepeval generate` to create tests/evals/dataset.json (see README).",
)
@pytest.mark.parametrize("golden", dataset.goldens)
async def test_recipe_agent(golden: Golden) -> None:
    response = await run_recipe_agent(golden.input)

    # Judge-free invariant: the agent may only cite recipe ids a tool actually
    # returned. A failure here is a hard bug (hallucinated citation), not a
    # subjective score, so it's a plain assert rather than a metric.
    assert citations_grounded(response), "agent cited a recipe id no tool ever returned"

    # LLM-judged, end-to-end metrics scored against the trace.
    assert_test(golden=golden, metrics=SINGLE_TURN_TRACE_METRICS)
