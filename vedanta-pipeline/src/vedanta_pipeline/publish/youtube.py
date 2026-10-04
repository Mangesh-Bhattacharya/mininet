"""YouTube publisher (Data API v3). Imports Google libs lazily so the rest of the pipeline
runs without them. Quota costs (default 10,000/day): broadcast insert 50, bind 50,
thumbnail 50, videos.update 50, playlistItems.insert 50 -> ~250 per event.

Never logs or stores the ingestion/stream key. Requires a one-time interactive OAuth
(`vedanta auth`) on a machine with a browser; the 0600 token file is then used headless.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..agents import security
from ..config import Config
from ..models import PackageStatus, Visibility, YouTubePackage

SCOPES = ["https://www.googleapis.com/auth/youtube"]


class YouTubePublisher:
    def __init__(self, cfg: Config, client_secret: Path, token_path: Path):
        self.cfg, self.client_secret, self.token_path = cfg, client_secret, token_path
        self._yt: Any = None

    # ---- auth -------------------------------------------------------------------------
    def authorize(self, interactive: bool = False) -> None:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        problems = [f for f in security.check_credentials(self.token_path, SCOPES) if f.severity == "block"]
        if problems:
            raise PermissionError("; ".join(p.detail for p in problems))
        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        if not creds or not creds.valid:
            if not interactive:
                raise PermissionError("no valid token; run `vedanta auth` interactively first")
            creds = InstalledAppFlow.from_client_secrets_file(str(self.client_secret), SCOPES).run_local_server(port=0)
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(creds.to_json())
        self.token_path.chmod(0o600)
        self._yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    # ---- operations -------------------------------------------------------------------
    def _playlist_id(self, title: str) -> str:
        yt = self._yt
        for item in yt.playlists().list(part="snippet", mine=True, maxResults=50).execute().get("items", []):
            if item["snippet"]["title"] == title:
                return item["id"]
        body = {"snippet": {"title": title}, "status": {"privacyStatus": "public"}}
        return yt.playlists().insert(part="snippet,status", body=body).execute()["id"]

    def schedule(self, pkg: YouTubePackage) -> YouTubePackage:
        yt = self._yt
        b = yt.liveBroadcasts().insert(part="snippet,status,contentDetails", body={
            "snippet": {"title": pkg.title, "description": pkg.description,
                        "scheduledStartTime": pkg.scheduled_start.astimezone().isoformat()},
            "status": {"privacyStatus": pkg.visibility.value, "selfDeclaredMadeForKids": False},
            "contentDetails": {"enableAutoStart": False, "enableAutoStop": True, "enableDvr": True,
                               "recordFromStart": True, "latencyPreference": "normal"},
        }).execute()
        vid = b["id"]
        streams = yt.liveStreams().list(part="id,snippet", mine=True, maxResults=5).execute().get("items", [])
        if streams:   # bind the channel's reusable stream; key stays inside YouTube
            yt.liveBroadcasts().bind(id=vid, part="id,contentDetails", streamId=streams[0]["id"]).execute()
        else:
            pkg.notes.append("no reusable live stream found: create one in Studio and bind manually")
        yt.videos().update(part="snippet", body={"id": vid, "snippet": {
            "title": pkg.title, "description": pkg.description, "tags": pkg.tags,
            "categoryId": pkg.category_id}}).execute()
        if pkg.thumbnail_path and Path(pkg.thumbnail_path).exists():
            from googleapiclient.http import MediaFileUpload
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(pkg.thumbnail_path)).execute()
        for name in pkg.playlists:
            yt.playlistItems().insert(part="snippet", body={"snippet": {
                "playlistId": self._playlist_id(name),
                "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
        pkg.links.update(links_for(vid))
        pkg.status = PackageStatus.SCHEDULED
        return pkg

    def set_visibility(self, video_id: str, visibility: Visibility) -> None:
        self._yt.videos().update(part="status", body={"id": video_id, "status": {
            "privacyStatus": visibility.value, "selfDeclaredMadeForKids": False}}).execute()

    def recent_video_stats(self, n: int = 50) -> list[tuple[Any, int]]:
        """(published_at, views) for learn_best_slots(); 1 quota unit per call."""
        from datetime import datetime
        yt = self._yt
        ch = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]
        up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
        ids = [i["contentDetails"]["videoId"] for i in
               yt.playlistItems().list(part="contentDetails", playlistId=up, maxResults=n).execute()["items"]]
        out = []
        for v in yt.videos().list(part="snippet,statistics", id=",".join(ids)).execute()["items"]:
            ts = datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00")).astimezone(self.cfg.tz)
            out.append((ts, int(v["statistics"].get("viewCount", 0))))
        return out


def links_for(video_id: str) -> dict[str, str]:
    return {
        "watch": f"https://www.youtube.com/watch?v={video_id}",
        "share": f"https://youtu.be/{video_id}",
        "studio_edit": f"https://studio.youtube.com/video/{video_id}/edit",
        "live_control_room": f"https://studio.youtube.com/video/{video_id}/livestreaming",
        "embed": f'<iframe width="560" height="315" src="https://www.youtube.com/embed/{video_id}" '
                 'title="YouTube video player" allowfullscreen></iframe>',
    }
