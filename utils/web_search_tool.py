import re
from ddgs import DDGS

def clean_markdown(text: str) -> str:
    """
    Strips navigation menus, reference lists, and excess 
    markdown formatting that confuses LLMs.
    """
    # 1. Remove the reference link list at the bottom (e.g., [1]: http://...)
    text = re.sub(r'\[\d+\]: http.*', '', text)
    
    # 2. Remove inline reference markers (e.g., [1], [25])
    text = re.sub(r'\[\d+\]', '', text)
    
    # 3. Remove common navigation/footer keywords and their surrounding lines
    noise_keywords = [
        "Terms of Use", "Privacy Policy", "Cookie Policy", "Contact Us", 
        "Log In", "Sign Up", "About Us", "All Rights Reserved", "Copyright"
    ]
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        # Skip lines that are just navigation links or contain too much noise
        if any(keyword.lower() in line.lower() for keyword in noise_keywords):
            continue
        # Skip lines that are likely just menu items (very short, multiple pipes or bullets)
        if len(line.strip()) < 100 and ('|' in line or '*' in line):
            if "°F" not in line and "°C" not in line: # Keep weather data!
                continue
        cleaned_lines.append(line)
    
    # 4. Collapse multiple newlines
    text = '\n'.join(cleaned_lines)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

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
            output += f"- **{res.get('title')}**: {res.get('body')}\n"
            
        # Extract content from the first result
        top_url = results[0].get('href')
        if top_url:
            try:
                extracted = ddgs.extract(top_url, fmt="text_markdown")
                if extracted and 'content' in extracted:
                    raw_content = extracted['content']
                    # CLEANING STEP:
                    cleaned_content = clean_markdown(raw_content)
                    
                    # Limit the length to prevent context overflow (e.g., first 5000 chars)
                    output += f"\n### Detailed Content from {top_url}:\n\n"
                    output += cleaned_content[:5000] 
                else:
                    output += "\n(Detailed content extraction failed.)"
            except Exception as e:
                output += f"\n(Error extracting content: {str(e)})"
                
        return output
    except Exception as e:
        return f"An error occurred during web search: {str(e)}"