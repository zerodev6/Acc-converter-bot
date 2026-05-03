# Use Python 3.11 slim image
FROM python:3.11-slim

# Install FFmpeg and ffprobe
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY bot.py .

# Expose port for Render health check
EXPOSE 8080

# Start the bot
CMD ["python", "bot.py"]
