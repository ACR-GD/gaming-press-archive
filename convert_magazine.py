import os
from pdf2image import convert_from_path

# --- CONFIGURATION ---
MAGAZINE_NAME = "Famitsu_1986_No01"
PDF_PATH = "/Users/acr/magazines/famitsu-01.pdf"
OUTPUT_FOLDER = f"./output_{MAGAZINE_NAME}"
DPI = 300 # 300 est le "sweet spot" pour GPT-4o Vision

# Créer le dossier s'il n'existe pas
if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)

print(f"🚀 Début de la conversion de {MAGAZINE_NAME}...")

# Conversion
# thread_count=4 permet d'utiliser plusieurs coeurs de ton processeur
pages = convert_from_path(PDF_PATH, dpi=DPI, thread_count=4)

for i, page in enumerate(pages):
    # Formatage du nom : Famitsu_1986_No01_Page_001.jpg
    page_number = str(i + 1).zfill(3)
    filename = f"{MAGAZINE_NAME}_Page_{page_number}.jpg"
    
    # Sauvegarde en haute qualité
    page.save(os.path.join(OUTPUT_FOLDER, filename), "JPEG", quality=95)
    print(f"✅ Page {page_number} exportée.")

print(f"\n✨ Terminé ! Tes images sont dans : {OUTPUT_FOLDER}")