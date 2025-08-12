#========================================================================================#
#                                      IDLEARN                                           #
#                                      utils.py                                          #
#========================================================================================#

# Filename: utils.py
# Author: diomir0
# Date of creation: 05 Jul 2025

# This script contains the utility functions for extracting and structuring the text from 
# a PDF file, and writing the output MD file containing the summary, key concepts and
# questions for each section of the text (if any).

import os
import re
from collections import Counter
import json
import pymupdf


def get_toc(doc):
    toc = doc.get_toc()  # format: [level, title, page]
    toc_with_end = []

    for i, (level, title, start_page) in enumerate(toc):
        # Look ahead for the next section at same or higher level
        end_page = doc.page_count  # default: end of document

        for j in range(i + 1, len(toc)):
            next_level, _, next_start = toc[j]
            if next_level <= level:
                end_page = toc[j][2]
                break

        toc_with_end.append([
            level,
            title,
            start_page,
            end_page
        ])

    return toc_with_end
    

# Getting the info from PDF
def info_extract(doc):
    from .logger import logger
    logger.info(f"--- PDF metadata: {doc.metadata}")
    # Get Table of Contents
    toc = get_toc(doc)
    logger.info(f"--- Table of Contents: {toc}")
    sec_names = [toc[i][1].lower() for i in range(len(toc))]
    

    # Defining page height from first page
    pheight = doc[0].rect.height
    logger.info(f"--- Page height: {pheight}")
    # Defining frame height 
    pframe = 50
    
    # Computing dominant text size throughout the document
    main_font = get_main_font(doc)
    logger.info(f"--- Main font size is {main_font}")

    return (toc, pheight, pframe, main_font)


# Function returning the main text's font of a document
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
    if (dominant_fonts[1][0] > dominant_fonts[0][0] and dominant_fonts[1][1] > dominant_fonts[0][0]/2):
        main_font = round(dominant_fonts[1][0]) 
    else:
        main_font = round(dominant_fonts[0][0]) 

    return main_font


def tocL2tocD(toc_list):
    root = {}
    stack = [(0, root)]  # stack of (level, current_dict)

    for level, title, startpage, endpage in toc_list:
        current_dict = {}
        while stack and level <= stack[-1][0]:
            stack.pop()
        stack[-1][1][(level, title, startpage, endpage)] = {"_page": page, "_sub": current_dict}
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
    

# Function extracting and structuring the text from PDF
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
            # Removing header and footer blocks
            if block["bbox"][1] > pframe and block["bbox"][3] < pheight-pframe:
                for line in block.get("lines", []):
                    # Get section titles as dict keys
                    if line.get("spans", [])[0]["text"].lower() in [section[0] for section in sections]: 
                        key = line.get("spans", [])[0]["text"].lower()
                        value = ""
                        continue
                    # If the references title is not included in the toc but still exists
                    elif (any([section[0].lower() == "references" for section in sections]) == False and
                             line.get("spans", [])[0]["text"].lower() == "references"):  
                        key = "references"
                        value = ""
                        continue
                    # Excluding figure and table captions
                    elif (re.match(r'Fig(ure)?\.(\s)?(\d+)?(\w+)?(\s+)?:', line.get("spans", [])[0]["text"]) or 
                          re.match(r'Table(\s)?(\d+)?(\w+)?(\s+)?:', line.get("spans", [])[0]["text"])):
                        break
                    # Get the block's text as dict value based on the font size
                    for span in line.get("spans", []):
                        # Introducing a tolerance of font size of 0.5 for small variations in the text body
                        if ((round(span["size"]) == main_font and key != "materials and methods")  
                            and key != ""):
                            text = span["text"]
                            # Repairing lines
                            if (len(value) > 1 and (value[-1] == "-" or value[-1] == "ﬁ" or value[-1] == 'ﬂ') 
                                or (text == 'ﬁ' or text == 'ﬂ')):
                                value = value + text   
                            else: 
                                value = value + ' ' + text 
                        # Text in an article "Materials and Methods" section can have a smaller font size
                        if (round(span["size"]) >= main_font-1 and round(span["size"]) <= main_font 
                             and key == "materials and methods"):
                            text = span["text"]
                            # Repairing lines
                            if (len(value) > 1 and (value[-1] == "-" or value[-1] == "ﬁ" or value[-1] == 'ﬂ') 
                                or (text == 'ﬁ' or text == 'ﬂ')):
                                value = value + text   
                            else: 
                                value = value + ' ' + text 
                            
            if (key != "" and value != ""):
                # Removing references
                value = re.sub(r'(;\s)?\[\s(\d(\s,\s+)?)+\s\]', '', value.strip())
                value = re.sub(r'(;\s)?\[\s\d+\s–\s\d+\s\]', '', value.strip())
                # Formatting spaces surrounding commas, dots, and parentheses
                value = re.sub(r'\s,\s', ', ', value.strip())
                value = re.sub(r'\s\.\s', '. ', value.strip())
                value = re.sub(r'\(\s', '(', value.strip())
                value = re.sub(r'\s\)', ')', value.strip())
                # Removing multiple spaces (strip method fails)
                value = re.sub(r'\s+', ' ', value.strip())
                # Replacing the 'ﬁ' and 'ﬂ' characters with correct "fi" string
                value = re.sub(r'ﬁ', 'fi', value.strip())
                value = re.sub(r'ﬂ', 'fl', value.strip())
                
                main_text[key] = value
    
    logger.info("-- Text extracted and structured")
    
    return main_text


