
import streamlit as st

st.title("Board Game Rules Chat")

q = st.text_input("Ask a question")

if q:
    st.write("(RAG response here)")