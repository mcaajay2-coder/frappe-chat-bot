# ==============================================================================
# KOINONIA ASSISTANT - CUSTOM PRODUCTION DOCKERFILE
# ==============================================================================
# Base image: Official Frappe ERPNext v16
FROM frappe/erpnext:v16.29.0

USER root

# 1. Install system utilities and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

USER frappe
WORKDIR /home/frappe/frappe-bench

# 2. Install AI and RAG Python dependencies into the bench virtualenv
RUN /home/frappe/frappe-bench/env/bin/pip install --no-cache-dir \
    langchain>=0.2.0 \
    langgraph>=0.1.0 \
    langchain-groq>=0.1.0 \
    sentence-transformers>=2.2.0 \
    psycopg2-binary>=2.9.0 \
    pgvector>=0.2.0 \
    requests>=2.28.0 \
    pydantic>=2.0.0

# 3. Copy Koinonia Assistant app into the bench apps directory
COPY --chown=frappe:frappe . /home/frappe/frappe-bench/apps/koinonia_assistant

# 4. Register app and build frontend assets
RUN echo "koinonia_assistant" >> /home/frappe/frappe-bench/sites/apps.txt && \
    /home/frappe/frappe-bench/env/bin/pip install -e /home/frappe/frappe-bench/apps/koinonia_assistant && \
    bench build --app koinonia_assistant

# 5. Set default entrypoint and user
EXPOSE 8000 8080 9000
USER frappe

CMD ["bench", "start"]
