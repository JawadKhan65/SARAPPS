# Calendar-Based Crawler Scheduler Implementation

## Overview
Implemented a user-friendly calendar-based scheduling system for web crawlers with automatic quarterly rescheduling.

## Features Implemented

### 1. **Calendar UI Component** (`admin/components/CrawlerScheduler.jsx`)
- **Date Picker**: Select any date from today to 3 months in the future
- **Time Picker**: Set exact time for crawler execution (default: 02:00 AM)
- **"Run Now" Button**: Schedule crawler to run immediately (+1 minute from now)
- **"Schedule" Button**: Schedule crawler for selected date and time
- **Visual Feedback**: Loading states, error messages, and success confirmations
- **Automatic Cron Generation**: Converts user-friendly date/time to cron expression

**Usage:**
```jsx
<CrawlerScheduler
    crawler={selectedCrawler}
    onClose={() => setScheduleModal(null)}
    onSchedule={async (crawlerId, cronExpression) => {
        await adminAPI.updateCrawlerConfig(crawlerId, {
            schedule_cron: cronExpression
        });
    }}
/>
```

### 2. **Automatic Quarterly Rescheduling** (`backend/services/crawler_scheduler.py`)

#### New Method: `_reschedule_quarterly(crawler_id)`
After each successful crawler run:
1. Calculates date **3 months (90 days)** from completion
2. Sets time to **2:00 AM** on that date
3. Generates new cron expression: `0 2 {day} {month} *`
4. Updates database with new schedule
5. Reschedules APScheduler job automatically

**Example:**
- Crawler completes: December 15, 2024
- Auto-reschedules for: March 15, 2025 at 2:00 AM
- Cron expression: `0 2 15 3 *`

#### Modified Method: `_execute_crawler(crawler_id)`
Added automatic rescheduling after successful runs:
```python
if result["success"]:
    logger.info(f"✅ Scheduled run completed for: {crawler_id}")
    # NEW: Automatically reschedule for 3 months later
    self._reschedule_quarterly(crawler_id)
```

### 3. **UI Integration** (`admin/app/crawlers/page.jsx`)

Added schedule button to each crawler card:
- **Calendar Icon Button**: Opens scheduling modal
- **Blue Accent**: Distinguishes from start/stop actions
- **Tooltip**: "Schedule Crawler" on hover

**Action Flow:**
1. User clicks calendar icon on crawler card
2. Modal opens with date/time pickers
3. User selects date/time or clicks "Run Now"
4. System generates cron expression
5. Updates crawler schedule via API
6. Modal closes and crawler list refreshes

## Technical Details

### Cron Expression Format
The system uses standard 5-field cron format:
```
{minute} {hour} {day-of-month} {month} *
```

**Examples:**
- `0 2 15 3 *` - March 15 at 2:00 AM
- `30 14 1 12 *` - December 1 at 2:30 PM
- `*/1 * * * *` - Every minute (for "Run Now")

### Dependencies
- **date-fns**: Date manipulation and formatting
  - `addMonths()`: Calculate future dates
  - `format()`: Format dates for input fields
  - Already included in `admin/package.json`

### Database Schema
Uses existing `Crawler` model fields:
- `schedule_cron`: Stores cron expression (VARCHAR)
- `next_run_at`: Timestamp of next scheduled run (TIMESTAMP)
- `is_active`: Must be true for scheduling (BOOLEAN)

## Usage Guide

### For Administrators

#### Schedule a Crawler:
1. Navigate to **Crawlers** page
2. Find desired crawler in list
3. Click **calendar icon** button
4. Choose scheduling option:
   - **Pick Date/Time**: Select specific date and time
   - **Run Now**: Click to schedule immediate execution
5. Click **"Schedule"** button
6. System confirms and shows next run time

#### What Happens After Run:
- Crawler executes at scheduled time
- Upon successful completion, **automatically reschedules for 3 months later**
- No manual intervention needed
- Check "Next Run" field to verify rescheduling

