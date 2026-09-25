"""
label_image.py  –  Add product images to Flipkart shipping label PDFs
Drop this file into your picklist project and add it to your navigation.

Requirements (add to requirements.txt if not already present):
    pymupdf>=1.24.0
    pdfplumber>=0.10.0
    requests>=2.31.0
    Pillow>=10.0.0

Usage:
    Upload a Flipkart multi-label PDF.
    The app auto-extracts Order IDs → fetches SKU + image from Firebase → stamps image on each label.
    Download the enhanced PDF.
"""

import streamlit as st
import fitz  # PyMuPDF
import pdfplumber
import re
import requests
import io
import tempfile
import os
import time
from PIL import Image

# ── Reuse your existing Firebase connection ──────────────────────────────────
from firebase_utils import db  # your existing module

# ── CONFIGURE: adjust collection/field names to match your Firestore ─────────
ORDERS_COLLECTION   = "orders"     # collection where order_id is the document ID
SKU_FIELD           = "sku"        # field name inside the order document

# ⚠️  UPDATE THIS to match your products collection
# Option A – products collection where doc ID = SKU, with an image_url field
PRODUCTS_COLLECTION = "products"
IMAGE_URL_FIELD     = "image_url"  # or "image", "img_url" etc.

# Option B – if image is stored directly on the order doc, set this to True
IMAGE_ON_ORDER_DOC  = False
ORDER_IMAGE_FIELD   = "image_url"  # only used if IMAGE_ON_ORDER_DOC = True
# ─────────────────────────────────────────────────────────────────────────────

ORDER_ID_PATTERN = re.compile(r'\b(OD\d{15,20})\b')
SKU_PATTERN = re.compile(r"\|\s*([^|]+?)\s*\|")
sku_image_map = {}  # Cache for SKU → image bytes to avoid repeated downloads

# ── Firebase helpers ──────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def fetch_image_url(order_id: str) -> tuple[str | None, str | None]:
    """Returns (sku, image_url) for an order_id. Cached for 5 minutes."""
    try:
        order_doc = db.collection(ORDERS_COLLECTION).document(order_id).get()
        if not order_doc.exists:
            return None, None
        order_data = order_doc.to_dict()
        sku = order_data.get(SKU_FIELD)

        if IMAGE_ON_ORDER_DOC:
            return sku, order_data.get(ORDER_IMAGE_FIELD)

        if not sku:
            return None, None

        sku_lower = sku.lower()
        product_doc = db.collection(PRODUCTS_COLLECTION).document(sku_lower).get()
        if not product_doc.exists:
            return sku, None
        return sku, product_doc.to_dict().get(IMAGE_URL_FIELD)

    except Exception as e:
        st.warning(f"Firebase error for {order_id}: {e}")
        return None, None


def download_image(url: str) -> bytes | None:
    """Download an image from URL and return as bytes."""
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None

def get_barcode_image(sku: str) -> bytes | None:
    """Generate a barcode image for the SKU using an online API."""
    if sku in sku_image_map:
        return sku_image_map[sku]  # Return cached image bytes
    try:
        start = time.perf_counter()
        # Using Barcode API from bwip-js (no API key required)
        api_url = (
            f"https://bwipjs-api.metafloor.com/"
            f"?bcid=datamatrix"
            f"&text={sku}"
            f"&scale=8"
            f"&paddingwidth=0"
            f"&paddingheight=0"
        )
        resp = requests.get(api_url, timeout=5)
        resp.raise_for_status()
        print(f"Barcode fetch time for {sku}: {time.perf_counter() - start:.3f}s")
        sku_image_map[sku] = resp.content  # Cache the image bytes
        return resp.content
    except Exception:
        return None

# ── PDF processing ────────────────────────────────────────────────────────────

def extract_order_id(page_text: str) -> str | None:
    """Extract OD... order ID from label text."""
    match = ORDER_ID_PATTERN.search(page_text)
    return match.group(1) if match else None

