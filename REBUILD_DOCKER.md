# Rebuilding Docker Containers

## The Problem

Your logs show the disc is being detected, but the new TV detection code isn't running. This is because Docker containers need to be rebuilt to include the updated code.

## Quick Fix (Recommended)

**1. Create .env file with your TheTVDB API key:**

```bash
cd "C:\Users\Aaron Clarkson\Documents\boz-ripper"
```

Create a file named `.env` with:
```
BOZ_THETVDB_API_KEY=your_actual_api_key_here
```

Or copy from the template:
```bash
cp .env.example .env
# Then edit .env and add your API key
```

**2. Rebuild and restart containers:**

```bash
# Stop existing containers
docker compose down

# Rebuild with new code
docker compose build --no-cache

# Start containers
docker compose up -d

# Watch logs to verify
docker compose logs -f server
```

## What to Look For

After rebuilding, when you insert the "OFFICE" disc, you should see:

```
========================================
DISC DETECTED ENDPOINT
Disc Name: OFFICE
Disc Type: DVD
Agent: aaron-pc
Drive: D:
Titles: 4
========================================
Triggering preview generation for new disc: 0b5b875e-316a-4862-bbcd-2be9057100c3
========================================
PREVIEW GENERATION START
Disc: OFFICE (ID: 0b5b875e-316a-4862-bbcd-2be9057100c3)
Titles: 4
========================================
STEP 1: TV Show Detection
TV detection: Analyzing disc name: 'OFFICE'
TV detection: Ambiguous name detected, will search TheTVDB - Show: 'OFFICE', Season: 1 (assumed)
Result: is_tv=True, show_name=OFFICE, season=1
✓ Detected TV show: OFFICE, Season 1
```

## If You Don't See These Logs

**Problem:** New code not loaded

**Solution:**
```bash
# Force rebuild without cache
docker compose build --no-cache --pull

# Restart
docker compose up -d
```

**Problem:** TheTVDB API key not set

**Solution:**
1. Check `.env` file exists
2. Verify API key is correct
3. Restart containers: `docker compose restart server`

**Problem:** Logging level too low

**Solution:**
```bash
# Edit docker-compose.yml and change:
BOZ_DEBUG=true

# Restart
docker compose restart server
```

## Verify API Key is Set

Check if the container sees your API key:

```bash
docker compose exec server env | grep THETVDB
```

Should output:
```
BOZ_THETVDB_API_KEY=your_key_here
```

## Quick Test After Rebuild

1. **Check server startup logs:**
   ```bash
   docker compose logs server | grep -i thetvdb
   ```

   Should see:
   ```
   INFO: TheTVDB API key configured, initializing client
   ```

2. **Insert disc and watch logs:**
   ```bash
   docker compose logs -f server
   ```

3. **Check disc in dashboard:**
   - Should show "TV Show" badge
   - Should have episode names
   - Should show "Pending Review" status

## Full Clean Rebuild (Nuclear Option)

If nothing else works:

```bash
# Stop and remove everything
docker compose down -v

# Remove old images
docker compose rm -f
docker rmi boz-ripper-server boz-ripper-dashboard

# Rebuild from scratch
docker compose build --no-cache --pull

# Start fresh
docker compose up -d
```

## Troubleshooting Commands

```bash
# View all server logs
docker compose logs server

# View last 100 lines
docker compose logs --tail=100 server

# Follow logs in real-time
docker compose logs -f server

# Check container status
docker compose ps

# Check container environment
docker compose exec server env

# Shell into server container
docker compose exec server bash
```

## Why This Happens

Docker builds an image with your code at build time. When you update the code:
1. The files on your host change ✅
2. But the Docker container still has the old code ❌
3. You must rebuild the image to include new code ✅

## After Successful Rebuild

You should see:
- ✅ Detailed logs with `========` markers
- ✅ "TV Show" detection for "OFFICE"
- ✅ TheTVDB queries in logs
- ✅ Episode names instead of "Title 0, Title 1"
- ✅ Preview page with episode information

The logs will be **much more verbose** and tell you exactly what's happening at each step!
