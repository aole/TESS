# TESS (Text Evaluation & Synthesis System)

**TESS** is a comprehensive local AI workspace built on top of [Ollama](https://ollama.com). It provides a powerful, unified interface for managing, testing, and interacting with your local large language models.

## Key Features

*   **Chat**: A robust chat interface with history, model selection, and parameter tuning.
*   **Arena**: Compare models side-by-side to evaluate performance and reasoning.
*   **Batch**: Run prompts across multiple models simultaneously to compare outputs.
*   **Notes**: A space to store thoughts, drafts, and synthesized information.
*   **Model Management**: Easily pull, delete, and manage your local Ollama models.
*   **Custom Models**: Create new model variants (Modelfiles) directly within the UI.

## Getting Started

1.  Ensure [Ollama](https://ollama.com) is installed and running.
2.  Install dependencies:
    ```bash
    uv pip install -r requirements.txt
    ```
3.  Run the application:
    ```bash
    uv run main.py
    ```
4.  Open your browser to `http://localhost:8080`.

## Technology

Built with ❤️ using:
*   [NiceGUI](https://nicegui.io) - For the beautiful, responsive web interface.
*   [Ollama](https://ollama.com) - For local LLM inference.
