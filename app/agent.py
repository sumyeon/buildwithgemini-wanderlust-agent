# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore
from google.genai import types

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager

from .a2ui_utils import a2ui_callback

MODEL = "gemini-3.6-flash"

# Explicit Project ID, Memory Bank / Agent Engine, and Asset Bucket constants
FIRESTORE_PROJECT = "qwiklabs-gcp-03-f9a25ebb0655"
ASSETS_BUCKET_NAME = "wanderlust-travel-assets-qwiklabs-gcp-03-f9a25ebb0655"
AGENT_ENGINE_ID = "8824061299483738112"
AGENT_ENGINE_RESOURCE = "projects/1064413292320/locations/us-east1/reasoningEngines/8824061299483738112"
SANDBOX_RESOURCE_NAME = "projects/1064413292320/locations/us-east1/reasoningEngines/8824061299483738112/sandboxEnvironments/2364363416090443776"


async def generate_memories_callback(callback_context: CallbackContext):
    """Saves turn context to Vertex AI Memory Bank across sessions."""
    await callback_context.add_session_to_memory()
    return None


def get_firestore_client() -> firestore.Client:
    """Returns a Firestore client pinned to the explicit project ID."""
    return firestore.Client(project=FIRESTORE_PROJECT)


def search_destinations(style: Optional[str] = None, max_budget_usd: Optional[int] = None) -> List[Dict[str, Any]]:
    """Searches the destination catalog filtered by travel style or maximum daily budget.

    Args:
        style: Optional style keyword to match (e.g., 'culture', 'foodie', 'relaxation', 'adventure', 'nature', 'beach').
        max_budget_usd: Optional maximum estimated daily cost in USD (e.g., 150).

    Returns:
        A list of matching destination dictionaries with details such as name, country, styles, budget tier, and attractions.
    """
    db = get_firestore_client()
    docs = db.collection("destinations").stream()
    results = []

    for doc in docs:
        data = doc.to_dict()
        if style:
            styles = [s.lower() for s in data.get("style", [])]
            if style.lower() not in styles:
                continue
        if max_budget_usd is not None:
            daily_cost = data.get("average_daily_cost_usd", 0)
            if daily_cost > max_budget_usd:
                continue
        results.append(data)

    return results


def get_destination_details(destination_id_or_name: str) -> Dict[str, Any]:
    """Retrieves full details for a specific destination from the catalog.

    Args:
        destination_id_or_name: The destination ID (e.g. 'kyoto-japan') or destination name (e.g. 'Kyoto').

    Returns:
        The detailed destination information including top attractions, best seasons, and daily cost.
    """
    db = get_firestore_client()
    # Try direct document lookup first
    doc_ref = db.collection("destinations").document(destination_id_or_name.lower())
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()

    # Search by destination name case-insensitively
    docs = db.collection("destinations").stream()
    for d in docs:
        data = d.to_dict()
        if data.get("name", "").lower() == destination_id_or_name.lower():
            return data

    return {"error": f"Destination '{destination_id_or_name}' not found in catalog."}


