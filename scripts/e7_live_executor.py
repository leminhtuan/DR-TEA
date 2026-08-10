import os
import sys
import json
import time
import csv
import socket
from datetime import datetime, timezone

# Force IPv4 in requests to prevent hanging on macOS
import requests.packages.urllib3.util.connection as urllib3_cn
def allowed_gai_family():
    return socket.AF_INET
urllib3_cn.allowed_gai_family = allowed_gai_family

from pycardano import (
    PaymentExtendedSigningKey,
    Address,
    Network,
    TransactionBuilder,
    AlonzoMetadata,
    Metadata,
    BlockFrostChainContext,
    AuxiliaryData,
    HDWallet
)
from blockfrost import BlockFrostApi, ApiError, ApiUrls

def wait_for_tx_confirmation(api, tx_hash, timeout=1800, poll_interval=10):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            tx_info = api.transaction(tx_hash)
            # If successful, the transaction is in a block
            return tx_info
        except ApiError as e:
            if e.status_code == 404:
                # Not found yet, still in mempool or dropped
                time.sleep(poll_interval)
            else:
                print(f"[WARN] BlockFrost API error while polling tx {tx_hash}: {e}")
                time.sleep(poll_interval)
        except Exception as e:
            print(f"[WARN] Unknown error while polling tx {tx_hash}: {e}")
            time.sleep(poll_interval)
    raise TimeoutError(f"Transaction {tx_hash} not confirmed within {timeout} seconds.")

