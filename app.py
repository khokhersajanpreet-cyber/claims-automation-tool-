import streamlit as st
import pandas as pd
import numpy as np
import re
import io
import zipfile
from datetime import timedelta
import dateutil.parser

# --- Page Configuration ---
st.set_page_config(page_title="Claims & Pendency Automation Tool", page_icon="📋", layout="wide")

st.title("📋 Claims Pendency & WhatsApp Chat Automation Tool")
st.markdown("Automate WhatsApp chat parsing, date filtering, and pendency list updates.")

# --- Upload Files ---
st.subheader("Step 1: Upload Files")
st.info("💡 You can upload just the WhatsApp chat to get the cleaned Excel, or upload BOTH files to auto-update your Pendency sheet.")

col1, col2 = st.columns(2)
with col1:
    chat_file = st.file_uploader("Upload WhatsApp Chat (.txt, .zip, or Processed .xlsx)", type=["txt", "zip", "xlsx"])
with col2:
    pendency_file = st.file_uploader("Upload Pendency Sheet (.xlsx)", type=["xlsx"])

# --- Date Filtering ---
st.subheader("Step 2: WhatsApp Chat Date Filter")
st.markdown("Select a start and end date. **Only messages within these dates will be evaluated and sent to the Pendency Sheet.**")
enable_date_filter = st.checkbox("Enable Date Filter", value=False)
start_date, end_date = None, None

if enable_date_filter:
    d_col1, d_col2 = st.columns(2)
    with d_col1:
        start_date = st.date_input("Start Date")
    with d_col2:
        end_date = st.date_input("End Date")

# --- Helper Functions ---
def clean_id_str(val):
    if pd.isna(val) or str(val).strip() == '': return ""
    v = str(val).strip().lower()
    if v.endswith('.0'): v = v[:-2]
    return v

def extract_id(msg):
    match = re.search(r'(?i)(?:booking|lead|case|ticket)\s*i[\'d]?\s*[:-]*\s*([a-zA-Z0-9]+)', str(msg))
    if match: return match.group(1).strip()
    match2 = re.match(r'^(\d{7,11})\b', str(msg).strip())
    if match2: return match2.group(1).strip()
    return ""

def clean_message_text(msg, lead_id=""):
    cleaned = str(msg)
    cleaned = re.sub(r'@\u2068.*?\u2069', '', cleaned)
    cleaned = re.sub(r'@[A-Za-z0-9_~\.\-\s]+(?=\n|$|@)', '', cleaned)
    cleaned = re.sub(r'@\d+', '', cleaned)
    cleaned = re.sub(r'(?i)(?:booking|lead|case|ticket|I\'d)\s*(?:id|i\'d|no)?\s*[:-]*\s*([a-zA-Z0-9]+)', '', cleaned)
    cleaned = re.sub(r'^(\d{7,11})\b', '', cleaned.strip())
    if lead_id and str(lead_id) in cleaned:
        cleaned = cleaned.replace(str(lead_id), '')
    cleaned = re.sub(r'[\u200e\u202a\u202c\u202d\u2069\u2068]', '', cleaned)
    
    final_lines = [re.sub(r'^[-:/]+|[-:/]+$', '', l).strip() for l in cleaned.split('\n') if l.strip() and l.strip().lower() not in ['image omitted', 'audio omitted', 'video omitted', 'document omitted']]
    return '\n'.join(final_lines).strip()

def clean_time_string(t):
    return re.sub(r'[\u202f\u200e\u202a\u202c\u202d\u2069]', ' ', str(t))

