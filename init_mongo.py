import os
import requests
from ui.fetch_videos import fetch_playlist_items
from dotenv import load_dotenv


load_dotenv()
USER_PW = os.getenv("USER_PW")
if not USER_PW:
    raise ValueError("Missing USER_PW in environment variables")

BASE_URL = "http://localhost:8000"  # Change to your server URL

# Sample user credentials
USER = {
    "username": "shreyas",
    "email": "shreyas.jukanti@gmail.com",
    "password": USER_PW
}

# Register the user
def register_user():
    url = f"{BASE_URL}/auth/register"
    response = requests.post(url, json=USER)
    print("Register:", response.status_code, response.json())
    return response.ok

# Login and get token
def login_user():
    url = f"{BASE_URL}/auth/token"
    data = {
        "username": USER["email"],
        "password": USER["password"]
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=data, headers=headers)
    print("Login:", response.status_code, response.json())
    return response.json()["access_token"]

# Create a playlist
def create_playlist(token, name="Grappling Journal"): #TODO: dynamically pull this name
    url = f"{BASE_URL}/playlists"
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "name": name
    }
    response = requests.post(url, json=data, headers=headers)
    print("Create Playlist:", response.status_code, response.json())
    return name

# Create a team
def create_team(token, name="Mat Lab"):
    url = f"{BASE_URL}/teams"
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "name": name
    }
    response = requests.post(url, json=data, headers=headers)
    print("Create Team:", response.status_code, response.json())
    return response.json()["id"]

# Assign the playlist to the team
def assign_playlist_to_team(token, playlist_name, team_id):
    url = f"{BASE_URL}/playlists/{playlist_name}/assign-team"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"team_id": team_id}
    response = requests.put(url, headers=headers, params=params)
    print("Assign Playlist:", response.status_code, response.json())

def upload_video_to_playlist(token, playlist_name, video):
    url = f"{BASE_URL}/playlists/{playlist_name}/videos"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    response = requests.post(url, headers=headers, json=video)

    if not response.ok:
        print(f"Failed to upload video {video['video_id']}: {response.text}")
    else:
        print(f"Uploaded {video['video_id']}")


def main():
    register_user()
    token = login_user()
    team_id = create_team(token)
    playlist_name = create_playlist(token)

    PLAYLIST_ID = "PLHXvJ_QLQWhXuOo2HcwsL4sysM79x8Id8" # Grappling Journal
    # PLAYLIST_ID = "PLHXvJ_QLQWhWfwGejBdQE8LjHHToMMCge" # Home Training Journal

    assign_playlist_to_team(token, playlist_name, team_id)

    raw_videos = fetch_playlist_items(PLAYLIST_ID)

    parsed_videos = []
    for v in raw_videos:
        parsed_videos.append({
            "title": v["title"],
            "video_id": v["video_id"],
            "youtube_url": v["url"],
            "date": v["published_at"],
            "duration_seconds": v.get("duration_seconds", None),  # Add duration data here
            "type": "",
            "partners": [],
            "positions": [],
            "notes": "",
            "labels": [],
            "clips": []
        })

    for video in parsed_videos:
        upload_video_to_playlist(token, playlist_name, video)

#TODO: removed this, also check this file if its working as expected with all the changes
if __name__ == "__main__":
    main()
