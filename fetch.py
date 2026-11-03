
import requests
import json
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

BASE_URL = "https://www.fotmob.com/api/data/matches"

OUTPUT = Path("public/api/v1")
OUTPUT.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.fotmob.com/",
    "Accept": "application/json"
}

session = requests.Session()
session.headers.update(HEADERS)


def save_json(filename, data):
    path = OUTPUT / filename
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def get_matches(date):
    date_string = date.strftime("%Y%m%d")

    params = {
        "date": date_string,
        "timezone": "UTC",
        "ccode3": "USA",
        "includeNextDayLateNight": "true"
    }

    try:
        response = session.get(
            BASE_URL,
            params=params,
            timeout=30
        )

        response.raise_for_status()
        data = response.json()

        leagues = data.get("leagues", [])

        if not isinstance(leagues, list):
            return []

        output = []

        for league in leagues:
            if not isinstance(league, dict):
                continue

            for match in league.get("matches", []):
                if not isinstance(match, dict):
                    continue

                item = {
                    **match,
                    "league": {
                        "id": league.get("id"),
                        "name": league.get("name"),
                        "ccode": league.get("ccode")
                    },
                    "fixtureDate": date_string
                }

                output.append(item)

        print(f"[OK] {date_string}: {len(output)} matches")

        return output

    except Exception as error:
        print(f"[ERROR] {date_string}: {error}")
        return None


def unique_matches(matches):
    unique = {}

    for match in matches:
        match_id = match.get("id")

        if match_id is not None:
            unique[str(match_id)] = match

    return list(unique.values())


def is_champions_league(match):
    league = match.get("league", {})

    league_id = str(league.get("id", ""))
    league_name = str(league.get("name", "")).lower()

    return (
        league_id == "42"
        or "champions league" in league_name
    )


def main():
    now = datetime.now(timezone.utc)

    today = now.date()

    all_matches = []
    successful_dates = []

    for offset in range(8):
        target_date = today + timedelta(days=offset)

        matches = get_matches(target_date)

        if matches is not None:
            all_matches.extend(matches)
            successful_dates.append(
                target_date.strftime("%Y%m%d")
            )

        time.sleep(1)

    all_matches = unique_matches(all_matches)

    today_string = today.strftime("%Y%m%d")

    today_matches = [
        match for match in all_matches
        if match.get("fixtureDate") == today_string
    ]

    upcoming_matches = [
        match for match in all_matches
        if match.get("fixtureDate", "") >= today_string
    ]

    champions_matches = [
        match for match in all_matches
        if is_champions_league(match)
        and match.get("fixtureDate", "") >= today_string
    ]

    metadata = {
        "provider": "FotMob",
        "generated_at": now.isoformat(),
        "timezone": "UTC",
        "total_matches": len(all_matches),
        "successful_dates": successful_dates
    }

    save_json("today.json", {
        **metadata,
        "date": today_string,
        "matches": today_matches
    })

    save_json("upcoming.json", {
        **metadata,
        "days": 7,
        "matches": upcoming_matches
    })

    save_json("champions-league.json", {
        **metadata,
        "league": "UEFA Champions League",
        "matches": champions_matches
    })

    save_json("fixtures.json", {
        **metadata,
        "matches": all_matches
    })

    save_json("health.json", {
        "status": (
            "ok" if len(successful_dates) == 8
            else "partial"
        ),
        **metadata
    })

    save_json("index.json", {
        "name": "FotMob Public Football API",
        "version": "1.0",
        "endpoints": {
            "today": "today.json",
            "upcoming": "upcoming.json",
            "champions_league": "champions-league.json",
            "fixtures": "fixtures.json",
            "health": "health.json"
        },
        **metadata
    })

    print("=" * 40)
    print("API GENERATION COMPLETE")
    print("Total matches:", len(all_matches))
    print("Today's matches:", len(today_matches))
    print("Upcoming:", len(upcoming_matches))
    print("Champions League:", len(champions_matches))


if __name__ == "__main__":
    main()
