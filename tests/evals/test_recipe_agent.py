"""RecipeBox agent eval suite (single-turn, traced).

Run it with DeepEval, not bare pytest, so scores + reasons are printed per span:

    uv run deepeval test run tests/evals/test_recipe_agent.py \
        --skip-on-missing-params --identifier round-1

Each golden's ``input`` is fed to the real traced agent; ``assert_test`` then
scores the trace with the end-to-end metrics. The retriever-span metric
(ContextualRelevancy) is attached inside recipe_agent_app.py and reported per
span. Goldens come from ``deepeval generate`` (see tests/evals/README.md).
"""

import os
from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.dataset import EvaluationDataset, Golden

from tests.evals.metrics import single_turn_trace_metrics
from tests.evals.recipe_agent_app import citations_grounded, run_recipe_agent

_DATASET_PATH = Path(__file__).parent / "dataset.json"

dataset = EvaluationDataset()
if _DATASET_PATH.exists():
    dataset.add_goldens_from_json_file(file_path=str(_DATASET_PATH))

# These evals call the REAL OpenAI + Anthropic APIs (money + latency), so they must
# NOT run in the default `uv run pytest` / CI. Opt in explicitly with RUN_AGENT_EVALS=1,
# which `deepeval test run` invocations set (see README). Metrics are built lazily
# inside the test so plain collection never needs an API key.
_OPTED_IN = os.environ.get("RUN_AGENT_EVALS", "").lower() in {"1", "true", "yes"}


@pytest.mark.skipif(
    not (_OPTED_IN and dataset.goldens),
    reason="Agent evals are opt-in: set RUN_AGENT_EVALS=1 and generate tests/evals/dataset.json (see README).",
)
@pytest.mark.parametrize("golden", dataset.goldens)
async def test_recipe_agent(golden: Golden) -> None:
    response = await run_recipe_agent(golden.input)

    # Judge-free invariant: the agent may only cite recipe ids a tool actually
    # returned. A failure here is a hard bug (hallucinated citation), not a
    # subjective score, so it's a plain assert rather than a metric.
    assert citations_grounded(response), "agent cited a recipe id no tool ever returned"

    # LLM-judged, end-to-end metrics scored against the trace (built lazily — needs a key).
    assert_test(golden=golden, metrics=single_turn_trace_metrics())
