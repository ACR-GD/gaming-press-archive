import argparse
import base64
import json
import os
import subprocess
import urllib.error
import urllib.request
from typing import Optional

# --- CONFIGURATION ---
INPUT_DIR = "output_Famitsu_1986_No01"
PAGE_COUNT = 10
VISION_MODEL = "gemma3:4b"
OUTPUT_FILE = "famitsu_pages_01_10_summary.json"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


def _run_command(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def _check_ollama_available() -> None:
    version = _run_command(["ollama", "--version"])
    if version.returncode != 0:
        raise RuntimeError(
            "Ollama n'est pas disponible. Installe-le puis relance ce script."
        )


def _ensure_model_present(model: str) -> None:
    list_result = _run_command(["ollama", "list"])
    if list_result.returncode != 0:
        raise RuntimeError(f"Impossible de lister les modèles Ollama: {list_result.stderr}")

    if model not in list_result.stdout:
        print(f"⬇️ Modèle absent, téléchargement: {model}")
        pull_result = _run_command(["ollama", "pull", model])
        if pull_result.returncode != 0:
            raise RuntimeError(f"Échec du pull du modèle {model}: {pull_result.stderr}")


def _call_ollama_api(model: str, prompt: str, image_path: Optional[str] = None) -> str:
    payload: dict[str, object] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if image_path:
        with open(image_path, "rb") as img:
            payload["images"] = [base64.b64encode(img.read()).decode("utf-8")]

    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Échec d'appel API Ollama: {exc}") from exc

    response = body.get("response", "")
    if not isinstance(response, str):
        raise RuntimeError(f"Réponse Ollama inattendue: {body}")
    return response.strip()


def _extract_page_text(model: str, image_path: str) -> str:
    prompt = (
        "Tu fais de l'OCR de haute fidélité sur cette page de magazine japonais. "
        "Extrais uniquement le texte lisible, sans traduction, sans commentaire, "
        "en conservant au mieux les noms propres de jeux."
    )
    return _call_ollama_api(model=model, prompt=prompt, image_path=image_path)


def _build_summary(model: str, extracted_text: str) -> str:
    prompt = (
        "Voici du texte OCR de 10 premières pages d'un magazine Famitsu.\n"
        "Fais un résumé concis en français.\n"
        "Concentre-toi sur le sommaire et les jeux mentionnés.\n"
        "Pour chaque jeu identifié, ajoute une courte note (contexte ou type de mention).\n\n"
        f"TEXTE OCR:\n{extracted_text}"
    )
    return _call_ollama_api(model=model, prompt=prompt)


def start_extraction_and_summary(
    model: str = VISION_MODEL,
    input_dir: str = INPUT_DIR,
    output_file: str = OUTPUT_FILE,
) -> None:
    print("🚀 Extraction OCR + résumé en cours...")

    _check_ollama_available()
    _ensure_model_present(model)

    page_results: list[dict[str, str]] = []
    all_text_chunks: list[str] = []

    for i in range(1, PAGE_COUNT + 1):
        filename = f"Famitsu_1986_No01_Page_{str(i).zfill(3)}.jpg"
        image_path = os.path.join(input_dir, filename)
        if not os.path.exists(image_path):
            page_results.append(
                {
                    "page": filename,
                    "status": "missing",
                    "text": "",
                }
            )
            continue

        print(f"🔍 OCR de {filename}...")
        try:
            page_text = _extract_page_text(model=model, image_path=image_path)
            page_results.append(
                {
                    "page": filename,
                    "status": "ok",
                    "text": page_text,
                }
            )
            all_text_chunks.append(f"[{filename}]\n{page_text}\n")
        except Exception as exc:  # noqa: BLE001
            page_results.append(
                {
                    "page": filename,
                    "status": f"error: {exc}",
                    "text": "",
                }
            )

    merged_text = "\n".join(all_text_chunks).strip()
    summary = _build_summary(model=model, extracted_text=merged_text) if merged_text else ""

    payload = {"model": model, "input_dir": input_dir, "pages": page_results, "summary": summary}
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"✅ Terminé. Résultat sauvegardé dans: {output_file}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OCR de pages Famitsu + résumé via Ollama.")
    parser.add_argument(
        "--model",
        default=VISION_MODEL,
        help=f"Nom du modèle Ollama (défaut: {VISION_MODEL})",
    )
    parser.add_argument(
        "--input-dir",
        default=INPUT_DIR,
        help=f"Dossier des images (défaut: {INPUT_DIR})",
    )
    parser.add_argument(
        "--output",
        default=OUTPUT_FILE,
        help=f"Fichier de sortie JSON (défaut: {OUTPUT_FILE})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    start_extraction_and_summary(model=args.model, input_dir=args.input_dir, output_file=args.output)