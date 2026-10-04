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
        ):
            print(
                f"ERRORE: prodotto {prodotto_id}: "
                "URL non valido."
            )
            valido = False

        try:
            soglia = Decimal(str(prodotto["soglia"]))

            if soglia <= 0:
                raise InvalidOperation

        except (InvalidOperation, ValueError, TypeError):
            print(
                f"ERRORE: prodotto {prodotto_id}: "
                "soglia non valida."
            )
            valido = False

        destinatari = prodotto["destinatari"]

        if (
            not isinstance(destinatari, list)
            or not destinatari
        ):
            print(
                f"ERRORE: prodotto {prodotto_id}: "
                "deve essere configurato almeno "
                "un destinatario."
            )
            valido = False

        elif (
            len(destinatari)
            != len(set(destinatari))
        ):
            print(
                f"ERRORE: prodotto {prodotto_id}: "
                "sono presenti destinatari duplicati."
            )
            valido = False

        else:
            for destinatario in destinatari:
                if (
                    not isinstance(destinatario, str)
                    or not destinatario.strip()
                ):
                    print(
                        f"ERRORE: prodotto {prodotto_id}: "
                        "destinatario non valido."
                    )
                    valido = False

    return valido


# ============================================================
# PREZZI
# ============================================================

def euro(valore):
    return (
        f"{Decimal(str(valore)):.2f}"
        .replace(".", ",")
        + " €"
    )


def normalizza_prezzo(valore):
    """Converte i principali formati di prezzo europei/internazionali in Decimal."""
    if valore is None:
        return None

    testo = str(valore).strip()
    testo = re.sub(r"[^0-9,.' ]", "", testo).replace(" ", "").replace("'", "")

    if not testo:
        return None

    # 1.234,56 -> 1234.56
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+,\d{2}", testo):
        testo = testo.replace(".", "").replace(",", ".")
    # 1,234.56 -> 1234.56
    elif re.fullmatch(r"\d{1,3}(?:,\d{3})+\.\d{2}", testo):
        testo = testo.replace(",", "")
    # 12,34 -> 12.34
    elif re.fullmatch(r"\d+,\d{2}", testo):
        testo = testo.replace(",", ".")
    # 12.34 oppure 1234.56
    elif re.fullmatch(r"\d+\.\d{2}", testo):
        pass
    # Prezzo intero: accettato solo se esplicitamente associato a una valuta/etichetta.
    elif re.fullmatch(r"\d+", testo):
        pass
    else:
        return None

    try:
        prezzo = Decimal(testo)
        if prezzo <= 0:
            return None
        return prezzo
    except InvalidOperation:
        return None


def estrai_prezzo_farmasave(testo):
    """Estrattore specifico mantenuto per piena compatibilità con Farmasave."""
    pattern = (
        r"Prezzo\s+Farmasave"
        r"[\s*:#\-]*"
        r"(\d{1,4}[.,]\d{2})\s*€"
    )

    match = re.search(pattern, testo, flags=re.IGNORECASE)
    if not match:
        return None

    return normalizza_prezzo(match.group(1))


def estrai_prezzo_json_ld(testo):
    """Cerca price nei blocchi JSON-LD Product/Offer, quando TinyFish li conserva."""
    blocchi = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        testo,
        flags=re.IGNORECASE | re.DOTALL,
    )

    def visita(oggetto):
        if isinstance(oggetto, dict):
            tipo = oggetto.get("@type")
            tipi = tipo if isinstance(tipo, list) else [tipo]

            if "Offer" in tipi or "AggregateOffer" in tipi:
                for chiave in ("price", "lowPrice"):
                    if chiave in oggetto:
                        prezzo = normalizza_prezzo(oggetto.get(chiave))
                        valuta = str(oggetto.get("priceCurrency", "EUR")).upper()
                        if prezzo is not None and valuta in ("EUR", "€", ""):
                            return prezzo

            # Alcuni siti mettono offers dentro Product.
            for valore in oggetto.values():
                trovato = visita(valore)
                if trovato is not None:
                    return trovato

        elif isinstance(oggetto, list):
            for elemento in oggetto:
                trovato = visita(elemento)
                if trovato is not None:
                    return trovato

        return None

    for blocco in blocchi:
        try:
            dati = json.loads(html.unescape(blocco).strip())
        except (json.JSONDecodeError, TypeError):
            continue

        prezzo = visita(dati)
        if prezzo is not None:
            return prezzo

    return None


