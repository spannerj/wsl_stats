import requests
import json
from collections import defaultdict
from datetime import datetime


def get_fixture_data() -> list[dict[str, str | int]]:
    """Fetches fixture data from the API and returns a list of dictionaries."""
    base_url = "https://api.aerialfantasy.co/graphql"
    query = """
        {
            clubs {
                id
                name
                games {
                    id
                    scheduledAt
                    hasStarted
                    stage { id }
                    home { party { __typename
                        ... on Club { name, shortName, id}
                    }
                    }
                    away { party { __typename
                        ... on Club { name, shortName, id}
                    }
                    }
                }
            }
        }
    """
    print("Fetching fixture data from API...")
    res = requests.post(base_url, json={"query": query})
    res.raise_for_status()
    data = res.json()
    return data["data"]


def process_game(game):
    """
    Transforms a complex game object into the simplified fixture format
    """
    home_name = game.get('home', {}).get('party', {}).get('name')
    home_short_name = game.get('home', {}).get('party', {}).get('shortName')
    home_id = game.get('home', {}).get('party', {}).get('id')
    away_name = game.get('away', {}).get('party', {}).get('name')
    away_short_name = game.get('away', {}).get('party', {}).get('shortName')
    away_id = game.get('away', {}).get('party', {}).get('id')
    stage_id = game.get('stage', {}).get('id')

    # --- Date/Time Transformation ---
    scheduled_at_str = game.get('scheduledAt')
    date_obj = datetime.fromisoformat(scheduled_at_str.replace('Z', '+00:00'))

    game_date = date_obj.strftime("%-d %b")
    kick_off_time = date_obj.strftime("%H:%M")

    return {
        "game_date": game_date,     
        "kick_off_time": kick_off_time,
        "game_week": stage_id,
        "home_id": home_id.upper(),
        "home_name": home_name,
        "home_short_name": home_short_name,
        "away_id": away_id.upper(),
        "away_name": away_name,
        "away_short_name": away_short_name,
    }


def filter_fixtures(fixtures_data):
    # Filter Fixtures into a map (Club ID -> [Upcoming Fixtures])
    club_fixtures_map = {}

    for club in fixtures_data.get('clubs', []):
        club_id = club.get('id').upper()

        upcoming_games = []
        for game in club.get('games', []):

            # Filter: Keep only games that haven't started
            if game.get('hasStarted') is False:
                # Transform the game object into the desired, simplified format
                simplified_fixture = process_game(game)
                upcoming_games.append(simplified_fixture)

        club_fixtures_map[club_id] = upcoming_games

    return club_fixtures_map


def get_player_data() -> list[dict[str, int | str | float]]:
    """Fetches the player details from the API and returns a list of dictionaries."""
    base_url = "https://api.aerialfantasy.co/graphql"
    query = """
        {
            players {
                slug
                firstName
                lastName
                club {id, shortName}
                position
                nationality
                price
                totalPoints
                selected
                performanceV2 {
                    games {
                        game {id, scheduledAt, stage {id}, home{score}, away{score}}
                        points
                        contributions {
                            contribution
                            quantity
                            individualPoints
                        }
                    }
                    extras {
                        contributions {
                            contribution
                            quantity
                            individualPoints
                        }
                    }
                }
            }
        }
    """
    res = requests.post(base_url, json={"query": query})
    res.raise_for_status()
    data = res.json()
    return data["data"]["players"]


# --- TEAM NAME EXTRACTION ---
def extract_teams_from_game_id(game_id):
    """
    Extracts home and away team codes from game ID.
    First 3 characters = home team, last 3 = away team.
    """
    if len(game_id) >= 6:
        home_team = game_id[:3].upper()
        away_team = game_id[-3:].upper()
        return home_team, away_team
    return "", ""


# --- MAPPING FUNCTIONS ---


