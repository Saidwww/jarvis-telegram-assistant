import os
import calendar
import datetime
import matplotlib
# Use Agg backend for headless systems (no GUI needed for saving plots)
matplotlib.use('Agg')

# Monkey patch matplotlib.path.Path.__deepcopy__ to fix recursion bug on Python 3.14
import copy
import matplotlib.path

def _path_deepcopy(self, memo=None):
    if memo is None:
        memo = {}
    cls = type(self)
    copied_path = cls.__new__(cls)
    memo[id(self)] = copied_path
    for k, v in self.__dict__.items():
        setattr(copied_path, k, copy.deepcopy(v, memo))
    copied_path._readonly = False
    return copied_path

matplotlib.path.Path.__deepcopy__ = _path_deepcopy

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

import db

def get_month_ranges():
    """
    Returns the start and end dates for the current month and the previous month.
    Format of all dates: datetime.date objects.
    """
    today = datetime.date.today()
    this_year = today.year
    this_month = today.month

    # Current month start and end
    this_month_start = datetime.date(this_year, this_month, 1)
    _, last_day_this = calendar.monthrange(this_year, this_month)
    this_month_end = datetime.date(this_year, this_month, last_day_this)

    # Previous month start and end
    if this_month == 1:
        last_month = 12
        last_year = this_year - 1
    else:
        last_month = this_month - 1
        last_year = this_year

    last_month_start = datetime.date(last_year, last_month, 1)
    _, last_day_last = calendar.monthrange(last_year, last_month)
    last_month_end = datetime.date(last_year, last_month, last_day_last)

    return (
        this_month_start, this_month_end, today,
        last_month_start, last_month_end,
        this_month, last_month, this_year, last_year
    )

