"""
product_lookup.py  –  Fast product image lookup for packing staff
Drop into your picklist project root and add to navigation.

Employee reads SKU description from the printed label → types 2-3 words → sees product image.
All 1700 SKUs are cached on first load, so search is instant after that.

── CONFIGURE BELOW ──────────────────────────────────────────────────────────
Update PRODUCTS_COLLECTION and field names to match your Firestore schema.
"""

import streamlit as st
import streamlit.components.v1 as components
from firebase_utils import db, get_sku_from_order          # your existing Firebase connection

# ── CONFIG: match your Firestore products collection ─────────────────────────
PRODUCTS_COLLECTION = "products"       # collection where SKU data lives
SKU_FIELD           = "sku"            # field for SKU code/id (or use doc ID)
NAME_FIELD          = "name"           # product name / description field
IMAGE_URL_FIELD     = "img_url"      # image URL field  (adjust if different)
USE_DOC_ID_AS_SKU   = False             # True if document ID IS the SKU
# ─────────────────────────────────────────────────────────────────────────────


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner="Loading product catalog…")
def load_all_products() -> list[dict]:
    """
    Loads entire products collection once and caches for 10 minutes.
    Returns list of {sku, name, image_url} dicts.
    """
    docs = db.collection(PRODUCTS_COLLECTION).stream()
    products = []
    for doc in docs:
        data = doc.to_dict() or {}
        sku       = doc.id if USE_DOC_ID_AS_SKU else data.get(SKU_FIELD, doc.id)
        name      = data.get(NAME_FIELD, "")
        image_url = data.get(IMAGE_URL_FIELD, "")
        if image_url:                  # only include products that have an image
            products.append({
                "sku":       sku,
                "name":      name,
                "image_url": image_url,
                # searchable text: combine SKU + name, lowercased
                "_search":   f"{sku} {name}".lower(),
            })
    return products


def fuzzy_search(products: list[dict], query: str, max_results: int = 12) -> list[dict]:
    """
    Simple multi-word search: all words in query must appear in the searchable text.
    Returns up to max_results matches.
    """
    if not query.strip():
        return []
    words = query.lower().split()
    results = [p for p in products if all(w in p["_search"] for w in words)]
    return results[:max_results]


# ── UI ────────────────────────────────────────────────────────────────────────

