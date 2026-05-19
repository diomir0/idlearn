# ========================================================================================#
#                                      IDLEARN                                           #
#                                      utils.py                                          #
# ========================================================================================#

# Filename: utils.py
# Author: diomir0
# Date of creation: 05 Jul 2025

# This script contains the utility functions for extracting and structuring the text from
# a PDF file, and writing the output MD file containing the summary, key concepts and
# questions for each section of the text (if any).

import json
import os
import re
from collections import Counter


def get_toc(doc):
    """
    Extracts and cleans the Table of Contents from a document.
    If the built-in ToC is missing, it uses TOCExtractor as a fallback.
    Returns a list of tuples: (level, title, start_page, end_page)
    """
    from .toc_extractor import TOCExtractor

    try:
        raw_toc = doc.get_toc()  # format: [level, title, page]
    except Exception:
        raw_toc = None

    # Fallback to TOCExtractor if built-in TOC is missing or empty
    if raw_toc is None or all([len(s) < 2 or s[1] == "" for s in raw_toc]):
        toc_extractor = TOCExtractor()
        # Use metadata location or filename as path
        location = doc.metadata.get("location", "") or doc.name

        # Ensure location is a valid, non-empty string before calling extractor
        if not location or not isinstance(location, str):
            raw_toc = []
        else:
            try:
                extracted = toc_extractor.extract_toc(location)
                # Convert TOCEntry objects to [level, title, page] format
                raw_toc = [[e.level, e.title, e.page or 1] for e in extracted]

                # Normalize levels to be consecutive (1, 2, 3...) and start at 1
                # PyMuPDF requires strict hierarchy with no gaps
                if raw_toc:
                    unique_levels = sorted(list(set(item[0] for item in raw_toc)))
                    level_map = {old_level: new_level for new_level, old_level in enumerate(unique_levels, start=1)}
                    for item in raw_toc:
                        item[0] = level_map[item[0]]

                doc.set_toc(raw_toc)
                doc.save()
            except Exception as e:
                from .logger import logger
                logger.error(f"Failed to extract or save inferred TOC: {e}", exc_info=True)
                # Fallback to an empty list if extraction fails
                raw_toc = []

    toc_with_end = []
    for i, item in enumerate(raw_toc):
        if len(item) < 3:
            continue

        level, title, start_page = item[0], item[1], item[2]

        # Look ahead for the next section at same or higher level to find end_page
        end_page = doc.page_count
        for j in range(i + 1, len(raw_toc)):
            next_item = raw_toc[j]
            if len(next_item) >= 1 and next_item[0] <= level:
                end_page = next_item[2]
                break

        # Clean title to ensure consistency (remove non-breaking spaces, etc.)
        cleaned_title = re.sub(
            r"(\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a)+",
            " ",
            re.sub(r"(\xad\xa0])+", "", re.sub(r"\r", "", title)),
        )
        toc_with_end.append((level, cleaned_title, start_page, end_page))

    return toc_with_end


def flatten_text(data, level=2):
    """Recursively flattens the extracted text structure into a single string with proper Markdown headers."""
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        return "\n".join([flatten_text(item, level) for item in data if item])
    if isinstance(data, dict):
        parts = []
        prefix = "#" * level
        for key, value in data.items():
            parts.append(f"{prefix} {key}\n{flatten_text(value, level + 1)}")
        return "\n\n".join(parts)
    return str(data)


def info_extract(doc):
    from .logger import logger

    logger.info(f"--- PDF metadata: {doc.metadata}")
    toc = get_toc(doc)
    logger.info(f"--- Table of Contents: {toc}")

    pheight = doc[0].rect.height
    logger.info(f"--- Page height: {pheight}")
    pframe = 50

    main_font = get_main_font(doc)
    logger.info(f"--- Main font size is {main_font}")

    return (toc, pheight, pframe, main_font)