def estrai_prezzo_metadata(testo):
    """Cerca metadati HTML comunemente usati dagli e-commerce."""
    patterns = [
        r'<meta[^>]+(?:property|name|itemprop)=["\'](?:product:price:amount|og:price:amount|price)["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name|itemprop)=["\'](?:product:price:amount|og:price:amount|price)["\']',
    ]

    for pattern in patterns:
        for valore in re.findall(pattern, testo, flags=re.IGNORECASE):
            prezzo = normalizza_prezzo(valore)
            if prezzo is not None:
                return prezzo

    return None


def testo_visibile_da_html(testo):
    pulito = re.sub(r"<script\b[^>]*>.*?</script>", " ", testo, flags=re.IGNORECASE | re.DOTALL)
    pulito = re.sub(r"<style\b[^>]*>.*?</style>", " ", pulito, flags=re.IGNORECASE | re.DOTALL)
    pulito = re.sub(r"<[^>]+>", " ", pulito)
    pulito = html.unescape(pulito)
    # Una sola sequenza di spazi: le etichette e il prezzo possono essere
    # separati da tag HTML o ritorni a capo.
    return re.sub(r"\s+", " ", pulito).strip()


def estrai_prezzo_testo_contestuale(testo):
    """
    Cerca il prezzo corrente in blocchi semanticamente forti della pagina.

    Non prende il prezzo minimo dell'intera pagina: considera soltanto
    importi molto vicini a etichette tipiche dell'area prezzo del prodotto.
    Se sono presenti prezzo corrente e prezzo di listino, restituisce il
    primo importo mostrato dopo l'etichetta.
    """
    visibile = testo_visibile_da_html(testo)

    numero = (
        r"(\d{1,3}(?:[. ]\d{3})*,\d{2}"
        r"|\d{1,3}(?:[, ]\d{3})*\.\d{2}"
        r"|\d+[.,]\d{2})"
    )
    valuta = r"(?:€|EUR)"

    # Etichette molto forti: indicano normalmente l'inizio del blocco
    # che contiene il prezzo principale del prodotto.
    etichette_forti = [
        r"info\s+prezzi?",
        r"prezzo\s+(?:online|web|speciale|scontato|attuale|finale|di\s+vendita)",
        r"nostro\s+prezzo",
        r"our\s+price",
        r"sale\s+price",
        r"current\s+price",
        r"special\s+price",
    ]

    for etichetta in etichette_forti:
        patterns = [
            rf"{etichetta}.{{0,160}}?{numero}\s*{valuta}",
            rf"{etichetta}.{{0,160}}?{valuta}\s*{numero}",
        ]
        for pattern in patterns:
            match = re.search(pattern, visibile, flags=re.IGNORECASE)
            if match:
                prezzo = normalizza_prezzo(match.group(1))
                if prezzo is not None:
                    return prezzo

    # Fallback più prudente per la semplice parola Prezzo: finestra corta
    # per evitare importi di spedizione, prodotti correlati o footer.
    patterns = [
        rf"(?:prezzo|price).{{0,50}}?{numero}\s*{valuta}",
        rf"(?:prezzo|price).{{0,50}}?{valuta}\s*{numero}",
    ]
    for pattern in patterns:
        match = re.search(pattern, visibile, flags=re.IGNORECASE)
        if match:
            prezzo = normalizza_prezzo(match.group(1))
            if prezzo is not None:
                return prezzo

    return None


def estrai_prezzo_testo(testo):
    # Alias mantenuto per compatibilità con la versione precedente.
    return estrai_prezzo_testo_contestuale(testo)


