import datetime
import calendar
from typing import Dict, List, Optional, Any, Sequence
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
import rich.box
import os
import sys

from client.status_panel.ui import StatusPanel


class HeatmapGrid:
    # region Class Constructor
    def __init__(self, num_weeks: int = 52, single_color_mode: bool = False) -> None:
        self.num_weeks: int = num_weeks
        self.single_color_mode: bool = single_color_mode
    # endregion

    # region Class Methods
    def _get_detected_color(self, count: int) -> str:
        """Returns a rich color string based on the dataset count linearly interpolated from 0 to 5."""
        if count == 0:
            return "color(237)" # Dark grey
        if self.single_color_mode:
            return "color(46)"  # Bright green
            
        if count == 1:
            return "color(22)"  # Very dark green
        elif count == 2:
            return "color(28)"  # Dark green
        elif count == 3:
            return "color(34)"  # Medium green
        elif count == 4:
            return "color(40)"  # Green
        else:
            return "color(46)"  # Bright green

    def _get_available_color(self, count: int) -> str:
        """Returns a rich color string based on the available dataset count."""
        if count == 0:
            return "color(237)" # Dark grey
        if self.single_color_mode:
            return "color(51)"  # Bright cyan
            
        if count == 1:
            return "color(23)"  # Dark cyan
        elif count == 2:
            return "color(30)"  # Medium dark cyan
        elif count == 3:
            return "color(37)"  # Medium cyan
        elif count == 4:
            return "color(44)"  # Cyan
        else:
            return "color(45)"  # Bright cyan (dimmed slightly)

    def render(self, available_counts: Dict[datetime.date, int], detected_counts: Dict[datetime.date, int]) -> Group:
        """Renders the heatmap grid and headers."""
        today: datetime.date = datetime.date.today()
        # Find the most recent Sunday
        end_date: datetime.date = today + datetime.timedelta(days=(6 - today.weekday()))
        start_date: datetime.date = end_date - datetime.timedelta(weeks=self.num_weeks)

        table: Table = Table(show_header=False, show_edge=False, box=None, padding=(0, 0))
        
        # Calculate column dates (the Sunday of each week)
        col_dates: List[datetime.date] = []
        for i in range(self.num_weeks):
            col_dates.append(start_date + datetime.timedelta(weeks=i))
            table.add_column("")
            
        header_chars1 = [" "] * self.num_weeks
        header_chars2 = [" "] * self.num_weeks
        
        def place_text(chars_list: List[str], idx: int, text: str, force: bool = False) -> None:
            available = True
            for j in range(len(text)):
                if idx + j < self.num_weeks and chars_list[idx + j] != " ":
                    available = False
                    break
            if available or force:
                for j, char in enumerate(text):
                    if idx + j < self.num_weeks:
                        chars_list[idx + j] = char

        # Place Januaries first (highest priority)
        for i, col_date in enumerate(col_dates):
            if (i == 0 or col_date.month != col_dates[i-1].month) and col_date.month == 1:
                place_text(header_chars2, i, calendar.month_abbr[1], force=True)
                place_text(header_chars1, i, str(col_date.year), force=True)

        # Place the first item if it's not January, and only if it fits
        if col_dates and col_dates[0].month != 1:
            place_text(header_chars2, 0, calendar.month_abbr[col_dates[0].month], force=False)
            place_text(header_chars1, 0, str(col_dates[0].year), force=False)

        # Place other months if they fit
        for i, col_date in enumerate(col_dates):
            if i > 0 and col_date.month != col_dates[i-1].month and col_date.month != 1:
                place_text(header_chars2, i, calendar.month_abbr[col_date.month], force=False)

        # 4 rows for 7 days using the Half-Block technique to remove vertical spaces
        for day_pair in range(0, 7, 2):
            row_cells: List[Text] = []
            for col_date in col_dates:
                # Top half (day_pair)
                day1 = day_pair
                cell_date1 = col_date - datetime.timedelta(days=(6 - day1))
                avail1 = available_counts.get(cell_date1, 0)
                det1 = detected_counts.get(cell_date1, 0)
                
                if cell_date1 > today:
                    color1 = "color(237)"
                elif det1 > 0:
                    color1 = self._get_detected_color(det1)
                elif avail1 > 0:
                    color1 = self._get_available_color(avail1)
                else:
                    color1 = "color(237)"

                # Bottom half (day_pair + 1)
                day2 = day_pair + 1
                if day2 < 7:
                    cell_date2 = col_date - datetime.timedelta(days=(6 - day2))
                    avail2 = available_counts.get(cell_date2, 0)
                    det2 = detected_counts.get(cell_date2, 0)
                    
                    if cell_date2 > today:
                        color2 = "color(237)"
                    elif det2 > 0:
                        color2 = self._get_detected_color(det2)
                    elif avail2 > 0:
                        color2 = self._get_available_color(avail2)
                    else:
                        color2 = "color(237)"
                        
                    # ▀ is upper half block. Foreground is top half, Background is bottom half.
                    row_cells.append(Text("▀", style=f"{color1} on {color2}"))
                else:
                    row_cells.append(Text("▀", style=color1))
            
            table.add_row(*row_cells)

        header_text = Text("".join(header_chars1) + "\n" + "".join(header_chars2))
        return Group(header_text, table)
        
    def render_legend(self) -> Text:
        """Renders the right-aligned legend for dataset counts."""
        if self.single_color_mode:
            legend: Text = Text("Detected Datasets: ", justify="left")
            legend.append("■ ", style="color(237)")
            legend.append("■ ", style="color(51)")
            legend.append(" | Synced Datasets: ")
            legend.append("■ ", style="color(237)")
            legend.append("■ ", style="color(46)")
            return legend
            
        legend: Text = Text("Detected Datasets: Less ", justify="left")
        legend.append("■ ", style="color(237)")
        legend.append("■ ", style="color(23)")
        legend.append("■ ", style="color(30)")
        legend.append("■ ", style="color(37)")
        legend.append("■ ", style="color(44)")
        legend.append("■ ", style="color(45)")
        legend.append("More | Synced Datasets: Less ")
        legend.append("■ ", style="color(237)")
        legend.append("■ ", style="color(22)")
        legend.append("■ ", style="color(28)")
        legend.append("■ ", style="color(34)")
        legend.append("■ ", style="color(40)")
        legend.append("■ ", style="color(46)")
        legend.append("More")
        return legend
    # endregion


