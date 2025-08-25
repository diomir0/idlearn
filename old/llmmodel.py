#========================================================================================#
#                                       IDLEARN                                          #
#                                     llmmodel.py                                        #
#========================================================================================# 

# Filename: llmmodel.py
# Author: diomir0
# Date of creation: 05 Jul 2025

# This script contains the pipieline functions for generating summaries and key concepts 
# from text structured in a Python dictionary, where keys correspond to the different 
# sections of the text and values to their associated text, using local quantized 
# version of the mistral-7B-Instruct LLM model run via ollama.

import requests
import subprocess
import threading
import shlex
from huggingface_hub import login
from huggingface_hub import InferenceClient
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM

class LLMModel:

    def __init__(self, model = 'mistral:7B-instruct', temperature = 0.4):
        self.model = model
        self.temperature = temperature


    def ollama_is_running(self):
        try:
            response = requests.get("http://localhost:11434")
            return response.status_code == 200
        except requests.exceptions.ConnectionError:
            return False

    
    def call(self):
        if self.ollama_is_running() == False:
            subprocess.Popen(["ollama", "serve"])

    
    # Function prompting mistral/7B-Instruct and returning its output
    def generate(self, prompt):
        url = "http://localhost:11434/api/generate"
        response = requests.post(url, json={
            "model": self.model,
            "prompt": prompt,
            "stream": False,  # Set to True if you want streaming responses
            "system": "You are a helpful assistant that has insight in academic, theoretical knowledge in science and humanities, and that is able to accurately summarize complex texts concisely yet precisely without skipping important details, as well as generate insightful questions about these texts.",
            "temperature": self.temperature
        })
        return response.json()["response"]
