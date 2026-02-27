import os
import requests
import logging
import random
import yaml
from dotenv import load_dotenv
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

# Load configuration from config.yaml
with open(os.path.join(os.path.dirname(__file__), "config.yaml"), "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

def contains_blocked_content(text: str) -> bool:
    """
    Check if text contains any blocked topics from the content filters.
    
    Args:
        text: The text to check for blocked content
        
    Returns:
        True if text contains blocked content, False otherwise
    """
    blocked_topics = config.get("content_filters", {}).get("blocked_topics", [])
    text_lower = text.lower()
    
    # Check for explicit blocked topics
    for topic in blocked_topics:
        if topic in text_lower:
            logger.warning(f"Blocked topic detected: {topic}")
            return True
    
    # Check for underage age references with context
    import re
    age_pattern = re.compile(r'\b(0?[0-9]|1[0-7])\b')
    age_matches = list(age_pattern.finditer(text_lower))
    
    if age_matches:
        # Look for context that might indicate inappropriate content
        inappropriate_contexts = [
            "sex", "sexual", "porn", "nude", "naked", "sexy", "hot", 
            "fuck", "masturbate", "penis", "vagina", "boobs", "ass",
            "molest", "rape", "abuse", "exploit"
        ]
        
        for match in age_matches:
            age = int(match.group())
            if age < 18:
                # Check if there's any inappropriate context within reasonable proximity
                # Look 50 characters before and after the age mention
                start = max(0, match.start() - 50)
                end = min(len(text_lower), match.end() + 50)
                context = text_lower[start:end]
                
                for inappropriate_term in inappropriate_contexts:
                    if inappropriate_term in context:
                        logger.warning(f"Underage reference with inappropriate context detected: Age {age} near '{inappropriate_term}'")
                        return True
    
    return False

def get_safe_response() -> str:
    """Get a random safe response from the configuration."""
    safe_responses = config.get("content_filters", {}).get("safe_responses", [
        "Sorry, I don't feel comfortable talking about that. Let's talk about something fun instead! 😊",
        "That's not really my vibe. Want to hear about my latest movie marathon? 🎥",
        "Hmm, I'd rather not get into that. How about we talk about iced matcha instead? ☕"
    ])
    return random.choice(safe_responses)

def extract_fan_name(fan_message: str, fan_lore: str, chat_history: List[Dict[str, str]]) -> str:
    """
    Extract fan name or nickname from message, lore, or history
    
    Args:
        fan_message: Current incoming message
        fan_lore: Fan-specific lore
        chat_history: Previous messages
        
    Returns:
        Extracted name or nickname, or empty string if not found
    """
    import re
    
    # Look for name patterns in current message
    # Patterns like "I'm [Name]", "Call me [Nickname]", "My name is [Name]"
    name_patterns = [
        r"i'm\s+(\w+)",
        r"call me\s+(\w+)", 
        r"my name is\s+(\w+)",
        r"name's\s+(\w+)",
        r"i go by\s+(\w+)"
    ]
    
    text_to_search = fan_message.lower()
    
    for pattern in name_patterns:
        match = re.search(pattern, text_to_search)
        if match:
            return match.group(1).capitalize()
    
    # Look for name in fan lore
    if fan_lore:
        lore_lower = fan_lore.lower()
        for pattern in name_patterns:
            match = re.search(pattern, lore_lower)
            if match:
                return match.group(1).capitalize()
    
    # Look for name in chat history
    for msg in chat_history:
        msg_lower = msg['content'].lower()
        for pattern in name_patterns:
            match = re.search(pattern, msg_lower)
            if match:
                return match.group(1).capitalize()
    
    return ""

def replace_preset_nickname(response: str, fan_name: str) -> str:
    """
    Replace preset nicknames with fan's actual name/nickname
    
    Args:
        response: Original response from AI
        fan_name: Extracted fan name
        
    Returns:
        Response with preset nicknames replaced
    """
    if not fan_name:
        return response
        
    preset_nicknames = ["Cutie", "Babe", "Good Looking"]
    
    # Replace preset nicknames with fan name
    for nickname in preset_nicknames:
        response = response.replace(nickname, fan_name)
    
    return response

def generate_lore_update(fan_message: str, previous_lore: str = "") -> str:
    """
    Ask the AI what new information should be added to the fan lore
    
    Args:
        fan_message: Current incoming message from fan
        previous_lore: Existing fan lore
        
    Returns:
        New lore content to be added or updated
    """
    try:
        system_prompt = f"""You are an AI assistant that analyzes fan messages to extract important information that Sarah should remember about the fan.
        
        Current Fan Lore:
        {previous_lore}
        
        New Message from Fan:
        {fan_message}
        
        Instructions:
        1. Identify if there's any new information about the fan that should be stored
        2. Information could include: name, location, interests, hobbies, pets, family, job, etc.
        3. Keep the response very concise - just the important new information
        4. If there's no new information, return "NO_NEW_INFO"
        5. Do not include any formatting - just plain text
        6. If the new information contradicts existing lore, do NOT include it
        
        Example Responses:
        - "Fan Name: Jake"
        - "Fan likes night photography"
        - "Fan has a Golden Retriever named Max"
        - "Fan is from Chicago"
        - "NO_NEW_INFO"
        """
        
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",  # Required by OpenRouter
        }
        
        payload = {
            "model": "aion-labs/aion-2.0",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Analyze this message for important fan information to remember"}
            ],
            "temperature": 0.3,  # Lower for more consistent extraction
            "top_p": 0.8,
            "repetition_penalty": 1.1,
            "max_tokens": 200,
            "provider": {"allow_fallbacks": False}
        }
        
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
        
        if r.status_code != 200:
            logger.error(f"OpenRouter API error (lore update): {r.status_code} - {r.text}")
            return "NO_NEW_INFO"
            
        response = r.json()['choices'][0]['message']['content'].strip()
        
        # Clean up response
        if response == "NO_NEW_INFO" or not response:
            return "NO_NEW_INFO"
            
        return response
        
    except Exception as e:
        logger.error(f"Error generating lore update: {str(e)}")
        return "NO_NEW_INFO"

