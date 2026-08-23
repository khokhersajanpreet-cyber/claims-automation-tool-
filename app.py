import streamlit as st
import pandas as pd
import numpy as np
import re
import io
import zipfile
from datetime import timedelta
import dateutil.parser

# --- Page Configuration ---
st.set_page_config(
    page_title="Claims Chat & Pendency Automation Tool",
    page_icon="📋",
    layout="wide"
)

st.title("📋 Claims Pendency & WhatsApp Chat Automation Tool")
st.markdown("Automate WhatsApp chat parsing, date filtering, and pendency list updates directly in your browser.")

# --- Step 1: Upload Files ---
st.subheader("Step 1: Upload Files")
col1, col2 = st.columns(2)

with col1:
    chat_file = st.file_uploader("Upload WhatsApp Chat (.txt or .zip)", type=["txt", "zip", "xlsx"])

with col2:
    pendency_file = st.file_uploader("Upload Pendency Sheet (.xlsx)", type=["xlsx"])

# --- Step 2: Date Filtering Option ---
st.subheader("Step 2: Select Date Range for Chat Analysis (Optional)")
enable_date_filter = st.checkbox("Filter WhatsApp Chat by Date Range", value=False)

start_date, end_date = None, None
if enable_date_filter:
    d_col1, d_col2 = st.columns(2)
    with d_col1:
        start_date = st.date_input("Start Date")
    with d_col2:
        end_date = st.date_input("End Date")

# --- Helper Functions ---
def extract_chat_text(uploaded_file):
    if uploaded_file.name.endswith(".zip"):
        with zipfile.ZipFile(uploaded_file) as z:
            for name in z.namelist():
                if name.endswith(".txt"):
                    with z.open(name) as f:
                        return f.read().decode("utf-8", errors="replace")
    elif uploaded_file.name.endswith(".txt"):
        return uploaded_file.read().decode("utf-8", errors="replace")
    elif uploaded_file.name.endswith(".xlsx"):
        df_raw = pd.read_excel(uploaded_file, header=None)
        return "\n".join(df_raw[0].dropna().astype(str).tolist())
    return ""

def extract_id(msg):
    match = re.search(r'(?i)(?:booking|lead|case|ticket)\s*i[\'d]?\s*[:-]*\s*([a-zA-Z0-9]+)', msg)
    if match:
        return match.group(1).strip()
    match2 = re.match(r'^(\d{7,11})\b', msg.strip())
    if match2:
        return match2.group(1).strip()
    return None

def clean_message_text(msg):
    cleaned = str(msg)
    cleaned = re.sub(r'@\u2068.*?\u2069', '', cleaned)
    cleaned = re.sub(r'@[A-Za-z0-9_~\.\-\s]+(?=\n|$|@)', '', cleaned)
    cleaned = re.sub(r'@\d+', '', cleaned)
    cleaned = re.sub(r'(?i)(?:booking|lead|case|ticket|I\'d)\s*(?:id|i\'d|no)?\s*[:-]*\s*([a-zA-Z0-9]+)', '', cleaned)
    cleaned = re.sub(r'^(\d{7,11})\b', '', cleaned.strip())
    cleaned = re.sub(r'[\u200e\u202a\u202c\u202d\u2069\u2068]', '', cleaned)
    lines = cleaned.split('\n')
    final_lines = []
    for l in lines:
        l = re.sub(r'^[-\s:/]+', '', l)
        l = re.sub(r'[-\s:/]+$', '', l)
        if l and l.lower() not in ['image omitted', 'audio omitted', 'video omitted', 'document omitted']:
            final_lines.append(l.strip())
    return '\n'.join(final_lines).strip()

def clean_id_str(val):
    if pd.isna(val) or str(val).strip() == '':
        return ""
    try:
        return str(int(float(val))).strip().lower()
    except:
        return str(val).strip().lower()

def clean_time_string(t):
    # This safely removes the problematic formatting characters without using pyarrow regex
    return re.sub(r'[\u202f\u200e\u202a\u202c\u202d\u2069]', ' ', str(t))

