from __future__ import annotations

import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import requests

from bgrules.config import BGG_API_TOKEN
from bgrules.db import GameInfo, Session

BGG_SEARCH_URL = "https://boardgamegeek.com/xmlapi2/search"
BGG_THING_URL = "https://boardgamegeek.com/xmlapi2/thing"
REQUEST_HEADERS = {
    "User-Agent": "bgrules/0.1.0",
    "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
}


class BoardGameGeekError(RuntimeError):
    """Raised when BoardGameGeek data cannot be fetched or parsed."""


@dataclass
class BoardGameGeekInfo:
    game_name: str
    bgg_id: int
    bgg_name: str
    year_published: Optional[int]
    average_rating: Optional[float]
    min_players: Optional[int]
    max_players: Optional[int]
    playing_time_minutes: Optional[int]
    average_weight: Optional[float]
    fetched_at: str


def _normalize_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_name.lower()).strip()


def _request_xml(url: str, params: dict[str, object], retries: int = 4) -> ET.Element:
    if not BGG_API_TOKEN:
        raise BoardGameGeekError(
            "BoardGameGeek now requires an API token. "
            "Set BGG_API_TOKEN in your environment before running `bgrules info`."
        )

    headers = dict(REQUEST_HEADERS)
    headers["Authorization"] = f"Bearer {BGG_API_TOKEN}"

    last_response = None
    for attempt in range(retries):
        response = requests.get(url, params=params, timeout=20, headers=headers)
        last_response = response
        if response.status_code == 202 and attempt < retries - 1:
            time.sleep(1 + attempt)
            continue

        if response.status_code == 401:
            raise BoardGameGeekError(
                "BoardGameGeek rejected the API token (401 Unauthorized). "
                "Check that BGG_API_TOKEN is valid and tied to an approved BGG application."
            )

        response.raise_for_status()
        try:
            return ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise BoardGameGeekError(f"Invalid XML response from BoardGameGeek: {exc}") from exc

    status_code = getattr(last_response, "status_code", "unknown")
    raise BoardGameGeekError(f"BoardGameGeek did not return ready data (status {status_code}).")


def _score_search_match(query: str, candidate_name: str, year_published: Optional[int]) -> tuple[int, int, str]:
    normalized_query = _normalize_name(query)
    normalized_candidate = _normalize_name(candidate_name)

    exact = int(normalized_query == normalized_candidate)
    prefix = int(normalized_candidate.startswith(normalized_query) or normalized_query.startswith(normalized_candidate))
    has_year = int(year_published is not None)
    return (exact, prefix, has_year, normalized_candidate)


def _parse_int(value: Optional[str]) -> Optional[int]:
    if value in (None, "", "N/A"):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _parse_float(value: Optional[str]) -> Optional[float]:
    if value in (None, "", "N/A"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _search_best_match(game: str) -> tuple[int, str, Optional[int]]:
    root = _request_xml(BGG_SEARCH_URL, {"query": game, "type": "boardgame", "exact": 1})
    items = root.findall("item")

    if not items:
        root = _request_xml(BGG_SEARCH_URL, {"query": game, "type": "boardgame"})
        items = root.findall("item")

    candidates = []
    for item in items:
        item_id = item.get("id")
        name_node = item.find("name")
        if not item_id or name_node is None:
            continue

        name = name_node.get("value")
        if not name:
            continue

        year = _parse_int(item.findtext("yearpublished"))
        candidates.append((_score_search_match(game, name, year), int(item_id), name, year))

    if not candidates:
        raise BoardGameGeekError(f"No BoardGameGeek result found for '{game}'.")

    _, best_id, best_name, best_year = max(candidates, key=lambda entry: entry[0])
    return best_id, best_name, best_year


def fetch_game_info_from_bgg(game: str) -> BoardGameGeekInfo:
    bgg_id, fallback_name, fallback_year = _search_best_match(game)
    root = _request_xml(BGG_THING_URL, {"id": bgg_id, "stats": 1})

    item = root.find("item")
    if item is None:
        raise BoardGameGeekError(f"BoardGameGeek details not found for '{game}'.")

    primary_name = item.find("./name[@type='primary']")
    ratings = item.find("./statistics/ratings")

    average_rating = None
    average_weight = None
    if ratings is not None:
        average_rating = _parse_float(ratings.find("./average").get("value") if ratings.find("./average") is not None else None)
        average_weight = _parse_float(
            ratings.find("./averageweight").get("value") if ratings.find("./averageweight") is not None else None
        )

    return BoardGameGeekInfo(
        game_name=game,
        bgg_id=bgg_id,
        bgg_name=primary_name.get("value") if primary_name is not None and primary_name.get("value") else fallback_name,
        year_published=_parse_int(item.find("./yearpublished").get("value") if item.find("./yearpublished") is not None else None)
        or fallback_year,
        average_rating=average_rating,
        min_players=_parse_int(item.find("./minplayers").get("value") if item.find("./minplayers") is not None else None),
        max_players=_parse_int(item.find("./maxplayers").get("value") if item.find("./maxplayers") is not None else None),
        playing_time_minutes=_parse_int(item.find("./playingtime").get("value") if item.find("./playingtime") is not None else None),
        average_weight=average_weight,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


def save_game_info(info: BoardGameGeekInfo, session_factory=Session) -> GameInfo:
    session = session_factory()
    try:
        record = session.query(GameInfo).filter_by(game_name=info.game_name).one_or_none()
        if record is None:
            record = GameInfo(game_name=info.game_name)
            session.add(record)

        record.bgg_id = info.bgg_id
        record.bgg_name = info.bgg_name
        record.year_published = info.year_published
        record.average_rating = info.average_rating
        record.min_players = info.min_players
        record.max_players = info.max_players
        record.playing_time_minutes = info.playing_time_minutes
        record.average_weight = info.average_weight
        record.fetched_at = info.fetched_at

        session.commit()
        session.refresh(record)
        return record
    finally:
        session.close()


def get_saved_game_info(game: str, session_factory=Session) -> Optional[GameInfo]:
    session = session_factory()
    try:
        return session.query(GameInfo).filter_by(game_name=game).one_or_none()
    finally:
        session.close()


def fetch_and_store_game_info(game: str, session_factory=Session) -> GameInfo:
    info = fetch_game_info_from_bgg(game)
    return save_game_info(info, session_factory=session_factory)
