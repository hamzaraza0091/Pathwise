import logging
import threading

logger = logging.getLogger("pathwise.nlp")
_lock = threading.Lock()
_state = {"loaded": False, "nlp": None}


def get_nlp():
    if _state["loaded"]:
        return _state["nlp"]
    with _lock:
        if not _state["loaded"]:
            try:
                import spacy

                _state["nlp"] = spacy.load("en_core_web_sm", disable=["lemmatizer"])
            except Exception as exc:
                logger.info("spaCy model unavailable, using heuristics only: %s", exc)
            _state["loaded"] = True
    return _state["nlp"]


def is_person(text: str) -> bool:
    nlp = get_nlp()
    if nlp is None:
        return False
    return any(e.label_ == "PERSON" for e in nlp(text).ents)


def header_entities(lines: list[str]) -> dict:
    nlp = get_nlp()
    if nlp is None or not lines:
        return {"person": None, "place": None}
    person = None
    for doc in nlp.pipe(lines[:6]):
        person = person or next((e.text.strip() for e in doc.ents if e.label_ == "PERSON" and 2 <= len(e.text.split()) <= 4), None)
    place = None
    fragments = [f.strip() for line in lines[:8] for f in line.replace("•", "|").replace("·", "|").split("|") if f.strip() and "@" not in f and len(f) < 60]
    for doc in nlp.pipe(fragments):
        place = place or next((e.text.strip() for e in doc.ents if e.label_ in ("GPE", "LOC") and len(e.text) < 50), None)
    return {"person": person, "place": place}
