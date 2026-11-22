import streamlit as st
from agent import run_professor_agent
from usage_limits import check_and_consume, remaining_this_session, redact

st.set_page_config(page_title="Professor Hunter", page_icon="🎓", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    /* Hide default elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    [data-testid="stExpandSidebarButton"] {visibility: visible;}

    /* Dark background */
    .stApp {
        background-color: #0a0a0f !important;
        color: #e2e8f0;
    }
    
    /* Glowing orb */
    .glowing-orb {
        width: 150px;
        height: 150px;
        background: linear-gradient(135deg, #7c3aed, #a855f7);
        border-radius: 50%;
        margin: 0 auto 30px auto;
        box-shadow: 0 0 80px 40px rgba(168, 85, 247, 0.4), 0 0 150px 80px rgba(124, 58, 237, 0.2);
    }
    
    /* Header styling */
    .title-container {
        text-align: center;
        margin-bottom: 2rem;
    }
    .main-title {
        font-size: 3.5rem;
        font-weight: 800;
        background: linear-gradient(to right, #a855f7, #7c3aed);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    .subtitle {
        font-size: 1.2rem;
        color: #94a3b8;
    }
    
    /* Primary button (Search) */
    div[data-testid="stButton"] > button[kind="primary"] {
        background: linear-gradient(135deg, #7c3aed, #a855f7) !important;
        color: white !important;
        border: none !important;
        padding: 0.5rem 2rem !important;
        border-radius: 8px !important;
        font-weight: bold !important;
        transition: all 0.3s ease !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        box-shadow: 0 0 15px 2px rgba(124, 58, 237, 0.5) !important;
        transform: translateY(-2px) !important;
    }
    
    /* Secondary buttons (Chips, Load More) */
    div[data-testid="stButton"] > button[kind="secondary"] {
        background: rgba(124, 58, 237, 0.1) !important;
        border: 1px solid rgba(124, 58, 237, 0.3) !important;
        color: #c084fc !important;
        transition: all 0.3s ease !important;
    }
    div[data-testid="stButton"] > button[kind="secondary"]:hover {
        background: rgba(124, 58, 237, 0.2) !important;
        border-color: #a855f7 !important;
        color: white !important;
    }
    
    /* Search box styling */
    .stTextInput>div>div>input {
        background-color: rgba(20, 20, 30, 0.8) !important;
        color: white !important;
        border: 1px solid rgba(124, 58, 237, 0.3) !important;
        border-radius: 8px !important;
        padding: 15px !important;
        font-size: 1.1rem !important;
    }
    .stTextInput>div>div>input:focus {
        border-color: #a855f7 !important;
        box-shadow: 0 0 0 1px #a855f7 !important;
    }

    /* Markdown Results Styling */
    .stMarkdown h2 {
        color: #a855f7 !important;
        margin-top: 1.5rem !important;
        margin-bottom: 0.5rem !important;
    }
    .stMarkdown hr {
        border-color: rgba(124, 58, 237, 0.3) !important;
        margin-top: 2rem !important;
        margin-bottom: 2rem !important;
    }
    .stMarkdown strong {
        color: #c084fc !important;
    }
</style>
""", unsafe_allow_html=True)

# State initialization
if "professors_markdown" not in st.session_state:
    st.session_state["professors_markdown"] = None
if "professor_sections" not in st.session_state:
    st.session_state["professor_sections"] = []
if "current_page" not in st.session_state:
    st.session_state["current_page"] = 0
if "search_query" not in st.session_state:
    st.session_state["search_query"] = ""
if "trigger_search" not in st.session_state:
    st.session_state["trigger_search"] = False

# Optional bring-your-own-key. The value is only passed to the search call:
# it is never written to disk, logged, or echoed back on the page.
with st.sidebar:
    st.markdown("### Use your own API key (optional)")
    own_key = st.text_input(
        "Anthropic API key",
        type="password",
        placeholder="sk-ant-...",
        help="Used only for your searches in this browser session. Never stored, logged, or shown. "
             "Searches with your own key skip the free-search limits.",
    ).strip()
    quota_slot = st.empty()

def show_quota():
    # Redrawn after a search is counted, so the number is never one search behind.
    if own_key:
        quota_slot.caption("Using your key: free-search limits don't apply.")
    else:
        quota_slot.caption(f"Free searches left this session: {remaining_this_session(st.session_state)}")

show_quota()

def handle_chip_click(q):
    st.session_state["search_query"] = q
    st.session_state["trigger_search"] = True

# Header
st.markdown('<div class="title-container">', unsafe_allow_html=True)
st.markdown('<div class="glowing-orb"></div>', unsafe_allow_html=True)
st.markdown('<div class="main-title">🎓 Professor Hunter</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Find funded STEM professors for your graduate school applications</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

if st.session_state.get("professors_markdown") is None:
    st.markdown("<br><br>", unsafe_allow_html=True)

# Search block
left_spacer, search_col1, search_col2, right_spacer = st.columns([1, 4, 1, 1])
with search_col1:
    query = st.text_input("Search", key="search_query", placeholder="Search for funded professors... (e.g. find AI hardware professors)", label_visibility="collapsed")
with search_col2:
    search_clicked = st.button("Hunt 🔍", use_container_width=True, type="primary")

do_search = search_clicked or st.session_state["trigger_search"]

# Suggested queries
st.markdown("<div style='text-align: center; color: #64748b; font-size: 0.9rem; margin-top: 5px; margin-bottom: 5px;'>Suggested searches:</div>", unsafe_allow_html=True)
c0, c1, c2, c3, c4, c5 = st.columns([0.5, 2, 2, 2, 2, 0.5])
with c1:
    st.button("Find AI hardware professors", on_click=handle_chip_click, args=("Find AI hardware professors",), use_container_width=True, type="secondary")
with c2:
    st.button("Find funded robotics professors at MIT", on_click=handle_chip_click, args=("Find funded robotics professors at MIT",), use_container_width=True, type="secondary")
with c3:
    st.button("Find ML professors at safety schools", on_click=handle_chip_click, args=("Find ML professors at safety schools",), use_container_width=True, type="secondary")
with c4:
    st.button("Find chip design professors at Target schools", on_click=handle_chip_click, args=("Find chip design professors at Target schools",), use_container_width=True, type="secondary")

# Execution
if do_search and query:
    st.session_state["trigger_search"] = False
    st.session_state["professors_markdown"] = None
    st.session_state["professor_sections"] = []
    st.session_state["current_page"] = 0

    allowed, limit_msg = check_and_consume(st.session_state, own_key)
    show_quota()
    if not allowed:
        st.warning(limit_msg)
        st.stop()

    with st.status("🔍 Searching the web for professors...", expanded=True) as status:
        st.markdown("*This search usually takes about 6-7 minutes while we verify real funding data for each professor*")
        try:
            def update_status(msg):
                status.write(msg)
                
            raw_result = run_professor_agent(query, status_callback=update_status, api_key=own_key or None)
            status.update(label="✅ Search complete!", state="complete", expanded=False)
            
            st.session_state["professors_markdown"] = raw_result
            
            # Split into individual professor sections
            sections = raw_result.split("---")
            # Filter out empty or whitespace-only sections
            # Only keep sections that contain "Institution:" to ensure it is a real professor section
            valid_sections = [s.strip() for s in sections if s.strip() and "Institution:" in s]
            st.session_state["professor_sections"] = valid_sections
            
        except Exception as e:
            st.error(f"Error executing agent: {redact(str(e), own_key)}")

# Results
if st.session_state.get("professor_sections"):
    st.markdown("<br><hr style='border-color: rgba(124, 58, 237, 0.2);'><br>", unsafe_allow_html=True)
    
    sections = st.session_state["professor_sections"]
    current_page = st.session_state["current_page"]
    
    items_per_page = 5
    total_pages = max(1, (len(sections) + items_per_page - 1) // items_per_page)
    
    # Calculate start and end indices for current page
    start_idx = current_page * items_per_page
    end_idx = min(start_idx + items_per_page, len(sections))
    
    # Display the items for the current page
    for i in range(start_idx, end_idx):
        st.markdown(sections[i])
        st.markdown("---")
        
    # Pagination controls
    st.markdown("<br>", unsafe_allow_html=True)
    p_col1, p_col2, p_col3 = st.columns([1, 2, 1])
    
    with p_col1:
        if st.button("◀ Previous", disabled=(current_page == 0), use_container_width=True):
            st.session_state["current_page"] -= 1
            st.rerun()
            
    with p_col2:
        st.markdown(f"<div style='text-align: center; color: #a855f7; font-weight: bold; margin-top: 8px;'>Page {current_page + 1} of {total_pages}</div>", unsafe_allow_html=True)
        
    with p_col3:
        if st.button("Next ▶", disabled=(current_page >= total_pages - 1), use_container_width=True):
            st.session_state["current_page"] += 1
            st.rerun()
