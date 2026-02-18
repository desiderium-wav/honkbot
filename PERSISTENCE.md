# HonkBot Persistence System

This document describes the Oracle DB persistence implementation for HonkBot state and context.

## Overview

HonkBot now persists all critical state to an Oracle Database, ensuring data survives bot restarts. The persistence system includes:

1. **Bot State (state/memory.py)** - User honk counts, channel activity, cooldowns, locks, safety state
2. **Conversation Context (media/context.py)** - Message history, keyword tracking, learned topics
3. **Server Media (media/providers.py)** - User-uploaded media indexed by guild and keyword
4. **Retaliation System (retaliation/)** - Provocation scores and user behavior history

## Architecture

### Shared Database Layer (`db_layer.py`)

The `db_layer.py` module provides:
- Connection pooling and health checking
- Helper functions for common operations (upsert, fetch, delete)
- Schema initialization with DDL statements
- Automatic reconnection on connection failure
- Context managers for safe cursor management

All persistence modules use this layer instead of directly calling `db.py`.

### Database Schema

The schema includes 15 tables organized by functional area:

#### State/Memory Tables
- `honkbot_user_honk_counts` - Per-user honk counters
- `honkbot_channel_honk_activity` - Per-channel activity tracking
- `honkbot_cooldowns` - Action cooldowns with expiration
- `honkbot_takeover_thresholds` - Channel-specific takeover thresholds
- `honkbot_recent_actions` - Recent actions for anti-repetition
- `honkbot_honklocks` - User honklock state
- `honkbot_echolocks` - User echolock state
- `honkbot_safety_state` - Guild-level safety configuration
- `honkbot_global_state` - Global settings (e.g., safety enabled)

#### Media/Context Tables
- `honkbot_context_messages` - Rolling message history (last 1000)
- `honkbot_context_keywords` - Keyword frequency counts
- `honkbot_learned_keywords` - Keywords learned from conversation
- `honkbot_keyword_topics` - Custom keyword-to-topic mappings

#### Server Media Tables
- `honkbot_server_media` - Guild-uploaded media with keyword indexing

#### Retaliation Tables
- `honkbot_provocation_scores` - User provocation scores with timestamps
- `honkbot_provocation_history` - Message history for scoring (last 100 per user)

### Persistence Modules

Each functional area has its own persistence module:

#### `state/persistence.py`
- Loads all bot state on startup
- Saves state changes immediately (synchronous)
- Handles JSON serialization for complex types (sets, dicts)
- Cleans up expired cooldowns automatically

#### `media/context_persistence.py`
- Loads conversation history on startup
- Saves messages as they arrive
- Periodically snapshots keyword/topic state (every 5 minutes)
- Maintains rolling window of last 1000 messages

#### `media/provider_persistence.py`
- Loads server media index on ServerMediaProvider initialization
- Saves new media immediately when added
- Supports deletion by guild, keyword, or URL

#### `retaliation/persistence.py`
- Loads provocation scores on engine initialization
- Saves scores and history after each message evaluation
- Applies decay on score retrieval
- Cleans up old history (>30 days)

### Integration Points

#### Bot Startup (`bot.py`)
On bot ready:
1. Initialize database schema (idempotent)
2. Load state/memory persistence
3. Load context analyzer state
4. Initialize retaliation engine
5. Start periodic persistence background task

#### Runtime Hooks

**State/Memory:**
- Hooks added to setter functions in `state/memory.py`
- Changes persisted immediately on modification
- Lazy loading of persistence module to avoid circular imports

**Context Analyzer:**
- Messages saved in `add_message()` method
- Periodic snapshots every 5 minutes via `utils/persistence_tasks.py`
- Manual snapshot available via `persist_snapshot()` method

**Server Media:**
- Index loaded in `ServerMediaProvider.initialize()`
- Media saved in `add_media()` method

**Retaliation:**
- Scores loaded in `retaliation/engine.initialize()`
- Updates saved in `update_provocation_score()`

## Configuration

### Environment Variables

The following environment variables are required (already configured in `db.py`):

```
DB_USER=<oracle_username>
DB_PASS=<oracle_password>
TNS_ADMIN=<path_to_wallet>
WALLET_PASS=<wallet_password>
```

### Persistence Settings

Configurable in code:

- **Connection retry attempts**: `db_layer.get_db_connection(retries=3)`
- **Periodic save interval**: `utils/persistence_tasks.SAVE_INTERVAL_SECONDS = 300` (5 minutes)
- **Message history limit**: `media/context_persistence` maintains last 1000 messages
- **Provocation history per user**: Last 100 entries, >30 days auto-deleted

## Error Handling

The persistence system is designed to be resilient:

1. **Connection failures**: Automatic retry with exponential backoff
2. **Persistence errors**: Logged but don't crash the bot
3. **Schema initialization**: Idempotent DDL with "already exists" error suppression
4. **Data corruption**: Each module validates loaded data

All persistence operations are wrapped in try-except blocks to prevent DB issues from affecting bot functionality.

## Maintenance

### Schema Migrations

When adding new persisted fields:

1. Add DDL to `db_layer.initialize_schema()`
2. Add load/save functions to appropriate persistence module
3. Add hooks to runtime code
4. DDL execution is idempotent - existing tables are not modified

### Data Cleanup

Automated cleanup:
- Expired cooldowns removed on load
- Old messages pruned to last 1000
- Provocation history older than 30 days removed

### Backup Recommendations

Since all bot state is in the database:
- Regular Oracle backups ensure full state recovery
- No additional bot-level backup needed
- Can restore to any point in time with Oracle PITR

## Performance Considerations

1. **Synchronous operations**: All DB writes are synchronous (not async) to ensure consistency
2. **Connection reuse**: Single global connection reused across all operations
3. **Batch operations**: Context snapshots batch keyword/topic updates
4. **Indexes**: Foreign key and timestamp indexes for efficient queries
5. **Rolling windows**: Message and history tables automatically pruned

## Testing

To verify persistence:

1. Start bot and let it run with activity
2. Check database tables for data
3. Stop bot gracefully
4. Restart bot and verify state is restored
5. Check logs for "Successfully loaded" messages

## Troubleshooting

### "Failed to connect to the database"
- Check Oracle wallet configuration
- Verify TNS_ADMIN path
- Ensure DB credentials are correct

### "Table already exists" (ORA-00955)
- Expected on restart - tables are idempotent
- Check logs for "Object already exists" (debug level)

### Missing data after restart
- Check error logs during shutdown
- Verify periodic save task is running
- Check database connectivity during operation

### Performance degradation
- Monitor database connection health
- Check table sizes (especially history tables)
- Review cleanup job effectiveness
