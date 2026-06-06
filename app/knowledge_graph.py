# ========================================================================================#
#                                       IDLEARN                                           #
#                                   knowledge_graph.py                                    #
# ========================================================================================#
"""
Filename: knowledge_graph.py
Author: diomir0
Date of creation: 06 Jul 2025

Knowledge graph extraction from document summaries.

This module provides the data structures and stub functions for extracting
a concept-level knowledge graph from LLM-generated summaries. The graph
captures entities, concepts, and their relationships as a structured
representation that can be exported to various formats.

Architecture:
    The knowledge graph pipeline is designed to sit between the summarization
    step and the export step in the main Pipeline:

        PDF → Extract Text/Images → Summarize (multimodal LLM) → Knowledge Graph → Export

    The graph is built by asking the LLM to extract concepts and relationships
    from the summaries it already generated. This avoids re-processing the raw
    text and leverages the structured summaries as a compact representation.

Data model:
    Concept   — A named entity or idea extracted from the text (node).
    Relation  — A typed, directed edge between two concepts.
    Graph     — The full knowledge graph with concepts, relations, and metadata.

Future implementation will:
    1. Use the LLM to extract concepts and relations from summaries.
    2. Support export to Obsidian canvas JSON, Mermaid diagrams, and GraphML.
    3. Provide a visualization layer for the Streamlit web interface.
"""

from dataclasses import dataclass, field
from typing import Optional
import json


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Concept:
    """A single concept (node) in the knowledge graph.

    Attributes:
        id:        Unique identifier (slug-like, e.g. 'divided_brain_hypothesis').
        label:     Human-readable name (e.g. 'Divided Brain Hypothesis').
        category:  Broad category (e.g. 'theory', 'person', 'method', 'finding').
        section:   The document section where this concept appears.
        definition: Optional short definition or description.
    """
    id: str = ""
    label: str = ""
    category: str = ""
    section: str = ""
    definition: str = ""


@dataclass
class Relation:
    """A directed relationship between two concepts (edge).

    Attributes:
        source:    ID of the source concept.
        target:    ID of the target concept.
        label:     Human-readable relationship label (e.g. 'supports', 'contradicts').
        weight:    Confidence or importance weight (0.0–1.0).
    """
    source: str = ""
    target: str = ""
    label: str = ""
    weight: float = 1.0