def render_product_lookup_panel():
    st.set_page_config(
        page_title="Product Lookup",
        page_icon="🔍",
        layout="centered",
    )

    # Mobile-first styles
    st.markdown("""
        <style>
            /* Large search input for fat fingers */
            .stTextInput > div > input {
                font-size: 1.2rem !important;
                height: 3.2rem !important;
                border-radius: 12px !important;
            }
            /* Product card grid */
            .product-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
                gap: 12px;
                margin-top: 8px;
            }
            .product-card {
                border: 1px solid #ddd;
                border-radius: 12px;
                overflow: hidden;
                background: white;
                box-shadow: 0 1px 4px rgba(0,0,0,0.08);
                text-align: center;
            }
            .product-card img {
                width: 100%;
                aspect-ratio: 1;
                object-fit: cover;
            }
            .product-card .label {
                padding: 6px 8px;
                font-size: 0.72rem;
                color: #333;
                line-height: 1.3;
                word-break: break-word;
            }
            .product-card .sku-badge {
                font-size: 0.65rem;
                color: #888;
                padding: 0 8px 6px;
            }
            /* No results message */
            .no-result {
                text-align: center;
                padding: 2rem;
                color: #888;
                font-size: 1rem;
            }
        </style>
    """, unsafe_allow_html=True)

    st.title("🔍 Product Lookup")

    # Load catalog (cached)
    products = load_all_products()
    total    = len(products)

    if total == 0:
        st.error("No products found. Check PRODUCTS_COLLECTION and IMAGE_URL_FIELD in config.")
        return

    st.caption(f"{total} products loaded · Type to search")

    raw_html_code = """
<!DOCTYPE html>
<html>
<head>
<script src="https://unpkg.com/@zxing/library@0.19.1/umd/index.min.js"></script>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; padding: 4px; font-family: sans-serif; background: transparent; }
  #scanner-wrap { display: none; position: relative; width: 100%; }
  video { width: 100%; max-height: 260px; border-radius: 10px; object-fit: cover; display: block; }
  canvas { display: none; }
  #overlay {
    position: absolute; bottom: 10px; left: 10px; right: 10px;
    background: rgba(0,0,0,0.75); color: #00ff88;
    padding: 8px 12px; border-radius: 8px;
    font-size: 15px; font-weight: bold;
    display: none; text-align: center;
  }
  #aim {
    position: absolute; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    width: 200px; height: 100px;
    border: 2px solid rgba(255,80,80,0.8);
    border-radius: 6px; pointer-events: none;
  }
  #status {
    font-size: 12px; color: #888; margin: 4px 0 6px;
    min-height: 16px; text-align: center;
  }
  .btn-row { display: flex; gap: 8px; }
  button {
    flex: 1; padding: 10px; border: none; border-radius: 8px;
    cursor: pointer; font-size: 15px; font-weight: 600;
  }
  #startBtn { background: #ff4b4b; color: white; }
  #stopBtn  { background: #555; color: white; display: none; }
</style>
</head>
<body>
<div class="btn-row">
  <button id="startBtn" onclick="startScan()">📷 Scan Barcode</button>
  <button id="stopBtn"  onclick="stopScan()">✕ Stop</button>
</div>
<div id="status"></div>
<div id="scanner-wrap">
  <video id="video" autoplay playsinline muted></video>
  <canvas id="canvas"></canvas>
  <div id="aim"></div>
  <div id="overlay"></div>
</div>

<script>
let stream = null;
let rafId  = null;
let zxingReader = null;
let useNative = false;
let nativeDetector = null;

const video   = document.getElementById('video');
const canvas  = document.getElementById('canvas');
const overlay = document.getElementById('overlay');
const status  = document.getElementById('status');

// ── Send scanned value to parent Streamlit page ───────────────────────────
// Strategy: inject into the text input via React's native setter (works when
// same origin). If cross-origin is blocked, falls back to postMessage which
// the parent page can optionally listen to.
function sendValue(value) {
  overlay.style.display = 'block';
  overlay.innerText = '✓ ' + value;

  try {
    const parentDoc = window.parent.document;
    const inputs = parentDoc.querySelectorAll('input[type="text"]');

    if (inputs.length > 0) {
      const input = inputs[0];

      // React native setter
      const nativeInputValueSetter =
        Object.getOwnPropertyDescriptor(
          window.parent.HTMLInputElement.prototype,
          "value"
        ).set;

      nativeInputValueSetter.call(input, value);

      // Important events for Streamlit/React
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));

      // Focus + Enter
      input.focus();

      nativeInputValueSetter.call(input, value);

      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));

      input.focus();

      setTimeout(() => {
        input.blur();

        setTimeout(() => {
          input.focus();
        }, 50);

      }, 100);

      status.textContent = '✓ Sent: ' + value;
    }
  } catch(e) {
    console.error(e);
    status.textContent = '❌ Failed to inject';
  }

  setTimeout(stopScan, 1800);
}

// ── Start scanning ────────────────────────────────────────────────────────
async function startScan() {
  status.textContent = 'Requesting camera…';
  document.getElementById('startBtn').style.display = 'none';
  document.getElementById('stopBtn').style.display  = 'block';
  document.getElementById('scanner-wrap').style.display = 'block';
  overlay.style.display = 'none';

  // Prefer rear camera on mobile
  const constraints = {
    video: {
      facingMode: { ideal: 'environment' },
      width:  { ideal: 1280 },
      height: { ideal: 720 },
    }
  };

  try {
    stream = await navigator.mediaDevices.getUserMedia(constraints);
    video.srcObject = stream;
    await video.play();
    status.textContent = 'Camera ready — point at barcode';

    // Choose decode method
    if ('BarcodeDetector' in window) {
      useNative = true;
      nativeDetector = new BarcodeDetector({
        formats: [
          'ean_13','ean_8','code_128','code_39','code_93',
          'qr_code','upc_a','upc_e','itf','data_matrix'
        ]
      });
      status.textContent = 'Native scanner ready';
      requestAnimationFrame(tickNative);
    } else {
      // ZXing fallback
      useNative = false;
      zxingReader = new ZXing.BrowserMultiFormatReader();
      // ZXing can decode directly from the video element
      zxingReader.decodeFromStream(stream, video, (result, err) => {
        if (result) {
          sendValue(result.getText());
        }
      });
      status.textContent = 'ZXing scanner ready';
    }
  } catch(err) {
    status.textContent = '❌ Camera error: ' + err.message;
    console.error(err);
    stopScan();
  }
}

// ── Native BarcodeDetector tick ───────────────────────────────────────────
async function tickNative() {
  if (!stream) return;
  if (video.readyState === video.HAVE_ENOUGH_DATA) {
    canvas.width  = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    try {
      const barcodes = await nativeDetector.detect(canvas);
      if (barcodes.length > 0) {
        sendValue(barcodes[0].rawValue);
        return; // stop ticking — stopScan called by sendValue
      }
    } catch(e) { /* ignore decode errors */ }
  }
  rafId = requestAnimationFrame(tickNative);
}

// ── Stop scanning ─────────────────────────────────────────────────────────
function stopScan() {
  if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
  if (zxingReader) { try { zxingReader.reset(); } catch(e){} zxingReader = null; }
  if (stream) {
    stream.getTracks().forEach(t => t.stop());
    stream = null;
  }
  video.srcObject = null;
  document.getElementById('scanner-wrap').style.display = 'none';
  document.getElementById('startBtn').style.display = 'block';
  document.getElementById('stopBtn').style.display  = 'none';
  if (!overlay.innerText.startsWith('✓')) status.textContent = '';
}
</script>
</body>
</html>
"""

    scanned = components.html(raw_html_code, height=360)
    print(f"Scanned value from component: {scanned}")

    # Search box — autofocus on mobile add barcode scanner input
    query = st.text_input(
        label="Search",
        placeholder="Type product name or SKU or order id…",
        label_visibility="collapsed",
    )

    # Results
    if not query.strip():
        st.markdown('<div class="no-result">👆 Start typing to find a product</div>', unsafe_allow_html=True)
        return
    flag =0
    # match query if it starts with OD or it ends with _1,_2 or _3
    
    results = fuzzy_search(products, query)

    if not results:
        if flag == 1:
            st.markdown('<div class="no-result">No product found for that order ID</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="no-result">No match — try fewer or different words</div>', unsafe_allow_html=True)
        return

    # Render image cards — 3 per row on mobile
    cols_per_row = 3
    rows = [results[i:i+cols_per_row] for i in range(0, len(results), cols_per_row)]

    for row in rows:
        cols = st.columns(cols_per_row)
        for col, product in zip(cols, row):
            with col:
                st.markdown(
                    f"<div style='font-size:0.7 rem; text-align:center; color:#333; margin-top:2px;'>"
                    f"{product['name'][:40] + '…' if len(product['name']) > 40 else product['name']}"
                    f"</div>"
                    f"<div style='font-size:1rem; text-align:center; color:#999;'>{product['sku']}</div>",
                    unsafe_allow_html=True,
                )
                try:
                    st.image(product["image_url"], use_container_width=True)
                except Exception:
                    st.markdown("🖼️ No image")

    if len(results) == 12:
        st.caption("Showing top 12 results — type more words to narrow down")


if __name__ == "__main__":
    main()