def save_itinerary(
    title: str,
    destination: str,
    days: int,
    schedule: List[Dict[str, Any]],
    user_id: str = "guest_traveler"
) -> Dict[str, Any]:
    """Saves a custom planned travel itinerary to the Firestore database.

    Args:
        title: Title of the itinerary (e.g., 'Paris 4-Day Art and Gourmet Tour').
        destination: Destination city or country name.
        days: Duration in number of days.
        schedule: Daily schedule list, e.g. [{"day": 1, "morning": "...", "afternoon": "...", "evening": "..."}].
        user_id: Identifier of the user or traveler.

    Returns:
        A confirmation dict with the generated itinerary ID and status.
    """
    db = get_firestore_client()
    import re
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', f"{destination}-{days}day-{title}").strip('-').lower()
    doc_id = slug[:50]

    data = {
        "title": title,
        "destination": destination,
        "days": days,
        "schedule": schedule,
        "user_id": user_id,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    db.collection("itineraries").document(doc_id).set(data)
    return {"status": "success", "itinerary_id": doc_id, "message": f"Itinerary '{title}' successfully saved to Firestore."}


def get_saved_itinerary(itinerary_id: str) -> Dict[str, Any]:
    """Retrieves a previously saved itinerary by its ID.

    Args:
        itinerary_id: The document ID of the itinerary.

    Returns:
        The itinerary dictionary or error message if not found.
    """
    db = get_firestore_client()
    doc = db.collection("itineraries").document(itinerary_id).get()
    if doc.exists:
        return doc.to_dict()
    return {"error": f"Itinerary '{itinerary_id}' not found."}


def get_weather(query: str) -> Dict[str, Any]:
    """Fetches real-time live weather and climate conditions for any city or destination.

    Args:
        query: Destination or city name (e.g. 'Kyoto', 'Paris', 'Bali', 'Seoul').

    Returns:
        A dictionary with real-time temperature, weather description, humidity, and feels-like temperature.
    """
    import urllib.parse
    import urllib.request
    import json

    city = urllib.parse.quote(query.strip())
    url = f"https://wttr.in/{city}?format=j1"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Wanderlust-Agent/1.0"})
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode("utf-8"))
            curr = data.get("current_condition", [{}])[0]
            temp_c = curr.get("temp_C", "N/A")
            feels_c = curr.get("FeelsLikeC", "N/A")
            humidity = curr.get("humidity", "N/A")
            desc = curr.get("weatherDesc", [{}])[0].get("value", "Clear")

            return {
                "destination": query,
                "temperature_c": f"{temp_c}°C",
                "temperature_f": f"{curr.get('temp_F', 'N/A')}°F",
                "condition": desc,
                "humidity": f"{humidity}%",
                "feels_like_c": f"{feels_c}°C",
                "source": "live_wttr_in_api"
            }
    except Exception as e:
        # Graceful fallback if network is constrained
        return {
            "destination": query,
            "condition": "Pleasant and clear",
            "temperature_c": "21°C",
            "note": f"Live data temporarily unavailable ({e}), using seasonal benchmark."
        }


def get_live_exchange_rates(base_currency: str = "USD") -> Dict[str, Any]:
    """Fetches real-time live currency exchange rates from the open public exchange rate API.

    Args:
        base_currency: Base 3-letter currency code (e.g. 'USD', 'EUR', 'KRW'). Default is 'USD'.

    Returns:
        A dictionary containing live exchange rates against major travel currencies.
    """
    import os
    import json
    import urllib.request

    base = base_currency.strip().upper()
    # Check for custom API key from environment if provided, otherwise use free open public endpoint
    custom_api_key = os.getenv("EXCHANGE_RATE_API_KEY")
    if custom_api_key:
        url = f"https://v6.exchangerate-api.com/v6/{custom_api_key}/latest/{base}"
    else:
        url = f"https://open.er-api.com/v6/latest/{base}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Wanderlust-Agent/1.0"})
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode("utf-8"))
            rates = data.get("rates", {})
            return {
                "base": base,
                "rates": {
                    "USD": rates.get("USD", 1.0),
                    "KRW": rates.get("KRW", 1340.0),
                    "JPY": rates.get("JPY", 155.0),
                    "EUR": rates.get("EUR", 0.90),
                    "GBP": rates.get("GBP", 0.76),
                    "IDR": rates.get("IDR", 17900.0)
                },
                "last_updated_utc": data.get("time_last_update_utc", "Recent"),
                "source": "live_open_exchange_api"
            }
    except Exception as e:
        # Fallback to standard benchmarks if network drops
        return {
            "base": base,
            "rates": {"USD": 1.0, "KRW": 1350.0, "JPY": 150.0, "EUR": 0.92, "GBP": 0.78, "IDR": 17800.0},
            "source": "benchmark_fallback",
            "note": str(e)
        }


