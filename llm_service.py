import os
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables (from .env in current directory or parent)
load_dotenv()

def summarize_law_changes(parsed_text):
    """Summarize legal changes from plain-text legislation using Gemini.
    
    Args:
        parsed_text (str): The plain-text of the legislative document.
        
    Returns:
        str: Objective markdown bullet points summarizing the changes, or an error message.
    """
    if not parsed_text or not parsed_text.strip():
        logger.warning("Empty input text provided for summarization.")
        return "No text available to summarize."

    # Validate that we have an API key configured (or Vertex credentials via default chain)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY environment variable is not set.")
        return (
            "Error: GEMINI_API_KEY environment variable is not configured.\n"
            "Please create a '.env' file in the root directory containing 'GEMINI_API_KEY=your_api_key_here'."
        )

    # Strict system instructions as per requirements and GUARDRAILS.md
    system_instruction = (
        "You are a precise legal analyst for the Finnish legislative system.\n\n"
        "Summarize the provided legal text into clear, objective markdown bullet points highlighting "
        "exactly what changed (e.g., changes to deadlines, fees, or compliance requirements).\n\n"
        "CRITICAL: Rely only on the facts explicitly stated in the input text. Do not extrapolate, "
        "assume future intent, or include external legal knowledge.\n\n"
        "DO NOT attempt to generate, guess, or output any URLs or source links in your response. "
        "The application layer handles links separately."
    )

    try:
        # Initialize Google GenAI client (it picks up GEMINI_API_KEY from environment)
        client = genai.Client()
        
        logger.info("Sending text to Gemini (gemini-2.0-flash) for summarization...")
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=parsed_text,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.0,  # Zero temperature for deterministic, factual reporting
            )
        )
        
        if not response.text:
            return "No summary generated."
            
        return response.text.strip()
        
    except genai.errors.APIError as ae:
        logger.error("Gemini API Error: %s", ae)
        return f"Error: Gemini API communication failed: {ae.message}"
    except Exception as e:
        logger.error("Unexpected error during summarization: %s", e)
        return f"Error: Summarization failed due to an unexpected error: {str(e)}"
