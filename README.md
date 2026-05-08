# TESS (Text Evaluation & Synthesis System)

**TESS** is a comprehensive local AI workspace built on top of [Ollama](https://ollama.com). It provides a powerful, unified interface for managing, testing, and interacting with your local large language models.

![TESS Screenshot](Screenshot01.png)
![TESS Screenshot](Screenshot02.png)

## Key Features

*   **Chat**: A robust chat interface with history, model selection, parameter tuning, and dynamic context injection.
*   **Arena**: Compare models side-by-side to evaluate performance and reasoning.
*   **Batch**: Run prompts across multiple models simultaneously to compare outputs.
*   **Story Studio**: High-fidelity, multi-speaker audio synthesis with voice cloning and dynamic character identification, using Omnivoice and Kokoro TTS.
*   **Voice Designer**: Craft custom synthetic voices by adjusting parameters like gender, age, pitch, and accent.
*   **Visual Generation**: Create stunning images using the Anima pipeline in a dedicated workspace or via integrated chat tools.
*   **Tools & Agents**: Automate workflows by seamlessly running tools directly through your local models.
*   **Web Search**: Equip your local models with real-time web access via integrated DuckDuckGo search and URL extraction.
*   **Google Integration**: Connect your Google Workspace to analyze and synthesize documents.
*   **Notes**: A space to store thoughts, drafts, and synthesized information.
*   **Model Management**: Easily pull, delete, and manage your local Ollama models.
*   **Custom Models**: Create new model variants (Modelfiles) directly within the UI.
*   **Playground**: An experimental space for rapid model testing and iteration.

## Getting Started

1.  Ensure [Ollama](https://ollama.com) is installed and running.
2.  Run the application using [uv](https://github.com/astral-sh/uv) (which will automatically handle dependencies from `pyproject.toml`):
    ```bash
    uv run main.py
    ```
3.  Open your browser to `http://localhost:8080`.

## Technology

Built with ❤️ using:
*   [NiceGUI](https://nicegui.io) - For the beautiful, responsive web interface.
*   [Ollama](https://ollama.com) - For local LLM inference.
*   [uv](https://github.com/astral-sh/uv) - Fast Python package and project management.
*   [Omnivoice](https://github.com/k2-fsa/OmniVoice) & [Kokoro](https://github.com/hexgrad/kokoro) - For state-of-the-art TTS and voice cloning.