def get_main_font(doc):
    font_sizes = []
    for page in doc:
        text_dict = page.get_text("dict")
        blocks = text_dict["blocks"]
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    font_sizes.append(span["size"])
    font_count = Counter(font_sizes)
    dominant_fonts = font_count.most_common(2)
    if (
        len(dominant_fonts) > 1
        and dominant_fonts[1][0] > dominant_fonts[0][0]
        and dominant_fonts[1][1] > dominant_fonts[0][0] / 2
    ):
        main_font = round(dominant_fonts[1][0])
    elif dominant_fonts:
        main_font = round(dominant_fonts[0][0])
    else:
        main_font = 12

    return main_font


def tocL2tocD(toc_list):
    root = {}
    stack = [(0, root)]

    for level, title, startpage, endpage in toc_list:
        current_dict = {}
        while stack and level <= stack[-1][0]:
            stack.pop()
        stack[-1][1][(level, title, startpage, endpage)] = {
            "_page": startpage,
            "_sub": current_dict,
        }
        stack.append((level, current_dict))

    def cleanup(d):
        return {
            k: cleanup(v["_sub"]) if v["_sub"] else {"_page": v["_page"]}
            for k, v in d.items()
        }

    return cleanup(root)


def find_parent(secname, toc_dict, parent=None):
    for key, value in toc_dict.items():
        if key == secname:
            if isinstance(parent, dict):
                return parent, parent.keys
            else:
                return parent, toc_dict.keys

        if isinstance(value, dict):
            child_dict = value
            r1, r2 = find_parent(secname, child_dict, key)
            if r1:
                return r1, r2
    return None


def text_extract(doc, sections):
    from .logger import logger

    logger.info("-- Starting text extraction")
    _, pheight, pframe, main_font = info_extract(doc)
    pblocks = [page.get_text("dict")["blocks"] for page in doc]

    main_text = {}
    key = ""
    value = ""

    for blocks in pblocks:
        for block in blocks:
            if block["bbox"][1] > pframe and block["bbox"][3] < pheight - pframe:
                for line in block.get("lines", []):
                    if line.get("spans", [])[0]["text"].lower() in [
                        section[0] for section in sections
                    ]:
                        key = line.get("spans", [])[0]["text"].lower()
                        value = ""
                        continue
                    elif not (
                        any(
                            [section[0].lower() == "references" for section in sections]
                        )
                        and line.get("spans", [])[0]["text"].lower() == "references"
                    ):
                        key = "references"
                        value = ""
                        continue
                    elif re.match(
                        r"Fig(ure)?\.(\s)?(\d+)?(\w+)?(\s+)?:",
                        line.get("spans", [])[0]["text"],
                    ) or re.match(
                        r"Table(\s)?(\d+)?(\w+)?(\s+)?:",
                        line.get("spans", [])[0]["text"],
                    ):
                        break
                    for span in line.get("spans", []):
                        if (
                            round(span["size"]) == main_font
                            and key != "materials and methods"
                        ) and key != "":
                            text = span["text"]
                            if (
                                len(value) > 1
                                and (
                                    value[-1] == "-"
                                    or value[-1] == "ﬁ"
                                    or value[-1] == "ﬂ"
                                )
                                or (text == "ﬁ" or text == "ﬂ")
                            ):
                                value = value + text
                            else:
                                value = value + " " + text
                        if (
                            round(span["size"]) >= main_font - 1
                            and round(span["size"]) <= main_font
                            and key == "materials and methods"
                        ):
                            text = span["text"]
                            if (
                                len(value) > 1
                                and (
                                    value[-1] == "-"
                                    or value[-1] == "ﬁ"
                                    or value[-1] == "ﬂ"
                                )
                                or (text == "ﬁ" or text == "ﬂ")
                            ):
                                value = value + text
                            else:
                                value = value + " " + text

            if key != "" and value != "":
                value = re.sub(r"(;\s)?\[\s(\d(\s,\s+)?)+\s\]", "", value.strip())
                value = re.sub(r"(;\s)?\[\s\d+\s–\s\d+\s\]", "", value.strip())
                value = re.sub(r"\s,\s", ", ", value.strip())
                value = re.sub(r"\s\.\s", ". ", value.strip())
                value = re.sub(r"\(\s", "(", value.strip())
                value = re.sub(r"\s\)", ")", value.strip())
                value = re.sub(r"\s+", " ", value.strip())
                value = re.sub(r"ﬁ", "fi", value.strip())
                value = re.sub(r"ﬂ", "fl", value.strip())
                main_text[key] = value

    logger.info("-- Text extracted and structured")
    return main_text


