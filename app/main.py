import streamlit as st
import pandas as pd
import difflib
import os
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai
from ai_faq import ask_policy_faq

# === CONFIG ===
DATA_FOLDER = "data"
LEAVE_DATA_FILE = os.path.join(DATA_FOLDER, "Sick_Leave_Data.xlsx")
RATE_DATA_FILE = os.path.join(DATA_FOLDER, "Sick_Pay_rates.xlsx")
LEAVE_LOG_FILE = os.path.join(DATA_FOLDER, "Leave_log.xlsx")

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(model_name="models/gemini-2.5-flash")

# === LOAD DATA ===
@st.cache_data
def load_data():
    leave_df = pd.read_excel(LEAVE_DATA_FILE)
    rate_df = pd.read_excel(RATE_DATA_FILE)

    leave_df.columns = leave_df.columns.str.strip()
    rate_df.columns = rate_df.columns.str.strip()

    leave_df['Clinician Name'] = leave_df['Clinician Name'].astype(str).str.strip()
    rate_df['Clinician Name'] = rate_df['Clinician Name'].astype(str).str.strip()
    leave_df['Time Off: Category'] = leave_df['Time Off: Category'].astype(str).str.strip()

    leave_df['Time Off: Available Balance'] = pd.to_numeric(leave_df['Time Off: Available Balance'], errors='coerce')
    leave_df['Time Off: Current Balance'] = pd.to_numeric(leave_df.get('Time Off: Current Balance'), errors='coerce')
    rate_df['Sick Pay Rate'] = pd.to_numeric(rate_df['Sick Pay Rate'], errors='coerce')

    return leave_df, rate_df

# === UTILITY FUNCTIONS ===
def match_name(name, names_list):
    matches = difflib.get_close_matches(name.lower().strip(), [n.lower().strip() for n in names_list], n=1, cutoff=0.6)
    return matches[0] if matches else None

def calculate_pay(clinician, rate_df, hours):
    row = rate_df[rate_df['Clinician Name'].str.lower().str.strip() == clinician.lower().strip()]
    if not row.empty:
        hourly_rate = float(row.iloc[0]['Sick Pay Rate'])
        return round(hourly_rate * float(hours), 2)
    return 0

def log_leave(clinician, category, hours, pay, balance_before):
    now = datetime.now().date()
    balance_after = balance_before - hours if category.lower() != "unpaid leave" else balance_before

    entry = pd.DataFrame([{
        "Clinician Name": clinician,
        "Date": now,
        "Balance Before": balance_before,
        "Balance After": balance_after,
        "Category": category,
        "Pay": pay
    }])

    os.makedirs(DATA_FOLDER, exist_ok=True)

    if os.path.exists(LEAVE_LOG_FILE):
        old = pd.read_excel(LEAVE_LOG_FILE)
        updated = pd.concat([old, entry], ignore_index=True)
    else:
        updated = entry

    updated.to_excel(LEAVE_LOG_FILE, index=False)

# === STREAMLIT UI ===
st.set_page_config(page_title="Clinician Leave Portal", layout="wide")
st.markdown("# 🩺 Clinician Leave Management System")
st.markdown("---")

leave_df, rate_df = load_data()
role = st.radio("Select your role:", ["Clinician", "Admin"], horizontal=True)