def estrai_prezzo(prodotto, testo):
    """
    Estrazione multilivello. Restituisce (prezzo, metodo).
    In caso di ambiguità restituisce (None, None) invece di inventare un prezzo.
    """
    dominio = prodotto.get("url", "").lower()

    # Farmasave resta prioritario: è il comportamento già collaudato.
    if "farmasave.it" in dominio:
        prezzo = estrai_prezzo_farmasave(testo)
        if prezzo is not None:
            return prezzo, "farmasave"

    strategie = [
        ("json_ld", estrai_prezzo_json_ld),
        ("metadata", estrai_prezzo_metadata),
        ("testo_contestuale", estrai_prezzo_testo_contestuale),
    ]

    for nome_metodo, funzione in strategie:
        prezzo = funzione(testo)
        if prezzo is not None:
            return prezzo, nome_metodo

    # Ultimo tentativo Farmasave, utile se il dominio cambia/redirecta.
    prezzo = estrai_prezzo_farmasave(testo)
    if prezzo is not None:
        return prezzo, "farmasave"

    return None, None


# ============================================================
# TINYFISH
# ============================================================

def recupera_pagine_tinyfish(prodotti):
    api_key = os.environ.get("TINYFISH_API_KEY")

    if not api_key:
        raise RuntimeError(
            "TINYFISH_API_KEY non configurata."
        )

    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }

    payload = {
        "urls": [
            prodotto["url"]
            for prodotto in prodotti
        ],
        "format": "html"
    }

    risposta = requests.post(
        TINYFISH_URL,
        headers=headers,
        json=payload,
        timeout=120
    )

    risposta.raise_for_status()

    dati = risposta.json()

    pagine = {}

    for pagina in dati.get("results", []):
        url = pagina.get("url")

        if url:
            pagine[url] = pagina

    errori = {}

    for errore in dati.get("errors", []):
        url = errore.get("url")

        if url:
            errori[url] = errore

    return pagine, errori


# ============================================================
# DESTINATARI
# ============================================================

def recupera_destinatari(
    prodotto,
    nomi_destinatari=None
):
    if nomi_destinatari is None:
        nomi_destinatari = prodotto.get(
            "destinatari",
            []
        )

    destinatari = []

    for nome_secret in nomi_destinatari:
        email = os.environ.get(nome_secret)

        if email:
            destinatari.append({
                "email": email
            })

        else:
            print(
                "ATTENZIONE: variabile destinatario "
                f"{nome_secret} non disponibile "
                "nell'ambiente."
            )

    return destinatari


# ============================================================
# INVIO EMAIL
# ============================================================

def invia_email(
    prodotto,
    oggetto,
    messaggio,
    nomi_destinatari=None
):
    api_key = os.environ.get("BREVO_API_KEY")
    mittente = os.environ.get("BREVO_SENDER")

    if not api_key or not mittente:
        print(
            "ERRORE: configurazione Brevo incompleta."
        )
        return False

    destinatari = recupera_destinatari(
        prodotto,
        nomi_destinatari
    )

    if not destinatari:
        print(
            "ERRORE: nessun destinatario disponibile "
            f"per {prodotto['nome']}."
        )
        return False

    payload = {
        "sender": {
            "name": "Price Monitor",
            "email": mittente
        },
        "to": destinatari,
        "subject": oggetto,
        "textContent": messaggio
    }

    try:
        risposta = requests.post(
            BREVO_URL,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )

        risposta.raise_for_status()

        print(
            "Email inviata correttamente a: "
            + ", ".join(
                nomi_destinatari
                if nomi_destinatari is not None
                else prodotto.get(
                    "destinatari",
                    []
                )
            )
        )

        return True

    except requests.RequestException as errore:
        print(
            f"ERRORE invio email: {errore}"
        )
        return False


# ============================================================
# EMAIL SOTTO SOGLIA
# ============================================================

