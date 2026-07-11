"""Metric instances for the RecipeBox agent eval suite.

Kept in one module (per the DeepEval skill) so the test file stays about *running
the app*, not constructing metrics. Two lists:

- ``SINGLE_TURN_TRACE_METRICS`` — end-to-end metrics, scored against the whole
  trace (the final reply + what the agent retrieved). Passed to ``assert_test``.
- ``RETRIEVER_SPAN_METRICS`` — a component metric attached to the
  ``search_recipes`` retriever span only, so a retrieval failure is diagnosed at
  the exact step it happened rather than blamed on the final answer.

All metrics use the same LLM judge (gpt-4o) so scores are comparable.
"""

from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
    GEval,
    TaskCompletionMetric,
)
from deepeval.test_case import SingleTurnParams

# The LLM-as-judge. gpt-4o balances judgment quality and cost for a first suite.
JUDGE_MODEL = "gpt-4o"

# Custom criterion for RecipeBox's headline guarantee: verifiable citations and
# no invented recipes. There is no generic "correctness" metric — correctness is
# domain-specific — so we spell it out as a GEval (the skill's default custom type).
grounded_citations = GEval(
    name="GroundedCitations",
    criteria=(
        "Judge whether the assistant grounds its recommendation. Every recipe it "
        "recommends must be cited by a numeric id written like '(recipe #123)'. It "
        "must NOT invent recipes, ingredients, or source URLs. A response that "
        "recommends a dish without a numeric citation, or that names a recipe/URL "
        "not tied to a cited id, should score low. Off-topic questions that it "
        "politely redirects (no recommendation, no citation) should score high."
    ),
    evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
    model=JUDGE_MODEL,
)

# End-to-end metrics — evaluated against the trace via assert_test(golden=...).
SINGLE_TURN_TRACE_METRICS = [
    TaskCompletionMetric(model=JUDGE_MODEL),  # did it actually help the user pick a recipe?
    AnswerRelevancyMetric(model=JUDGE_MODEL),  # is the reply on-topic for the request?
    FaithfulnessMetric(model=JUDGE_MODEL),  # is the reply grounded in retrieved recipes (no hallucination)?
    grounded_citations,  # RecipeBox-specific: cited, verifiable, invented nothing
]

# Component metric — attached to the search_recipes retriever span only.
RETRIEVER_SPAN_METRICS = [
    ContextualRelevancyMetric(model=JUDGE_MODEL),  # did semantic search return recipes relevant to the query?
]
