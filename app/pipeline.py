#========================================================================================#
#                                       IDLEARN                                          #
#                                     pipeline.py                                        #
#========================================================================================#

# Filename: pipeline.py
# Author: diomir0
# Date of creation: 05 Jul 2025

# This script contains the pipeline for extracting the text from an input PDF, running the 
# summarization, the generation of question-answer pairs, and the generation of Anki cards
# from these pairs. 

import os
import re
import json
import random
import pymupdf
from app import config
from .config import deck_id
from .utils import IdlearnCache, text_extract, write_markdown
from .llmmodel import LLMModel
from .cg import CG

class Pipeline:
    
    def __init__(self, input_file, output_folder, cards=True):
        self.deck_id = random.randint(0, 9999999999) 
        config.deck_id = self.deck_id
        self.cache = IdlearnCache()
        self.model = LLMModel()
        self.output_folder = output_folder
        self.doc = pymupdf.open(input_file)
        self.cards = cards
        
        
    def run(self, sections):
        from .logger import logger
        
        # Create the structure containing all texts from all subsections from PDF file
        text_dict = text_extract(self.doc, sections)
        
        # Initialize dictionaries used for storing summaries and question sets
        sum_dict = self.cache.data["summaries"]
        qa_dict = self.cache.data["qa"]
    
        # Iterate through all sections to generate their summary and question set
        logger.info("-- Starting summary and Q&A generation")
        
        # Starting the LLM model by launching Ollama in a subprocess
        self.model.call()

        # Start of LLM prompt asking for a complete, precise summary yet as concise as possible 
        summary_instruct = "You are an expert science and humanities educator. Given the following text, do two things: 1. Summarize it clearly, precisely and as concisely as precision allows. 2. Then, extract the key concepts or facts as 3–8 concise bullet points. Output them in the form: 'Summary: ... Key Concepts: ...'Text: {text}"
    
        # Start of LLM prompt asking for a set of 5 questions about a previously fed text
        questions_instruct = "You are an expert science and humanities educator. Given the following text, generate a set of five relevant questions and their answers, making sure to only output the questions and their answers in the form of 'Q: ... A:...'. Text: {text}"
        
        for key in text_dict.keys():
            # Create summary and bullet points of each main_text entry and store it in sum_dict
            if not key in sum_dict.keys():
                logger.info("--- Generating summary of section '{}'".format(key))
                sum_dict[key] = self.model.generate(summary_instruct.format(text=text_dict[key]))
                self.cache.update_summary(key, sum_dict[key])
            else:
                logger.warning("--- Summary of section '{}' already exists, skipping")
            # Generate questions based on the text
            if not key in qa_dict.keys():
                logger.info("--- Generating Q&A of section '{}'".format(key))
                qa_dict[key] = self.model.generate(questions_instruct.format(text=text_dict[key]))
                self.cache.update_qa(key, qa_dict[key])
            else:
                logger.warning("--- Q&A of section '{}' already exists, skipping")

        logger.info("-- Finished summary and Q&A generation")
        
        # Generate MarkDown file structuring the summaries, key concepts and questions by section
        write_markdown(self.doc.metadata["title"], sum_dict, qa_dict, self.output_folder) 
    
        # Generate Anki cards using both Basic and Cloze models from qa_dict
        if self.cards:
            deck = CG(self.doc.metadata["title"], self.deck_id)
            deck.generate(qa_dict, self.output_folder)
    
        # Indicate the pipeline has finished running
        logger.warning("==== DONE ====")