def email_sotto_soglia(
    prodotto,
    prezzo,
    ulteriore=False,
    nomi_destinatari=None
):
    soglia = Decimal(
        str(prodotto["soglia"])
    )

    if ulteriore:
        oggetto = (
            "📉 Nuovo ribasso: "
            f"{prodotto['nome']} "
            f"a {euro(prezzo)}"
        )

        apertura = (
            "Il prodotto è sceso ulteriormente "
            "di prezzo mentre si trova sotto "
            "la soglia impostata."
        )

    else:
        oggetto = (
            "🔔 Prezzo sotto soglia: "
            f"{prodotto['nome']} "
            f"a {euro(prezzo)}"
        )

        apertura = (
            "Il prezzo del prodotto è sceso "
            "sotto la soglia impostata."
        )

    messaggio = f"""PRICE MONITOR

{apertura}

Prodotto:
{prodotto['nome']}

Prezzo rilevato:
{euro(prezzo)}

Soglia:
{euro(soglia)}

Pagina prodotto:
{prodotto['url']}
"""

    return invia_email(
        prodotto,
        oggetto,
        messaggio,
        nomi_destinatari
    )


# ============================================================
# EMAIL RITORNO SOPRA SOGLIA
# ============================================================

def email_ritorno_sopra_soglia(
    prodotto,
    prezzo
):
    soglia = Decimal(
        str(prodotto["soglia"])
    )

    oggetto = (
        "↗️ Prezzo tornato sopra soglia: "
        f"{prodotto['nome']}"
    )

    messaggio = f"""PRICE MONITOR

Il prezzo del prodotto non è più sotto
la soglia impostata.

Prodotto:
{prodotto['nome']}

Prezzo rilevato:
{euro(prezzo)}

Soglia:
{euro(soglia)}

Non riceverai altre notifiche di questo tipo
finché il prodotto non scenderà nuovamente
sotto soglia.

Pagina prodotto:
{prodotto['url']}
"""

    return invia_email(
        prodotto,
        oggetto,
        messaggio
    )


# ============================================================
# EMAIL ERRORE
# ============================================================

def email_errore(prodotto):
    oggetto = (
        "⚠️ Price Monitor: problema con "
        f"{prodotto['nome']}"
    )

    messaggio = f"""PRICE MONITOR

Non è stato possibile controllare correttamente
questo prodotto per {MAX_ERRORI_CONSECUTIVI}
esecuzioni consecutive.

Prodotto:
{prodotto['nome']}

Pagina prodotto:
{prodotto['url']}

Il monitor continuerà automaticamente a tentare
i controlli successivi.

Non verranno inviati altri avvisi di errore
finché il controllo non tornerà a funzionare.
"""

    return invia_email(
        prodotto,
        oggetto,
        messaggio
    )


# ============================================================
# STATO
# ============================================================

def nuovo_stato(soglia):
    return {
        "stato": None,
        "ultimo_prezzo": None,
        "minimo_notificato": None,
        "soglia": float(soglia),
        "destinatari_notificati": [],
        "errori_consecutivi": 0,
        "errore_notificato": False
    }


def aggiorna_struttura_stato(
    prodotto,
    stato_prodotto
):
    """
    Migra automaticamente eventuali stati creati
    dalle versioni precedenti del monitor.
    """

    if "destinatari_notificati" not in stato_prodotto:

        if (
            stato_prodotto.get("stato") == "sotto"
            and stato_prodotto.get(
                "minimo_notificato"
            ) is not None
        ):
            stato_prodotto[
                "destinatari_notificati"
            ] = list(
                prodotto.get(
                    "destinatari",
                    []
                )
            )

        else:
            stato_prodotto[
                "destinatari_notificati"
            ] = []

    stato_prodotto.setdefault(
        "errori_consecutivi",
        0
    )

    stato_prodotto.setdefault(
        "errore_notificato",
        False
    )


# ============================================================
# ERRORI
# ============================================================

def registra_errore(
    prodotto,
    stato_prodotto
):
    stato_prodotto[
        "errori_consecutivi"
    ] += 1

    print(
        "Errori consecutivi:",
        stato_prodotto[
            "errori_consecutivi"
        ]
    )

    if (
        stato_prodotto[
            "errori_consecutivi"
        ] >= MAX_ERRORI_CONSECUTIVI
        and not stato_prodotto[
            "errore_notificato"
        ]
    ):
        if email_errore(prodotto):
            stato_prodotto[
                "errore_notificato"
            ] = True


