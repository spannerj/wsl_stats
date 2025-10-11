import json
import os
from collections import defaultdict


def get_wsl_team_code(team_name):
    """
    Transforms a full or partial WSL team name into its standardized 3-character code.

    Args:
        team_name (str): The name of the WSL club.

    Returns:
        str: The 3-character code if found (e.g., 'ARS', 'MUN'),
             or the original team name if no match is found.
    """
    # Define the mapping using the shortened/aerial-site names as keys
    TEAM_CODE_MAP = {
        "ARSENAL": "ARS",
        "ASTON VILLA": "AVL",
        "BRIGHTON": "BHA",
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

    # Perform the final lookup
    return TEAM_CODE_MAP.get(team_name.upper().strip(), team_name)


def get_position_code(position):
    """
    Transforms a players position into a standardized code.

    Args:
        position (str): The position of the player.

    Returns:
        str: The character code if found (e.g., 'GK', 'DEF'),
    """
    # Define the mapping using the shortened/aerial-site names as keys
    POSITION_MAP = {
        "GOALKEEPER": "GK",
        "DEFENDER": "DEF",
        "MIDFIELDER": "MID",
        "FORWARD": "FOR"
    }

    if not position:
        return ""

    # Perform the final lookup
    return POSITION_MAP.get(position.upper().strip(), position)


def transform_player_data(
    input_file="data.json", output_file="transformed_data.json", recent_games_count=4
):
    """
    Reads raw player data, calculates complex derived metrics, and outputs
    a flattened JSON structure suitable for DataTables.

    The logic now correctly distinguishes between a 0-point game played and a DNP
    (Did Not Play) for accurate Gameweek point representation ('-') and recent stats.
    """
    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' not found in the current directory.")
        return

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            raw_players = json.load(f)
    except json.JSONDecodeError:
        print(
            f"Error: Could not decode JSON from '{input_file}'. Please check file integrity."
        )
        return
    except Exception as e:
        print(f"An unexpected error occurred while reading the file: {e}")
        return

    # --- SETUP ---
    transformed_data = []
    
    # Updated keys to reflect calculation over Gameweeks, not just player's last X games
    recent_games_key = f"Total Over {recent_games_count} Gameweeks"
    recent_games_played_key = f"Games Played Over {recent_games_count} Gameweeks"
    ppg_recent_key = f"Points Per Game Over {recent_games_count} Gameweeks"
    ppm_recent_key = f"Points Per Million Over {recent_games_count} Gameweeks"


    # Define all contribution types we are interested in tracking.
    CONTRIBUTION_MAP = {
        "Scored": "Total Goals",
        "Assisted": "Total Assists",
        "Bonus": "Total Bonus Points",
        "PlayedOneMinute": "Total 1 min Appearances",
        "PlayedSixtyMinutes": "Total 60 min Appearances",
        "Saves": "Total Saves",
        "ThreeSaves": "Total Saves",
        "CleanSheet": "Total Clean Sheet",
        "ConcededGoals": "Total Conceeded",
        "ReceivedYellowCard": "Total Yellow Cards",
        "ReceivedRedCard": "Total Red Cards",
        "GoalLineClearance": "Total Clearances",
        "MissedPenalty": "Total Missed Penalties",
        "ScoredOwnGoal": "Total Own Goals",
    }

    print(f"Processing {len(raw_players)} players...")

    # --- PASS 1: Determine all Gameweeks in the season and sort them ---
    all_gameweeks = set()
    for player in raw_players:
        for match in player.get("Match_Results", []):
            all_gameweeks.add(f"{match.get('gameweek', 'N/A')}")

    # Sort Gameweeks from most recent (highest number) to oldest
    final_gameweeks = sorted(
        list(all_gameweeks),
        key=lambda x: int(x.replace("GW", "").replace("N/A", "0")),
        reverse=True,
    )
    # Get the key names for the X most recent gameweeks
    recent_gameweek_keys = final_gameweeks[:recent_games_count]
    

    # --- PASS 2: Process players for transformation ---
    for player in raw_players:
        # --- 1. Basic Fields ---
        name = player.get("Name", "Unknown Player")
        
        total_points_str = player.get("Total_Points", "0pts").replace("pts", "")
        selected_pct_str = player.get("Selected_Percentage", "0.0%").replace("%", "")
        player_value_millions_str = player.get("Value", "0.0m").replace("m", "")

        try:
            total_points = float(total_points_str)
            selected_pct = float(selected_pct_str)
            player_value_million = float(player_value_millions_str)
            if player_value_million <= 0:
                player_value_million = 10.0 # Use a default value
        except ValueError:
            print(
                f"Warning: Skipping derived calculations for {name} due to invalid numeric data."
            )
            total_points = 0.0
            selected_pct = 0.0
            player_value_million = 10.0

        match_results = player.get("Match_Results", [])

        # --- 2. Aggregate Totals and Gameweek Data (Accurate Counting) ---
        total_games_played = 0 # Start at 0, only increment if they actually played
        aggregate_stats = defaultdict(lambda: 0)
        
        # Map stores GW -> points (even 0 if they played and got 0). Used for final output.
        gameweek_points_map = {} 

        for match in match_results:
            gw_key = f"{match.get('gameweek', 'N/A')}"
            points = int(match.get("total_points", 0))

            # CRITICAL: Distinguish between 'Played' and 'DNP'. 
            # If PlayedOneMinute is present/positive OR they have points > 0, they played.
            played_one_minute_qty = match.get("contributions", {}).get("PlayedOneMinute", {}).get("quantity", 0)
            
            player_played = (played_one_minute_qty > 0) or (points > 0) or (match.get("contributions", {}).get("PlayedSixtyMinutes", {}).get("quantity", 0) > 0)

            if player_played:
                # Player played
                gameweek_points_map[gw_key] = points
                
                # Aggregate contributions (only count if played)
                for contribution, details in match.get("contributions", {}).items():
                    if contribution in CONTRIBUTION_MAP:
                        aggregate_stats[CONTRIBUTION_MAP[contribution]] += details.get(
                            "quantity", 0
                        )
                
                total_games_played += 1
            else:
                # Player was listed in data but recorded 0 minutes/0 points (DNP/unused sub)
                gameweek_points_map[gw_key] = 0
                # Do NOT count towards total_games_played
                
        # --- 3. Recent Gameweeks Calculations ---
        recent_points = 0
        recent_games_played_count = 0

        # Iterate over the season's last X gameweeks (from Pass 1)
        for gw_key in recent_gameweek_keys:
            # Get points. Defaults to 0 if the GW is missing from the player's data 
            # (which means DNP and 0 points earned).
            points_for_gw = gameweek_points_map.get(gw_key, 0)
            
            # The gameweek points should always be added to the recent total, 
            # whether the player played or was DNP (since DNP contributes 0 points).
            recent_points += points_for_gw
            
            # CRITICAL: Count only if the player played this specific gameweek.
            # We rely on the initial loop's definition of what constitutes a 'game played'
            # (which is captured by checking if the GW exists in the map AND if the original source
            # confirmed an appearance, which we determined by only counting appearance-based
            # contributions or points > 0).
            
            # The simplest way to check if they played this specific GW is to look back at the raw data:
            for match in match_results:
                if f"{match.get('gameweek', 'N/A')}" == gw_key:
                    points_match = int(match.get("total_points", 0))
                    played_qty = match.get("contributions", {}).get("PlayedOneMinute", {}).get("quantity", 0)
                    sixty_min_qty = match.get("contributions", {}).get("PlayedSixtyMinutes", {}).get("quantity", 0)

                    if played_qty > 0 or points_match > 0 or sixty_min_qty > 0:
                        recent_games_played_count += 1
                    break # Found the match result for this GW
        
        # --- 4. Final Derived Metrics ---
        ppg = total_points / total_games_played if total_games_played > 0 else 0.0
        
        # PPG recent relies on games *played* in the recent GW span (correcting the user's issue)
        ppg_recent = (
            recent_points / recent_games_played_count if recent_games_played_count > 0 else 0.0
        )

        ppm = total_points / player_value_million
        # PPM recent relies on the total points earned in the recent GW span
        ppm_recent = recent_points / player_value_million

        # Create the base transformed player object
        transformed_player = {
            "Name": name,
            "Club": get_wsl_team_code(player.get("Team", "N/A")),
            "Position": get_position_code(player.get("Position", "N/A")),
            "Value": player_value_million,  # Stored as number (M)
            "Total Points": int(total_points),  # Stored as integer
            "Total Games Played": total_games_played,
            # Updated Keys
            recent_games_key: int(recent_points),  # Stored as integer
            recent_games_played_key: recent_games_played_count,
            ppg_recent_key: round(ppg_recent, 1), # Calculated using recent_games_played_count
            "Points Per Million": round(ppm, 1),  # Stored as float
            ppm_recent_key: round(ppm_recent, 1),
        }

        # Add all aggregated contribution stats (stored as integer).
        unique_display_names = set(CONTRIBUTION_MAP.values())
        for display_name in unique_display_names:
            transformed_player[display_name] = int(aggregate_stats[display_name])

        # Store the points map for final flattening
        transformed_player["GW_Points_Map"] = gameweek_points_map

        transformed_data.append(transformed_player)

    # --- 5. Final Output Formatting (Replace DNP weeks with a dash) ---
    final_output = []
    for player in transformed_data:
        # Create the final flat structure
        final_player = player.copy()
        # Extract the temporary GW map
        gw_points_map = final_player.pop("GW_Points_Map")

        # Add dynamic Gameweek columns
        for gw in final_gameweeks:
            points = gw_points_map.get(gw)
            
            # If the GW is NOT in the map (player DNP that GW) OR the points are 0 
            # and the gameweek is missing in the map, use a dash.
            # Here, we use the fact that if a GW is missing, it's a DNP. 
            # If points is 0, the map will store 0 (if they were listed DNP or played for 1 min and got 0).
            # We want to show a dash if they were DNP. Since we only record entries 
            # from Match_Results, any missing GW in the map is a DNP for the season's GW sequence.
            
            # If the GW is missing from the player's match_results, output '-'
            final_player[gw] = gw_points_map.get(gw, '-')

        final_output.append(final_player)

    # --- 6. Save Output ---
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=4, ensure_ascii=False)

    print(f"\nSuccessfully transformed data for {len(final_output)} players.")
    print(f"Output saved to {output_file}")
    print(
        f"Generated {len(final_gameweeks)} Gameweek columns: {', '.join(final_gameweeks)}"
    )
    print(f"Recent stats calculated over the last {recent_games_count} gameweeks: {', '.join(recent_gameweek_keys)}")
    print(
        "\nNext Steps: 1. Rename your original JSON list to 'data.json'. 2. Run this Python script."
    )


if __name__ == "__main__":
    transform_player_data()
