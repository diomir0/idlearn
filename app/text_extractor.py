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

import re
from collections import Counter

from .logger import logger
from .toc_extractor import TOCExtractor


class TextExtractor:
    def __init__(self, doc):
        self.doc = doc
        self.toc = self.get_toc()

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

    def extract(self, sections: list, num_block=0) -> dict:
        """
        Extracts the specified sections'dictionary structured text.

        Args:
            sections (list): A list of sections to extract.
            num_block (int): The number of blocks to extract.

        Returns:
            dict: The specified sections'dictionary structured text.
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

            skip = False
            stop = False
            flag = False
            for blocks in pblocks:
                if stop:
                    break
                skip = False
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
                        for line in block.get("lines", []):
                            inline_title = False
                            spans = self.get_span(line)
                            # Check if line span is empty
                            if len(spans) > 0:
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
