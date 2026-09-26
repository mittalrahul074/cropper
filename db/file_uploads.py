"""
AWB (Air Way Bill) management functions for pending returns
"""
from db.firestore import get_db_connection
from firebase_admin import firestore
from datetime import datetime, timedelta
import pandas as pd
import tempfile

def update_data_in_firebase(platform: str, df : pd.DataFrame) -> None:
    db = firestore.client()
    
    if platform.lower() not in ["flipkart", "meesho"]:
        print(f"⚠️ Invalid platform '{platform}'. Must be 'flipkart' or 'meesho'.")
        return

    try:
        # Choose collection name based on platform
        collection_name = f"{platform.lower()}_sku_mapping"
        
        # Delete old data (optional)
        old_docs = db.collection(collection_name).stream()
        for doc in old_docs:
            doc.reference.delete()
        
        # Save each row as a document
        for idx, row in df.iterrows():
            doc_data = row.to_dict()
            # Handle NaN values
            doc_data = {k: (None if pd.isna(v) else v) for k, v in doc_data.items()}
            
            db.collection(collection_name).document(str(idx)).set(doc_data)
        
        print(f"✅ {len(df)} records saved to Firebase/{collection_name}")
        
    except Exception as e:
        print(f"❌ Error saving to Firebase: {e}")
def pending_awb(awb):
    """Record a pending AWB with timestamp"""
    db = get_db_connection()
    if db is None:
        print("❌ Database connection failed in pending_awb")
        return
    pending_ref = db.collection("pending_awbs").document(awb)
    pending_ref.set({
        "awb": awb,
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    print(f"✅ Pending AWB {awb} recorded in database.")


def pending_awbs_list():
    """Fetch all pending AWBs older than 1 day"""
    db = get_db_connection()
    if db is None:
        print("❌ Database connection failed in pending_awbs_list")
        return []
    # where timestamp is older than 1 day
    pending_ref = db.collection("pending_awbs").where("timestamp", "<=", datetime.utcnow() - timedelta(days=1))
    docs = pending_ref.stream()
    awb_list = [doc.id for doc in docs]
    print(f"✅ Fetched {len(awb_list)} pending AWBs from database.")
    return awb_list


def remove_pending_awb(awb):
    """Remove a pending AWB if it exists (no error if not found)"""
    db = get_db_connection()
    if db is None:
        print("❌ Database connection failed in remove_pending_awb")
        return
    try:
        pending_ref = db.collection("pending_awbs").document(awb)
        if pending_ref.get().exists:
            pending_ref.delete()
            print(f"✅ Removed pending AWB {awb} from database.")
    except Exception as e:
        print(f"⚠️ Could not remove pending AWB {awb}: {e}")
