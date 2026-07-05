import sys
import sqlite3
from api_connector import fetch_recent_matters, fetch_finlex_xml
from database import initialize_db, is_law_tracked, insert_or_update_law, DEFAULT_DB_PATH
from parser import extract_legal_text
from llm_service import summarize_law_changes

def print_db_contents(db_path=DEFAULT_DB_PATH):
    """Debug helper to print all rows currently in the tracked_laws table."""
    print(f"\n[*] Contents of tracked_laws table in {db_path}:")
    print("-" * 100)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT matter_id, title, last_modified_date, finlex_statute_id, status, processed_at FROM tracked_laws;")
        rows = cursor.fetchall()
        for r in rows:
            print(f"ID:           {r[0]}")
            print(f"Title:        {r[1][:80]}...")
            print(f"Last Mod:     {r[2]}")
            print(f"Finlex ID:    {r[3]}")
            print(f"Status:       {r[4]}")
            print(f"Processed At: {r[5]}")
            print("-" * 100)
    except sqlite3.Error as e:
        print(f"[-] Error reading database contents: {e}", file=sys.stderr)
    finally:
        conn.close()

def main():
    print("=== Testing Legislative Tracker Integration ===")
    
    # 1. Initialize SQLite Database
    print("\n[*] Initializing local database...")
    try:
        initialize_db()
    except Exception as e:
        print(f"[-] Database initialization failed: {e}", file=sys.stderr)
        sys.exit(1)
        
    # 2. Test fetching 2 proposals from Eduskunta and inserting them
    print("\n[*] Fetching recent matters to store in database...")
    try:
        proposals = fetch_recent_matters(limit=2)
        print(f"[+] Retrieved {len(proposals)} proposals. Saving to database...")
        
        for prop in proposals:
            matter_id = str(prop.get("id"))
            title = prop.get("title")
            last_mod = prop.get("created")
            status = prop.get("message_type")
            
            # Check if tracked BEFORE inserting
            tracked_before = is_law_tracked(matter_id)
            print(f"  -> Matter {matter_id} tracked before insert? {tracked_before}")
            
            # Insert/Update
            insert_or_update_law(matter_id, title, last_mod, status)
            
            # Check if tracked AFTER inserting
            tracked_after = is_law_tracked(matter_id)
            print(f"  -> Matter {matter_id} tracked after insert? {tracked_after}")
            
    except Exception as e:
        print(f"[-] Failed during matter insertion test: {e}", file=sys.stderr)

    # 3. Test updating an existing law (e.g. adding a Finlex ID)
    if proposals:
        target_prop = proposals[0]
        target_id = str(target_prop.get("id"))
        print(f"\n[*] Testing update: Adding a Finlex ID to matter {target_id}...")
        try:
            insert_or_update_law(
                matter_id=target_id,
                title=target_prop.get("title"),
                last_modified_date=target_prop.get("created"),
                status="ENACTED",
                finlex_statute_id="999/2026"
            )
        except Exception as e:
            print(f"[-] Failed during matter update test: {e}", file=sys.stderr)
            
    # Print contents of the database
    print_db_contents()

    # 4. Test fetching a statute from Finlex
    test_statute = "585/2023"
    print(f"\n[*] Verifying Finlex connector: fetching statute {test_statute}...")
    xml_text = None
    try:
        xml_text = fetch_finlex_xml(test_statute)
        if xml_text:
            print(f"[+] Successfully fetched Finlex XML for statute {test_statute} ({len(xml_text)} bytes).")
        else:
            print(f"[-] Failed to fetch statute {test_statute} from Finlex.")
    except Exception as e:
        print(f"[-] Finlex check failed: {e}", file=sys.stderr)

    # 5. Test parsing the fetched statute XML
    plain_text = None
    if xml_text:
        print(f"\n[*] Testing parser.py: extracting text from statute {test_statute}...")
        try:
            plain_text = extract_legal_text(xml_text)
            print(f"[+] Successfully parsed legal text ({len(plain_text)} characters).")
        except Exception as e:
            print(f"[-] Text extraction failed: {e}", file=sys.stderr)

    # 6. Test LLM Summarization Service
    if plain_text:
        print(f"\n[*] Testing llm_service.py: summarizing changes in statute {test_statute}...")
        try:
            summary = summarize_law_changes(plain_text)
            print("[+] Summarization response received:")
            print("=" * 70)
            print(summary)
            print("=" * 70)
        except Exception as e:
            print(f"[-] Summarization test failed: {e}", file=sys.stderr)

    # 7. Test parser robustness with empty/malformed inputs
    print("\n[*] Testing parser robustness with empty and invalid inputs...")
    try:
        res_none = extract_legal_text(None)
        res_empty = extract_legal_text("")
        res_invalid = extract_legal_text("<invalid><xml>not Akoma Ntoso")
        
        print(f"  -> Parsing None:    '{res_none}'")
        print(f"  -> Parsing Empty:   '{res_empty}'")
        print(f"  -> Parsing Invalid: '{res_invalid}'")
        print("[+] Parser handles invalid inputs gracefully!")
    except Exception as e:
        print(f"[-] Parser crashed on invalid input: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
