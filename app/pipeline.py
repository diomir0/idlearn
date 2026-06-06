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

import json
import os
import random

import pymupdf

from app import config

from .cg import CG
from .llmmodel import LLMModel
from .text_extractor import TextExtractor

# from .config import deck_id
from .utils import IdlearnCache, write_markdown, write_full_text_markdown, get_toc, flatten_text
from .tokenizer import SmartTokenizer
from .knowledge_graph import extract_knowledge_graph, KnowledgeGraph
from .obsidize import (
    clip_pdf, load_template, resolve_template_name,
    PdfContent, PdfMetadata, PdfPage, Template, Property,
)


class Pipeline:
    def __init__(self, input_file, output_folder, cards=True,
                 api_type="ollama", model=None, base_url=None, api_key=None):
        self.deck_id = random.randint(0, 9999999999)
        config.deck_id = self.deck_id
        self.cache = IdlearnCache()
        # Clear cached summaries and Q&A from previous documents so they
        # don't leak into the new document's output.
        self.cache.data["summaries"] = {}
        self.cache.data["qa"] = {}
        self.cache.save()

        # Configure LLM Model (supports Ollama and OpenAI-compatible APIs)
        # Default to a multimodal model so images can be included in summaries.
        model_name = model or ("gemma3:4b" if api_type == "ollama" else "gpt-4o")
        self.model = LLMModel(model=model_name, api_type=api_type,
                              base_url=base_url, api_key=api_key)
        self.output_folder = output_folder
        self.obsidian_folder = os.path.expanduser("~/Documents/obsidian")
        self.doc = pymupdf.open(input_file)
        self.cards = cards
        self.text_extractor = TextExtractor(self.doc)
        self.tokenizer = SmartTokenizer(max_tokens=3000)
        # Images extracted per section: {section_title: [image_path, ...]}
        self.section_images = {}
        # Knowledge graph extracted from summaries
        self.knowledge_graph = None



    def recursive_summarize(self, text, instruct, is_final=False, images=None):
        """Summarizes text using a nested approach for long segments.

        Args:
            text: The text to summarize.
            instruct: The instruction prompt for final summarization.
            is_final: Whether this is the final summarization pass.
            images: Optional list of image file paths to include for
                    multimodal models (only used in the final pass).
        """
        if not is_final:
            # Intermediate prompt for nested summarization
            prompt = "Summarize the following text concisely while preserving all key information: {text}"
        else:
            prompt = instruct

        segments = self.tokenizer.tokenize(text)

        if len(segments) == 1:
            # For the final pass, include images if available
            if is_final and images:
                return self.model.generate(prompt.format(text=text), images=images)
            return self.model.generate(prompt.format(text=text))

        summaries = []
        for seg in segments:
            content = seg['content']
            summaries.append(self.recursive_summarize(content, instruct, is_final=False))

        combined_summaries = "\n\n".join(summaries)
        return self.recursive_summarize(combined_summaries, instruct, is_final=is_final, images=images)

    def run(self, sections, summarize=True):
        from .logger import logger

        dsum = {}
        dqa = {}
        dtext = {}

        # 1. Prepare sections and extract images for summarization
        logger.info("-- Preparing sections for processing")
        try:
            # If no specific sections are selected, default to all sections
            all_sections_toc = get_toc(self.doc)
            if not sections:
                sections = all_sections_toc

            # Extract text for summarization (used internally even if not exported)
            dtext_selected = self.text_extractor.extract(sections)

            # Extract images from the selected sections for multimodal summarization
            try:
                img_dir = os.path.join(self.output_folder, "extracted_images")
                logger.info("-- Extracting images from selected sections")
                self.section_images = self.text_extractor.extract_section_images(
                    sections, output_dir=img_dir
                )
                total_imgs = sum(len(v) for v in self.section_images.values())
                logger.info(f"-- Extracted {total_imgs} images across {len(self.section_images)} sections")
            except Exception as e:
                logger.warning(f"Image extraction failed (continuing without images): {e}")
                self.section_images = {}
        except Exception as e:
            logger.error(f"Error during section preparation: {e}", exc_info=True)
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

            # Start of LLM prompt asking for a comprehensive detailed digest
            summary_instruct = (
                "You are an expert academic educator and research synthesizer. "
                "Given the following text (and any accompanying figures), produce a "
                "**comprehensive detailed digest** that:\n\n"
                "1. **Comprehensive Summary**: Write a thorough narrative summary that "
                "captures every significant concept, argument, finding, and nuance. "
                "Do not omit important details — be as complete as precision requires. "
                "Organize the summary logically, following the structure of the original text.\n\n"
                "2. **Key Concepts**: List 5–12 key concepts, definitions, or facts as "
                "bullet points. Each should be precise and self-contained.\n\n"
                "3. **Figures**: If any figures/images are provided, describe each one in "
                "detail: what it shows, its key takeaways, and how it relates to the text.\n\n"
                "Format your response as:\n\n"
                "## Summary\n"
                "[Your detailed summary here]\n\n"
                "## Key Concepts\n"
                "- [Concept 1]\n"
                "- [Concept 2]\n"
                "...\n\n"
                "## Figures\n"
                "- **Figure X**: [Description and key takeaway]\n\n"
                "Text: {text}"
            )

            # Start of LLM prompt asking for a set of 5 questions about a previously fed text
            questions_instruct = "You are an expert science and humanities educator. Given the following text, generate a set of five relevant questions and their answers. Make sure to only output the questions and their answers in the form of 'Q: ... A:...'. Text: {text}"

            for key in dtext.keys():
                from .utils import flatten_text
                text_content = flatten_text(dtext[key])

                # Get images for this section (if any)
                section_imgs = self.section_images.get(key, [])

                # Create summary and bullet points of each main_text entry and store it in dsum
                if key not in dsum.keys():
                    logger.info("--- Generating nested summary of section '{}{}'".format(
                        key, f" ({len(section_imgs)} images)" if section_imgs else ""))
                    try:
                        dsum[key] = self.recursive_summarize(
                            text_content, summary_instruct, is_final=True,
                            images=section_imgs if section_imgs else None,
                        )
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

        # 5. Generate knowledge graph from summaries
        if summarize and dsum:
            try:
                doc_title = ""
                if self.doc.metadata and self.doc.metadata.get("title"):
                    doc_title = self.doc.metadata["title"]
                self.knowledge_graph = extract_knowledge_graph(
                    dsum, model=self.model, title=doc_title
                )
                logger.info(f"Knowledge graph generated: "
                            f"{len(self.knowledge_graph.concepts)} concepts, "
                            f"{len(self.knowledge_graph.relations)} relations")
            except Exception as e:
                logger.error(f"Knowledge graph extraction failed: {e}", exc_info=True)

        # Indicate the pipeline has finished running
        logger.warning("==== DONE ====")
        return dtext_selected, dtext, dsum, dqa

    # ------------------------------------------------------------------
    # Obsidian export
    # ------------------------------------------------------------------

    def export_obsidian(
        self,
        template="idlearn-summary",
        sections=None,
        dtext=None,
        dsum=None,
        dqa=None,
        output_folder=None,
    ):
        """Export the pipeline results as an Obsidian note using an Obsidize template.

        This method takes idlearn's extracted PDF content (sections, summaries,
        Q&A) and feeds it into the Obsidize template engine to produce a
        structured Markdown file compatible with Obsidian, complete with YAML
        frontmatter.

        Args:
            template: Template name ("idlearn-summary", "idlearn-study-notes",
                      "idlearn-academic", "idlearn-flashcard-review",
                      "academic", "default") or an absolute path to a JSON
                      template file.
            sections: List of ToC section tuples (level, title, start, end).
                      If None, uses the document's full ToC.
            dtext:    Dict of section_title → extracted text. If None, extracts
                      from the document using the given sections.
            dsum:     Dict of section_title → LLM summary. If None, uses
                      cached summaries.
            dqa:      Dict of section_title → LLM Q&A. If None, uses cached Q&A.
            output_folder: Folder to write the .md file. Defaults to
                           self.output_folder.

        Returns:
            ClipPdfResult with note_name, full_content, frontmatter, etc.
            Also writes the .md file and copies images to disk.
        """
        from .logger import logger

        logger.info("-- Starting Obsidian export")

        # --- Resolve template ---------------------------------------------------
        if isinstance(template, str):
            obs_template = load_template(template)
        elif isinstance(template, Template):
            obs_template = template
        else:
            raise ValueError(
                f"template must be a template name string or a Template object, "
                f"got {type(template)}"
            )

        # --- Build PdfContent from the open document -----------------------------
        meta = self.doc.metadata or {}
        pdf_metadata = PdfMetadata(
            title=meta.get("title", "") or "",
            author=meta.get("author", "") or "",
            subject=meta.get("subject", "") or "",
            keywords=meta.get("keywords", "") or "",
            creator=meta.get("creator", "") or "",
            producer=meta.get("producer", "") or "",
            creation_date=meta.get("creationDate", "") or "",
            mod_date=meta.get("modDate", "") or "",
        )

        # Extract per-page text
        pdf_pages = []
        for page_num in range(self.doc.page_count):
            page = self.doc.load_page(page_num)
            pdf_pages.append(PdfPage(
                page_number=page_num + 1,
                text=page.get_text(),
            ))

        # Derive filename from the opened document
        file_name = os.path.basename(self.doc.name) if hasattr(self.doc, 'name') and self.doc.name else ""
        file_path = self.doc.name if hasattr(self.doc, 'name') else ""

        pdf_content = PdfContent(
            text="\n".join(p.text for p in pdf_pages),
            pages=pdf_pages,
            page_count=self.doc.page_count,
            metadata=pdf_metadata,
            file_name=file_name,
            file_path=file_path,
            file_size=os.path.getsize(file_path) if file_path and os.path.exists(file_path) else 0,
            images=[img for imgs in self.section_images.values() for img in imgs],
        )

        # --- Extract section text if not provided -------------------------------
        if dtext is None:
            toc_sections = sections or get_toc(self.doc)
            try:
                dtext = self.text_extractor.extract(toc_sections)
            except Exception as e:
                logger.error(f"Error extracting text for Obsidian export: {e}", exc_info=True)
                dtext = {}

        # --- Build extra template variables from idlearn data --------------------
        extra_variables = {}
        # Sections: list of dicts with title and content
        if dtext:
            sections_list = []
            for i, (key, value) in enumerate(dtext.items(), start=1):
                flat = flatten_text(value) if isinstance(value, (dict, list)) else str(value)
                sections_list.append({
                    "title": key,
                    "content": flat,
                    "index": i,
                })
            extra_variables["{{sections}}"] = json.dumps(sections_list)

            # Always prefer idlearn's structured content over raw PDF text.
            # The structured extraction preserves section boundaries and
            # headings, producing much better Markdown output.
            full_text_parts = []
            for key, value in dtext.items():
                flat = flatten_text(value) if isinstance(value, (dict, list)) else str(value)
                full_text_parts.append(f"## {key}\n\n{flat}")
            extra_variables["{{content}}"] = "\n\n".join(full_text_parts)

        # Summaries: list of dicts with title and summary text
        # Include image references in the summary data for multimodal context
        if dsum:
            summaries_list = []
            for i, (key, value) in enumerate(dsum.items(), start=1):
                # Include image references as Obsidian wikilinks
                section_imgs = self.section_images.get(key, [])
                img_markdown = ""
                if section_imgs:
                    img_markdown = "\n\n" + "\n".join(
                        f"![[{os.path.basename(img)}]]"
                        for img in section_imgs
                    )
                summaries_list.append({
                    "title": key,
                    "summary": value + img_markdown if img_markdown else value,
                    "index": i,
                })
            extra_variables["{{summaries}}"] = json.dumps(summaries_list)

        # Q&A pairs: list of dicts with section title and Q&A text
        if dqa:
            qa_list = []
            for i, (key, value) in enumerate(dqa.items(), start=1):
                qa_list.append({
                    "title": key,
                    "qa": value,
                    "index": i,
                })
            extra_variables["{{qa_pairs}}"] = json.dumps(qa_list)

        # --- Clip with template -------------------------------------------------
        result = clip_pdf(
            pdf_content=pdf_content,
            template=obs_template,
            extra_variables=extra_variables,
        )

        # --- Write output file --------------------------------------------------
        out_dir = output_folder or self.obsidian_folder
        os.makedirs(out_dir, exist_ok=True)
        output_path = os.path.join(out_dir, f"{result.note_name}.md")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result.full_content)

        # --- Copy extracted images into the vault / output folder ----------------
        if self.section_images:
            import shutil
            img_dest_dir = os.path.join(out_dir, "extracted_images")
            os.makedirs(img_dest_dir, exist_ok=True)
            for section_title, img_paths in self.section_images.items():
                for img_path in img_paths:
                    if os.path.isfile(img_path):
                        dest = os.path.join(img_dest_dir, os.path.basename(img_path))
                        if not os.path.exists(dest):
                            shutil.copy2(img_path, dest)
            logger.info(f"-- Copied images to {img_dest_dir}")

        logger.info(f"-- Obsidian note written to {output_path}")

        return result