@dataclass
class KnowledgeGraph:
    """The complete knowledge graph extracted from a document.

    Attributes:
        title:      Document title.
        concepts:   List of Concept nodes.
        relations:  List of Relation edges.
        metadata:   Arbitrary metadata (model used, timestamp, etc.).
    """
    title: str = ""
    concepts: list[Concept] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Export methods
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Convert to a plain dictionary suitable for JSON serialization."""
        return {
            "title": self.title,
            "concepts": [
                {
                    "id": c.id,
                    "label": c.label,
                    "category": c.category,
                    "section": c.section,
                    "definition": c.definition,
                }
                for c in self.concepts
            ],
            "relations": [
                {
                    "source": r.source,
                    "target": r.target,
                    "label": r.label,
                    "weight": r.weight,
                }
                for r in self.relations
            ],
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize the graph to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_mermaid(self) -> str:
        """Generate a Mermaid flowchart representation of the graph.

        Returns:
            A string containing a Mermaid ``graph TD`` block.
        """
        lines = ["graph TD"]
        for c in self.concepts:
            # Sanitize node IDs for Mermaid
            node_id = c.id.replace(" ", "_").replace("-", "_")
            lines.append(f"    {node_id}[\"{c.label}\"]")
        for r in self.relations:
            src = r.source.replace(" ", "_").replace("-", "_")
            tgt = r.target.replace(" ", "_").replace("-", "_")
            lines.append(f"    {src} -->|\"{r.label}\"| {tgt}")
        return "\n".join(lines)

    def to_obsidian_canvas(self) -> str:
        """Generate an Obsidian Canvas JSON representation.

        Returns:
            A JSON string in Obsidian Canvas format (.canvas).
        """
        nodes = []
        edges = []
        # Lay out concepts in a grid
        cols = max(3, len(self.concepts) // 3)
        for i, c in enumerate(self.concepts):
            x = (i % cols) * 300
            y = (i // cols) * 250
            nodes.append({
                "id": c.id,
                "type": "text",
                "x": x,
                "y": y,
                "width": 260,
                "height": 120,
                "text": f"**{c.label}**\n{c.definition}" if c.definition else c.label,
            })
        for r in self.relations:
            edges.append({
                "id": f"e_{r.source}_{r.target}",
                "fromNode": r.source,
                "fromSide": "bottom",
                "toNode": r.target,
                "toSide": "top",
                "label": r.label,
            })
        return json.dumps({"nodes": nodes, "edges": edges}, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Stub functions (to be implemented)
# ---------------------------------------------------------------------------

EXTRACT_CONCEPTS_PROMPT = (
    "You are an expert knowledge engineer. Given the following summary of a text, "
    "extract ALL significant concepts, entities, and ideas as a structured list.\n\n"
    "For each concept, provide:\n"
    "- A short, unique identifier (snake_case, e.g. 'divided_brain_hypothesis')\n"
    "- A human-readable label (e.g. 'Divided Brain Hypothesis')\n"
    "- A category (one of: theory, person, method, finding, concept, event, term)\n"
    "- A brief definition (1–2 sentences)\n\n"
    "Output as a JSON array of objects with keys: id, label, category, definition.\n\n"
    "Summary:\n{text}"
)

EXTRACT_RELATIONS_PROMPT = (
    "You are an expert knowledge engineer. Given the following concepts and the "
    "original summary, identify the meaningful relationships between these concepts.\n\n"
    "For each relationship, provide:\n"
    "- source: the id of the source concept\n"
    "- target: the id of the target concept\n"
    "- label: a short relationship description (e.g. 'supports', 'contradicts', "
    "'is a type of', 'leads to', 'is based on')\n"
    "- weight: a confidence score from 0.0 to 1.0\n\n"
    "Output as a JSON array of objects with keys: source, target, label, weight.\n\n"
    "Concepts:\n{concepts}\n\n"
    "Summary:\n{text}"
)


def extract_knowledge_graph(summaries: dict, model=None, title: str = "") -> KnowledgeGraph:
    """Extract a knowledge graph from LLM-generated summaries.

    For each section's summary, the LLM is asked to extract concepts and then
    identify relationships between them. The results are deduplicated and
    merged into a single KnowledgeGraph.

    Args:
        summaries: Dict of section_title → summary text.
        model: An LLMModel instance for generating the graph.
        title: An optional document title for the graph metadata.

    Returns:
        A KnowledgeGraph with concepts and relations.
    """
    import re as _re
    import json as _json
    from .logger import logger

    if model is None:
        logger.warning("No LLM model provided for knowledge graph extraction. Returning empty graph.")
        return KnowledgeGraph(title=title or "Empty Graph")

    graph = KnowledgeGraph(title=title or "Document Knowledge Graph")
    all_section_concepts: dict[str, list[Concept]] = {}

    # 1. Extract concepts from each section summary
    for section, summary_text in summaries.items():
        logger.info(f"Extracting concepts from section: {section}")
        prompt = EXTRACT_CONCEPTS_PROMPT.format(text=summary_text)
        try:
            response = model.generate(prompt)
        except Exception as e:
            logger.error(f"Failed to extract concepts from '{section}': {e}")
            continue
        if not response:
            logger.warning(f"Empty response for concepts in section '{section}'")
            continue

        # Extract JSON array from the response (handle markdown code fences)
        json_match = _re.search(r"\[.*\]", response, _re.DOTALL)
        if not json_match:
            logger.warning(f"No JSON array found in concept response for '{section}'")
            continue

        try:
            concepts_data = _json.loads(json_match.group())
        except _json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in concept response for '{section}': {e}")
            continue

        section_concepts = []
        for item in concepts_data:
            if not isinstance(item, dict):
                continue
            concept = Concept(
                id=item.get("id", "").strip(),
                label=item.get("label", "").strip(),
                category=item.get("category", "concept").strip(),
                section=section,
                definition=item.get("definition", "").strip(),
            )
            if concept.id and concept.label:
                section_concepts.append(concept)
        all_section_concepts[section] = section_concepts

    # 2. Deduplicate concepts across sections
    seen_ids: dict[str, Concept] = {}
    for section, concepts in all_section_concepts.items():
        for c in concepts:
            if c.id not in seen_ids:
                seen_ids[c.id] = c
                graph.concepts.append(c)
            # If a concept appears in multiple sections, keep the first definition
            # but note additional sections in metadata if needed

    if not graph.concepts:
        logger.warning("No concepts extracted. Returning empty graph.")
        return graph

    # 3. Extract relations between concepts (batch per section)
    for section, summary_text in summaries.items():
        section_concepts = all_section_concepts.get(section, [])
        if not section_concepts:
            continue

        concepts_str = "\n".join(
            f"- {c.id}: {c.label} ({c.category})" for c in section_concepts
        )
        prompt = EXTRACT_RELATIONS_PROMPT.format(
            concepts=concepts_str, text=summary_text
        )
        logger.info(f"Extracting relations for section: {section}")
        try:
            response = model.generate(prompt)
        except Exception as e:
            logger.error(f"Failed to extract relations for '{section}': {e}")
            continue
        if not response:
            continue

        json_match = _re.search(r"\[.*\]", response, _re.DOTALL)
        if not json_match:
            logger.warning(f"No JSON array found in relations response for '{section}'")
            continue

        try:
            relations_data = _json.loads(json_match.group())
        except _json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in relations response for '{section}': {e}")
            continue

        for item in relations_data:
            if not isinstance(item, dict):
                continue
            source_id = item.get("source", "").strip()
            target_id = item.get("target", "").strip()
            # Only add relations between concepts we actually extracted
            if source_id in seen_ids and target_id in seen_ids:
                graph.relations.append(Relation(
                    source=source_id,
                    target=target_id,
                    label=item.get("label", "related to").strip(),
                    weight=float(item.get("weight", 1.0)),
                ))

    logger.info(
        f"Knowledge graph: {len(graph.concepts)} concepts, "
        f"{len(graph.relations)} relations"
    )
    return graph