def analyze_pendency_and_date(row, pendency_col, exp_date_col, work_date_col, remarks_col):
    msg = str(row.get(remarks_col, "")).lower()
    if msg == "agent not shared remarks on whatsapp" or not msg:
        return row.get(pendency_col, ""), row.get(exp_date_col, "")
    
    k_closed = ['visit done', 'visit completed', 'documents collected', 'docs collected', 'shared on mail', 'shared on claims mail', 'couriered', 'courier done', 'scan copy mailed', 'pod share', 'pod details', 'uploaded in mailed']
    k_cx_no_ans = ['not answering', 'not responding', 'not picking', 'switched off', 'switch off', 'not reachable', 'disconnected', 'cut my call', 'unreachable', 'invalid no', 'not connecting']
    k_hospital = ['hospital denied', 'from hospital', 'doctor not available', 'doctor is not', 'mrd', 'part b pending', 'icp pending', 'hospital refused', 'hospital staff']
    k_customer = ['customer out of', 'cx out of', 'out of station', 'out of town', 'out of city', 'cx busy', 'customer busy', 'customer denied', 'cx denied', 'not available', 'not at home']
    k_agent = ['reschedule', 'rescheduled', 'agent on leave', 'medical leave', 'sick leave', 'stuck in rain', 'vehicle broke down', 'not in system', 'agent not available', 'week off', 'off today']
    k_claims = ['claims team', 'share query letter', 'share rejection letter', 'reconsideration status', 'update on this case', 'need query letter', 'waiting for approval', 'waiting for final approval']
    
    pendency = row.get(pendency_col, "")
    if any(k in msg for k in k_closed): pendency = "closed"
    elif any(k in msg for k in k_hospital): pendency = "Hospital"
    elif any(k in msg for k in k_customer): pendency = "Customer"
    elif any(k in msg for k in k_cx_no_ans): pendency = "CX not answering"
    elif any(k in msg for k in k_agent): pendency = "Agent"
    elif any(k in msg for k in k_claims): pendency = "claims team"
        
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
                    if len(d_str) <= 2: d_str = f"{d_str} {work_date.strftime('%b %Y')}"
                    elif not any(char.isdigit() for char in d_str[3:]): d_str = f"{d_str} {work_date.year}"
                    exp_date = dateutil.parser.parse(d_str).strftime('%d-%m-%Y')
                except: pass
    return pendency, exp_date

