# ---------------- app/routes.py ----------------
import os
from typing import Literal, Optional
import jwt
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from fastapi.security import (
    HTTPAuthorizationCredentials,
    OAuth2PasswordRequestForm,
    OAuth2PasswordBearer,
)
from bson import ObjectId
from uuid import uuid4

from .models import Playlist, Video, Clip, Cliplist
from .auth_models import Team, User, RegisterUser
from .auth import (
    auth_scheme_optional,
    get_password_hash,
    verify_password,
    create_access_token,
)
from .db import db
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
):  # This line enables Swagger auth
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# APIRouter
router = APIRouter()


# Utility functions
def convert_objectid(data):
    if isinstance(data, list):
        return [convert_objectid(item) for item in data]
    elif isinstance(data, dict):
        return {key: convert_objectid(value) for key, value in data.items()}
    elif isinstance(data, ObjectId):
        return str(data)
    else:
        return data


async def get_playlist_by_name(name: str):
    return await db.playlists.find_one({"name": name})


async def get_all_playlists() -> list:
    playlists = await db.playlists.find().to_list(length=None)
    return playlists

# Get all playlists where the given id is the direct owner
async def get_playlist_by_owner(id: str) -> list:
    return await db.playlists.find({"owner_id": ObjectId(id)}).to_list(length=None)


async def get_playlist_by_member(user_id: str) -> list:
    user_oid = ObjectId(user_id)

    # Find all teams where this user is a member
    teams = await db.teams.find({"member_ids": user_oid}).to_list(length=None)
    team_ids = [team["_id"] for team in teams]

    # Find all playlists that belong to the team(s) the user is a member of
    return await db.playlists.find({
        "team_id": {"$in": team_ids}
    }).to_list(length=None)


async def get_playlists_for_user(user_id: str) -> list:
    owned = await get_playlist_by_owner(user_id)
    member = await get_playlist_by_member(user_id)
    filtered_member = [p for p in member if p["_id"] not in {pl["_id"] for pl in owned}]
    return {"owned": owned, "member": filtered_member}


async def get_video_by_id(playlist_name: str, video_id: str):
    return await db.playlists.find_one(
        {"name": playlist_name, "videos.video_id": video_id}
    )


async def insert_playlist(playlist: Playlist):
    await db.playlists.insert_one(playlist.dict())


async def insert_video(playlist_name: str, video: Video):
    await db.playlists.update_one(
        {"name": playlist_name}, {"$push": {"videos": video.dict()}}
    )


async def insert_clip(playlist_name: str, video_id: str, clip: Clip):
    await db.playlists.update_one(
        {"name": playlist_name, "videos.video_id": video_id},
        {"$push": {"videos.$.clips": clip.dict()}},
    )

async def get_cliplist_by_id(cliplist_id: str) -> dict:
    return await db.cliplists.find_one({"_id": cliplist_id})

async def insert_cliplist(cliplist: Cliplist):
    await db.cliplists.insert_one(cliplist.dict(by_alias=True))

async def update_cliplist(cliplist_id: str, cliplist_data: dict):
    await db.cliplists.update_one({"_id": cliplist_id}, {"$set": cliplist_data})

# ---------------- Cliplist Routes ----------------

@router.get("/cliplists")
async def get_cliplists(_: HTTPAuthorizationCredentials = Depends(auth_scheme_optional)):
    return convert_objectid(await db.cliplists.find().to_list(length=None))


@router.get("/cliplist/{cliplist_id}")
async def get_cliplist(
    cliplist_id: str,
    _: HTTPAuthorizationCredentials = Depends(auth_scheme_optional)
):
    cliplist = await get_cliplist_by_id(cliplist_id)
    if not cliplist:
        raise HTTPException(status_code=404, detail="Cliplist not found.")
    return convert_objectid(cliplist)


@router.post("/cliplist")
async def create_cliplist(
    cliplist: Cliplist,
    user=Depends(get_current_user),
):
    cliplist.owner_id = user["_id"]
    await insert_cliplist(cliplist)
    return {"msg": "Cliplist created successfully"}


