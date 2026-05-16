import requests

def fetch_knowledge(query: str) -> dict[str, any]:
    """
    Search and retrieve a concise summary from Wikipedia for a given topic.

    This tool is designed for fact-retrieval and entity lookup. It accesses the 
    Wikimedia REST API to pull the 'lead' section of a page.

    IMPORTANT:
    - QUERY FORMAT: You MUST use precise nouns or official titles (e.g., "Nikola Tesla", 
      "Quantum Mechanics", "Fishers, Indiana"). 
    - NO QUESTIONS: Do NOT pass full questions like "Who was Nikola Tesla?" or 
      "Tell me about Tesla." The API will fail if the string does not match a page title.
    - REFINEMENT: If the tool returns a 'Topic not found' error, try a more specific 
      or simplified noun. If you need general 'facts' or 'news', use the `search_web` 
      tool instead.
    - NO API KEY REQUIRED: Uses public Wikipedia endpoints.

    Args:
        query (str): The specific encyclopedic title or entity to look up.

    Returns:
        dict[str, any]: A dictionary containing:
            - title: The official Wikipedia page title.
            - extract: A high-level summary of the subject.
            - url: The direct link to the full article.
    """
    # Wikipedia expects underscores for spaces in the URL path
    formatted_query = query.strip().replace(' ', '_')
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{formatted_query}"
    
    headers = {
        "User-Agent": "ModelMgmtKnowledgeBot/1.1 (developer-contact@example.local)"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 404:
            return {
                "error": f"Topic '{query}' not found on Wikipedia. "
                         "Try using a simpler noun or the search_web tool for broader questions."
            }
            
        response.raise_for_status()
        data = response.json()

        return {
            "title": data.get("title"),
            "extract": data.get("extract"),
            "url": data.get("content_urls", {}).get("desktop", {}).get("page")
        }

    except Exception as e:
        return {"error": f"Failed to retrieve knowledge: {str(e)}"}