def get_wsl_team_code(team_name):
    """
    Transforms a full or partial WSL team name into its standardized 3-character code.
    """
    TEAM_CODE_MAP = {
        "ARSENAL": "ARS",
        "ASTON VILLA": "AVL",
        "BRIGHTON": "BHA",
        "BRIGHTON & HOVE ALBION": "BHA",
        "CHELSEA": "CHE",
        "EVERTON": "EVE",
        "LEICESTER CITY": "LEI",
        "LIVERPOOL": "LIV",
        "LONDON CITY LIONESSES": "LCL",
        "MANCHESTER CITY": "MCI",
        "MANCHESTER UNITED": "MUN",
        "TOTTENHAM HOTSPUR": "TOT",
        "WEST HAM UNITED": "WHU",
    }
    if not team_name:
        return ""
    normalized_name = team_name.upper().strip()
    return TEAM_CODE_MAP.get(normalized_name, team_name)


def get_position_code(position):
    """
    Transforms a players position into a standardized code.
    """
    POSITION_MAP = {
        "GOALKEEPER": "GK",
        "DEFENDER": "DEF",
        "MIDFIELDER": "MID",
        "FORWARD": "FOR",
    }
    if not position:
        return ""
    return POSITION_MAP.get(position.upper().strip(), position[:3].upper())


# --- TOOLTIP FUNCTION ---
def create_gw_tooltip(game_data, player_team_code):
    """
    Creates a detailed, multi-line tooltip string for Gameweek match.
    Works directly with API game data structure.
    """
    game = game_data["game"]

    # 1. Date Formatting
    try:
        date_obj = datetime.fromisoformat(game["scheduledAt"].replace("Z", "+00:00"))
        date_str = date_obj.strftime("%-d %b")
    except (KeyError, ValueError):
        date_str = "Date Unknown"

    # 2. Extract team codes from game ID
    game_id = game.get("id", "")
    home_team, away_team = extract_teams_from_game_id(game_id)

    # 3. Determine opponent and location
    if player_team_code == home_team:
        opponent_team = away_team
        location = "(H)"
    elif player_team_code == away_team:
        opponent_team = home_team
        location = "(A)"
    else:
        opponent_team = "Unknown"
        location = ""

    fixture_line = f"{opponent_team} {location}"

    # 4. Score and Result (W/D/L) - use already-separated scores
    home_score = game.get("home", {}).get("score", 0)
    away_score = game.get("away", {}).get("score", 0)
    score = f"{home_score} - {away_score}"

    # Determine result
    result_abbr = "D"
    if player_team_code == home_team:
        player_score, opponent_score = home_score, away_score
    elif player_team_code == away_team:
        player_score, opponent_score = away_score, home_score
    else:
        player_score, opponent_score = home_score, away_score

    if player_score > opponent_score:
        result_abbr = "W"
    elif player_score < opponent_score:
        result_abbr = "L"

    score_line = f"{result_abbr} {score}"
    header_line = f"{date_str}\n{fixture_line}\n{score_line}"

    # 5. Process contributions
    contribution_lines = []
    CONTRIBUTION_MAP = {
        "PlayedOneMinute": "1 min",
        "PlayedSixtyMinutes": "60 min",
        "Scored": "Goal",
        "Assisted": "Assist",
        "CleanSheet": "Clean Sheet",
        "Bonus": "Bonus",
        "ThreeSaves": "Saves",
        "GoalLineClearance": "Clearance",
        "MissedPenalty": "Missed Pen",
        "ReceivedRedCard": "Red Card",
        "ReceivedYellowCard": "Yellow Card",
        "ScoredOwnGoal": "Own Goal",
        "ConcededGoals": "Conceded",
    }

    # Sort contributions by total points (quantity * individualPoints)
    contributions = game_data.get("contributions", [])
    sorted_contributions = sorted(
        contributions,
        key=lambda c: c.get("quantity", 1) * c.get("individualPoints", 0),
        reverse=True,
    )

    for contrib in sorted_contributions:
        contrib_type = contrib["contribution"]
        label = CONTRIBUTION_MAP.get(contrib_type, contrib_type)
        quantity = contrib.get("quantity", 1)
        individual_points = contrib.get("individualPoints", 0)
        # Calculate total points for this contribution
        total_points = quantity * individual_points

        # Only include contributions with non-zero points or where it's a card/event
        if total_points != 0 or contrib_type in [
            "ReceivedRedCard",
            "ReceivedYellowCard",
            "MissedPenalty",
            "ScoredOwnGoal",
        ]:
            sign = "+" if total_points > 0 else ""

            if quantity > 1:
                line = f"{label} x{quantity} ({sign}{total_points}pt{'' if abs(total_points) == 1 else 's'})"
            else:
                line = f"{label} ({sign}{total_points}pt{'' if abs(total_points) == 1 else 's'})"

            contribution_lines.append(line)

    # Combine: Header line, separator, Contribution lines
    tooltip_parts = [header_line, "—" * 20] + contribution_lines
    return "\n".join(tooltip_parts)