### For Developers

#### Testing the Scheduler:
```bash
# Check scheduler initialization
tail -f backend/logs/app.log | grep "scheduler"

# Test immediate run
1. Click calendar icon on any crawler
2. Click "Run Now" button
3. Watch logs for execution (~1 minute)
4. Verify auto-rescheduling occurs after completion
```

#### API Endpoint:
```javascript
// Update crawler schedule
PUT /api/admin/crawlers/{id}/config
{
    "schedule_cron": "0 2 15 3 *"
}
```

## Future Enhancements (Not Yet Implemented)

### Staggered Scheduling
**Requirement:** "each scraper should have difference of 1 day between them"

**Planned Implementation:**
```python
def schedule_all_crawlers_staggered(base_date):
    """Schedule all crawlers with 1-day intervals"""
    crawlers = Crawler.query.filter_by(is_active=True).all()
    
    for index, crawler in enumerate(crawlers):
        # Stagger by 1 day per crawler
        schedule_date = base_date + timedelta(days=index)
        schedule_date = schedule_date.replace(hour=2, minute=0)
        
        cron = f"0 2 {schedule_date.day} {schedule_date.month} *"
        add_crawler_job(crawler.id, cron)
```

**UI Addition:**
- "Schedule All Crawlers" button on crawlers page
- Opens date picker for base date
- Automatically staggers all active crawlers from that date

## Files Modified

### Backend
- `backend/services/crawler_scheduler.py`
  - Added `timedelta` import
  - Added `_reschedule_quarterly()` method
  - Modified `_execute_crawler()` to call reschedule after success

### Frontend (Admin)
- `admin/components/CrawlerScheduler.jsx` - **CREATED**
  - Full calendar-based scheduling modal
  - Date/time pickers with validation
  - "Run Now" and "Schedule" actions
  
- `admin/app/crawlers/page.jsx`
  - Imported `CrawlerScheduler` component
  - Added `scheduleModal` state
  - Added calendar button to crawler cards
  - Added modal rendering with API integration

## Testing Checklist

- [x] Calendar UI opens when clicking schedule button
- [x] Date picker restricts to today through +3 months
- [x] Time picker accepts valid times
- [x] "Run Now" schedules for immediate execution
- [x] Cron expression generates correctly
- [x] Scheduler initializes on app startup
- [ ] Crawler executes at scheduled time (needs real-time test)
- [ ] Auto-rescheduling triggers after successful run (needs real-time test)
- [ ] Database updates with new schedule (needs real-time test)
- [ ] Error handling for failed runs (needs testing)

## Logs to Monitor

```bash
# Scheduler initialization
🟢 Crawler scheduler started
📅 Loading crawler schedules from database...
✅ Loaded {N} crawler schedules

# Scheduled execution
🔔 Scheduled execution triggered for crawler: {crawler_id}
✅ Scheduled run completed for: {crawler_id}

# Auto-rescheduling
🔄 Auto-rescheduling {crawler_id} for {date}
✅ Auto-reschedule complete: {cron_expression}
```

## Known Limitations

1. **No Validation for Past Dates**: Backend accepts any cron expression (UI prevents but API doesn't validate)
2. **Single Run Per Cron**: Each cron only runs once per matching time (not recurring)
3. **Month-Specific Scheduling**: Cron includes specific month, won't repeat yearly
4. **No Conflict Detection**: Multiple crawlers can be scheduled for same time
5. **No Timezone Awareness**: Uses server timezone for all scheduling

## Recommendations

### Immediate:
- Test with real crawler execution
- Monitor logs during scheduled runs
- Verify auto-rescheduling works as expected

### Short-term:
- Add backend validation for cron expressions
- Implement staggered scheduling for all crawlers
- Add notification when crawler completes and reschedules

### Long-term:
- Add recurring schedules (weekly, monthly, etc.)
- Implement timezone selection
- Add schedule conflict detection
- Create scheduling history/audit log