def analyze_pendency_and_date(row, pendency_col, exp_date_col, work_date_col, remarks_col):
    msg = str(row.get(remarks_col, "")).lower()
    if msg == "agent not shared remarks on whatsapp" or not msg:
        return row.get(pendency_col, ""), row.get(exp_date_col, "")
    
    # 6 Specified Dropdown Selectors
    k_closed = ['visit done', 'visit completed', 'documents collected', 'docs collected', 'shared on mail', 'shared on claims mail', 'couriered', 'courier done', 'scan copy mailed', 'pod share', 'pod details']
    k_cx_no_ans = ['not answering', 'not responding', 'not picking', 'switched off', 'switch off', 'not reachable', 'disconnected', 'cut my call', 'unreachable', 'invalid no', 'not connecting']
    k_hospital = ['hospital denied', 'from hospital', 'doctor not available', 'doctor is not', 'mrd', 'part b pending', 'icp pending', 'hospital refused']
    k_customer = ['customer out of', 'cx out of', 'out of station', 'out of town', 'out of city', 'cx busy', 'customer busy', 'customer denied', 'cx denied', 'not available', 'not at home']
    k_agent = ['reschedule', 'rescheduled', 'agent on leave', 'medical leave', 'sick leave', 'stuck in rain', 'vehicle broke down', 'not in system', 'agent not available', 'week off', 'off today']
    k_claims = ['claims team', 'share query letter', 'share rejection letter', 'reconsideration status', 'update on this case', 'need query letter', 'waiting for approval', 'waiting for final approval']
    
    pendency = row.get(pendency_col, "")
    if any(k in msg for k in k_cx_no_ans):
        pendency = "CX not answering"
    elif any(k in msg for k in k_hospital):
        pendency = "Hospital"
    elif any(k in msg for k in k_customer):
        pendency = "Customer"
    elif any(k in msg for k in k_agent):
        pendency = "Agent"
    elif any(k in msg for k in k_closed):
        pendency = "closed"
    elif any(k in msg for k in k_claims):
        pendency = "claims team"
        
    # Expected Appointment Date Analysis
    exp_date = row.get(exp_date_col, "")
    work_date = pd.to_datetime(row.get(work_date_col, pd.NaT), errors='coerce')
    
    if pd.notna(work_date):
        if 'day after tomorrow' in msg:
            exp_date = (work_date + timedelta(days=2)).strftime('%d-%m-%Y')
        elif any(w in msg for w in ['tomorrow', 'tommorow', 'tmrw']):
            exp_date = (work_date + timedelta(days=1)).strftime('%d-%m-%Y')
        else:
            date_match = re.search(r'(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*|\d{1,2}(?:st|nd|rd|th))', msg)
            if date_match:
                d_str = date_match.group(1).replace('st','').replace('nd','').replace('rd','').replace('th','')
                try:
                    if len(d_str) <= 2:
                        d_str = f"{d_str} {work_date.strftime('%b %Y')}"
                    elif not any(char.isdigit() for char in d_str[3:]):
                        d_str = f"{d_str} {work_date.year}"
                    parsed_d = dateutil.parser.parse(d_str)
                    exp_date = parsed_d.strftime('%d-%m-%Y')
                except:
                    pass
    
    return pendency, exp_date

