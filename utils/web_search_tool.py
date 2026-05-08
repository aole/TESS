from ddgs import DDGS
from trafilatura import fetch_url, extract

def web_search(query: str, max_results: int = 3) -> str:
    """
    Search the web for a given query and return a cleaned summary.
    """
    try:
        ddgs = DDGS()
        # Using a smaller max_results to keep context window clean
        results = list(ddgs.text(query, max_results=max_results))
        
        if not results:
            return "No results found."
            
        output = "### Search Results\n"
        for i, res in enumerate(results):
            output += f"- **{res.get('title')}** ({res.get('href')}): {res.get('body')}\n"
        
        return output
    except Exception as e:
        return f"An error occurred during web search: {str(e)}"

def extract_url(url: str) -> str:
    """
    Fetch and extract the content of a specific URL.
    Use this to read the full webpage content from a link.
    """
    try:
        result = fetch_url(url)
        if result:
            output = extract(result, output_format="markdown", include_comments=False, favor_precision=True)
            return str(output[:25000])
    except Exception as e:
        return f"An error occurred during URL extraction: {str(e)}"
