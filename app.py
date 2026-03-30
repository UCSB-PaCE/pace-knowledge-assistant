import streamlit as st
from mongodb_RAG import ZohoTicket

# Cache Resource allows the USER to only run the initilization of the chatbot once, and then reuse the same instance across multiple interactions, improving performance and user experience.
@st.cache_resource
def load_chatbot():
    return ZohoTicket()

st.set_page_config(page_title='MongoDB RAG Chatbot', page_icon='💬', layout="centered")

# Title
st.title('Zoho Tickets Chatbot!')
st.caption("Ask questions about your support tickets.")

# Input Box
question = st.text_input(label="Your Question", placeholder="E.g., Summarize Tickets for the last 10 days?")

chatbot = load_chatbot()

# Answer
if st.button("Ask", type="primary"):
    if not question.strip():
        st.warning("Please enter a question.")
    else:
        with st.spinner("Searching tickets and generating answer..."):
            answer = chatbot.ask(question)
        
        st.subheader("Answer")
        st.write(answer)