def extract_sku_flipkart(page_text: str) -> str | None:
    match = SKU_PATTERN.search(page_text)
    if match:
        sku = match.group(1).strip()
        #remove 1 & 2 nd word
        parts = sku.split()
        if len(parts) > 2:
            sku = " ".join(parts[2:])
        # remove first character
        sku = sku[1:]
        return sku.strip()
    
def extract_sku_meesho(page_text: str) -> str | None:
    lines = [
        line.strip()
        for line in page_text.splitlines()
        if line.strip()
    ]
    for i, line in enumerate(lines): 
        if ( line == "SKU"):
            # print (f"Found SKU line at index {i}: {line}")
            if(i + 10 < len(lines) and lines[i + 1] == "Size" and lines[i + 2] == "Qty" and lines[i + 3] == "Color" and "Order No" in lines[i + 4] ): 
                sku = lines[i + 5] 
                return sku

def stamp_image_on_page(page: fitz.Page, img_bytes: bytes) -> bool:
    """
    Insert a small product image into the label page.
    Targets the blank space in the SKU description row.
    Returns True if successful.
    """
    try:
        rect = page.rect
        w, h = rect.width, rect.height

        # Flipkart label: SKU row is roughly 65-85% down the page
        # Place image in the right portion of the description cell
        # ~18% of the smaller dimension
        margin    = w * 0.04
        
        img_width = 80
        img_height = 80

        x1 = w - img_width - margin
        y1 = h * 0.64
        x2 = x1 + img_width
        y2 = y1 + img_height

        img_rect = fitz.Rect(x1, y1, x2, y2)

        page.insert_image(img_rect, stream=img_bytes, keep_proportion=True)

        # Draw a thin border around the image
        page.draw_rect(img_rect, color=(0.7, 0.7, 0.7), width=0.5)
        return True

    except Exception as e:
        return False

def stamp_image_on_page_meesho(page: fitz.Page, img_bytes: bytes) -> bool:
    """
    Insert a small product image into the label page.
    Targets the blank space in the SKU description row.
    Returns True if successful.
    """
    try:
        rect = page.rect
        w, h = rect.width, rect.height

        # Meesho label: use a larger image size than Flipkart
        margin = w * 0.02
        max_img_size = min(w * 0.26, h * 0.26, 170)

        img_width = max_img_size
        img_height = max_img_size

        x1 = w - (img_width*4.1)
        y1 = h * 0.35
        x2 = x1 + img_width
        y2 = y1 + img_height

        img_rect = fitz.Rect(x1, y1, x2, y2)

        page.insert_image(img_rect, stream=img_bytes, keep_proportion=True)

        # Draw a thin border around the image
        page.draw_rect(img_rect, color=(0.7, 0.7, 0.7), width=0.5)
        return True

    except Exception as e:
        return False


def process_pdf(pdf_bytes: bytes, platform: str) -> tuple[bytes, list[dict]]:
    """Main processing function that handles different platforms."""
    if platform == "flipkart":
        return process_pdf_flipkart(pdf_bytes)
    elif platform == "meesho":
        return process_pdf_meesho(pdf_bytes)
    
def prepare_barcode_image(
    img_bytes: bytes,
    padding: int = 20,
    background="white"
) -> bytes:
    """
    Add white background + quiet zone around barcode/QR image.
    Returns cleaned PNG bytes.
    """

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")

    # Create white background
    bg = Image.new(
        "RGB",
        (
            img.width + padding * 2,
            img.height + padding * 2
        ),
        background
    )

    # Paste barcode in center
    bg.paste(img, (padding, padding), img)

    output = io.BytesIO()
    bg.save(output, format="PNG")

    return output.getvalue()

def prepare_barcode_image_meesho(
    img_bytes: bytes,
    padding: int = 20,
    background="white"
) -> bytes:
    """
    Add white background + quiet zone around barcode/QR image.
    Returns cleaned PNG bytes.
    """

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")

    # Create white background
    bg = Image.new(
        "RGB",
        (
            img.width + padding * 2,
            img.height + padding * 2
        ),
        background
    )

    # Paste barcode in center
    bg.paste(img, (padding, padding), img)

    output = io.BytesIO()
    bg.save(output, format="PNG")

    return output.getvalue()

