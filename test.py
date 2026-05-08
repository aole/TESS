from ddgs import DDGS
from trafilatura import fetch_url, extract

# results = DDGS().extract("https://en.wikipedia.org/wiki/List_of_Twenty20_International_records", fmt="text_markdown")
# print(results['content'])


url = "https://en.wikipedia.org/wiki/List_of_Twenty20_International_records"
result = fetch_url(url)
if result:
    output = extract(result, output_format="markdown", include_comments=False, favor_precision=True)
    print(output)