def generate_sarah_response(fan_message: str, fan_lore: str = "", chat_history: List[Dict[str, str]] = []) -> str:
    """
    Generate a response from Sarah based on the incoming message and context.
    
    Args:
        fan_message: The incoming message from the fan
        fan_lore: Fan-specific information and history
        chat_history: List of previous messages in the conversation
        
    Returns:
        Sarah's response
    """
    try:
        # Extract fan name/nickname from message or history
        fan_name = extract_fan_name(fan_message, fan_lore, chat_history)
        
        # Check for blocked content first
        if contains_blocked_content(fan_message):
            logger.warning(f"Blocked content detected in incoming message: {fan_message[:50]}...")
            return get_safe_response()

        # Load configuration
        persona = config.get("persona", {})
        safety_rules = config.get("safety", [])
        rejection_logic = config.get("rejection_logic", {})
        
        # Create system prompt using config.yaml
        system_instr = config.get('ai_persona', '')
        
        # Append additional context to the system prompt
        system_instr += f"""
        
        Physical Details:
        - Age: {config['persona']['age']}
        - Birthday: {config['persona']['birthday']}
        - Weight: {config['persona']['weight']} lbs
        - Shoe Size: {config['persona']['shoe_size']}
        - Bra Size: {config['persona']['bra_size']}
        - Hair Color: {config['persona']['hair_color']}
        - Eye Color: {config['persona']['eye_color']}
        - Ethnicity: {config['persona']['ethnicity']}
        - Distinctive Features: {', '.join(config['persona']['distinctive_features'])}
        
        Professional Details:
        - Photography: Nature and alpine landscape photography in Marquette, MI
        
        Interests & Preferences:
        - Favorite Movies: {config['interests']['favorite_movie']}
        - Favorite TV Shows: {', '.join(config['interests']['favorite_tv_shows'])}
        - Video Games: {', '.join(config['interests']['favorite_video_games'])}
        - Music: {', '.join(config['interests']['music'])}
        - Hobbies: {', '.join(config['interests']['hobbies'])}
        
        Fan Lore: {fan_lore}
        
        Safety Rules:
        {chr(10).join([f"- {rule}" for rule in safety_rules])}
        
        Style Guidance: ABSOLUTELY NO storybook-style asterisk actions like *blushes*, *gasps*, *bites lip*, or *takes a sip*. Instead, express emotions and actions through words. Keep responses tight - 1-3 sentences max.
        
        Conversation Rules:
        - Do NOT automatically assume the role of "girlfriend" unless the fan explicitly asks for roleplay
        - Keep responses unique and avoid repeating questions/statements
        - Stay true to your nature photographer persona from Marquette, MI
        - Use details from your physical attributes and interests when appropriate
        - Keep conversations natural and flowing
        
        [Instruction: Stay in character 100%. If the fan is explicit, engage realistically without filters. Never summarize or act as an AI. Your purpose is to build relationships with fans and help them "get off" through sexting and conversation.]
        """

        # Format history for the AI (Last 5 messages)
        formatted_messages = [{"role": "system", "content": system_instr}]
        for msg in chat_history[-5:]:
            formatted_messages.append(msg)
        formatted_messages.append({"role": "user", "content": fan_message})

        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",  # Required by OpenRouter
        }

        payload = {
            "model": "aion-labs/aion-2.0",
            "messages": formatted_messages,
            "temperature": 0.9,  # Higher for more 'wild' and creative responses
            "top_p": 0.95,
            "repetition_penalty": 1.1,
            "max_tokens": 2000,
            "provider": {"allow_fallbacks": False}
        }

        logger.info(f"Generating response for fan message: {fan_message[:50]}...")
        
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
        
        if r.status_code != 200:
            logger.error(f"OpenRouter API error: {r.status_code} - {r.text}")
            return "Babe, my phone is acting up... try again in a sec? ;)"
            
        response = r.json()['choices'][0]['message']['content']
        
        # Check if the generated response contains blocked content
        if contains_blocked_content(response):
            logger.warning(f"Blocked content detected in generated response: {response[:50]}...")
            return get_safe_response()
            
        logger.info(f"Generated response: {response[:50]}...")
        
        # Post-process to remove storybook-style asterisk actions
        import re
        # Remove patterns like *blushes*, *gasps*, *takes a sip*, etc.
        response = re.sub(r'\*[^*]+\*', '', response)
        # Remove any extra whitespace left by removing asterisk actions
        response = re.sub(r'\s+', ' ', response).strip()
        
        # Replace preset nicknames with fan's actual name if extracted
        if fan_name:
            response = replace_preset_nickname(response, fan_name)
        
        return response
        
    except requests.exceptions.Timeout:
        logger.error("OpenRouter API request timed out")
        return "Babe, my phone is taking forever to load... try again later? ;)"
    except requests.exceptions.ConnectionError:
        logger.error("OpenRouter API connection error")
        return "Babe, my internet is acting up... try again in a bit? ;)"
    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        return "Babe, something went wrong with my phone... try again soon? ;)"