# --- Step 3: Run Processor ---
st.subheader("Step 3: Process & Download")
if st.button("🚀 Process Data", type="primary"):
    if not chat_file:
        st.error("⚠️ Please upload a WhatsApp Chat file at minimum to proceed.")
    else:
        with st.spinner("Analyzing and evaluating data..."):
            try:
                # --- CHAT PROCESSING ---
                if chat_file.name.endswith(".xlsx"):
                    df_chat = pd.read_excel(chat_file)
                    if 'Booking/Lead ID' not in df_chat.columns:
                        df_chat['Booking/Lead ID'] = df_chat.iloc[:, 0].apply(extract_id)
                else:
                    if chat_file.name.endswith(".zip"):
                        with zipfile.ZipFile(chat_file) as z:
                            txt_name = [n for n in z.namelist() if n.endswith('.txt')][0]
                            with z.open(txt_name) as f: chat_text = f.read().decode("utf-8", errors="replace")
                    else:
                        chat_text = chat_file.read().decode("utf-8", errors="replace")
                        
                    parsed_data, cur_date, cur_time, cur_sender, cur_msg = [], "", "", "", []
                    for line in [re.sub(r'[\u200e\u202a\u202c\u202d\u2069]', '', l).strip() for l in chat_text.split('\n') if l.strip()]:
                        match = re.match(r'^\[?(\d{2}/\d{2}/\d{2,4}),\s*(.*?)\]?\s*(.*?):\s*(.*)', line)
                        if not match: match = re.match(r'^(\d{2}/\d{2}/\d{2,4}),\s*(.*?)\s*-\s*(.*?):\s*(.*)', line)
                        if match:
                            if cur_sender: parsed_data.append([cur_date, cur_time, cur_sender, '\n'.join(cur_msg)])
                            cur_date, cur_time, cur_sender, m = match.groups()
                            cur_sender, cur_msg = cur_sender.strip(), [m.strip()]
                        else:
                            if cur_sender: cur_msg.append(line)
                    if cur_sender: parsed_data.append([cur_date, cur_time, cur_sender, '\n'.join(cur_msg)])
                    
                    df_chat = pd.DataFrame(parsed_data, columns=['Date', 'Time', 'Sender', 'Raw_Message'])
                    df_chat['Booking/Lead ID'] = df_chat['Raw_Message'].apply(extract_id)
                    df_chat['Message'] = df_chat.apply(lambda r: clean_message_text(r['Raw_Message'], r['Booking/Lead ID']), axis=1)

                # Format Datetime safely
                df_chat['Clean_Time'] = df_chat['Time'].apply(clean_time_string)
                df_chat['Date_Parsed'] = pd.to_datetime(df_chat['Date'], format='mixed', dayfirst=True, errors='coerce')
                df_chat['DateTime_str'] = df_chat['Date'].astype(str) + ' ' + df_chat['Clean_Time']
                df_chat['DateTime'] = pd.to_datetime(df_chat['DateTime_str'], format='mixed', dayfirst=True, errors='coerce')
                
                # --- APPLY THE DATE FILTER HERE BEFORE DOING ANYTHING ELSE ---
                if enable_date_filter and start_date and end_date:
                    start_dt = pd.to_datetime(start_date)
                    end_dt = pd.to_datetime(end_date)
                    df_chat = df_chat[(df_chat['Date_Parsed'] >= start_dt) & (df_chat['Date_Parsed'] <= end_dt)]
                
                # Prepare Evaluated Chat Excel Output
                df_chat_out = df_chat[['Date', 'Time', 'Booking/Lead ID', 'Message']].copy()
                if not df_chat_out.empty:
                    df_chat_out['Date'] = df_chat['Date_Parsed'].dt.strftime('%d-%m-%y')
                
                chat_buffer = io.BytesIO()
                with pd.ExcelWriter(chat_buffer, engine='openpyxl') as writer:
                    if df_chat_out.empty:
                        pd.DataFrame({'Message':['No data found for these dates']}).to_excel(writer, index=False, sheet_name="No Data")
                    else:
                        for date in sorted(df_chat_out['Date'].dropna().unique()):
                            sheet_name = str(date).replace('/', '-')
                            df_date = df_chat_out[df_chat_out['Date'] == date].copy()
                            df_date.to_excel(writer, index=False, sheet_name=sheet_name[:31])
                chat_buffer.seek(0)
                
                # Extract valid IDs from the ALREADY FILTERED chat dataframe
                df_chat_valid = df_chat.dropna(subset=['Booking/Lead ID']).copy()
                df_chat_valid['Clean_ID'] = df_chat_valid['Booking/Lead ID'].apply(clean_id_str)
                df_chat_valid = df_chat_valid[df_chat_valid['Clean_ID'] != '']
                df_chat_valid = df_chat_valid.sort_values(by='DateTime', ascending=False).drop_duplicates(subset=['Clean_ID'], keep='first')
                
                # This mapping ONLY contains messages from the filtered date range!
                msg_mapping = dict(zip(df_chat_valid['Clean_ID'], df_chat_valid['Message']))

                # --- PENDENCY PROCESSING ---
                pendency_buffer = None
                if pendency_file:
                    df_pen = pd.read_excel(pendency_file)
                    lead_col = [c for c in df_pen.columns if 'lead' in str(c).lower()][0]
                    
                    remarks_col = next((c for c in df_pen.columns if 'remark' in str(c).lower()), 'Remarks')
                    pendency_col = next((c for c in df_pen.columns if 'pendency' in str(c).lower()), 'Pendency')
                    exp_date_col = next((c for c in df_pen.columns if 'expected' in str(c).lower()), 'Expected appointment')
                    work_date_col = next((c for c in df_pen.columns if 'work date' in str(c).lower()), 'Work Date')
                    
                    for col in [remarks_col, pendency_col, exp_date_col]:
                        if col not in df_pen.columns: df_pen[col] = ""
                    
                    df_pen['Clean_LeadId'] = df_pen[lead_col].apply(clean_id_str)
                    
                    # Fill Remarks (It will use "Agent not shared remarks" if the message was filtered out by date)
                    df_pen[remarks_col] = df_pen['Clean_LeadId'].apply(lambda cid: msg_mapping.get(cid, "Agent not shared remarks on whatsapp") if cid else "")
                    
                    # Apply final logic
                    df_pen[[pendency_col, exp_date_col]] = df_pen.apply(lambda r: analyze_pendency_and_date(r, pendency_col, exp_date_col, work_date_col, remarks_col), axis=1, result_type='expand')
                    df_pen = df_pen.drop(columns=['Clean_LeadId'])
                    
                    pendency_buffer = io.BytesIO()
                    df_pen.to_excel(pendency_buffer, index=False, engine='openpyxl')
                    pendency_buffer.seek(0)

                st.success("✅ Evaluated Chat and Pendency Update Complete!")
                
                c1, c2 = st.columns(2)
                with c1:
                    st.download_button("📥 1. Download Evaluated WhatsApp Chat", data=chat_buffer, file_name="Evaluated_Chat_Log.xlsx")
                with c2:
                    if pendency_buffer:
                        st.download_button("📥 2. Download Updated Pendency Sheet", data=pendency_buffer, file_name="Updated_Pendency_List.xlsx")
                        
            except Exception as e:
                st.error(f"Error processing files: {e}")
