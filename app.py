import streamlit as st
import pandas as pd
import re
import io
import zipfile

# --- Page Configuration ---
st.set_page_config(page_title="WhatsApp Chat to Excel Converter", page_icon="💬", layout="centered")

st.title("💬 WhatsApp Chat to Excel Converter")
st.markdown("Upload your WhatsApp chat text file, pick your dates, and get a clean, date-wise Excel sheet.")

# --- Step 1: Upload File ---
st.subheader("Step 1: Upload WhatsApp Chat")
chat_file = st.file_uploader("Upload WhatsApp Chat (.txt or .zip)", type=["txt", "zip"])

# --- Step 2: Date Filtering ---
st.subheader("Step 2: Filter by Date (Optional)")
enable_date_filter = st.checkbox("Enable Date Filter", value=False)
start_date, end_date = None, None
if enable_date_filter:
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date")
    with col2:
        end_date = st.date_input("End Date")

# --- Helper Functions ---
def extract_id(msg):
    # Hunt for Booking ID / Lead ID
    match = re.search(r'(?i)(?:booking|lead|case|ticket)\s*i[\'d]?\s*[:-]*\s*([a-zA-Z0-9]+)', str(msg))
    if match: return match.group(1).strip()
    # Or hunt for a standalone 7-11 digit number at the start
    match2 = re.match(r'^(\d{7,11})\b', str(msg).strip())
    if match2: return match2.group(1).strip()
    return ""

def clean_message_text(msg, lead_id=""):
    cleaned = str(msg)
    
    # 1. Remove all @ tags (names and numbers)
    cleaned = re.sub(r'@\u2068.*?\u2069', '', cleaned)
    cleaned = re.sub(r'@[A-Za-z0-9_~\.\-\s]+(?=\n|$|@)', '', cleaned)
    cleaned = re.sub(r'@\d+', '', cleaned)
    
    # 2. Remove the Lead ID text from the message body
    cleaned = re.sub(r'(?i)(?:booking|lead|case|ticket|I\'d)\s*(?:id|i\'d|no)?\s*[:-]*\s*([a-zA-Z0-9]+)', '', cleaned)
    cleaned = re.sub(r'^(\d{7,11})\b', '', cleaned.strip())
    if lead_id and str(lead_id) in cleaned:
        cleaned = cleaned.replace(str(lead_id), '')
        
    # 3. Remove invisible WhatsApp characters
    cleaned = re.sub(r'[\u200e\u202a\u202c\u202d\u2069\u2068]', '', cleaned)
    
    # 4. Clean up blank lines, dashes, and 'image omitted'
    lines = cleaned.split('\n')
    final_lines = []
    for l in lines:
        l = re.sub(r'^[-\s:/]+', '', l) 
        l = re.sub(r'[-\s:/]+$', '', l) 
        if l and l.lower() not in ['image omitted', 'audio omitted', 'video omitted', 'document omitted']:
            final_lines.append(l.strip())
            
    return '\n'.join(final_lines).strip()

def clean_time_string(t):
    return re.sub(r'[\u202f\u200e\u202a\u202c\u202d\u2069]', ' ', str(t))

# --- Step 3: Process & Download ---
st.subheader("Step 3: Process & Download")
if st.button("🚀 Convert to Excel", type="primary"):
    if not chat_file:
        st.error("⚠️ Please upload a WhatsApp Chat file first.")
    else:
        with st.spinner("Extracting and cleaning chat data..."):
            try:
                # 1. Read File
                if chat_file.name.endswith(".zip"):
                    with zipfile.ZipFile(chat_file) as z:
                        txt_name = [n for n in z.namelist() if n.endswith('.txt')][0]
                        with z.open(txt_name) as f: chat_text = f.read().decode("utf-8", errors="replace")
                else:
                    chat_text = chat_file.read().decode("utf-8", errors="replace")
                
                # 2. Parse Text
                parsed_data, cur_date, cur_time, cur_sender, cur_msg = [], "", "", "", []
                
                # Remove invisible chars before splitting
                clean_lines = [re.sub(r'[\u200e\u202a\u202c\u202d\u2069]', '', l).strip() for l in chat_text.split('\n') if l.strip()]
                
                for line in clean_lines:
                    # Match [DD/MM/YY, HH:MM:SS] format
                    match = re.match(r'^\[?(\d{2}/\d{2}/\d{2,4}),\s*(.*?)\]?\s*(.*?):\s*(.*)', line)
                    if not match: 
                        # Match DD/MM/YY, HH:MM - format
                        match = re.match(r'^(\d{2}/\d{2}/\d{2,4}),\s*(.*?)\s*-\s*(.*?):\s*(.*)', line)
                        
                    if match:
                        if cur_sender: parsed_data.append([cur_date, cur_time, cur_msg])
                        cur_date, cur_time, cur_sender, m = match.groups()
                        cur_msg = [m.strip()]
                    else:
                        if cur_sender: cur_msg.append(line)
                        
                if cur_sender: parsed_data.append([cur_date, cur_time, cur_msg])
                
                # 3. Create DataFrame
                df = pd.DataFrame(parsed_data, columns=['Date', 'Time', 'Raw_Message'])
                df['Raw_Message'] = df['Raw_Message'].apply(lambda x: '\n'.join(x))
                
                # Extract IDs and Clean Message
                df['Booking/Lead ID'] = df['Raw_Message'].apply(extract_id)
                df['Message'] = df.apply(lambda r: clean_message_text(r['Raw_Message'], r['Booking/Lead ID']), axis=1)
                
                # Format Dates safely
                df['Clean_Time'] = df['Time'].apply(clean_time_string)
                df['Date_Parsed'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce')
                
                # 4. Filter by Date (If enabled)
                if enable_date_filter and start_date and end_date:
                    df = df[(df['Date_Parsed'] >= pd.to_datetime(start_date)) & (df['Date_Parsed'] <= pd.to_datetime(end_date))]
                
                # Prepare Final Output
                df_out = df[['Date', 'Clean_Time', 'Booking/Lead ID', 'Message']].copy()
                df_out.rename(columns={'Clean_Time': 'Time'}, inplace=True)
                
                if not df_out.empty:
                    df_out['Date'] = df['Date_Parsed'].dt.strftime('%d-%m-%Y')
                
                # 5. Write to Excel
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    if df_out.empty:
                        pd.DataFrame({'Message':['No data found for these dates']}).to_excel(writer, index=False, sheet_name="No Data")
                    else:
                        # Create a sheet for every unique date
                        for date in sorted(df_out['Date'].dropna().unique()):
                            sheet_name = str(date).replace('/', '-')
                            df_date = df_out[df_out['Date'] == date].copy()
                            df_date.to_excel(writer, index=False, sheet_name=sheet_name[:31])
                
                excel_buffer.seek(0)
                
                st.success("✅ Chat processed and cleaned successfully!")
                
                # Download Button
                st.download_button(
                    label="📥 Download Excel Sheet",
                    data=excel_buffer,
                    file_name="Cleaned_WhatsApp_Data.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                # Show Preview
                st.subheader("Data Preview")
                st.dataframe(df_out.head(15))
                
            except Exception as e:
                st.error(f"Error processing file: {e}")
