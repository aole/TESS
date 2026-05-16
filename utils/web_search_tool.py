import requests
from ddgs import DDGS
from trafilatura import extract

def web_search(query: str, max_results: int = 3) -> str:
    """
    Search the web for a given query and return a cleaned summary of results.
    
    Use this tool when the user asks about current events, real-time data, 
    news, or local information that may have changed since your last training update.
    
    Args:
        query (str): The search terms or question to look up.
        max_results (int): The number of search results to return (default 3).

    Returns:
        str: A formatted string containing the titles, URLs, and snippets of the results.
    """
    try:
        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=max_results))
        
        if not results:
            return "No results found for the given query."
            
        output = "### Web Search Results\n"
        for i, res in enumerate(results):
            output += f"- **{res.get('title')}** ({res.get('href')}): {res.get('body')}\n"
        
        return output
    except Exception as e:
        return f"An error occurred during web search: {str(e)}"

def extract_url(url: str) -> str:
    """
    Fetch and extract the full text content of a specific webpage.
    
    This tool is essential for deep-reading a page after a `web_search` identifies 
    a relevant link. It bypasses basic bot-detection by using realistic browser 
    headers and extracts clean markdown text, removing ads and navigation junk.

    Args:
        url (str): The direct URL of the webpage to read.

    Returns:
        str: The extracted page content in markdown format. 
             If the site blocks access or extraction fails, an error message is returned.
    """
    # Mimicking a modern Chrome browser on Windows 10
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    try:
        # Perform the request with custom headers and a 15-second timeout
        response = requests.get(url, headers=headers, timeout=15)
        
        # Explicit check for 403 Forbidden (common for bot blocking)
        if response.status_code == 403:
            return (f"Error: Access denied (403). The website at {url} is protected by "
                    "anti-bot measures and cannot be read by this tool.")
        
        response.raise_for_status()
        
        # Use trafilatura to extract clean content from the HTML body
        content = extract(
            response.text, 
            output_format="markdown", 
            include_comments=False, 
            favor_precision=True
        )
        
        if not content:
            return "Error: The page was loaded, but no meaningful text content could be extracted."

        # Return content with a character limit to prevent context window overflow
        return str(content[:25000])

    except requests.exceptions.RequestException as e:
        return f"Network error occurred while fetching the URL: {str(e)}"
    except Exception as e:
        return f"An unexpected error occurred during extraction: {str(e)}"