# Episode Matching Fix - Sequential Order

## Problem

Episodes were being matched out of order because the matcher was sorting titles by duration (longest first) instead of by disc order (title index).

**Before:**
- Title 0 (longest) → Episode 1 ✓
- Title 1 (2nd longest) → Episode 4 ✗
- Title 2 (3rd longest) → Episode 2 ✗
- Title 3 (4th longest) → Episode 6 ✗

This happened because the code was doing:
```python
sorted_titles = sorted(titles, key=lambda t: t.duration_seconds, reverse=True)
```

## Solution

DVDs have episodes in sequential order by title index. The fix:

1. **Sort by title index** (disc order) instead of duration
2. **Match sequentially**: Title 0 → Episode 1, Title 1 → Episode 2, etc.
3. **Validate duration** is within 5 minutes of expected
4. **Report validation rate** to warn if something seems wrong

**After:**
- Title 0 → Episode 1 ✓
- Title 1 → Episode 2 ✓
- Title 2 → Episode 3 ✓
- Title 3 → Episode 4 ✓

## What Changed

**File:** `server/src/boz_server/services/episode_matcher.py`

**Key Changes:**
1. Sort by `t.index` instead of `t.duration_seconds`
2. Use 5-minute tolerance (300 seconds) for validation
3. Enhanced logging with validation symbols
4. Calculate validation rate to detect issues

## New Logging Output

You'll now see detailed matching info:

```
Matching 6 titles to episodes, starting from episode 1
Using sequential matching strategy (disc order)
Titles sorted by index: [0, 1, 2, 3, 4, 5]

✓ Title 0 → Episode 1: Pilot (duration match: ±45s, 3.4%)
✓ Title 1 → Episode 2: Diversity Day (duration match: ±23s, 1.7%)
✓ Title 2 → Episode 3: Health Care (duration match: ±12s, 0.9%)
~ Title 3 → Episode 4: The Alliance (duration acceptable: ±340s, 25.8%)
✓ Title 4 → Episode 5: Basketball (duration match: ±67s, 5.1%)
⚠ Title 5 → Episode 6: Hot Girl (duration mismatch: ±890s, 67.4%)

Sequential matching validation: 5/6 titles validated (83%)
✓ Sequential matching looks good (83% validated)
```

**Validation Symbols:**
- `✓` = High confidence (within 5 minutes)
- `~` = Medium confidence (within 20% but >5 minutes)
- `⚠` = Low confidence (20-50% difference)
- `✗` = Very low confidence (>50% difference)
- `?` = No metadata to validate

**Validation Rate:**
- **80%+** = Good - sequential matching is working
- **50-80%** = Acceptable - review low-confidence matches
- **<50%** = Warning - episodes may be out of order, manual review needed

## Confidence Scoring

**High (0.9):**
- Duration within 5 minutes of expected
- Green checkmark in preview

**Medium (0.7):**
- Duration within 20% but more than 5 minutes off
- Yellow indicator in preview

**Low (0.5):**
- Duration 20-50% different
- Orange warning in preview

**Very Low (0.3):**
- Duration >50% different OR no metadata
- Red warning in preview - review carefully!

## Testing the Fix

**1. Rebuild Docker containers:**
```bash
docker compose down
docker compose build --no-cache server
docker compose up -d
```

**2. Insert your "OFFICE" disc again**

**3. Watch logs:**
```bash
docker compose logs -f server | grep -A 20 "STEP 4"
```

**4. Expected output:**
```
STEP 4: Episode Matching
Matching 6 titles to episodes
Using sequential matching strategy (disc order)
Titles sorted by index: [0, 1, 2, 3, 4, 5]
✓ Title 0 → Episode 1: Pilot
✓ Title 1 → Episode 2: Diversity Day
✓ Title 2 → Episode 3: Health Care
✓ Title 3 → Episode 4: The Alliance
✓ Title 4 → Episode 5: Basketball
✓ Title 5 → Episode 6: Hot Girl
Sequential matching validation: 6/6 titles validated (100%)
✓ Sequential matching looks good (100% validated)
```

**5. Check dashboard:**
- Episodes should be in order: E01, E02, E03, E04, E05, E06
- Confidence indicators should be mostly green
- Preview page should show correct episode names

## Edge Cases Handled

**Multi-disc seasons:**
- Continues from last episode on previous disc
- Example: Disc 1 ends at E08, Disc 2 starts at E09

**Missing metadata:**
- Episodes beyond TheTVDB data get "Episode N" names
- Low confidence score warns user to review

**Duration mismatches:**
- Commercial cuts or extended editions may not match exactly
- Validation rate warns if many titles don't validate
- User can manually correct in preview page

**Out-of-order discs:**
- If validation rate <50%, logs warning
- User should check episode numbers in preview
- Can manually reorder if needed

## Fallback Behavior

If sequential matching produces a low validation rate (<50%), the system will:
1. Log a warning in server logs
2. Still use sequential matching (user can fix in preview)
3. Show low confidence scores in UI
4. Alert user to review carefully

**No automatic duration-based fallback** because:
- DVDs are almost always in order by index
- Duration-based matching often produces worse results
- Manual review in preview page is safer

## If Episodes Are Still Wrong

**Possible causes:**

1. **Disc actually has episodes out of order**
   - Some DVDs are mastered incorrectly
   - Solution: Manual correction in preview page

2. **Wrong show matched on TheTVDB**
   - "OFFICE" could match UK or US version
   - Solution: Use more specific name like "The Office US S01"

3. **Commercial cuts vs. streaming versions**
   - DVD episodes may be different length than TheTVDB data
   - Solution: Review confidence scores, manually adjust if needed

4. **Special editions or director's cuts**
   - Extended episodes won't match standard runtime
   - Solution: Check confidence, accept if episodes are in right order

## Manual Override

In the preview page, you can:
1. Edit episode numbers
2. Edit episode titles
3. Reorder episodes
4. Mark episodes as extras
5. Uncheck episodes to skip

All changes will be saved when you approve the preview.

## Summary

✅ **Fixed:** Episodes now match in disc order (Title 0→E01, Title 1→E02, etc.)
✅ **Improved:** 5-minute tolerance for duration validation
✅ **Enhanced:** Detailed logging with validation symbols
✅ **Added:** Validation rate to detect issues
✅ **Maintained:** User can still manually correct in preview page

The fix respects how DVDs are actually authored - with episodes in sequential order by title index!
