# ai_feedback_logger.py
import json
import time
from pathlib import Path
from typing import List, Dict, Any
from .config import config

class AIFeedbackLogger:
    """
    Receives feedback on AI-predicted tags and logs it to a persistent file.
    """
    def __init__(self):
        self.log_file = config.get_path("ai_feedback_log")
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log_feedback(self, message_id: str,
                     ai_predicted_tags: List[str],
                     user_final_tags: List[str]):
        """
        Logs a user's tag corrections for a specific message.
        """
        log_entry = {
            "timestamp": time.time(),
            "message_id": message_id,
            "ai_predicted_tags": ai_predicted_tags,
            "user_final_tags": user_final_tags
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

# Global instance for easy access
feedback_logger = AIFeedbackLogger()
