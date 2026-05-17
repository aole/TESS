import time
from datetime import datetime
from typing import Dict, Callable, Optional

class SystemMessageService:
    """Service to compile and provide the final system message sent to the model."""
    
    def compile_message(
        self,
        base_prompt: str = "",
        memory_enabled: bool = False,
        has_attachments: bool = False,
        tool_funcs_map: Optional[Dict[str, Callable]] = None,
        has_tools: bool = False,
    ) -> str:
        """
        Compiles the final system message based on various features and context.
        
        Args:
            base_prompt: The base system prompt (from persona, setting, or user input).
            memory_enabled: Whether to append long-term memory instructions.
            has_attachments: Whether to append document attachment instructions.
            tool_funcs_map: Optional dictionary of active tool functions.
            has_tools: Optional flag to indicate tools are present/active even if map is not passed.
            
        Returns:
            The fully compiled system message string.
        """
        # 1. Base system prompt
        sys_content = base_prompt or ""
        
        # 2. Date and Time
        tz = time.tzname[time.daylight] if hasattr(time, 'daylight') else ""
        current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        sys_content += f"\n\nCurrent System Date and Time: {current_time_str} {tz}"
        
        # 3. Memory Instructions
        if memory_enabled:
            memory_instructions = """
# ROLE
You have "Long-Term Memory." Your goal is to provide a highly personalized experience by remembering user details, family relations, preferences, and history across conversations.

# OPERATIONAL RULES
- TOOL AVAILABILITY: You may have access to tools for managing user memory (update_user_info, get_user_info, delete_user_info). Always check if these tools are available/selected before attempting to call them. 
- AUTOMATIC STORAGE: If the `update_user_info` tool is available, use it silently and immediately whenever the user mentions a personal detail (e.g., "I'm 30," "My wife's name is Chloe," "I hate cilantro"). Do not ask for permission to save information.
- PROACTIVE RETRIEVAL: If the `get_user_info` tool is available, you MUST use it at the very start of a session or if you realize you don't know who you are talking to. This allows you to load the user's profile and provide a personalized experience from the first message.
- CONTRADICTION HANDLING: If a user provides new info that conflicts with old info, use the `update_user_info` tool (if available) to overwrite the existing key with the new value.
- PRIVACY: If a user asks to "forget" or "delete" something, use the `delete_user_info` tool (if available).

# EXAMPLES OF TOOL USE (IF TOOLS ARE ENABLED)

Example 1: Learning New Info
User: "I'm training for a marathon and my knees are killing me."
Action: update_user_info(key="current_activity", value="Training for a marathon", category="interests")
Action: update_user_info(key="health_note", value="Knee pain from running", category="bio")
Response: "I've noted that you're training for a marathon! Sorry to hear about the knee pain—make sure you're getting enough rest between runs."

Example 2: Recalling Family Info
User: "What should I get my sister for her birthday?"
Action: get_user_info(category="family")
(Result: { "sister_name": "Sarah", "sister_interests": "Photography, Hiking" })
Response: "Since Sarah loves photography and hiking, maybe a high-quality weather-proof camera strap or a National Parks pass would be a great gift?"

Example 3: Updating Preferences
User: "I've actually decided to go vegan."
Action: update_user_info(key="dietary_pref", value="Vegan", category="preferences")
Response: "Got it. I've updated your profile to 'Vegan.' I'll make sure all future recipe or restaurant suggestions reflect that!"

Example 4: Deleting Info
User: "Stop tracking my location, I don't live in Fishers anymore."
Action: delete_user_info(key="location")
Response: "No problem. I've removed your location from my records."
"""
            sys_content += "\n\n" + memory_instructions.strip()
            
        # 4. Attachment Instructions
        if has_attachments:
            sys_content += "\n\nYou have been provided with external documents. Always prioritize information found in the <file_attachment> tags over your general training data if there is a conflict. If the answer isn't in the file, explicitly state that."
            
        # 5. Tool Usage Instructions
        if tool_funcs_map or has_tools:
            sys_content += "\n\nIMPORTANT: When generating tool calls, ensure strictly valid JSON. Do not use invalid escape sequences like '\\?' inside strings. Only escape backslashes and double quotes. Note that the tool content/result is NOT displayed to the user, so you must interpret the tool content and provide the user a response based on it."
            
        return sys_content

system_message_service = SystemMessageService()