def calculate_trip_budget(
    destination: str,
    days: int,
    travelers: int = 1,
    currency: str = "USD"
) -> Dict[str, Any]:
    """Calculates an itemized travel budget and estimated total cost for a trip using live exchange rates.

    Args:
        destination: Name or ID of the destination (e.g. 'Kyoto', 'Paris', 'Bali', 'Barcelona').
        days: Trip duration in days (minimum 1).
        travelers: Number of travelers (default: 1).
        currency: Target display currency ('USD', 'KRW', 'JPY', 'EUR', 'GBP', 'IDR', default: 'USD').

    Returns:
        A breakdown of estimated accommodation, food/dining, activities, local transit, and total costs.
    """
    days = max(1, days)
    travelers = max(1, travelers)

    # Fetch daily base cost from Firestore catalog if available
    dest_info = get_destination_details(destination)
    if "average_daily_cost_usd" in dest_info:
        daily_base_usd = float(dest_info["average_daily_cost_usd"])
    else:
        daily_base_usd = 130.0  # reasonable fallback

    # Budget breakdown weights per person per day
    hotel_usd = round(daily_base_usd * 0.45 * days * max(1, (travelers + 1) // 2), 2)  # shared room scaling
    food_usd = round(daily_base_usd * 0.30 * days * travelers, 2)
    activities_usd = round(daily_base_usd * 0.15 * days * travelers, 2)
    transport_usd = round(daily_base_usd * 0.10 * days * travelers, 2)
    total_usd = round(hotel_usd + food_usd + activities_usd + transport_usd, 2)

    # Fetch real-time live currency exchange rate
    rate_info = get_live_exchange_rates(base_currency="USD")
    rates = rate_info.get("rates", {})
    target_currency = currency.upper()
    rate = rates.get(target_currency, 1.0)

    is_integer_currency = target_currency in ("KRW", "JPY", "IDR")

    return {
        "destination": dest_info.get("name", destination),
        "days": days,
        "travelers": travelers,
        "currency": target_currency,
        "live_exchange_rate_to_usd": rate,
        "breakdown": {
            "accommodation": round(hotel_usd * rate, 0 if is_integer_currency else 2),
            "food_and_dining": round(food_usd * rate, 0 if is_integer_currency else 2),
            "activities_and_admission": round(activities_usd * rate, 0 if is_integer_currency else 2),
            "local_transit": round(transport_usd * rate, 0 if is_integer_currency else 2),
        },
        "total_estimated_cost": round(total_usd * rate, 0 if is_integer_currency else 2),
        "total_estimated_cost_usd": total_usd,
        "daily_per_person_usd": round(daily_base_usd, 2)
    }


def geocode_address(address: str) -> Dict[str, Any]:
    """Converts a street address, city, or landmark name into geographic coordinates (lat/lng) using Google Maps Geocoding API.

    Args:
        address: The address or place to geocode (e.g. 'Eiffel Tower, Paris' or 'Kyoto Station').

    Returns:
        A dictionary with formatted address, latitude, longitude, and place_id.
    """
    import os
    import json
    import urllib.parse
    import urllib.request

    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY is not set in environment."}

    encoded_address = urllib.parse.quote(address)
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Wanderlust-Agent/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") == "OK" and data.get("results"):
                first = data["results"][0]
                loc = first.get("geometry", {}).get("location", {})
                return {
                    "query": address,
                    "formatted_address": first.get("formatted_address"),
                    "latitude": loc.get("lat"),
                    "longitude": loc.get("lng"),
                    "place_id": first.get("place_id"),
                    "status": "OK"
                }
            return {
                "query": address,
                "error": data.get("error_message") or f"Geocoding failed with status: {data.get('status')}",
                "status": data.get("status")
            }
    except Exception as e:
        return {"query": address, "error": str(e)}


def search_nearby_places(
    latitude: float,
    longitude: float,
    included_types: Optional[List[str]] = None,
    radius_meters: float = 1500.0,
    max_results: int = 5
) -> Dict[str, Any]:
    """Searches for nearby places (attractions, restaurants, cafes, hotels) around coordinates using Google Maps Places API (New).

    Args:
        latitude: The latitude coordinate of the center point.
        longitude: The longitude coordinate of the center point.
        included_types: List of place types to filter by (e.g. ['tourist_attraction'], ['restaurant'], ['cafe'], ['lodging']).
        radius_meters: Search radius in meters (default 1500m, max 50000m).
        max_results: Maximum number of places to return (default 5).

    Returns:
        A list of nearby places with display name, formatted address, location coordinates, and rating.
    """
    import os
    import json
    import urllib.request

    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY is not set in environment."}

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.rating,places.types",
        "User-Agent": "Wanderlust-Agent/1.0"
    }

    body: Dict[str, Any] = {
        "maxResultCount": min(max(1, max_results), 20),
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude
                },
                "radius": float(radius_meters)
            }
        }
    }
    if included_types:
        body["includedTypes"] = included_types

    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            places = []
            for item in data.get("places", []):
                places.append({
                    "name": item.get("displayName", {}).get("text", "Unknown"),
                    "address": item.get("formattedAddress", ""),
                    "location": item.get("location", {}),
                    "rating": item.get("rating"),
                    "types": item.get("types", [])
                })
            return {
                "center": {"latitude": latitude, "longitude": longitude},
                "count": len(places),
                "places": places
            }
    except Exception as e:
        return {"error": f"Places API call failed: {e}"}


