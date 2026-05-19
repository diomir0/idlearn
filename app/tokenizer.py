"""
Tokenizer module for token-aware text segmentation with semantic boundaries.

This module handles:
1. Token estimation for text splitting
2. Semantic-aware segmentation preserving sentence boundaries
3. Hierarchical summarization preparation
4. Cross-lingual token counting (basic support)
"""

import re
import math
from typing import Dict, List, Optional, Tuple
from collections import Counter, deque


# Token estimation parameters
# These are calibrated for Mistral 7B and similar models
DEFAULT_TOKEN_PER_CHAR_RATIO = 0.05
MIN_TOKENS_PER_SEGMENT = 100
MAX_TOKENS_PER_SEGMENT = 3000
MIN_WORDS_PER_SEGMENT = 50
MAX_WORDS_PER_SEGMENT = 1500

# Sentence boundary patterns for smart splitting
SENTENCE_BOUNDARIES = [
    r'\n{2,}',  # Double newline (paragraph break)
    r'\n\.\s*\n',  # Period followed by newline
    r'\n\?\s*\n',  # Question mark followed by newline
    r'\n!\s*\n',  # Exclamation followed by newline
    r'\.\s+(?:\d+[:.\s]|$)',  # Period followed by number or end
    r'\.\s+(?:[A-Z][a-z]+:\s|$)',  # Period followed by capitalized word
]

# Language-specific adjustments (basic support)
LANGUAGE_TOKEN_RATIOS = {
    'en': 0.05,  # English
    'fr': 0.06,  # French (slightly more tokens per char)
    'de': 0.07,  # German
    'es': 0.055,  # Spanish
    'it': 0.055,  # Italian
    'pt': 0.055,  # Portuguese
    'zh': 0.15,  # Chinese (many characters per token)
    'ja': 0.18,  # Japanese
    'ko': 0.12,  # Korean
    'auto': 0.05,  # Default fallback
}


