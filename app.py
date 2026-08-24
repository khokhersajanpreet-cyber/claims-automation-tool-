import streamlit as st
import pandas as pd
import re
import io
import zipfile

# --- Page Configuration ---
st.set_page_config(page_title="WhatsApp Chat to Excel Converter", page_icon="💬", layout="centered")

st.title("💬 WhatsApp Chat to Excel Converter")
st.markdown("Convert your raw WhatsApp chat into a clean, date-filtered Excel sheet. No tags, no IDs in the message, and perfectly split columns.")

# --- Step 1: Upload File ---
st.subheader("Step 1: Upload File")
chat_file = st.file_uploader("Upload WhatsApp Chat (.txt or .zip)", type=["txt", "zip"])

# --- Step 2: Date Filtering ---
st.subheader("Step 2: Select Date Range")
st.markdown("Only messages within this exact date range will be exported.")
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start Date")
with col2:
    end_date = st.date_input("End Date")

# --- Helper Functions ---
def extract_id(msg):
    # Hunt for Booking/Lead ID
    match = re.search(r'(?i)(?:booking|lead|case|ticket)\s*i[\'d]?\s*[:-]*\s*([a-zA-Z0-9]+)', str(msg))
    if match: return match.group(1).strip()
    match2 = re.match(r'^(\d{7,11})\b', str(msg).strip())
    if match2: return match2.group(1).strip()
    return ""

def clean_message_text(msg, lead_id=""):
    cleaned = str(msg)
    
    # 1. Remove WhatsApp Specific Tags first (the hidden characters)
    cleaned = re.sub(r'@\u2068.*?\u2069', '', cleaned)
    # Remove normal @ tags (e.g., @Name)
    cleaned = re.sub(r'@[^\s]+', '', cleaned)
    
    # 2. Clean out Unicode formatting characters
    cleaned = re.sub(r'[\u200e\u202a\u202c\u202d\u2069\u2068\u202f]', '', cleaned)
    
    # 3. Remove "Lead id: 1234", "Booking ID: 1234"
    cleaned = re.sub(r'(?i)(?:booking|lead|case|ticket)\s*i[\'d]?\s*[:-]*\s*([a-zA-Z0-9]+)', '', cleaned)
    
    # 4. Remove standalone numbers at the start of a line
    cleaned = re.sub(r'(?m)^(\d{7,11})\b', '', cleaned)
    
    # 5. Remove the exact lead id if it's still lingering
    if lead_id and str(lead_id) in cleaned:
        cleaned = cleaned.replace(str(lead_id), '')
        
    # 6. Remove any timestamps/dates that leaked into the message
    cleaned = re.sub(r'\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b', '', cleaned)
    cleaned = re.sub(r'\[\d{1,2}/\d{1,2}/\d{2,4}.*?\]', '', cleaned)
    
    # 7. Clean up lines and punctuation
    lines = cleaned.split('\n')
    final_lines = []
    for l in lines:
        l = re.sub(r'^[-\s:/,]+', '', l) # Remove leading dashes/colons/commas
        l = re.sub(r'[-\s:/,]+$', '', l) # Remove trailing dashes/colons/commas
        l = l.strip()
        ignore_list = ['image omitted', 'audio omitted', 'video omitted', 'document omitted', 'this message was deleted.']
        if l and l.lower() not in ignore_list:
            final_lines.append(l)
            
    return '\n'.join(final_lines).strip()

