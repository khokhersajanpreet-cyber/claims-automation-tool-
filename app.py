import streamlit as st
import pandas as pd
import re
import io
import zipfile

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="AI Nexus | Chat Processor", 
    page_icon="🤖", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- 2. CYBER-AI CUSTOM CSS ---
st.markdown("""
<style>
    /* Hide default Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Gradient High-Tech Title */
    .cyber-title {
        background: -webkit-linear-gradient(45deg, #00f2fe, #4facfe, #00f2fe);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 3.5rem;
        font-weight: 900;
        margin-bottom: 0rem;
        text-align: center;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    .cyber-subtitle {
        color: #9ca3af;
        font-size: 1.2rem;
        text-align: center;
        margin-bottom: 3rem;
        font-weight: 300;
        letter-spacing: 1px;
    }
    
    /* Neon Process Button */
    div.stButton > button {
        background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
        color: white;
        border: none;
        box-shadow: 0 0 15px rgba(0, 242, 254, 0.4);
        border-radius: 8px;
        font-weight: 800;
        font-size: 1.2rem;
        letter-spacing: 1px;
        padding: 0.5rem 1rem;
        transition: all 0.3s ease-in-out;
        text-transform: uppercase;
    }
    div.stButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0 0 25px rgba(0, 242, 254, 0.8);
        border: 1px solid #ffffff;
    }
    
    /* Emerald Neon Download Button */
    div.stDownloadButton > button {
        background: linear-gradient(90deg, #10b981 0%, #059669 100%);
        color: white;
        border: none;
        box-shadow: 0 0 15px rgba(16, 185, 129, 0.4);
        border-radius: 8px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 1px;
        transition: all 0.3s ease-in-out;
        width: 100%;
    }
    div.stDownloadButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0 0 25px rgba(16, 185, 129, 0.8);
    }
    
    /* Glassmorphism Metric Cards */
    div[data-testid="metric-container"] {
        background-color: rgba(17, 24, 39, 0.6);
        border: 1px solid rgba(0, 242, 254, 0.2);
        border-top: 3px solid #00f2fe;
        padding: 1rem;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
        backdrop-filter: blur(10px);
    }
    
    /* Section Headers */
    h3 {
        color: #00f2fe !important;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. MAIN HEADER ---
st.markdown("<h1 class='cyber-title'>Neural Data Extractor</h1>", unsafe_allow_html=True)
st.markdown("<p class='cyber-subtitle'>Automated Intelligence for WhatsApp Parsing & Structuring</p>", unsafe_allow_html=True)

# --- 4. UI LAYOUT: UPLOAD & FILTER ---
col1, space, col2 = st.columns([1.2, 0.1, 1.2])

with col1:
    st.markdown("### 📥 01. Data Ingestion")
    st.caption("Supported formats: .TXT / .ZIP")
    chat_file = st.file_uploader("", type=["txt", "zip"], label_visibility="collapsed")

with col2:
    st.markdown("### ⏱️ 02. Temporal Filter")
    st.caption("Isolate specific timelines")
    enable_date_filter = st.toggle("Activate Temporal Filtering", value=False)
    start_date, end_date = None, None
    if enable_date_filter:
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            start_date = st.date_input("From Sequence")
        with d_col2:
            end_date = st.date_input("To Sequence")
    else:
        st.info("🌐 Core filter disabled. Processing entire data spectrum.")

st.write("")
st.write("")

# --- 5. CORE LOGIC FUNCTIONS ---
def extract_id(msg):
    match = re.search(r'(?i)(?:booking|lead|case|ticket)\s*i[\'d]?\s*[:-]*\s*([a-zA-Z0-9]+)', str(msg))
    if match: return match.group(1).strip()
    match2 = re.match(r'^(\d{7,11})\b', str(msg).strip())
    if match2: return match2.group(1).strip()
    return ""

def clean_message_text(msg, lead_id=""):
    cleaned = str(msg)
    cleaned = re.sub(r'@\u2068.*?\u2069', '', cleaned)
    cleaned = re.sub(r'@[^\s]+', '', cleaned)
    cleaned = re.sub(r'[\u200e\u202a\u202c\u202d\u2069\u2068\u202f]', '', cleaned)
    cleaned = re.sub(r'(?i)(?:booking|lead|case|ticket|I\'d)\s*(?:id|i\'d|no)?\s*[:-]*\s*([a-zA-Z0-9]+)', '', cleaned)
    cleaned = re.sub(r'(?m)^(\d{7,11})\b', '', cleaned)
    if lead_id and str(lead_id) in cleaned:
        cleaned = cleaned.replace(str(lead_id), '')
    cleaned = re.sub(r'\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b', '', cleaned)
    cleaned = re.sub(r'\[\d{1,2}/\d{1,2}/\d{2,4}.*?\]', '', cleaned)
    
    lines = cleaned.split('\n')
    final_lines = []
    for l in lines:
        l = re.sub(r'^[-\s:/,]+', '', l) 
        l = re.sub(r'[-\s:/,]+$', '', l) 
        l = l.strip()
        ignore_list = ['image omitted', 'audio omitted', 'video omitted', 'document omitted', 'this message was deleted.']
        if l and l.lower() not in ignore_list:
            final_lines.append(l)
    return '\n'.join(final_lines).strip()

# --- 6. PROCESSING BLOCK ---
col_btn1, col_btn2, col_btn3 = st.columns([1, 1.5, 1])
with col_btn2:
    process_button = st.button("⚡ Initialize Extraction Sequence", use_container_width=True)

if process_button:
    if not chat_file:
        st.error("⚠️ SYSTEM HALTED: No data source detected in ingestion bay.")
    else:
        with st.status("🧠 AI Engine Active...", expanded=True) as status:
            try:
                st.write("📡 Scanning file contents...")
                if chat_file.name.endswith(".zip"):
                    with zipfile.ZipFile(chat_file) as z:
                        txt_name = [n for n in z.namelist() if n.endswith('.txt')][0]
                        with z.open(txt_name) as f: chat_text = f.read().decode("utf-8", errors="replace")
                else:
                    chat_text = chat_file.read().decode("utf-8", errors="replace")
                
                if not chat_text.strip():
                    st.error("⚠️ SYSTEM HALTED: Data source is empty.")
                    st.stop()
                
                st.write("⚙️ Parsing raw string anomalies...")
                parsed_data = []
                cur_date, cur_time, cur_sender, cur_msg = "", "", "", []
                raw_lines = chat_text.split('\n')
                
                for line in raw_lines:
                    line = line.strip()
                    if not line: continue
                    match = re.match(r'^\[?(\d{1,2}/\d{1,2}/\d{2,4}),\s*([^\]\-]+)\]?\s*[-]?\s*(.*?):\s*(.*)', line)
                    if match:
                        if cur_sender: parsed_data.append([cur_date, cur_time, cur_sender, '\n'.join(cur_msg)])
                        cur_date, cur_time, cur_sender, m = match.groups()
                        cur_sender = cur_sender.strip()
                        cur_time = re.sub(r'[\u202f\u200e\u202a\u202c\u202d\u2069]', ' ', cur_time).strip()
                        cur_msg = [m.strip()]
                    else:
                        sys_match = re.match(r'^\[?(\d{1,2}/\d{1,2}/\d{2,4}),\s*([^\]\-]+)\]?\s*[-]?\s*(.*)', line)
                        if sys_match: continue
                        else:
                            if cur_sender: cur_msg.append(line)
                        
                if cur_sender: parsed_data.append([cur_date, cur_time, cur_sender, '\n'.join(cur_msg)])
                
                if not parsed_data:
                    st.error("⚠️ SYSTEM HALTED: Format unrecognizable. Not a standard WhatsApp string.")
                    st.stop()
                
                df = pd.DataFrame(parsed_data, columns=['Date', 'Time', 'Sender', 'Raw_Message'])
                df['Date_Parsed'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce').dt.date
                
                if enable_date_filter and start_date and end_date:
                    st.write(f"⏳ Applying temporal constraints: {start_date} to {end_date}...")
                    mask = (df['Date_Parsed'] >= start_date) & (df['Date_Parsed'] <= end_date)
                    df = df[mask]
                    
                if df.empty:
                    st.error(f"⚠️ NO DATA YIELD: Sequence {start_date.strftime('%d-%b-%Y')} to {end_date.strftime('%d-%b-%Y')} generated zero results.")
                    st.stop()
                    
                st.write("🧬 Isolating target IDs & purging noise...")
                df['Booking/Lead ID'] = df['Raw_Message'].apply(extract_id)
                df['Message'] = df.apply(lambda r: clean_message_text(r['Raw_Message'], r['Booking/Lead ID']), axis=1)
                df = df[df['Message'] != '']
                
                df_out = df[['Date', 'Time', 'Booking/Lead ID', 'Message']].copy()
                df_out['Date'] = pd.to_datetime(df_out['Date'], format='mixed', dayfirst=True).dt.strftime('%d-%m-%Y')
                
                st.write("💾 Formatting matrix into Excel array...")
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    for date in sorted(df_out['Date'].dropna().unique()):
                        sheet_name = str(date).replace('/', '-')
                        df_date = df_out[df_out['Date'] == date].copy()
                        df_date.to_excel(writer, index=False, sheet_name=sheet_name[:31])
                
                excel_buffer.seek(0)
                status.update(label="✅ Extraction Sequence Complete", state="complete", expanded=False)
                
                # --- 7. CYBER RESULTS DASHBOARD ---
                st.divider()
                st.markdown("<h3 style='text-align: center; margin-bottom: 2rem;'>📊 Telemetry Report</h3>", unsafe_allow_html=True)
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Lines Purified", len(df_out))
                m2.metric("Unique IDs Acquired", df_out['Booking/Lead ID'].replace('', pd.NA).nunique())
                m3.metric("Temporal Grids (Days)", df_out['Date'].nunique())
                
                st.write("")
                st.write("")
                
                dl_col1, dl_col2, dl_col3 = st.columns([1, 1.5, 1])
                with dl_col2:
                    st.download_button(
                        label="💾 Download Cleaned Matrix (.xlsx)",
                        data=excel_buffer,
                        file_name="AI_Cleaned_WhatsApp_Data.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                
                st.write("")
                with st.expander("👁️ Inspect Data Matrix"):
                    st.dataframe(df_out.head(100), use_container_width=True)
                
            except Exception as e:
                status.update(label="❌ System Malfunction", state="error")
                st.error(f"Error trace: {e}")
