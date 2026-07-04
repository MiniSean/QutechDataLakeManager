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
    def __init__(self, num_weeks: int = 52) -> None:
        self.num_weeks: int = num_weeks
    # endregion

    # region Class Methods
    def _get_detected_color(self, count: int) -> str:
        """Returns a rich color string based on the dataset count linearly interpolated from 0 to 5."""
        if count == 0:
            return "color(237)" # Dark grey
        elif count == 1:
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
        elif count == 1:
            return "color(23)"  # Dark cyan
        elif count == 2:
            return "color(30)"  # Medium dark cyan
        elif count == 3:
            return "color(37)"  # Medium cyan
        elif count == 4:
            return "color(44)"  # Cyan
        else:
            return "color(45)"  # Bright cyan (dimmed slightly)

    def render(self, available_counts: Dict[datetime.date, int], detected_counts: Dict[datetime.date, int]) -> Table:
        """Renders the heatmap grid as a Rich Table."""
        today: datetime.date = datetime.date.today()
        # Find the most recent Sunday
        end_date: datetime.date = today + datetime.timedelta(days=(6 - today.weekday()))
        start_date: datetime.date = end_date - datetime.timedelta(weeks=self.num_weeks)

        table: Table = Table(show_header=True, header_style="bold", show_edge=False, box=None, padding=(0, 0))
        
        # Calculate column dates (the Sunday of each week)
        col_dates: List[datetime.date] = []
        for i in range(self.num_weeks):
            col_dates.append(start_date + datetime.timedelta(weeks=i))
            
        # Add columns: month names on the first week of the month
        for i, col_date in enumerate(col_dates):
            header = ""
            # If it's the first column or the month changed from the previous column
            if i == 0 or col_date.month != col_dates[i-1].month:
                header = calendar.month_abbr[col_date.month]
            table.add_column(header, justify="center")

        # 7 rows for days (Monday = 0, Sunday = 6)
        # However, standard Github heatmap is Sun-Sat. Let's do Mon-Sun.
        for day_of_week in range(7):
            row_cells: List[Text] = []
            for col_date in col_dates:
                # The actual date for this cell
                cell_date: datetime.date = col_date - datetime.timedelta(days=(6 - day_of_week))
                
                avail_count: int = available_counts.get(cell_date, 0)
                det_count: int = detected_counts.get(cell_date, 0)
                # Ensure future dates remain empty/dark
                if cell_date > today:
                    color = "color(237)"
                elif det_count > 0:
                    color = self._get_detected_color(det_count)
                elif avail_count > 0:
                    color = self._get_available_color(avail_count)
                else:
                    color = "color(237)"
                
                row_cells.append(Text("■", style=color))
            
            table.add_row(*row_cells)

        return table
        
    def render_legend(self) -> Text:
        """Renders the right-aligned legend for dataset counts."""
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


