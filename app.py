import sqlite3
import os
import streamlit as st
import main
import database

SECRET_PASSCODE = os.environ.get("SECRET_SCAN_PASSCODE", "admin123")  # Fallback to admin123 for local testing

# Configure Streamlit page settings
st.set_page_config(
    page_title="Suomen lakiseuranta (Finnish Legislative Tracker)",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for premium fonts and cards layout
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    font-family: 'Outfit', sans-serif;
}
h1, h2, h3, h4, h5, h6 {
    font-family: 'Outfit', sans-serif;
    font-weight: 700;
    color: #1E293B;
}
.card-header {
    font-size: 1.1rem;
    font-weight: 600;
    color: #0F172A;
    margin-bottom: 0.5rem;
}
.status-badge {
    padding: 0.2rem 0.6rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    display: inline-block;
    margin-bottom: 0.5rem;
}
.status-enacted {
    background-color: #DEF7EC;
    color: #03543F;
    border: 1px solid #BCF0DA;
}
.status-proposal {
    background-color: #E1EFFE;
    color: #1E429F;
    border: 1px solid #C3DDFD;
}
.status-other {
    background-color: #F3F4F6;
    color: #374151;
    border: 1px solid #E5E7EB;
}
.metric-text {
    font-size: 0.85rem;
    color: #64748B;
}
.stAppDeployButton {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

def load_legislative_data():
    """Query local SQLite database and return tracked updates."""
    # Ensure database exists/is initialized
    database.initialize_db()
    
    conn = sqlite3.connect(database.DEFAULT_DB_PATH)
    try:
        cursor = conn.cursor()
        query = """
        SELECT tl.matter_id, tl.title, tl.last_modified_date, tl.status, s.summary_text, s.ground_truth_url
        FROM tracked_laws tl
        LEFT JOIN summaries s ON tl.matter_id = s.matter_id
        ORDER BY tl.last_modified_date DESC, tl.processed_at DESC;
        """
        cursor.execute(query)
        return cursor.fetchall()
    except sqlite3.Error as e:
        st.error(f"Database error: {e}")
        return []
    finally:
        conn.close()

# Sidebar: Actions and Launch Guide
with st.sidebar:
    st.image("https://images.unsplash.com/photo-1589829545856-d10d557cf95f?auto=format&fit=crop&q=80&w=300", caption="Suomen lainsäädäntö", use_container_width=True)
    st.title("Hallintapaneeli")
    
    # Check for GEMINI_API_KEY
    has_api_key = "GEMINI_API_KEY" in os.environ and bool(os.environ["GEMINI_API_KEY"].strip())
    if not has_api_key:
        st.warning("⚠️ **GEMINI_API_KEY** ei ole asetettu. Summarization will fallback to error text.")
    else:
        st.success("🔑 Gemini API avain ladattu.")
        
    st.subheader("Toiminnot (Actions)")
    
    # Kaggle Judge Callout
    st.info("👋 **Welcome Kaggle Judges!** The dashboard below is pre-populated. To trigger a live API sync and see the AI agent fetch and summarize new laws in real-time, please enter the competition passcode.")
    
    # Password Input Field
    user_passcode = st.text_input("Enter Passcode to Scan", type="password")
    
    # Scanner trigger button
    if st.button("🔄 Skannaa uudet päivitykset", use_container_width=True, type="primary"):
        if user_passcode == SECRET_PASSCODE or user_passcode == "KaggleDemo2026":
            st.success("Passcode verified! Starting live legal scan...")
            with st.spinner("Haetaan eduskunnan aineistoja ja päivitetään tietokantaa..."):
                try:
                    main.run_tracker(limit=10)
                    st.success("Tietokanta päivitetty!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Virhe skannauksessa: {e}")
        else:
            st.error("Invalid passcode. Live scanning is restricted to protect API quotas. Use the passcode displayed above to test.")
                
    st.divider()
    st.subheader("Käynnistysohjeet (Launch Instructions)")
    st.markdown("""
    Käynnistä tämä sovellus palvelimella suorittamalla terminalissa:
    ```bash
    .venv/bin/streamlit run app.py
    ```
    Voit sulkea palvelimen painamalla `Ctrl + C`.
    """)

# Main Content
st.title("⚖️ Suomen lakiseuranta")
st.caption("Automaattinen eduskunnan valtiopäiväasioiden seuranta (Finnish Legislative Tracker)")

# Load data
laws = load_legislative_data()

st.metric(label="Seurattavia säädöksiä yhteensä (Total Tracked Matters)", value=len(laws))

if not laws:
    st.info("Tietokanta on tyhjä. Klikkaa sivupalkista **Skannaa uudet päivitykset** aloittaaksesi seurannan.")
else:
    st.write("---")
    # Display each legislative matter
    for matter_id, title, last_modified_date, status, summary, ground_truth_url in laws:
        # Render a clean border container for each card
        with st.container(border=True):
            col1, col2 = st.columns([4, 1])
            
            with col1:
                # Format header
                st.markdown(f"#### {title}")
                
                # Determine status badge
                status_class = "status-other"
                status_label = status
                if status == "ENACTED":
                    status_class = "status-enacted"
                    status_label = "Vahvistettu (Enacted)"
                elif "GovernmentProposal" in str(status):
                    status_class = "status-proposal"
                    status_label = "Hallituksen esitys (HE)"
                    
                st.markdown(
                    f'<span class="status-badge {status_class}">{status_label}</span>'
                    f'<span class="metric-text" style="margin-left: 15px;">🗓️ Päivitetty: {last_modified_date} | Tunnus: {matter_id}</span>',
                    unsafe_allow_html=True
                )
                
                # Summary content
                if summary:
                    st.markdown("**Muutosten tiivistelmä (Summary of Changes):**")
                    st.markdown(summary)
                else:
                    st.info("Tälle esitykselle ei ole tekoälyn tiivistelmää tallennettuna.")
                    
            with col2:
                # Source URL action button
                if ground_truth_url:
                    st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True)  # spacing
                    st.link_button("🔗 Avaa virallinen lähde", ground_truth_url, use_container_width=True)
                else:
                    st.caption("Ei virallista linkkiä saatavilla.")
