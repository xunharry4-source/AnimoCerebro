#!/usr/bin/env python3
"""
Memory Store Format Migration Tool

This tool helps migrate mixed-format memory stores (JSONL + binary ZMEM)
to a consistent format.

Usage:
    python scripts/migrate_memory_store.py <file_path> [--dry-run]
"""

import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def analyze_file(file_path: Path) -> dict:
    """Analyze the file format and return statistics."""
    stats = {
        'total_lines': 0,
        'valid_json_lines': 0,
        'binary_lines': 0,
        'empty_lines': 0,
        'first_binary_line': None,
    }
    
    with open(file_path, 'rb') as f:
        for i, line in enumerate(f):
            stats['total_lines'] += 1
            line = line.strip()
            
            if not line:
                stats['empty_lines'] += 1
                continue
            
            try:
                text = line.decode('utf-8')
                json.loads(text)
                stats['valid_json_lines'] += 1
            except (UnicodeDecodeError, json.JSONDecodeError):
                stats['binary_lines'] += 1
                if stats['first_binary_line'] is None:
                    stats['first_binary_line'] = i
    
    return stats


def extract_valid_records(file_path: Path) -> list:
    """Extract all valid JSON records from the file."""
    records = []
    
    with open(file_path, 'rb') as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            
            try:
                text = line.decode('utf-8')
                record = json.loads(text)
                records.append(record)
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                logger.debug(f"Skipping malformed line {i}: {str(e)[:50]}")
                continue
    
    return records


def clean_file(file_path: Path, dry_run: bool = False) -> dict:
    """Clean the file by removing binary lines and keeping only valid JSON."""
    logger.info(f"Analyzing {file_path}...")
    stats = analyze_file(file_path)
    
    logger.info(f"File analysis:")
    logger.info(f"  Total lines: {stats['total_lines']}")
    logger.info(f"  Valid JSON lines: {stats['valid_json_lines']}")
    logger.info(f"  Binary lines: {stats['binary_lines']}")
    logger.info(f"  Empty lines: {stats['empty_lines']}")
    
    if stats['binary_lines'] == 0:
        logger.info("✅ File is already clean (no binary data)")
        return {'cleaned': False, **stats}
    
    if stats['first_binary_line'] is not None:
        logger.warning(f"⚠️  First binary line detected at line {stats['first_binary_line']}")
    
    if dry_run:
        logger.info("🔍 Dry run mode - no changes will be made")
        return {'cleaned': False, 'would_clean': True, **stats}
    
    # Extract valid records
    logger.info("Extracting valid JSON records...")
    records = extract_valid_records(file_path)
    logger.info(f"Extracted {len(records)} valid records")
    
    # Backup original file
    backup_path = file_path.with_suffix('.jsonl.bak')
    logger.info(f"Creating backup: {backup_path}")
    file_path.rename(backup_path)
    
    # Write clean file
    logger.info(f"Writing clean file: {file_path}")
    with open(file_path, 'w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    
    logger.info(f"✅ File cleaned successfully!")
    logger.info(f"   Original backed up to: {backup_path}")
    logger.info(f"   Clean file contains {len(records)} records")
    
    return {
        'cleaned': True,
        'records_kept': len(records),
        'backup_path': str(backup_path),
        **stats
    }


def main():
    parser = argparse.ArgumentParser(
        description='Clean mixed-format memory store files'
    )
    parser.add_argument(
        'file_path',
        type=Path,
        help='Path to the memory store file'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Analyze only, do not modify files'
    )
    
    args = parser.parse_args()
    
    if not args.file_path.exists():
        logger.error(f"File not found: {args.file_path}")
        return 1
    
    result = clean_file(args.file_path, dry_run=args.dry_run)
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for key, value in result.items():
        print(f"{key:20s}: {value}")
    print("="*60)
    
    return 0


if __name__ == '__main__':
    exit(main())
