import logging
import re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def extract_legal_text(xml_content):
    """Extract clean, plain-text legislative content from Akoma Ntoso XML.
    
    Args:
        xml_content (str): The raw XML content of a statute or parliamentary document.
        
    Returns:
        str: Clean, plain-text representation of the legislative document.
    """
    if not xml_content or not isinstance(xml_content, str):
        logger.warning("No XML content provided or invalid type.")
        return ""
        
    try:
        # Parse XML using lxml-xml parser which handles XML namespaces and elements correctly
        soup = BeautifulSoup(xml_content, "lxml-xml")
    except Exception as e:
        logger.error("Failed to parse XML with BeautifulSoup: %s", e, exc_info=True)
        return ""

    # Check if this is an Eduskunta metadata payload by searching local names
    def find_by_local_name(parent, local_names):
        for tag in parent.find_all():
            local_name = tag.name.split(":")[-1]
            if local_name in local_names:
                return tag
        return None

    sisalto_kuvaus = find_by_local_name(soup, ["SisaltoKuvaus", "AsiaKuvaus"])
    if sisalto_kuvaus:
        texts = list(sisalto_kuvaus.stripped_strings)
        if texts:
            logger.info("Eduskunta metadata found - using SisaltoKuvaus (summary) element")
            return " ".join(texts).strip()

    nimeke_teksti = find_by_local_name(soup, ["NimekeTeksti", "OtsikkoTeksti"])
    if nimeke_teksti:
        texts = list(nimeke_teksti.stripped_strings)
        if texts:
            logger.info("Eduskunta metadata found - using NimekeTeksti (title) element")
            return " ".join(texts).strip()

    # Find the main body of the document to exclude meta/technical headers
    # Akoma Ntoso uses <body> or <mainBody>
    body_elem = soup.find(["body", "mainBody"])
    
    if not body_elem:
        # If no body element was found, we parse the whole document but strip out <meta> first
        logger.warning("No <body> or <mainBody> element found. Parsing full document after removing <meta>.")
        meta_elem = soup.find(["meta", "identification"])
        if meta_elem:
            meta_elem.decompose()
        body_elem = soup

    def format_element(elem):
        """Recursively formats elements into structured plain text."""
        if not elem:
            return ""
            
        tag_name = elem.name
        
        # Reconstruct child elements
        text_parts = []
        for child in elem.children:
            if child.name is None:
                # This is a NavigableString (text node)
                text_val = child.string
                if text_val:
                    text_parts.append(text_val)
            else:
                # Recursive call for element node
                formatted_child = format_element(child)
                if formatted_child:
                    text_parts.append(formatted_child)

        # Merge text parts
        raw_text = "".join(text_parts).strip()
        if not raw_text:
            return ""

        # Format block-level elements
        if tag_name == "num":
            # Numbers (e.g. "1 §") should be followed by a space
            return f"{raw_text} "
        elif tag_name == "heading":
            # Headings should be followed by a newline
            return f"{raw_text}\n"
        elif tag_name == "p":
            # Paragraphs should be followed by a newline
            return f"{raw_text}\n"
        elif tag_name in ("section", "article", "paragraph", "chapter", "sectionTitel"):
            # Major divisions should be clearly separated by newlines
            return f"\n{raw_text}\n"
        elif tag_name in ("list", "blockList"):
            # Lists get double spacing
            return f"\n{raw_text}\n"
        
        return raw_text

    # Extract and format
    try:
        plain_text = format_element(body_elem)
        
        # Clean up whitespace and consecutive empty lines
        plain_text = re.sub(r'[ \t]+', ' ', plain_text)  # collapse spaces/tabs
        plain_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', plain_text)  # collapse multiple newlines into max 2
        return plain_text.strip()
    except Exception as e:
        logger.error("Error formatting Akoma Ntoso elements: %s", e, exc_info=True)
        # Final fallback: return standard text extraction
        return body_elem.get_text(separator=" ").strip()
