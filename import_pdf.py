from pathlib import Path
import json
from pypdf import PdfReader

PDF_PATH = Path("scheda.pdf")
OUT_JSON = Path("personaggio.json")

def main():
    reader = PdfReader(str(PDF_PATH))
    fields = reader.get_fields()

    data = {}

    for k, v in fields.items():
        val = v.get("/V", "")
        if val is None:
            val = ""
        data[k] = str(val)

    character = {
        "nome": data.get("untitled1",""),
        "motivazione": data.get("untitled2",""),
        "inventario_raw": data.get("untitled26",""),
        "xp_raw": data.get("untitled27",""),
        "inventario": [],
        "unguenti": [],
        "talenti": [],
        "qualita": [],
        "appunti": ""
    }

    OUT_JSON.write_text(json.dumps(character, indent=2, ensure_ascii=False), encoding="utf-8")

    print("IMPORT COMPLETATO")
    print("Creato file:", OUT_JSON)

if __name__ == "__main__":
    main()