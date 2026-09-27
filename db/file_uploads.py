"""
AWB (Air Way Bill) management functions for pending returns
"""
from db.firestore import get_db_connection
from firebase_admin import firestore
from datetime import datetime, timedelta
import pandas as pd
import tempfile

def update_data_in_firebase(platform: str, df : pd.DataFrame,user_name:str) -> None:
    db = firestore.client()
    
    if platform.lower() not in ["flipkart", "meesho"]:
        print(f"⚠️ Invalid platform '{platform}'. Must be 'flipkart' or 'meesho'.")
        return

    try:
        # Choose collection name based on platform
        collection_name = f"{platform.lower()}_sku_mapping"
        
        # Delete old data (optional)
        print("getting old docs")

        mapping_ref = (
            db.collection("user")
              .document(user_name)
              .collection(collection_name)
        )

        old_docs = mapping_ref.stream()
        for doc in old_docs:
            doc.reference.delete()
        print("delted old docs")

        if platform == "flipkart":
            print(df)
            sku_col = df.iloc[:, 1]
            fsn_col = df.iloc[:,4] #e coloum
        elif platform == "meesho":
            print(df)
            sku_col = df.iloc[:, 5]
            fsn_col = df.iloc[:,4]

        print(f"sku:{sku_col}")
        # Save each row as a document
        for idx, (sku, fsn) in enumerate(zip(sku_col, fsn_col)):

            if pd.isna(sku) or pd.isna(fsn):
                continue

            mapping_ref.document(str(idx)).set({
                "sku": str(sku),
                "fsn": str(fsn)
            })

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
            f"✅ {len(df)} records saved to Firebase/{collection_name}"
        )
                
    except Exception as e:
        print(f"❌ Error saving to Firebase: {e}")

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