#!/usr/bin/env python3
"""
Convert snapshotTxStatusData files between different TARGET_TICK_DURATION values.

This script adjusts the TX status snapshot files when changing TARGET_TICK_DURATION
mid-epoch in Qubic Core nodes with ADDON_TX_STATUS_REQUEST enabled.
"""

import struct
import sys
import os
from typing import Tuple

# Constants from Qubic Core
NUMBER_OF_COMPUTORS = 676
TICKS_TO_KEEP_FROM_PRIOR_EPOCH = 100
SECONDS_PER_WEEK = 60 * 60 * 24 * 7


def calculate_max_ticks_per_epoch(target_tick_duration_ms: int) -> int:
    """
    Calculate MAX_NUMBER_OF_TICKS_PER_EPOCH using the exact formula from public_settings.h:
    #define MAX_NUMBER_OF_TICKS_PER_EPOCH (((((60 * 60 * 24 * 7) / (TARGET_TICK_DURATION / 1000)) + NUMBER_OF_COMPUTORS - 1) / NUMBER_OF_COMPUTORS) * NUMBER_OF_COMPUTORS)
    """
    target_tick_duration_seconds = target_tick_duration_ms / 1000
    
    # Integer division matching C++ behavior
    ticks_per_week = SECONDS_PER_WEEK // target_tick_duration_seconds
    
    # Round up to nearest multiple of NUMBER_OF_COMPUTORS
    max_ticks = ((ticks_per_week + NUMBER_OF_COMPUTORS - 1) // NUMBER_OF_COMPUTORS) * NUMBER_OF_COMPUTORS
    
    return int(max_ticks)


def read_tx_status_data(file_path: str, max_ticks_per_epoch: int) -> Tuple:
    """
    Read the snapshotTxStatusData file with the given array size.
    
    Returns:
        Tuple of (tickTxCounter, tickTxIndexStart, confirmedTxPreviousEpochBeginTick, confirmedTxCurrentEpochBeginTick)
    """
    array_size = max_ticks_per_epoch + TICKS_TO_KEEP_FROM_PRIOR_EPOCH
    expected_size = array_size * 4 * 2 + 8  # Two arrays of unsigned ints + two unsigned ints
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    actual_size = os.path.getsize(file_path)
    if actual_size != expected_size:
        raise ValueError(
            f"File size mismatch! Expected {expected_size:,} bytes for "
            f"TARGET_TICK_DURATION that gives {max_ticks_per_epoch:,} max ticks, "
            f"but file is {actual_size:,} bytes"
        )
    
    with open(file_path, 'rb') as f:
        # Read tickTxCounter array
        tickTxCounter = list(struct.unpack(f'{array_size}I', f.read(array_size * 4)))
        
        # Read tickTxIndexStart array
        tickTxIndexStart = list(struct.unpack(f'{array_size}I', f.read(array_size * 4)))
        
        # Read the two tick boundary values
        confirmedTxPreviousEpochBeginTick = struct.unpack('I', f.read(4))[0]
        confirmedTxCurrentEpochBeginTick = struct.unpack('I', f.read(4))[0]
    
    return (tickTxCounter, tickTxIndexStart, 
            confirmedTxPreviousEpochBeginTick, confirmedTxCurrentEpochBeginTick)


def write_tx_status_data(file_path: str, max_ticks_per_epoch: int,
                         tickTxCounter: list, tickTxIndexStart: list,
                         confirmedTxPreviousEpochBeginTick: int,
                         confirmedTxCurrentEpochBeginTick: int) -> None:
    """
    Write the snapshotTxStatusData file with the given array size.
    """
    new_array_size = max_ticks_per_epoch + TICKS_TO_KEEP_FROM_PRIOR_EPOCH
    
    # Adjust array sizes (expand with zeros or truncate)
    if len(tickTxCounter) < new_array_size:
        # Expand with zeros
        tickTxCounter = tickTxCounter + [0] * (new_array_size - len(tickTxCounter))
        tickTxIndexStart = tickTxIndexStart + [0] * (new_array_size - len(tickTxIndexStart))
    elif len(tickTxCounter) > new_array_size:
        # Truncate (warning: this could lose data if there are transactions in the truncated region)
        # Check if we're truncating non-zero data
        truncated_tx_counter = tickTxCounter[new_array_size:]
        truncated_tx_index = tickTxIndexStart[new_array_size:]
        
        if any(x != 0 for x in truncated_tx_counter) or any(x != 0 for x in truncated_tx_index):
            print("WARNING: Truncating arrays will lose transaction data!")
            response = input("Continue anyway? (y/n): ")
            if response.lower() != 'y':
                sys.exit(1)
        
        tickTxCounter = tickTxCounter[:new_array_size]
        tickTxIndexStart = tickTxIndexStart[:new_array_size]
    
    with open(file_path, 'wb') as f:
        # Write tickTxCounter array
        f.write(struct.pack(f'{new_array_size}I', *tickTxCounter))
        
        # Write tickTxIndexStart array
        f.write(struct.pack(f'{new_array_size}I', *tickTxIndexStart))
        
        # Write the two tick boundary values
        f.write(struct.pack('I', confirmedTxPreviousEpochBeginTick))
        f.write(struct.pack('I', confirmedTxCurrentEpochBeginTick))
    
    print(f"Successfully wrote {os.path.getsize(file_path):,} bytes to {file_path}")


def convert_tx_status(input_file: str, output_file: str, 
                     old_tick_duration: int, new_tick_duration: int) -> None:
    """
    Convert snapshotTxStatusData file from old to new TARGET_TICK_DURATION.
    """
    # Calculate array sizes for both configurations
    old_max_ticks = calculate_max_ticks_per_epoch(old_tick_duration)
    new_max_ticks = calculate_max_ticks_per_epoch(new_tick_duration)
    
    print(f"Old configuration (TARGET_TICK_DURATION = {old_tick_duration}ms):")
    print(f"  MAX_NUMBER_OF_TICKS_PER_EPOCH = {old_max_ticks:,}")
    print(f"  Array size = {old_max_ticks + TICKS_TO_KEEP_FROM_PRIOR_EPOCH:,}")
    print(f"  File size = {((old_max_ticks + TICKS_TO_KEEP_FROM_PRIOR_EPOCH) * 4 * 2 + 8):,} bytes")
    print()
    print(f"New configuration (TARGET_TICK_DURATION = {new_tick_duration}ms):")
    print(f"  MAX_NUMBER_OF_TICKS_PER_EPOCH = {new_max_ticks:,}")
    print(f"  Array size = {new_max_ticks + TICKS_TO_KEEP_FROM_PRIOR_EPOCH:,}")
    print(f"  File size = {((new_max_ticks + TICKS_TO_KEEP_FROM_PRIOR_EPOCH) * 4 * 2 + 8):,} bytes")
    print()
    
    # Read the old format
    print(f"Reading {input_file}...")
    try:
        data = read_tx_status_data(input_file, old_max_ticks)
        tickTxCounter, tickTxIndexStart, prevEpochBegin, currEpochBegin = data
        print(f"  Previous epoch begin tick: {prevEpochBegin}")
        print(f"  Current epoch begin tick: {currEpochBegin}")
        
        # Count non-zero entries to show how much data is actually used
        non_zero_counter = sum(1 for x in tickTxCounter if x != 0)
        non_zero_index = sum(1 for x in tickTxIndexStart if x != 0)
        print(f"  Non-zero tick counters: {non_zero_counter:,}")
        print(f"  Non-zero tick indices: {non_zero_index:,}")
        
        # Find the highest used tick index
        highest_used_tick = -1
        for i in range(len(tickTxCounter) - 1, -1, -1):
            if tickTxCounter[i] != 0:
                highest_used_tick = i
                break
        
        if highest_used_tick >= 0:
            print(f"  Highest used tick index: {highest_used_tick:,}")
            if highest_used_tick >= new_max_ticks + TICKS_TO_KEEP_FROM_PRIOR_EPOCH:
                print(f"  WARNING: Highest used tick ({highest_used_tick:,}) exceeds new array size!")
        
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Write the new format
    print()
    print(f"Writing {output_file}...")
    write_tx_status_data(output_file, new_max_ticks,
                        tickTxCounter, tickTxIndexStart,
                        prevEpochBegin, currEpochBegin)
    
    print()
    print("Conversion complete!")
    
    # Verify the output file
    print()
    print("Verifying output file...")
    try:
        verify_data = read_tx_status_data(output_file, new_max_ticks)
        print("  Output file is valid and can be read with new TARGET_TICK_DURATION")
    except Exception as e:
        print(f"  ERROR: Failed to verify output file: {e}")
        sys.exit(1)


def main():
    if len(sys.argv) != 5:
        print("Usage: python convert_tx_status_snapshot.py <input_file> <output_file> <old_tick_duration_ms> <new_tick_duration_ms>")
        print()
        print("Example:")
        print("  python convert_tx_status_snapshot.py ep176/snapshotTxStatusData ep176/snapshotTxStatusData.new 3000 2000")
        print()
        print("This will convert the file from TARGET_TICK_DURATION=3000 to TARGET_TICK_DURATION=2000")
        print()
        print("After conversion, replace the original file:")
        print("  mv ep176/snapshotTxStatusData ep176/snapshotTxStatusData.backup")
        print("  mv ep176/snapshotTxStatusData.new ep176/snapshotTxStatusData")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    old_tick_duration = int(sys.argv[3])
    new_tick_duration = int(sys.argv[4])
    
    if old_tick_duration <= 0 or new_tick_duration <= 0:
        print("Error: Tick durations must be positive integers (milliseconds)")
        sys.exit(1)
    
    if input_file == output_file:
        print("Error: Input and output files must be different")
        print("Tip: Use a temporary output file and then replace the original")
        sys.exit(1)
    
    convert_tx_status(input_file, output_file, old_tick_duration, new_tick_duration)


if __name__ == "__main__":
    main()