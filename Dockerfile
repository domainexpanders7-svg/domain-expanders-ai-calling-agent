FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PORT=7860

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Hugging Face Spaces runs as user 1000
RUN useradd -m -u 1000 user && \
    chown -R user:user /app
USER user

# Expose port
EXPOSE 7860

# Launch server
CMD ["python", "main.py"]
