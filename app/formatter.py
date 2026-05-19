# app/formatter.py
"""
Formatter module for PDF/EPUB text extraction and markdown formatting.

This module handles:
1. Raw text extraction and formatting from PDF/EPUB files
2. Nested text segmentation based on token counts (max 3000 tokens per segment)
3. Markdown formatting for the extracted text
4. Semantic-aware segmentation that preserves meaning across segments
"""

import re
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import fitz  # PyMuPDF


# Constants for token estimation
# These are rough estimates and can be adjusted based on your specific use case
DEFAULT_TOKEN_PER_CHAR_RATIO = 0.05  # Approximate tokens per character (varies by text)
MAX_TOKENS_PER_SEGMENT = 3000
MIN_TOKENS_PER_SEGMENT = 100  # To avoid overly small segments
DEFAULT_CHUNK_SIZE = 4096  # Default PDF page chunk size for splitting


@dataclass
class TextSegment:
    """Represents a text segment with its metadata."""
    content: str
    start_index: int
    end_index: int
    title: Optional[str] = None
    level: int = 0  # Hierarchical level (0 = root)
    page_numbers: List[int] = field(default_factory=list)
    word_count: int = 0
    estimated_tokens: int = 0


class TextFormatter:
    """
    Handles text extraction, segmentation, and formatting from PDF/EPUB files.

    Features:
    - Extracts and formats text from PDF/EPUB files
    - Segments text based on token counts to avoid hallucinations
    - Preserves semantic meaning across segments
    - Generates properly formatted markdown output
    """

    def __init__(self, max_tokens_per_segment: int = MAX_TOKENS_PER_SEGMENT):
        """
        Initialize the text formatter.

        Args:
            max_tokens_per_segment: Maximum tokens allowed per segment (default: 3000)
        """
        self.max_tokens_per_segment = max_tokens_per_segment
        self.current_token_ratio = DEFAULT_TOKEN_PER_CHAR_RATIO  # Will be refined
        self.text_segments: List[TextSegment] = []
        self.segmentation_level = 0  # 0 = raw text, 1+ = summarized

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate the number of tokens in a text.

        This uses character count as a proxy since we don't have access to
        an actual tokenizer in the pure Python environment. In a production
        setup, you might integrate with tiktoken or similar for accurate counts.

        Args:
            text: The text to estimate tokens for

        Returns:
            Estimated token count
        """
        # Adjust token ratio based on text complexity
        if len(text) > 1000:
            # Longer texts might have more complex tokenization
            self.current_token_ratio = DEFAULT_TOKEN_PER_CHAR_RATIO * 1.1
        else:
            self.current_token_ratio = DEFAULT_TOKEN_PER_CHAR_RATIO

        return max(MIN_TOKENS_PER_SEGMENT, int(len(text) * self.current_token_ratio))

    def extract_text_from_pdf(self, doc: fitz.Document) -> Dict[str, List[TextSegment]]:
        """
        Extract and segment text from a PDF document.

        Args:
            doc: PyMuPDF document object

        Returns:
            Dictionary mapping section titles to their text segments
        """
        sections: Dict[str, List[TextSegment]] = defaultdict(list)

        # Get table of contents if available
        toc = doc.get_toc()

        if toc and toc[0]:
            # Use existing TOC structure
            toc_entries = toc
        else:
            # Try to extract headings automatically
            toc_entries = self._extract_headings_from_pdf(doc)

        if not toc_entries:
            # Fall back to full text extraction without segmentation
            return self._full_text_extraction(doc)

        # Process each TOC entry
        for entry in toc_entries:
            if not entry[1]:  # Empty title
                continue

            section_title = entry[1]
            start_page = entry[2]
            end_page = entry[3] if len(entry) > 3 else doc.page_count - 1

            # Extract text for this section
            section_text = self._extract_section_text(
                doc, start_page, end_page, section_title
            )

            # Segment the text
            segments = self._segment_text(section_text, section_title, level=1)
            sections[section_title.lower()] = segments

        return dict(sections)

    def _extract_headings_from_pdf(self, doc: fitz.Document) -> List[Tuple[int, str]]:
        """
        Extract headings from a PDF document.

        Args:
            doc: PyMuPDF document object

        Returns:
            List of tuples: (level, title, start_page, end_page)
        """
        headings = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]

            for block in blocks:
                if "lines" not in block:
                    continue

                # Check font sizes to identify headings
                lines = block["lines"]
                if not lines:
                    continue

                # Analyze font characteristics
                font_sizes = []
                heading_candidates = []

                for line in lines:
                    for span in line.get("spans", []):
                        size = span.get("size", 0)
                        flags = span.get("flags", 0)
                        text = span.get("text", "").strip()

                        if not text or text == " ":
                            continue

                        # Track font sizes
                        font_sizes.append(size)

                        # Check if this is likely a heading
                        # Headings are typically larger, bold, or have specific patterns
                        if size > 12 or (flags & 2**4):  # Bold flag
                            heading_candidates.append({
                                "text": text,
                                "size": size,
                                "position": span.get("bbox", [0, 0, 0, 0])[1],
                                "page": page_num + 1
                            })

                # Sort headings by position
                heading_candidates.sort(key=lambda x: x["position"])

                # Group consecutive headings into sections
                if heading_candidates:
                    last_heading = heading_candidates[0]
                    section_start = last_heading["page"]
                    section_text = last_heading["text"]

                    for candidate in heading_candidates[1:]:
                        if candidate["position"] > last_heading["position"] + 50:
                            # End of current section
                            level = self._estimate_heading_level(heading_candidates[:len(heading_candidates)])
                            headings.append((
                                level,
                                last_heading["text"],
                                section_start,
                                candidate["position"] - 50
                            ))
                            section_text = candidate["text"]
                            section_start = candidate["page"]
                            last_heading = candidate
                        else:
                            section_text += " " + candidate["text"]

                    # Add final section
                    level = self._estimate_heading_level(heading_candidates)
                    headings.append((
                        level,
                        last_heading["text"],
                        section_start,
                        doc.page_count
                    ))

        return headings

    def _estimate_heading_level(self, candidates: List[dict]) -> int:
        """
        Estimate the hierarchical level of a heading based on font characteristics.

        Args:
            candidates: List of heading candidates with their font info

        Returns:
            Estimated heading level (1-6, where 1 is highest)
        """
        if not candidates:
            return 1

        # Larger fonts = higher level headings
        max_size = max(c.get("size", 0) for c in candidates)
        median_size = sum(c.get("size", 0) for c in candidates) / len(candidates)

        # Use font size ratio to estimate level
        if max_size > 20:
            return 1  # Very large font = top-level heading
        elif max_size > 14:
            return 2
        elif max_size > 12:
            return 3
        else:
            return 4

    def _extract_section_text(self, doc: fitz.Document, start_page: int,
                              end_page: int, section_title: str) -> str:
        """
        Extract text for a specific section.

        Args:
            doc: PyMuPDF document
            start_page: Starting page number (0-indexed)
            end_page: Ending page number (0-indexed)
            section_title: Title of the section

        Returns:
            Extracted text for the section
        """
        text_parts = []

        for page_num in range(start_page, min(end_page + 1, len(doc))):
            page = doc[page_num]
            page_text = page.get_text("text")

            # Skip headers and footers
            text_parts.append(page_text)

        return "\n\n".join(text_parts)

    def _segment_text(self, text: str, title: Optional[str] = None,
                      level: int = 0) -> List[TextSegment]:
        """
        Segment text into semantically meaningful parts based on token count.

        This uses a greedy approach: it takes the largest possible segment
        that doesn't exceed the token limit, then recursively processes the rest.

        Args:
            text: The full text to segment
            title: Optional title for the section
            level: Hierarchical level (0 = raw, 1+ = summarized)

        Returns:
            List of TextSegment objects
        """
        if not text:
            return []

        estimated_tokens = self.estimate_tokens(text)

        # If text is small enough, return as single segment
        if estimated_tokens <= self.max_tokens_per_segment:
            return [TextSegment(
                content=text,
                start_index=0,
                end_index=len(text),
                title=title,
                level=level,
                estimated_tokens=estimated_tokens,
                word_count=len(text.split())
            )]

        # Need to split the text
        # Use sentence boundaries as preferred split points
        segments = self._smart_split(text, title, level)

        return segments

    def _smart_split(self, text: str, title: Optional[str] = None,
                     level: int = 0) -> List[TextSegment]:
        """
        Smart text splitting using semantic boundaries.

        This prefers to split at:
        1. End of paragraphs
        2. Section breaks
        3. Sentence boundaries

        Args:
            text: Text to split
            title: Optional section title
            level: Hierarchical level

        Returns:
            List of properly split segments
        """
        # Find potential split points (prefer paragraph breaks)
        split_candidates = self._find_split_candidates(text)

        if not split_candidates:
            # Fall back to simple splitting
            return self._simple_split(text, title, level)

        # Greedy approach: take largest valid segment
        segments = []
        remaining = text

        while remaining:
            # Find the longest valid segment from the current position
            best_split = None
            best_index = None

            for candidate in split_candidates:
                split_pos = remaining.find(candidate)
                if split_pos == -1:
                    continue

                # Calculate segment with this split
                end_pos = split_pos + len(candidate)
                if end_pos > len(remaining):
                    end_pos = len(remaining)

                segment = remaining[:end_pos]
                estimated_tokens = self.estimate_tokens(segment)

                # Check if this segment fits within limits
                if estimated_tokens <= self.max_tokens_per_segment:
                    # Prefer larger segments
                    if best_index is None or end_pos > best_index:
                        best_split = candidate
                        best_index = end_pos

            if best_index is None:
                # No valid split found, use simple splitting
                return self._simple_split(text, title, level)

            # Create segment
            segment = remaining[:best_index]
            segments.append(TextSegment(
                content=segment,
                start_index=text.find(remaining[:best_index]),
                end_index=text.find(remaining[:best_index]) + best_index,
                title=title,
                level=level,
                estimated_tokens=self.estimate_tokens(segment),
                word_count=len(segment.split())
            ))

            # Move to next segment
            remaining = remaining[best_index:].strip()

        return segments

    def _find_split_candidates(self, text: str) -> List[str]:
        """
        Find potential text split candidates at semantic boundaries.

        Args:
            text: The text to analyze

        Returns:
            List of strings to use as split points
        """
        candidates = []

        # Pattern 1: Paragraph breaks (double newlines)
        para_pattern = r'\n\s*\n'
        candidates.extend(re.findall(para_pattern, text))

        # Pattern 2: Section headers (capitalized words followed by newline)
        header_pattern = r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:\s*\d+)?:\s*\n'
        candidates.extend(re.findall(header_pattern, text))

        # Pattern 3: List item breaks
        list_pattern = r'([^-+•]\s*$)'
        candidates.extend(re.findall(list_pattern, text))

        # Remove duplicates and filter
        seen = set()
        unique_candidates = []
        for candidate in candidates:
            normalized = candidate.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique_candidates.append(normalized)

        return unique_candidates

    def _simple_split(self, text: str, title: Optional[str] = None,
                      level: int = 0) -> List[TextSegment]:
        """
        Simple text splitting when semantic boundaries are not available.

        Args:
            text: Text to split
            title: Optional section title
            level: Hierarchical level

        Returns:
            List of segments
        """
        segments = []
        remaining = text
        current_pos = 0

        while remaining:
            # Estimate tokens for chunks of text
            chunk_size = DEFAULT_CHUNK_SIZE * (self.max_tokens_per_segment // MIN_TOKENS_PER_SEGMENT)

            # If remaining text is small, take it all
            estimated_tokens = self.estimate_tokens(remaining)

            if estimated_tokens <= self.max_tokens_per_segment:
                segments.append(TextSegment(
                    content=remaining,
                    start_index=current_pos,
                    end_index=current_pos + len(remaining),
                    title=title,
                    level=level,
                    estimated_tokens=estimated_tokens,
                    word_count=len(remaining.split())
                ))
                break
            else:
                # Split at the last reasonable position
                test_chunk = remaining[:chunk_size]
                test_tokens = self.estimate_tokens(test_chunk)

                if test_tokens <= self.max_tokens_per_segment:
                    segments.append(TextSegment(
                        content=test_chunk,
                        start_index=current_pos,
                        end_index=current_pos + len(test_chunk),
                        title=title,
                        level=level,
                        estimated_tokens=test_tokens,
                        word_count=len(test_chunk.split())
                    ))
                    current_pos += len(test_chunk)
                    remaining = remaining[len(test_chunk):].strip()
                else:
                    # Take a smaller chunk
                    scale = self.max_tokens_per_segment / test_tokens
                    test_chunk = remaining[:int(chunk_size * scale)]
                    segments.append(TextSegment(
                        content=test_chunk,
                        start_index=current_pos,
                        end_index=current_pos + len(test_chunk),
                        title=title,
                        level=level,
                        estimated_tokens=self.estimate_tokens(test_chunk),
                        word_count=len(test_chunk.split())
                    ))
                    current_pos += len(test_chunk)
                    remaining = remaining[len(test_chunk):].strip()

        return segments

    def extract_text_from_epub(self, epub_path: str) -> Dict[str, List[TextSegment]]:
        """
        Extract and segment text from an EPUB file.

        Args:
            epub_path: Path to the EPUB file

        Returns:
            Dictionary mapping section titles to their text segments
        """
        import zipfile

        segments_dict: Dict[str, List[TextSegment]] = defaultdict(list)

        with zipfile.ZipFile(epub_path, 'r') as epub:
            # Read all HTML content
            html_files = [
                f for f in epub.namelist()
                if f.endswith(('.html', '.xhtml', '.htm'))
            ]

            for html_file in html_files:
                try:
                    content = epub.read(html_file).decode('utf-8', errors='ignore')
                    segments = self._extract_from_html(content)
                    segments_dict.update(segments)
                except Exception as e:
                    print(f"Error reading {html_file}: {e}")
                    continue

        return dict(segments_dict)

    def _extract_from_html(self, content: str) -> Dict[str, List[TextSegment]]:
        """
        Extract text from HTML content (EPUB chapters).

        Args:
            content: HTML content

        Returns:
            Dictionary of text segments
        """
        segments_dict: Dict[str, List[TextSegment]] = defaultdict(list)

        # Find all headings
        heading_pattern = r'<h([1-6])[^>]*>([^<]+)</h[1-6]>'
        headings = re.findall(heading_pattern, content, re.IGNORECASE)

        for level_str, title in headings:
            level = int(level_str)

            # Extract content between this heading and the next
            start_pos = content.find(f'</h{level}>') + len(f'</h{level}>')
            next_heading_pattern = rf'<h{level}[^>]*>|<h[1-9]{level + 1 if level < 6 else 1}[^>]*>'

            if level == 1:
                # Top-level heading goes to end
                end_pos = len(content)
            else:
                # Find next heading at same or higher level
                remaining_content = content[start_pos:]
                next_match = re.search(rf'<h({level}|[1-{level - 1 if level > 1 else 9})[^>]*>', remaining_content, re.IGNORECASE)
                if next_match:
                    end_pos = start_pos + next_match.start()
                else:
                    end_pos = len(content)

            title = title.strip()
            if not title:
                continue

            section_text = content[start_pos:end_pos].strip()

            # Add to segments
            segments_dict[title.lower()].append(TextSegment(
                content=section_text,
                start_index=start_pos,
                end_index=end_pos,
                title=title,
                level=level,
                estimated_tokens=self.estimate_tokens(section_text),
                word_count=len(section_text.split())
            ))

        return dict(segments_dict)

    def format_as_markdown(self, sections: Dict[str, List[TextSegment]],
                          include_raw: bool = False) -> str:
        """
        Format extracted text segments as markdown.

        Args:
            sections: Dictionary of section title to text segments
            include_raw: Whether to include raw formatted text

        Returns:
            Formatted markdown string
        """
        markdown_parts = []

        for section_title, segments in sorted(sections.items(), key=lambda x: x[0].lower()):
            if not section_title or not segments:
                continue

            # Determine heading level
            if include_raw:
                # Include formatted raw text
                formatted_text = self._format_raw_text(segments)
                markdown_parts.append(self._section_to_markdown(
                    section_title, formatted_text, level=0
                ))
            else:
                # Include summary-level text
                markdown_parts.append(self._section_to_markdown(
                    section_title, segments, level=0
                ))

        return "\n\n".join(markdown_parts)

    def _section_to_markdown(self, title: str, content: str | List[TextSegment],
                            level: int = 0) -> str:
        """
        Convert a section to markdown format.

        Args:
            title: Section title
            content: Content as string or list of segments
            level: Heading level

        Returns:
            Markdown formatted section
        """
        if isinstance(content, list):
            # Multiple segments - concatenate
            text = "\n\n".join(segment.content for segment in content)
        else:
            text = content

        # Escape markdown special characters
        text = self._escape_markdown(text)

        # Build markdown
        if level > 0:
            heading = f"## " + title.replace("#", "\u2020")
        else:
            heading = f"# {title}"

        return f"{heading}\n\n{text}\n\n"

    def _format_raw_text(self, segments: List[TextSegment]) -> str:
        """
        Format raw text segments with proper markdown formatting.

        Args:
            segments: List of text segments

        Returns:
            Formatted text
        """
        text_parts = []

        for i, segment in enumerate(segments):
            # Add markdown formatting for lists
            formatted = self._apply_markdown_formatting(segment.content)
            text_parts.append(formatted)

        return "\n\n".join(text_parts)

    def _apply_markdown_formatting(self, text: str) -> str:
        """
        Apply basic markdown formatting to text.

        Args:
            text: Plain text

        Returns:
            Markdown formatted text
        """
        # Convert bullet points
        text = re.sub(r'^\s*•\s+(.+)$', r'- \1', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*[-*]\s+(.+)$', r'- \1', text, flags=re.MULTILINE)

        # Convert numbered lists
        text = re.sub(r'^\s*\d+\.\s+(.+)$', r'1. \1', text, flags=re.MULTILINE)

        # Convert bold text
        text = re.sub(r'\*\*(.+?)\*\*', r'**\1**', text)

        # Convert italic text
        text = re.sub(r'\*(.+?)\*', r'*\1*', text)

        # Convert code
        text = re.sub(r'`([^`]+)`', r'`\1`', text)

        return text

    def _escape_markdown(self, text: str) -> str:
        """
        Escape special markdown characters.

        Args:
            text: Text to escape

        Returns:
            Escaped text
        """
        # Escape backslashes first
        text = text.replace('\\', r'\')

        # Escape other special characters
        text = text.replace('#', r'\#')
        text = text.replace('*', r'\*')
        text = text.replace('_', r'\_')
        text = text.replace('[', r'\[')
        text = text.replace(']', r'\]')
        text = text.replace('(', r'\(')
        text = text.replace(')', r'\)')
        text = text.replace('|', r'\|')
        text = text.replace('>', r'\>')
        text = text.replace('~', r'\~')
        text = text.replace('`', r'\`')

        return text

    def create_nested_summary(self, sections: Dict[str, List[TextSegment]],
                             max_segments: int = 3) -> Dict[str, str]:
        """
        Create nested summaries at different levels.

        This creates summaries at multiple levels of granularity:
        - Level 0: Full document
        - Level 1: Main sections
        - Level 2: Subsections

        Args:
            sections: Dictionary of text segments
            max_segments: Maximum number of segments to consider at each level

        Returns:
            Dictionary mapping levels to summary strings
        """
        summaries = {}

        # Level 0: Full document
        full_text = "\n\n".join(
            segment.content for segments in sections.values()
            for segment in segments[:max_segments]
        )
        summaries['full'] = full_text

        # Level 1: Main sections
        level1_summaries = {}
        for title, segments in sections.items():
            if not segments:
                continue

            # Take the first segment as representative
            if segments:
                level1_summaries[title] = segments[0].content

        summaries['section'] = level1_summaries

        # Level 2: Subsections (if any)
        level2_summaries = {}
        for title, segments in sections.items():
            for i, segment in enumerate(segments[:2]):
                key = f"{title} (para {i+1})"
                level2_summaries[key] = segment.content

        summaries['subsection'] = level2_summaries

        return summaries

    def get_text_statistics(self, sections: Dict[str, List[TextSegment]]) -> Dict:
        """
        Get statistics about the extracted text.

        Args:
            sections: Dictionary of text segments

        Returns:
            Statistics dictionary
        """
        total_words = 0
        total_tokens = 0
        segment_count = 0

        for segments in sections.values():
            for segment in segments:
                total_words += segment.word_count
                total_tokens += segment.estimated_tokens
                segment_count += 1

        return {
            'total_words': total_words,
            'total_tokens': total_tokens,
            'segment_count': segment_count,
            'average_tokens_per_segment': total_tokens / max(1, segment_count),
            'segments_per_section': {
                title: len(segments)
                for title, segments in sections.items()
            }
        }
