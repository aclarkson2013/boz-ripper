# Season/Episode Manual Controls - Implementation Plan

## Problem Statement

Multi-disc TV seasons are being misidentified. For example:
- Season 2, Disc 1 detected as S01E07-S01E12 instead of S02E01-S02E06
- Episode names are wrong
- All confidence scores show "Low (30%)"

**Root Cause**: No way to specify which season and which episodes a disc contains.

## Solution: Manual Season/Episode Controls

Add UI controls to let users specify:
1. **Season number** (1-20)
2. **Starting episode** number (1, 7, 13, etc.)

When changed, re-query TheTVDB for the correct season and re-match episodes.

## Implementation Status

###  COMPLETED

1. **✅ Disc Model Updated** (`server/src/boz_server/models/disc.py`)
   - Added `starting_episode_number: Optional[int]` field
   - Stores user-specified starting episode

2. **✅ Episode Matcher Enhanced** (`server/src/boz_server/services/episode_matcher.py`)
   - Added `starting_episode` parameter to `match_episodes()`
   - Improved confidence calculation per user requirements:
     - **High (95%)**: Within 10% OR 2 minutes
     - **Medium (70%)**: Within 20% OR 5 minutes
     - **Low (40%)**: 20-50% difference
     - **Very Low (30%)**: >50% difference
   - Added `get_confidence_symbol()` for ✓ ~ ⚠ ✗ indicators
   - Logs now show S02E07 format

### ⏳ IN PROGRESS / TODO

3. **⏳ Preview Generator Update** (`server/src/boz_server/services/preview_generator.py`)
   - Need to pass `disc.starting_episode_number` to episode matcher
   - Update line ~160:
   ```python
   # OLD:
   self.episode_matcher.match_episodes(main_titles, tv_season)

   # NEW:
   self.episode_matcher.match_episodes(
       main_titles,
       tv_season,
       starting_episode=disc.starting_episode_number
   )
   ```

4. **⏳ API Endpoint** (`server/src/boz_server/api/discs.py`)
   - Add `POST /api/discs/{disc_id}/preview/update-season`
   - Endpoint should:
     - Accept `season_number` and `starting_episode`
     - Update `disc.tv_season_number` and `disc.starting_episode_number`
     - Re-fetch TheTVDB episodes for the correct season
     - Re-run episode matching with new starting_episode
     - Return updated disc with new episode assignments

   ```python
   @router.post("/{disc_id}/preview/update-season")
   async def update_season_and_episode(
       disc_id: str,
       request: SeasonEpisodeUpdate,  # season_number, starting_episode
       job_queue: JobQueueDep,
       preview_generator: PreviewGeneratorDep,
       _: ApiKeyDep,
   ) -> Disc:
       disc = job_queue.get_disc(disc_id)
       if not disc:
           raise HTTPException(404, "Disc not found")

       # Update season and starting episode
       disc.tv_season_number = request.season_number
       disc.starting_episode_number = request.starting_episode

       # Re-generate preview with new settings
       disc = await preview_generator.regenerate_preview(disc)

       return disc
   ```

5. **⏳ Dashboard Preview Page UI** (`dashboard/templates/disc_preview.html`)
   - Add controls above the track table:

   ```html
   <!-- Season/Episode Controls -->
   <div class="season-controls mb-3">
       <div class="row">
           <div class="col-md-3">
               <label for="seasonSelect">Season:</label>
               <select id="seasonSelect" class="form-control">
                   <option value="1">Season 1</option>
                   <option value="2">Season 2</option>
                   <!-- ... up to 20 -->
               </select>
           </div>
           <div class="col-md-3">
               <label for="episodeSelect">Starting Episode:</label>
               <select id="episodeSelect" class="form-control">
                   <option value="1">Episode 1</option>
                   <option value="7">Episode 7</option>
                   <option value="13">Episode 13</option>
                   <option value="19">Episode 19</option>
               </select>
           </div>
           <div class="col-md-3 align-self-end">
               <button id="updateSeasonBtn" class="btn btn-primary">
                   Update Season/Episodes
               </button>
           </div>
       </div>
   </div>
   ```

   - Add JavaScript to handle updates:

   ```javascript
   document.getElementById('updateSeasonBtn').addEventListener('click', async () => {
       const season = document.getElementById('seasonSelect').value;
       const episode = document.getElementById('episodeSelect').value;

       const response = await fetch(`/api/discs/${discId}/preview/update-season`, {
           method: 'POST',
           headers: { 'Content-Type': 'application/json' },
           body: JSON.stringify({
               season_number: parseInt(season),
               starting_episode: parseInt(episode)
           })
       });

       if (response.ok) {
           const updatedDisc = await response.json();
           // Refresh the track table with new episode assignments
           refreshTrackTable(updatedDisc);
       }
   });
   ```