# ============================================================
# ELABORAZIONE PRODOTTO
# ============================================================

def processa_prodotto(
    prodotto,
    pagina,
    stato_prodotto
):
    soglia = Decimal(
        str(prodotto["soglia"])
    )

    destinatari_configurati = prodotto.get(
        "destinatari",
        []
    )

    testo = pagina.get(
        "text",
        ""
    )

    prezzo, metodo_prezzo = estrai_prezzo(
        prodotto,
        testo
    )

    if prezzo is None:
        print(
            "ERRORE: prezzo del prodotto non individuato "
            "con sufficiente affidabilità."
        )

        registra_errore(
            prodotto,
            stato_prodotto
        )

        return

    titolo = pagina.get(
        "title",
        ""
    )

    print(
        f"Titolo pagina: {titolo}"
    )

    print(
        f"Prezzo rilevato: {euro(prezzo)}"
    )

    print(
        f"Metodo estrazione: {metodo_prezzo}"
    )

    print(
        f"Soglia: {euro(soglia)}"
    )

    # Il controllo è tornato a funzionare.
    stato_prodotto[
        "errori_consecutivi"
    ] = 0

    stato_prodotto[
        "errore_notificato"
    ] = False

    soglia_precedente = Decimal(
        str(
            stato_prodotto.get(
                "soglia",
                soglia
            )
        )
    )

    # ========================================================
    # SOGLIA MODIFICATA
    # ========================================================

    if soglia != soglia_precedente:

        print(
            "Soglia modificata: "
            f"{euro(soglia_precedente)} "
            f"-> {euro(soglia)}"
        )

        stato_prodotto[
            "soglia"
        ] = float(soglia)

        stato_prodotto[
            "ultimo_prezzo"
        ] = float(prezzo)

        if prezzo < soglia:

            stato_prodotto[
                "stato"
            ] = "sotto"

            stato_prodotto[
                "minimo_notificato"
            ] = float(prezzo)

            # Una modifica manuale della soglia
            # non genera un alert artificiale.
            stato_prodotto[
                "destinatari_notificati"
            ] = list(
                destinatari_configurati
            )

        else:

            stato_prodotto[
                "stato"
            ] = "sopra"

            stato_prodotto[
                "minimo_notificato"
            ] = None

            stato_prodotto[
                "destinatari_notificati"
            ] = []

        print(
            "Stato riallineato alla nuova soglia. "
            "Nessuna email inviata."
        )

        return

    stato_precedente = stato_prodotto.get(
        "stato"
    )

    # ========================================================
    # PRIMA RILEVAZIONE
    # ========================================================

    if stato_precedente is None:

        stato_prodotto[
            "ultimo_prezzo"
        ] = float(prezzo)

        stato_prodotto[
            "soglia"
        ] = float(soglia)

        if prezzo < soglia:

            print(
                "Nuovo prodotto già sotto soglia: "
                "invio alert iniziale."
            )

            if email_sotto_soglia(
                prodotto,
                prezzo,
                ulteriore=False,
                nomi_destinatari=destinatari_configurati
            ):
                stato_prodotto[
                    "stato"
                ] = "sotto"

                stato_prodotto[
                    "minimo_notificato"
                ] = float(prezzo)

                stato_prodotto[
                    "destinatari_notificati"
                ] = list(
                    destinatari_configurati
                )

            else:
                # Lasciamo lo stato non inizializzato,
                # così il monitor ritenterà al prossimo giro.
                stato_prodotto[
                    "stato"
                ] = None

                stato_prodotto[
                    "minimo_notificato"
                ] = None

                stato_prodotto[
                    "destinatari_notificati"
                ] = []

        else:

            stato_prodotto[
                "stato"
            ] = "sopra"

            stato_prodotto[
                "minimo_notificato"
            ] = None

            stato_prodotto[
                "destinatari_notificati"
            ] = []

            print(
                "Prima rilevazione: "
                "prodotto sopra soglia. "
                "Nessuna email necessaria."
            )

        return

    # ========================================================
    # PREZZO SOTTO SOGLIA
    # ========================================================

    if prezzo < soglia:

        # ----------------------------------------------------
        # DISCESA DA SOPRA A SOTTO SOGLIA
        # ----------------------------------------------------

        if stato_precedente == "sopra":

            print(
                "Il prezzo è sceso sotto soglia."
            )

            if email_sotto_soglia(
                prodotto,
                prezzo,
                ulteriore=False,
                nomi_destinatari=destinatari_configurati
            ):
                stato_prodotto[
                    "stato"
                ] = "sotto"

                stato_prodotto[
                    "minimo_notificato"
                ] = float(prezzo)

                stato_prodotto[
                    "destinatari_notificati"
                ] = list(
                    destinatari_configurati
                )

        # ----------------------------------------------------
        # ERA GIÀ SOTTO SOGLIA
        # ----------------------------------------------------

        else:

            minimo = stato_prodotto.get(
                "minimo_notificato"
            )

            destinatari_notificati = (
                stato_prodotto.get(
                    "destinatari_notificati",
                    []
                )
            )

            nuovi_destinatari = [
                destinatario
                for destinatario
                in destinatari_configurati
                if destinatario
                not in destinatari_notificati
            ]

            # ------------------------------------------------
            # NESSUN PREZZO PRECEDENTEMENTE NOTIFICATO
            # ------------------------------------------------

            if minimo is None:

                print(
                    "Prodotto sotto soglia ma "
                    "senza precedente prezzo notificato."
                )

                if email_sotto_soglia(
                    prodotto,
                    prezzo,
                    ulteriore=False,
                    nomi_destinatari=destinatari_configurati
                ):
                    stato_prodotto[
                        "minimo_notificato"
                    ] = float(prezzo)

                    stato_prodotto[
                        "destinatari_notificati"
                    ] = list(
                        destinatari_configurati
                    )

            # ------------------------------------------------
            # NUOVO RIBASSO
            # ------------------------------------------------

            elif prezzo < Decimal(str(minimo)):

                print(
                    "Nuovo minimo rilevato "
                    "sotto soglia."
                )

                # In caso di nuovo minimo la mail viene
                # inviata una sola volta a TUTTI gli attuali
                # destinatari. In questo modo un eventuale
                # nuovo destinatario non riceve due email
                # nella stessa esecuzione.
                if email_sotto_soglia(
                    prodotto,
                    prezzo,
                    ulteriore=True,
                    nomi_destinatari=destinatari_configurati
                ):
                    stato_prodotto[
                        "minimo_notificato"
                    ] = float(prezzo)

                    stato_prodotto[
                        "destinatari_notificati"
                    ] = list(
                        destinatari_configurati
                    )

            # ------------------------------------------------
            # PREZZO NON DIMINUITO: EVENTUALI NUOVI DESTINATARI
            # ------------------------------------------------

            elif nuovi_destinatari:

                print(
                    "Nuovi destinatari rilevati: "
                    + ", ".join(
                        nuovi_destinatari
                    )
                )

                print(
                    "Invio lo stato corrente "
                    "solo ai nuovi destinatari."
                )

                if email_sotto_soglia(
                    prodotto,
                    prezzo,
                    ulteriore=False,
                    nomi_destinatari=nuovi_destinatari
                ):
                    for destinatario in nuovi_destinatari:

                        if destinatario not in (
                            stato_prodotto[
                                "destinatari_notificati"
                            ]
                        ):
                            stato_prodotto[
                                "destinatari_notificati"
                            ].append(
                                destinatario
                            )

            else:

                print(
                    "Prodotto ancora sotto soglia, "
                    "ma nessun nuovo minimo e nessun "
                    "nuovo destinatario. Nessuna email."
                )

    # ========================================================
    # PREZZO SOPRA SOGLIA
    # ========================================================

    else:

        if stato_precedente == "sotto":

            print(
                "Il prezzo è tornato sopra soglia."
            )

            if email_ritorno_sopra_soglia(
                prodotto,
                prezzo
            ):
                stato_prodotto[
                    "stato"
                ] = "sopra"

                stato_prodotto[
                    "minimo_notificato"
                ] = None

                # Termina il ciclo sotto soglia.
                stato_prodotto[
                    "destinatari_notificati"
                ] = []

        else:

            stato_prodotto[
                "stato"
            ] = "sopra"

            print(
                "Prodotto sopra soglia. "
                "Nessuna email."
            )

    stato_prodotto[
        "ultimo_prezzo"
    ] = float(prezzo)

    stato_prodotto[
        "soglia"
    ] = float(soglia)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("UNIVERSAL PRICE MONITOR")
    print("=" * 70)

    prodotti = carica_json(
        FILE_PRODOTTI
    )

    if not valida_prodotti(prodotti):
        print(
            "\nERRORE: configurazione prodotti non valida. "
            "Controllo interrotto."
        )
        sys.exit(1)

    stato = carica_json(
        FILE_STATO,
        default={}
    )

    if not isinstance(stato, dict):
        print(
            "ERRORE: stato.json non contiene "
            "una struttura valida."
        )
        sys.exit(1)

    ids = [
        prodotto["id"]
        for prodotto in prodotti
    ]

    # --------------------------------------------------------
    # ELIMINA PRODOTTI RIMOSSI
    # --------------------------------------------------------

    ids_attivi = set(ids)

    for id_vecchio in list(stato.keys()):

        if id_vecchio not in ids_attivi:

            print(
                "Rimuovo dallo stato prodotto "
                "non più configurato: "
                f"{id_vecchio}"
            )

            del stato[id_vecchio]

    # --------------------------------------------------------
    # CREA STATO NUOVI PRODOTTI
    # --------------------------------------------------------

    for prodotto in prodotti:

        prodotto_id = prodotto["id"]

        if prodotto_id not in stato:

            print(
                "Nuovo prodotto rilevato: "
                f"{prodotto['nome']}"
            )

            stato[
                prodotto_id
            ] = nuovo_stato(
                prodotto["soglia"]
            )

        else:

            aggiorna_struttura_stato(
                prodotto,
                stato[prodotto_id]
            )

    # --------------------------------------------------------
    # TINYFISH
    # --------------------------------------------------------

    try:

        pagine, errori = (
            recupera_pagine_tinyfish(
                prodotti
            )
        )

    except Exception as errore:

        print(
            "ERRORE TinyFish generale: "
            f"{errore}"
        )

        for prodotto in prodotti:

            registra_errore(
                prodotto,
                stato[
                    prodotto["id"]
                ]
            )

        salva_stato(stato)

        sys.exit(1)

    # --------------------------------------------------------
    # ELABORAZIONE
    # --------------------------------------------------------

    for prodotto in prodotti:

        print(
            "\n" + "-" * 70
        )

        print(
            f"Controllo: {prodotto['nome']}"
        )

        print(
            f"ID: {prodotto['id']}"
        )

        print(
            f"URL: {prodotto['url']}"
        )

        stato_prodotto = stato[
            prodotto["id"]
        ]

        pagina = pagine.get(
            prodotto["url"]
        )

        if pagina is None:

            print(
                "ERRORE: TinyFish non ha "
                "restituito la pagina."
            )

            if prodotto["url"] in errori:

                print(
                    "Dettaglio TinyFish:",
                    errori[
                        prodotto["url"]
                    ]
                )

            registra_errore(
                prodotto,
                stato_prodotto
            )

            continue

        processa_prodotto(
            prodotto,
            pagina,
            stato_prodotto
        )

    salva_stato(stato)

    print(
        "\n" + "=" * 70
    )

    print(
        "CONTROLLO TERMINATO"
    )

    print(
        "=" * 70
    )


if __name__ == "__main__":
    main()