def combine_player_and_fixture_data(final_player_list, fixtures_map):
    """
    Filters upcoming fixtures and joins them to the player data.

    Args:
        final_player_list (list): The list of fully processed player dictionaries.
        fixtures_map (dict): The map of {club_id: [upcoming_fixtures]}.
    """
    print("Combine player data and fixture data.")

    # Initialize the final output list
    all_players_with_fixtures = []

    # Iterate directly over the list of players (which is the input 'final_player_list')
    # Use 'player' here as the loop variable.
    for player in final_player_list:
        # NOTE: The player dicts inside final_output still have the 'Club' key
        # since it was transformed but not removed yet.
        club_id = player.get('Club', '').upper()

        # Retrieve the upcoming fixtures list for this player's club
        upcoming_fixtures = fixtures_map.get(club_id, [])

        # Attach the fixtures data
        player['upcoming_fixtures'] = upcoming_fixtures

        all_players_with_fixtures.append(player)

    print(f"{len(all_players_with_fixtures)} players combined with fixtures.")

    return all_players_with_fixtures


# --- MAIN TRANSFORMATION FUNCTION ---
def transform_data(output_file="transformed_data.json", recent_games_count=4):
    """
    Fetches data from API, transforms it directly, and saves to output file.
    """

    # 1. Fetch data from API
    print("Fetching player data from API...")
    try:
        api_players = get_player_data()
    except Exception as e:
        print(f"Error fetching API data: {e}")
        return

    print(f"Loaded {len(api_players)} players from API.")

    # 2. Determine max gameweeks from all players
    all_gameweek_numbers = set()
    for player in api_players:
        for performance in player.get("performanceV2", []):
            for game_data in performance.get("games", []):
                try:
                    gw = game_data["game"]["stage"]["id"]
                    all_gameweek_numbers.add(int(gw))
                except (KeyError, ValueError):
                    continue

    if not all_gameweek_numbers:
        final_gameweeks = []
    else:
        max_gw = max(all_gameweek_numbers)
        final_gameweeks = [str(gw) for gw in range(1, max_gw + 1)]

    # 3. Stat accumulation mappings
    STAT_ACCUMULATORS = {
        "CleanSheet": "Total Clean Sheet",
        "Scored": "Total Goals",
        "Assisted": "Total Assists",
        "Bonus": "Total Bonus Points",
        "ReceivedYellowCard": "Total Yellow Cards",
        "ReceivedRedCard": "Total Red Cards",
        "MissedPenalty": "Total Missed Penalties",
        "ScoredOwnGoal": "Total Own Goals",
        "ThreeSaves": "Total Saves",
        "GoalLineClearance": "Total Clearances",
        "PlayedOneMinute": "Total 1 min Appearances",
        "PlayedSixtyMinutes": "Total 60 min Appearances",
        "ConcededGoals": "Total Conceeded",
    }

    final_output = []

    # 4. Process each player
    for player in api_players:
        # Extract basic info directly from API
        name = f"{player.get('firstName', '')} {player.get('lastName', '')}".strip()
        if not name:
            continue

        club = player.get("club", {}).get("id", "").upper()
        nationality = player.get("nationality", "")
        position = get_position_code(player.get("position", ""))
        value = player.get("price", 0) / 10.0  # API returns in tenths
        selected_percentage = player.get("selected", 0) * 100  # Convert to percentage

        # Initialize stats
        gw_data_map = {}
        gw_points_total_4gw = 0
        gw_games_played_4gw = 0
        overall_stats = defaultdict(int)
        overall_games_played = 0
        total_points = 0  # Will calculate by summing all game points

        # Collect all games
        all_games = []
        for performance in player.get("performanceV2", []):
            for game_data in performance.get("games", []):
                all_games.append(game_data)

        # Sort games by gameweek (most recent first)
        sorted_games = sorted(
            all_games,
            key=lambda g: int(g.get("game", {}).get("stage", {}).get("id", 0)),
            reverse=True,
        )

        # Process each game
        for i, game_data in enumerate(sorted_games):
            game = game_data.get("game", {})
            gw = game.get("stage", {}).get("id", "")
            points = game_data.get("points", 0)

            if not gw:
                continue

            # Create tooltip
            tooltip_str = create_gw_tooltip(game_data, club)

            # Store gameweek data
            gw_data_map[gw] = {"points": points, "tooltip": tooltip_str}

            # Calculate total points by summing all game points
            total_points += points

            # Calculate 4GW stats (last 4 games)
            if i < recent_games_count:
                gw_points_total_4gw += points
                gw_games_played_4gw += 1

            overall_games_played += 1

            # Accumulate contribution stats
            for contrib in game_data.get("contributions", []):
                contrib_type = contrib["contribution"]
                target_stat_key = STAT_ACCUMULATORS.get(contrib_type)

                if target_stat_key:
                    if contrib_type == "ConcededGoals":
                        # For conceded goals, accumulate total points (quantity * individualPoints)
                        # This matches the old format: Total Conceeded stores negative points
                        quantity = contrib.get("quantity", 1)
                        individual_pts = contrib.get("individualPoints", 0)
                        overall_stats[target_stat_key] += quantity * individual_pts
                    else:
                        # For everything else, accumulate the quantity
                        overall_stats[target_stat_key] += contrib.get("quantity", 1)

        # Calculate derived metrics
        ppm_total = total_points / value if value > 0 else 0.0
        ppm_4gw = gw_points_total_4gw / value if value > 0 else 0.0
        ppg_4gw = (
            gw_points_total_4gw / recent_games_count if recent_games_count > 0 else 0.0
        )

        # Assemble final player object
        final_player = {
            "Name": name,
            "Club": club,
            "Position": position,
            "Value": round(value, 1),
            "Nationality": nationality,
            "Total Points": total_points,
            "Selected Percentage": round(selected_percentage, 1),
            "Total Games Played": overall_games_played,
            "Total Over 4 Gameweeks": gw_points_total_4gw,
            "Games Played Over 4 Gameweeks": gw_games_played_4gw,
            "Points Per Game Over 4 Gameweeks": round(ppg_4gw, 1),
            "Points Per Million": round(ppm_total, 1),
            "Points Per Million Over 4 Gameweeks": round(ppm_4gw, 1),
            "Total Goals": overall_stats["Total Goals"],
            "Total Assists": overall_stats["Total Assists"],
            "Total Red Cards": overall_stats["Total Red Cards"],
            "Total Yellow Cards": overall_stats["Total Yellow Cards"],
            "Total Saves": overall_stats["Total Saves"],
            "Total Own Goals": overall_stats["Total Own Goals"],
            "Total Conceeded": overall_stats["Total Conceeded"],
            "Total Clean Sheet": overall_stats["Total Clean Sheet"],
            "Total Bonus Points": overall_stats["Total Bonus Points"],
            "Total Missed Penalties": overall_stats["Total Missed Penalties"],
            "Total Clearances": overall_stats["Total Clearances"],
            "Total 1 min Appearances": overall_stats["Total 1 min Appearances"],
            "Total 60 min Appearances": overall_stats["Total 60 min Appearances"],
        }

        # Add dynamic gameweek columns
        for gw in final_gameweeks:
            final_player[gw] = gw_data_map.get(gw, "-")

        final_output.append(final_player)

    print(f"{len(final_output)} players processed.")

    # Get fixtrure data for teams
    fixtures = get_fixture_data()
    print("Loaded fixtures from API.")

    filtered_fixtures = filter_fixtures(fixtures)
    combined_data = combine_player_and_fixture_data(final_output, filtered_fixtures)

    # Save output
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(combined_data, f, indent=4, ensure_ascii=False)
    print(f"Data saved to {output_file}")


# Execute the transformation when the script is run
if __name__ == "__main__":
    transform_data(output_file="transformed_data.json")
