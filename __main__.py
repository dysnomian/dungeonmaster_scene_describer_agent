import os
import json
import yaml

from typing import Any, Union

from openai import OpenAI

from dungeonmaster_db.adapter import DbConnection as db_conn

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_CONFIG = {"model": "lmstudio-community/Meta-Llama-3-8B-Instruct-GGUF"}


def build_llm_config(name: Union[str, None]) -> dict:
    with open("llm_config.yml", "r") as f:
        config_yaml = yaml.safe_load(f)

    return config_yaml.get(name, {})


client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")


### Database
def fetch_full_location_info(session_id: int) -> None | str:
    "Given a session ID, fetches the current location id and time of day from the database. Use the current location ID to fetch the full location info."
    session = None

    with db_conn() as conn:
        with conn.cursor() as cur:

            # Get the session info
            cur.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
            result = cur.fetchone()
            session = {
                "id": result[0],
                "location_id": result[1],
                "time_of_day": result[2],
            }
            # print("TIME OF DAY:", session["time_of_day"])

    if session is None:
        return None
    else:
        location = fetch_location(session["location_id"])
        if location.get("id"):
            location["time_of_day"] = session["time_of_day"]
            return json.dumps(location)


def fetch_location(location_id: int) -> dict:
    "Given a location ID, fetches the location from the database and returns it as JSON."
    location = None
    exits = []

    with db_conn() as conn:
        location = {}

        with conn.cursor() as cur:

            # Get the base location info
            cur.execute(
                "SELECT * FROM locations WHERE id = %s",
                (location_id,)
            )
            result = cur.fetchone() or {}
            if result is None:
                return {}

            location = {
                "id": result[0],
                "starting_location_id": result[1],
                "parent_id": result[2],
                "name": result[3],
                "category": result[4],
                "interior_description": result[5],
                "exterior_description": result[6],
                "notes": result[7]
            }
            print("LOCATION:", location)

            # Get the exits where the start_location_id or end_location_id is the location_id
            if location.get("id"):
                cur.execute(
                    """
                    SELECT id, start_location_id, end_location_id, name, description, category, is_one_way, is_fast_travel_path, describe_end_location_exterior
                    FROM connections
                    WHERE start_location_id = %s OR end_location_id = %s
                    """,
                    (location_id, location_id)
                )
                result = cur.fetchall()

                if result is not None:
                    for row in result:
                        exits.append({
                            "id": row[0],
                            "start_location_id": row[1],
                            "end_location_id": row[2],
                            "name": row[3],
                            "description": row[4],
                            "category": row[5],
                            "is_one_way": row[6],
                            "is_fast_travel_path": row[7],
                            "describe_end_location_exterior": row[8],
                        })
                    location["exits"] = exits
                # print("EXITS:", location["exits"])

    return location


### Agent

system_prompt = """
You are an agent that takes JSON scene descriptions and fleshes them out into vivid but succinct descriptions for a story. Give your description in the second person ('You see a room with...', 'The tree towers before you...') and write them using the interior_description field as the basis. The notes are to guide your description, but should be concealed from the player and should not be mentioned explicitly.

If the time of day is included, take that into account in your description. Consider differences in noises, activitites, lighting.

Describe all non-hidden exits, but do not make up any. Do not mention hidden exits. Do not use the exits' names. If an exit specifies to describe the exit end location's exterior, do so.
"""

user_prompt = fetch_full_location_info(1)

response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": str(user_prompt)},
            ],
            model=LLM_CONFIG.get("model", "gpt-3.5-turbo"),
            temperature=1,
            max_tokens=1024,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
        )

# print("LOCATION JSON:\n", user_prompt)
print("RESPONSE:\n", response.choices[0].message.content)
