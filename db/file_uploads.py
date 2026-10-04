"""
AWB (Air Way Bill) management functions for pending returns
"""
from db.firestore import get_db_connection
from firebase_admin import firestore
from datetime import datetime, timedelta
import pandas as pd
import tempfile

def update_data_in_firebase(
    platform: str,
    df: pd.DataFrame,
    user_name: str
) -> None:

    db = firestore.client()

    platform = platform.lower()

    if platform not in ["flipkart", "meesho"]:
        print(f"⚠️ Invalid platform '{platform}'.")
        return

    try:
        collection_name = f"{platform}_sku_mapping"

        mapping_ref = (
            db.collection("user")
            .document(user_name)
            .collection(collection_name)
        )

        # ---------------------------------------
        # Select SKU / FSN columns
        # ---------------------------------------

        if platform == "flipkart":
            sku_col = df.iloc[:, 1]   # B
            fsn_col = df.iloc[:, 4]   # E

        elif platform == "meesho":
            sku_col = df.iloc[:, 5]
            fsn_col = df.iloc[:, 4]

        # ---------------------------------------
        # Get existing SKUs
        # ---------------------------------------

        print("🔍 Getting existing SKUs...", flush=True)

        existing_docs = mapping_ref.stream()

        existing_skus = {
            doc.id
            for doc in existing_docs
        }

        print(
            f"📦 Existing SKUs: {len(existing_skus)}",
            flush=True
        )

        # ---------------------------------------
        # Prepare new records
        # ---------------------------------------

        new_records = []

        for sku, fsn in zip(sku_col, fsn_col):

            if pd.isna(sku) or pd.isna(fsn):
                continue

            sku = str(sku).strip()
            fsn = str(fsn).strip()

            if fsn in existing_skus:
                continue

            new_records.append({
                "sku": sku,
                "fsn": fsn
            })

            # Prevent duplicate SKU within the same file
            existing_skus.add(fsn)

        print(
            f"🆕 New SKUs: {len(new_records)}",
            flush=True
        )

        # ---------------------------------------
        # Batch write
        # ---------------------------------------

        batch = db.batch()
        batch_count = 0
        total_added = 0

        for record in new_records:

            doc_ref = mapping_ref.document(record["fsn"])

            batch.set(doc_ref, record)

            batch_count += 1

            # Firestore batch limit = 500 operations
            if batch_count == 500:

                batch.commit()

                total_added += batch_count

                print(
                    f"✅ Uploaded {total_added} records...",
                    flush=True
                )

                batch = db.batch()
                batch_count = 0

        # Commit remaining records
        if batch_count > 0:

            batch.commit()

            total_added += batch_count

        # ---------------------------------------
        # Update upload date
        # ---------------------------------------

        metadata_ref = (
            db.collection("user")
            .document(user_name)
            .collection("metadata")
            .document(collection_name)
        )

        metadata_ref.set({
            "uploaded_at": firestore.SERVER_TIMESTAMP
        })

        print(
            f"✅ Upload complete. Added {total_added} new SKUs.",
            flush=True
        )

    except Exception as e:

        print(
            f"❌ Error saving to Firebase: {e}",
            flush=True
        )

def get_last_upload_date(user_name: str, platform: str):
    db = firestore.client()

    platform = platform.lower()
    collection_name = f"{platform}_sku_mapping"

    metadata_ref = (
        db.collection("user")
        .document(user_name)
        .collection("metadata")
        .document(collection_name)
    )

    doc = metadata_ref.get()

    if not doc.exists:
        return None

    data = doc.to_dict()

    uploaded_at = data.get("uploaded_at")

    if uploaded_at is None:
        return None

    return uploaded_at

def get_fsn_from_fb(user_name: str, sku: str, platform: str) -> str | None:
    db = firestore.client()

    platform = platform.lower()
    collection_name = f"{platform}_sku_mapping"

    mapping_ref = (
        db.collection("user")
        .document(user_name)
        .collection(collection_name)
        .where("sku", "==", sku)
    )

    docs = mapping_ref.stream()

    for doc in docs:
        data = doc.to_dict()
        return data.get("fsn")

    return None