def crop_pdf(pdf_bytes: bytes,left,top,right,bottom) -> bytes:
    """
    Crop the PDF to remove extra margins (specific to Meesho labels).
    This helps ensure the stamped image fits well within the label area.
    """
    t= time.perf_counter()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page in doc:
        rect = page.rect
        w, h = rect.width, rect.height

        # Define crop box (adjust these values based on your label layout)
        crop_rect = fitz.Rect(
            w * left,  # left
            h * top,  # top
            w * right,  # right
            h * bottom   # bottom
        )
        page.set_cropbox(crop_rect)

    output_buf = io.BytesIO()
    doc.save(output_buf)
    doc.close()
    print(f"PDF cropping time: {time.perf_counter() - t:.3f}s")
    return output_buf.getvalue()

def clean_sku(sku):
    if not sku:
        return ""

    sku = str(sku)

    # Remove leading/trailing spaces and convert to uppercase
    sku = sku.strip().upper()

    # Remove invisible / whitespace characters
    # sku = re.sub(r"\s+", "", sku)

    return sku

def get_fsn_from_xls(sku: str, platform: str) -> str | None:
    """
    Fetch the FSN (Flipkart Stock Number) for a given SKU from the uploaded listing XLS.
    Returns FSN as string if found, else None.
    """
    user_ip = st.session_state.get("user_ip")
    if not user_ip:
        st.warning("User IP not found in session state.")
        return None

    xls_bytes = load_uploaded_file(user_ip, platform)
    if not xls_bytes:
        st.warning(f"No {platform} listing file found for user {user_ip}.")
        return None

    try:
        import pandas as pd
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_file:
            tmp_file.write(xls_bytes)
            tmp_file_path = tmp_file.name

        # Read the XLS file
        df = pd.read_excel(tmp_file_path)

        # Assuming the XLS has columns 'SKU' in column B and 'FSN' in column E
        if platform == "flipkart":
            sku_col = df.columns[1].strip()  # Column B
        else:
            sku_col = df.columns[5].strip()  # Column F
        fsn_col = df.columns[4].strip()  # Column E

        print(f"Loaded {platform} listing with {len(df)} rows. Searching for SKU: >>>{sku}<<<")

        if sku_col not in df.columns or fsn_col not in df.columns:
            st.warning(f"{platform.capitalize()} listing file missing required columns.")
            return None

        # check if sku is in the sku column (case-insensitive, stripped)
        sku = clean_sku(sku)
        if sku not in df[sku_col].astype(str).str.upper().str.strip().values:
            st.warning(f"SKU {sku} not found in {platform} listing.")
            return None

        # Search for the SKU in the DataFrame
        matched_row = df[df[sku_col].astype(str).str.upper().str.strip() == sku]
        if not matched_row.empty:
            print(f"Found SKU {sku} in {platform} listing. FSN: {matched_row.iloc[0][fsn_col]}")
            fsn_value = matched_row.iloc[0][fsn_col]
            return str(fsn_value).strip() if pd.notna(fsn_value) else None
        else:
            print(f"SKU {sku} not found in {platform} listing.")

    except Exception as e:
        st.warning(f"Error reading {platform} listing file: {e}")
        return None
    finally:
        if os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)
    
