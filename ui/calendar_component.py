from nicegui import ui
from datetime import date
import calendar

def calendar_container(grouped_videos_by_day):
    """Reusable calendar component that takes grouped videos by day."""
    state = {'current_month': date.today().replace(day=1)}
    month_label = None  # Reference for the month label

    def render_calendar():
        calendar_grid.clear()  # Clear stale data
        current = state['current_month']
        year, month = current.year, current.month
        first_day = date(year, month, 1)
        start_weekday = first_day.weekday()  # Monday=0
        days_in_month = calendar.monthrange(year, month)[1]

        # Update the month label
        month_label.text = first_day.strftime('%B %Y')

        # Weekday Headers
        with calendar_grid:
            for wd in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']:
                ui.label(wd).classes('text-center font-semibold text-gray-600')

            # Padding for First Week
            for _ in range(start_weekday):
                ui.label('').classes('')

            # Calendar Days
            for day in range(1, days_in_month + 1):
                d = date(year, month, day)
                d_str = d.strftime('%Y-%m-%d')
                videos = grouped_videos_by_day.get(d_str, [])

                with ui.card().classes('h-20 p-2 bg-gray-50 border border-gray-300 shadow-sm hover:shadow-md transition rounded-lg'):
                    ui.label(str(day)).classes('text-sm font-bold text-gray-800')
                    if videos:
                        ui.link(f'{len(videos)} film(s)', f'/film/{videos[0]["video_id"]}') \
                            .classes('text-blue-500 text-xs underline')
                        for video in videos:
                            ui.label(video['title']).classes('text-xs text-gray-500 truncate')

    # --- Calendar Layout ---
    with ui.column().classes('w-full h-full items-center gap-4'):
        # Navigation Buttons with Month Label
        with ui.row().classes('justify-between w-1/2 items-center mb-4'):
            ui.button('← Previous', on_click=lambda: change_month(-1)).props('flat').classes('text-blue-500 hover:bg-blue-100')
            month_label = ui.label('').classes('text-xl font-bold text-blue-500')  # Dynamically updated label
            ui.button('Next →', on_click=lambda: change_month(1)).props('flat').classes('text-blue-500 hover:bg-blue-100')

        # Calendar Grid
        with ui.row().classes('w-full h-full max-w-5xl flex-1 bg-white rounded-lg shadow-lg overflow-hidden'):
            with ui.column().classes('w-full h-full p-4 gap-2'):
                calendar_grid = ui.grid(columns=7).classes('gap-2 w-full h-full')
                render_calendar()

    def change_month(offset):
        """Change the current month and re-render the calendar."""
        current_month = state['current_month']
        new_month = current_month.month + offset
        new_year = current_month.year

        # Adjust year if the month goes out of bounds
        if new_month < 1:
            new_month = 12
            new_year -= 1
        elif new_month > 12:
            new_month = 1
            new_year += 1

        # Update the state and re-render the calendar
        state['current_month'] = date(new_year, new_month, 1)
        render_calendar()