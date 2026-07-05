import logging
import sys
import datetime
from urllib.parse import quote
import api_connector
import database
import parser
import llm_service

# Configure centralized logging to console and agent.log file
log_format = "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Clear existing handlers
root_logger.handlers = []

# File Handler
file_handler = logging.FileHandler("agent.log", encoding="utf-8")
file_handler.setFormatter(logging.Formatter(log_format))
root_logger.addHandler(file_handler)

# Console/Stream Handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter(log_format))
root_logger.addHandler(console_handler)

logger = logging.getLogger("main_orchestrator")

def construct_ground_truth_url(matter, used_finlex_xml=False):
    """Deterministically construct verified URLs as per GUARDRAILS.md.
    
    Args:
        matter (dict): The legislative matter dictionary.
        used_finlex_xml (bool): True if Finlex XML was successfully processed.
        
    Returns:
        str: The constructed URL string.
    """
    finlex_id = matter.get("finlex_statute_id")
    if finlex_id and used_finlex_xml:
        try:
            year, number = api_connector.parse_statute_id(finlex_id)
            # Standard Finlex original statute URL format
            return f"https://www.finlex.fi/fi/laki/alkup/{year}/{number}"
        except Exception as e:
            logger.warning("Error parsing statute ID %s for Finlex URL: %s. Using default string.", finlex_id, e)
            return f"https://www.finlex.fi/fi/laki/alkup/{finlex_id}"
            
    # For proposals/pre-ratified or if Finlex XML failed, construct a permanent link directly to Eduskunta
    tunnus = matter.get("identifier", "")
    if tunnus:
        # Safe percent-encoding for spaces (%20) and forward slashes (%2F) using safe=''
        encoded_id = quote(tunnus.strip(), safe='')
        return f"https://www.eduskunta.fi/asiat-ja-aanestykset/valtiopaivaasiat/{encoded_id}"
        
    # Final fallback using row ID
    return f"https://avoindata.eduskunta.fi/api/v1/tables/VaskiData/rows?columnName=Id&columnValue={matter.get('id')}"

def run_tracker(limit=50):
    """Execute the main legislative tracking loop."""
    logger.info("Starting Finnish Legislative Tracker...")
    
    # 1. Initialize the SQLite database
    database.initialize_db()
    
    # 2. Fetch recent legislative matters
    logger.info("Fetching recent legislative matters (limit=%d)...", limit)
    matters = api_connector.fetch_recent_matters(limit=limit)
    if not matters:
        logger.info("No matters fetched or Eduskunta API is unavailable.")
        return
        
    logger.info("Fetched %d recent matters. Processing new ones...", len(matters))
    new_records_count = 0
    
    # 3. Process each legislative matter
    for idx, matter in enumerate(matters, 1):
        matter_id = str(matter.get("id"))
        tunnus = matter.get("identifier", "Unknown ID")
        title = matter.get("title", "No Title")
        created_date = matter.get("created", "Unknown Date")
        message_type = matter.get("message_type", "Unknown Type")
        finlex_id = matter.get("finlex_statute_id")
        
        # Check if already tracked
        if database.is_law_tracked(matter_id):
            logger.debug("Matter ID %s (%s) is already tracked. Skipping.", matter_id, tunnus)
            continue
            
        logger.info("[%d/%d] Processing new matter: %s - %s", idx, len(matters), tunnus, title[:50])
        new_records_count += 1
        
        # 4. Fetch the raw XML (with fallback to Eduskunta Vaski XML)
        xml_content = None
        used_finlex_xml = False
        if finlex_id:
            logger.info("  -> Querying Finlex for enacted statute: %s...", finlex_id)
            xml_content = api_connector.fetch_finlex_xml(finlex_id)
            if xml_content:
                used_finlex_xml = True
            
        if not xml_content:
            logger.info("Finlex XML missing - using Eduskunta metadata")
            xml_content = matter.get("xml_content")
            
        if not xml_content:
            logger.error("  [-] Error: No XML content found for matter %s. Skipping.", tunnus)
            continue
            
        # 5. Parse out the plain-text legislative body
        clean_text = parser.extract_legal_text(xml_content)
        if not clean_text:
            logger.error("  [-] Error: Extracted legal text is empty for %s. Skipping.", tunnus)
            continue
            
        # 6. Pass clean text to LLM service for summarization
        logger.info("  -> Requesting AI summarization of changes...")
        summary = llm_service.summarize_law_changes(clean_text)
        
        # Fallback summary if LLM call fails
        if not summary or summary.startswith("Error"):
            logger.warning("  [!] LLM summarization failed. Using high-level summary of intent instead of skipping.")
            summary = (
                f"### Esityksen tarkoitus (Proposal Intent)\n"
                f"Tämä säädösmuutos koskee seuraavaa asiaa: **{title}**.\n\n"
                f"Eduskunnan aineiston mukaan kyseessä on säädöksen valmisteluasiakirja (HE), "
                f"jonka tavoitteena on edistää asiaan liittyvää lainsäädäntöä.\n\n"
                f"*Alkuperäinen kuvaus*:\n{clean_text[:500]}..."
            )
        
        # 7. Construct ground-truth URL deterministically
        source_url = construct_ground_truth_url(matter, used_finlex_xml=used_finlex_xml)
        
        # 8. Print/Log final Markdown payload and append to file
        print("\n" + "=" * 80)
        print(f"### [{tunnus}] {title}")
        print(f"- **Matter ID**: {matter_id}")
        print(f"- **Created Date**: {created_date}")
        print(f"- **Summary of Changes**:")
        print(summary)
        print(f"- **Source Link**: [Official Legislative Source]({source_url})")
        print("=" * 80 + "\n")
        
        processed_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        md_entry = (
            f"### [{tunnus}] {title}\n"
            f"- **Matter ID**: {matter_id}\n"
            f"- **Created Date**: {created_date}\n"
            f"- **Processed At**: {processed_at}\n"
            f"- **Summary of Changes**:\n{summary}\n"
            f"- **Source Link**: [Official Legislative Source]({source_url})\n\n"
            f"---\n\n"
        )
        try:
            with open("legal_updates.md", "a", encoding="utf-8") as f:
                f.write(md_entry)
            logger.info("  -> Saved summary to legal_updates.md")
        except Exception as e:
            logger.error("  [-] Failed to write to legal_updates.md: %s", e)
        
        # 9. Update database so it is not processed again
        try:
            database.insert_or_update_law(
                matter_id=matter_id,
                title=title,
                last_modified_date=created_date,
                status=message_type,
                finlex_statute_id=finlex_id
            )
            database.insert_or_update_summary(
                matter_id=matter_id,
                title=title,
                summary_text=summary,
                ground_truth_url=source_url
            )
        except Exception as e:
            logger.error("  [-] Failed to update database for %s: %s", tunnus, e)
            
    logger.info("Legislative tracking cycle completed. Processed %d new matters.", new_records_count)

if __name__ == "__main__":
    # Check if a different limit is requested via CLI argument
    scan_limit = 50
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        scan_limit = int(sys.argv[1])
        
    run_tracker(limit=scan_limit)
