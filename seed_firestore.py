#!/usr/bin/env python3
"""Seed script for Wanderlust AI travel database."""

from google.cloud import firestore

# IMPORTANT: Pin the exact project ID as a string constant to prevent 404s in Agent Engine / Vertex AI
FIRESTORE_PROJECT = "qwiklabs-gcp-03-f9a25ebb0655"

def seed():
    print(f"Connecting to Firestore for project: {FIRESTORE_PROJECT}")
    db = firestore.Client(project=FIRESTORE_PROJECT)

    # 1. Destinations Catalog
    destinations = [
        {
            "id": "kyoto-japan",
            "name": "Kyoto",
            "country": "Japan",
            "style": ["culture", "foodie", "relaxation"],
            "budget_tier": "medium",
            "summary": "Ancient temples, traditional tea houses, beautiful bamboo groves, and incredible culinary heritage.",
            "best_seasons": ["Spring", "Autumn"],
            "top_attractions": ["Fushimi Inari Taisha", "Kinkaku-ji", "Arashiyama Bamboo Grove", "Gion District"],
            "average_daily_cost_usd": 120
        },
        {
            "id": "paris-france",
            "name": "Paris",
            "country": "France",
            "style": ["culture", "romance", "foodie", "art"],
            "budget_tier": "high",
            "summary": "The City of Light known for world-class museums, iconic architecture, cafes, and haute cuisine.",
            "best_seasons": ["Spring", "Autumn"],
            "top_attractions": ["Eiffel Tower", "Louvre Museum", "Montmartre", "Musée d'Orsay"],
            "average_daily_cost_usd": 220
        },
        {
            "id": "bali-indonesia",
            "name": "Bali",
            "country": "Indonesia",
            "style": ["relaxation", "adventure", "nature", "wellness"],
            "budget_tier": "low",
            "summary": "Tropical island paradise with lush terraces, spiritual temples, surf beaches, and yoga retreats.",
            "best_seasons": ["Summer", "Spring"],
            "top_attractions": ["Ubud Monkey Forest", "Uluwatu Temple", "Tegallalang Rice Terrace", "Canggu Beach"],
            "average_daily_cost_usd": 65
        },
        {
            "id": "reykjavik-iceland",
            "name": "Reykjavik",
            "country": "Iceland",
            "style": ["adventure", "nature"],
            "budget_tier": "high",
            "summary": "Gateway to geothermal wonders, cascading waterfalls, volcanic landscapes, and Northern Lights.",
            "best_seasons": ["Winter", "Summer"],
            "top_attractions": ["Blue Lagoon", "Golden Circle", "Hallgrimskirkja", "South Coast Waterfalls"],
            "average_daily_cost_usd": 250
        },
        {
            "id": "barcelona-spain",
            "name": "Barcelona",
            "country": "Spain",
            "style": ["culture", "foodie", "beach", "nightlife"],
            "budget_tier": "medium",
            "summary": "Vibrant Catalan capital renowned for Gaudí architecture, tapas bars, and Mediterranean beaches.",
            "best_seasons": ["Spring", "Autumn", "Summer"],
            "top_attractions": ["Sagrada Família", "Park Güell", "Gothic Quarter", "La Boqueria Market"],
            "average_daily_cost_usd": 140
        }
    ]

    for dest in destinations:
        doc_id = dest["id"]
        db.collection("destinations").document(doc_id).set(dest)
        print(f"  ✓ Seeded destination: {dest['name']} ({doc_id})")

    # 2. Sample Itinerary
    sample_itinerary = {
        "title": "Kyoto 3-Day Cultural & Foodie Getaway",
        "destination": "Kyoto",
        "days": 3,
        "style": "culture & foodie",
        "schedule": [
            {"day": 1, "morning": "Fushimi Inari 10,000 torii gates hike", "afternoon": "Kiyomizu-dera temple exploration", "evening": "Gion evening walk & Kaiseki dinner"},
            {"day": 2, "morning": "Arashiyama Bamboo Grove & Tenryu-ji", "afternoon": "Monkey Park & Sagano Romantic Train", "evening": "Pontocho Alley dinner by the river"},
            {"day": 3, "morning": "Kinkaku-ji (Golden Pavilion)", "afternoon": "Nishiki Market food tour", "evening": "Traditional matcha tea ceremony"}
        ],
        "created_by": "sample_user"
    }
    db.collection("itineraries").document("kyoto-3day-sample").set(sample_itinerary)
    print("  ✓ Seeded sample itinerary: kyoto-3day-sample")

    print("\n✅ Firestore seeding completed successfully!")

if __name__ == "__main__":
    seed()
