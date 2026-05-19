# ========================================================================================#
#                                       IDLEARN                                          #
#                                     llmmodel.py                                        #
# ========================================================================================#

# Filename: llmmodel.py
# Author: diomir0
# Date of creation: 05 Jul 2025

# This script contains the pipeline functions for generating summaries and key concepts
# from text structured in a Python dictionary, where keys correspond to the different
# sections of the text and values to their associated text, using local quantized
# version of the mistral-7B-Instruct LLM model run via ollama.

import os
import re
import subprocess

import requests

from .logger import logger
from .utils import IdlearnCache


class LLMModel:
    def __init__(self, model="mistral:7B-instruct", temperature=0.4,
                 api_type="ollama", base_url="https://ollama.com", api_key=None):
        self.model = model
        self.temperature = temperature
        self.api_type = api_type  # "ollama" or "openai"

        # Default URLs based on API type
        if api_type == "ollama":
            self.base_url = base_url or "http://localhost:11434"
        else:  # openai
            self.base_url = base_url or "https://api.openai.com/v1"

        self.api_key = api_key
        self.cache = IdlearnCache()

    def _clean_base_url(self):
        """Removes trailing /v1 or /api paths to ensure compatibility with the ollama package."""
        url = self.base_url
        if url.endswith('/v1'):
            url = url[:-3]
        if url.endswith('/api'):
            url = url[:-4]
        # Ensure no trailing slash for consistency
        return url.rstrip('/')

    def ollama_is_running(self):
        """Checks if the local Ollama server is running."""
        try:
            response = requests.get(self.base_url)
            return response.status_code == 200
        except requests.exceptions.ConnectionError:
            return False

    def call(self):
        """Starts the Ollama server if using local API and it's not running."""
        if self.api_type == "ollama":
            # Only attempt to start if it's a local URL (not cloud)
            if "localhost" in self.base_url or "127.0.0.1" in self.base_url:
                if not self.ollama_is_running():
                    logger.info("Starting local Ollama server...")
                    subprocess.Popen(["ollama", "serve"])
        # Cloud APIs don't need a local server

    def generate(self, prompt):
        """Generates text using the configured LLM API."""
        if self.api_type == "ollama":
            try:
                return self._generate_ollama(prompt)
            except Exception as e:
                logger.warning(f"Ollama package failed ({e}), falling back to requests-based Ollama API...")
                return self._generate_ollama_requests(prompt)
        elif self.api_type == "openai":
            return self._generate_openai(prompt)
        else:
            raise ValueError(f"Unsupported api_type: {self.api_type}")

    def _generate_ollama(self, prompt):
        """Generates text using the official Ollama Python package (Local or Cloud)."""
        from ollama import Client

        clean_url = self._clean_base_url()
        headers = {}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'

        client = Client(host=clean_url, headers=headers)

        messages = [
            {
                'role': 'system',
                'content': "You are a helpful assistant that has insight in academic, theoretical knowledge in science and humanities, and that is able to accurately summarize complex texts concisely yet precisely without skipping important details, as well as generate insightful questions about these texts."
            },
            {
                'role': 'user',
                'content': prompt
            }
        ]

        # Use stream=True and accumulate chunks for Ollama Cloud compatibility
        full_response = ""
        for part in client.chat(self.model, messages=messages, stream=True):
            if 'message' in part and 'content' in part['message']:
                full_response += part['message']['content']

        return full_response

    def _generate_ollama_requests(self, prompt):
        """Fallback: Generates text using the local Ollama REST API directly."""
        url = f"{self._clean_base_url()}/api/generate"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = requests.post(
            url,
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "system": "You are a helpful assistant that has insight in academic, theoretical knowledge in science and humanities, and that is able to accurately summarize complex texts concisely yet precisely without skipping important details, as well as generate insightful questions about these texts.",
                "temperature": self.temperature,
            },
            headers=headers
        )
        response.raise_for_status()
        return response.json()["response"]

    def _generate_openai(self, prompt):
        """Generates text using an OpenAI-compatible Cloud API (e.g., Zed, OpenAI)."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant that has insight in academic, theoretical knowledge in science and humanities, and that is able to accurately summarize complex texts concisely yet precisely without skipping important details, as well as generate insightful questions about these texts."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": self.temperature
        }
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    # Function splitting the text provided as argument in full sentence strings shorten than ~2500 tokens
    def partition(self, text, partitions=[]):
        d = round(len(text) / 2500 * 0.75)
        if d > 1:
            breakpos = [
                item.span()[1] for item in list(re.finditer(r"[a-zA-Z]+\s?\.+", text))
            ]
            if len(breakpos) != 0:
                if len(breakpos) % 2 == 0:
                    midbreak = breakpos[int(len(breakpos) / 2) - 1]
                else:
                    import numpy as np
                    midbreak = np.median(breakpos)
                splittext = [text[:midbreak], text[midbreak + 1 :]]
                for split in splittext:
                    _ = self.partition(split, partitions)
            else:
                partitions.append(text)
        else:
            partitions.append(text)
        return partitions

    # Function shortening the text provided as argument if it is longer than ~2500 tokens
    def shorten(self, text):
        parts = self.partition(text)
        summary = ""
        if len(parts) > 1:
            instruction = "You are an expert science and humanities educator. Summarize the following text clearly and as concisely as precision allows, as if you were the author of the text: '{text}'."
            summaries = ""
            for p in parts:
                s = self.generate(instruction.format(p))
                summaries += s + " "
            summary = self.summarize(summaries)
        else:
            return text
        return summary

    def summarize(self, dtext):
        summary_instruct = "You are an expert science and humanities educator. Given the following text, do two things: 1. Summarize it clearly and as concisely as precision allows. 2. Then, extract the key concepts or facts as 3–5 concise bullet points. Your answer should look like: 'Summary: ... Key Concepts: ...'. Text: {text}"

        for key in dtext.keys():
            # Create summary and bullet points of each main_text entry and store it in dsum
            if key not in dtext.keys():
                logger.info("--- Generating summary of section '{}'".format(key))

                dtext[key] = self.generate(summary_instruct.format(text=dtext[key]))
                self.cache.update_summary(key, dtext[key])
            else:
                logger.warning("--- Summary of section '{}' already exists, skipping")
