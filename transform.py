import json
import os
from collections import defaultdict
from datetime import datetime
import re

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


def create_gw_tooltip(match_result, player_team):
    """
    Creates a detailed, multi-line tooltip string for Gameweek match.
    """
    # 1. Date Formatting (UPDATED: %-d %b)
    try:
        date_obj = datetime.strptime(match_result["date"], "%Y-%m-%d")
        date_str = date_obj.strftime("%-d %b")
    except (KeyError, ValueError):
        date_str = "Date Unknown"

    # 2. Fixture and Location
    player_team_code = get_wsl_team_code(player_team)
    home_team = get_wsl_team_code(match_result.get("home_team"))
    away_team = get_wsl_team_code(match_result.get("away_team"))

    if player_team_code == home_team:
        opponent_team = away_team
        location = "(H)"
    elif player_team_code == away_team:
        opponent_team = home_team
        location = "(A)"
    else:
        opponent_team = "Unknown Opponent"
        location = ""

    fixture_line = f"{opponent_team} {location}"

    # 3. Score and Result (W/D/L)
    score = match_result.get("score", "0 - 0")
    result_abbr = "D"
    try:
        score_parts = [int(p.strip()) for p in score.split(" - ") if p.strip()]
        if len(score_parts) == 2:
            home_score, away_score = score_parts

            if home_team == player_team_code:
                player_score, opponent_score = home_score, away_score
            elif away_team == player_team_code:
                player_score, opponent_score = away_score, home_score
            else:
                player_score, opponent_score = home_score, away_score

            if player_score > opponent_score:
                result_abbr = "W"
            elif player_score < opponent_score:
                result_abbr = "L"
    except ValueError:
        pass

    # UPDATED: Result first
    score_line = f"{result_abbr} {score}"

    # UPDATED: No icon on header line
    header_line = f"{date_str}\n{fixture_line}\n{score_line}"

    contribution_lines = []

    # UPDATED CONTRIBUTION MAP: All icons removed
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

    # Iterate through contributions, sorted by points (best first)
    sorted_contributions = sorted(
        match_result.get("contributions", {}).items(),
        key=lambda item: item[1].get("points", 0),
        reverse=True,
    )

    for key, data in sorted_contributions:
        label = CONTRIBUTION_MAP.get(key, key)
        quantity = data.get("quantity", 1)
        points = data.get("points", 0)

        # Only include contributions with non-zero points or where it's a card/event
        if points != 0 or key in [
            "ReceivedRedCard",
            "ReceivedYellowCard",
            "MissedPenalty",
            "ScoredOwnGoal",
        ]:
            sign = "+" if points > 0 else ""

            if quantity > 1:
                line = f"{label} x{quantity} ({sign}{points}pt{'' if abs(points) == 1 else 's'})"
            else:
                line = f"{label} ({sign}{points}pt{'' if abs(points) == 1 else 's'})"

            contribution_lines.append(line)

    # Combine: Header line, separator, Contribution lines
    tooltip_parts = [header_line, "—" * 20] + contribution_lines
    return "\n".join(tooltip_parts)


# --- MAIN TRANSFORMATION FUNCTION ---


def transform_data(
    input_file="data.json", output_file="transformed_data.json", recent_games_count=4
):

    # 1. Load Data
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading data: {e}")
        return
    print(f"Loaded {len(raw_data)} players from {input_file}.")

    # 2. Determine Max Gameweeks
    all_gameweek_numbers = set()
    for player in raw_data:
        for match in player.get("Match_Results", []):
            try:
                all_gameweek_numbers.add(int(match["gameweek"]))
            except (KeyError, ValueError):
                continue

    if not all_gameweek_numbers:
        final_gameweeks = []
    else:
        max_gw = max(all_gameweek_numbers)
        final_gameweeks = [str(gw) for gw in range(1, max_gw + 1)]

    final_output = []

    # Helper functions for safe conversion (Logic remains unchanged)
    def safe_float(value):
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = re.sub(r"[^\d\.]", "", value)
            try:
                return float(cleaned)
            except ValueError:
                return 0.0
        return 0.0

    def safe_int(value):
        if isinstance(value, int):
            return value
        return int(safe_float(value))

    # ACCUMULATION MAPPINGS (Logic remains unchanged)
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

    # --- 3. Process Each Player ---
    for player in raw_data:
        # A. Static Stats
        name = player.get("Name")

        # Skip players with no name
        if not name:
            continue

        club = get_wsl_team_code(player.get("Team"))
        position = get_position_code(player.get("Position"))

        # RETAIN full float precision for intermediate calculation
        value = safe_float(player.get("Value"))
        selected_percentage = safe_float(player.get("Selected_Percentage"))
        total_points = safe_int(player.get("Total_Points"))

        # B. Dynamic Stats Accumulation (Logic remains unchanged)
        gw_data_map = {}
        gw_points_total_4gw = 0
        gw_games_played_4gw = 0
        overall_stats = defaultdict(int)
        overall_games_played = 0

        sorted_matches = sorted(
            player.get("Match_Results", []),
            key=lambda m: int(m.get("gameweek", 0)),
            reverse=True,
        )

        for i, match in enumerate(sorted_matches):
            gw = match.get("gameweek")
            points = match.get("total_points", 0)

            if not gw:
                continue

            player_team = player.get("Team")
            tooltip_str = create_gw_tooltip(match, player_team)

            gw_data_map[gw] = {"points": points, "tooltip": tooltip_str}

            if i < recent_games_count:
                gw_points_total_4gw += points
                gw_games_played_4gw += 1

            overall_games_played += 1

            for key, data in match.get("contributions", {}).items():
                target_stat_key = STAT_ACCUMULATORS.get(key)

                if target_stat_key:
                    if key == "ConcededGoals":
                        overall_stats[target_stat_key] += data.get("points", 0)
                    else:
                        overall_stats[target_stat_key] += data.get("quantity", 1)

        # C. Calculate final derived metrics
        ppm_total = total_points / value if value > 0 else 0.0
        ppm_4gw = gw_points_total_4gw / value if value > 0 else 0.0
        ppg_4gw = (
            gw_points_total_4gw / recent_games_count if recent_games_count > 0 else 0.0
        )

        # --- 5. Final Player Object Assembly (Rounding applied) ---
        final_player = {
            "Name": name,
            "Club": club,
            "Position": position,
            # ROUNDING APPLIED TO DECIMAL FIELDS
            "Value": round(value, 1),
            "Total Points": total_points,
            "Selected Percentage": round(selected_percentage, 1),
            "Total Games Played": overall_games_played,
            # 4GW Stats (Rounding applied)
            "Total Over 4 Gameweeks": gw_points_total_4gw,
            "Games Played Over 4 Gameweeks": gw_games_played_4gw,
            "Points Per Game Over 4 Gameweeks": round(ppg_4gw, 1),
            "Points Per Million": round(ppm_total, 1),
            "Points Per Million Over 4 Gameweeks": round(ppm_4gw, 1),
            # Overall Contribution Stats (Integers, no change)
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

        # Dynamic Gameweek columns (containing the required object: {points, tooltip})
        for gw in final_gameweeks:
            final_player[gw] = gw_data_map.get(gw, "-")

        final_output.append(final_player)

    print(len(final_output), "players processed.")
    # --- 6. Save Output ---
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=4, ensure_ascii=False)


# Execute the transformation when the script is run
transform_data(input_file="data.json", output_file="transformed_data.json")
