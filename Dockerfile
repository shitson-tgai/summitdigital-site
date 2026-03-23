FROM node:20-slim

# Install Python for audit scripts
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
RUN python3 -m pip install --break-system-packages requests beautifulsoup4

# Install Node dependencies
COPY package.json ./
RUN npm install --production

# Copy application code
COPY . .

EXPOSE 3000

CMD ["node", "server.js"]
