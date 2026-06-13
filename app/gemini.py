import os
import google.generativeai as genai

_client: genai.GenerativeModel | None = None


def _get_client() -> genai.GenerativeModel:
    global _client
    if _client is None:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
        _client = genai.GenerativeModel("gemini-1.5-flash")
    return _client


def get_recommendations(watched_titles: list[str]) -> str:
    if not watched_titles:
        return "Add some movies or shows to your library first."
    titles = ", ".join(watched_titles[:20])
    prompt = (
        f"Based on these movies/TV shows I've watched: {titles}\n\n"
        "Recommend 10 movies or TV shows I might enjoy. "
        "For each, give the title, year, and a one-sentence reason why I'd like it. "
        "Format as a numbered list."
    )
    model = _get_client()
    response = model.generate_content(prompt)
    return response.text