class TokenEstimator:
    """
    Estimates token counts for text segments.

    This class provides accurate token estimation without requiring
    an actual tokenizer (like tiktoken) by using calibrated ratios.
    """

    def __init__(self, language: str = 'auto'):
        """
        Initialize the token estimator.

        Args:
            language: Language code for token ratio calibration
        """
        self.language = language
        self.token_ratio = LANGUAGE_TOKEN_RATIOS.get(language, DEFAULT_TOKEN_PER_CHAR_RATIO)
        self.calibration_factor = 1.0

    def calibrate(self, text: str, known_tokens: int) -> None:
        """
        Calibrate token estimation using known token count.

        Args:
            text: Text with known token count
            known_tokens: Actual token count (from a tokenizer API)
        """
        if not text or not known_tokens:
            return

        estimated = int(len(text) * self.token_ratio)
        if estimated > 0 and known_tokens > 0:
            self.calibration_factor = known_tokens / max(estimated, 1)
            self.token_ratio = (known_tokens / len(text)) if len(text) > 0 else DEFAULT_TOKEN_PER_CHAR_RATIO

    def estimate(self, text: str) -> int:
        """
        Estimate the number of tokens in text.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        if not text:
            return 0

        # Adjust for text complexity
        word_count = len(text.split())
        if word_count > 100:
            # Longer texts might have different tokenization patterns
            complexity_factor = 1.0 + (word_count - 100) * 0.001
        else:
            complexity_factor = 1.0

        return max(MIN_TOKENS_PER_SEGMENT, int(len(text) * self.token_ratio * self.calibration_factor * complexity_factor))

    def adjust_ratio(self, text: str) -> float:
        """
        Adjust token ratio based on text characteristics.

        Args:
            text: Text to analyze

        Returns:
            Adjusted token ratio
        """
        if len(text) < 500:
            return self.token_ratio

        # Analyze text complexity
        word_count = len(text.split())
        punctuation_count = len(re.findall(r'[^\w\s]', text))

        # Adjust ratio based on complexity
        if word_count > 200:
            return self.token_ratio * 1.1
        elif punctuation_count > word_count * 0.1:
            return self.token_ratio * 1.05
        else:
            return self.token_ratio


class SmartTokenizer:
    """
    Smart text tokenizer for segmenting text at semantic boundaries.

    This tokenizer preserves:
    - Sentence boundaries
    - Section headers
    - Paragraph structures
    - List items
    """

    def __init__(self, max_tokens: int = MAX_TOKENS_PER_SEGMENT,
                 min_tokens: int = MIN_TOKENS_PER_SEGMENT):
        """
        Initialize the smart tokenizer.

        Args:
            max_tokens: Maximum tokens per segment
            min_tokens: Minimum tokens per segment (to avoid fragmentation)
        """
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self.estimator = TokenEstimator()

    def tokenize(self, text: str) -> List[Dict]:
        """
        Tokenize text into segments with semantic boundaries.

        Args:
            text: Text to tokenize

        Returns:
            List of tokenized segments with metadata
        """
        if not text or len(text.strip()) == 0:
            return []

        # Estimate initial token count
        total_tokens = self.estimator.estimate(text)

        # If text fits in one segment, return as-is
        if total_tokens <= self.max_tokens:
            return [{
                'content': text,
                'start_index': 0,
                'end_index': len(text),
                'estimated_tokens': total_tokens,
                'word_count': len(text.split()),
                'segment_type': 'single',
                'contains_sentence_boundary': False
            }]

        # Need to split the text
        segments = self._smart_tokenize(text)

        return segments

    def _smart_tokenize(self, text: str) -> List[Dict]:
        """
        Smart text tokenization using semantic boundaries.

        Args:
            text: Text to tokenize

        Returns:
            List of tokenized segments
        """
        # Find potential split points
        split_candidates = self._find_split_candidates(text)

        if not split_candidates:
            # Fall back to simple splitting
            return self._simple_tokenize(text)

        # Greedy approach with semantic awareness
        segments = []
        remaining = text
        current_position = 0
        context_window = 200  # Keep some context at split points

        while remaining:
            remaining_tokens = self.estimator.estimate(remaining)

            # If remaining text is small enough, take it all
            if remaining_tokens <= self.max_tokens:
                segments.append({
                    'content': remaining,
                    'start_index': current_position,
                    'end_index': current_position + len(remaining),
                    'estimated_tokens': remaining_tokens,
                    'word_count': len(remaining.split()),
                    'segment_type': 'remainder',
                    'contains_sentence_boundary': remaining.endswith(('.', '!', '?', '\n\n'))
                })
                break
            else:
                # Find best split point within token limit
                best_split = None
                best_split_pos = None
                best_tokens = None

                for candidate in split_candidates:
                    split_pos = remaining.find(candidate)
                    if split_pos == -1:
                        continue

                    # Calculate split position
                    end_pos = split_pos + len(candidate)

                    # Check context - ensure we have some context on both sides
                    if end_pos - context_window < split_pos:
                        continue

                    # Test this split
                    test_segment = remaining[:end_pos]
                    test_tokens = self.estimator.estimate(test_segment)

                    if test_tokens <= self.max_tokens:
                        # Prefer semantic boundaries with larger segments
                        if best_tokens is None or test_tokens > best_tokens:
                            best_split = candidate
                            best_split_pos = end_pos
                            best_tokens = test_tokens

                if best_split is None:
                    # No valid semantic split found, use simple splitting
                    return self._simple_tokenize(text)

                # Create segment
                segment_content = remaining[:best_split_pos]
                segments.append({
                    'content': segment_content,
                    'start_index': current_position,
                    'end_index': current_position + len(segment_content),
                    'estimated_tokens': best_tokens,
                    'word_count': len(segment_content.split()),
                    'segment_type': 'semantic',
                    'contains_sentence_boundary': best_split.endswith(('.', '!', '?', '\n\n'))
                })

                # Update for next iteration
                current_position += len(segment_content)
                remaining = remaining[best_split_pos:].strip()

        return segments

    def _find_split_candidates(self, text: str) -> List[str]:
        """
        Find semantic split candidates in text.

        Args:
            text: Text to analyze

        Returns:
            List of split candidate strings
        """
        candidates = set()

        for pattern in SENTENCE_BOUNDARIES:
            found = re.findall(pattern, text)
            candidates.update(found)

        # Also add paragraph breaks
        para_pattern = r'\n\s*\n'
        found = re.findall(para_pattern, text)
        candidates.update(found)

        # Filter and sort by frequency (prefer common splits)
        seen = set()
        filtered = []
        for candidate in candidates:
            normalized = candidate.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                filtered.append(normalized)

        return filtered

    def _simple_tokenize(self, text: str) -> List[Dict]:
        """
        Simple text tokenization as fallback.

        Args:
            text: Text to tokenize

        Returns:
            List of tokenized segments
        """
        segments = []
        remaining = text
        current_position = 0

        # Simple chunk-based splitting
        chunk_size = int(self.max_tokens / self.estimator.token_ratio / 2)

        while remaining:
            # Estimate tokens for chunks
            test_chunk = remaining[:chunk_size]
            test_tokens = self.estimator.estimate(test_chunk)

            # If this chunk fits, use it
            if test_tokens <= self.max_tokens:
                segments.append({
                    'content': test_chunk,
                    'start_index': current_position,
                    'end_index': current_position + len(test_chunk),
                    'estimated_tokens': test_tokens,
                    'word_count': len(test_chunk.split()),
                    'segment_type': 'chunk',
                    'contains_sentence_boundary': test_chunk.endswith(('.', '!', '?', '\n\n'))
                })
                current_position += len(test_chunk)
                remaining = remaining[len(test_chunk):].strip()
            else:
                # Take smaller chunk
                scale = self.max_tokens / test_tokens
                test_chunk = remaining[:int(chunk_size * scale)]
                segments.append({
                    'content': test_chunk,
                    'start_index': current_position,
                    'end_index': current_position + len(test_chunk),
                    'estimated_tokens': self.estimator.estimate(test_chunk),
                    'word_count': len(test_chunk.split()),
                    'segment_type': 'chunk',
                    'contains_sentence_boundary': test_chunk.endswith(('.', '!', '?', '\n\n'))
                })
                current_position += len(test_chunk)
                remaining = remaining[len(test_chunk):].strip()

        return segments


class HierarchicalSegmenter:
    """
    Segments text hierarchically for nested summarization.

    This class supports:
    - Multi-level segmentation (document -> sections -> subsections)
    - Nested summarization preparation
    - Context preservation across levels
    """

    def __init__(self, tokenizer: SmartTokenizer = None,
                 max_segments_per_level: int = 3):
        """
        Initialize the hierarchical segmenter.

        Args:
            tokenizer: SmartTokenizer instance (creates default if None)
            max_segments_per_level: Max segments at each hierarchy level
        """
        self.tokenizer = tokenizer or SmartTokenizer()
        self.max_segments_per_level = max_segments_per_level
        self.levels = {
            'document': {'title': 'Document', 'level': 0},
            'section': {'title': 'Section', 'level': 1},
            'subsection': {'title': 'Subsection', 'level': 2},
            'paragraph': {'title': 'Paragraph', 'level': 3}
        }

    def segment_hierarchical(self, text: str, sections: Dict[str, str]) -> Dict:
        """
        Hierarchically segment text with nested structure.

        Args:
            text: Full document text
            sections: Section titles and their content

        Returns:
            Hierarchical segmentation structure
        """
        hierarchy = {
            'document': {'title': self.levels['document']['title'], 'segments': []},
            'sections': {}
        }

        # Segment document level
        doc_segments = self.tokenizer.tokenize(text)
        hierarchy['document']['segments'] = doc_segments

        # Segment each section
        for section_title, section_content in sections.items():
            if not section_content:
                continue

            # Tokenize section content
            section_segments = self.tokenizer.tokenize(section_content)

            # Create subsection structure
            hierarchy['sections'][section_title] = {
                'title': section_title,
                'content_length': len(section_content),
                'segments': section_segments
            }

        # Add paragraph-level segmentation for first few segments per section
        for section_title, section_data in hierarchy['sections'].items():
            if section_data and section_data['segments']:
                first_section = section_data['segments'][0]
                if first_section:
                    first_segments = self.tokenizer.tokenize(first_section['content'])
                    if first_segments:
                        hierarchy['sections'][section_title]['paragraphs'] = first_segments[:self.max_segments_per_level]

        return hierarchy

    def prepare_for_nested_summarization(self, hierarchy: Dict) -> List[Dict]:
        """
        Prepare hierarchical segments for nested summarization.

        Args:
            hierarchy: Hierarchical segmentation structure

        Returns:
            List of summarization tasks
        """
        tasks = []

        # Task 1: Document-level summary (from full document segments)
        if hierarchy.get('document', {}).get('segments'):
            tasks.append({
                'level': 'document',
                'prompt_context': 'full_document',
                'segments': hierarchy['document']['segments'],
                'max_output_tokens': 1000
            })

        # Task 2: Section-level summaries
        for section_title, section_data in hierarchy.get('sections', {}).items():
            if section_data.get('segments'):
                tasks.append({
                    'level': 'section',
                    'prompt_context': section_title,
                    'segments': section_data['segments'],
                    'max_output_tokens': 500
                })

        # Task 3: Subsection-level summaries (if available)
        for section_title, section_data in hierarchy.get('sections', {}).items():
            if section_data.get('paragraphs'):
                for paragraph in section_data['paragraphs'][:2]:
                    tasks.append({
                        'level': 'subsection',
                        'prompt_context': f"{section_title} - paragraph",
                        'segments': [paragraph],
                        'max_output_tokens': 300
                    })

        return tasks

    def merge_summarization_outputs(self, document_summary: str,
                                    section_summaries: Dict,
                                    subsection_summaries: Dict = None) -> str:
        """
        Merge summarization outputs at different levels.

        Args:
            document_summary: High-level document summary
            section_summaries: Section-level summaries
            subsection_summaries: Subsection-level summaries (optional)

        Returns:
            Merged summary with hierarchical structure
        """
        merged_parts = [document_summary]

        # Add section summaries
        for title, summary in section_summaries.items():
            merged_parts.append(f"\n\n## {title}")
            merged_parts.append(summary)

        # Add subsection summaries if available
        if subsection_summaries:
            for title, summary in subsection_summaries.items():
                merged_parts.append(f"\n### {title}")
                merged_parts.append(summary)

        return "\n".join(merged_parts)

    def get_cross_reference(self, hierarchy: Dict) -> Dict:
        """
        Generate cross-references between segments at different levels.

        Args:
            hierarchy: Hierarchical segmentation structure

        Returns:
            Cross-reference dictionary
        """
        cross_refs = {}

        for section_title, section_data in hierarchy.get('sections', {}).items():
            section_refs = {
                'references': [],
                'referenced_by': []
            }

            # Build references within section
            if section_data.get('segments'):
                for i, segment in enumerate(section_data['segments'][:self.max_segments_per_level]):
                    key = f"{section_title}_{i}"
                    cross_refs[key] = {
                        'segment': segment,
                        'level': 'section',
                        'referenced_by': []
                    }
                    section_refs['references'].append(key)

            # Find cross-section references
            for other_title, other_data in hierarchy.get('sections', {}).items():
                if other_title == section_title:
                    continue

                for j, other_segment in enumerate(other_data.get('segments', [])):
                    key = f"{other_title}_{j}"
                    if key in cross_refs:
                        cross_refs[key]['referenced_by'].append(section_title)
                        section_refs['referenced_by'].append(key)

        return cross_refs


class TextSegment:
    """
    Represents a text segment with metadata for summarization.

    Attributes:
        content: The text content
        start_index: Start position in original text
        end_index: End position in original text
        estimated_tokens: Estimated token count
        word_count: Word count
        title: Segment title (if applicable)
        level: Hierarchical level
        segment_type: Type of segment (semantic, chunk, single, etc.)
        contains_sentence_boundary: Whether segment ends with sentence boundary
    """

    def __init__(self, content: str, start_index: int = 0,
                 end_index: int = 0, estimated_tokens: int = 0,
                 word_count: int = 0, title: Optional[str] = None,
                 level: int = 0, segment_type: str = 'chunk',
                 contains_sentence_boundary: bool = False):
        """
        Initialize a text segment.

        Args:
            content: Text content
            start_index: Start position in original text
            end_index: End position in original text
            estimated_tokens: Estimated token count
            word_count: Word count
            title: Optional segment title
            level: Hierarchical level
            segment_type: Type of segment
            contains_sentence_boundary: Whether segment ends with sentence boundary
        """
        self.content = content
        self.start_index = start_index
        self.end_index = end_index
        self.estimated_tokens = estimated_tokens
        self.word_count = word_count
        self.title = title
        self.level = level
        self.segment_type = segment_type
        self.contains_sentence_boundary = contains_sentence_boundary

    def __repr__(self) -> str:
        return f"TextSegment(content={self.content[:50]}..., tokens={self.estimated_tokens})"

    def to_dict(self) -> Dict:
        """
        Convert segment to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            'content': self.content,
            'start_index': self.start_index,
            'end_index': self.end_index,
            'estimated_tokens': self.estimated_tokens,
            'word_count': self.word_count,
            'title': self.title,
            'level': self.level,
            'segment_type': self.segment_type,
            'contains_sentence_boundary': self.contains_sentence_boundary
        }
