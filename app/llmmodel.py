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

import base64
import os
import re
import subprocess

import requests

from .logger import logger
from .utils import IdlearnCache


class LLMModel:
    def __init__(self, model="gemma4:31b:cloud", temperature=0.4,
                 api_type="ollama", base_url="https://ollama.com", api_key=None):
        self.model = model
        self.temperature = temperature
        self.api_type = api_type  # "ollama" or "openai"

        # Default URLs based on API type
        if api_type == "ollama":
            self.base_url = base_url or "http://localhost:11434"
        else:  # openai
            self.base_url = base_url or "https://api.openai.com/v1"

        # If no API key was provided, check the OLLAMA_API_KEY environment variable
        # (required for Ollama Cloud at https://ollama.com/api)
        if not api_key:
            api_key = os.environ.get("OLLAMA_API_KEY")
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

    def generate(self, prompt, images=None):
        """Generates text using the configured LLM API.

        Args:
            prompt: Text prompt to send to the LLM.
            images: Optional list of image paths or base64-encoded strings
                    for multimodal models. Each element can be:
                    - A file path (str) to an image file
                    - A base64-encoded string of image bytes
        """
        if self.api_type == "ollama":
            try:
                return self._generate_ollama(prompt, images=images)
            except Exception as e:
                logger.warning(f"Ollama package failed ({e}), falling back to requests-based Ollama API...")
                # return self._generate_ollama_requests(prompt)
                return None
        elif self.api_type == "openai":
            return self._generate_openai(prompt, images=images)
        else:
            raise ValueError(f"Unsupported api_type: {self.api_type}")

    @staticmethod
    def _prepare_images(images):
        """Convert a list of image paths or raw bytes to base64-encoded strings.

        Args:
            images: List of file paths (str) or base64-encoded strings.

        Returns:
            List of base64-encoded strings suitable for the Ollama API.
        """
        if not images:
            return []
        result = []
        for img in images:
            if img is None:
                continue
            # If it looks like a file path, read and encode it
            if isinstance(img, str) and os.path.isfile(img):
                with open(img, "rb") as f:
                    result.append(base64.b64encode(f.read()).decode("utf-8"))
            elif isinstance(img, bytes):
                result.append(base64.b64encode(img).decode("utf-8"))
            else:
                # Assume it's already a base64 string
                result.append(img)
        return result

    def _generate_ollama(self, prompt, images=None):
        """Generates text using the official Ollama Python package (Local or Cloud).

        Args:
            prompt: Text prompt.
            images: Optional list of image paths or base64 strings for multimodal models.
        """
        from ollama import Client

        clean_url = self._clean_base_url()
        headers = {}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'

        client = Client(host=clean_url, headers=headers)

        user_message = {
            'role': 'user',
            'content': prompt,
        }

        # Attach images if provided (multimodal models like gemma3, llava, etc.)
        prepared_images = self._prepare_images(images)
        if prepared_images:
            user_message['images'] = prepared_images

        messages = [
            {
                'role': 'system',
                'content': "You are a helpful assistant that has insight in academic, theoretical knowledge in science and humanities, and that is able to accurately summarize complex texts in details without skipping important details, as well as generate insightful questions about these texts."
            },
            user_message,
        ]

        # Use stream=True and accumulate chunks for Ollama Cloud compatibility
        full_response = ""
        for part in client.chat(self.model, messages=messages, stream=True):
            if 'message' in part and 'content' in part['message']:
                full_response += part['message']['content']

        return full_response

    def _generate_ollama_requests(self, prompt, images=None):
        """Fallback: Generates text using the Ollama REST API directly."""
        url = f"{self._clean_base_url()}/api/chat"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        user_message = {
            "role": "user",
            "content": prompt,
        }

        prepared_images = self._prepare_images(images)
        if prepared_images:
            user_message["images"] = prepared_images

        response = requests.post(
            url,
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that has insight in academic, theoretical knowledge in science and humanities, and that is able to accurately summarize complex texts concisely yet precisely without skipping important details, as well as generate insightful questions about these texts."
                    },
                    user_message,
                ],
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                },
            },
            headers=headers
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

    def _generate_openai(self, prompt, images=None):
        """Generates text using an OpenAI-compatible Cloud API (e.g., Zed, OpenAI).

        Supports multimodal (vision) models by sending images as base64 in the
        OpenAI chat-completions image_url format.
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        # Build user message content — text-only or multimodal
        user_content = [{"type": "text", "text": prompt}]
        prepared_images = self._prepare_images(images)
        for img_b64 in prepared_images:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_b64}"
                }
            })

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant that has insight in academic, theoretical knowledge in science and humanities, and that is able to accurately summarize complex texts concisely yet precisely without skipping important details, as well as generate insightful questions about these texts."
                },
                {
                    "role": "user",
                    "content": user_content if len(user_content) > 1 else prompt
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
                summaries += (s or "") + " "
            summary = self.summarize(summaries)
        else:
            return text
        return summary

    def summarize(self, dtext):
        summary_instruct = "You are an expert science and humanities educator. Given the following text, do two things: 1. Summarize it clearly and as concisely as precision allows. 2. Then, extract the key concepts or facts as 3–5 concise bullet points. Your answer should look like: 'Summary: ... Key Concepts: ...'. Text: {text}"

        for key in dtext.keys():
            # Create summary and bullet points of each main_text entry and store it in dsum
            if key not in self.cache.data["summaries"]:
                logger.info("--- Generating summary of section '{}'".format(key))

                dtext[key] = self.generate(summary_instruct.format(text=dtext[key]))
                self.cache.update_summary(key, dtext[key])
            else:
                logger.warning("--- Summary of section '{}' already exists, skipping".format(key))
