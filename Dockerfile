# ── STAGE 1: Build the React Frontend ──
FROM node:20-alpine AS frontend-builder

# Set working directory for frontend
WORKDIR /app/frontend

# Copy npm package info and install
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install

# Copy the rest of the frontend code and build it
COPY frontend/ ./
RUN npm run build


# ── STAGE 2: Setup Python Backend & Serve ──
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Combine system updates and installs to reduce layers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the entire backend app
COPY . .

# Copy the compiled React files from the builder stage into the frontend/dist folder
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Expose the port Koyeb expects (8000)
EXPOSE 8000

# Start FastAPI using Uvicorn
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
