import os
import re
from collections import Counter
import json
import pymupdf

class TextExtractor:
    
    def __init__(self, doc):
        self.doc = doc
        self.toc = self.get_toc()


    # Returns the formatted ToC (comprising the end page of each section) 
    def get_toc(self):
        toc = self.doc.get_toc()  # format: [level, title, page]
        toc_with_end = []
    
        for i, (level, title, start_page) in enumerate(toc):
            # Look ahead for the next section at same or higher level
            end_page = self.doc.page_count  # default: end of document
    
            for j in range(i + 1, len(toc)):
                next_level, _, next_start = toc[j]
                if next_level <= level:
                    end_page = toc[j][2]
                    break
            title = re.sub(r'(\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a)+', ' ', 
                           re.sub(r'(\xad\xa0])+', '',re.sub(r'\r', '', title)))
            toc_with_end.append(
                (level,
                title,
                start_page,
                end_page)
            )
    
        return toc_with_end
        

    # Getting the info from PDF
    def info_extract(self):
        
        # Defining page height from first page
        pheight = doc[0].rect.height
        
        # Defining frame height 
        PFRAME = 50
        
        # Computing dominant text size throughout the document
        main_size = self.get_main_size()
        main_font = self.get_main_font()
    
        return (pheight, PFRAME, main_size, main_font)

    
    # Returns the main text's size of a document
    def get_main_size(self):
        font_sizes = []
        for page in self.doc:
            text_dict = page.get_text("dict")
            blocks = text_dict["blocks"]
            for block in blocks:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if not re.match(r'[\s\t]+', span["text"]): font_sizes.append(round(span["size"]))
        size_count = Counter(font_sizes)
        dominant_size = size_count.most_common(2)
        if (dominant_size[1][0] > dominant_size[0][0] and dominant_size[1][1] > dominant_size[0][0]/2):
            main_size = round(dominant_size[1][0]) 
        else:
            main_size = round(dominant_size[0][0]) 
    
        return main_size
    

    # Returns the main text's font of a document
    def get_main_font(self):
        fonts = []
        for page in self.doc:
            text_dict = page.get_text("dict")
            blocks = text_dict["blocks"]
            for block in blocks:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if not re.match(r'[\s\t]+', span["text"]): fonts.append(span["font"])
        font_count = Counter(fonts)
        dominant_font = font_count.most_common(1)[0]
        if type(dominant_font) == tuple:
            dominant_font = dominant_font[0]
        
        return dominant_font


    # Returns the dictionary version of ToC
    def toc2dtoc(self):
        root = {}
        stack = [(0, root)]  # stack of (level, current_dict)
    
        for level, title, startpage, endpage in self.toc:
            current_dict = {}
            while stack and level <= stack[-1][0]:
                stack.pop()
            stack[-1][1][(level, title, startpage, endpage)] = {"_page": (startpage, endpage), "_sub": current_dict}
            stack.append((level, current_dict))
    
        def cleanup(d):
            return {
                k: cleanup(v["_sub"]) if v["_sub"] else {"_page": v["_page"]}
                for k, v in d.items()
            }
    
        return cleanup(root)


    # Returns the first parent section of secname
    def get_parent(self, section, parent=None):
        dtoc = self.toc2dtoc()
        for key, value in dtoc.items():
            if key == section:
                return parent
                
            if isinstance(value, dict):
                dchild = value
                result = get_parent(section, dchild, key)
                if result:
                    return result
        return None
    

    # Returns the list of all the descendance of a section
    def get_children(self, section):
        subsections=[]
        level = section[0]
        for sec in self.toc[self.toc.index(section)+1:]:
            if sec[0]>level:
                subsections.append(sec)
            elif sec[0]==level:
                break
        return subsections
    

    # Returns the section following the given section
    def get_next_section(self, section):
        level = section[0]
        for sec in self.toc[self.toc.index(section)+1:]:
            if sec[0]<=level:
                return sec
        return None


    # Returns the different spans composing a line. Each span will have a different font, size, or both than the other spans of the line
    def get_span(self, line):
        spans = []
        span = {}
        for s in line.get("spans", []):
            s["font"] = re.sub(r'\+.*', '', s["font"])
            if not re.match(r'[\s\t]+$', s["text"]):
                s["text"] = re.sub(r'.*(\\u200[0-9a])+.*', ' ', re.sub(r'.*(\\xa[d0])+.*', '',s["text"]))
                if span == {}: 
                    span = {'text': s["text"], 
                            'font': s["font"], 
                            'size': s["size"]}
                else: 
                    if re.match(r"(([A-Z]+\s)+)?[A-Z]$", span["text"].strip(' ,.:?!')): 
                        span["text"] = span["text"] + s["text"] 
                        span["size"] = s["size"]  
                        span["font"] = s["font"]
                        
                    elif span["font"] != s["font"] or span["size"] != s["size"]: 
                        if re.match(r"[A-Z]+$", s["text"]):
                            span["text"] = span["text"] + ' ' + s["text"]
                        else:
                            spans.append(span.copy())
                            span = {'text': s["text"], 
                                    'font': s["font"], 
                                    'size': s["size"]}
    
                    elif (re.match(r"(\s)?[ﬁﬂ—](\s)?$", s["text"]) 
                          or re.match(r"[ﬁﬂ—]$", span["text"][-1])
                         ):
                        span["text"] = span["text"] + s["text"]
                        
                    elif (span["font"] == s["font"] and
                          span["size"] == s["size"]
                         ):
                        if (' ' in (s["text"][0], span["text"][-1]) 
                            or (len(span["text"]) > 1 and re.match(r"^\s[A-Z]$", span["text"][-2:]))
                           ):
                            span["text"] = span["text"] + s["text"] 
                        else:
                            span["text"] = span["text"] + ' ' + s["text"] 
                    else:
                        continue
        if span != {}: spans.append(span)
        for span in spans: 
            span["text"] = span["text"].strip()
            span["text"] = re.sub(r'(\\u200[0-9a])+', ' ', span["text"])
            # Removing references
            span["text"] = re.sub(r'(;\s)?\[\s(\d(\s,\s+)?)+\s\]', '', span["text"])
            span["text"] = re.sub(r'(;\s)?\[\s\d+\s–\s\d+\s\]', '', span["text"])
            # Formatting spaces surrounding commas, dots, and parentheses
            span["text"] = re.sub(r'\(\s', '(', span["text"])
            span["text"] = re.sub(r'\s\)', ')', span["text"])
            # Removing multiple spaces (strip method fails)
            span["text"] = re.sub(r'\s+', ' ', span["text"])
            # Replacing the 'ﬁ' and 'ﬂ' characters with correct "fi" string
            span["text"] = re.sub(r'ﬁ', 'fi', span["text"])
            span["text"] = re.sub(r'ﬂ', 'fl', span["text"])
        return spans


        # Returns the specified sections'dictionary structured text 
        def text_extract(self, sections, num_block=0):
    
            pheight, pframe, main_size, main_font = self.info_extract(self.doc)
            dtoc = self.toc2dtoc(self.toc)
        
            main_text = {}
        
            for section in sections:
                start_page = section[2]
                end_page = section[3]
                level = section[0]
                parent = self.get_parent(section, dtoc)
        
                next_section = self.get_next_section(section)
                subsections = self.get_children(section)
        
                if (parent in sections) and (parent is not None):
                    continue
        
                key = ""
                value = []
                
                pblocks = []
                for i in range(start_page, end_page+1):
                    page = self.doc.load_page(i-1)
                    pblocks.append(page.get_text("dict")["blocks"])
        
                skip = False
                stop = False
                flag = False
                for blocks in pblocks:
                    if stop: break
                    skip = False
                    if pblocks.index(blocks) > 0:
                        num_block = 0
                    for block in blocks[num_block:]:
                        if skip or stop: break  
                        # Removing header and footer blocks
                        if (("pdf" in self.doc.metadata["format"].lower() and block["bbox"][1] > pframe and block["bbox"][3] < pheight-pframe) or
                            "epub" in self.doc.metadata["format"].lower()):
                            for line in block.get("lines", []):
                                inline_title = False
                                spans = self.get_span(line)
                                # Check if line span is empty
                                if len(spans) > 0: 
                                                                                            
                                    # Detect captions
                                    if (blocks[blocks.index(block)-1]['type'] == 1
                                        and (spans[0]["font"] != main_font or spans[0]["size"] < main_size)
                                       ): 
                                        break
                                    
                                    # Detect titles
                                    if (spans[0]["font"] != main_font or spans[0]["size"] != main_size
                                        and block.get("lines", []).index(line) < 4
                                       ):
                                        
                                        # Detect current section's title
                                        if (re.search(rf"{re.escape(re.sub(r'[ ,.:?!]', '', spans[0]['text'].lower().strip()))}", 
                                                      re.sub(r'[ ,.:?!]', '', section[1].lower())) 
                                            or re.search(rf"{re.escape(re.sub(r'[ ,.:?!]', '', section[1].lower()))}", 
                                                         re.sub(r'[ ,.:?!]', '', spans[0]['text'].lower().strip()))
                                           ):
                                            if key == '':
                                                key = section[1]
                                                value = ['']
                                                if len(spans) <= 1: continue
                                                else: inline_title = True
                                            else:
                                                if re.sub(r'[ ,.:?!]', '', spans[0]['text'].lower().strip()) == re.sub(r'[ ,.:?!]', '', section[1].lower()): 
                                                    continue
        
                                        # Skip subsections' text 
                                        elif flag:
                                            if not (re.search(rf"{re.escape(re.sub(r'[ ,.:?!]', '', spans[0]['text'].lower().strip()))}", 
                                                              re.sub(r'[ ,.:?!]', '', next_section[1].lower())) 
                                                    or re.search(rf"{re.escape(re.sub(r'[ ,.:?!]', '', next_section[1].lower()))}", 
                                                                 re.sub(r'[ ,.:?!]', '', spans[0]['text'].lower().strip()))
                                                   ):
                                                skip = True
                                            else:
                                                flag = False
                                                stop = True
                                            break
                                                
                                        # Detect next section's title
                                        elif (next_section is not None
                                              and (re.search(rf"{re.escape(re.sub(r'[ ,.:?!]', '', spans[0]['text'].lower().strip()))}", 
                                                             re.sub(r'[ ,.:?!]', '', next_section[1].lower())) 
                                                   or re.search(rf"{re.escape(re.sub(r'[ ,.:?!]', '', next_section[1].lower()))}", 
                                                                re.sub(r'[ ,.:?!]', '', spans[0]['text'].lower().strip())))
                                              and key != ''
                                             ):
                                            stop = True
                                            break
        
                                        # Detect first subsection 
                                        elif (len(subsections)>0
                                              and (re.search(rf"{re.escape(re.sub(r'[ ,.:?!]', '', spans[0]['text'].lower().strip()))}", 
                                                             re.sub(r'[ ,.:?!]', '', subsections[0][1].lower())) 
                                                   or re.search(rf"{re.escape(re.sub(r'[ ,.:?!]', '', subsections[0][1].lower()))}", 
                                                                re.sub(r'[ ,.:?!]', '', spans[0]['text'].lower().strip())))
                                              and key != ''
                                             ): 
                                            value.append(self.text_extract(subsections, blocks.index(block))) 
                                            flag = True
                                            break
                                            
                                        # Detect bibliography or references section (in case they are not in toc)
                                        elif spans[0]["text"].lower().strip() in ("references", "bibliography"):
                                            stop = True
                                            break
                                        
                                        # Remove footer blocks from the text
                                        elif (re.match(r'\s?\d+\s?$', spans[0]["text"]) 
                                              and [span["size"] < main_size for span in spans]):
                                            skip = True
                                            break
                                        
                                    #else:
                                    if key != '': 
                                        #if not inline_title and spans[0]["text"].lower().strip(',.:?!') in key.lower().strip(',.:?!'):
                                        #    continue
                                        if inline_title: spans = spans[1:]
                                        for span in spans: 
                                            if re.match(r'\s?\d+\s?$', span["text"]) and span["size"] < main_size:
                                                continue
                                            elif (len(value[0]) > 1 and re.match(r'-', value[0][-1])
                                                 or len(value[0])==0): 
                                                value[0] = value[0].strip() + span["text"]
                                            else: 
                                                value[0] = value[0].strip() + ' ' + span["text"] 
                                        
                        if key != "":
                            main_text[key] = value
                            value[0] = re.sub(r'[\xad\xa0]\s', '', value[0])
                            value[0] = re.sub(r'\s+([.,:?!]([A-Z]))', r'\1 \2', value[0])
                            if re.match(r'\. ', value[0]): 
                                value[0] = value[0][2:] 
                            if re.match(r'[a-z]+(\.)?\s?\w+', value[0]):
                                value[0] = re.sub(r'^[a-z]+(\.)?\s?(\w+)', r'\2', value[0])
                            
                                
                
            return main_text