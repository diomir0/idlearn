from .utils import *


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


def tocL2tocD(toc_list):
    root = {}
    stack = [(0, root)]  # stack of (level, current_dict)

    for level, title, startpage, endpage in toc_list:
        current_dict = {}
        while stack and level <= stack[-1][0]:
            stack.pop()
        stack[-1][1][(level, title, startpage, endpage))] = {"_page": page, "_sub": current_dict}
        stack.append((level, current_dict))

    def cleanup(d):
        return {
            k: cleanup(v["_sub"]) if v["_sub"] else {"_page": v["_page"]}
            for k, v in d.items()
        }

    return cleanup(root)


def find_parent(section, toc_dict, parent=None):
    for key, value in toc_dict.items():
        if key == section:
            if isinstance(parent, dict):
                return parent, parent.keys
            else: 
                return parent, toc_dict.keys
            
        if isinstance(value, dict):
            child_dict = value
            r1, r2 = find_parent(section, child_dict, key)
            if r1:
                return r1, r2
    return None
    

# Function extracting and structuring the text from PDF
def text_extract(doc, sections):
    from .logger import logger
    logger.info("-- Starting text extraction")
    
    toc, pheight, pframe, main_font = info_extract(doc)
    toc_dict = tocL2tocD(toc)

    main_text = {}

    for section in sections:

        start_page = section[2]
        end_page = section[3]
        level = section[0]
        parent, level_sections = find_parent(section, toc_dict)

        if parent in sections:
            continue

        key = ""
        value = ""
        pblocks = []

        for i in range(start_page, end_page+1):
            page = doc.load_page(i)
            pblocks.append(page.get_text("dict")["blocks"])

        while cflag == False:
            for blocks in pblocks:
                if cflag == True: break
                for block in blocks:
                    if cflag == True : break
                    # Removing header and footer blocks
                    if block["bbox"][1] > pframe and block["bbox"][3] < pheight-pframe:
                        for line in block.get("lines", []):
                            
                            # Excluding figure and table captions
                            if (re.match(r'Fig(ure)?\.(\s)?(\d+)?(\w+)?(\s+)?:', line.get("spans", [])[0]["text"]) or 
                                  re.match(r'Table(\s)?(\d+)?(\w+)?(\s+)?:', line.get("spans", [])[0]["text"])):
                                break
                            
                            # Get section titles as dict keys
                            elif line.get("spans", [])[0]["text"].lower() in [section[1] for section in sections]: 
                                key = line.get("spans", [])[0]["text"].lower()
                                value = ""
                                continue
    
                            elif (line.get("spans", [])[0]["text"].lower() in [section[1] for section in level_section]):
                                cflag = True
                                break
                                     
                            # If the references title is not included in the toc but still exists
                            #elif (any([section[1]].lower() == "references" for section in sections]) == False and
                            #         line.get("spans", [])[0]["text"].lower() == "references"):  
                            #    key = "references"
                            #    value = ""
                            #    continue
                            
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
