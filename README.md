# Qubic Node Save State Adjustment Tools

This repository contains Python scripts for adjusting Qubic Core node save state files when changing the `TARGET_TICK_DURATION` parameter mid-epoch.

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

**Usage:**
```bash
# Convert from 3000ms to 2000ms tick duration
python adjust_tx_status.py ep176/snapshotTxStatusData ep176/snapshotTxStatusData.new 3000 2000

# After verification, replace the original
mv ep176/snapshotTxStatusData ep176/snapshotTxStatusData.backup
mv ep176/snapshotTxStatusData.new ep176/snapshotTxStatusData
```

**Parameters:**
- `input_file`: Path to the original snapshotTxStatusData file
- `output_file`: Path for the converted file
- `old_tick_duration_ms`: Old TARGET_TICK_DURATION in milliseconds
- `new_tick_duration_ms`: New TARGET_TICK_DURATION in milliseconds

## Requirements

- Python 3.6+
- No external dependencies (uses only Python standard library)