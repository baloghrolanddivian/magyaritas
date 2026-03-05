# Külföldi számla fordító webapp

Egyszerű Flask alapú webes felület, ahol egy külföldi számlát feltöltesz, majd a rendszer automatikusan készít egy magyar nyelvű Word (`.docx`) dokumentumot a kinyert adatokkal.

## Funkciók

- PDF, képfájl és TXT számlák feltöltése
- Alap mezők automatikus felismerése (számlaszám, dátum, határidő, szállító, vevő, nettó, áfa, bruttó, pénznem)
- Egy kattintással letölthető magyar fordítási dokumentum (`.docx`)
- Eredeti kinyert szöveg beágyazása a Word dokumentumba ellenőrzéshez

## Indítás

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Ezután nyisd meg: `http://localhost:5000`

## Megjegyzés OCR-ről

Képfájlok esetén a `pytesseract` használatához rendszer szinten szükséges a Tesseract OCR bináris. PDF esetén a szövegkivonatolás a `pypdf` csomaggal történik.
