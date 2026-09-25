"""Fehler, die die API-Schicht in HTTP-Antworten übersetzt."""


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    """Die Aktion passt nicht zum aktuellen Zustand, z.B. Analyse eines Logs ohne Zuordnung."""


class BadInputError(Exception):
    pass


class TooLargeError(Exception):
    pass