def generate_postcard(
    prompt: str,
    tool_context: Optional[ToolContext] = None
) -> Dict[str, Any]:
    """Generates an aesthetic destination travel postcard image using gemini-3.1-flash-lite-image.

    The generated image is saved as an ADK session artifact (visible in Playground Artifacts tab)
    and uploaded to the public Cloud Storage bucket for direct browser display.

    Args:
        prompt: Description of the postcard image to generate (e.g. 'Watercolor postcard of Kyoto golden pavilion in autumn').

    Returns:
        A dictionary with the public image URL, bucket path, and status.
    """
    import base64
    import datetime
    import uuid
    from google import genai
    from google.cloud import storage

    try:
        # 1. Generate image using gemini-3.1-flash-lite-image in global location
        client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT, location="global")
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"])
        )

        image_bytes = None
        for candidate in response.candidates or []:
            for part in candidate.content.parts or []:
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    break
            if image_bytes:
                break

        if not image_bytes:
            return {"error": "No image data returned from image generation model."}

        # 2. Save artifact in ADK ToolContext (Playground Artifacts tab)
        filename = f"postcard_{uuid.uuid4().hex[:8]}.jpg"
        if tool_context:
            try:
                part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
                tool_context.save_artifact(filename=filename, artifact=part)
            except Exception as e:
                pass

        # 3. Upload to public Cloud Storage bucket
        gcs_client = storage.Client(project=FIRESTORE_PROJECT)
        bucket = gcs_client.bucket(ASSETS_BUCKET_NAME)
        blob = bucket.blob(f"postcards/{filename}")
        blob.upload_from_string(image_bytes, content_type="image/jpeg")

        public_url = f"https://storage.googleapis.com/{ASSETS_BUCKET_NAME}/postcards/{filename}"
        return {
            "status": "success",
            "prompt": prompt,
            "filename": filename,
            "public_url": public_url,
            "message": f"Generated postcard uploaded successfully: {public_url}"
        }
    except Exception as e:
        return {"error": f"Image generation failed: {e}"}