# --- Step 3: Run Button ---
st.subheader("Step 3: Process & Download")
if st.button("🚀 Process and Auto-Fill Pendency Sheet", type="primary"):
    if not chat_file or not pendency_file:
        st.error("⚠️ Please upload BOTH the WhatsApp chat file and the Pendency Excel sheet.")
    else:
        with st.spinner("Processing chat logs and updating pendency rows..."):
            try:
                chat_text = extract_chat_text(chat_file)
                if not chat_text:
                    st.error("Could not read text from the WhatsApp file. Please ensure it's a valid .txt, .zip, or .xlsx file.")
                    st.stop()
                
                # 1. Parse Chat Log
                parsed_data = []
                clean_lines = [re.sub(r'[\u200e\u202a\u202c\u202d\u2069]', '', l).strip() for l in chat_text.split('\n') if l.strip()]
                
                cur_date, cur_time, cur_sender, cur_msg = "", "", "", []
                for line in clean_lines:
                    match = re.match(r'^\[?(\d{2}/\d{2}/\d{2,4}),\s*(.*?)\]?\s*(.*?):\s*(.*)', line)
                    if not match:
                        match = re.match(r'^(\d{2}/\d{2}/\d{2,4}),\s*(.*?)\s*-\s*(.*?):\s*(.*)', line)
                    if match:
                        if cur_sender:
                            parsed_data.append([cur_date, cur_time, cur_sender, '\n'.join(cur_msg)])
                        cur_date, cur_time, cur_sender, m = match.groups()
                        cur_sender = cur_sender.strip()
                        cur_msg = [m.strip()]
                    else:
                        if cur_sender:
                            cur_msg.append(line)
                if cur_sender:
                    parsed_data.append([cur_date, cur_time, cur_sender, '\n'.join(cur_msg)])
                    
                df_chat = pd.DataFrame(parsed_data, columns=['Date', 'Time', 'Sender', 'Raw_Message'])
                
                if df_chat.empty:
                    st.error("No messages could be parsed from the uploaded chat file. Please ensure it's a standard WhatsApp export.")
                    st.stop()

                df_chat['Booking/Lead ID'] = df_chat['Raw_Message'].apply(extract_id)
                df_chat['Message'] = df_chat['Raw_Message'].apply(clean_message_text)
                
                # Datetime processing - Safely applied to avoid PyArrow regex crashes
                df_chat['Clean_Time'] = df_chat['Time'].apply(clean_time_string)
                df_chat['DateTime_str'] = df_chat['Date'].astype(str) + ' ' + df_chat['Clean_Time']
                df_chat['DateTime'] = pd.to_datetime(df_chat['DateTime_str'], format='mixed', dayfirst=True, errors='coerce')
                df_chat['Date_Parsed'] = pd.to_datetime(df_chat['Date'], format='mixed', dayfirst=True, errors='coerce')
                
                # Apply Date Filter if enabled
                if enable_date_filter and start_date and end_date:
                    start_dt = pd.to_datetime(start_date)
                    end_dt = pd.to_datetime(end_date)
                    df_chat = df_chat[(df_chat['Date_Parsed'] >= start_dt) & (df_chat['Date_Parsed'] <= end_dt)]
                
                df_chat_valid = df_chat.dropna(subset=['Booking/Lead ID']).copy()
                df_chat_valid['Clean_ID'] = df_chat_valid['Booking/Lead ID'].apply(clean_id_str)
                df_chat_valid = df_chat_valid[df_chat_valid['Clean_ID'] != '']
                
                # Sort to get the latest message per Lead ID
                df_chat_valid = df_chat_valid.sort_values(by='DateTime', ascending=False)
                latest_chat = df_chat_valid.drop_duplicates(subset=['Clean_ID'], keep='first')
                msg_mapping = dict(zip(latest_chat['Clean_ID'], latest_chat['Message']))
                
                # 2. Process Pendency Sheet
                df_pendency = pd.read_excel(pendency_file)
                
                # Safely find column names (case-insensitive and handles trailing spaces)
                lead_cols = [c for c in df_pendency.columns if 'lead' in str(c).lower()]
                remarks_cols = [c for c in df_pendency.columns if 'remark' in str(c).lower()]
                pendency_cols = [c for c in df_pendency.columns if 'pendency' in str(c).lower()]
                exp_date_cols = [c for c in df_pendency.columns if 'expected' in str(c).lower()]
                work_date_cols = [c for c in df_pendency.columns if 'work date' in str(c).lower()]
                
                if not lead_cols:
                    st.error("Could not find a 'Lead Id' column in the uploaded Excel sheet. Please verify column names.")
                    st.stop()
                    
                lead_col = lead_cols[0]
                remarks_col = remarks_cols[0] if remarks_cols else 'Remarks'
                pendency_col = pendency_cols[0] if pendency_cols else 'Pendency'
                exp_date_col = exp_date_cols[0] if exp_date_cols else 'Expected appointment'
                work_date_col = work_date_cols[0] if work_date_cols else 'Work Date'
                
                # Ensure missing columns are created so the file doesn't break
                for col in [remarks_col, pendency_col, exp_date_col]:
                    if col not in df_pendency.columns:
                        df_pendency[col] = ""
                
                df_pendency['Clean_LeadId'] = df_pendency[lead_col].apply(clean_id_str)
                
                # Fill Remarks
                def get_remarks(row):
                    cid = row['Clean_LeadId']
                    if not cid:
                        return row.get(remarks_col, "")
                    return msg_mapping.get(cid, "Agent not shared remarks on whatsapp")

                df_pendency[remarks_col] = df_pendency.apply(get_remarks, axis=1)
                
                # Fill Pendency and Expected Appointment
                df_pendency[[pendency_col, exp_date_col]] = df_pendency.apply(
                    lambda r: analyze_pendency_and_date(r, pendency_col, exp_date_col, work_date_col, remarks_col),
                    axis=1,
                    result_type='expand'
                )
                
                df_pendency = df_pendency.drop(columns=['Clean_LeadId'])
                
                # Generate Download Output
                output_buffer = io.BytesIO()
                df_pendency.to_excel(output_buffer, index=False, engine='openpyxl')
                output_buffer.seek(0)
                
                st.success(f"✅ Finished! Found and updated matching leads.")
                
                st.download_button(
                    label="📥 Download Updated Pendency Sheet",
                    data=output_buffer,
                    file_name="Updated_Creation_Pendency_Final.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                st.subheader("Preview of Updated Data")
                st.dataframe(df_pendency.head(15))
                
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")
                st.write("Please check your input files or try refreshing the app.")
