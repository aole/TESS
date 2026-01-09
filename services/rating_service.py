import json
import os
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from datetime import datetime

DATA_FILE = os.path.join(os.getcwd(), 'data', 'ratings.json')

@dataclass
class Rating:
    model: str
    tag: str
    rating: int
    message_id: str
    timestamp: str

class RatingService:
    def __init__(self):
        self.ratings: List[Rating] = self._load_ratings()

    def _load_ratings(self) -> List[Rating]:
        if not os.path.exists(DATA_FILE):
            return []
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                return [Rating(**item) for item in data]
        except Exception as e:
            print(f"Error loading ratings: {e}")
            return []

    def _save_ratings(self):
        try:
            os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
            with open(DATA_FILE, 'w') as f:
                json.dump([asdict(r) for r in self.ratings], f, indent=4)
        except Exception as e:
            print(f"Error saving ratings: {e}")

    def add_rating(self, model: str, tag: str, rating: int, message_id: str):
        # Check if update is needed (rating exists for this msg + tag?)
        # Usually we allow one rating per tag per message.
        # If user rates "Coding" 5, then "Coding" 4, we should update.
        
        existing = next((r for r in self.ratings if r.message_id == message_id and r.tag == tag), None)
        
        if existing:
            existing.rating = rating
            existing.timestamp = datetime.now().isoformat()
        else:
            new_rating = Rating(
                model=model,
                tag=tag,
                rating=rating,
                message_id=message_id,
                timestamp=datetime.now().isoformat()
            )
            self.ratings.append(new_rating)
            
        self._save_ratings()

    def get_ratings_for_message(self, message_id: str) -> List[Rating]:
        return [r for r in self.ratings if r.message_id == message_id]

    def get_model_stats(self, model_name: str) -> Dict[str, Dict[str, float]]:
        """
        Returns stats per tag for a model:
        {
            "Coding": {"average": 4.5, "count": 10},
            "General": {"average": 3.0, "count": 5}
        }
        """
        model_ratings = [r for r in self.ratings if r.model == model_name]
        stats = {}
        
        # Group by tag
        tags = set(r.tag for r in model_ratings)
        for tag in tags:
            tag_ratings = [r.rating for r in model_ratings if r.tag == tag]
            if tag_ratings:
                avg = sum(tag_ratings) / len(tag_ratings)
                stats[tag] = {"average": round(avg, 1), "count": len(tag_ratings)}
                
        return stats

    def get_best_tag_for_model(self, model_name: str) -> Optional[Dict]:
        stats = self.get_model_stats(model_name)
        if not stats:
            return None
        
        # Heuristic for "best": Highest average, tie-break by count
        best_tag = max(stats.items(), key=lambda item: (item[1]['average'], item[1]['count']))
        return {"tag": best_tag[0], "average": best_tag[1]['average'], "count": best_tag[1]['count']}

rating_service = RatingService()
