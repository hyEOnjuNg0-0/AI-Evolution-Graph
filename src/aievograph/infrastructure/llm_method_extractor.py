"""OpenAI GPT-4o implementation of MethodExtractorPort with gleaning."""

import logging

from openai import OpenAI

from aievograph.domain.models import ExtractionResult, Method, MethodRelation
from aievograph.domain.ports.method_extractor import MethodExtractorPort

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert AI research analyst. Extract Method entities and their evolutionary \
relationships from paper abstracts.

ENTITY TYPES:
- Method   : A general algorithmic approach (e.g., "Attention", "Backpropagation")
- Model    : A specific architecture or trained model (e.g., "BERT", "ResNet", "GPT-3")
- Technique: A specific implementation strategy (e.g., "Dropout", "Layer Normalization")
- Framework: A software framework or system (e.g., "PyTorch", "Transformers")

RELATIONSHIP TYPES (method-to-method evolutionary relationships only):
- IMPROVES : source achieves better results by refining target
- EXTENDS  : source adds new capability to target while retaining it
- REPLACES : source supersedes or substitutes target

EXTRACTION RULES:
1. Only extract entities explicitly mentioned in the abstract.
2. Use canonical names (e.g., "BERT" not "bert model").
3. Only extract relationships directly stated or clearly implied in the text.
4. The evidence field must closely quote or paraphrase the abstract.
5. Do NOT extract generic terms like "deep learning" unless they are the direct subject.

EXAMPLE:
Abstract: "We introduce GPT-3, a language model that extends the GPT-2 architecture to \
175 billion parameters. Unlike BERT which uses bidirectional attention, GPT-3 employs \
autoregressive Transformer decoding. GPT-3 outperforms fine-tuned BERT on several \
benchmarks using only in-context learning, replacing the need for task-specific fine-tuning."

Output:
{
  "methods": [
    {"name": "GPT-3", "method_type": "Model",
     "description": "Autoregressive 175B-parameter language model extending GPT-2"},
    {"name": "GPT-2", "method_type": "Model",
     "description": "Predecessor language model that GPT-3 extends"},
    {"name": "BERT", "method_type": "Model",
     "description": "Bidirectional Transformer language model"},
    {"name": "Transformer", "method_type": "Method",
     "description": "Core sequence-to-sequence neural architecture"},
    {"name": "In-Context Learning", "method_type": "Technique",
     "description": "Learning from prompt examples without gradient updates"}
  ],
  "relations": [
    {"source_method": "GPT-3", "target_method": "GPT-2",
     "relation_type": "EXTENDS",
     "evidence": "extends the GPT-2 architecture to 175 billion parameters"},
    {"source_method": "GPT-3", "target_method": "BERT",
     "relation_type": "IMPROVES",
     "evidence": "GPT-3 outperforms fine-tuned BERT on several benchmarks"},
    {"source_method": "In-Context Learning", "target_method": "Fine-tuning",
     "relation_type": "REPLACES",
     "evidence": "replacing the need for task-specific fine-tuning"}
  ]
}
"""

_EXTRACT_TEMPLATE = """\
Extract all AI methods, models, techniques, and frameworks from the following abstract, \
along with any evolutionary relationships between them.

Abstract:
{abstract}
"""

_GLEAN_TEMPLATE = """\
Review the abstract below and check whether any AI methods, models, techniques, or \
frameworks were missed in the first pass.

Abstract:
{abstract}

Already extracted methods: {method_names}

Return ONLY items NOT already listed above. If nothing was missed, return empty lists.
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _merge(first: ExtractionResult, gleaned: ExtractionResult) -> ExtractionResult:
    """Merge two extraction results, deduplicating by method name and relation key."""
    # First-pass entries take priority on name collision
    methods_by_name: dict[str, Method] = {m.name: m for m in gleaned.methods}
    methods_by_name.update({m.name: m for m in first.methods})

    seen: set[tuple[str, str, str]] = set()
    merged_relations: list[MethodRelation] = []
    for rel in (*first.relations, *gleaned.relations):
        key = (rel.source_method, rel.target_method, rel.relation_type)
        if key not in seen:
            seen.add(key)
            merged_relations.append(rel)

    return ExtractionResult(
        methods=list(methods_by_name.values()),
        relations=merged_relations,
    )


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class LLMMethodExtractor(MethodExtractorPort):
    """Extract Method entities and relations using GPT-4o structured output + gleaning."""

    def __init__(self, client: OpenAI, model: str = "gpt-4o") -> None:
        self._client = client
        self._model = model

    def extract(self, abstract: str) -> ExtractionResult:
        # Pass 1: initial extraction
        first = self._call_llm(_EXTRACT_TEMPLATE.format(abstract=abstract))

        # Pass 2: gleaning — look for missed entities
        method_names = ", ".join(m.name for m in first.methods) or "(none)"
        gleaned = self._call_llm(
            _GLEAN_TEMPLATE.format(abstract=abstract, method_names=method_names)
        )

        merged = _merge(first, gleaned)
        logger.debug(
            "extraction complete: methods=%d relations=%d (pass1=%d gleaned=%d)",
            len(merged.methods),
            len(merged.relations),
            len(first.methods),
            len(gleaned.methods),
        )
        return merged

    def _call_llm(self, user_message: str) -> ExtractionResult:
        response = self._client.beta.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format=ExtractionResult,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            logger.warning("LLM returned no parsed result; using empty ExtractionResult")
            return ExtractionResult()
        return parsed
