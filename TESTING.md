# HonkBot Persistence Testing Guide

This guide provides step-by-step instructions for testing the Oracle DB persistence implementation.

## Prerequisites

Before testing:
1. Oracle Database instance is running and accessible
2. Environment variables are configured:
   - `DB_USER`
   - `DB_PASS`
   - `TNS_ADMIN`
   - `WALLET_PASS`
   - `DISCORD_TOKEN`
3. Oracle instant client is installed (required by oracledb)

## Installation

```bash
pip install -r requirements.txt
```

## Test 1: Schema Initialization

**Objective**: Verify database schema is created correctly

**Steps**:
1. Start the bot:
   ```bash
   python bot.py
   ```

2. Check logs for:
   ```
   INFO:honkbot:Connected to the database.
   INFO:honkbot:Initializing database schema...
   INFO:db_layer:Executed DDL: CREATE TABLE honkbot_user_honk_counts...
   ...
   INFO:db_layer:Database schema initialized successfully
   ```

3. Query the database to verify tables exist:
   ```sql
   SELECT table_name FROM user_tables WHERE table_name LIKE 'HONKBOT_%';
   ```

**Expected**: 15 tables created

## Test 2: State Persistence

**Objective**: Verify bot state is saved and restored

### 2a. User Honk Counts

**Steps**:
1. In Discord, trigger some honks (specific commands depend on bot implementation)
2. Check database:
   ```sql
   SELECT * FROM honkbot_user_honk_counts;
   ```
3. Restart bot
4. Check logs for:
   ```
   DEBUG:state.persistence:Loaded N user honk counts
   ```
5. Verify counts persisted after restart

### 2b. Cooldowns

**Steps**:
1. Trigger an action with a cooldown
2. Check database:
   ```sql
   SELECT * FROM honkbot_cooldowns;
   ```
3. Restart bot within cooldown period
4. Verify cooldown is still active

### 2c. Locks (Honklock/Echolock)

**Steps**:
1. Apply a honklock or echolock to a user
2. Check database:
   ```sql
   SELECT * FROM honkbot_honklocks;
   SELECT * FROM honkbot_echolocks;
   ```
3. Restart bot
4. Verify lock persists and user is still locked

## Test 3: Context Persistence

**Objective**: Verify conversation context is saved and restored

**Steps**:
1. Send several messages in channels where bot can see them
2. Wait 5+ minutes for periodic save (or trigger manual save if exposed)
3. Check database:
   ```sql
   SELECT COUNT(*) FROM honkbot_context_messages;
   SELECT * FROM honkbot_context_keywords;
   SELECT * FROM honkbot_learned_keywords;
   ```
4. Restart bot
5. Check logs for:
   ```
   INFO:media.context_persistence:Loaded N message history items
   INFO:media.context_persistence:Loaded N keyword counts
   ```
6. Verify context analyzer has historical data

## Test 4: Server Media Persistence

**Objective**: Verify server-uploaded media index is saved and restored

**Steps**:
1. Add server media (command depends on implementation)
2. Check database:
   ```sql
   SELECT * FROM honkbot_server_media;
   ```
3. Restart bot
4. Check logs for:
   ```
   INFO:media.provider_persistence:Loaded server media index: N entries...
   ```
5. Request media matching saved keywords
6. Verify uploaded media is returned

## Test 5: Retaliation System Persistence

**Objective**: Verify provocation scores and history are saved and restored

**Steps**:
1. Send messages that would trigger provocation scoring (mentions, insults, etc.)
2. Check database:
   ```sql
   SELECT * FROM honkbot_provocation_scores;
   SELECT * FROM honkbot_provocation_history;
   ```
3. Restart bot
4. Check logs for:
   ```
   INFO:retaliation.persistence:Loaded N provocation scores
   ```
5. Verify scores influence bot behavior after restart

## Test 6: Background Persistence Task

**Objective**: Verify periodic context saving works

**Steps**:
1. Start bot
2. Send messages continuously
3. Wait 5 minutes
4. Check logs for:
   ```
   DEBUG:utils.persistence_tasks:Periodic context snapshot saved
   ```
