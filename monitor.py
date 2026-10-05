import html
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation

import requests


# ============================================================
# CONFIGURAZIONE
# ============================================================

FILE_PRODOTTI = "prodotti.json"
FILE_STATO = "stato.json"

TINYFISH_URL = "https://api.fetch.tinyfish.ai"
BREVO_URL = "https://api.brevo.com/v3/smtp/email"

MAX_ERRORI_CONSECUTIVI = 3


# ============================================================
# GESTIONE FILE JSON
# ============================================================

def carica_json(percorso, default=None):
    try:
        with open(percorso, "r", encoding="utf-8") as file:
            return json.load(file)

    except FileNotFoundError:
        return default

    except json.JSONDecodeError as errore:
        print(
            f"ERRORE: {percorso} contiene JSON non valido: "
            f"{errore}"
        )
        sys.exit(1)


def salva_stato(stato):
    with open(FILE_STATO, "w", encoding="utf-8") as file:
        json.dump(
            stato,
            file,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# VALIDAZIONE PRODOTTI
# ============================================================

def valida_prodotti(prodotti):

    if not isinstance(prodotti, list) or not prodotti:
        print("ERRORE: prodotti.json non contiene prodotti validi.")
        return False

    campi_obbligatori = {
        "id",
        "nome",
        "url",
        "soglia",
        "destinatari"
    }

    ids = set()
    valido = True

    for indice, prodotto in enumerate(prodotti, start=1):

        if not isinstance(prodotto, dict):
            print(
                f"ERRORE: prodotto numero {indice} "
                "non è un oggetto JSON valido."
            )
            valido = False
            continue

        mancanti = campi_obbligatori - set(prodotto.keys())

        if mancanti:
            print(
                f"ERRORE: prodotto numero {indice}: "
                "campi mancanti: "
                + ", ".join(sorted(mancanti))
            )
            valido = False
            continue

        prodotto_id = prodotto["id"]

        if not isinstance(prodotto_id, str) or not prodotto_id.strip():
            print(
                f"ERRORE: prodotto numero {indice}: "
                "ID non valido."
            )
            valido = False

        elif prodotto_id in ids:
            print(
                f"ERRORE: ID duplicato: {prodotto_id}"
            )
            valido = False

        else:
            ids.add(prodotto_id)

        if (
            not isinstance(prodotto["nome"], str)
            or not prodotto["nome"].strip()
        ):
            print(
                f"ERRORE: prodotto {prodotto_id}: "
                "nome non valido."
            )
            valido = False

        if (
            not isinstance(prodotto["url"], str)
            or not prodotto["url"].startswith(
                ("http://", "https://")
            )
