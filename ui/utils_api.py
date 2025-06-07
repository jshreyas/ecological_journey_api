import os
import re
import requests
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from cache import cache_del, cache_get, cache_set
from utils import format_time
load_dotenv()

BASE_URL = os.getenv("BACKEND_URL")
_playlists_cache = None  # file-level in-memory cache

def get_headers(token: Optional[str] = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def api_get(endpoint: str, token: Optional[str] = None):
    url = f"{BASE_URL}{endpoint}"
    response = requests.get(url, headers=get_headers(token))
    response.raise_for_status()
    return response.json()

def api_post(endpoint: str, data: dict, token: Optional[str] = None):
    url = f"{BASE_URL}{endpoint}"
    response = requests.post(url, json=data, headers=get_headers(token))
    response.raise_for_status()
    return response.json()

def api_put(endpoint: str, data: dict, token: Optional[str] = None):
    url = f"{BASE_URL}{endpoint}"
    response = requests.put(url, json=data, headers=get_headers(token))
    response.raise_for_status()
    return response.json()

def create_team(name, token, user_id):
    cache_key = f"teams_user_{user_id}"
    response = api_post("/teams", data={"name": name}, token=token)
    # Refresh cache for this user
    teams_get = api_get(f"/teams?user_id={user_id}")
    cache_set(cache_key, teams_get)
    return response

def fetch_teams_for_user(user_id: str) -> List[Dict[str, Any]]:
    cache_key = f"teams_user_{user_id}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    response = api_get(f"/teams?user_id={user_id}")
    cache_set(cache_key, response)
    return response

def create_playlist(video_data, token, name, playlist_id):
    response = api_post("/playlists", data={"name": name, "playlist_id": playlist_id}, token=token)
    #TODO: combine all these individual API calls to a single call
    create_video(video_data, token, name)
    #TODO: please do error handling
    _refresh_playlists_cache()
    return response

def create_video(video_data, token, name):
    for video in video_data:
        response = api_post(f"/playlists/{name}/videos", data=video, token=token)
    _refresh_playlists_cache()

def load_playlists() -> List[Dict[str, Any]]:
    global _playlists_cache
    if _playlists_cache is not None:
        return _playlists_cache
    cache_key = "playlists"
    cached = cache_get(cache_key)
    if cached:
        _playlists_cache = cached
        return cached
    data = api_get("/playlists")
    cache_set(cache_key, data)
    _playlists_cache = data
    return data

def load_playlists_for_user(user_id: str, filter: str = "all") -> Dict[str, List[Dict[str, Any]]]:
    playlists = load_playlists()
    teams = fetch_teams_for_user(user_id)
    # Combine all teams if teams is a dict (API returns {'owned': [], 'member': []})
    if isinstance(teams, dict):
        all_teams = (teams.get('owned', []) or []) + (teams.get('member', []) or [])
    else:
        all_teams = teams or []
    user_team_ids = {team.get("_id") for team in all_teams if user_id in team.get("member_ids", [])}

    owned = [pl for pl in playlists if pl.get("owner_id") == user_id]
    member = [
        pl for pl in playlists
        if pl.get("owner_id") != user_id and pl.get("team_id") in user_team_ids
    ]
    # Remove duplicates by _id
    owned_ids = {pl["_id"] for pl in owned}
    filtered_member = [pl for pl in member if pl["_id"] not in owned_ids]

    if filter == "owned":
        return {"owned": owned, "member": []}
    elif filter == "member":
        return {"owned": [], "member": filtered_member}
    else:  # "all"
        return {"owned": owned, "member": filtered_member}

def _refresh_playlists_cache():
    """Force refresh playlists from backend and update both Redis and in-memory cache."""
    global _playlists_cache
    playlists = api_get("/playlists")
    cache_set("playlists", playlists)
    _playlists_cache = playlists

def format_duration(seconds: int) -> str:
    """Convert seconds into a human-readable format (HH:MM:SS or MM:SS)."""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"  # HH:MM:SS
    return f"{int(minutes):02}:{int(seconds):02}"  # MM:SS

def load_videos(playlist_id: Optional[str] = None, response_dict=False) -> List[Dict[str, Any]]:
    playlists = load_playlists()
    videos = []
    for playlist in playlists:
        if playlist_id is None or playlist.get("_id") == playlist_id:
            for video in playlist.get("videos", []):
                video["playlist_id"] = playlist.get("_id")
                video["playlist_name"] = playlist.get("name")
                # Add human-readable duration to each video
                video["duration_human"] = format_duration(video.get("duration_seconds", 0))
                videos.append(video)
    videos.sort(key=lambda x: x.get("date", ""), reverse=True)
    if response_dict:
        return {video["video_id"]: video for video in videos if "video_id" in video}
    return videos

def load_video(video_id: str) -> Optional[Dict[str, Any]]:
    """Return a single video dict by video_id, or None if not found."""
    videos = load_videos(response_dict=True)
    return videos.get(video_id)

def get_playlist_id_for_video(video_id: str) -> Optional[str]:
    playlists = load_playlists()
    for playlist in playlists:
        for video in playlist.get("videos", []):
            if video.get("video_id") == video_id:
                return playlist.get("name") # TODO: Fix usage of playlist name vs id
    return None

def load_clips() -> List[Dict[str, Any]]:
    clips = []
    playlists = load_playlists()
    for playlist in playlists:
        for video in playlist.get("videos", []):
            if video.get("clips", []):
                for clip in video["clips"]:
                    partners = (clip.get("partners") or []) + (video.get("partners") or [])
                    labels = (clip.get("labels") or []) + (video.get("labels") or [])
                    clip_data = {
                        "video_id": video["video_id"],
                        "playlist_id": playlist["_id"],
                        "playlist_name": playlist["name"],
                        "start": clip.get("start", 0),
                        "end": clip.get("end", 0),
                        "title": clip.get("title", ""),
                        "date": video.get("date", ""),
                        "duration_human": format_duration(clip.get("end", 0) - clip.get("start", 0)),
                        "description": clip.get("description", ""),
                        "partners": partners,
                        "labels": labels,
                        "type": clip.get("type", "clip"),
                        "clip_id": clip.get("clip_id", "")
                    }
                    clips.append(clip_data)
    clips.sort(key=lambda x: x.get("date", ""), reverse=True)
    return clips

def convert_clips_to_raw_text(video_id: str, video_duration: Optional[int] = None) -> str:
    videos = load_videos()
    video_metadata = next((v for v in videos if v["video_id"] == video_id), {})
    clips = video_metadata.get("clips", [])
    duration = video_duration or video_metadata.get("duration_seconds")

    lines = []

    has_metadata = any(video_metadata.get(k) for k in ["partners", "labels", "type", "notes"])
    has_clips = bool(clips)

    if has_metadata:
        if video_metadata.get("partners"):
            lines.append(" ".join(f"@{p}" for p in video_metadata["partners"]))
        if video_metadata.get("labels"):
            lines.append(" ".join(f"#{l}" for l in video_metadata["labels"]))
        if video_metadata.get("type"):
            lines.append(f"type: {video_metadata['type']}")
        if video_metadata.get("notes"):
            lines.append(f"notes: {video_metadata['notes']}")
        lines.append("")
    else:
        lines += [
            "@partner1 @partner2 #position1 #position2",
            "type: positional/sparring/rolling/instructional",
            "notes: optional general notes about this video",
            ""
        ]

    if not has_clips and duration:
        lines.append("00:00 - 00:30 | Clip Title Here | Optional description here @partner1 @partner2 #label1 #label2")
        clips = [{
            "start": 0,
            "end": duration,
            "type": "autogen"
        }]

    for clip in clips:
        start = clip.get("start", 0)
        end = clip.get("end", 0)
        if duration and end > duration:
            end = duration

        if clip.get("type") != "clip":
            lines.append(f"{format_time(start)} - {format_time(end)} | Full video | @autogen")
            continue

        title = clip.get("title", "")
        description = clip.get("description", "")
        partners = " ".join(f"@{p}" for p in clip.get("partners", []))
        labels = " ".join(f"#{l}" for l in clip.get("labels", []))
        full_desc = " ".join(part for part in [description, partners, labels] if part)

        lines.append(f"{format_time(start)} - {format_time(end)} | {title} | {full_desc}")
    return "\n".join(lines)

def parse_clip_line(line: str) -> Optional[Dict[str, Any]]:
    try:
        if "Clip Title Here" in line or "@autogen" in line:
            return None

        import re
        match = re.match(r'(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*\|\s*([^|]+)\s*(?:\|\s*(.*))?', line)
        if not match:
            return None
        start_str, end_str, title, full_desc = match.groups()

        def to_seconds(t: str) -> int:
            minutes, seconds = map(int, t.strip().split(":"))
            return minutes * 60 + seconds

        full_desc = full_desc or ""
        partners = re.findall(r'@(\w+)', full_desc)
        labels = re.findall(r'#(\w+)', full_desc)
        description = re.sub(r'[@#]\w+', '', full_desc).strip()

        return {
            "start": to_seconds(start_str),
            "end": to_seconds(end_str),
            "title": title.strip(),
            "description": description,
            "type": "clip",
            "partners": partners,
            "labels": labels
        }
    except Exception:
        return None

def parse_raw_text(raw_text: str) -> Dict[str, Any]:
    video_data = {
        "partners": [],
        "labels": [],
        "type": "",
        "notes": "",
        "clips": [],
        "youtube_url": "",
        "date": "",
        "title": "",
        "duration_seconds": 0.0
    }

    for line in raw_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        tokens = line.split()
        if all(token.startswith('@') or token.startswith('#') for token in tokens):
            for token in tokens:
                if token.startswith("@"):
                    video_data["partners"].append(token[1:].strip())
                elif token.startswith("#"):
                    video_data["labels"].append(token[1:].strip())
        elif line.lower().startswith("type:"):
            video_data["type"] = line.split(":", 1)[1].strip()
        elif line.lower().startswith("notes:"):
            video_data["notes"] = line.split(":", 1)[1].strip()
        elif re.match(r'\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}', line):
            clip = parse_clip_line(line)
            if clip:
                video_data["clips"].append(clip)

    return video_data

def save_video_data_clips(video_data: Dict[str, Any], token) -> bool:
    playlist_name = get_playlist_id_for_video(video_data.get("video_id"))
    if not playlist_name:
        print(f"Could not find playlist for video_id: {video_data.get('video_id')}")
        return False
    try:
        api_put(f"/playlists/{playlist_name}/videos", data=video_data, token=token)
        _refresh_playlists_cache()
        return True
    except requests.HTTPError as e:
        print(f"Failed to save video data: {e}")
        #TODO: if not successful, display reason in ui?
        return False

def parse_and_save_clips(video_id: str, raw_text: str, token):
    video_data = parse_raw_text(raw_text)
    video_data["video_id"] = video_id
    return save_video_data_clips(video_data, token)

def get_all_partners() -> List[str]:
    cache_key = "all_partners"
    cached = cache_get(cache_key)
    if cached:
        return cached
    partners_set = set()
    videos = load_videos()
    for video in videos:
        video_partners = video.get("partners", [])
        partners_set.update(video_partners)
        clips = video.get("clips", [])
        for clip in clips:
            if clip.get("type") == "clip":
                partners_set.update(clip.get("partners", []))
    result = sorted(partners_set)
    cache_set(cache_key, result)
    return result

def find_clips_by_partner(partner: str) -> List[Dict[str, Any]]:
    result = []
    videos = load_videos()
    for video in videos:
        video_id = video["video_id"]
        video_partners = video.get("partners", [])
        clips = video.get("clips", [])
        for clip in clips:
            clip_partners = clip.get("partners", [])
            if partner in clip_partners or partner in video_partners:
                merged_labels = list(set(video.get("labels", []) + clip.get("labels", [])))
                combined = {
                    "video_id": video_id,
                    **video,
                    **clip,
                    "labels": merged_labels
                }
                result.append(combined)
    return result

def add_clip_to_video(playlist_name: str, video_id: str, clip: dict, token: str):
    """Add a single clip to a video in a playlist."""
    endpoint = f"/playlists/{playlist_name}/videos/{video_id}/clips"
    result = api_post(endpoint, data=clip, token=token)
    _refresh_playlists_cache()
    return result

def update_clip_in_video(playlist_name: str, video_id: str, clip: dict, token: str):
    """Update a single clip in a video in a playlist."""
    endpoint = f"/playlists/{playlist_name}/videos/{video_id}/clips"
    result = api_put(endpoint, data=clip, token=token)
    _refresh_playlists_cache()
    return result

def convert_video_metadata_to_raw_text(video: dict) -> str:
    partners_line = " ".join(f"@{p}" for p in video.get("partners", []))
    labels_line = " ".join(f"#{l}" for l in video.get("labels", []))
    notes = video.get("notes", "")
    return "\n".join(filter(None, [partners_line, labels_line, notes]))

def save_video_metadata(video_metadata: dict, token: str) -> bool:
    playlist_name = get_playlist_id_for_video(video_metadata.get("video_id"))
    if not playlist_name:
        print(f"Could not find playlist for video_id: {video_metadata.get('video_id')}")
        return False
    try:
        reponse = api_put(f"/playlists/{playlist_name}/videos", data=video_metadata, token=token)
        _refresh_playlists_cache()
        return True
    except Exception as e:
        print(f"Failed to save video metadata: {e}")
        return False

def load_cliplist(cliplist_id: str=None):
    if not cliplist_id:
        return api_get("/cliplists")
    return api_get(f"/cliplist/{cliplist_id}")

def save_cliplist(name, filters_state, token):
    data = {
        "name": name,
        "filters": filters_state,
        # "clip_ids": filtered_clips
    }
    import pdb; pdb.set_trace()  # Debugging breakpoint
    try:
        response = api_post("/cliplist", data=data, token=token)
        return response
    except requests.HTTPError as e:
        print(f"Failed to save cliplist: {e}")
        return None