5. Verify this occurs every 5 minutes

## Test 7: Error Resilience

**Objective**: Verify bot handles DB failures gracefully

### 7a. DB Unavailable at Startup

**Steps**:
1. Stop Oracle database
2. Start bot
3. Verify bot starts with in-memory state (logs should show connection errors but no crash)
4. Restore database
5. Verify bot continues operating

### 7b. DB Failure During Operation

**Steps**:
1. Start bot normally
2. Stop Oracle database while bot is running
3. Trigger bot actions
4. Check logs for persistence errors (but bot should continue)
5. Restore database
6. Verify bot reconnects and resumes persistence

## Test 8: Data Cleanup

**Objective**: Verify automatic cleanup works

### 8a. Expired Cooldowns

**Steps**:
1. Add cooldowns to database with expired timestamps
2. Restart bot
3. Check logs for:
   ```
   DEBUG:state.persistence:Cleaned up N expired cooldowns
   ```
4. Verify expired cooldowns removed from database

### 8b. Old Provocation History

**Steps**:
1. Insert old history records (>30 days)
2. Trigger cleanup (or wait for automatic cleanup)
3. Verify old records removed

## Test 9: Performance

**Objective**: Verify performance is acceptable

**Steps**:
1. Generate high activity (many messages, honks, etc.)
2. Monitor CPU and memory usage
3. Check database connection count
4. Verify response times remain acceptable
5. Check logs for any performance warnings

## Test 10: Integration

**Objective**: Verify all systems work together

**Steps**:
1. Run bot for 24 hours with normal activity
2. Perform multiple restarts at random times
3. Verify:
   - State consistently restored
   - No data loss
   - Bot behavior consistent across restarts
   - All features working with persistence

## Troubleshooting

### Schema Creation Fails

**Symptoms**: "ORA-00955: name is already used by an existing object"

**Fix**: Expected on restart. If initial creation fails, check:
- Database permissions
- Table space availability
- Oracle instance health

### Data Not Persisting

**Symptoms**: Data lost after restart

**Check**:
1. Database connectivity during operation
2. Error logs for persistence exceptions
3. Transactions are committing (check db_layer.db_cursor)

### Performance Degradation

**Symptoms**: Bot slow, high DB load

**Check**:
1. Table sizes (especially history tables)
2. Index usage
3. Connection pool health
4. Query execution plans

### Connection Errors

**Symptoms**: "Failed to connect to the database"

**Check**:
1. Oracle instance running
2. Wallet files in TNS_ADMIN path
3. Credentials correct
4. Network connectivity

## Success Criteria

All tests pass if:
- ✅ Schema creates successfully
- ✅ All state types persist and restore correctly
- ✅ Bot survives database unavailability
- ✅ Automatic cleanup works
- ✅ Performance is acceptable
- ✅ No data loss across restarts
- ✅ CodeQL security scan shows 0 alerts

## Cleanup

To reset all persisted data:

```sql
-- Clear all HonkBot tables
TRUNCATE TABLE honkbot_user_honk_counts;
TRUNCATE TABLE honkbot_channel_honk_activity;
TRUNCATE TABLE honkbot_cooldowns;
TRUNCATE TABLE honkbot_takeover_thresholds;
TRUNCATE TABLE honkbot_recent_actions;
TRUNCATE TABLE honkbot_honklocks;
TRUNCATE TABLE honkbot_echolocks;
TRUNCATE TABLE honkbot_safety_state;
TRUNCATE TABLE honkbot_global_state;
TRUNCATE TABLE honkbot_context_messages;
TRUNCATE TABLE honkbot_context_keywords;
TRUNCATE TABLE honkbot_learned_keywords;
TRUNCATE TABLE honkbot_keyword_topics;
TRUNCATE TABLE honkbot_server_media;
TRUNCATE TABLE honkbot_provocation_scores;
TRUNCATE TABLE honkbot_provocation_history;
```

Or to completely remove:

```sql
-- Drop all HonkBot tables
DROP TABLE honkbot_user_honk_counts;
DROP TABLE honkbot_channel_honk_activity;
-- ... (repeat for all tables)
```
