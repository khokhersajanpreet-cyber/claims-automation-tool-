import streamlit as st
import pandas as pd
import re
import io
import zipfile

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="WhatsApp Data Processor", 
    page_icon="📊", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. CUSTOM CSS FOR PROFESSIONAL UI ---
st.markdown("""
<style>
    /* Hide default Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Style headers */
    h1 {color: #1E3A8A; font-weight: 700;}
    h2, h3 {color: #2563EB;}
    
    /* Style the Download Button */
    div.stDownloadButton > button:first-child {
        background-color: #10B981;
        color: white;
        border-radius: 8px;
        padding: 12px 24px;
        border: none;
        font-weight: 700;
        width: 100%;
        transition: all 0.3s ease;
    }
    div.stDownloadButton > button:first-child:hover {
        background-color: #059669;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    /* Card-like containers for metrics */
    div[data-testid="metric-container"] {
        background-color: #F3F4F6;
        border: 1px solid #E5E7EB;
        padding: 5% 5% 5% 10%;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

# --- 3. SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/732/732220.png", width=60) # Excel Icon
    st.title("⚙️ Settings & Info")
    st.markdown("""
    **How to use this tool:**
    1. Upload your exported WhatsApp `.txt` or `.zip` file.
    2. (Optional) Toggle the date filter to isolate specific days.
    3. Click **Process Data**.
    4. Download your clean, date-separated Excel report.
    """)
    st.divider()
    st.caption("🔒 All processing is done locally in your browser. No data is stored or shared.")

# --- 4. MAIN HEADER ---
st.title("📱 WhatsApp Chat to Excel Converter")
st.markdown("Transform your raw WhatsApp exports into structured, date-filtered, and perfectly clean Excel reports.")
st.write("---")

# --- 5. UI LAYOUT: UPLOAD & FILTER SIDE-BY-SIDE ---
col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.markdown("### 📂 1. Upload Data")
    chat_file = st.file_uploader("Drop your WhatsApp Chat (.txt or .zip)", type=["txt", "zip"])

with col2:
    st.markdown("### 📅 2. Filter Dates")
    enable_date_filter = st.toggle("Enable strict date filtering", value=False)
    start_date, end_date = None, None
    if enable_date_filter:
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            start_date = st.date_input("Start Date")
        with d_col2:
            end_date = st.date_input("End Date")
    else:
        st.info("Date filter is currently OFF. The entire chat log will be processed.")

st.write("---")

# --- 6. CORE LOGIC FUNCTIONS ---
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

# --- 7. PROCESSING BLOCK ---
col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
with col_btn2:
    process_button = st.button("🚀 Process Data", type="primary", use_container_width=True)

if process_button:
    if not chat_file:
        st.error("⚠️ Please upload a WhatsApp Chat file to begin.")
    else:
        with st.status("Processing your data...", expanded=True) as status:
            try:
                st.write("Reading file contents...")
                if chat_file.name.endswith(".zip"):
                    with zipfile.ZipFile(chat_file) as z:
                        txt_name = [n for n in z.namelist() if n.endswith('.txt')][0]
                        with z.open(txt_name) as f: chat_text = f.read().decode("utf-8", errors="replace")
                else:
                    chat_text = chat_file.read().decode("utf-8", errors="replace")
                
                if not chat_text.strip():
                    st.error("⚠️ The uploaded file is empty.")
                    st.stop()
                
                st.write("Parsing messages and cleaning formats...")
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
                    st.error("⚠️ No valid WhatsApp messages found.")
                    st.stop()
                
                df = pd.DataFrame(parsed_data, columns=['Date', 'Time', 'Sender', 'Raw_Message'])
                df['Date_Parsed'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce').dt.date
                
                if enable_date_filter and start_date and end_date:
                    st.write(f"Applying strict date filter: {start_date} to {end_date}...")
                    mask = (df['Date_Parsed'] >= start_date) & (df['Date_Parsed'] <= end_date)
                    df = df[mask]
                    
                if df.empty:
                    st.error(f"⚠️ No data found between {start_date.strftime('%d-%b-%Y')} and {end_date.strftime('%d-%b-%Y')}.")
                    st.stop()
                    
                st.write("Extracting Lead IDs and sanitizing messages...")
                df['Booking/Lead ID'] = df['Raw_Message'].apply(extract_id)
                df['Message'] = df.apply(lambda r: clean_message_text(r['Raw_Message'], r['Booking/Lead ID']), axis=1)
                df = df[df['Message'] != '']
                
                df_out = df[['Date', 'Time', 'Booking/Lead ID', 'Message']].copy()
                df_out['Date'] = pd.to_datetime(df_out['Date'], format='mixed', dayfirst=True).dt.strftime('%d-%m-%Y')
                
                st.write("Generating final Excel report...")
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    for date in sorted(df_out['Date'].dropna().unique()):
                        sheet_name = str(date).replace('/', '-')
                        df_date = df_out[df_out['Date'] == date].copy()
                        df_date.to_excel(writer, index=False, sheet_name=sheet_name[:31])
                
                excel_buffer.seek(0)
                status.update(label="✅ Processing Complete!", state="complete", expanded=False)
                
                # --- 8. RESULTS DASHBOARD ---
                st.divider()
                st.markdown("## 📊 Processing Results")
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Total Messages Cleaned", len(df_out))
                m2.metric("Unique Lead IDs Found", df_out['Booking/Lead ID'].replace('', pd.NA).nunique())
                m3.metric("Total Days Exported", df_out['Date'].nunique())
                
                st.write("")
                
                dl_col1, dl_col2, dl_col3 = st.columns([1, 2, 1])
                with dl_col2:
                    st.download_button(
                        label="📥 Download Final Excel Report",
                        data=excel_buffer,
                        file_name="Cleaned_WhatsApp_Data.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                
                with st.expander("👁️ Preview Cleaned Data"):
                    st.dataframe(df_out.head(50), use_container_width=True)
                
            except Exception as e:
                status.update(label="❌ Error Occurred", state="error")
                st.error(f"Error details: {e}")
