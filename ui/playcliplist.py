from nicegui import ui
from utils_api import load_cliplist, load_clips
from video_player import VideoPlayer

# ---- Global State ----
current_index = 0
is_autoplay = True
is_loop = True

queue_buttons = []
queue = []


def playcliplist_page(cliplist_id):

    global current_index, queue_buttons, queue

    all_videos = load_clips()
    cliplist = load_cliplist(cliplist_id)
    filters_to_use = cliplist.get('filters', {})

    filtered_videos = [
        v for v in all_videos
        if v['playlist_name'] in filters_to_use.get('playlists', [])
        and (not filters_to_use.get('labels') or any(label in v.get('labels', []) for label in filters_to_use.get('labels', [])))
        and (not filters_to_use.get('partners') or any(partner in v.get('partners', []) for partner in filters_to_use.get('partners', [])))
    ]

    queue = filtered_videos.copy()
    queue_buttons = []
    if not queue:
        ui.notify("No clips found for selected filters", type='warning')
        return

    def play_clip(index: int):
        global current_index
        current_index = index
        highlight_queue()

        player_column.clear()
        with player_column:
            VideoPlayer(
                video_url=queue[index]['video_id'],
                start=queue[index]['start'],
                end=queue[index]['end'],
                speed=2.0, #TODO: pick from clip, else default to 2.0
                on_end=lambda: next_clip() if is_autoplay else None,
                parent=player_column  # ✅ key fix
            )

    def next_clip():
        global current_index
        current_index = (current_index + 1) % len(queue)
        play_clip(current_index)

    def highlight_queue():
        for i, btn in enumerate(queue_buttons):
            btn.props('color=secondary' if i == current_index else 'color=primary')

    # --- Layout ---
    with ui.splitter(value=70, horizontal=False).classes('w-full h-full') as splitter:
        with splitter.before:
            player_column = ui.column().classes('w-full h-full').style('height: 100%; height: 56.25vw; max-height: 70vh;')
        with splitter.after:
            for i, clip in enumerate(queue):
                title = clip.get('title') or f"clip-{i + 1}"
                btn = ui.button(title, on_click=lambda i=i: play_clip(i)).classes('w-full')
                queue_buttons.append(btn)

    # Start
    play_clip(current_index)

# .style('height: 100%; min-height: 400px height: 56.25vw; max-height: 90vh; width: 100%;')