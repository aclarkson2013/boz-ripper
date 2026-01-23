# Debugging TV Show Detection

## What Changed

I've added comprehensive logging and an **ambiguous name fallback** to the TV detection system.

### New Features

1. **Ambiguous Name Detection:**
   - Short disc names (1-3 words) without movie indicators are now treated as potential TV shows
   - Examples: "OFFICE", "FRIENDS", "SUITS" will now trigger TheTVDB search
   - Assumes Season 1 by default

2. **Enhanced Logging:**
   - Every step of preview generation is now logged with clear markers
   - Shows TV detection results, TheTVDB queries, episode matching, etc.

## How to Debug

### 1. Check Server Logs

When you insert a disc named "OFFICE", you should now see:

```
========================================
DISC DETECTED ENDPOINT
Disc Name: OFFICE
Disc Type: DVD
Agent: agent-123
Drive: D:
Titles: 4
========================================
Triggering preview generation for new disc: abc-123
========================================
PREVIEW GENERATION START
Disc: OFFICE (ID: abc-123)
Titles: 4
========================================
STEP 1: TV Show Detection
TV detection: Analyzing disc name: 'OFFICE'
TV detection: Ambiguous name detected, will search TheTVDB - Show: 'OFFICE', Season: 1 (assumed)
Result: is_tv=True, show_name=OFFICE, season=1
✓ Detected TV show: OFFICE, Season 1
Season tracker: OFFICE:s1 (last_episode: 0)
STEP 2: TheTVDB Metadata Lookup
Searching TheTVDB for series: 'OFFICE'
✓ Found series on TheTVDB - ID: 73244
Fetching episodes for season 1
✓ Loaded 6 episodes from TheTVDB
  Episode 1: Pilot (22min)
  Episode 2: Diversity Day (22min)
  Episode 3: Health Care (22min)
  Episode 4: The Alliance (22min)
  Episode 5: Basketball (22min)
STEP 3: Extras Filtering
Analyzing 4 titles
✓ Identified 0 extras, 4 main titles
STEP 4: Episode Matching
Matching 4 main titles to episodes
✓ Episode matching complete
  Title 0 → Episode 1: Pilot (confidence: 0.90)
  Title 1 → Episode 2: Diversity Day (confidence: 0.90)
  Title 2 → Episode 3: Health Care (confidence: 0.90)
  Title 3 → Episode 4: The Alliance (confidence: 0.90)
STEP 5: Filename Generation
✓ Generated filenames for 4 titles
========================================
PREVIEW GENERATION COMPLETE
Media Type: tv_show
Preview Status: pending
TV Show: OFFICE S01
========================================
```

### 2. If You Don't See These Logs

**Possible Issues:**

1. **Preview Generator Not Initialized**
   - Check server startup logs for: `"TheTVDB API key configured, initializing client"`
   - If missing, your API key isn't set

2. **API Key Not Set**
   ```bash
   # Check environment variable
   echo $BOZ_THETVDB_API_KEY

   # Set it if missing
   export BOZ_THETVDB_API_KEY=your_api_key_here
   ```

3. **Server Not Running Updated Code**
   - Restart the server to load the new code
   - Check that you're running from the correct directory

### 3. Common Disc Name Patterns

| Disc Name | Detection Result | Notes |
|-----------|-----------------|-------|
| `OFFICE` | TV Show (Season 1) | Ambiguous fallback |
| `The Office S01` | TV Show (Season 1) | Explicit season pattern |
| `The Office Season 1` | TV Show (Season 1) | Explicit season pattern |
| `The Office Disc 1` | TV Show (Season 1) | Disc pattern |
| `Friends` | TV Show (Season 1) | Ambiguous fallback |
| `Inception (2010)` | Movie | Year indicator = movie |
| `Star Wars Blu-ray` | Movie | "Blu-ray" indicator = movie |
| `Breaking Bad Complete Series` | TV Show (Season 1) | Keyword pattern |

### 4. TheTVDB Search Results

The ambiguous detection will search TheTVDB with the exact disc name. For best results:

- **"OFFICE"** → May match "The Office" (US) or "The Office" (UK)
  - TheTVDB returns the most popular match first
  - Check logs to see which series was matched

- **Better Names:**
  - "The Office US S01" - More specific
  - "The Office (US)" - Differentiates from UK version
  - "Office Season 1" - Clear season indicator

### 5. Manual Override

If the detection is wrong, you can:

1. **Edit in Preview Page:**
   - Change episode numbers
   - Change episode titles
   - Edit filenames
   - Mark titles as extras

2. **Reject and Re-insert with Better Name:**
   - Reject the disc
   - Eject and relabel (if using MakeMKV rename)
   - Re-insert with better name

### 6. Checking Episode Matching

Look for these log lines:

```
STEP 4: Episode Matching
Matching 4 main titles to episodes
✓ Episode matching complete
  Title 0 → Episode 1: Pilot (confidence: 0.90)
```

**Confidence Scores:**
- **0.9+** (High) - Duration matches episode runtime within 20%
- **0.7+** (Medium) - Acceptable duration mismatch
- **0.5+** (Low) - Significant duration mismatch
- **0.3+** (Very Low) - No episode metadata available

Low confidence = review carefully in preview page!

### 7. Testing the Fix

1. **Stop the server** (Ctrl+C)
2. **Restart the server:**
   ```bash
   cd server
   python -m boz_server.main
   ```
3. **Insert "OFFICE" disc**
4. **Watch server logs** for the detailed output above
5. **Check dashboard** - Disc should show:
   - Media Type badge: "TV Show"
   - Preview Status: "Pending Review"
   - TV show panel with "OFFICE Season 1"

### 8. If TheTVDB Search Fails

**Logs will show:**
```
✗ Could not find series on TheTVDB: OFFICE
```

**Solutions:**

1. **Try more specific name:**
   - "The Office US"
   - "The Office (2005)"

2. **Check TheTVDB directly:**
   - Go to https://thetvdb.com/
   - Search for your show
   - Use the exact name from search results

3. **Check API key:**
   - Verify it's valid and not expired
   - Generate new key if needed

4. **Check network:**
   - Test API connectivity: `curl https://api4.thetvdb.com/v4`
   - Should return JSON response

## Expected Behavior Now

✅ **"OFFICE"** → Detected as TV Show, searches TheTVDB
✅ **"Friends"** → Detected as TV Show, searches TheTVDB
✅ **"Breaking Bad S01"** → Detected as TV Show with explicit season
✅ **"Inception (2010)"** → Detected as Movie (year indicator)
✅ **Comprehensive logs** at every step

## Still Not Working?

If you're still seeing "Unknown" type after these changes:

1. Share the **full server logs** from disc insertion
2. Check the exact disc name being sent by the agent
3. Verify the preview_generator is being called (look for "PREVIEW GENERATION START")

The logs will now tell us exactly where the detection is failing!
