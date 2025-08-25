#!/usr/bin/env python3
"""
Automatic Table of Contents Extractor for EPUBs and PDFs
Uses multiple heuristics to identify chapter/section headings
"""

import fitz  # PyMuPDF
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict, Counter
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict
import statistics

@dataclass
class TOCEntry:
    title: str
    level: int
    page: Optional[int] = None
    position: Optional[float] = None

class TOCExtractor:
    def __init__(self):
        # Common patterns for chapter/section titles
        self.heading_patterns = [
            r'^(Chapter|CHAPTER)\s+(\d+|[IVXLCDM]+)[\s\.\-:]*(.*)$',
            r'^(\d+)[\.\)]\s+(.+)$',
            r'^(\d+\.\d+)[\.\)]\s+(.+)$',
            r'^([IVXLCDM]+)[\.\)\s]+(.+)$',
            r'^(PART|Part)\s+(\d+|[IVXLCDM]+)[\s\.\-:]*(.*)$',
            r'^(Section|SECTION)\s+(\d+)[\s\.\-:]*(.*)$',
        ]
        
        # Words that often indicate chapter/section starts
        self.heading_keywords = {
            'chapter', 'section', 'part', 'introduction', 'conclusion',
            'appendix', 'bibliography', 'references', 'index', 'abstract',
            'summary', 'overview', 'background', 'methodology', 'results',
            'discussion', 'acknowledgments', 'preface', 'foreword'
        }

    def extract_toc_from_pdf(self, pdf_path: str) -> List[TOCEntry]:
        """Extract TOC from PDF using multiple strategies"""
        doc = fitz.open(pdf_path)
        
        # Try built-in TOC first
        built_in_toc = self._extract_builtin_toc(doc)
        if built_in_toc:
            doc.close()
            return built_in_toc
        
        # Use text analysis approach
        toc_entries = []
        
        # Analyze font characteristics across document
        font_stats = self._analyze_font_characteristics(doc)
        
        # Extract potential headings
        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]
            
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text = span["text"].strip()
                            if self._is_potential_heading(text, span, font_stats):
                                level = self._determine_heading_level(text, span, font_stats)
                                toc_entries.append(TOCEntry(
                                    title=text,
                                    level=level,
                                    page=page_num + 1,
                                    position=span["bbox"][1]  # y-coordinate
                                ))
        
        doc.close()
        return self._clean_and_sort_toc(toc_entries)

    def extract_toc_from_epub(self, epub_path: str) -> List[TOCEntry]:
        """Extract TOC from EPUB"""
        toc_entries = []
        
        with zipfile.ZipFile(epub_path, 'r') as epub:
            # Try to find navigation document or NCX file
            nav_toc = self._extract_epub_nav_toc(epub)
            if nav_toc:
                return nav_toc
            
            # Fallback: analyze HTML content
            html_files = [f for f in epub.namelist() if f.endswith(('.html', '.xhtml', '.htm'))]
            
            for html_file in html_files:
                try:
                    content = epub.read(html_file).decode('utf-8', errors='ignore')
                    headings = self._extract_headings_from_html(content)
                    toc_entries.extend(headings)
                except Exception:
                    continue
        
        return self._clean_and_sort_toc(toc_entries)

    def _extract_builtin_toc(self, doc) -> List[TOCEntry]:
        """Extract built-in TOC if available"""
        toc = doc.get_toc()
        if not toc:
            return []
        
        entries = []
        for item in toc:
            level, title, page = item
            entries.append(TOCEntry(title=title, level=level, page=page))
        
        return entries

    def _analyze_font_characteristics(self, doc) -> Dict:
        """Analyze font sizes and styles across the document"""
        font_info = defaultdict(list)
        font_sizes = []
        
        # Sample first 20 pages for font analysis
        sample_pages = min(20, len(doc))
        
        for page_num in range(sample_pages):
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]
            
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            size = span["size"]
                            font = span["font"]
                            flags = span["flags"]
                            
                            font_sizes.append(size)
                            font_info[size].append({
                                'font': font,
                                'flags': flags,
                                'text': span["text"].strip()
                            })
        
        # Determine likely heading font sizes
        if font_sizes:
            font_sizes.sort(reverse=True)
            unique_sizes = sorted(list(set(font_sizes)), reverse=True)
            
            return {
                'sizes': unique_sizes,
                'median_size': statistics.median(font_sizes),
                'large_sizes': unique_sizes[:3] if len(unique_sizes) >= 3 else unique_sizes,
                'font_info': dict(font_info)
            }
        
        return {'sizes': [], 'median_size': 12, 'large_sizes': [], 'font_info': {}}

    def _is_potential_heading(self, text: str, span: dict, font_stats: dict) -> bool:
        """Determine if text is likely a heading"""
        if not text or len(text) < 3:
            return False
        
        # Check if it's too long (likely body text)
        if len(text) > 200:
            return False
        
        # Font size check
        size = span["size"]
        if size <= font_stats.get('median_size', 12):
            # Only consider smaller fonts if they match patterns
            if not any(re.match(pattern, text, re.IGNORECASE) for pattern in self.heading_patterns):
                return False
        
        # Bold or italic text is more likely to be a heading
        flags = span["flags"]
        is_bold = flags & 2**4  # Bold flag
        is_italic = flags & 2**1  # Italic flag
        
        # Pattern matching
        pattern_match = any(re.match(pattern, text, re.IGNORECASE) for pattern in self.heading_patterns)
        
        # Keyword matching
        keyword_match = any(keyword in text.lower() for keyword in self.heading_keywords)
        
        # Numeric patterns (like "1.2.3")
        numeric_start = re.match(r'^\d+(\.\d+)*[\.\)\s]', text)
        
        # Roman numeral patterns
        roman_start = re.match(r'^[IVXLCDM]+[\.\)\s]', text, re.IGNORECASE)
        
        # All caps (but not too long)
        is_caps = text.isupper() and len(text) < 50
        
        # Scoring system
        score = 0
        if size > font_stats.get('median_size', 12):
            score += 2
        if is_bold:
            score += 2
        if is_italic:
            score += 1
        if pattern_match:
            score += 3
        if keyword_match:
            score += 2
        if numeric_start:
            score += 2
        if roman_start:
            score += 2
        if is_caps:
            score += 1
        
        return score >= 3

    def _determine_heading_level(self, text: str, span: dict, font_stats: dict) -> int:
        """Determine the hierarchical level of a heading"""
        size = span["size"]
        large_sizes = font_stats.get('large_sizes', [])
        
        # Level based on font size
        if large_sizes:
            if size >= large_sizes[0]:
                level = 1
            elif len(large_sizes) > 1 and size >= large_sizes[1]:
                level = 2
            elif len(large_sizes) > 2 and size >= large_sizes[2]:
                level = 3
            else:
                level = 4
        else:
            level = 2
        
        # Adjust based on content patterns
        if re.match(r'^(Chapter|CHAPTER|Part|PART)', text):
            level = min(level, 1)
        elif re.match(r'^\d+\.\d+\.\d+', text):  # Like 1.2.3
            level = max(level, 3)
        elif re.match(r'^\d+\.\d+', text):  # Like 1.2
            level = max(level, 2)
        elif re.match(r'^\d+[\.\)]', text):  # Like 1. or 1)
            level = max(level, 1)
        
        return max(1, min(level, 6))  # Keep between 1-6

    def _extract_epub_nav_toc(self, epub: zipfile.ZipFile) -> List[TOCEntry]:
        """Extract TOC from EPUB navigation files"""
        nav_files = []
        
        # Look for common navigation files
        for filename in epub.namelist():
            if any(nav in filename.lower() for nav in ['nav', 'toc', 'ncx']):
                nav_files.append(filename)
        
        for nav_file in nav_files:
            try:
                content = epub.read(nav_file).decode('utf-8', errors='ignore')
                
                if nav_file.endswith('.ncx'):
                    return self._parse_ncx_file(content)
                else:
                    return self._parse_nav_html(content)
            except Exception:
                continue
        
        return []

    def _parse_ncx_file(self, content: str) -> List[TOCEntry]:
        """Parse NCX navigation file"""
        entries = []
        try:
            # Remove namespace declarations for simpler parsing
            content = re.sub(r'xmlns[^=]*="[^"]*"', '', content)
            root = ET.fromstring(content)
            
            nav_points = root.findall('.//navPoint')
            for nav_point in nav_points:
                play_order = nav_point.get('playOrder', '0')
                text_elem = nav_point.find('.//text')
                if text_elem is not None:
                    title = text_elem.text
                    level = len(nav_point.findall('./ancestor::navPoint')) + 1
                    entries.append(TOCEntry(title=title, level=level))
        except Exception:
            pass
        
        return entries

    def _parse_nav_html(self, content: str) -> List[TOCEntry]:
        """Parse HTML navigation file"""
        entries = []
        
        # Look for nav elements or lists that might contain TOC
        nav_patterns = [
            r'<nav[^>]*>(.*?)</nav>',
            r'<ol[^>]*class="[^"]*toc[^"]*"[^>]*>(.*?)</ol>',
            r'<ul[^>]*class="[^"]*toc[^"]*"[^>]*>(.*?)</ul>'
        ]
        
        for pattern in nav_patterns:
            matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
            for match in matches:
                entries.extend(self._extract_list_items(match))
        
        return entries

    def _extract_list_items(self, content: str) -> List[TOCEntry]:
        """Extract TOC entries from HTML list items"""
        entries = []
        
        # Find all list items
        li_pattern = r'<li[^>]*>(.*?)</li>'
        items = re.findall(li_pattern, content, re.DOTALL | re.IGNORECASE)
        
        for item in items:
            # Extract text from links or plain text
            text_match = re.search(r'<a[^>]*>([^<]+)</a>|([^<]+)', item)
            if text_match:
                title = (text_match.group(1) or text_match.group(2)).strip()
                if title:
                    # Determine nesting level by counting parent lists
                    level = item.count('<ol') + item.count('<ul') + 1
                    entries.append(TOCEntry(title=title, level=level))
        
        return entries

    def _extract_headings_from_html(self, content: str) -> List[TOCEntry]:
        """Extract headings from HTML content"""
        entries = []
        
        # Find all heading tags
        heading_pattern = r'<h([1-6])[^>]*>([^<]+)</h[1-6]>'
        matches = re.findall(heading_pattern, content, re.IGNORECASE)
        
        for level_str, title in matches:
            level = int(level_str)
            title = re.sub(r'<[^>]+>', '', title).strip()  # Remove any nested tags
            if title:
                entries.append(TOCEntry(title=title, level=level))
        
        return entries

    def _clean_and_sort_toc(self, entries: List[TOCEntry]) -> List[TOCEntry]:
        """Clean up and sort TOC entries"""
        if not entries:
            return []
        
        # Remove duplicates while preserving order
        seen = set()
        cleaned = []
        for entry in entries:
            key = (entry.title.lower(), entry.level)
            if key not in seen:
                seen.add(key)
                cleaned.append(entry)
        
        # Sort by page number if available, otherwise by position
        if any(entry.page for entry in cleaned):
            cleaned.sort(key=lambda x: (x.page or 0, x.position or 0))
        elif any(entry.position for entry in cleaned):
            cleaned.sort(key=lambda x: x.position or 0)
        
        return cleaned

def main():
    """Example usage"""
    extractor = TOCExtractor()
    
    # Example for PDF
    pdf_toc = extractor.extract_toc_from_pdf("example.pdf")
    print("PDF TOC:")
    for entry in pdf_toc:
        indent = "  " * (entry.level - 1)
        page_info = f" (Page {entry.page})" if entry.page else ""
        print(f"{indent}{entry.title}{page_info}")
    
    # Example for EPUB
    epub_toc = extractor.extract_toc_from_epub("example.epub")
    print("\nEPUB TOC:")
    for entry in epub_toc:
        indent = "  " * (entry.level - 1)
        print(f"{indent}{entry.title}")

if __name__ == "__main__":
    main()