def is_quantitative_question(q):
    quant_keywords = [
        "how many", "how much", "what is the value", "compute",
        "calculate", "determine", "estimate", "give the value",
        "at what time", "what is the result",
    ]
    q = q.lower()
    return any(kw in q for kw in quant_keywords)


def answer_contains_number(a):
    return bool(re.search(r"\d", a))


def write_full_text_markdown(title, full_text_dict, output_folder):
    from .logger import logger

    logger.info("-- Generating full text MD file")
    output_path = output_folder + f"/{title.replace(' ', '_')}_full_text.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n\n")
        for i, (key, value) in enumerate(full_text_dict.items(), start=1):
            f.write(f"## {i}. {key}\n\n")
            f.write(flatten_text(value, level=3) + "\n\n")
    logger.info("-- Full text MD file generated")


def write_markdown(title, sum_dict, q_dict, output_folder):
    from .logger import logger

    logger.info("-- Generating MD file")
    output_path = output_folder + f"/{title.replace(' ', '_')}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n\n")
        numbered_answers = []
        for i, key in enumerate(sum_dict.keys(), start=1):
            f.write(f"## {i}. {key.capitalize()}\n")
            summary = re.sub(r"(1\.[\s])?Summary:", "", sum_dict[key])
            summary = re.sub(
                r"(2\.[\s])?Key Concepts(/Facts)?(\:)?\n(\n)?",
                "### Key concepts\n",
                summary,
            )
            summary = re.sub(r"\d+\.\s", "- ", summary)
            f.write(summary.strip() + "\n\n")

            f.write("### Questions\n")
            questions = re.findall(r"Q:\s.*?(?=\nA:|\Z)", q_dict[key], re.DOTALL)
            answers = re.findall(r"A:\s.*?(?=\n+Q:|\Z)", q_dict[key], re.DOTALL)
            numbered_questions = [
                f"- **Q{i}:** {q.strip()[2:].strip()}"
                for i, q in enumerate(questions, start=1)
            ]
            numbered_answers.append(
                [
                    f"- **A{i}:** {a.strip()[2:].strip()}"
                    for i, a in enumerate(answers, start=1)
                ]
            )
            f.write("\n".join(numbered_questions))
            f.write("\n\n\n")

        f.write("## Answers\n")
        for i, key in enumerate(sum_dict.keys(), start=1):
            f.write(f"{i}. {key.capitalize()}\n")
            f.write("\n".join(numbered_answers[i - 1]))
            f.write("\n\n")
    logger.info("-- MD file generated")


class IdlearnCache:
    from .logger import logger

    def __init__(self):
        os.makedirs(".cache/", exist_ok=True)
        self.path = ".cache/cache.json"
        self.data = {"summaries": {}, "qa": {}}
        self.load()

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2)

    def load(self):
        try:
            with open(self.path, "r") as f:
                self.data = json.load(f)
                self.logger.info("-- Found cache file")
        except FileNotFoundError:
            self.logger.info("-- Creating cache file")

    def get_summary(self, section):
        return self.data["summaries"].get(section)

    def get_qa(self, section):
        return self.data["qa"].get(section)

    def update_summary(self, section, summary):
        self.data["summaries"][section] = summary
        self.save()

    def update_qa(self, section, qa):
        self.data["qa"][section] = qa
        self.save()

    def delete(self):
        try:
            os.remove(self.path)
            self.logger.warning("Cache file deleted")
        except FileNotFoundError:
            pass
