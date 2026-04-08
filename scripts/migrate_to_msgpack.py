#!/usr/bin/env python3
"""
ZMEM Migration Tool v1.0
------------------------
Converts legacy JSONL memory stores to the new production-grade MessagePack binary format.
Supports transparent re-encryption and tiered compression during migration.

Usage:
    python scripts/migrate_to_msgpack.py --input path/to/memory.jsonl --output path/to/memory.zmem --tier warm
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# Ensure src is in path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from zentex.memory.enhanced import EnhancedMemoryRecord, _EnhancedMemoryJSONLStore
from zentex.memory.compression import TieredCompressionService
from zentex.memory.encryption import EnterpriseEncryptionService
from zentex.memory.storage_format import MessagePackSerializer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("zmem-migration")

def migrate(input_path: str, output_path: str, tier: str):
    logger.info(f"Starting migration: {input_path} -> {output_path} (Tier: {tier})")
    
    # 1. Load existing records (handles binary/JSON/compressed/encrypted automatically)
    store = _EnhancedMemoryJSONLStore(input_path)
    records = store.list_records()
    logger.info(f"Loaded {len(records)} records from source.")
    
    if not records:
        logger.warning("No records found to migrate.")
        return

    # 2. Initialize target services
    serializer = MessagePackSerializer()
    compressor = TieredCompressionService()
    # Ensure master key is available for encryption
    encryption = EnterpriseEncryptionService()
    if not encryption.enabled:
        logger.warning("Encryption is disabled (no master key found). Data will be migrated as plaintext binary.")

    # 3. Write target file
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    with out_file.open("wb") as handle:
        for i, record in enumerate(records):
            # Serialize
            rec_dict = record.model_dump(mode="json")
            
            # Determine encryption requirement
            visibility = str(record.payload.get("visibility", "internal"))
            encrypt_this = (visibility != "public") and encryption.enabled
            
            # MessagePack layer
            payload = serializer.serialize(
                rec_dict,
                compressed=True, # Always compress in migration
                encrypted=encrypt_this
            )
            
            # Tiered Compression layer
            data = compressor.compress_for_tier(payload, tier)
            
            # Encryption layer
            if encrypt_this:
                data = encryption.encrypt(data, context=record.memory_layer)
            
            handle.write(data)
            
            if (i+1) % 1000 == 0:
                logger.info(f"Migrated {i+1} records...")

    logger.info(f"Migration COMPLETED. Total records: {len(records)}")
    
    # 4. Integrity check (optional but recommended)
    logger.info("Performing integrity verification...")
    new_store = _EnhancedMemoryJSONLStore(output_path)
    new_records = new_store.list_records()
    if len(new_records) == len(records):
        logger.info("Verfication PASSED. Record count matches.")
        orig_size = Path(input_path).stat().st_size
        new_size = Path(output_path).stat().st_size
        ratio = (1 - (new_size / orig_size)) * 100
        logger.info(f"Space optimization: {ratio:.2f}% reduction.")
    else:
        logger.error(f"Verification FAILED. Expected {len(records)}, got {len(new_records)}.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ZMEM Migration Tool")
    parser.add_argument("--input", required=True, help="Path to input memory file")
    parser.add_argument("--output", required=True, help="Path to output memory file")
    parser.add_argument("--tier", default="warm", choices=["hot", "warm", "cold"], help="Target memory tier")
    
    args = parser.parse_args()
    migrate(args.input, args.output, args.tier)
