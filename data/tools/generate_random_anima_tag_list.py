import json, random

def generate_random_anima_tag_list():
    with open(r"D:\downloads\danbooru-tags.json", "r", encoding="utf-8") as file:
        data = json.load(file)
    
    tags = data["tags"]
    tags_gen = [tagsg for tagsg in tags if tagsg["c"] ==0]
    
    keywords = ", ".join(random.choice(tags_gen)["n"].strip() for i in range(20))
    return keywords
