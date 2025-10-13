import requests
import json
import time
import re
import html
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

# --- Configuration ---
BASE_URL = "https://www.aerialfantasy.co/players"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}
MAX_THREADS = 8
POLITE_SLEEP_SECONDS = 0.5


def _first_match(patterns, text, flags=0):
    """Helper function to return the first successful match group from a list of regex patterns."""
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1).strip()
    return None


def fetch_all_player_slugs():
    """Fetches the main player list and returns only a list of URL slugs."""
    print(f"1. Fetching player slugs from: {BASE_URL}...")
    try:
        response = requests.get(BASE_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        html_content = response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching player list: {e}")
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    slugs = []

    # Locate the container of player cards
    players_container = soup.find(
        "div",
        class_="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4",
    )
    if not players_container:
        return []

    # Locate all player links and extract the slug
    player_links = players_container.find_all(
        "a", href=re.compile(r"/players/[a-z0-9\-]+")
    )

    for link in player_links:
        href = link.get("href")
        if href:
            slug = href.split("/")[-1]
            slugs.append(slug)

    return list(set(slugs))  # Return unique slugs


def fetch_and_parse_player_details(slug):
    """
    Fetches the individual player page using the slug and extracts ALL
    data (Name, Team, Position, Selected %, Value, Matches).
    """
    DETAIL_URL = f"{BASE_URL}/{slug}/performance"
    time.sleep(POLITE_SLEEP_SECONDS)

    player_data = {
        "Name": None,
        "Team": "N/A",
        "Position": "N/A",
        "Selected_Percentage": "0.0%",
        "Value": "0.0m",
        "URL_Slug": slug,
        "Total_Points": "0pts",
        "Match_Results": [],
    }

    try:
        response = requests.get(DETAIL_URL, headers=HEADERS, timeout=10)
        response.raise_for_status()
        text = response.text

        # --- Name ---
        name_match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.DOTALL)
        if name_match:
            raw_name = html.unescape(name_match.group(1))
            player_data["Name"] = re.sub(r"<!--.*?-->", "", raw_name).strip()

        # --- Team ---
        team = None
        team_match = re.search(
            r'/images/logos/[a-z0-9\-]+\.svg[^\n]{0,120}?(?:alt|title|aria-label)\\?":\\?"([^"\\]+)',
            text,
            re.IGNORECASE,
        )
        if team_match:
            team = team_match.group(1).strip()
        else:
            team = _first_match(
                [
                    r'"club"\\s*:\\s*\\"([a-z0-9]+)\\"',
                    r'"title"\\s*:\\s*\\"([^\\"]+)\\"',
                    r'"aria-label"\\s*:\\s*\\"([^\\"]+)\\"',
                ],
                text,
                re.IGNORECASE,
            )
        if team:
            player_data["Team"] = team

        # --- Position ---
        position = _first_match(
            [
                r"\b(Goalkeeper|Defender|Midfielder|Forward)\b",
                r'"children"\s*:\s*"(Goalkeeper|Defender|Midfielder|Forward)"',
            ],
            text,
            re.IGNORECASE,
        )
        if position:
            player_data["Position"] = position.title()

        # --- Selected Percentage ---
        selected_pct = _first_match(
            [
                r'"children"\s*:\s*"Selected \(%\)".*?"children"\s*:\s*"([^"]+%)"',
                r"Selected \(%\).*?([0-9]{1,3}(?:\.[0-9]+)?%)",
                r"([0-9]{1,3}(?:\.[0-9]+)?%)",
            ],
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if selected_pct:
            player_data["Selected_Percentage"] = selected_pct

        # --- EXTRACT PLAYER VALUE (more reliable heuristic) ---
        value = None

        # Find all occurrences of Xm (e.g. 9.5m, 12.0m, etc.)
        all_values = re.findall(r"([0-9]+(?:\.[0-9]+)?m)", text, re.IGNORECASE)

        if all_values:
            # Try to locate the one *closest to "Selected" or "Total Points"*
            last_selected_idx = max(text.find("Selected"), text.find("Total Points"))
            if last_selected_idx != -1:
                # pick the last value that appears *before* the Selected/Total Points text
                candidates = [v for v in all_values if text.find(v) < last_selected_idx]
                if candidates:
                    value = candidates[-1]
            # Fallback: if nothing matched proximity, take the last 'Xm' in file
            if not value:
                value = all_values[-1]

            value = value.lower().strip()
            player_data["Value"] = value

        # --- Extract ALL GameBasedPerformance blocks (escaped JSON) ---
        pattern = (
            r'\{\\"contributions\\":\[.*?\\"__typename\\":\\"GameBasedPerformance\\"\}'
        )
        matches = re.findall(pattern, text, re.DOTALL)
        if not matches:
            return player_data

        s = "[" + ",".join(matches) + "]"
        s = html.unescape(s)
        s = s.replace('\\"', '"')
        s = re.sub(r",(\s*[\]}])", r"\1", s)
        fixtures = json.loads(s)

        fixtures = sorted(
            fixtures, key=lambda f: f["game"]["scheduledAt"], reverse=True
        )

        match_results = []
        total_points = 0
        for f in fixtures:
            total_points += f["points"]
            game = f["game"]

            home_team_name = game["home"]["party"]["name"]
            away_team_name = game["away"]["party"]["name"]

            contributions = {
                c["contribution"]: {
                    "quantity": c["quantity"],
                    "points": c["totalPoints"],
                }
                for c in f["contributions"]
            }

            match_results.append(
                {
                    "home_team": home_team_name,
                    "away_team": away_team_name,
                    "gameweek": game["stage"]["id"],
                    "total_points": f["points"],
                    "score": f"{game['home']['score']} - {game['away']['score']}",
                    "date": datetime.fromisoformat(
                        game["scheduledAt"].replace("Z", "+00:00")
                    )
                    .date()
                    .isoformat(),
                    "contributions": contributions,
                }
            )

        player_data["Total_Points"] = f"{total_points}pts"
        player_data["Match_Results"] = match_results

    except requests.exceptions.RequestException as e:
        print(f"Warning: Request failed for {slug}: {e}")
    except json.JSONDecodeError as e:
        print(f"Warning: JSON parsing failed for {slug}: {e}")
    except Exception as e:
        print(f"Warning: General error for {slug}: {e.__class__.__name__}: {e}")

    return player_data


def main_scraper_threaded():
    start_time = time.time()
    player_slugs = fetch_all_player_slugs()

    if not player_slugs:
        print("Scraper stopped. No player slugs found.")
        return []

    total_players = len(player_slugs)
    print(
        f"\n2. Starting concurrent fetching for all {total_players} players using {MAX_THREADS} threads..."
    )

    enriched_players = []

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        # Submit the fetch and parse function for every slug
        futures = {
            executor.submit(fetch_and_parse_player_details, slug): slug
            for slug in player_slugs
        }

        for i, future in enumerate(as_completed(futures)):
            slug = futures[future]
            try:
                enriched_player = future.result()
                enriched_players.append(enriched_player)

                # Log using the player name if available, otherwise use the slug
                player_name = (
                    enriched_player.get("Name") if enriched_player.get("Name") else slug
                )
                match_count = len(enriched_player["Match_Results"])

                if match_count > 0:
                    print(
                        f"  > ({i + 1}/{total_players}) Finished: {player_name} (Data Found: {match_count} matches)"
                    )
                else:
                    print(
                        f"  > ({i + 1}/{total_players}) Finished: {player_name} (No Match Data)"
                    )

            except Exception as exc:
                print(
                    f"  > ({i + 1}/{total_players}) {slug} generated an unexpected exception: {exc.__class__.__name__}: {exc}"
                )

    end_time = time.time()
    print(
        f"\n3. Scraping complete. Total time taken: {end_time - start_time:.2f} seconds."
    )
    return enriched_players


# --- Execution ---
if __name__ == "__main__":
    final_data = main_scraper_threaded()

    if final_data:
        file_name = "data.json"
        with open(file_name, "w", encoding="utf-8") as f:
            json.dump(final_data, f, indent=4, ensure_ascii=False)

        print(f"\nData saved to {file_name}")
        print(f"Total records saved: {len(final_data)}")

        # Example to show the fixed output structure
        print("\nExample Combined Player Object (First Player with match data):")
        # Find the first player who actually has match data for a good example printout
        example_player = next(
            (p for p in final_data if p.get("Match_Results")),
            final_data[0] if final_data else None,
        )

        if example_player:
            first_match = (
                example_player["Match_Results"][0]
                if example_player["Match_Results"]
                else {}
            )

            print(
                json.dumps(
                    {
                        "Name": example_player.get("Name"),
                        "Team": example_player.get("Team"),
                        "Position": example_player.get("Position"),
                        "Value": example_player.get("Value"),
                        "Selected_Percentage": example_player.get(
                            "Selected_Percentage"
                        ),
                        "Total_Points": example_player.get("Total_Points"),
                        "Example_Match_Result": first_match,
                    },
                    indent=4,
                    ensure_ascii=False,
                )
            )