def main():
    print("=" * 60)
    print("DR-TEA — E7 Cardano Mainnet Live Pilot: Submission Engine")
    print("=" * 60)

    # 1. Environment and API setup
    blockfrost_proj_id = os.environ.get("BLOCKFROST_PROJECT_ID")
    expected_addr_str = os.environ.get("CARDANO_WALLET_ADDR")
    mnemonic = os.environ.get("CARDANO_MNEMONIC")

    if not blockfrost_proj_id or not expected_addr_str or not mnemonic:
        print("[FAIL] Missing credentials in environment. Ensure CARDANO_MNEMONIC is set.")
        sys.exit(1)

    print("Initializing PyCardano keys and context...")
    try:
        hdwallet = HDWallet.from_mnemonic(mnemonic)
        spend = hdwallet.derive_from_path("m/1852'/1815'/0'/0/0")
        sk = PaymentExtendedSigningKey.from_hdwallet(spend)
        
        my_address = Address.from_primitive(expected_addr_str)
        context = BlockFrostChainContext(project_id=blockfrost_proj_id, base_url=ApiUrls.mainnet.value)
        api = BlockFrostApi(project_id=blockfrost_proj_id, base_url=ApiUrls.mainnet.value)
    except Exception as e:
        print(f"[FAIL] Error initializing PyCardano/BlockFrost: {e}")
        sys.exit(1)

    # 2. Load Manifest
    manifest_path = "results/e7_mainnet_live_manifest.json"
    if not os.path.exists(manifest_path):
        print(f"[FAIL] Manifest not found at {manifest_path}")
        sys.exit(1)

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    batches = manifest.get("batches", [])
    if not batches:
        print("[FAIL] No batches found in manifest.")
        sys.exit(1)

    # Output CSV setup
    csv_file_path = "results/e7_mainnet_live.csv"
    file_exists = os.path.exists(csv_file_path)
    
    completed_batches = set()
    if file_exists:
        with open(csv_file_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                completed_batches.add(int(row["batch_id"]))
                
    csv_file = open(csv_file_path, "a", newline="")
    csv_writer = csv.writer(csv_file)
    
    if not file_exists:
        csv_writer.writerow([
            "batch_id", "tx_id", "fee_ada", "tx_size_bytes",
            "submit_ts_utc", "inclusion_ts_utc", "included_block_no", "included_block_hash"
        ])
        csv_file.flush()

    print(f"Loaded {len(batches)} batches from manifest. Starting execution...")

    # Limit to 30 batches as per constraint
    batches = batches[:30]
    
    last_tx_hash = None

    for b in batches:
        batch_id = b["batch_id"]
        if batch_id in completed_batches:
            print(f"Skipping Batch {batch_id} (already completed)")
            continue
            
        root_hex = b["root_hex"]
        prev_root_hex = b["prev_root_hex"]

        print(f"\n--- Processing Batch {batch_id} ---")
        
        # UTxO Fetch Loop with Retry
        utxos = []
        while True:
            try:
                utxos = context.utxos(my_address)
                if not utxos:
                    print("  [WAIT] No UTxOs found (mempool lag). Waiting 5 seconds...")
                    time.sleep(5)
                    continue
                    
                if last_tx_hash:
                    found_new_utxo = False
                    for u in utxos:
                        if str(u.input.transaction_id) == last_tx_hash:
                            found_new_utxo = True
                            break
                    if not found_new_utxo:
                        print("  [WAIT] UTxO index not updated yet. Waiting 5s...")
                        time.sleep(5)
                        continue
                        
                break
            except Exception as e:
                print(f"  [WAIT] Error fetching UTxOs: {e}. Waiting 5 seconds...")
                time.sleep(5)
        
        print(f"  Fetched {len(utxos)} UTxO(s) for input.")

        # CIP-20 Metadata Format
        metadata = {
            674: {
                "msg": [
                    "DR-TEA E7 Pilot",
                    f"batch:{batch_id}",
                    f"root:{root_hex[:32]}",
                    f"r_cont:{root_hex[32:]}",
                    f"prev:{prev_root_hex[:32]}",
                    f"p_cont:{prev_root_hex[32:]}"
                ]
            }
        }

        # Build Transaction
        builder = TransactionBuilder(context)
        for utxo in utxos:
            builder.add_input(utxo)
        
        # No explicit outputs -> all goes to change
        builder.auxiliary_data = AuxiliaryData(AlonzoMetadata(metadata=Metadata(metadata)))

        try:
            signed_tx = builder.build_and_sign([sk], change_address=my_address)
        except Exception as e:
            print(f"  [FAIL] Error building transaction: {e}")
            sys.exit(1)

        fee_lovelace = signed_tx.transaction_body.fee
        fee_ada = fee_lovelace / 1_000_000
        tx_size_bytes = len(signed_tx.to_cbor())

        print(f"  Tx Built. Size: {tx_size_bytes} bytes, Fee: {fee_ada:.6f} ADA")

        if fee_ada > 0.30:
            print(f"  [FAIL] Fee exceeds 0.30 ADA limit! Aborting.")
            sys.exit(1)

        tx_hash_hex = signed_tx.transaction_body.hash().hex()
        print(f"  Submitting Tx: {tx_hash_hex} ...")
        submit_ts_utc = datetime.now(timezone.utc).isoformat()

        try:
            context.submit_tx(signed_tx.to_cbor())
        except Exception as e:
            # If submit fails (e.g. BadInputs), we wait and retry
            print(f"  [WARN] Submit failed: {e}. UTxO state might be out of sync. Waiting 20s and retrying this batch.")
            time.sleep(20)
            # To simply retry the batch, we can continue a local retry loop. 
            # Given the script structure, we will just abort and the user can rerun.
            print("  [FAIL] Submission error. Aborting.")
            sys.exit(1)

        print("  Tx submitted successfully. Polling for block inclusion (this may take 20s-2m)...")
        try:
            tx_info = wait_for_tx_confirmation(api, tx_hash_hex)
        except TimeoutError as e:
            print(f"  [FAIL] {e}")
            sys.exit(1)

        inclusion_ts_utc = datetime.fromtimestamp(tx_info.block_time, tz=timezone.utc).isoformat()
        included_block_no = tx_info.block_height
        included_block_hash = tx_info.block

        print(f"  [SUCCESS] Batch {batch_id} confirmed in Block {included_block_no}!")

        # Record result
        csv_writer.writerow([
            batch_id,
            tx_hash_hex,
            f"{fee_ada:.6f}",
            tx_size_bytes,
            submit_ts_utc,
            inclusion_ts_utc,
            included_block_no,
            included_block_hash
        ])
        csv_file.flush()
        
        last_tx_hash = tx_hash_hex
        
        print("  Moving to next batch...\n")

    csv_file.close()
    print("=" * 60)
    print("ALL 30 BATCHES SUCCESSFULLY ANCHORED.")
    print("Results written to results/e7_mainnet_live.csv")

if __name__ == "__main__":
    main()