def process_pdf_meesho(uploaded_bytes: bytes) -> tuple[bytes, list[dict]]:
    """
    Process every page of the label PDF:
      1. Extract Order ID
      2. Fetch image URL from Firebase
      3. Stamp image onto the page
    Returns (modified_pdf_bytes, results_log).
    """

    start = time.time()
    uploaded_bytes = crop_pdf(uploaded_bytes, 0, 0, 1, 0.5)
    print("Crop:", time.time() - start)
    results = []
    page_sku_map = {}  # Track SKU for each page index

    # --- Modify PDF (PyMuPDF for image stamping) ---
    doc = fitz.open(stream=uploaded_bytes, filetype="pdf")

    start = time.time()
    for i, page in enumerate(doc):
        start_page = time.time()
        text = page.get_text("text") or ""
        # text = page_texts[i] if i < len(page_texts) else ""
        print(f"Page {i+1} - Text extraction time: {time.time() - start_page:.3f}s")
        start_sku = time.time()
        sku = extract_sku_meesho(text)
        # print(f"Page {i+1} - Extracted SKU: {sku}")

        if not sku:
            results.append({"page": i + 1, "order_id": "—", "sku": "—", "status": "⚠️ SKU not found"})
            page_sku_map[i] = ("", i)  # Empty SKU, keep original index
            continue
        print(f"Page {i+1} - SKU extraction time: {time.time() - start_sku:.3f}s")
        start_sku = time.time()
        product_id = get_fsn_from_xls(sku, platform="meesho")  # Fetch product ID from Meesho listing xls
        if not product_id:
            print(f"Page {i+1} - Product ID not found for SKU: {sku}")
            img_bytes = get_barcode_image(sku)  # Use barcode image instead of product image
        else:
            print(f"Page {i+1} - Product ID fetched: {product_id}")
            meesho_url = f"https://www.meesho.com/search?q=s-{product_id}&searchIdentifier=text_search"
            img_bytes = get_barcode_image(meesho_url)
        # img_bytes = download_image(image_url)
        if img_bytes:
            img_bytes = prepare_barcode_image_meesho(
                img_bytes,
                padding=25
        )
        if not img_bytes:
            results.append({"page": i + 1, "sku": sku, "status": "❌ Image download failed"})
            page_sku_map[i] = (sku, i)
            continue
        print(f"Page {i+1} - Image preparation time: {time.time() - start_sku:.3f}s")
        start_stamp = time.time()
        ok = stamp_image_on_page_meesho(page, img_bytes)
        print(f"Page {i+1} - Stamp time: {time.time() - start_stamp:.3f}s")
        status = "✅ Image added" if ok else "❌ Stamp failed"
        results.append({"page": i + 1, "sku": sku, "status": status})
        page_sku_map[i] = (sku, i)

    print("Processing time:", time.time() - start)
    start = time.time()
    sorted_pages = sorted(page_sku_map.items(), key=lambda x: x[1][0], reverse=True)
    new_doc = fitz.open()
    sorted_indices = []
    for original_idx, (sku, _) in sorted_pages:
        new_doc.insert_pdf(doc, from_page=original_idx, to_page=original_idx)
        sorted_indices.append(original_idx + 1)

    results_sorted = []
    for new_page_num, original_idx in enumerate(sorted_indices):
        for result in results:
            if result["page"] == original_idx + 1:
                result["new_page"] = new_page_num + 1
                results_sorted.append(result)
                break
    print("Sorting time:", time.time() - start)

    output_buf = io.BytesIO()
    new_doc.save(output_buf)
    new_doc.close()
    return output_buf.getvalue(), results_sorted

