# ========================================================================================#
#                                       IDLEARN                                          #
#                                     pipeline.py                                        #
# ========================================================================================#
"""
Filename: pipeline.py
Author: diomir0
Date of creation: 05 Jul 2025

This script contains the pipeline for extracting the text from an input PDF, running the
summarization, the generation of question-answer pairs, and the generation of Anki cards
from these pairs.
"""

import random

import pymupdf

from app import config

from .cg import CG
from .llmmodel import LLMModel
from .text_extractor import TextExtractor

# from .config import deck_id
from .utils import IdlearnCache, write_markdown, write_full_text_markdown, get_toc
from .tokenizer import SmartTokenizer


class Pipeline:
    def __init__(self, input_file, output_folder, cards=True,
                 api_type="ollama", model=None, base_url=None, api_key=None):
        self.deck_id = random.randint(0, 9999999999)
        config.deck_id = self.deck_id
        self.cache = IdlearnCache()

        # Configure LLM Model (supports Ollama and OpenAI-compatible APIs)
        model_name = model or ("mistral:7B-instruct" if api_type == "ollama" else "gpt-3.5-turbo")
        self.model = LLMModel(model=model_name, api_type=api_type,
                              base_url=base_url, api_key=api_key)
        self.output_folder = output_folder
        self.doc = pymupdf.open(input_file)
        self.cards = cards
        self.text_extractor = TextExtractor(self.doc)
        self.tokenizer = SmartTokenizer(max_tokens=3000)



    def recursive_summarize(self, text, instruct, is_final=False):
        """Summarizes text using a nested approach for long segments."""
        if not is_final:
            # Intermediate prompt for nested summarization
            prompt = "Summarize the following text concisely while preserving all key information: {text}"
        else:
            prompt = instruct

        segments = self.tokenizer.tokenize(text)

        if len(segments) == 1:
            return self.model.generate(prompt.format(text=text))

        summaries = []
        for seg in segments:
            content = seg['content']
            summaries.append(self.recursive_summarize(content, instruct, is_final=False))

        combined_summaries = "\n\n".join(summaries)
        return self.recursive_summarize(combined_summaries, instruct, is_final=is_final)

    def run(self, sections, summarize=True):
        from .logger import logger

        dsum = {}
        dqa = {}
        dtext = {}

        # 1. Extract and export the selected sections as a markdown file
        logger.info("-- Generating markdown export for selected sections")
        try:
            # If no specific sections are selected, default to all sections
            all_sections_toc = get_toc(self.doc)
            if not sections:
                sections = all_sections_toc

            dtext_selected = self.text_extractor.extract(sections)
            if self.doc.metadata:
                write_full_text_markdown(self.doc.metadata["title"], dtext_selected, self.output_folder)
        except Exception as e:
            logger.error(f"Error during full text extraction or export: {e}", exc_info=True)
            raise

        if summarize:
            # 2. Summarize the selected sections
            try:
                dtext = dtext_selected
            except Exception as e:
                logger.error(f"Error extracting selected sections: {e}", exc_info=True)
                raise

            # Initialize dictionaries used for storing summaries and question sets
            dsum = self.cache.data["summaries"]
            dqa = self.cache.data["qa"]

            # Iterate through all sections to generate their summary and question set
            logger.info("-- Starting summary and Q&A generation")

            # Starting the LLM model by launching Ollama in a subprocess
            try:
                self.model.call()
            except Exception as e:
                logger.error(f"Error starting LLM model (Ollama): {e}", exc_info=True)
                raise

            # Start of LLM prompt asking for a complete, precise summary yet as concise as possible
            summary_instruct = "You are an expert science and humanities educator. Given the following text, do two things: 1. Summarize it clearly and as concisely as precision allows. 2. Then, extract the key concepts or facts as 3–8 concise bullet points. Your answer should look like: 'Summary: ... Key Concepts: ...'. Text: {text}"

            # Start of LLM prompt asking for a set of 5 questions about a previously fed text
            questions_instruct = "You are an expert science and humanities educator. Given the following text, generate a set of five relevant questions and their answers. Make sure to only output the questions and their answers in the form of 'Q: ... A:...'. Text: {text}"

            for key in dtext.keys():
                from .utils import flatten_text
                text_content = flatten_text(dtext[key])

                # Create summary and bullet points of each main_text entry and store it in dsum
                if key not in dsum.keys():
                    logger.info("--- Generating nested summary of section '{}'".format(key))
                    try:
                        dsum[key] = self.recursive_summarize(text_content, summary_instruct, is_final=True)
                        self.cache.update_summary(key, dsum[key])
                    except Exception as e:
                        logger.error(f"Error generating summary for section '{key}': {e}", exc_info=True)

                else:
                    logger.warning("--- Summary of section '{}' already exists, skipping")

                # Generate questions based on the text
                if key not in dqa.keys():
                    logger.info("--- Generating Q&A of section '{}'".format(key))
                    try:
                        dqa[key] = self.model.generate(
                            questions_instruct.format(text=text_content)
                        )
                        self.cache.update_qa(key, dqa[key])
                    except Exception as e:
                        logger.error(f"Error generating Q&A for section '{key}': {e}", exc_info=True)
                else:
                    logger.warning("--- Q&A of section '{}' already exists, skipping")

            logger.info("-- Finished summary and Q&A generation")

            if self.doc.metadata:
                try:
                    # Generate MD file structuring the summaries, key concepts and questions by section
                    write_markdown(self.doc.metadata["title"], dsum, dqa, self.output_folder)

                    # Generate Anki cards using both Basic and Cloze models from dqa
                    if self.cards:
                        deck = CG(self.doc.metadata["title"], self.deck_id)
                        deck.generate(dqa, self.output_folder)
                except Exception as e:
                    logger.error(f"Error writing output files (Markdown/Anki): {e}", exc_info=True)

        # Indicate the pipeline has finished running
        logger.warning("==== DONE ====")
        return dtext_selected, dtext, dsum, dqa