def generate_stats_chart(user_id, output_path="stats.png"):
    """
    Generates a chart comparing habit completions and sleep trends
    between this month and last month, saving the figure to output_path.
    """
    (
        this_start, this_end, today,
        last_start, last_end,
        this_m_num, last_m_num, this_y, last_y
    ) = get_month_ranges()

    # Fetch data from DB
    sleep_this = db.get_sleep_stats(user_id, this_start.isoformat(), this_end.isoformat())
    sleep_last = db.get_sleep_stats(user_id, last_start.isoformat(), last_end.isoformat())
    habits_this = db.get_habit_stats(user_id, this_start.isoformat(), this_end.isoformat())
    habits_last = db.get_habit_stats(user_id, last_start.isoformat(), last_end.isoformat())

    # Get month names
    this_month_name = f"{calendar.month_name[this_m_num]} {this_y}"
    last_month_name = f"{calendar.month_name[last_m_num]} {last_y}"

    # Setup the plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 10), gridspec_kw={'hspace': 0.3})
    fig.patch.set_facecolor('#F8F9FA')

    # --- Plot 1: Sleep Chart ---
    # We plot the X-axis as day of the month (1 to 31)
    # This month data only up to today (or end of month if viewing in past)
    days_in_this_month = calendar.monthrange(this_y, this_m_num)[1]
    days_in_last_month = calendar.monthrange(last_y, last_m_num)[1]
    max_days = max(days_in_this_month, days_in_last_month)
    
    x_days = list(range(1, max_days + 1))
    
    sleep_vals_this = []
    sleep_vals_last = []
    
    for d in x_days:
        # Last Month sleep
        if d <= days_in_last_month:
            date_str = datetime.date(last_y, last_m_num, d).isoformat()
            sleep_vals_last.append(sleep_last.get(date_str, float('nan')))
        else:
            sleep_vals_last.append(float('nan'))
            
        # This Month sleep (stop plotting future days)
        if d <= days_in_this_month:
            if d > today.day and this_y == today.year and this_m_num == today.month:
                sleep_vals_this.append(float('nan'))
            else:
                date_str = datetime.date(this_y, this_m_num, d).isoformat()
                sleep_vals_this.append(sleep_this.get(date_str, float('nan')))
        else:
            sleep_vals_this.append(float('nan'))

    # Plot lines
    ax1.plot(x_days, sleep_vals_last, color='#ADB5BD', linestyle='--', linewidth=2.0, marker='x', label=last_month_name)
    ax1.plot(x_days, sleep_vals_this, color='#0D9488', linewidth=2.5, marker='o', label=this_month_name)

    # Add averages to legend
    valid_sleep_this = [v for v in sleep_this.values() if v is not None]
    valid_sleep_last = [v for v in sleep_last.values() if v is not None]
    
    avg_this = sum(valid_sleep_this) / len(valid_sleep_this) if valid_sleep_this else 0
    avg_last = sum(valid_sleep_last) / len(valid_sleep_last) if valid_sleep_last else 0
    
    if avg_last > 0:
        ax1.axhline(avg_last, color='#ADB5BD', linestyle=':', alpha=0.7, label=f'{last_month_name} Avg ({avg_last:.1f}h)')
    if avg_this > 0:
        ax1.axhline(avg_this, color='#0D9488', linestyle=':', alpha=0.7, label=f'{this_month_name} Avg ({avg_this:.1f}h)')

    ax1.set_title("Sleep Progress & Trends (Hours per Day)", fontsize=14, fontweight='bold', color='#1F2937', pad=10)
    ax1.set_xlabel("Day of Month", fontsize=11, color='#4B5563')
    ax1.set_ylabel("Hours Slept", fontsize=11, color='#4B5563')
    ax1.set_xlim(0.5, max_days + 0.5)
    ax1.set_ylim(0, 13)
    ax1.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax1.set_facecolor('#FFFFFF')
    ax1.grid(True, linestyle=':', alpha=0.6, color='#E5E7EB')
    ax1.legend(loc='upper right', framealpha=0.9, facecolor='#FFFFFF', edgecolor='#E5E7EB')

    # --- Plot 2: Habits Chart ---
    # We compare the completion counts of all habits
    all_habits = db.get_habits(user_id)
    
    if not all_habits:
        # No habits defined
        ax2.text(0.5, 0.5, "No habits configured yet.\nAdd habits using the `/addhabit` command in the bot!", 
                 horizontalalignment='center', verticalalignment='center', fontsize=12, color='#6B7280', transform=ax2.transAxes)
        ax2.set_title("Habit Completion Comparison", fontsize=14, fontweight='bold', color='#1F2937', pad=10)
        ax2.set_facecolor('#FFFFFF')
        ax2.set_xticks([])
        ax2.set_yticks([])
    else:
        # We have habits to compare
        habit_names = all_habits
        last_counts = [habits_last.get(name, 0) for name in habit_names]
        this_counts = [habits_this.get(name, 0) for name in habit_names]

        x = range(len(habit_names))
        width = 0.35  # Bar width

        rects1 = ax2.bar([i - width/2 for i in x], last_counts, width, label=last_month_name, color='#9CA3AF')
        rects2 = ax2.bar([i + width/2 for i in x], this_counts, width, label=this_month_name, color='#14B8A6')

        # Add counts above bars
        for rect in rects1:
            h = rect.get_height()
            if h > 0:
                ax2.annotate(f'{int(h)}',
                            xy=(rect.get_x() + rect.get_width() / 2, h),
                            xytext=(0, 3),  # 3 points vertical offset
                            textcoords="offset points",
                            ha='center', va='bottom', fontsize=9, color='#4B5563')
                            
        for rect in rects2:
            h = rect.get_height()
            if h > 0:
                ax2.annotate(f'{int(h)}',
                            xy=(rect.get_x() + rect.get_width() / 2, h),
                            xytext=(0, 3),
                            textcoords="offset points",
                            ha='center', va='bottom', fontsize=9, color='#0D9488', fontweight='bold')

        ax2.set_title("Habit Completion Comparison (Days Completed)", fontsize=14, fontweight='bold', color='#1F2937', pad=10)
        ax2.set_ylabel("Days Logged", fontsize=11, color='#4B5563')
        ax2.set_xticks(x)
        ax2.set_xticklabels(habit_names, fontsize=11, fontweight='bold')
        ax2.yaxis.set_major_locator(MaxNLocator(integer=True))
        ax2.set_facecolor('#FFFFFF')
        ax2.grid(True, axis='y', linestyle=':', alpha=0.6, color='#E5E7EB')
        ax2.legend(loc='upper right', framealpha=0.9, facecolor='#FFFFFF', edgecolor='#E5E7EB')

    # Overall Adjustments
    fig.suptitle(f"Personal Dashboard: {this_month_name} vs {last_month_name}", fontsize=16, fontweight='bold', color='#111827', y=0.96)
    
    # Save output
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close()
    return output_path