def process_pdf_flipkart(uploaded_bytes: bytes) -> tuple[bytes, list[dict]]:
    """
    Process every page of the label PDF:
      1. Extract Order ID
      2. Fetch image URL from Firebase
      3. Stamp image onto the page
    Returns (modified_pdf_bytes, results_log).
    """
    uploaded_bytes = crop_pdf(uploaded_bytes, 0.31, 0.03, 0.68, 0.46)
    results = []

    # --- Extract text (pdfplumber is better for text positions) ---
    page_texts = []

    # --- Modify PDF (PyMuPDF for image stamping) ---
    doc = fitz.open(stream=uploaded_bytes, filetype="pdf")

    t = time.perf_counter()
    # with pdfplumber.open(io.BytesIO(uploaded_bytes)) as plumber_pdf:
    #     for p in plumber_pdf.pages:
    #         page_texts.append(p.extract_text() or "")
    for page in doc:
        page_texts.append(
            page.get_text("text")
        )
    print(f"Text extraction time: {time.perf_counter() - t:.3f}s")


    for i, page in enumerate(doc):

        page_start = time.perf_counter()

        text = page_texts[i] if i < len(page_texts) else ""
        t = time.perf_counter()
        sku = extract_sku_flipkart(text)
        print(f"Page {i+1} - SKU extraction: {time.perf_counter() - t:.3f}s")

        if not sku:
            results.append({"page": i + 1, "order_id": "—", "sku": "—", "status": "⚠️ SKU not found"})
            continue

        t = time.perf_counter()
        # img_bytes = download_image(image_url)
        fsn  = get_fsn_from_xls(sku, platform="flipkart")  # Fetch FSN from Flipkart listing xls
        if not fsn:
            print(f"Page {i+1} - FSN not found for SKU: {sku}")
            results.append({"page": i + 1, "sku": sku, "status": "⚠️ FSN not found in Flipkart listing"})
            img_bytes = get_barcode_image(sku)  # Use barcode image instead of product image
        else:
            print(f"Page {i+1} - FSN fetched: {fsn}")
            flip_url = f"https://www.flipkart.com/i/p/itme?pid={fsn}"
            img_bytes = get_barcode_image(flip_url)
        print(f"Page {i+1} - Image fetching: {time.perf_counter() - t:.3f}s")
        #save image for debugging in images folder with filename as order_id.png
        # with tempfile.TemporaryDirectory() as tmpdir:
        #     img_path = os.path.join(tmpdir, f"{sku}.png")
        #     with open(img_path, "wb") as f:
        #         f.write(img_bytes)
        #     st.image(img_path, caption=f"Barcode for {sku}", width=200)
        t = time.perf_counter()
        if img_bytes:
            img_bytes = prepare_barcode_image(
                img_bytes,
                padding=20
            )
        print(f"Page {i+1} - Image preparation: {time.perf_counter() - t:.3f}s")
        t = time.perf_counter()
        if not img_bytes:
            results.append({"page": i + 1, "sku": sku, "status": "❌ Image download failed"})
            continue

        ok = stamp_image_on_page(page, img_bytes)
        print(f"Page {i+1} - Image stamping: {time.perf_counter() - t:.3f}s")
        print(
            f"TOTAL PAGE {i+1}: "
            f"{time.perf_counter() - page_start:.3f}s"
        )
        status = "✅ Image added" if ok else "❌ Stamp failed"
        results.append({"page": i + 1, "sku": sku, "status": status})

    output_buf = io.BytesIO()
    doc.save(output_buf)
    doc.close()
    return output_buf.getvalue(), results


# ── Streamlit UI ──────────────────────────────────────────────────────────────

def get_user_ip() -> str:
    """Return the user's IP address from the Streamlit request headers."""
    try:
        headers = st.context.headers
        forwarded_for = headers.get("X-Forwarded-For", "")
        st.info(f"User IP from headers: {forwarded_for}")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        st.warning("Could not determine user IP from headers. Using fallback.")
        return headers.get("X-Real-IP", "") or headers.get("Remote-Addr", "Unknown")
    except Exception:
        st.warning("Could not determine user IP.")
        return "Unknown"


def store_uploaded_file(uploaded_file, user_ip: str, platform: str) -> str | None:
    """Store an uploaded file in a directory named for the uploader's IP."""
    if uploaded_file is None:
        return None

    safe_ip = re.sub(r"[^A-Za-z0-9_.-]", "_", user_ip or "Unknown")
    storage_dir = os.path.join("uploaded_files", safe_ip, platform)
    os.makedirs(storage_dir, exist_ok=True)
    file_path = os.path.join(storage_dir, os.path.basename(platform))

    with open(file_path, "wb") as file_handle:
        file_handle.write(uploaded_file.getvalue())
    return file_path

def load_uploaded_file(user_ip: str, platform: str) -> bytes | None:
    """Load a previously uploaded file for the given user IP and platform."""
    safe_ip = re.sub(r"[^A-Za-z0-9_.-]", "_", user_ip or "Unknown")
    storage_dir = os.path.join("uploaded_files", safe_ip, platform)
    file_path = os.path.join(storage_dir, os.path.basename(platform))

    if os.path.exists(file_path):
        with open(file_path, "rb") as file_handle:
            return file_handle.read()
    return None