# === CLINICIAN VIEW ===
if role == "Clinician":
    tab1, tab2 = st.tabs(["📝 Leave Request", "🤖 AI FAQ - Sick Leave Policy"])

    with tab1:
        with st.expander("👤 Clinician Login", expanded=True):
            col1, col2 = st.columns([3, 2])
            name_input = col1.text_input("Enter your name:")
            matched_name = match_name(name_input, leave_df['Clinician Name'].tolist()) if name_input else None

        if matched_name:
            st.success(f"👋 Welcome, **{matched_name.title()}**!")
            clinician_rows = leave_df[leave_df['Clinician Name'].str.lower().str.strip() == matched_name.lower().strip()]
            categories = sorted(clinician_rows['Time Off: Category'].unique())

            category = st.selectbox("📂 Select Leave Category:", categories)
            record = clinician_rows[clinician_rows['Time Off: Category'].str.lower() == category.lower()]

            available_balance = float(record.iloc[0]['Time Off: Available Balance']) if not record.empty else 0.0
            if category.lower() != "unpaid":
                st.info(f"🧮 **Available Balance** for *{category}* leave: `{available_balance}` hours")

            requested_hours = float(st.number_input("⏱️ Enter leave hours to request:", min_value=0.0, step=0.5))

            # Session state
            if 'eligible' not in st.session_state:
                st.session_state.eligible = False
            if 'pending_pay' not in st.session_state:
                st.session_state.pending_pay = 0.0
            if 'pending_hours' not in st.session_state:
                st.session_state.pending_hours = 0.0
            if 'pending_category' not in st.session_state:
                st.session_state.pending_category = ""

            payable_categories = ["sick", "vacation f/t", "bereavement"]

            if requested_hours > 0:
                if st.button("🔎 Check Eligibility and Pay"):
                    category_clean = category.lower()
                    pay = 0

                    if category_clean == "unpaid leave":
                        st.info("ℹ️ Unpaid leave will be logged. No balance check or pay.")
                        st.session_state.eligible = True
                        st.session_state.pending_pay = 0
                        st.session_state.pending_hours = requested_hours
                        st.session_state.pending_category = category
                    elif requested_hours <= available_balance:
                        if category_clean in payable_categories:
                            pay = calculate_pay(matched_name, rate_df, requested_hours)
                            st.success(f"✅ You are eligible. Estimated Pay: **₹{pay}** for {requested_hours} hrs.")
                        else:
                            st.info(f"ℹ️ **No payment** for `{category}` leave. It will still be logged.")

                        st.session_state.eligible = True
                        st.session_state.pending_pay = pay
                        st.session_state.pending_hours = requested_hours
                        st.session_state.pending_category = category
                    else:
                        st.error("❌ Insufficient balance for requested hours.")
                        st.session_state.eligible = False

            if st.session_state.eligible:
                if st.button("📝 Confirm and Log Leave"):
                    log_leave(
                        matched_name,
                        st.session_state.pending_category,
                        st.session_state.pending_hours,
                        st.session_state.pending_pay,
                        balance_before=available_balance
                    )
                    st.success("📄 Leave logged successfully!")
                    st.session_state.eligible = False  # reset

        elif name_input:
            st.warning("⚠️ Clinician name not found. Please check spelling.")

        with tab2:
                st.markdown("## 🧠 Sick Leave AI Assistant")

                col1, col2 = st.columns(2)

        # ==== SECTION 1: Ask Your Own Question ====
        with col1:
            st.markdown("### 💬 Ask a Question")
            user_question = st.text_input("Type your question about NJ sick leave policy:")
            if user_question:
                with st.spinner("AI is thinking..."):
                    ai_answer = ask_policy_faq(user_question)
                    st.markdown("#### 🤖 AI Response")
                    st.success(ai_answer)

        # ==== SECTION 2: Common Questions (Dropdowns) ====
        with col2:
            st.markdown("### 📚 Common Questions")

            pre_answered_faqs = [
                {
                    "question": "How many hours of sick leave am I entitled to in NJ?",
                    "answer": "You are entitled to up to 40 hours of paid sick leave per year in New Jersey."
                },
                {
                    "question": "Can unused sick leave be carried over?",
                    "answer": "Yes, up to 40 hours of unused sick leave can be carried over to the next benefit year, "
                            "but your employer is not required to let you use more than 40 hours in a year."
                },
                {
                    "question": "What reasons can I use sick leave for?",
                    "answer": "You can use sick leave for your own illness, to care for a family member, for school closures, "
                            "for domestic/sexual violence recovery, and more."
                },
                {
                    "question": "Can I be fired for taking sick leave?",
                    "answer": "No. It is illegal for your employer to retaliate against you for using earned sick leave."
                }
            ]

            questions = [faq["question"] for faq in pre_answered_faqs]
            selected_q = st.selectbox("Choose a common question:", ["-- Select a question --"] + questions)

            if selected_q != "-- Select a question --":
                selected_answer = next((faq["answer"] for faq in pre_answered_faqs if faq["question"] == selected_q), "")
                st.markdown("#### 👉 Answer")
                st.info(selected_answer)



# === ADMIN VIEW ===
elif role == "Admin":
    tab1, tab2, tab3 = st.tabs(["📋 Leave Data", "📈 Pay Rates", "🤖 Gemini AI Insights"])

    with tab1:
        st.markdown("### 🗂️ Full Leave Records")
        st.dataframe(leave_df, use_container_width=True)

        st.markdown("### 🧾 Leave Log History")
        if os.path.exists(LEAVE_LOG_FILE):
            log_df = pd.read_excel(LEAVE_LOG_FILE)
            st.dataframe(log_df, use_container_width=True)
        else:
            st.info("No leave log available yet.")

    with tab2:
        st.markdown("### 💰 Clinician Sick Pay Rates")
        st.dataframe(rate_df, use_container_width=True)

    with tab3:
        st.markdown("### 💡 Ask Gemini AI about leave data")
        prompt = st.text_area("Ask a question (based on leave/pay data):")
        if prompt:
            context = leave_df.to_string(index=False) + "\n" + rate_df.to_string(index=False)
            gemini_prompt = f"You are a data assistant. Answer only based on this Excel data:\n\n{context}\n\nQuestion: {prompt}"
            response = model.generate_content(gemini_prompt)
            st.markdown("#### 🤖 Gemini's Answer")
            st.write(response.text)
