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
    
    # Fixed sizes from the C++ code
    LOG_BUFFER_PAGE_SIZE = 300_000_000
    PMAP_LOG_PAGE_SIZE = 30_000_000
    IMAP_LOG_PAGE_SIZE = 10_000
    DIGEST_SIZE = 32  # Each digest is 32 bytes
    K12_STATE_SIZE = 448  # sizeof(XKCP::KangarooTwelve_Instance)
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
        
        print("Adjusting logEventState.db file:")
        print(f"  OLD TARGET_TICK_DURATION: {old_tick_duration} ms")
        print(f"  NEW TARGET_TICK_DURATION: {new_tick_duration} ms")
        print(f"  OLD MAX_NUMBER_OF_TICKS_PER_EPOCH: {self.old_max_ticks}")
        print(f"  NEW MAX_NUMBER_OF_TICKS_PER_EPOCH: {self.new_max_ticks}")
        print()
        
    def read_file(self):
        """Read the entire file into memory"""
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"File not found: {self.filepath}")
            
        with open(self.filepath, 'rb') as f:
            self.data = bytearray(f.read())  # Use bytearray for mutability
        
        print(f"Input file size: {len(self.data)} bytes")
        
    def backup_file(self):
        """Create a backup of the original file"""
        backup_path = self.filepath + '.backup'
        shutil.copy2(self.filepath, backup_path)
        print(f"Created backup at: {backup_path}")
        
    def calculate_sizes(self):
        """Calculate the sizes of each section"""
        # Match C++ calculations exactly
        log_buffer_vm_size = self.LOG_BUFFER_PAGE_SIZE + 8 + 8
        map_log_id_vm_size = self.PMAP_LOG_PAGE_SIZE * 16 + 8 + 8  # sizeof(BlobInfo) = 16
        map_tx_vm_size = self.IMAP_LOG_PAGE_SIZE * 16464 + 8 + 8  # sizeof(TickBlobInfo) = 16464
        old_digests_size = 32 * self.old_max_ticks
        new_digests_size = 32 * self.new_max_ticks
        
        return {
            'log_buffer_vm_size': log_buffer_vm_size,
            'map_log_id_vm_size': map_log_id_vm_size,
            'map_tx_vm_size': map_tx_vm_size,
            'old_digests_size': old_digests_size,
            'new_digests_size': new_digests_size
        }
    
    def adjust_file(self):
        """Adjust the file for the new TARGET_TICK_DURATION"""
        sizes = self.calculate_sizes()
        
        # Calculate expected old file size
        expected_old_size = (sizes['log_buffer_vm_size'] + sizes['map_log_id_vm_size'] + 
                            sizes['map_tx_vm_size'] + sizes['old_digests_size'] + 
                            self.K12_STATE_SIZE + self.VARIABLES_SIZE)
        
        print("Expected input file structure:")
        print(f"  Log buffer VM: {sizes['log_buffer_vm_size']} bytes")
        print(f"  MapLogId VM: {sizes['map_log_id_vm_size']} bytes")
        print(f"  MapTx VM: {sizes['map_tx_vm_size']} bytes")
        print(f"  Digests (old): {sizes['old_digests_size']} bytes")
        print(f"  K12 instance: {self.K12_STATE_SIZE} bytes")
        print(f"  Variables: {self.VARIABLES_SIZE} bytes")
        print(f"  Expected total: {expected_old_size} bytes")
        
        if abs(len(self.data) - expected_old_size) > 1000:
            print(f"\nWarning: File size doesn't match expected size (difference: {abs(len(self.data) - expected_old_size)} bytes)")
            print("File might not be from TARGET_TICK_DURATION={} or K12 size is different".format(self.old_tick_duration))
            response = input("Continue anyway? (y/n): ")
            if response.lower() != 'y':
                sys.exit(1)
        
        # Calculate actual K12 size based on file
        actual_k12_size = (len(self.data) - sizes['log_buffer_vm_size'] - sizes['map_log_id_vm_size'] - 
                          sizes['map_tx_vm_size'] - sizes['old_digests_size'] - self.VARIABLES_SIZE)
        print(f"\nActual K12 instance size: {actual_k12_size} bytes")
        
        # Create new buffer for adjusted file
        new_file_size = (sizes['log_buffer_vm_size'] + sizes['map_log_id_vm_size'] + 
                        sizes['map_tx_vm_size'] + sizes['new_digests_size'] + 
                        actual_k12_size + self.VARIABLES_SIZE)
        new_data = bytearray(new_file_size)
        
        print("\nAdjusting file structure...")
        
        # Copy data sections
        src_offset = 0
        dst_offset = 0
        
        # 1. Copy Log buffer VM state (unchanged)
        print("  Copying log buffer VM state...")
        copy_size = sizes['log_buffer_vm_size']
        new_data[dst_offset:dst_offset+copy_size] = self.data[src_offset:src_offset+copy_size]
        src_offset += copy_size
        dst_offset += copy_size
        
        # 2. Copy MapLogId VM state (unchanged)
        print("  Copying MapLogId VM state...")
        copy_size = sizes['map_log_id_vm_size']
        new_data[dst_offset:dst_offset+copy_size] = self.data[src_offset:src_offset+copy_size]
        src_offset += copy_size
        dst_offset += copy_size
        
        # 3. Copy MapTx VM state (unchanged)
        print("  Copying MapTx VM state...")
        copy_size = sizes['map_tx_vm_size']
        new_data[dst_offset:dst_offset+copy_size] = self.data[src_offset:src_offset+copy_size]
        src_offset += copy_size
        dst_offset += copy_size
        
        # 4. Adjust digests array
        print("  Adjusting digests array...")
        
        # First, clear the new digests area with zeros
        for i in range(sizes['new_digests_size']):
            new_data[dst_offset + i] = 0
        
        # Copy existing digests (tick numbers don't change)
        ticks_to_copy = min(self.old_max_ticks, self.new_max_ticks)
        copy_size = ticks_to_copy * 32
        new_data[dst_offset:dst_offset+copy_size] = self.data[src_offset:src_offset+copy_size]
        
        src_offset += sizes['old_digests_size']
        dst_offset += sizes['new_digests_size']
        
        # 5. Copy K12 instance (unchanged)
        print("  Copying K12 instance...")
        new_data[dst_offset:dst_offset+actual_k12_size] = self.data[src_offset:src_offset+actual_k12_size]
        src_offset += actual_k12_size
        dst_offset += actual_k12_size
        
        # 6. Read and adjust variables
        print("  Adjusting variables...")
        
        # Read variables from old file
        log_buffer_tail = struct.unpack('<Q', self.data[src_offset:src_offset+8])[0]
        log_id = struct.unpack('<Q', self.data[src_offset+8:src_offset+16])[0]
        tick_begin = struct.unpack('<I', self.data[src_offset+16:src_offset+20])[0]
        last_updated_tick = struct.unpack('<I', self.data[src_offset+20:src_offset+24])[0]
        current_tx_id = struct.unpack('<I', self.data[src_offset+24:src_offset+28])[0]
        current_tick = struct.unpack('<I', self.data[src_offset+28:src_offset+32])[0]
        
        print("\nVariables:")
        print(f"  logBufferTail: {log_buffer_tail}")
        print(f"  logId: {log_id}")
        print(f"  tickBegin: {tick_begin}")
        print(f"  lastUpdatedTick: {last_updated_tick}")
        print(f"  currentTxId: {current_tx_id}")
        print(f"  currentTick: {current_tick}")
        
        # Write variables to new buffer (unchanged - ticks are absolute events)
        struct.pack_into('<Q', new_data, dst_offset, log_buffer_tail)
        struct.pack_into('<Q', new_data, dst_offset+8, log_id)
        struct.pack_into('<I', new_data, dst_offset+16, tick_begin)
        struct.pack_into('<I', new_data, dst_offset+20, last_updated_tick)
        struct.pack_into('<I', new_data, dst_offset+24, current_tx_id)
        struct.pack_into('<I', new_data, dst_offset+28, current_tick)
        
        return new_data
    
    def write_file(self, data, output_path=None):
        """Write the adjusted data to file"""
        if output_path is None:
            output_path = self.filepath
        
        with open(output_path, 'wb') as f:
            f.write(data)
        
        print(f"\nWriting output file...")
        print(f"Output file size: {len(data)} bytes")
        print(f"Size difference: {len(data) - len(self.data)} bytes")
        print(f"\nSuccessfully adjusted {output_path}")
    
    

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
        
        # Write the adjusted file
        adjuster.write_file(new_data, args.output)
    
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