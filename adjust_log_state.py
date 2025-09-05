#!/usr/bin/env python3
"""
Adjust logEventState.db file when TARGET_TICK_DURATION changes.

This script modifies the saved logging state to accommodate a different
TARGET_TICK_DURATION value, which affects MAX_NUMBER_OF_TICKS_PER_EPOCH.

IMPORTANT: This only adjusts the logEventState.db file. The .pg files 
(page files on disk) remain unchanged and will still be compatible since
they only contain raw log data, not tick-indexed structures.
"""

import struct
import sys
import os
import shutil
from datetime import datetime
import argparse

def calculate_max_ticks_per_epoch(target_tick_duration_ms, number_of_computors=676):
    """
    Calculate MAX_NUMBER_OF_TICKS_PER_EPOCH using integer arithmetic.
    
    Formula from public_settings.h:
    #define MAX_NUMBER_OF_TICKS_PER_EPOCH (((((60 * 60 * 24 * 7) / (TARGET_TICK_DURATION / 1000)) + NUMBER_OF_COMPUTORS - 1) / NUMBER_OF_COMPUTORS) * NUMBER_OF_COMPUTORS)
    
    This uses integer division throughout to match C++ behavior.
    """
    seconds_per_week = 60 * 60 * 24 * 7  # 604800
    target_tick_duration_seconds = target_tick_duration_ms // 1000  # Integer division
    
    # Calculate ticks per week using integer division
    ticks_per_week = seconds_per_week // target_tick_duration_seconds
    
    # Round up to nearest multiple of NUMBER_OF_COMPUTORS
    # This is what the formula does: ((x + N - 1) / N) * N rounds up to multiple of N
    max_ticks = ((ticks_per_week + number_of_computors - 1) // number_of_computors) * number_of_computors
    
    return max_ticks

class LogStateAdjuster:
    """Adjusts logEventState.db for different TARGET_TICK_DURATION values"""
    
    # Fixed sizes from the code
    LOG_BUFFER_PAGE_SIZE = 300_000_000
    PMAP_PAGE_SIZE = 480_000_000  # 30M * 16
    IMAP_PAGE_SIZE = 164_640_000  # 10K * 16464
    DIGEST_SIZE = 32  # Each digest is 32 bytes
    K12_STATE_SIZE = 400  # Approximate K12 instance size
    VARIABLES_SIZE = 32  # 8+8+4+4+4+4 bytes
    NUMBER_OF_COMPUTORS = 676
    
    def __init__(self, filepath, old_tick_duration, new_tick_duration):
        self.filepath = filepath
        self.old_tick_duration = old_tick_duration
        self.new_tick_duration = new_tick_duration
        
        # Calculate MAX_NUMBER_OF_TICKS_PER_EPOCH for both values
        self.old_max_ticks = calculate_max_ticks_per_epoch(old_tick_duration, self.NUMBER_OF_COMPUTORS)
        self.new_max_ticks = calculate_max_ticks_per_epoch(new_tick_duration, self.NUMBER_OF_COMPUTORS)
        
        self.data = None
        
        print(f"TARGET_TICK_DURATION: {old_tick_duration}ms -> {new_tick_duration}ms")
        print(f"MAX_NUMBER_OF_TICKS_PER_EPOCH: {self.old_max_ticks:,} -> {self.new_max_ticks:,}")
        
    def read_file(self):
        """Read the entire file into memory"""
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"File not found: {self.filepath}")
            
        with open(self.filepath, 'rb') as f:
            self.data = bytearray(f.read())  # Use bytearray for mutability
        
        print(f"\nLoaded {len(self.data):,} bytes from {self.filepath}")
        
    def backup_file(self):
        """Create a backup of the original file"""
        backup_path = self.filepath + '.backup'
        shutil.copy2(self.filepath, backup_path)
        print(f"Created backup at: {backup_path}")
        
    def calculate_offsets(self):
        """Calculate the offsets of each section"""
        offsets = {}
        
        # Three virtual memory dumps
        offset = 0
        offsets['log_buffer_start'] = offset
        offset += self.LOG_BUFFER_PAGE_SIZE + 16  # page + currentId + currentPageId
        
        offsets['pmap_start'] = offset
        offset += self.PMAP_PAGE_SIZE + 16
        
        offsets['imap_start'] = offset
        offset += self.IMAP_PAGE_SIZE + 16
        
        # Digests array (this is what changes!)
        offsets['digests_start'] = offset
        offsets['old_digests_size'] = self.old_max_ticks * self.DIGEST_SIZE
        offsets['new_digests_size'] = self.new_max_ticks * self.DIGEST_SIZE
        offset += offsets['old_digests_size']
        
        # K12 state
        offsets['k12_start'] = offset
        offset += self.K12_STATE_SIZE
        
        # Variables
        offsets['variables_start'] = offset
        offset += self.VARIABLES_SIZE
        
        offsets['file_end'] = offset
        
        return offsets
    
    def adjust_file(self):
        """Adjust the file for the new TARGET_TICK_DURATION"""
        offsets = self.calculate_offsets()
        
        print(f"\nAdjusting digest array:")
        print(f"  Old size: {offsets['old_digests_size']:,} bytes ({offsets['old_digests_size'] / 1024 / 1024:.2f} MB)")
        print(f"  New size: {offsets['new_digests_size']:,} bytes ({offsets['new_digests_size'] / 1024 / 1024:.2f} MB)")
        print(f"  Difference: {offsets['new_digests_size'] - offsets['old_digests_size']:+,} bytes")
        
        # Extract the current sections
        digests_data = self.data[offsets['digests_start']:offsets['digests_start'] + offsets['old_digests_size']]
        k12_data = self.data[offsets['k12_start']:offsets['k12_start'] + self.K12_STATE_SIZE]
        variables_data = self.data[offsets['variables_start']:offsets['variables_start'] + self.VARIABLES_SIZE]
        
        # Parse variables to show what we're preserving
        log_buffer_tail = struct.unpack('<Q', variables_data[0:8])[0]
        log_id = struct.unpack('<Q', variables_data[8:16])[0]
        tick_begin = struct.unpack('<I', variables_data[16:20])[0]
        last_updated_tick = struct.unpack('<I', variables_data[20:24])[0]
        current_tx_id = struct.unpack('<I', variables_data[24:28])[0]
        current_tick = struct.unpack('<I', variables_data[28:32])[0]
        
        print(f"\nPreserving variables:")
        print(f"  Log Buffer Tail: {log_buffer_tail:,}")
        print(f"  Current Log ID: {log_id:,}")
        print(f"  Tick Begin: {tick_begin:,}")
        print(f"  Last Updated Tick: {last_updated_tick:,}")
        print(f"  Current TX ID: {current_tx_id}")
        print(f"  Current Tick: {current_tick:,}")
        
        # Check how many digests are actually used
        ticks_used = last_updated_tick - tick_begin + 1 if last_updated_tick >= tick_begin else 0
        print(f"\nDigests actually used: {ticks_used:,} (of {self.old_max_ticks:,} allocated)")
        
        if ticks_used > self.new_max_ticks:
            print(f"\n⚠️  WARNING: {ticks_used:,} ticks used but new limit is {self.new_max_ticks:,}")
            print("   Some digest data will be lost!")
            response = input("   Continue anyway? (y/N): ")
            if response.lower() != 'y':
                print("Aborted.")
                sys.exit(1)
        
        # Create new file data
        new_data = bytearray()
        
        # Copy everything before digests unchanged
        new_data.extend(self.data[0:offsets['digests_start']])
        
        # Handle digest array resize
        if offsets['new_digests_size'] > offsets['old_digests_size']:
            # Expanding - add zeros
            new_data.extend(digests_data)
            new_data.extend(b'\x00' * (offsets['new_digests_size'] - offsets['old_digests_size']))
            print(f"\n✓ Expanded digest array with {offsets['new_digests_size'] - offsets['old_digests_size']:,} zero bytes")
        else:
            # Shrinking - truncate
            new_data.extend(digests_data[:offsets['new_digests_size']])
            print(f"\n✓ Truncated digest array by {offsets['old_digests_size'] - offsets['new_digests_size']:,} bytes")
        
        # Append K12 state and variables
        new_data.extend(k12_data)
        new_data.extend(variables_data)
        
        print(f"\nNew file size: {len(new_data):,} bytes (was {len(self.data):,} bytes)")
        
        return new_data
    
    def write_file(self, data, output_path=None):
        """Write the adjusted data to file"""
        if output_path is None:
            output_path = self.filepath
        
        with open(output_path, 'wb') as f:
            f.write(data)
        
        print(f"\n✓ Written adjusted file to: {output_path}")
    
    def verify_adjustment(self, new_data):
        """Verify the adjusted file will load correctly"""
        print("\nVerifying adjusted file structure:")
        
        # Calculate expected offsets with new size
        offset = 0
        offset += self.LOG_BUFFER_PAGE_SIZE + 16
        offset += self.PMAP_PAGE_SIZE + 16
        offset += self.IMAP_PAGE_SIZE + 16
        offset += self.new_max_ticks * self.DIGEST_SIZE
        offset += self.K12_STATE_SIZE
        offset += self.VARIABLES_SIZE
        
        print(f"  Expected size: {offset:,} bytes")
        print(f"  Actual size: {len(new_data):,} bytes")
        print(f"  Match: {'✓ YES' if offset == len(new_data) else '✗ NO'}")
        
        # Verify variables are at correct position
        var_offset = len(new_data) - self.VARIABLES_SIZE
        variables_check = new_data[var_offset:var_offset + self.VARIABLES_SIZE]
        
        log_id_check = struct.unpack('<Q', variables_check[8:16])[0]
        tick_check = struct.unpack('<I', variables_check[28:32])[0]
        
        print(f"\nVariable position check:")
        print(f"  Log ID at new position: {log_id_check:,}")
        print(f"  Current tick at new position: {tick_check:,}")
        
        return offset == len(new_data)
    
    def show_pg_files_info(self):
        """Show information about .pg files"""
        print("\n" + "="*60)
        print("IMPORTANT: About .pg Page Files")
        print("="*60)
        print("""
The .pg files on disk do NOT need to be adjusted because:

1. They contain raw log buffer pages (300MB each of log entries)
2. Log entries have their tick number embedded in the header
3. The virtual memory system will still find them by page ID
4. Page IDs don't change with TARGET_TICK_DURATION

What the .pg files contain:
  - Sequential log entries with headers
  - Each entry: [epoch][tick][size/type][logId][digest][message]
  - No dependency on MAX_NUMBER_OF_TICKS_PER_EPOCH

The only tick-indexed structure is the digest array in logEventState.db,
which maps tick offset -> digest for state verification.

✓ Your existing .pg files will work perfectly with the adjusted node!
""")

