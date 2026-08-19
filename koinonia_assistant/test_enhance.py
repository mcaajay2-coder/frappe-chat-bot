import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '.env'))

llm = ChatGroq(
    model="llama3-8b-8192",
    temperature=0,
    groq_api_key=os.getenv("GROQ_API_KEY")
)

ENHANCE_QUERY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a SQL query enhancement assistant for the KOINONIA Parish Assistant app.
The user asked a question about parish sacrament registries or family records.
Your job is to rewrite their question into a more precise, SQL-friendly version that:
- Refers explicitly to table entities (Family, Member, Baptism, Communion, Confirmation, Marriage, Anointing Of Sick, Death).
- Keeps the original intent but resolves any pronouns ("them", "those", "he", "she", "it") using the conversation history.

Conversation History:
{history_context}

Return only the enhanced question — no explanation or markdown."""),
    ("human", "User question: {question}"),
])

history_context = """User: anointing sick 2023 how many
Assistant: Total Count: 5"""

response = llm.invoke(ENHANCE_QUERY_PROMPT.format_messages(
    history_context=history_context,
    question="list them"
))

print("Enhanced:", response.content.strip())
