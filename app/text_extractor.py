# ========================================================================================#
#                                       IDLEARN                                           #
#                                  text_extractor.py                                      #
# ========================================================================================#
"""
Filename: text_extractor.py
Author: Timothy Piton
Date of creation: 05 Jul 2025

This script defines the class TextExtractor. This class defines functions to extract
text in a structured, systematic way by using the ToC information either provided by the
file, or automatically inferred by the styling (font, keywords, etc) detected in the file.
"""

import hashlib
import os
import re
from collections import Counter

from .logger import logger
from .toc_extractor import TOCExtractor


class TextExtractor:
    def __init__(self, doc):
        self.doc = doc
        self.toc = self.get_toc()
        self.augment_toc_with_typography()

    def _convertTOC(self, tocEntries) -> list:
        toc_list = []
        for entry in tocEntries:
            tuple_entry = (entry.level, entry.title, entry.page)
            toc_list.append(tuple_entry)

        return toc_list

    # Returns the formatted ToC (comprising the end page of each section)
    def get_toc(self):
        from .logger import logger
        from .utils import get_toc as utils_get_toc
        try:
            self.toc = utils_get_toc(self.doc)
            return self.toc
        except Exception as e:
            logger.error(f"Error extracting TOC: {e}", exc_info=True)
            raise

    def info_extract(self) -> tuple:
        """
        Getting the info from PDF
        """
        # Defining page height from first page
        pheight = self.doc[0].rect.height

        # Defining frame height
        PFRAME = 50

        # Computing dominant text size throughout the document
        main_size = self.get_main_size()
        main_font = self.get_main_font()

        return (pheight, PFRAME, main_size, main_font)

    def get_main_size(self) -> int:
        """
        Returns the main text's size of a document.
        """
        font_sizes = []
        for page in self.doc:
            text_dict = page.get_text("dict")
            blocks = text_dict["blocks"]
            for block in blocks:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if not re.match(r"[\s\t]+", span["text"]):
                            font_sizes.append(round(span["size"]))
        size_count = Counter(font_sizes)
        dominant_size = size_count.most_common(2)
        if (
            dominant_size[1][0] > dominant_size[0][0]
            and dominant_size[1][1] > dominant_size[0][0] / 2
        ):
            main_size = round(dominant_size[1][0])
        else:
            main_size = round(dominant_size[0][0])

        return main_size

    def get_main_font(self) -> tuple:
        """
        Returns the main text's font of a document.
        """
        fonts = []
        for page in self.doc:
            text_dict = page.get_text("dict")
            blocks = text_dict["blocks"]
            for block in blocks:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if not re.match(r"[\s\t]+", span["text"]):
                            fonts.append(span["font"])
        font_count = Counter(fonts)
        dominant_font = font_count.most_common(1)[0]
        if type(dominant_font) is tuple:
            dominant_font = dominant_font[0]

        return dominant_font

    def get_main_font_size(self) -> int | tuple:
        """
        Returns the main text's font size of a document.
        """
        font_sizes = []
        for page in self.doc:
            text_dict = page.get_text("dict")
            blocks = text_dict["blocks"]
            for block in blocks:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if not re.match(r"[\s\t]+", span["text"]):
                            font_sizes.append(span["size"])
        font_size_count = Counter(font_sizes)
        dominant_size = font_size_count.most_common(1)[0]
        if type(dominant_size) is tuple:
            return dominant_size[1]
        else:
            return dominant_size

    # ------------------------------------------------------------------
    # Typography-based subsection detection
    # ------------------------------------------------------------------

    def _is_heading_by_typography(self, span, text, main_size, main_font):
        """
        Determine if a span is likely a heading based on typographic cues:
        - Different font size from the main body text
        - Different font type (family or bold/italic variant)
        - Different case (ALL CAPS, Title Case for short text)
        """
        if not text or len(text) < 3:
            return False
        # Too long to be a heading
        if len(text) > 150:
            return False
        # Skip figure/table captions and page numbers
        if re.match(r"^(Fig(ure)?|Table)\\s*\\d+", text, re.IGNORECASE):
            return False
        if re.match(r"^\\d+$", text.strip()):
            return False

        size = span.get("size", main_size)
        font = span.get("font", main_font or "")
        flags = span.get("flags", 0)
        is_bold = bool(flags & (1 << 4))

        base_font = re.sub(r"[+\\-].*", "", font) if font else ""
        base_main = re.sub(r"[+\\-].*", "", main_font) if main_font else ""

        # 1. Different font size (larger than main text)
        if size > main_size + 0.5:
            return True

        # 2. Different font family
        if base_font and base_main and base_font != base_main:
            return True

        # 3. Bold text that is short (likely a heading, not emphasis in body text)
        if is_bold and len(text.split()) <= 12 and size >= main_size - 0.5:
            return True

        # 4. ALL CAPS text with multiple words (likely a section heading)
        if text.isupper() and len(text.split()) >= 2 and len(text) < 80:
            return True

        return False

    def _compute_heading_level_by_typography(
        self, span, text, main_size, main_font, heading_sizes
    ):
        """
        Determine the relative heading level (1 = most prominent) based on
        typographic hierarchy.

        heading_sizes is sorted largest-first and contains the distinct font
        sizes found among heading candidates.

        The primary determinant is font size. Secondary cues (bold, font
        family, case) adjust the level by at most one step.
        """
        size = round(span.get("size", main_size), 1)

        # Base level from font size position in the heading hierarchy
        level = len(heading_sizes) + 1  # default: below any known heading size
        for i, hs in enumerate(heading_sizes):
            if abs(size - hs) < 0.5:
                level = i + 1  # 1-based, smaller = more prominent
                break

        # Secondary typographic cues – adjust by at most one level
        font = span.get("font", "")
        flags = span.get("flags", 0)
        is_bold = bool(flags & (1 << 4))
        base_font = re.sub(r"[+\\-].*", "", font) if font else ""
        base_main = re.sub(r"[+\\-].*", "", main_font) if main_font else ""

        secondary_cues = 0
        if is_bold:
            secondary_cues += 1
        if base_font and base_main and base_font != base_main:
            secondary_cues += 1
        if text.isupper() and len(text) < 50 and len(text.split()) <= 8:
            secondary_cues += 1

        # At least two secondary cues promote the heading one level
        if secondary_cues >= 2 and level > 1:
            level -= 1

        return level

    @staticmethod
    def _titles_match(text1, text2):
        """Fuzzy title comparison: strip punctuation/spaces and compare lower-case."""
        t1 = re.sub(r"[ ,.:?!]", "", text1.lower().strip())
        t2 = re.sub(r"[ ,.:?!]", "", text2.lower().strip())
        return t1 == t2 or t1 in t2 or t2 in t1

    def detect_subsections(self, start_page, end_page, parent_level=1, parent_title=""):
        """
        Detect subsections within a page range using typographic cues.

        Scans all lines whose font size, font type, or case differs from the
        main body text and assigns hierarchical levels based on relative
        typography.

        Args:
            start_page:  First page (1-based, inclusive).
            end_page:    Last page (1-based, inclusive).
            parent_level: ToC level of the parent section.
            parent_title: Title of the parent section (to skip it).

        Returns:
            A list of (level, title, start_page, end_page) tuples.
        """
        if not hasattr(self, "_cached_info"):
            self._cached_info = self.info_extract()
        pheight, pframe, main_size, main_font = self._cached_info

        doc_format = self.doc.metadata.get("format", "").lower()

        heading_candidates = []

        for page_num in range(start_page - 1, end_page):
            page = self.doc.load_page(page_num)
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                # Skip header/footer regions
                if "pdf" in doc_format:
                    if block["bbox"][1] < pframe or block["bbox"][3] > pheight - pframe:
                        continue
                for line in block.get("lines", []):
                    spans = self.get_span(line)
                    if not spans:
                        continue
                    first_span = spans[0]
                    combined_text = " ".join(s["text"] for s in spans).strip()
                    if not combined_text or len(combined_text) < 3:
                        continue

                    # Skip lines that match the parent section title
                    if parent_title and self._titles_match(combined_text, parent_title):
                        continue
                    # Skip lines that match any existing ToC entry
                    if any(self._titles_match(combined_text, s[1]) for s in self.toc):
                        continue

                    if self._is_heading_by_typography(
                        first_span, combined_text, main_size, main_font
                    ):
                        heading_candidates.append(
                            {
                                "text": combined_text,
                                "span": first_span,
                                "page": page_num + 1,
                            }
                        )

        if not heading_candidates:
            return []

        # Deduplicate (same normalised text on same page)
        seen = set()
        unique = []
        for h in heading_candidates:
            key = (h["text"].lower().strip()[:60], h["page"])
            if key not in seen:
                seen.add(key)
                unique.append(h)
        heading_candidates = unique

        # Build font-size hierarchy among the heading candidates
        heading_sizes = sorted(
            set(round(h["span"]["size"], 1) for h in heading_candidates),
            reverse=True,
        )

        # Assign levels relative to parent
        raw = []
        for h in heading_candidates:
            relative = self._compute_heading_level_by_typography(
                h["span"], h["text"], main_size, main_font, heading_sizes
            )
            level = parent_level + relative
            raw.append((level, h["text"], h["page"]))

        # Compute end pages: next heading at same or higher level ends this one
        result = []
        for i, (lvl, title, pg) in enumerate(raw):
            end = end_page
            for j in range(i + 1, len(raw)):
                if raw[j][0] <= lvl:
                    end = raw[j][2]
                    break
            result.append((lvl, title, pg, end))

        return result

    def augment_toc_with_typography(self):
        """
        For every section in the ToC that has no children, scan its page
        range for typographically distinct sub-headings and insert them
        into ``self.toc`` so that the extraction pipeline can partition
        the text into a finer hierarchy.
        """
        if not self.toc:
            return

        new_entries = []

        for section in list(self.toc):  # iterate over a snapshot
            children = self.get_children(section)
            if not children:
                subsections = self.detect_subsections(
                    start_page=section[2],
                    end_page=section[3],
                    parent_level=section[0],
                    parent_title=section[1],
                )
                if subsections:
                    new_entries.extend(subsections)

        if new_entries:
            self.toc.extend(new_entries)
            # Sort by page, then by level (so deeper sections come after
            # their parents on the same page)
            self.toc.sort(key=lambda s: (s[2], s[0]))
            logger.info(
                f"Augmented ToC with {len(new_entries)} typographically "
                f"detected subsection(s)"
            )

    def toc2dtoc(self) -> dict:
        """
        Returns the dictionary version of ToC.
        """
        root = {}
        stack = [(0, root)]  # stack of (level, current_dict)
        if self.toc is not None:
            for level, title, startpage, endpage in self.toc:
                current_dict = {}
                while stack and level <= stack[-1][0]:
                    stack.pop()
                stack[-1][1][(level, title, startpage, endpage)] = {
                    "_page": (startpage, endpage),
                    "_sub": current_dict,
                }
                stack.append((level, current_dict))
        else:
            return {}

        def cleanup(d):
            return {
                k: cleanup(v["_sub"]) if v["_sub"] else {"_page": v["_page"]}
                for k, v in d.items()
            }

        return cleanup(root)

    # Returns the first parent section of secname
    def _get_toc_index(self, section):
        if self.toc is None:
            return -1
        try:
            return self.toc.index(section)
        except ValueError:
            # Fallback: match by level and title if exact tuple match fails
            for i, sec in enumerate(self.toc):
                if sec[0] == section[0] and sec[1] == section[1]:
                    return i
            return -1

    def get_parent(self, section: tuple):
        """
        Returns the parent section of the given section.
        Iteratively searches backwards through the flat TOC for the first
        section with a strictly lower hierarchical level.
        """
        idx = self._get_toc_index(section)
        if idx == -1:
            return None

        for i in range(idx - 1, -1, -1):
            if self.toc[i][0] < section[0]:
                return self.toc[i]
        return None

    def get_children(self, section) -> list:
        """Returns the list of all the descendance of a section."""
        subsections = []
        level = section[0]
        idx = self._get_toc_index(section)

        if idx != -1:
            for sec in self.toc[idx + 1 :]:
                if sec[0] > level:
                    subsections.append(sec)
                elif sec[0] == level:
                    break
            return subsections

        return []

    def get_next_section(self, section) -> tuple:
        """Returns the section following the given section."""
        level = section[0]
        idx = self._get_toc_index(section)

        if idx != -1:
            for sec in self.toc[idx + 1 :]:
                if sec[0] <= level:
                    return sec
        return None

        return ()

    def get_span(self, line) -> list:
        """
        Returns the different spans composing a line. Each span will have a different font, size, or both than the other spans of the line.
        """
        spans = []
        span = {}
        for s in line.get("spans", []):
            s["font"] = re.sub(r"\+.*", "", s["font"])
            if not re.match(r"[\s\t]+$", s["text"]):
                s["text"] = re.sub(
                    r".*(\\u200[0-9a])+.*",
                    " ",
                    re.sub(r".*(\\xa[d0])+.*", "", s["text"]),
                )
                if span == {}:
                    span = {"text": s["text"], "font": s["font"], "size": s["size"]}
                else:
                    if re.match(r"(([A-Z]+\s)+)?[A-Z]$", span["text"].strip(" ,.:?!")):
                        span["text"] = span["text"] + s["text"]
                        span["size"] = s["size"]
                        span["font"] = s["font"]

                    elif span["font"] != s["font"] or span["size"] != s["size"]:
                        if re.match(r"[A-Z]+$", s["text"]):
                            span["text"] = span["text"] + " " + s["text"]
                        else:
                            spans.append(span.copy())
                            span = {
                                "text": s["text"],
                                "font": s["font"],
                                "size": s["size"],
                            }

                    elif re.match(r"(\s)?[ﬁﬂ—](\s)?$", s["text"]) or re.match(
                        r"[ﬁﬂ—]$", span["text"][-1]
                    ):
                        span["text"] = span["text"] + s["text"]

                    elif span["font"] == s["font"] and span["size"] == s["size"]:
                        if " " in (s["text"][0], span["text"][-1]) or (
                            len(span["text"]) > 1
                            and re.match(r"^\s[A-Z]$", span["text"][-2:])
                        ):
                            span["text"] = span["text"] + s["text"]
                        else:
                            span["text"] = span["text"] + " " + s["text"]
                    else:
                        continue
        if span != {}:
            spans.append(span)
        for span in spans:
            span["text"] = span["text"].strip()
            span["text"] = re.sub(r"(\\u200[0-9a])+", " ", span["text"])
            # Removing references
            span["text"] = re.sub(r"(;\s)?\[\s(\d(\s,\s+)?)+\s\]", "", span["text"])
            span["text"] = re.sub(r"(;\s)?\[\s\d+\s–\s\d+\s\]", "", span["text"])
            # Formatting spaces surrounding commas, dots, and parentheses
            span["text"] = re.sub(r"\(\s", "(", span["text"])
            span["text"] = re.sub(r"\s\)", ")", span["text"])
            # Removing multiple spaces (strip method fails)
            span["text"] = re.sub(r"\s+", " ", span["text"])
            # Replacing the 'ﬁ' and 'ﬂ' characters with correct "fi" string
            span["text"] = re.sub(r"ﬁ", "fi", span["text"])
            span["text"] = re.sub(r"ﬂ", "fl", span["text"])
        return spans

    # ------------------------------------------------------------------
    # Image extraction
    # ------------------------------------------------------------------

    def extract_section_images(self, sections, output_dir=None):
        """Extract relevant images from PDF pages for the given sections.

        Filters out tiny images (icons, bullets), repeated images that appear
        on many pages (watermarks, logos), and 1px images (spacers).  Returns
        a dict mapping section titles to lists of extracted image file paths.

        Args:
            sections: List of (level, title, start_page, end_page) tuples.
            output_dir: Directory to save images.  Defaults to
                        ./extracted_images/.

        Returns:
            dict: {section_title: [image_path, ...]}
        """
        from .logger import logger

        if output_dir is None:
            output_dir = os.path.join(os.getcwd(), "extracted_images")
        os.makedirs(output_dir, exist_ok=True)

        # --- Detect watermark / logo images (appear on many pages) -----------
        xref_page_counts = {}  # xref -> number of pages it appears on
        for page_num in range(self.doc.page_count):
            page = self.doc.load_page(page_num)
            for img in page.get_images(full=True):
                xref = img[0]
                xref_page_counts[xref] = xref_page_counts.get(xref, 0) + 1

        total_pages = max(self.doc.page_count, 1)
        # Threshold: if an image appears on more than 30% of pages, it's likely
        # a watermark or logo.
        watermark_threshold = max(3, total_pages * 0.3)
        watermark_xrefs = {
            xref for xref, count in xref_page_counts.items()
            if count > watermark_threshold
        }

        # Cache extracted image data to avoid calling doc.extract_image multiple times
        xref_cache = {}  # xref -> {"image": bytes, "ext": str, "width": int, "height": int}

        section_images = {}
        seen_hashes = set()  # deduplicate identical images across sections

        for section in sections:
            start_page = section[2]
            end_page = section[3]
            images = []

            for page_num in range(start_page - 1, end_page):
                page = self.doc.load_page(page_num)
                image_list = page.get_images(full=True)

                for img_info in image_list:
                    xref = img_info[0]

                    # Skip watermarks / logos
                    if xref in watermark_xrefs:
                        continue

                    # Extract image data (cache to avoid repeated calls)
                    if xref not in xref_cache:
                        try:
                            extracted = self.doc.extract_image(xref)
                            xref_cache[xref] = {
                                "image": extracted["image"],
                                "ext": extracted.get("ext", "png"),
                                "width": extracted.get("width", 0),
                                "height": extracted.get("height", 0),
                            }
                        except Exception as e:
                            logger.debug(f"Could not extract image xref={xref}: {e}")
                            continue

                    img_data = xref_cache[xref]
                    img_bytes = img_data["image"]
                    img_ext = img_data["ext"]
                    img_width = img_data["width"]
                    img_height = img_data["height"]

                    # Skip tiny images (icons, bullets, spacers)
                    if img_width < 50 or img_height < 50:
                        continue
                    if img_width <= 1 or img_height <= 1:
                        continue

                    # Deduplicate identical images
                    img_hash = hashlib.md5(img_bytes).hexdigest()
                    if img_hash in seen_hashes:
                        continue
                    seen_hashes.add(img_hash)

                    # Build a descriptive filename from section + page
                    section_slug = re.sub(r'[^a-zA-Z0-9]+', '_', section[1])[:30]
                    img_filename = f"{section_slug}_p{page_num + 1}_{img_hash[:8]}.{img_ext}"
                    img_path = os.path.join(output_dir, img_filename)

                    # Write image file
                    with open(img_path, "wb") as f:
                        f.write(img_bytes)

                    images.append(img_path)

            section_images[section[1]] = images

        total_imgs = sum(len(v) for v in section_images.values())
        logger.info(f"Extracted {total_imgs} images across {len(section_images)} sections")

        return section_images

    # ------------------------------------------------------------------
    # Watermark / footnote / title-page detection
    # ------------------------------------------------------------------

    def _detect_title_pages(self, max_pages=3):
        """Detect title pages — early pages with very little body text.

        Title pages typically have minimal body-font text, often just the
        document title, authors, affiliations, and publication info.

        Returns:
            set of 0-based page numbers that are likely title / front-matter pages.
        """
        if not hasattr(self, '_cached_info'):
            self._cached_info = self.info_extract()
        pheight, pframe, main_size, main_font = self._cached_info

        title_pages = set()

        # Only check the first few pages
        for page_num in range(min(max_pages, self.doc.page_count)):
            page = self.doc.load_page(page_num)
            blocks = page.get_text("dict")["blocks"]

            body_char_count = 0
            total_char_count = 0

            for block in blocks:
                # Skip content outside the text frame (headers/footers)
                if block.get("type", 0) != 0:
                    continue
                if block["bbox"][1] < pframe or block["bbox"][3] > pheight - pframe:
                    continue

                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text:
                            continue
                        total_char_count += len(text)
                        # Count body-font characters
                        if round(span.get("size", 0)) == main_size:
                            body_char_count += len(text)

            # If the page has very little body text relative to total text,
            # it's likely a title page.
            if total_char_count > 0 and total_char_count < 300:
                title_pages.add(page_num)
            elif total_char_count > 0 and body_char_count / max(total_char_count, 1) < 0.3:
                title_pages.add(page_num)

        return title_pages

    @staticmethod
    def _is_footnote_block(block, main_size, page_height, bottom_margin=120):
        """Check if a text block looks like a footnote block.

        Footnotes are typically:
        - In smaller font than the main text
        - Near the bottom of the page
        - Often start with a superscript number or letter
        """
        if block.get("type", 0) != 0:
            return False

        # Is the block near the bottom of the page?
        if block["bbox"][3] < page_height - bottom_margin:
            return False

        # Check if spans are in smaller font
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                # Small font size near bottom of page = likely footnote
                if span.get("size", main_size) < main_size - 1:
                    # Check if it starts with a superscript-like number
                    first_text = text.lstrip()
                    if re.match(r'^[\d\*†‡]+[\.\)]?\s', first_text):
                        return True
                    # Or if the flags indicate superscript
                    if span.get("flags", 0) & (1 << 0):  # superscript bit
                        return True

        return False

    @staticmethod
    def _is_watermark_span(span, main_size, main_font):
        """Check if a text span looks like a watermark.

        Watermarks are typically:
        - Same text repeated on many pages
        - Often in a different, larger font
        - May be a single short word or phrase
        """
        text = span.get("text", "").strip()
        if not text or len(text) < 2:
            return False

        size = span.get("size", main_size)
        font = span.get("font", main_font or "")
        flags = span.get("flags", 0)

        # Watermarks often have very different size (much larger) or font
        # and are short text fragments.
        # We check for common watermark patterns rather than font size alone
        # (since headings also have different sizes).
        # Typical watermark patterns:
        # - "CONFIDENTIAL", "DRAFT", "SAMPLE", etc.
        watermark_keywords = {
            'confidential', 'draft', 'sample', 'review copy', 'not for distribution',
            'watermark', 'do not copy', 'restricted', 'preprint',
        }
        if text.lower() in watermark_keywords:
            return True

        return False

    def _detect_repeated_spans(self, threshold_pct=0.3):
        """Detect text spans that appear identically on many pages.

        A span that appears on more than ``threshold_pct`` of all pages in
        the same position (within a small tolerance) is almost certainly a
        running header, footer, or watermark.

        Returns:
            set of (text, round(bbox_top, 1)) tuples that are repeated.
        """
        from collections import defaultdict

        span_occurrences = defaultdict(set)  # (text, rounded_y) -> set of page_nums
        total_pages = self.doc.page_count

        for page_num in range(min(total_pages, 50)):  # sample first 50 pages
            page = self.doc.load_page(page_num)
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block.get("type", 0) != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text or len(text) < 2:
                            continue
                        # Normalise: lowercase, collapse whitespace
                        normalised = re.sub(r'\s+', ' ', text.lower())
                        y_pos = round(block["bbox"][1], 0)  # vertical position
                        key = (normalised, y_pos)
                        span_occurrences[key].add(page_num)

        # Threshold: appears on more than threshold_pct of sampled pages
        min_pages = max(3, int(total_pages * threshold_pct))
        repeated = {
            key for key, pages in span_occurrences.items()
            if len(pages) >= min_pages
        }
        return repeated

    def extract(self, sections: list, num_block=0) -> dict:
        """
        Extracts the specified sections' dictionary structured text.

        Args:
            sections (list): A list of sections to extract.
            num_block (int): The number of blocks to extract.

        Returns:
            dict: The specified sections' dictionary structured text.
        """
        from .logger import logger
        try:
            return self._extract_internal(sections, num_block)
        except Exception as e:
            logger.error(f"Error during text extraction: {e}", exc_info=True)
            raise

    def _extract_internal(self, sections: list, num_block=0) -> dict:
        # To avoid RecursionError and performance loss, info_extract is called once
        # at the top level or values are passed. Since this is a recursive method,
        # we can cache these values in the instance.
        if not hasattr(self, '_cached_info'):
            self._cached_info = self.info_extract()
        pheight, pframe, main_size, main_font = self._cached_info

        # Detect title / front-matter pages to skip
        title_pages = self._detect_title_pages()

        # Build a set of repeated text spans (potential watermarks) for fast lookup
        # Text that appears verbatim on more than 30% of pages in the same position
        # is treated as a watermark and skipped.
        _watermark_texts = self._detect_repeated_spans()

        main_text = {}

        for section in sections:
            start_page = section[2]
            end_page = section[3]
            parent = self.get_parent(section)

            next_section = self.get_next_section(section)
            subsections = self.get_children(section)

            if (parent in sections) and (parent is not None):
                continue

            key = ""
            value = []

            pblocks = []
            for i in range(start_page, end_page + 1):
                page = self.doc.load_page(i - 1)
                pblocks.append(page.get_text("dict")["blocks"])

            # Track current page index (0-based) within pblocks for image
            # placeholder insertion
            page_image_counts = {}  # page_num (0-based) -> count of images found

            skip = False
            stop = False
            flag = False
            for blocks in pblocks:
                if stop:
                    break
                skip = False
                current_page_idx = pblocks.index(blocks)
                current_page_num = start_page + current_page_idx  # 1-based

                # Skip title / front-matter pages
                if (current_page_num - 1) in title_pages:
                    continue

                if pblocks.index(blocks) > 0:
                    num_block = 0
                for block in blocks[num_block:]:
                    if skip or stop:
                        break
                    # Removing header and footer blocks
                    doc_format = self.doc.metadata.get("format", "").lower()
                    if (
                        "pdf" in doc_format
                        and block["bbox"][1] > pframe
                        and block["bbox"][3] < pheight - pframe
                    ) or "epub" in doc_format:
                        # Skip footnote blocks
                        if self._is_footnote_block(block, main_size, pheight):
                            continue

                        # Handle image blocks - insert placeholder
                        if block.get("type") == 1:
                            if key != "":
                                page_key = current_page_num - 1  # 0-based
                                img_idx = page_image_counts.get(page_key, 0) + 1
                                page_image_counts[page_key] = img_idx
                                value[0] += f"\n[FIGURE: page_{current_page_num}_img_{img_idx}]\n"
                            continue  # Skip further processing of image block

                        for line in block.get("lines", []):
                            inline_title = False
                            spans = self.get_span(line)
                            # Check if line span is empty
                            if len(spans) > 0:
                                # Skip watermark text
                                if self._is_watermark_span(spans[0], main_size, main_font):
                                    continue
                                if any(self._is_watermark_span(s, main_size, main_font) for s in spans):
                                    continue
                                # Skip running headers / footers (repeated text)
                                _is_repeated = False
                                for _s in spans:
                                    _norm = re.sub(r'\s+', ' ', _s.get("text", "").strip().lower())
                                    if any(_norm == wt[0] for wt in _watermark_texts):
                                        _is_repeated = True
                                        break
                                if _is_repeated:
                                    continue

                                # Detect and skip figure/table captions
                                if re.match(r"^(Fig(ure)?|Table)\s*(\d+)?", spans[0]["text"], re.IGNORECASE):
                                    continue
                                # Detect captions based on previous image block and font
                                if blocks[blocks.index(block) - 1]["type"] == 1 and (
                                    spans[0]["font"] != main_font
                                    or spans[0]["size"] < main_size
                                ):
                                    break

                                # Detect titles
                                if len(spans[0]["text"]) > 1 and (
                                    spans[0]["font"] != main_font
                                    or spans[0]["size"] != main_size
                                    and block.get("lines", []).index(line) < 4
                                ):
                                    # Detect current section's title
                                    if re.search(
                                        rf"{re.escape(re.sub(r'[ ,.:?!]', '', spans[0]['text'].lower().strip()))}",
                                        re.sub(r"[ ,.:?!]", "", section[1].lower()),
                                    ) or re.search(
                                        rf"{re.escape(re.sub(r'[ ,.:?!]', '', section[1].lower()))}",
                                        re.sub(
                                            r"[ ,.:?!]",
                                            "",
                                            spans[0]["text"].lower().strip(),
                                        ),
                                    ):
                                        if key == "":
                                            key = section[1]
                                            value = [""]
                                            if len(spans) <= 1:
                                                continue
                                            else:
                                                inline_title = True
                                        else:
                                            if re.sub(
                                                r"[ ,.:?!]",
                                                "",
                                                spans[0]["text"].lower().strip(),
                                            ) == re.sub(
                                                r"[ ,.:?!]", "", section[1].lower()
                                            ):
                                                continue

                                    # Skip subsections' text
                                    elif flag:
                                        if next_section is not None and not (
                                            re.search(
                                                rf"{re.escape(re.sub(r'[ ,.:?!]', '', spans[0]['text'].lower().strip()))}",
                                                re.sub(
                                                    r"[ ,.:?!]",
                                                    "",
                                                    next_section[1].lower(),
                                                ),
                                            )
                                            or re.search(
                                                rf"{re.escape(re.sub(r'[ ,.:?!]', '', next_section[1].lower()))}",
                                                re.sub(
                                                    r"[ ,.:?!]",
                                                    "",
                                                    spans[0]["text"].lower().strip(),
                                                ),
                                            )
                                        ):
                                            skip = True
                                        elif next_section is None:
                                            skip = True
                                        else:
                                            flag = False
                                            stop = True
                                        break

                                    # Detect next section's title
                                    elif (
                                        next_section is not None
                                        and (
                                            re.search(
                                                rf"{re.escape(re.sub(r'[ ,.:?!]', '', spans[0]['text'].lower().strip()))}",
                                                re.sub(
                                                    r"[ ,.:?!]",
                                                    "",
                                                    next_section[1].lower(),
                                                ),
                                            )
                                            or re.search(
                                                rf"{re.escape(re.sub(r'[ ,.:?!]', '', next_section[1].lower()))}",
                                                re.sub(
                                                    r"[ ,.:?!]",
                                                    "",
                                                    spans[0]["text"].lower().strip(),
                                                ),
                                            )
                                        )
                                        and key != ""
                                    ):
                                        stop = True
                                        break

                                    # Detect first subsection
                                    elif (
                                        len(subsections) > 0
                                        and (
                                            re.search(
                                                rf"{re.escape(re.sub(r'[ ,.:?!]', '', spans[0]['text'].lower().strip()))}",
                                                re.sub(
                                                    r"[ ,.:?!]",
                                                    "",
                                                    subsections[0][1].lower(),
                                                ),
                                            )
                                            or re.search(
                                                rf"{re.escape(re.sub(r'[ ,.:?!]', '', subsections[0][1].lower()))}",
                                                re.sub(
                                                    r"[ ,.:?!]",
                                                    "",
                                                    spans[0]["text"].lower().strip(),
                                                ),
                                            )
                                        )
                                        and key != ""
                                    ):
                                        value.append(
                                            self.extract(
                                                subsections, blocks.index(block)
                                            )
                                        )
                                        flag = True
                                        break

                                    # Detect bibliography or references section (in case they are not in toc)
                                    elif spans[0]["text"].lower().strip() in (
                                        "references",
                                        "bibliography",
                                    ):
                                        stop = True
                                        break

                                    # Remove footer blocks from the text
                                    elif re.match(r"\s?\d+\s?$", spans[0]["text"]) and [
                                        span["size"] < main_size for span in spans
                                    ]:
                                        skip = True
                                        break

                                # else:
                                if key != "":
                                    # if not inline_title and spans[0]["text"].lower().strip(',.:?!') in key.lower().strip(',.:?!'):
                                    #    continue
                                    if inline_title:
                                        spans = spans[1:]
                                    for span in spans:
                                        if (
                                            re.match(r"\s?\d+\s?$", span["text"])
                                            and span["size"] < main_size
                                        ):
                                            continue
                                        elif len(value[0]) > 1 and value[0].rstrip().endswith('-'):
                                            # Remove the hyphen and join with next span
                                            value[0] = value[0].rstrip()[:-1] + span["text"]
                                        elif len(value[0]) == 0:
                                            value[0] = span["text"]
                                        else:
                                            value[0] = value[0].rstrip() + " " + span["text"]

                    if key != "":
                        main_text[key] = value
                        value[0] = re.sub(r"[\xad\xa0]\s", "", value[0])
                        value[0] = re.sub(r"\s+([.,:?!]([A-Z]))", r"\1 \2", value[0])
                        if re.match(r"\. ", value[0]):
                            value[0] = value[0][2:]
                        if re.match(r"[a-z]+(\.)?\s?\w+", value[0]):
                            value[0] = re.sub(r"^[a-z]+(\.)?\s?(\w+)", r"\2", value[0])

        return main_text