@router.put("/cliplist/{cliplist_id}")
async def update_cliplist_filters(
    cliplist_id: str,
    cliplist: Cliplist,
    user=Depends(get_current_user),
):
    existing = await get_cliplist_by_id(cliplist_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Cliplist not found.")

    if existing.get("owner_id") != user["_id"]:
        raise HTTPException(status_code=403, detail="Access denied to update this cliplist.")

    await update_cliplist(cliplist_id, cliplist.dict(exclude={"id", "owner_id"}))
    return {"msg": "Cliplist updated successfully"}


# auth Routes
@router.post("/auth/register")
async def register(user_data: RegisterUser):
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed = get_password_hash(user_data.password)

    user = User(
        username=user_data.username, email=user_data.email, hashed_password=hashed
    )

    result = await db.users.insert_one(user.dict(by_alias=True))
    token = create_access_token({"sub": str(result.inserted_id)})
    return {"access_token": token, "id": str(result.inserted_id), "email": user.email, "username": user.username}


@router.get("/users")
async def get_users(
    _: HTTPAuthorizationCredentials = Depends(auth_scheme_optional),
):
    projection = {"_id": 1, "username": 1, "team_ids": 1}
    users = await db.users.find({}, projection).to_list(length=None)
    return convert_objectid(users)


@router.post("/auth/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await db.users.find_one(
        {"email": form_data.username}
    )  # TODO: check username or email?
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    token = create_access_token({"sub": str(user["_id"])})
    return {"access_token": token, "id": str(user["_id"]), "email": user["email"], "username": user["username"]}


# book keeping
async def get_teams_owned_by(user_id: str) -> list:
    return await db.teams.find({"owner_id": ObjectId(user_id)}).to_list(length=None)

async def get_teams_member_of(user_id: str) -> list:
    return await db.teams.find({"member_ids": ObjectId(user_id)}).to_list(length=None)

async def get_teams_for_user(user_id: str) -> dict:
    owned = await get_teams_owned_by(user_id)
    member = await get_teams_member_of(user_id)
    filtered_member = [team for team in member if team["_id"] not in {t["_id"] for t in owned}]
    return {"owned": owned, "member": filtered_member}

@router.get("/teams")
async def get_teams(
    user_id: Optional[str] = Query(None),
    filter: Literal["owned", "member", "all"] = "all",
    _: HTTPAuthorizationCredentials = Depends(auth_scheme_optional),
):
    if user_id:
        if filter == "owned":
            teams = await get_teams_owned_by(user_id)
        elif filter == "member":
            teams = await get_teams_member_of(user_id)
        else:  # filter == "all"
            teams = await get_teams_for_user(user_id)
    else:
        teams = await db.teams.find().to_list(length=None)
    return convert_objectid(teams)


@router.post("/teams")
async def create_team(team: Team, user=Depends(get_current_user)):
    # Default owner_id to authenticated user
    team.owner_id = user["_id"]
    team.member_ids = [user["_id"]]
    result = await db.teams.insert_one(team.dict(by_alias=True))
    await db.users.update_one(
        {"_id": user["_id"]}, {"$push": {"team_ids": result.inserted_id}}
    )
    return {"id": str(result.inserted_id)}


@router.post("/teams/{team_id}/add_user/{user_id}")
async def add_user_to_team(team_id: str, user_id: str, user=Depends(get_current_user)):
    # TODO: Check if the user is already in the team? or doesnt matter
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if team["owner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only owner can add members")

    await db.teams.update_one(
        {"_id": ObjectId(team_id)}, {"$addToSet": {"member_ids": ObjectId(user_id)}}
    )
    await db.users.update_one(
        {"_id": ObjectId(user_id)}, {"$addToSet": {"team_ids": ObjectId(team_id)}}
    )
    return {"msg": "User added to team"}


@router.get("/teams/{team_id}/members")
async def get_team_members(team_id: str, user=Depends(get_current_user)):
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if user["_id"] not in team["member_ids"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    members = await db.users.find({"_id": {"$in": team["member_ids"]}}).to_list(
        length=None
    )
    return [
        {"id": str(m["_id"]), "email": m["email"], "username": m["username"]}
        for m in members
    ]


# playlist
@router.get("/playlists")
async def get_playlists(
    user_id: Optional[str] = Query(None),
    filter: Literal["owned", "member", "all"] = "all",
    token: HTTPAuthorizationCredentials = Depends(auth_scheme_optional),
):
    if user_id:
        # TODO: get rid of this query functionality in the api, and use the filter in the frontend instead
        # TODO: owned and member filters are not tested, and are inconsistent with all's response
        if filter == "owned":
            playlists = await get_playlist_by_owner(user_id)
        elif filter == "member":
            playlists = await get_playlist_by_member(user_id)
        else:  # filter == "all"
            playlists = await get_playlists_for_user(user_id)
    else:
        playlists = await get_all_playlists()
    return convert_objectid(playlists)


@router.post("/playlists")
async def create_playlist(playlist: Playlist, user=Depends(get_current_user)):
    existing_playlist = await get_playlist_by_name(playlist.name)
    if existing_playlist:
        raise HTTPException(status_code=400, detail="Playlist already exists.")

    playlist_dict = playlist.dict(by_alias=True)

    # Default owner_id to authenticated user
    if not playlist.owner_id:
        playlist_dict["owner_id"] = user["_id"]

    await db.playlists.insert_one(playlist_dict)
    return {"msg": "Playlist created successfully!"}


@router.get("/playlists/{playlist_name}")
async def get_playlist(
    playlist_name: str,
    _: HTTPAuthorizationCredentials = Depends(auth_scheme_optional),
):
    playlist = await get_playlist_by_name(playlist_name)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found.")
    return convert_objectid(playlist)


@router.post("/playlists/{playlist_name}/videos")
async def create_video(
    playlist_name: str, video: Video, user=Depends(get_current_user)
):

    playlist = await get_playlist_by_name(playlist_name)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found.")

    if not playlist["owner_id"] == user["_id"]:
        raise HTTPException(status_code=403, detail="Access denied to this playlist.")

    existing_video = await get_video_by_id(playlist_name, video.video_id)
    if existing_video:
        raise HTTPException(status_code=400, detail="Video already exists.")

    await insert_video(playlist_name, video)
    return {
        "msg": "Video added to playlist!"
    }  # TODO: return video object or something?


@router.post("/playlists/{playlist_name}/videos/{video_id}/clips")
async def create_clip(
    playlist_name: str, video_id: str, clip: Clip, user=Depends(get_current_user)
):
    playlist = await get_playlist_by_name(playlist_name)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found.")
    if not playlist["owner_id"] == user["_id"]:
        raise HTTPException(status_code=403, detail="Access denied to this playlist.")

    video = await get_video_by_id(playlist_name, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")

    if not clip.clip_id:
        clip.clip_id = str(uuid4())

    await insert_clip(playlist_name, video_id, clip)
    return {"msg": "Clip added to video!"}


@router.put("/playlists/{playlist_name}/videos")
async def update_video(
    playlist_name: str, updated_video: Video, user=Depends(get_current_user)
):
    playlist = await get_playlist_by_name(playlist_name)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found.")

    # Extend access: allow playlist owner OR users from the team with access
    is_owner = playlist["owner_id"] == user["_id"]
    user_team_ids = set(user.get("team_ids", []))
    playlist_team_id = playlist.get("team_id")
    is_team_member = playlist_team_id in user_team_ids

    if not (is_owner or is_team_member):
        raise HTTPException(status_code=403, detail="Access denied to this playlist.")

    videos = playlist.get("videos", [])
    for i, video in enumerate(videos):
        if video["video_id"] == updated_video.video_id:
            updated_data = updated_video.dict()
            updated_data["video_id"] = video.get("video_id")
            updated_data["youtube_url"] = video.get("youtube_url")
            updated_data["date"] = video.get("date")
            updated_data["title"] = video.get("title")
            updated_data["duration_seconds"] = video.get("duration_seconds")
            updated_data["added_date"] = video.get("added_date")
            videos[i] = updated_data

            await db.playlists.update_one(
                {"name": playlist_name}, {"$set": {"videos": videos}}
            )
            return {"msg": "Video updated successfully!"}

    raise HTTPException(status_code=404, detail="Video not found in playlist.")


@router.put("/playlists/{playlist_name}/assign-team")
async def assign_playlist_to_team(
    playlist_name: str, team_id: str, user=Depends(get_current_user)
):
    user_id = user["_id"]

    # 1. Check if playlist exists and is owned by the user
    playlist = await get_playlist_by_name(playlist_name)
    if not playlist:
        raise HTTPException(
            status_code=404, detail="Playlist not found or not owned by user."
        )
    if not playlist["owner_id"] == user_id:
        raise HTTPException(status_code=403, detail="Access denied to this playlist.")

    # 2. Check if the team exists and user is a member
    team = await db.teams.find_one({"_id": ObjectId(team_id), "member_ids": user_id})
    if not team:
        raise HTTPException(status_code=403, detail="User not a member of this team.")

    # 3. Assign playlist to team
    await db.playlists.update_one(
        {"name": playlist_name}, {"$set": {"team_id": ObjectId(team_id)}}
    )

    return {"msg": "Playlist assigned to team successfully."}


@router.put("/playlists/{playlist_name}/videos/{video_id}/clips")
async def update_clip(
    playlist_name: str,
    video_id: str,
    clip: Clip = Body(...),
    user=Depends(get_current_user)
):
    playlist = await get_playlist_by_name(playlist_name)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found.")
    if not playlist["owner_id"] == user["_id"]:
        raise HTTPException(status_code=403, detail="Access denied to this playlist.")

    video = await get_video_by_id(playlist_name, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")

    # Find and update the clip by title and start time (or use a unique id if you have one)
    updated = False
    for v in playlist.get("videos", []):
        if v["video_id"] == video_id:
            for i, c in enumerate(v.get("clips", [])):
                # You can use a better unique identifier if available
                if c.get("clip_id") == clip.clip_id:
                    v["clips"][i] = clip.dict()
                    updated = True
                    break
            if not updated:
                raise HTTPException(status_code=404, detail="Clip not found.")
            break

    if not updated:
        raise HTTPException(status_code=404, detail="Clip not found.")

    await db.playlists.update_one(
        {"name": playlist_name},
        {"$set": {"videos": playlist["videos"]}}
    )
    return {"msg": "Clip updated successfully!"}