6. **⏳ Request Model** (`server/src/boz_server/models/disc.py` or `api/discs.py`)
   ```python
   class SeasonEpisodeUpdate(BaseModel):
       season_number: int
       starting_episode: int = 1
   ```

## Testing Plan

### Test Case 1: Season 2, Disc 1 (Episodes 1-6)
1. Insert Season 2 disc
2. System auto-detects as S01E07-S01E12 (wrong)
3. User changes:
   - Season: 2
   - Starting Episode: 1
4. Click "Update Season/Episodes"
5. **Expected**: Episodes re-match to S02E01-S02E06
6. **Expected**: Episode names correct from TheTVDB
7. **Expected**: Confidence scores improve (High/Medium instead of Low)

### Test Case 2: Season 2, Disc 2 (Episodes 7-12)
1. Insert second disc of Season 2
2. Change:
   - Season: 2
   - Starting Episode: 7
3. **Expected**: S02E07-S02E12
4. **Expected**: Correct episode names

### Test Case 3: Confidence Indicators
1. Episodes with good duration match → ✓ High (95%)
2. Episodes within 20% → ~ Medium (70%)
3. Episodes >20% off → ⚠ Low (40%)
4. Episodes with no metadata → ✗ Very Low (30%)

## File Changes Summary

| File | Status | Changes |
|------|--------|---------|
| `server/src/boz_server/models/disc.py` | ✅ Done | Added `starting_episode_number` field |
| `server/src/boz_server/services/episode_matcher.py` | ✅ Done | Added `starting_episode` param, improved confidence |
| `server/src/boz_server/services/preview_generator.py` | ⏳ TODO | Pass `starting_episode_number` to matcher |
| `server/src/boz_server/api/discs.py` | ⏳ TODO | Add `POST /preview/update-season` endpoint |
| `dashboard/templates/disc_preview.html` | ⏳ TODO | Add Season/Episode dropdown controls |
| `dashboard/app.py` | ⏳ TODO | Add proxy route for update-season endpoint |

## Next Steps (Priority Order)

1. **Update preview_generator.py** - 1 line change to pass starting_episode
2. **Add API endpoint** - Create update-season endpoint
3. **Add UI controls** - Season/Episode dropdowns in preview page
4. **Test with real disc** - Verify Season 2 detection works
5. **Deploy and rebuild server**

## Future Enhancements (Optional)

1. **Smart Suggestions**:
   - Parse disc label: "OFFICE_S02" → suggest Season 2
   - Remember last disc: "Last was S01E06, suggest S01E07 or S02E01"
   - Auto-suggest starting episodes based on disc count (1, 7, 13, 19...)

2. **Validation**:
   - Warn if starting_episode > total episodes in season
   - Show episode count: "Season 2 has 22 episodes"

3. **Bulk Operations**:
   - "Apply to all pending discs from this show"
   - "Remember this setting for future discs"

## Known Limitations

- Requires manual user input for each disc
- No automatic detection of season from disc label (could be added)
- No persistence across server restarts (in-memory only)

## Confidence Calculation Details

**New Formula** (per user requirements):

```python
if duration_diff_seconds <= 120 or duration_diff_percent <= 0.10:
    # Within 2 minutes OR within 10%
    confidence = 0.95  # High
elif duration_diff_seconds <= 300 or duration_diff_percent <= 0.20:
    # Within 5 minutes OR within 20%
    confidence = 0.70  # Medium
elif duration_diff_percent <= 0.50:
    # Within 50%
    confidence = 0.40  # Low
else:
    # > 50% difference
    confidence = 0.30  # Very Low
```

**Why "OR" instead of "AND"**:
- Some shows have consistent episode lengths (e.g., 22 minutes) → percentage works
- Some shows vary widely (pilot 44 min, others 22 min) → absolute time works
- Using "OR" (whichever is MORE permissive) gives better results

## Example Log Output

**Before** (with auto-detection):
```
STEP 4: Episode Matching
Matching 6 titles to episodes, starting from episode 7 (auto-continue)
✗ Title 0 → S01E07 (duration mismatch: 30%)
✗ Title 1 → S01E08 (duration mismatch: 30%)
Sequential matching validation: 0/6 titles validated (0%)
⚠ Low validation rate - episodes may be mismatched
```

**After** (with manual S02E01):
```
STEP 4: Episode Matching
Matching 6 titles to episodes, starting from episode 1 (user-specified)
✓ Title 0 → S02E01: The Dundies (duration match: ±45s, 3.4%)
✓ Title 1 → S02E02: Sexual Harassment (duration match: ±23s, 1.7%)
~ Title 2 → S02E03: Office Olympics (duration acceptable: ±312s, 18.2%)
✓ Title 3 → S02E04: The Fire (duration match: ±67s, 5.1%)
Sequential matching validation: 6/6 titles validated (100%)
✓ Sequential matching looks good (100% validated)
```