# Check whether the question is quantitative
def is_quantitative_question(q):
    quant_keywords = ['how many', 'how much', 'what is the value', 'compute', 'calculate', 'determine', 'estimate', 'give the value', 'at what time', 'what is the result']
    q = q.lower()
    return any(kw in q for kw in quant_keywords)


# Check whether the answer contains numbers
def answer_contains_number(a):
    return bool(re.search(r"\d", a))


# Fcuntion writing a MarkDown file containing summaries, key concepts and questions organized by section
def write_markdown(title, sum_dict, q_dict, output_folder):
    from .logger import logger
    logger.info("-- Generating MD file")
    output_path = output_folder + f"/{title.replace(' ', '_')}.md"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"# {title}\n\n\n")
        numbered_answers = []
        for i, key in enumerate(sum_dict.keys(), start=1):
            f.write(f"## {i}. {key.capitalize()}\n")
            summary = re.sub(r'(1\.[\s])?Summary:', '', sum_dict[key])
            summary = re.sub(r'(2\.[\s])?Key Concepts(/Facts)?(\:)?\n(\n)?', '### Key concepts\n', summary)
            summary = re.sub(r'\d+\.\s', '- ', summary)
            f.write(summary.strip() + "\n\n")
            
            # Writing questions
            f.write("### Questions\n") 
            # Extract questions and answers using regex
            questions = re.findall(r"Q:\s.*?(?=\nA:|\Z)", q_dict[key], re.DOTALL)
            answers = re.findall(r"A:\s.*?(?=\n+Q:|\Z)", q_dict[key], re.DOTALL)
            # Reformat with Q1:/A1:
            numbered_questions = [f"- **Q{i}:** {q.strip()[2:].strip()}" for i, q in enumerate(questions, start=1)]
            numbered_answers.append([f"- **A{i}:** {a.strip()[2:].strip()}" for i, a in enumerate(answers, start=1)])
            f.write("\n".join(numbered_questions))
            f.write("\n\n\n")

        # Writing answers
        f.write("## Answers\n")
        for i, key in enumerate(sum_dict.keys(), start=1):
            f.write(f"{i}. {key.capitalize()}\n")
            f.write("\n".join(numbered_answers[i-1]))
            f.write("\n\n")
    logger.info("-- MD file generated")


class IdlearnCache:

    from .logger import logger
    
    def __init__(self):
        # Create cache directory if it doesn't exist
        os.makedirs(".cache/", exist_ok=True)
        
        self.path = ".cache/cache.json"
        self.data = {'summaries': {}, "qa": {}}
        self.load()
    
    def save(self):
        with open(self.path, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def load(self):
        try:
            with open(self.path, 'r') as f:
                self.data = json.load(f)
                self.logger.info("-- Found cache file") 
        except FileNotFoundError:
            self.logger.info("-- Creating cache file") 
            
            pass
    
    def get_summary(self, section):
        return self.data['summaries'].get(section)

    def get_qa(self, section):
        return self.data['qa'].get(section)

    def update_summary(self, section, summary):
        self.data['summaries'][section] = summary
        self.save()

    def update_qa(self, section, qa):
        self.data['qa'][section] = qa
        self.save()

    def delete(self):
        try:
            os.remove(self.path)
            self.logger.warning("Cache file deleted")
        except FileNotFoundError:
            self.logger.warning("Cache file not found")