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
# PREZZI
# ============================================================

def euro(valore):
    return (
        f"{Decimal(str(valore)):.2f}"
        .replace(".", ",")
        + " €"
    )


def estrai_prezzo_farmasave(testo):
    pattern = (
        r"Prezzo\s+Farmasave"
        r"[\s*:#\-]*"
        r"(\d{1,4}[.,]\d{2})\s*€"
    )

    match = re.search(
        pattern,
        testo,
        flags=re.IGNORECASE
    )

    if not match:
        return None

    valore = match.group(1).replace(",", ".")

    try:
        prezzo = Decimal(valore)

        if prezzo <= 0:
            return None

        return prezzo

    except InvalidOperation:
        return None


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
        "format": "markdown"
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

def recupera_destinatari(prodotto, nomi_destinatari=None):
    """
    Converte i nomi simbolici presenti in prodotti.json
    (es. EMAIL_MANDARINO) nei relativi indirizzi email
    disponibili come variabili d'ambiente.
    """

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
                f"ATTENZIONE: variabile destinatario "
                f"{nome_secret} non disponibile "
                f"nell'ambiente."
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
            f"ERRORE: nessun destinatario disponibile "
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
                else prodotto.get("destinatari", [])
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
            f"📉 Nuovo ribasso: "
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
            f"🔔 Prezzo sotto soglia: "
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

Prezzo Farmasave:
{euro(prezzo)}

Soglia:
{euro(soglia)}

Pagina Farmasave:
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
        f"↗️ Prezzo tornato sopra soglia: "
        f"{prodotto['nome']}"
    )

    messaggio = f"""PRICE MONITOR

Il prezzo del prodotto non è più sotto
la soglia impostata.

Prodotto:
{prodotto['nome']}

Prezzo Farmasave:
{euro(prezzo)}

Soglia:
{euro(soglia)}

Non riceverai altre notifiche di questo tipo
finché il prodotto non scenderà nuovamente
sotto soglia.

Pagina Farmasave:
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
        f"⚠️ Price Monitor: problema con "
        f"{prodotto['nome']}"
    )

    messaggio = f"""PRICE MONITOR

Non è stato possibile controllare correttamente
questo prodotto per {MAX_ERRORI_CONSECUTIVI}
esecuzioni consecutive.

Prodotto:
{prodotto['nome']}

Pagina Farmasave:
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
    Migra automaticamente gli stati creati
    dalle versioni precedenti del monitor.
    """

    if "destinatari_notificati" not in stato_prodotto:

        if (
            stato_prodotto.get("stato") == "sotto"
            and stato_prodotto.get(
                "minimo_notificato"
            ) is not None
        ):
            # Nella vecchia versione uno stato "sotto"
            # con minimo_notificato significava che
            # l'alert era già stato inviato.
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

    prezzo = estrai_prezzo_farmasave(
        testo
    )

    if prezzo is None:
        print(
            "ERRORE: Prezzo Farmasave "
            "non individuato."
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
        f"Prezzo Farmasave: {euro(prezzo)}"
    )

    print(
        f"Soglia: {euro(soglia)}"
    )

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

            # La modifica manuale della soglia non genera
            # una notifica artificiale.
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

            # Troviamo eventuali nuovi destinatari.
            nuovi_destinatari = [
                destinatario
                for destinatario
                in destinatari_configurati
                if destinatario
                not in destinatari_notificati
            ]

            # ------------------------------------------------
            # NUOVI DESTINATARI
            # ------------------------------------------------

            if nuovi_destinatari:

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

            elif prezzo < Decimal(
                str(minimo)
            ):

                print(
                    "Nuovo minimo rilevato "
                    "sotto soglia."
                )

                if email_sotto_soglia(
                    prodotto,
                    prezzo,
                    ulteriore=True,
                    nomi_destinatari=destinatari_configurati
                ):
                    stato_prodotto[
                        "minimo_notificato"
                    ] = float(prezzo)

                    # Tutti i destinatari attuali hanno
                    # ricevuto il nuovo minimo.
                    stato_prodotto[
                        "destinatari_notificati"
                    ] = list(
                        destinatari_configurati
                    )

            else:

                if not nuovi_destinatari:
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

                # Il ciclo sotto soglia è terminato.
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
    print("PRICE MONITOR FARMASAVE")
    print("=" * 70)

    prodotti = carica_json(
        FILE_PRODOTTI
    )

    if not prodotti:
        print(
            "ERRORE: nessun prodotto configurato."
        )
        sys.exit(1)

    ids = [
        prodotto.get("id")
        for prodotto in prodotti
    ]

    if (
        None in ids
        or len(ids) != len(set(ids))
    ):
        print(
            "ERRORE: ogni prodotto deve avere "
            "un ID univoco."
        )
        sys.exit(1)

    stato = carica_json(
        FILE_STATO,
        default={}
    )

    # --------------------------------------------------------
    # ELIMINA PRODOTTI RIMOSSI
    # --------------------------------------------------------

    ids_attivi = set(ids)

    for id_vecchio in list(
        stato.keys()
    ):
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

            # Migrazione automatica dello stato precedente.
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
            f"Controllo: "
            f"{prodotto['nome']}"
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