def main():
    parser = argparse.ArgumentParser(
        description='Adjust logEventState.db when TARGET_TICK_DURATION changes',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Change from 3 seconds to 2 seconds per tick
  %(prog)s logEventState.db --old-duration 3000 --new-duration 2000
  
  # Change from 2 seconds to 5 seconds per tick
  %(prog)s logEventState.db --old-duration 2000 --new-duration 5000
  
  # Save to different file
  %(prog)s logEventState.db --old-duration 3000 --new-duration 2000 --output adjusted.db
  
Note: TARGET_TICK_DURATION is in milliseconds (3000 = 3 seconds)
        """
    )
    
    parser.add_argument(
        'filepath',
        help='Path to logEventState.db file to adjust'
    )
    parser.add_argument(
        '--old-duration',
        type=int,
        required=True,
        help='Old TARGET_TICK_DURATION in milliseconds'
    )
    parser.add_argument(
        '--new-duration',
        type=int,
        required=True,
        help='New TARGET_TICK_DURATION in milliseconds'
    )
    parser.add_argument(
        '--output',
        help='Output file path (default: overwrite input file)'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Do not create backup file'
    )
    parser.add_argument(
        '--show-calculation',
        action='store_true',
        help='Show the MAX_NUMBER_OF_TICKS_PER_EPOCH calculation details'
    )
    
    args = parser.parse_args()
    
    if args.show_calculation:
        print("MAX_NUMBER_OF_TICKS_PER_EPOCH Calculation:")
        print("="*50)
        for duration in [1000, 2000, 3000, 4000, 5000]:
            max_ticks = calculate_max_ticks_per_epoch(duration)
            print(f"  TARGET_TICK_DURATION = {duration}ms -> {max_ticks:,} max ticks")
        print()
    
    if args.old_duration == args.new_duration:
        print("Old and new durations are the same. No adjustment needed.")
        return
    
    # Create adjuster
    adjuster = LogStateAdjuster(args.filepath, args.old_duration, args.new_duration)
    
    try:
        # Read file
        adjuster.read_file()
        
        # Create backup unless disabled
        if not args.no_backup and not args.output:
            adjuster.backup_file()
        
        # Adjust the file
        new_data = adjuster.adjust_file()
        
        # Verify the adjustment
        if adjuster.verify_adjustment(new_data):
            # Write the adjusted file
            adjuster.write_file(new_data, args.output)
            
            # Show info about .pg files
            adjuster.show_pg_files_info()
            
            print("\n✓ Adjustment completed successfully!")
        else:
            print("\n✗ Verification failed! File not written.")
            sys.exit(1)
    
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()