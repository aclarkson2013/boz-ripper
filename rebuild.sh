#!/bin/bash
# Quick rebuild script for Boz Ripper Docker containers

set -e

echo "========================================="
echo "Boz Ripper - Docker Rebuild Script"
echo "========================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  WARNING: .env file not found!"
    echo "Creating .env from template..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ Created .env file"
        echo ""
        echo "⚠️  IMPORTANT: Edit .env and add your TheTVDB API key!"
        echo "   BOZ_THETVDB_API_KEY=your_key_here"
        echo ""
        read -p "Press Enter after you've added your API key to .env..."
    else
        echo "❌ .env.example not found. Please create .env manually."
        exit 1
    fi
fi

echo "1. Stopping containers..."
docker compose down

echo ""
echo "2. Rebuilding server (this may take a minute)..."
docker compose build --no-cache server

echo ""
echo "3. Rebuilding dashboard..."
docker compose build --no-cache dashboard

echo ""
echo "4. Starting containers..."
docker compose up -d

echo ""
echo "5. Waiting for server to start..."
sleep 5

echo ""
echo "========================================="
echo "✅ Rebuild complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Watch logs: docker compose logs -f server"
echo "  2. Insert 'OFFICE' disc"
echo "  3. Look for detailed logs with ======== markers"
echo "  4. Check dashboard at http://localhost:5000"
echo ""
echo "Checking server status..."
docker compose ps server

echo ""
echo "Checking if TheTVDB API key is set..."
API_KEY=$(docker compose exec -T server env | grep BOZ_THETVDB_API_KEY || echo "NOT_SET")
if [[ $API_KEY == *"NOT_SET"* ]] || [[ $API_KEY == *"your_"* ]]; then
    echo "❌ TheTVDB API key not set or still has placeholder value!"
    echo "   Edit .env and add your real API key, then run: docker compose restart server"
else
    echo "✅ TheTVDB API key is configured"
fi

echo ""
echo "To view logs: docker compose logs -f server"
