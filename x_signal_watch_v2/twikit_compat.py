"""Compatibilite de Twikit 2.3.3 avec les pages et scripts X de 2026.

Correctif limite a cette version, en attendant une publication amont :
https://github.com/d60/twikit/pull/410
https://github.com/iSarabjitDhiman/XClientTransaction/blob/master/x_client_transaction/utils.py
"""

import re
from importlib.metadata import version


_LEGACY_SCRIPT = re.compile(r"""["']ondemand\.s["']\s*:\s*["']([0-9a-fA-F]+)["']""")
_CHUNK_ID = re.compile(r"""(?:^|[,{])\s*["']?(\d+)["']?\s*:\s*["']ondemand\.s["']""")
_KEY_INDICES = re.compile(r"\[\s*(\d+)\s*\]\s*,\s*16\b")


def ondemand_script_url(homepage):
    """Retrouve le script dans les anciens et nouveaux manifestes webpack."""
    source = str(homepage)
    legacy = _LEGACY_SCRIPT.search(source)
    script_hash = legacy.group(1) if legacy else None
    if script_hash is None:
        chunk = _CHUNK_ID.search(source)
        if chunk:
            hash_entry = re.search(
                r"""(?:^|[,{])\s*["']?""" + re.escape(chunk.group(1))
                + r"""["']?\s*:\s*["']([0-9a-fA-F]+)["']""",
                source,
            )
            if hash_entry:
                script_hash = hash_entry.group(1)
    if script_hash is None:
        raise RuntimeError("Twikit : script ondemand.s introuvable dans la page X.")
    return f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{script_hash}a.js"


async def _get_indices(self, home_page_response, session, headers):
    response = self.validate_response(home_page_response)
    script = await session.request(
        method="GET", url=ondemand_script_url(response), headers=headers,
    )
    # Conserver les erreurs HTTP (403, 429...) sans retenter ni masquer le blocage.
    script.raise_for_status()
    indices = [int(match.group(1)) for match in _KEY_INDICES.finditer(script.text)]
    if len(indices) < 2:
        raise RuntimeError("Twikit : indices KEY_BYTE absents ou incomplets dans le script X.")
    return indices[0], indices[1:]


async def _load_homepage(session, headers):
    """Charge /home ; la nouvelle page d'accueil publique n'a plus le manifeste."""
    from bs4 import BeautifulSoup

    response = await session.request(
        method="GET", url="https://x.com/home", headers=headers, follow_redirects=True,
    )
    response.raise_for_status()
    page = BeautifulSoup(response.content, "lxml")
    if page.select_one('script[src*="entry-client-logged-out-"]'):
        raise RuntimeError(
            "X renvoie sa page de connexion : ajoute X_AUTH_TOKEN et X_CT0 dans .env "
            "depuis une session X ouverte dans ton navigateur."
        )
    return page


def apply_twikit_compat():
    """Installe le correctif idempotent uniquement pour Twikit 2.3.3."""
    if version("twikit") != "2.3.3":
        return False
    from twikit.x_client_transaction import transaction

    transaction.ClientTransaction.get_indices = _get_indices
    transaction.handle_x_migration = _load_homepage
    return True