def generate_destination_video(
    prompt: str,
    duration_seconds: int = 4,
    tool_context: Optional[ToolContext] = None
) -> Dict[str, Any]:
    """Generates a short destination travel video clip using the Google Gemini/Veo video generation model (veo-3.1-lite-generate-001).

    The video bytes are uploaded to the public Cloud Storage bucket and a public HTTPS URL is returned.

    Args:
        prompt: Detailed visual prompt describing the travel video scene (e.g., 'Cinematic aerial drone shot of tropical beach with turquoise waves and palm trees').
        duration_seconds: Length of the video in seconds (supported: 4, 6, 8; default 4).

    Returns:
        A dictionary containing the public video URL, filename, status, and message.
    """
    import time
    import uuid
    from google import genai
    from google.genai import types
    from google.cloud import storage

    # Validate duration according to model spec
    if duration_seconds not in [4, 6, 8]:
        duration_seconds = 4

    try:
        # 1. Request video generation from Veo 3.1 Lite in us-central1
        client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT, location="us-central1")
        operation = client.models.generate_videos(
            model="veo-3.1-lite-generate-001",
            prompt=prompt,
            config=dict(
                aspect_ratio="16:9",
                duration_seconds=duration_seconds,
            )
        )

        # 2. Poll operation until complete (usually 15-25 seconds)
        max_attempts = 24  # up to 120s
        for _ in range(max_attempts):
            time.sleep(5)
            res = client.operations.get(operation=operation)
            if res.done:
                break

        if not res.done:
            return {"error": "Video generation timed out waiting for completion."}

        if res.error:
            return {"error": f"Video generation failed with API error: {res.error}"}

        # 3. Extract video bytes from the response
        video_bytes = None
        if hasattr(res, "response") and res.response and hasattr(res.response, "generated_videos"):
            videos = res.response.generated_videos
            if videos and len(videos) > 0:
                video_bytes = getattr(videos[0].video, "video_bytes", None)

        if not video_bytes:
            return {"error": "No video bytes found in generated video response."}

        filename = f"video_{uuid.uuid4().hex[:8]}.mp4"

        # 4. Save artifact in ADK ToolContext if present
        if tool_context:
            try:
                part = types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")
                tool_context.save_artifact(filename=filename, artifact=part)
            except Exception:
                pass

        # 5. Upload to public Cloud Storage bucket
        gcs_client = storage.Client(project=FIRESTORE_PROJECT)
        bucket = gcs_client.bucket(ASSETS_BUCKET_NAME)
        blob = bucket.blob(f"videos/{filename}")
        blob.upload_from_string(video_bytes, content_type="video/mp4")

        public_url = f"https://storage.googleapis.com/{ASSETS_BUCKET_NAME}/videos/{filename}"
        return {
            "status": "success",
            "prompt": prompt,
            "filename": filename,
            "duration_seconds": duration_seconds,
            "public_url": public_url,
            "message": f"Generated destination video uploaded successfully: {public_url}"
        }
    except Exception as e:
        return {"error": f"Destination video generation failed: {e}"}


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are Wanderlust AI, a knowledgeable and inspiring personal travel concierge. "
        "Your mission is to help travelers discover wonderful destinations and plan personalized itineraries. "
        "CRITICAL MEMORY REQUIREMENT: You MUST actively remember and strictly adhere to all of the user's allergies and dietary restrictions (e.g., peanut allergy, celiac/gluten-free, vegan, halal, lactose intolerance) across all sessions and conversations. "
        "Whenever recommending restaurants, food, activities, or travel itineraries, you must always take their remembered allergies and dietary restrictions into account to ensure their safety and comfort. "
        "You also remember general travel preferences, favorite destinations, and personal facts from previous conversations. "
        "You have direct access to a curated Firestore destination catalog and can search destinations by style or budget, "
        "look up detailed attractions and costs, check real-time live destination weather, "
        "query live currency exchange rates, calculate comprehensive trip budgets, "
        "generate aesthetic travel postcard images uploaded to Cloud Storage, "
        "generate short destination travel video clips uploaded to Cloud Storage, "
        "geocode addresses into precise coordinates using Google Maps Geocoding API, "
        "find nearby tourist attractions, restaurants, and hotels via Google Maps Places API (New), "
        "and execute Python calculations or analysis in a secure Agent Platform sandbox. "
        "Always be welcoming, structured, safety-conscious, and helpful."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="wanderlust_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    code_executor=AgentEngineSandboxCodeExecutor(
        sandbox_resource_name=SANDBOX_RESOURCE_NAME,
        agent_engine_resource_name=AGENT_ENGINE_RESOURCE
    ),
    tools=[
        PreloadMemoryTool(),
        search_destinations,
        get_destination_details,
        get_weather,
        get_live_exchange_rates,
        calculate_trip_budget,
        generate_postcard,
        generate_destination_video,
        geocode_address,
        search_nearby_places,
        save_itinerary,
        get_saved_itinerary,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
