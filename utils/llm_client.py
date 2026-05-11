from utils.ollama_client import OllamaClient

# Centralized provider for the LLM client instance.
# Currently defaults to OllamaClient, but can be updated later to instantiate
# different clients based on configuration.

client = OllamaClient()
