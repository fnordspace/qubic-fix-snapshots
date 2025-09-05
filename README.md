# Qubic Node Save State Adjustment Tools

This repository contains Python scripts for adjusting Qubic Core node save state files when changing the `TARGET_TICK_DURATION` parameter mid-epoch.

## Data Structures

### logEventState.db Structure
The `adjust_log_state.py` script modifies the following binary file structure:
- **Log Buffer Page** (300MB): Virtual memory page containing raw log entries
- **PMAP Page** (480MB): Page map for memory management  
- **IMAP Page** (164.64MB): Index map for memory management
- **Digest Array** (variable size): Array of 32-byte digests indexed by tick offset, size = `MAX_NUMBER_OF_TICKS_PER_EPOCH * 32 bytes`
- **K12 State** (400 bytes): Cryptographic state
- **Variables** (32 bytes): `logBufferTail` (8B), `logId` (8B), `tickBegin` (4B), `lastUpdatedTick` (4B), `currentTxId` (4B), `currentTick` (4B)

The script resizes only the digest array when `TARGET_TICK_DURATION` changes, preserving all other data.

### snapshotTxStatusData Structure  
The `adjust_tx_status.py` script modifies the following binary file structure:
- **tickTxCounter Array**: Number of confirmed transactions per tick, size = `(MAX_NUMBER_OF_TICKS_PER_EPOCH + 100) * 4 bytes`
- **tickTxIndexStart Array**: Starting index in confirmedTx array for each tick's transactions, size = `(MAX_NUMBER_OF_TICKS_PER_EPOCH + 100) * 4 bytes`
- **confirmedTxPreviousEpochBeginTick** (4 bytes): First tick of the previous epoch for which confirmed transactions are stored
- **confirmedTxCurrentEpochBeginTick** (4 bytes): First tick of the current epoch for which confirmed transactions are stored

The script resizes both arrays by expanding with zeros or truncating when `TARGET_TICK_DURATION` changes.

## Scripts

### 1. adjust_log_state.py

**Purpose:** Adjusts the `logEventState.db` file when `TARGET_TICK_DURATION` changes.

This script modifies the saved logging state to accommodate a different tick duration value, which affects `MAX_NUMBER_OF_TICKS_PER_EPOCH`. The adjustment is necessary because the digest array size depends on the maximum number of ticks per epoch.

**Key Features:**
- Automatically creates a backup of the original file
- Preserves all log data, virtual memory pages, and state variables
- Verifies the adjusted file structure
- Page files (.pg) remain unchanged and compatible

**Usage:**
```bash
# Change from 3 seconds to 2 seconds per tick
python adjust_log_state.py logEventState.db --old-duration 3000 --new-duration 2000

# Change from 2 seconds to 5 seconds per tick  
python adjust_log_state.py logEventState.db --old-duration 2000 --new-duration 5000

# Save to different file
python adjust_log_state.py logEventState.db --old-duration 3000 --new-duration 2000 --output adjusted.db

# Show calculation details
python adjust_log_state.py logEventState.db --old-duration 3000 --new-duration 2000 --show-calculation
```

**Parameters:**
- `filepath`: Path to the `logEventState.db` file to adjust
- `--old-duration`: Old TARGET_TICK_DURATION in milliseconds
- `--new-duration`: New TARGET_TICK_DURATION in milliseconds  
- `--output`: Optional output file path (default: overwrite input)
- `--no-backup`: Skip creating backup file
- `--show-calculation`: Display MAX_NUMBER_OF_TICKS_PER_EPOCH calculation details

### 2. adjust_tx_status.py

**Purpose:** Converts `snapshotTxStatusData` files between different `TARGET_TICK_DURATION` values.

This script is specifically for nodes with `ADDON_TX_STATUS_REQUEST` enabled. It adjusts the transaction status snapshot arrays to match the new tick duration.

**Key Features:**
- Handles array resizing (expansion with zeros or truncation)
- Warns if truncation would lose transaction data
- Verifies the converted file is valid
- Shows statistics about data usage
- Automatically creates a backup of the original file

**Usage:**
```bash
# Change from 3 seconds to 2 seconds per tick
python adjust_tx_status.py snapshotTxStatusData --old-duration 3000 --new-duration 2000

# Change from 2 seconds to 5 seconds per tick
python adjust_tx_status.py snapshotTxStatusData --old-duration 2000 --new-duration 5000

# Save to different file
python adjust_tx_status.py snapshotTxStatusData --old-duration 3000 --new-duration 2000 --output adjusted.db

# Show calculation details
python adjust_tx_status.py snapshotTxStatusData --old-duration 3000 --new-duration 2000 --show-calculation
```

**Parameters:**
- `filepath`: Path to the snapshotTxStatusData file to adjust
- `--old-duration`: Old TARGET_TICK_DURATION in milliseconds
- `--new-duration`: New TARGET_TICK_DURATION in milliseconds
- `--output`: Optional output file path (default: overwrite input)
- `--no-backup`: Skip creating backup file
- `--show-calculation`: Display MAX_NUMBER_OF_TICKS_PER_EPOCH calculation details

## Requirements

- Python 3.6+
- No external dependencies (uses only Python standard library)