# --- Step 3: Process & Download ---
st.subheader("Step 3: Process & Download")
if st.button("🚀 Convert to Excel", type="primary"):
    if not chat_file:
        st.error("⚠️ Please upload a WhatsApp Chat file first.")
    else:
        with st.spinner("Extracting, filtering, and cleaning chat data..."):
            try:
                # Read the file
                if chat_file.name.endswith(".zip"):
                    with zipfile.ZipFile(chat_file) as z:
                        txt_name = [n for n in z.namelist() if n.endswith('.txt')][0]
                        with z.open(txt_name) as f: chat_text = f.read().decode("utf-8", errors="replace")
                else:
                    chat_text = chat_file.read().decode("utf-8", errors="replace")
                
                if not chat_text.strip():
                    st.error("⚠️ The uploaded file is empty.")
                    st.stop()
                
                parsed_data = []
                cur_date, cur_time, cur_sender, cur_msg = "", "", "", []
                
                raw_lines = chat_text.split('\n')
                
                for line in raw_lines:
                    line = line.strip()
                    if not line: continue
                    
                    # Universal Regex for both iOS and Android WhatsApp formats
                    match = re.match(r'^\[?(\d{1,2}/\d{1,2}/\d{2,4}),\s*([^\]\-]+)\]?\s*[-]?\s*(.*?):\s*(.*)', line)
                    
                    if match:
                        if cur_sender: 
                            parsed_data.append([cur_date, cur_time, cur_sender, '\n'.join(cur_msg)])
                        cur_date, cur_time, cur_sender, m = match.groups()
                        cur_sender = cur_sender.strip()
                        # Safely clean the time format
                        cur_time = re.sub(r'[\u202f\u200e\u202a\u202c\u202d\u2069]', ' ', cur_time).strip()
                        cur_msg = [m.strip()]
                    else:
                        # Check if it's a system message (No colon). If so, we completely ignore it.
                        sys_match = re.match(r'^\[?(\d{1,2}/\d{1,2}/\d{2,4}),\s*([^\]\-]+)\]?\s*[-]?\s*(.*)', line)
                        if sys_match:
                            continue
                        else:
                            if cur_sender: 
                                cur_msg.append(line)
                        
                if cur_sender: 
                    parsed_data.append([cur_date, cur_time, cur_sender, '\n'.join(cur_msg)])
                
                if not parsed_data:
                    st.error("⚠️ No valid WhatsApp messages found. Are you sure this is a WhatsApp export?")
                    st.stop()
                
                df = pd.DataFrame(parsed_data, columns=['Date', 'Time', 'Sender', 'Raw_Message'])
                
                # --- EXACT DATE FILTERING ---
                # This ensures ONLY the dates between start and end are kept
                df['Date_Parsed'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce').dt.date
                
                if start_date and end_date:
                    mask = (df['Date_Parsed'] >= start_date) & (df['Date_Parsed'] <= end_date)
                    df = df[mask]
                    
                if df.empty:
                    st.error(f"⚠️ No data found! There are no messages between {start_date.strftime('%d-%b-%Y')} and {end_date.strftime('%d-%b-%Y')} in this file.")
                    st.stop()
                    
                # Extract IDs and strictly clean the Message column
                df['Booking/Lead ID'] = df['Raw_Message'].apply(extract_id)
                df['Message'] = df.apply(lambda r: clean_message_text(r['Raw_Message'], r['Booking/Lead ID']), axis=1)
                
                # Remove blank messages
                df = df[df['Message'] != '']
                
                # Final Output Formatting: Just the 4 columns
                df_out = df[['Date', 'Time', 'Booking/Lead ID', 'Message']].copy()
                df_out['Date'] = pd.to_datetime(df_out['Date'], format='mixed', dayfirst=True).dt.strftime('%d-%m-%Y')
                
                # Generate Excel
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    for date in sorted(df_out['Date'].dropna().unique()):
                        sheet_name = str(date).replace('/', '-')
                        df_date = df_out[df_out['Date'] == date].copy()
                        df_date.to_excel(writer, index=False, sheet_name=sheet_name[:31])
                
                excel_buffer.seek(0)
                
                st.success("✅ Chat processed and cleaned successfully!")
                st.download_button(
                    label="📥 Download Cleaned Excel Sheet",
                    data=excel_buffer,
                    file_name="Cleaned_WhatsApp_Data.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                st.subheader("Data Preview")
                st.dataframe(df_out.head(15))
                
            except Exception as e:
                st.error(f"❌ An error occurred: {e}")