def render_label_stamper_panel():
    st.set_page_config(
        page_title="Label Image Stamper",
        page_icon="🖨️",
        layout="centered",
    )

    # Mobile-friendly CSS
    st.markdown("""
        <style>
            .stButton > button {
                width: 100%;
                height: 3.2rem;
                font-size: 1.1rem;
                border-radius: 10px;
            }
            .stDownloadButton > button {
                width: 100%;
                height: 3.5rem;
                font-size: 1.15rem;
                background-color: #1a73e8;
                color: white;
                border-radius: 10px;
            }
            .result-box {
                padding: 0.4rem 0.8rem;
                border-radius: 8px;
                margin: 4px 0;
                font-size: 0.9rem;
            }
        </style>
    """, unsafe_allow_html=True)

    st.title("🖨️ Label Image Stamper")
    user_ip = get_user_ip()
    if user_ip is None:
        st.error("Could not determine your IP address. Please check your network settings.")
        
    st.session_state["user_ip"] = user_ip

    is_flipkart_file = 0
    is_meesho_file = 0
    if load_uploaded_file(user_ip, "flipkart"):
        st.success("✅ Flipkart listing xls already uploaded")
        is_flipkart_file = 1
    else:
        st.caption("Upload Flipkart listing xls file")

        flipkart_file = st.file_uploader(
            "📂 Upload Flipkart listing xls file",
            type=["xls", "xlsx"],
            help="Download the listing xls from Flipkart seller panel and upload here",
        )
        if flipkart_file is not None:
            store_uploaded_file(flipkart_file, user_ip, "flipkart")

    if load_uploaded_file(user_ip, "meesho"):
        st.success("✅ Meesho inventory file already uploaded")
        is_meesho_file = 1
    else:
        st.caption("Upload Meesho inventory file")

        meesho_file = st.file_uploader(
            "📂 Upload Meesho inventory file",
            type=["xls", "xlsx"],
            help="Download the inventory xls from Meesho seller panel and upload here",
        )
        if meesho_file is not None:
            store_uploaded_file(meesho_file, user_ip, "meesho")

    if is_flipkart_file and is_meesho_file:
        st.caption("Upload Flipkart label PDF → auto-adds product images → download for printing")

        uploaded = st.file_uploader(
            "📂 Upload Label PDF",
            type=["pdf"],
            help="Download the label PDF from Flipkart seller panel and upload here",
        )

        if uploaded is None:
            st.info("👆 Upload a label PDF to get started")
            return

        pdf_bytes = uploaded.read()
        total_pages = len(list(pdfplumber.open(io.BytesIO(pdf_bytes)).pages))
        st.success(f"📄 Loaded **{total_pages} label(s)**")

        platform = st.radio(
            "Select Platform",
            ["flipkart", "meesho"],
            index=0,
            format_func=lambda x: x.capitalize(),
            horizontal=True
        )

        if st.button("🚀 Process Labels", type="primary"):
            with st.spinner(f"Processing {total_pages} labels… fetching images…"):
                modified_pdf, results = process_pdf(pdf_bytes,platform)

            # Results table
            ok_count = sum(1 for r in results if "✅" in r["status"])
            st.markdown(f"### Results: {ok_count}/{total_pages} labels stamped")

            for r in results:
                color = "#d4edda" if "✅" in r["status"] else "#fff3cd" if "⚠️" in r["status"] else "#f8d7da"
                st.markdown(
                    f'<div class="result-box" style="background:{color}">'
                    f'<b>Page {r["page"]}</b> &nbsp;|&nbsp; {r["sku"]} &nbsp;|&nbsp; '
                    f'</div>',
                    unsafe_allow_html=True,
                )

            st.divider()
            st.download_button(
                label="⬇️ Download Enhanced PDF",
                data=modified_pdf,
                file_name=f"labels_with_images_{uploaded.name}",
                mime="application/pdf",
            )
            st.caption("Print this PDF directly. Product images are stamped on each label.")
    else:
        st.info("👆 Upload both Flipkart and Meesho listing files to enable label processing.")


if __name__ == "__main__":
    main()
