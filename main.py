"""
Diet Tracker Application - Refactored with KV Language

Architecture:
- style.kv: All UI styling, layouts, and widget definitions
- main.py: Business logic, data handling, and event processing

Key Components:
- LoadingScreen: Initial app loading with progress tracking
- ChatScreen: Main interface with chat history and macro tracking
- MacrosHeader: Daily calorie/macro visualization with pie chart and progress bars
- MealLoggingScreen: Image upload and nutrition entry interface
- PieChart: Custom widget for donut chart visualization
- LineGraph: Custom widget for analytics graphs
- AnalyticsPopup: 7-day nutrition trends display

Important Notes:
- All self.ids access must be scheduled after __init__ or use on_kv_post
- KV file is auto-loaded by Builder.load_file('style.kv')
- Widget styling and layout changes should be made in .kv file
"""

from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.core.text import Label as CoreLabel
from kivy.uix.widget import Widget
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.image import AsyncImage, Image
from kivy.core.image import Image as CoreImage
from kivy.graphics import Color, Line, RoundedRectangle, Ellipse, Rectangle
from kivy.utils import get_color_from_hex
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.config import Config
from kivy import platform
from kivy.utils import platform
from kivy.uix.behaviors import ButtonBehavior
from kivy.lang import Builder
from kivy.properties import StringProperty, ListProperty
from kivy.app import App

from plyer import filechooser, camera
import io
import math, threading, time, traceback, datetime, os, shutil
from functools import partial

from chatbot import load_model, estimate_nutrition, handle_logged_meal, get_chat_response, describe_food, get_recipe_from_image, get_recipe_from_text, get_recipe_from_text_and_image
from upload import upload_meal, update_macro_goals, init_firebase, get_user_doc, get_meal_doc

# Mobile Configuration
if platform == 'android':
    Config.set('kivy', 'keyboard_mode', 'system')
    Window.softinput_mode = "below_target"
    Window.keyboard_anim_args = {'d': 0.2, 't': 'in_out_expo'}
else:
    Config.set('kivy', 'keyboard_mode', 'dock')

Config.set('graphics', 'orientation', 'portrait')
Config.set('graphics', 'resizable', True)
Config.set('graphics', 'fullscreen', '0')
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

# Config
COLORS = {
    'main': get_color_from_hex("#1E2D2F"),
    'text': get_color_from_hex("#BFD1E5"),
    'accent1': get_color_from_hex("#809848"),
    'accent2': get_color_from_hex("#B0CA87"),
    'accent3': get_color_from_hex("#7D4E57")
}
Window.clearcolor = COLORS['main']

# insert your user id, project id and firebase url here
USER_ID = "#USER_ID HERE#"
PROJECT_ID = "#PROJECT_ID HERE#"
FIREBASE_URL = f"#FIRESTORE_URL HERE#"
# Window.size = (360, 640)  # Comment out when compiling to mobile

# Load KV file
Builder.load_file('assets/style.kv')

# ==============================
# UTILITY FUNCTIONS
# ==============================
def show_popup(title, message, callback=None):
    """Generic popup with OK button"""
    content = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))
    content.add_widget(Label(text=message, color=(1,1,1,1), font_size=dp(14), 
                            halign='center', valign='middle'))
    btn = Button(text="OK", size_hint=(1, None), height=dp(50), 
                 background_color=COLORS['accent1'], color=COLORS['text'], 
                 font_size=dp(16), bold=True)
    content.add_widget(btn)
    popup = Popup(title=title, content=content, size_hint=(0.8, 0.4), auto_dismiss=False)
    btn.bind(on_press=lambda x: (popup.dismiss(), callback() if callback else None))
    popup.open()

# ==============================
# LOADING SCREEN
# ==============================
class LoadingScreen(FloatLayout):
    def update_status(self, status, progress):
        self.ids.status_label.text = status
        self.ids.progress.value = progress

# ==============================
# CHAT BUBBLE
# ==============================
class ChatBubble(BoxLayout):
    def __init__(self, text, is_user=False, **kwargs):
        self.text = text
        self.is_user = is_user
        super().__init__(**kwargs)
        self._update_padding()
        Window.bind(width=lambda i, v: self._update_padding())
        
        # Set height based on text
        Clock.schedule_once(self._update_height, 0.1)
    
    def _update_height(self, dt):
        label = self.ids.bubble_label
        label.text_size = (label.width, None)
        label.texture_update()
        label.height = label.texture_size[1] + dp(10)
        self.children[0].height = label.height + dp(30)
        self.height = self.children[0].height + dp(10)
    
    def _update_padding(self):
        w = Window.width if hasattr(Window, 'width') else 360
        self.padding = [w * 0.1, dp(5), dp(10), dp(5)] if self.is_user else \
                      [dp(10), dp(5), w * 0.1, dp(5)]

# ==============================
# PIE CHART
# ==============================
class PieChart(Widget):
    def __init__(self, consumed, remaining, calorie_goal, **kwargs):
        super().__init__(**kwargs)
        self.consumed, self.remaining, self.calorie_goal = consumed, remaining, calorie_goal
        self.size_hint = (None, None)
        self._parent_fraction = 0.8
        self.bind(pos=self.draw_chart, size=self.draw_chart, parent=self._on_parent_set)
        Clock.schedule_once(self.draw_chart, 0.05)

    def _on_parent_set(self, instance, parent):
        if parent:
            parent.bind(size=self._on_parent_resize, pos=self._on_parent_resize)
            self._on_parent_resize(parent, None)

    def _on_parent_resize(self, parent, _):
        size = min(parent.width, parent.height) * self._parent_fraction
        self.size = (size, size)
        self.center = parent.center
        Clock.schedule_once(self.draw_chart, 0)

    def draw_chart(self, *args):
        if self.width <= 0 or self.height <= 0:
            return
        self.canvas.clear()
        self.canvas.after.clear()

        # Segments
        if self.remaining < 0:
            total = self.calorie_goal + abs(self.remaining) or 1
            segments = [
                {'angle': (self.calorie_goal / total) * 360, 'color': (1, 0.9, 0.43, 1), 
                 'label': f'Goal\n{int(self.calorie_goal)}'},
                {'angle': (abs(self.remaining) / total) * 360, 'color': (1, 0.42, 0.42, 1), 
                 'label': f'Over\n{int(abs(self.remaining))}'}
            ]
        else:
            total = self.consumed + self.remaining or 1
            segments = [
                {'angle': (self.consumed / total) * 360, 'color': (0.31, 0.80, 0.77, 1), 
                 'label': f'Consumed\n{int(self.consumed)}'},
                {'angle': (self.remaining / total) * 360, 'color': COLORS['accent1'], 
                 'label': f'Remaining\n{int(self.remaining)}'}
            ]

        cx, cy = self.x + self.width / 2, self.y + self.height / 2
        outer_radius = min(self.width, self.height) / 2.0
        inner_radius = outer_radius * 0.6

        # Draw donut
        start_angle = 90
        with self.canvas:
            for seg in segments:
                Color(*seg['color'])
                Ellipse(pos=(cx - outer_radius, cy - outer_radius),
                       size=(outer_radius * 2, outer_radius * 2),
                       angle_start=start_angle, angle_end=start_angle + seg['angle'])
                start_angle += seg['angle']
            Color(*COLORS['accent2'])
            Ellipse(pos=(cx - inner_radius, cy - inner_radius),
                   size=(inner_radius * 2, inner_radius * 2))

        # Labels
        start_angle = 90
        for seg in segments:
            mid_angle = start_angle + seg['angle'] / 2
            label_distance = outer_radius * 0.85
            label_x = cx + label_distance * math.cos(math.radians(mid_angle))
            label_y = cy + label_distance * math.sin(math.radians(mid_angle))
            text_label = CoreLabel(text=seg['label'], font_size=dp(10), bold=True, 
                                  halign='center', valign='middle')
            text_label.refresh()
            with self.canvas.after:
                Color(0, 0, 0, 1)
                Rectangle(texture=text_label.texture,
                         pos=(label_x - text_label.width / 2, label_y - text_label.height / 2),
                         size=text_label.size)
            start_angle += seg['angle']

# ==============================
# LINE GRAPH
# ==============================
class LineGraph(FloatLayout):
    # Make title a Kivy Property so KV can bind to it
    title = StringProperty("")
    
    def __init__(self, title, data_points, colors, labels, y_label="Value", dates=None, **kwargs):
        self.title = title  # Set before super().__init__
        super().__init__(**kwargs)
        self.data_points = data_points
        self.colors = colors
        self.labels = labels
        self.y_label = y_label
        self.dates = dates  # List of dates for x-axis labels
    
    def draw_graph(self):
        self.canvas.after.clear()
        
        # Clear any existing value labels and x-axis labels
        for child in self.children[:]:
            if isinstance(child, Label) and not isinstance(child.parent, BoxLayout):
                self.remove_widget(child)
        
        if not self.data_points or not any(self.data_points):
            return
        
        padding = {'left': dp(45), 'right': dp(20), 'top': dp(60), 'bottom': dp(50)}
        graph_w = self.width - padding['left'] - padding['right']
        graph_h = self.height - padding['top'] - padding['bottom']
        
        if graph_w <= 0 or graph_h <= 0:
            return
        
        max_val = max(max(series) if series else 0 for series in self.data_points) or 1
        x_step = graph_w / 6 if len(self.data_points[0]) > 1 else 0
        
        with self.canvas.after:
            # Axes
            Color(0.2, 0.2, 0.3, 1)
            Line(points=[self.x + padding['left'], self.y + padding['bottom'],
                        self.x + padding['left'], self.y + padding['bottom'] + graph_h], width=1.5)
            Line(points=[self.x + padding['left'], self.y + padding['bottom'],
                        self.x + padding['left'] + graph_w, self.y + padding['bottom']], width=1.5)
            
            # Grid
            Color(0.2, 0.2, 0.3, 0.6)
            for i in range(6):
                y_pos = self.y + padding['bottom'] + (graph_h / 5) * i
                Line(points=[self.x + padding['left'], y_pos,
                           self.x + padding['left'] + graph_w, y_pos], 
                    width=1, dash_offset=2, dash_length=3)
            
            # Data series
            for series_idx, series in enumerate(self.data_points):
                if not series:
                    continue
                color = get_color_from_hex(self.colors[series_idx])
                Color(*color)
                points = []
                for day_idx, value in enumerate(series):
                    x = self.x + padding['left'] + (x_step * day_idx)
                    y = self.y + padding['bottom'] + (value / max_val) * graph_h
                    points.extend([x, y])
                
                if len(points) >= 4:
                    Line(points=points, width=2.5)
                    for i in range(0, len(points), 2):
                        Ellipse(pos=(points[i] - dp(4), points[i+1] - dp(4)), size=(dp(8), dp(8)))
                        
                        # Add value labels above data points
                        value_idx = i // 2
                        value = series[value_idx]
                        value_label = Label(
                            text=str(int(value)),
                            font_size=dp(10),
                            color=COLORS['main'],  # Changed to COLORS['main']
                            bold=True,
                            size_hint=(None, None),
                            size=(dp(30), dp(15)),
                            pos=(points[i] - dp(15), points[i+1] + dp(8))
                        )
                        self.add_widget(value_label)
        
        # Add X-axis date labels (OUTSIDE the canvas context)
        if self.dates and len(self.dates) == 7:
            for day_idx in range(7):
                x_pos = self.x + padding['left'] + (x_step * day_idx)
                date_label = Label(
                    text=self.dates[day_idx],
                    font_size=dp(10),
                    color=COLORS['main'],
                    size_hint=(None, None),
                    size=(dp(40), dp(20)),
                    pos=(x_pos - dp(20), self.y + dp(5)),  # Position at bottom
                    halign='center',
                    valign='middle'
                )
                date_label.bind(size=date_label.setter('text_size'))
                self.add_widget(date_label)
        
        # Legend
        legend_y = self.y + self.height - dp(40)
        for idx, label in enumerate(self.labels):
            legend_box = BoxLayout(pos=(self.x + padding['left'] + idx * dp(45), legend_y),
                                  size=(dp(80), dp(20)), size_hint=(None, None), spacing=dp(5))
            color_ind = Widget(size_hint=(None, 1), width=dp(15))
            with color_ind.canvas:
                Color(*get_color_from_hex(self.colors[idx]))
                color_ind.rect = RoundedRectangle(pos=color_ind.pos, size=color_ind.size, 
                                                  radius=[dp(2)])
            color_ind.bind(pos=lambda w, v: setattr(w.rect, 'pos', v),
                          size=lambda w, v: setattr(w.rect, 'size', v))
            legend_label = Label(text=label, color=COLORS['main'], font_size=dp(10), 
                               size_hint=(1, 1), halign='left', valign='middle')
            legend_label.bind(size=legend_label.setter('text_size'))
            legend_box.add_widget(color_ind)
            legend_box.add_widget(legend_label)
            self.add_widget(legend_box)

# ==============================
# MACROS HEADER
# ==============================
class MacrosHeader(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calorie_goal = 2000
        self.protein_goal = 150
        self.carbs_goal = 250
        self.fats_goal = 65
        # Bind after widget is fully constructed
        Clock.schedule_once(self._bind_button, 0)
    
    def _bind_button(self, dt):
        """Bind analytics button after widget is ready"""
        self.ids.analytics_btn.bind(on_press=self.show_analytics_popup)

    def _update_bar(self, bar_widget, current, goal):
        pct = min((current / goal * 100) if goal > 0 else 0, 100)
        bar_widget.ids.value_label.text = f"{int(current)}/{int(goal)}g"
        
        is_over = current > goal
        bar_widget.ids.value_label.color = get_color_from_hex("#8B0000") if is_over else COLORS['main']
        color = "#8B0000" if is_over else bar_widget.bar_color

        bar = bar_widget.ids.bar
        with bar.canvas.before:
            bar.canvas.before.clear()
            Color(*get_color_from_hex(color))
            bar.rect = RoundedRectangle(radius=[dp(3)], pos=bar.pos, 
                                       size=(bar.parent.width * (pct / 100), bar.height))

        def update_size(o, v):
            bar.rect.pos = o.pos
            bar.rect.size = (o.width * (pct / 100), o.height)
        bar.parent.unbind(pos=update_size, size=update_size)
        bar.parent.bind(pos=update_size, size=update_size)

    def set_data(self, consumed, goals=None):
        if goals:
            self.calorie_goal = goals.get('calories', 2000)
            self.protein_goal = goals.get('proteins', 150)
            self.carbs_goal = goals.get('carbs', 250)
            self.fats_goal = goals.get('fats', 65)

        cal_consumed = consumed.get('calories', 0)
        cal_remaining = self.calorie_goal - cal_consumed

        self.ids.pie_container.clear_widgets()
        self.ids.pie_container.add_widget(PieChart(cal_consumed, cal_remaining, self.calorie_goal))
        Clock.schedule_once(lambda dt: self.ids.pie_container.children[0].draw_chart() 
                          if self.ids.pie_container.children else None, 0.1)

        self._update_bar(self.ids.protein_bar, consumed.get('proteins', 0), self.protein_goal)
        self._update_bar(self.ids.carbs_bar, consumed.get('carbs', 0), self.carbs_goal)
        self._update_bar(self.ids.fats_bar, consumed.get('fats', 0), self.fats_goal)
    
    def show_analytics_popup(self, instance):
        chat_screen = self._find_parent(ChatScreen)
        if chat_screen:
            loading = Popup(title="Loading Analytics...", 
                          content=Label(text="Fetching 7-day data..."),
                          size_hint=(0.6, 0.3), auto_dismiss=False)
            loading.open()
            
            def fetch():
                weekly_data = chat_screen.load_weekly_analytics()
                loading.dismiss()
                Clock.schedule_once(lambda dt: AnalyticsPopup(weekly_data).open(), 0)
            threading.Thread(target=fetch, daemon=True).start()
        else:
            AnalyticsPopup().open()
    
    def _find_parent(self, parent_type):
        parent = self.parent
        while parent:
            if isinstance(parent, parent_type):
                return parent
            parent = parent.parent
        return None

# ==============================
# ANALYTICS POPUP
# ==============================
class AnalyticsPopup(Popup):
    def __init__(self, weekly_data=None, **kwargs):
        super().__init__(**kwargs)
        
        # Store data for later use
        self.weekly_data = weekly_data
        
        # Schedule graph creation after widget is fully built
        Clock.schedule_once(self._create_graphs, 0)
    
    def _create_graphs(self, dt):
        """Create and add graphs after popup is ready"""
        # Generate date labels for the past 7 days
        today = datetime.date.today()
        dates = [(today - datetime.timedelta(days=6-i)).strftime("%d/%m") for i in range(7)]
        
        # Data
        if self.weekly_data:
            cal_data = self.weekly_data.get('calories', [0]*7)
            prot_data = self.weekly_data.get('protein', [0]*7)
            carb_data = self.weekly_data.get('carbs', [0]*7)
            fat_data = self.weekly_data.get('fats', [0]*7)
            energy_data = self.weekly_data.get('energy', [0]*7)
            hunger_data = self.weekly_data.get('hunger', [0]*7)
        else:
            cal_data = [1800, 2000, 1900, 2100, 1850, 2050, 1950]
            prot_data = [120, 140, 130, 145, 135, 150, 140]
            carb_data = [200, 220, 210, 230, 205, 225, 215]
            fat_data = [60, 65, 62, 70, 58, 68, 64]
            energy_data = [3, 4, 3, 5, 4, 3, 4]
            hunger_data = [2, 3, 4, 3, 2, 3, 3]
        
        # Graphs
        graphs = self.ids.graphs_container
        
        # Calorie graph
        calories_graph = LineGraph(
            "7-Day Calorie Intake", 
            [cal_data], 
            ["#9B59B6"], 
            ["Calories"], 
            "Calories (kcal)",
            dates=dates
        )
        
        # SEPARATE macro graphs
        protein_graph = LineGraph(
            "7-Day Protein Intake",
            [prot_data],
            ["#FF6B6B"],
            ["Protein"],
            "Grams (g)",
            dates=dates
        )
        
        carbs_graph = LineGraph(
            "7-Day Carbs Intake",
            [carb_data],
            ["#4ECDC4"],
            ["Carbs"],
            "Grams (g)",
            dates=dates
        )
        
        fats_graph = LineGraph(
            "7-Day Fats Intake",
            [fat_data],
            ["#FFE66D"],
            ["Fats"],
            "Grams (g)",
            dates=dates
        )
        
        # Energy and hunger graphs
        energy_graph = LineGraph(
            "7-Day Energy Levels", 
            [energy_data], 
            ["#F39C12"], 
            ["Energy"], 
            "Level (1-5)",
            dates=dates
        )
        
        hunger_graph = LineGraph(
            "7-Day Hunger Levels", 
            [hunger_data], 
            ["#E74C3C"], 
            ["Hunger"], 
            "Level (1-5)",
            dates=dates
        )
        
        # Add all graphs
        all_graphs = [
            calories_graph, 
            protein_graph, 
            carbs_graph, 
            fats_graph, 
            energy_graph, 
            hunger_graph
        ]
        
        for graph in all_graphs:
            graphs.add_widget(graph)
        
        Clock.schedule_once(lambda dt: self._draw_all_graphs(all_graphs), 0.3)
    
    def _draw_all_graphs(self, graphs):
        """Draw all graphs"""
        for graph in graphs:
            graph.draw_graph()

# ==============================
# CHAT SCREEN
# ==============================
class ChatScreen(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_meal_type = "breakfast"
        # Bind after widget is fully constructed
        Clock.schedule_once(self._setup_bindings, 0)
        Clock.schedule_once(lambda dt: self.load_macros(), 1.0)
        Clock.schedule_once(lambda dt: self.add_message(
            "Welcome to Diet Tracker!\nTap 'Log Meal' to record your meals.", False), 0.5)
    
    def _setup_bindings(self, dt):
        """Setup bindings after widget is ready"""
        self.ids.chat_input.bind(on_text_validate=self.send_chat)
    
    def send_chat(self, instance):
        msg = self.ids.chat_input.text.strip()
        if not msg:
            return
        self.ids.chat_input.text = ""
        self.add_message(msg, True)
        self.add_message("Thinking...", False)
        threading.Thread(target=self._process_chat, args=(msg,), daemon=True).start()
    
    def _process_chat(self, msg):
        try:
            context = {
                'daily_macros': self.total_daily_macros,
                'daily_goals': self.daily_goal_macros,
                'meals_logged': getattr(self, 'meals_logged_today', []),
                'user_id': USER_ID
            } if hasattr(self, 'total_daily_macros') else None
            
            response = get_chat_response(msg, context)
            Clock.schedule_once(lambda dt: self.remove_last_message(), 0)
            Clock.schedule_once(lambda dt: self.add_message(response, False), 0)
        except Exception as e:
            traceback.print_exc()
            Clock.schedule_once(lambda dt: self.remove_last_message(), 0)
            Clock.schedule_once(lambda dt: self.add_message(
                "Sorry, I couldn't process that. Please try again.", False), 0)
    
    def load_macros(self):
        def load():
            try:
                db = init_firebase()
                if db is None:
                    Clock.schedule_once(lambda dt: self.ids.macros_header.set_data(
                        {'calories': 0, 'proteins': 0, 'carbs': 0, 'fats': 0},
                        {'calories': 2000, 'proteins': 150, 'carbs': 250, 'fats': 65}), 0)
                    return
                
                use_rest = isinstance(db, bool)
                today = datetime.date.today().strftime("%Y-%m-%d")
                
                if use_rest:
                    user_doc = get_user_doc(USER_ID)
                    meal_data = get_meal_doc(USER_ID, today) or {}
                else:
                    user_ref = db.collection('users').document(USER_ID)
                    user_doc = user_ref.get().to_dict() if user_ref.get().exists else None
                    meal_ref = db.collection('users').document(USER_ID).collection('mealLogs').document(today)
                    meal_data = meal_ref.get().to_dict() if meal_ref.get().exists else {}
                
                daily_goal = user_doc.get('daily_macros_goal', 
                    {'calories': 2000, 'proteins': 150, 'carbs': 250, 'fats': 65}) \
                    if user_doc else {'calories': 2000, 'proteins': 150, 'carbs': 250, 'fats': 65}
                
                consumed = {'calories': 0, 'proteins': 0, 'carbs': 0, 'fats': 0}
                
                if meal_data:
                    if 'macros_left' in meal_data and isinstance(meal_data['macros_left'], dict):
                        ml = meal_data['macros_left']
                        for key in consumed:
                            consumed[key] = daily_goal.get(key, 0) - ml.get(key, 0)
                    else:
                        for meal_type in ['breakfast', 'lunch', 'dinner', 'supper', 'snacks']:
                            if meal_type in meal_data and isinstance(meal_data[meal_type], dict):
                                m = meal_data[meal_type]
                                consumed['calories'] += int(m.get('calories') or m.get('Calories') or 0)
                                consumed['proteins'] += int(m.get('proteins') or m.get('Protein') or 0)
                                consumed['carbs'] += int(m.get('carbs') or m.get('Carbs') or 0)
                                consumed['fats'] += int(m.get('fats') or m.get('Fats') or 0)
                
                self.meals_logged_today = []
                if meal_data:
                    for meal_type in ['breakfast', 'lunch', 'dinner', 'supper', 'snacks']:
                        if meal_type in meal_data and isinstance(meal_data[meal_type], dict):
                            m = meal_data[meal_type]
                            # Check if meal has actual data
                            if m.get('calories') or m.get('Calories'):
                                self.meals_logged_today.append(meal_type)
                
                self.total_daily_macros = {k.capitalize(): v for k, v in consumed.items()}
                self.daily_goal_macros = {k.capitalize(): v for k, v in daily_goal.items()}
                
                Clock.schedule_once(lambda dt: self.ids.macros_header.set_data(consumed, daily_goal), 0)

            except:
                traceback.print_exc()
                Clock.schedule_once(lambda dt: self.ids.macros_header.set_data(
                    {'calories': 0, 'proteins': 0, 'carbs': 0, 'fats': 0},
                    {'calories': 2000, 'proteins': 150, 'carbs': 250, 'fats': 65}), 0)
        
        threading.Thread(target=load, daemon=True).start()
    
    def load_weekly_analytics(self):
        """Fetch 7 days of meal data"""
        try:
            db = init_firebase()
            if db is None:
                return None
            
            use_rest = isinstance(db, bool)
            today = datetime.date.today()
            data = {k: [] for k in ['calories', 'protein', 'carbs', 'fats', 'energy', 'hunger']}
            
            for i in range(6, -1, -1):
                date_str = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
                meal_data = get_meal_doc(USER_ID, date_str) if use_rest else \
                    (lambda ref: ref.get().to_dict() if ref.get().exists else {})(
                        db.collection('users').document(USER_ID).collection('mealLogs').document(date_str))
                
                day_totals = {'calories': 0, 'protein': 0, 'carbs': 0, 'fats': 0}
                energy_vals, hunger_vals = [], []
                
                if meal_data:
                    for meal_type in ['breakfast', 'lunch', 'dinner', 'supper', 'snacks']:
                        if meal_type in meal_data and isinstance(meal_data[meal_type], dict):
                            m = meal_data[meal_type]
                            day_totals['calories'] += int(m.get('calories') or m.get('Calories') or 0)
                            day_totals['protein'] += int(m.get('proteins') or m.get('Protein') or 0)
                            day_totals['carbs'] += int(m.get('carbs') or m.get('Carbs') or 0)
                            day_totals['fats'] += int(m.get('fats') or m.get('Fats') or 0)
                            if 'energy' in m and m['energy']:
                                energy_vals.append(int(m['energy']))
                            if 'hunger' in m and m['hunger']:
                                hunger_vals.append(int(m['hunger']))
                
                for key in day_totals:
                    data[key].append(day_totals[key])
                data['energy'].append(sum(energy_vals) // len(energy_vals) if energy_vals else 0)
                data['hunger'].append(sum(hunger_vals) // len(hunger_vals) if hunger_vals else 0)
            
            return data
        except:
            traceback.print_exc()
            return None

    def add_message(self, msg, is_user=False):
        self.ids.chat_history.add_widget(ChatBubble(msg, is_user=is_user))
        Clock.schedule_once(lambda dt: setattr(self.ids.scroll, 'scroll_y', 0), 0.1)
    
    def remove_last_message(self):
        if self.ids.chat_history.children:
            self.ids.chat_history.remove_widget(self.ids.chat_history.children[0])
    
    def open_navigation_popup(self, instance):
        """Open navigation popup instead of directly going to meal screen"""
        popup = NavigationPopup(self)
        popup.open()

# ==============================
# NAVIGATION POPUP
# ==============================
class NavigationPopup(Popup):
    def __init__(self, chat_screen, **kwargs):
        super().__init__(**kwargs)
        self.chat_screen = chat_screen
    
    def go_to_chat(self):
        # Already on chat screen, just close popup
        self.dismiss()
    
    def go_to_meal_logging(self):
        self.dismiss()
        App.get_running_app().root.clear_widgets()
        App.get_running_app().root.add_widget(MealLoggingScreen(self.chat_screen))
    
    def go_to_macro_goals(self):
        self.dismiss()
        App.get_running_app().root.clear_widgets()
        App.get_running_app().root.add_widget(UserMacroGoals(self.chat_screen))
    
    def go_to_recipe_generator(self):
        self.dismiss()
        App.get_running_app().root.clear_widgets()
        App.get_running_app().root.add_widget(RecipeGenerator(self.chat_screen))

# ==============================
# MEAL LOGGING SCREEN
# ==============================
class MealLoggingScreen(BoxLayout):
    def __init__(self, chat_screen, **kwargs):
        super().__init__(**kwargs)
        self.chat_screen = chat_screen
        self.selected_image = None
        self.food_description = ""
        self._logging_in_progress = False
        
        # Set initial meal type after widget is ready
        Clock.schedule_once(lambda dt: self.set_meal_type(chat_screen.current_meal_type), 0)
        
        # Bind text inputs to validation
        Clock.schedule_once(self._setup_validation, 0)
        
        self._request_permissions()
    
    def set_meal_type(self, meal_type):
        """Set the selected meal type and update button states"""
        self.selected_meal_type = meal_type.lower()
        
        # Update button colors
        meal_buttons = {
            'breakfast': self.ids.breakfast_btn,
            'lunch': self.ids.lunch_btn,
            'dinner': self.ids.dinner_btn,
            'supper': self.ids.supper_btn,
            'snacks': self.ids.snacks_btn
        }
        
        for meal, button in meal_buttons.items():
            if meal == self.selected_meal_type:
                # Selected state - bright green
                button.bg_color = get_color_from_hex("#B0CA87")
                button.color = get_color_from_hex("#1E2D2F")
            else:
                # Unselected state - darker
                button.bg_color = get_color_from_hex("#4A5A4B")
                button.color = get_color_from_hex("#BFD1E5")
    
    def _setup_validation(self, dt):
        """Setup validation for nutrition inputs"""
        # Start with button disabled
        self.ids.log_btn.disabled = True
        
        # Bind all inputs to validation using text property (NOT on_text_validate)
        for input_id in ['calories_input', 'proteins_input', 'carbs_input', 'fats_input']:
            input_field = self.ids[input_id].ids.input_field
            # Use text binding - works reliably on Android
            input_field.bind(text=lambda instance, value: self._validate_form(instance, value))

    def _validate_form(self, instance=None, value=None):
        """Enable log button if at least calories is filled"""
        # Defer validation to avoid focus conflicts
        Clock.schedule_once(self._do_validate, 0)

    def _do_validate(self, dt):
        """Actual validation logic - deferred to avoid focus conflicts"""
        try:
            calories_text = self.ids.calories_input.ids.input_field.text.strip()
            should_enable = bool(calories_text)
            
            # Only update if the state actually changed
            if self.ids.log_btn.disabled != (not should_enable):
                self.ids.log_btn.disabled = not should_enable
        except Exception as e:
            print(f"Validation error: {e}")
    
    def _request_permissions(self):
        if platform == 'android':
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([
                    Permission.READ_EXTERNAL_STORAGE, 
                    Permission.WRITE_EXTERNAL_STORAGE,
                    Permission.CAMERA
                ])
            except:
                pass
    
    def go_back(self, instance):
        App.get_running_app().root.clear_widgets()
        App.get_running_app().root.add_widget(self.chat_screen)

    def upload_image(self, *args):
        """
        Opens a fast native file chooser using Plyer.
        Works on Android/iOS/Windows/Linux/macOS.
        """
        try:
            filechooser.open_file(
                on_selection=self._on_file_selection,
                filters=["*.png", "*.jpg", "*.jpeg", "*.webp"]
            )
        except Exception as e:
            show_popup("Error", f"Could not open file chooser:\n{e}")

    def take_photo(self, *args):
        """
        Opens the device camera to capture a photo.
        Works on Android/iOS.
        """
        try:
            if platform == 'android':
                from android.permissions import request_permissions, Permission, check_permission
                
                # Check if permission is already granted
                if not check_permission(Permission.CAMERA):
                    # Request permission with callback
                    request_permissions([Permission.CAMERA], self._on_camera_permission_result)
                    return
                
                # Permission already granted, open camera
                Clock.schedule_once(lambda dt: self._open_camera_widget(), 0)
                
            else:
                # Desktop - show message
                show_popup("Camera", "Camera is only available on mobile devices")
                
        except Exception as e:
            show_popup("Camera Error", f"Could not open camera:\n{str(e)}")
            print(f"Full camera error: {e}")

    def _on_camera_permission_result(self, permissions, grant_results):
        """Callback when camera permission is granted/denied"""
        if all(grant_results):
            # Permission granted, open camera
            Clock.schedule_once(lambda dt: self._open_camera_widget(), 0)
        else:
            # Permission denied
            Clock.schedule_once(
                lambda dt: show_popup(
                    "Permission Denied", 
                    "Camera permission required.\nEnable in Settings."
                ), 0
            )

    def _open_camera_widget(self):
        """Open camera using Kivy Camera widget"""
        from kivy.uix.camera import Camera
        from kivy.uix.button import Button
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.floatlayout import FloatLayout
        from kivy.uix.popup import Popup
        from kivy.graphics import PushMatrix, PopMatrix, Rotate
        
        # Use FloatLayout for absolute positioning control
        camera_container = FloatLayout()
        
        # Create camera widget - force it to fill the container
        camera_widget = Camera(
            play=True, 
            resolution=(1280, 720), 
            index=0,
            size_hint=(None, None),  # Disable size hints for manual control
            allow_stretch=True
        )
        
        # Store rotation instruction
        rotation = Rotate(angle=270, origin=(0, 0))
        
        # Add rotation to camera
        with camera_widget.canvas.before:
            PushMatrix()
            camera_widget.canvas.before.add(rotation)
        with camera_widget.canvas.after:
            PopMatrix()
        
        def update_camera_transform(instance, value):
            """Update camera size and rotation to fill the container"""
            # Get container size (accounting for buttons at bottom)
            container_width = camera_container.width
            container_height = camera_container.height - 50  # Subtract button height
            
            # After 270° rotation, width becomes height and vice versa
            # So we need to swap dimensions for the camera widget
            camera_widget.width = container_height  # Will become height after rotation
            camera_widget.height = container_width  # Will become width after rotation
            
            # Position at center before rotation
            camera_widget.x = camera_container.x + (container_width - camera_widget.width) / 2
            camera_widget.y = camera_container.y + 50 + (container_height - camera_widget.height) / 2
            
            # Update rotation origin to camera center
            rotation.origin = (camera_widget.center_x, camera_widget.center_y)
        
        camera_container.bind(pos=update_camera_transform, size=update_camera_transform)
        
        # Add camera to container
        camera_container.add_widget(camera_widget)
        
        # Create button layout at the bottom
        button_layout = BoxLayout(
            size_hint=(1, None),
            height=50,
            pos_hint={'x': 0, 'y': 0}
        )
        
        # Create cancel button
        cancel_btn = Button(
            text='Cancel',
            background_color=(0.5, 0.5, 0.5, 1)
        )
        
        # Create capture button
        capture_btn = Button(
            text='Capture Photo',
            background_color=COLORS['accent1']
        )
        
        button_layout.add_widget(cancel_btn)
        button_layout.add_widget(capture_btn)
        camera_container.add_widget(button_layout)
        
        # Create fullscreen popup
        camera_popup = Popup(
            title='',
            content=camera_container,
            size_hint=(1, 1),
            auto_dismiss=False,
            separator_height=0,
            title_size=0
        )
        
        def capture_photo(instance):
            """Capture and save the photo"""
            try:
                if platform == 'android':
                    from android.storage import app_storage_path
                    temp_dir = app_storage_path()
                else:
                    temp_dir = os.path.expanduser("~")
                
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = os.path.join(temp_dir, f"camera_photo_{timestamp}.png")
                
                # Export camera texture to file
                camera_widget.export_to_png(filepath)
                
                # Stop camera and close popup
                camera_widget.play = False
                camera_popup.dismiss()
                
                print(f"Photo saved to: {filepath}")
                
                # Process the captured photo (same route as image upload)
                Clock.schedule_once(lambda dt: self._process_camera_photo(filepath), 0.1)
                
            except Exception as e:
                camera_widget.play = False
                camera_popup.dismiss()
                show_popup("Capture Error", f"Could not capture photo:\n{str(e)}")
                print(f"Capture error: {e}")
        
        def cancel_camera(instance):
            """Cancel and close camera"""
            camera_widget.play = False
            camera_popup.dismiss()
        
        # Bind button events
        capture_btn.bind(on_press=capture_photo)
        cancel_btn.bind(on_press=cancel_camera)
        
        # Open the popup
        camera_popup.open()
        
        # Force initial update
        Clock.schedule_once(lambda dt: update_camera_transform(camera_container, None), 0.1)

    def _process_camera_photo(self, filepath):
        """Process captured photo - runs on main Kivy thread"""
        # Check if file exists
        if not os.path.exists(filepath):
            show_popup("Camera Error", f"Photo file not found: {filepath}")
            return
        
        try:
            self.selected_image = filepath
            print("Photo saved to:", filepath)
            
            # Display preview
            self.ids.img_placeholder.opacity = 0
            self.ids.img_preview.source = filepath
            self.ids.img_preview.reload()
            
            # Load the image to get its actual dimensions
            from kivy.core.image import Image as CoreImage
            img = CoreImage(filepath)
            img_width, img_height = img.texture.size
            img_aspect = img_width / img_height
            
            # Get the container (FloatLayout) size
            container = self.ids.img_preview.parent
            container_width = container.width
            container_height = container.height
            
            # Calculate size that fits entirely in container
            if img_aspect > (container_width / container_height):
                # Image is wider - fit to width
                preview_width = container_width * 0.9
                preview_height = preview_width / img_aspect
            else:
                # Image is taller - fit to height
                preview_height = container_height * 0.9
                preview_width = preview_height * img_aspect
            
            # Set size and manually center it
            self.ids.img_preview.size = (preview_width, preview_height)
            self.ids.img_preview.pos = (
                container.x + (container_width - preview_width) / 2,
                container.y + (container_height - preview_height) / 2
            )
            self.ids.img_preview.opacity = 1
            
            # Auto-analyze the captured image
            Clock.schedule_once(lambda dt: self.auto_analyze_image(), 0.1)
            
        except Exception as e:
            show_popup("Preview Error", f"Could not process photo:\n{str(e)}")
            print(f"Full preview error: {e}")

    def _on_file_selection(self, selection):
        """
        Called when the user picks a file using Plyer.
        selection = list of selected file paths.
        """
        if not selection:
            return  # user cancelled

        path = selection[0]
        print("Selected image:", path)
        
        # Schedule all UI updates on the main thread
        Clock.schedule_once(lambda dt: self._process_selected_image(path), 0)

    def _process_selected_image(self, path):
        """Process selected image - runs on main Kivy thread"""
        self.selected_image = path

        # Try preview normally (works for Windows/Mac/Linux/Android for filesystem paths)
        if os.path.exists(path):
            try:
                self.ids.img_placeholder.opacity = 0
                self.ids.img_preview.source = path
                self.ids.img_preview.reload()
                
                # Load the image to get its actual dimensions
                from kivy.core.image import Image as CoreImage
                img = CoreImage(path)
                img_width, img_height = img.texture.size
                img_aspect = img_width / img_height
                
                # Get the container (FloatLayout) size
                container = self.ids.img_preview.parent
                container_width = container.width
                container_height = container.height
                
                # Calculate size that fits entirely in container
                if img_aspect > (container_width / container_height):
                    # Image is wider - fit to width
                    preview_width = container_width * 0.9  # 90% of container
                    preview_height = preview_width / img_aspect
                else:
                    # Image is taller - fit to height
                    preview_height = container_height * 0.9  # 90% of container
                    preview_width = preview_height * img_aspect
                
                # Set size and manually center it
                self.ids.img_preview.size = (preview_width, preview_height)
                self.ids.img_preview.pos = (
                    container.x + (container_width - preview_width) / 2,
                    container.y + (container_height - preview_height) / 2
                )
                self.ids.img_preview.opacity = 1

                Clock.schedule_once(lambda dt: self.auto_analyze_image(), 0.1)
                return
            except Exception as e:
                print("Failed preview:", e)

        # Android SAF: content:// URI (when user picks directly from Google Photos)
        if platform == "android" and path.startswith("content://"):
            self._load_android_uri(path)
            return

        # Otherwise, invalid
        show_popup("Invalid Image", "Could not load selected image. Try a different file.")

    def _load_android_uri(self, uri_path):
        """
        Loads Android SAF content:// URI into the preview widget.
        Also saves to local storage for analysis.
        """
        try:
            from jnius import autoclass
            from android.storage import app_storage_path
            
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            content_resolver = activity.getContentResolver()
            Uri = autoclass('android.net.Uri')
            uri = Uri.parse(uri_path)
            istream = content_resolver.openInputStream(uri)
            
            if istream is None:
                raise RuntimeError("Could not open content URI")
            
            # Read the image data
            data = io.BytesIO()
            buf = bytearray(8192)
            while True:
                read = istream.read(buf)
                if not read or read == -1:
                    break
                data.write(buf[:read])
            istream.close()
            data.seek(0)
            
            # Save to local file for analysis
            temp_dir = app_storage_path()
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            local_path = os.path.join(temp_dir, f"selected_image_{timestamp}.jpg")
            
            with open(local_path, 'wb') as f:
                f.write(data.getvalue())
            
            # Update the selected image path to the local file
            self.selected_image = local_path
            print(f"Image saved to: {local_path}")
            
            # Reset data stream for preview
            data.seek(0)
            
            # Create core image for preview
            from kivy.core.image import Image as CoreImage
            core_img = CoreImage(data, ext="jpg")
            
            def update_preview(dt):
                self.ids.img_placeholder.opacity = 0
                
                # Get texture dimensions
                img_width, img_height = core_img.texture.size
                img_aspect = img_width / img_height
                
                # Get container size
                container = self.ids.img_preview.parent
                container_width = container.width
                container_height = container.height
                
                # Calculate fitted size
                if img_aspect > (container_width / container_height):
                    preview_width = container_width * 0.9
                    preview_height = preview_width / img_aspect
                else:
                    preview_height = container_height * 0.9
                    preview_width = preview_height * img_aspect
                
                # Apply texture and position
                self.ids.img_preview.texture = core_img.texture
                self.ids.img_preview.size = (preview_width, preview_height)
                self.ids.img_preview.pos = (
                    container.x + (container_width - preview_width) / 2,
                    container.y + (container_height - preview_height) / 2
                )
                self.ids.img_preview.opacity = 1
            
            Clock.schedule_once(update_preview, 0)
            Clock.schedule_once(lambda dt: self.auto_analyze_image(), 0.1)
            
        except Exception as e:
            print("URI load error:", e)
            import traceback
            traceback.print_exc()
            show_popup("Preview Error", f"Failed to load image:\n{str(e)}")


    def auto_analyze_image(self):
        """Automatically analyze uploaded image and populate form"""
        if not self.selected_image:
            return
        
        # Prevent duplicate calls
        if hasattr(self, '_analyzing') and self._analyzing:
            return
        
        self._analyzing = True
        self.ids.status_label.text = "Analyzing image... (10-30 seconds)"
        self.ids.status_label.color = COLORS['accent1']
        self.ids.log_btn.disabled = True
        
        # Clear previous values ONLY if fields don't have focus
        for input_id in ['calories_input', 'proteins_input', 'carbs_input', 'fats_input']:
            field = self.ids[input_id].ids.input_field
            if not field.focus:  # Only clear if not being edited
                field.text = ""
        
        # Clear description field ONLY if it doesn't have focus
        if hasattr(self.ids, 'description_input'):
            text_field = self.ids.description_input.ids.text_input
            if not text_field.focus:  # Only clear if not being edited
                text_field.text = ""
        
        def analyze():
            try:                
                # Get both nutrition and description
                nutrition = estimate_nutrition(self.selected_image)
                description = describe_food(self.selected_image)
                
                if not nutrition:
                    Clock.schedule_once(lambda dt: self._handle_analysis_failure(), 0)
                    self._analyzing = False
                    return
                
                def update_form(dt):
                    """Safer update: small delay helps keyboard animation complete"""
                    try:
                        # Update nutrition fields - CRITICAL FIXES:
                        # 1. Don't change text if it's already the same
                        # 2. Don't update focused fields
                        # 3. NEVER set field.focus = False
                        fields = {
                            "calories_input": str(nutrition.get("Calories", 0)),
                            "proteins_input": str(nutrition.get("Protein", 0)),
                            "carbs_input": str(nutrition.get("Carbs", 0)),
                            "fats_input": str(nutrition.get("Fats", 0)),
                        }

                        for field_id, value in fields.items():
                            field = self.ids[field_id].ids.input_field
                            # Only update if: not focused AND value is different
                            if not getattr(field, "focus", False) and field.text != value:
                                field.text = value

                        # Set description if available
                        if description and hasattr(self.ids, 'description_input'):
                            text_input = self.ids.description_input.ids.text_input
                            if not getattr(text_input, "focus", False) and text_input.text != description:
                                text_input.text = description
                                self.food_description = description
                                print(f"Description set: {description}")

                        # Defer UI status changes a tiny bit to be safe
                        Clock.schedule_once(lambda dt: setattr(self.ids.status_label, 'text',
                                                            "✓ Analysis complete! Review and edit if needed."), 0.02)
                        Clock.schedule_once(lambda dt: setattr(self.ids.status_label, 'color',
                                                            (0.2, 0.8, 0.3, 1)), 0.02)
                        Clock.schedule_once(lambda dt: setattr(self.ids.log_btn, 'disabled', False), 0.02)

                        self._analyzing = False

                    except Exception as e:
                        print(f"Error updating form: {e}")
                        traceback.print_exc()
                        self._analyzing = False

                # Schedule update with a slightly larger delay to avoid keyboard race
                Clock.schedule_once(update_form, 0.12)

                
            except Exception as e:
                traceback.print_exc()
                error_msg = str(e)
                Clock.schedule_once(lambda dt: self._handle_analysis_failure(error_msg), 0)
                self._analyzing = False
        
        threading.Thread(target=analyze, daemon=True).start()

    def _handle_analysis_failure(self, error=""):
        """Handle analysis failure"""
        self.ids.status_label.text = "Analysis failed. Please enter values manually."
        self.ids.status_label.color = (0.9, 0.3, 0.3, 1)
        self.ids.log_btn.disabled = False
        self._analyzing = False
        if error:
            show_popup("Analysis Error", f"Could not analyze image: {error}")
    
    def log_meal(self, instance):
        """Log the meal with current form values"""
        # Prevent duplicate calls to log_meal itself
        if hasattr(self, '_logging_in_progress') and self._logging_in_progress:
            print("[DEBUG] Meal logging already in progress")
            return
        
        meal_type = self.selected_meal_type
        
        if not self.ids.calories_input.ids.input_field.text.strip():
            show_popup("Missing Information", "Please enter at least the calories value!")
            return
        
        try:
            nutrition = {
                "Calories": int(float(self.ids.calories_input.ids.input_field.text or 0)),
                "Protein": int(float(self.ids.proteins_input.ids.input_field.text or 0)),
                "Carbs": int(float(self.ids.carbs_input.ids.input_field.text or 0)),
                "Fats": int(float(self.ids.fats_input.ids.input_field.text or 0))
            }
        except ValueError:
            show_popup("Invalid Input", "Please enter valid numbers for all fields!")
            return
        
        self._logging_in_progress = True  # Set flag before opening popup
        self.ids.log_btn.disabled = True
        self.ids.status_label.text = "Logging meal..."
        self.ids.status_label.color = COLORS['accent1']
        
        def on_survey(energy, hunger):
            nutrition["energy"], nutrition["hunger"] = energy, hunger
            today = datetime.date.today().strftime("%Y-%m-%d")
            success = upload_meal(USER_ID, meal_type, nutrition, today)
            
            if success:
                self._handle_successful_log(meal_type, nutrition, energy, hunger)
            else:
                self._logging_in_progress = False  # Reset on failure
                Clock.schedule_once(lambda dt: (
                    show_popup("Upload Failed", 
                        "Could not save meal data. Please check your connection."),
                    setattr(self.ids.status_label, 'text', "Upload failed. Try again."),
                    setattr(self.ids.status_label, 'color', (0.9, 0.3, 0.3, 1)),
                    setattr(self.ids.log_btn, 'disabled', False)), 0)
        
        MealSurveyPopup(callback=on_survey).open()
    
    def _handle_successful_log(self, meal_type, nutrition, energy, hunger):
        """Handle successful meal logging"""
        self.ids.status_label.text = "✓ Meal logged successfully!"
        self.ids.status_label.color = (0.2, 0.8, 0.3, 1)
        self.chat_screen.current_meal_type = meal_type
        
        # Get description from text field if available
        description = ""
        if hasattr(self.ids, 'description_input'):
            description = self.ids.description_input.ids.text_input.text.strip()
        
        # Build result message
        result = f"{meal_type.capitalize()} logged:\n"
        if description:
            result += f"📝 {description}\n\n"
        result += (f"Calories: {nutrition.get('Calories')} kcal\n"
                f"Protein: {nutrition.get('Protein')} g\n"
                f"Carbs: {nutrition.get('Carbs')} g\n"
                f"Fats: {nutrition.get('Fats')} g\n"
                f"Energy: {energy}/5\nHunger: {hunger}/5")
        
        Clock.schedule_once(lambda dt: self.chat_screen.add_message(result, False), 0)
        Clock.schedule_once(lambda dt: self.chat_screen.load_macros(), 1.5)
        
        # Generate tips
        Clock.schedule_once(lambda dt: self.chat_screen.add_message("Generating tips...", False), 0)
        
        def tips():
            try:
                time.sleep(1.0)
                advice = handle_logged_meal(meal_type, nutrition, 
                                            self.chat_screen.daily_goal_macros,
                                            energy, hunger)
                Clock.schedule_once(lambda dt: self.chat_screen.remove_last_message(), 0)
                msg = advice.strip() if advice else "All nutrients within range."
                Clock.schedule_once(lambda dt: self.chat_screen.add_message(msg, False), 0)
            except:
                traceback.print_exc()
                Clock.schedule_once(lambda dt: self.chat_screen.remove_last_message(), 0)
            finally:
                # Reset flag after tips complete
                Clock.schedule_once(lambda dt: setattr(self, '_logging_in_progress', False), 0)
        
        threading.Thread(target=tips, daemon=True).start()
        
        Clock.schedule_once(lambda dt: self.go_back(None), 2.5)

# ==============================
# MEAL SURVEY POPUP
# ==============================
class MealSurveyPopup(Popup):
    def __init__(self, callback, **kwargs):
        super().__init__(**kwargs)
        self.callback = callback
        self.energy_value = None
        self.hunger_value = None
        self._submitted = False  # ADD THIS FLAG
        
        # Create buttons after popup is built
        Clock.schedule_once(self._create_buttons, 0)
    
    def _create_buttons(self, dt):
        # Energy buttons
        energy_layout = self.ids.energy_layout
        self.energy_buttons = []
        for i in range(1, 6):
            btn = Button(text=str(i), background_color=(0.5, 0.5, 0.5, 1), 
                        font_size='18sp', bold=True)
            btn.bind(on_press=lambda x, val=i: self.select_energy(val))
            self.energy_buttons.append(btn)
            energy_layout.add_widget(btn)
        
        # Hunger buttons
        hunger_layout = self.ids.hunger_layout
        self.hunger_buttons = []
        for i in range(1, 6):
            btn = Button(text=str(i), background_color=(0.5, 0.5, 0.5, 1), 
                        font_size='18sp', bold=True)
            btn.bind(on_press=lambda x, val=i: self.select_hunger(val))
            self.hunger_buttons.append(btn)
            hunger_layout.add_widget(btn)
    
    def select_energy(self, value):
        self.energy_value = value
        for i, btn in enumerate(self.energy_buttons, 1):
            btn.background_color = (0.2, 0.6, 1, 1) if i == value else (0.5, 0.5, 0.5, 1)
    
    def select_hunger(self, value):
        self.hunger_value = value
        for i, btn in enumerate(self.hunger_buttons, 1):
            btn.background_color = (0.2, 0.6, 1, 1) if i == value else (0.5, 0.5, 0.5, 1)
    
    def submit(self, instance):
        # CRITICAL FIX: Prevent duplicate submissions
        if self._submitted:
            print("[DEBUG] Survey already submitted, ignoring duplicate call")
            return
        
        if self.energy_value is None or self.hunger_value is None:
            show_popup("Incomplete Selection", 
                      "Please select both Energy and Hunger levels")
            return
        
        # Mark as submitted BEFORE calling callback
        self._submitted = True
        
        # Call the callback
        self.callback(self.energy_value, self.hunger_value)
        
        # Dismiss the popup
        self.dismiss()

# ==============================
# USER MACRO GOALS SCREEN
# ==============================
class UserMacroGoals(BoxLayout):
    def __init__(self, chat_screen, **kwargs):
        super().__init__(**kwargs)
        self.chat_screen = chat_screen
        self.load_current_goals()
    
    def load_current_goals(self):
        """Load current macro goals from Firebase and populate fields"""
        def load():
            try:
                user_doc = get_user_doc(USER_ID)
                if user_doc and 'daily_macros_goal' in user_doc:
                    goals = user_doc['daily_macros_goal']
                    Clock.schedule_once(lambda dt: self._populate_fields(goals), 0)
            except Exception as e:
                print(f"Error loading macro goals: {e}")
                traceback.print_exc()
        
        threading.Thread(target=load, daemon=True).start()
    
    def _populate_fields(self, goals):
        """Populate input fields with current goals"""
        if 'calories' in goals:
            self.ids.calories_input.ids.input_field.text = str(goals['calories'])
        if 'proteins' in goals:
            self.ids.proteins_input.ids.input_field.text = str(goals['proteins'])
        if 'carbs' in goals:
            self.ids.carbs_input.ids.input_field.text = str(goals['carbs'])
        if 'fats' in goals:
            self.ids.fats_input.ids.input_field.text = str(goals['fats'])
    
    def save_goals(self, instance):
        """Save macro goals to Firebase"""
        # Get values from input fields
        calories_text = self.ids.calories_input.ids.input_field.text.strip()
        proteins_text = self.ids.proteins_input.ids.input_field.text.strip()
        carbs_text = self.ids.carbs_input.ids.input_field.text.strip()
        fats_text = self.ids.fats_input.ids.input_field.text.strip()
        
        # Build update dict - only include non-empty fields
        updates = {}
        if calories_text:
            try:
                updates['calories'] = int(float(calories_text))
            except ValueError:
                pass
        
        if proteins_text:
            try:
                updates['proteins'] = int(float(proteins_text))
            except ValueError:
                pass
        
        if carbs_text:
            try:
                updates['carbs'] = int(float(carbs_text))
            except ValueError:
                pass
        
        if fats_text:
            try:
                updates['fats'] = int(float(fats_text))
            except ValueError:
                pass
        
        # If no valid updates, show message and return
        if not updates:
            self.show_status("No changes to save", error=True)
            return
        
        # Disable save button during upload
        self.ids.save_btn.disabled = True
        self.ids.save_btn.text = "Saving..."
        
        # Upload in background thread
        def upload():
            try:
                success = update_macro_goals(USER_ID, updates)
                if success:
                    Clock.schedule_once(lambda dt: self.show_status("Goals saved successfully!", error=False), 0)
                    Clock.schedule_once(lambda dt: self.chat_screen.load_macros(), 0.5)
                else:
                    Clock.schedule_once(lambda dt: self.show_status("Failed to save goals", error=True), 0)
            except Exception as e:
                print(f"Error saving goals: {e}")
                traceback.print_exc()
                Clock.schedule_once(lambda dt: self.show_status("Error saving goals", error=True), 0)
            finally:
                Clock.schedule_once(lambda dt: self._reset_button(), 0)
        
        threading.Thread(target=upload, daemon=True).start()
    
    def _reset_button(self):
        """Reset save button state"""
        self.ids.save_btn.disabled = False
        self.ids.save_btn.text = "Save Goals"
    
    def show_status(self, message, error=False):
        """Show status message"""
        self.ids.status_label.text = message
        self.ids.status_label.color = get_color_from_hex("#FF6B6B") if error else get_color_from_hex("#B0CA87")
        # Clear message after 3 seconds
        Clock.schedule_once(lambda dt: setattr(self.ids.status_label, 'text', ''), 3)
    
    def go_back(self, instance):
        """Return to chat screen"""
        App.get_running_app().root.clear_widgets()
        App.get_running_app().root.add_widget(self.chat_screen)

# =============================
# RECIPE GENERATOR SCREEN
# =============================
def _display_image(self, filepath):
    """Display selected image"""
    try:
        self.current_image_path = filepath
        
        # Hide placeholder
        self.ids.img_placeholder.opacity = 0
        
        # Load image source
        self.ids.img_preview.source = filepath
        self.ids.img_preview.reload()
        
        # Load the image to get its actual dimensions
        from kivy.core.image import Image as CoreImage
        img = CoreImage(filepath)
        img_width, img_height = img.texture.size
        img_aspect = img_width / img_height
        
        # Get the container (FloatLayout) size
        container = self.ids.img_preview.parent
        container_width = container.width
        container_height = container.height
        
        # Calculate size that fits entirely in container
        if img_aspect > (container_width / container_height):
            # Image is wider - fit to width
            preview_width = container_width * 0.9  # 90% of container
            preview_height = preview_width / img_aspect
        else:
            # Image is taller - fit to height
            preview_height = container_height * 0.9  # 90% of container
            preview_width = preview_height * img_aspect
        
        # Set size and manually center it
        self.ids.img_preview.size = (preview_width, preview_height)
        self.ids.img_preview.pos = (
            container.x + (container_width - preview_width) / 2,
            container.y + (container_height - preview_height) / 2
        )
        self.ids.img_preview.opacity = 1
        
        self.show_status("Image loaded successfully")
        
    except Exception as e:
        print(f"[Recipe] Error displaying image: {e}")
        traceback.print_exc()
        self.show_status("Failed to display image", error=True)


# ============================================
# COMPLETE UPDATED RecipeGenerator CLASS
# ============================================


class RecipeGenerator(BoxLayout):
    def __init__(self, chat_screen, **kwargs):
        super().__init__(**kwargs)
        self.chat_screen = chat_screen
        self.current_image_path = None
    
    def take_photo(self, instance):
        """Take a photo using camera"""
        try:
            if platform == 'android':
                from android.permissions import request_permissions, Permission, check_permission
                
                if not check_permission(Permission.CAMERA):
                    request_permissions([Permission.CAMERA], self._on_camera_permission_result)
                    return
                
                Clock.schedule_once(lambda dt: self._open_camera_widget(), 0)
                
            else:
                self.show_status("Camera is only available on mobile devices", error=True)
                
        except Exception as e:
            print(f"[Recipe] Camera error: {e}")
            self.show_status("Failed to open camera", error=True)
    
    def _on_camera_permission_result(self, permissions, grant_results):
        """Callback when camera permission is granted/denied"""
        if all(grant_results):
            Clock.schedule_once(lambda dt: self._open_camera_widget(), 0)
        else:
            Clock.schedule_once(
                lambda dt: self.show_status(
                    "Camera permission required. Enable in Settings.", 
                    error=True
                ), 0
            )
    
    def _open_camera_widget(self):
        """Open camera using Kivy Camera widget"""
        from kivy.uix.camera import Camera
        from kivy.uix.button import Button
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.floatlayout import FloatLayout
        from kivy.uix.popup import Popup
        from kivy.graphics import PushMatrix, PopMatrix, Rotate
        
        camera_container = FloatLayout()
        
        camera_widget = Camera(
            play=True, 
            resolution=(1280, 720), 
            index=0,
            size_hint=(None, None),
            allow_stretch=True
        )
        
        rotation = Rotate(angle=270, origin=(0, 0))
        
        with camera_widget.canvas.before:
            PushMatrix()
            camera_widget.canvas.before.add(rotation)
        with camera_widget.canvas.after:
            PopMatrix()
        
        def update_camera_transform(instance, value):
            container_width = camera_container.width
            container_height = camera_container.height - 50
            
            camera_widget.width = container_height
            camera_widget.height = container_width
            
            camera_widget.x = camera_container.x + (container_width - camera_widget.width) / 2
            camera_widget.y = camera_container.y + 50 + (container_height - camera_widget.height) / 2
            
            rotation.origin = (camera_widget.center_x, camera_widget.center_y)
        
        camera_container.bind(pos=update_camera_transform, size=update_camera_transform)
        camera_container.add_widget(camera_widget)
        
        button_layout = BoxLayout(
            size_hint=(1, None),
            height=50,
            pos_hint={'x': 0, 'y': 0}
        )
        
        cancel_btn = Button(
            text='Cancel',
            background_color=(0.5, 0.5, 0.5, 1)
        )
        
        capture_btn = Button(
            text='Capture Photo',
            background_color=get_color_from_hex("#809848")
        )
        
        button_layout.add_widget(cancel_btn)
        button_layout.add_widget(capture_btn)
        camera_container.add_widget(button_layout)
        
        camera_popup = Popup(
            title='',
            content=camera_container,
            size_hint=(1, 1),
            auto_dismiss=False,
            separator_height=0,
            title_size=0
        )
        
        def capture_photo(instance):
            try:
                if platform == 'android':
                    from android.storage import app_storage_path
                    temp_dir = app_storage_path()
                else:
                    temp_dir = os.path.expanduser("~")
                
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = os.path.join(temp_dir, f"recipe_photo_{timestamp}.png")
                
                camera_widget.export_to_png(filepath)
                camera_widget.play = False
                camera_popup.dismiss()
                
                print(f"Photo saved to: {filepath}")
                Clock.schedule_once(lambda dt: self._display_image(filepath), 0.1)
                
            except Exception as e:
                camera_widget.play = False
                camera_popup.dismiss()
                self.show_status(f"Could not capture photo: {str(e)}", error=True)
                print(f"Capture error: {e}")
        
        def cancel_camera(instance):
            camera_widget.play = False
            camera_popup.dismiss()
        
        capture_btn.bind(on_press=capture_photo)
        cancel_btn.bind(on_press=cancel_camera)
        
        camera_popup.open()
        Clock.schedule_once(lambda dt: update_camera_transform(camera_container, None), 0.1)
    
    def upload_image(self, instance):
        """Upload an image from gallery"""
        try:
            if platform == 'android':
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.READ_EXTERNAL_STORAGE])
            filechooser.open_file(on_selection=self.on_file_selected, filters=['*.jpg', '*.png', '*.jpeg'])
        except Exception as e:
            print(f"[Recipe] File chooser error: {e}")
            traceback.print_exc()
            self.show_status("Failed to open file chooser", error=True)
    
    def on_file_selected(self, selection):
        """Handle file selection"""
        if selection:
            Clock.schedule_once(lambda dt: self._display_image(selection[0]), 0)
    
    def _display_image(self, filepath):
        """Display selected image"""
        try:
            self.current_image_path = filepath
            
            self.ids.img_placeholder.opacity = 0
            self.ids.img_preview.source = filepath
            self.ids.img_preview.reload()
            
            from kivy.core.image import Image as CoreImage
            img = CoreImage(filepath)
            img_width, img_height = img.texture.size
            img_aspect = img_width / img_height
            
            container = self.ids.img_preview.parent
            container_width = container.width
            container_height = container.height
            
            if img_aspect > (container_width / container_height):
                preview_width = container_width * 0.9
                preview_height = preview_width / img_aspect
            else:
                preview_height = container_height * 0.9
                preview_width = preview_height * img_aspect
            
            self.ids.img_preview.size = (preview_width, preview_height)
            self.ids.img_preview.pos = (
                container.x + (container_width - preview_width) / 2,
                container.y + (container_height - preview_height) / 2
            )
            self.ids.img_preview.opacity = 1
            
            self.show_status("Image loaded successfully")
            
        except Exception as e:
            print(f"[Recipe] Error displaying image: {e}")
            traceback.print_exc()
            self.show_status("Failed to display image", error=True)
    
    def generate_recipe(self, instance):
        """Generate recipe based on text and/or image input"""
        text_prompt = self.ids.recipe_input.ids.text_input.text.strip()
        has_image = self.current_image_path is not None
        
        if not text_prompt and not has_image:
            self.show_status("Please provide a text prompt or upload an image of ingredients", error=True)
            return
        
        # Show generating status
        self.show_status("Generating recipe... (10-30 seconds)")
        self.ids.generate_btn.disabled = True
        self.ids.generate_btn.text = "Generating..."
        
        # Process in background thread
        threading.Thread(target=self._process_recipe_request, args=(text_prompt, has_image), daemon=True).start()
    
    def _process_recipe_request(self, text_prompt, has_image):
        """Process the recipe generation request"""
        try:
            # Case 1: Image only
            if has_image and not text_prompt:
                Clock.schedule_once(lambda dt: self._handle_image_only(), 0)
            
            # Case 2: Text only
            elif text_prompt and not has_image:
                response = get_recipe_from_text(text_prompt)
                Clock.schedule_once(lambda dt: self._display_response(response), 0)
            
            # Case 3: Both text and image
            elif text_prompt and has_image:
                response = get_recipe_from_text_and_image(text_prompt, self.current_image_path)
                Clock.schedule_once(lambda dt: self._display_response(response), 0)
        
        except Exception as e:
            print(f"[Recipe] Error generating recipe: {e}")
            traceback.print_exc()
            Clock.schedule_once(lambda dt: self._display_response("Failed to generate recipe. Please try again."), 0)
        finally:
            Clock.schedule_once(lambda dt: self._reset_button(), 0)
    
    def _handle_image_only(self):
        """Handle case where only image is provided"""
        self.show_status("Analyzing image...")
        
        def analyze():
            try:
                description = describe_food(self.current_image_path)
                
                if description and any(word in description.lower() for word in ['ingredient', 'vegetable', 'produce', 'raw', 'fresh']):
                    recipe = get_recipe_from_image(self.current_image_path)
                    Clock.schedule_once(lambda dt: self._display_response(recipe), 0)
                else:
                    message = f"Image description: {description}\n\nThis doesn't appear to be ingredients. Please provide a text prompt describing what recipe you'd like to generate."
                    Clock.schedule_once(lambda dt: self._display_response(message), 0)
            except Exception as e:
                print(f"[Recipe] Error analyzing image: {e}")
                traceback.print_exc()
                Clock.schedule_once(lambda dt: self._display_response("Failed to analyze image. Please try again or add a text prompt."), 0)
            finally:
                Clock.schedule_once(lambda dt: self._reset_button(), 0)
        
        threading.Thread(target=analyze, daemon=True).start()
    
    def _display_response(self, response):
        """Display the generated recipe in a popup"""
        RecipePopup(recipe_text=response).open()
        self.show_status("Recipe generated successfully")
    
    def _reset_button(self):
        """Reset generate button state"""
        self.ids.generate_btn.disabled = False
        self.ids.generate_btn.text = "Generate Recipe"
    
    def show_status(self, message, error=False):
        """Show status message"""
        self.ids.status_label.text = message
        self.ids.status_label.color = get_color_from_hex("#FF6B6B") if error else get_color_from_hex("#B0CA87")
    
    def go_back(self, instance):
        """Return to chat screen"""
        App.get_running_app().root.clear_widgets()
        App.get_running_app().root.add_widget(self.chat_screen)

class RecipePopup(Popup):
    recipe_text = StringProperty("") 

    def __init__(self, recipe_text, **kwargs):
        super().__init__(**kwargs)
        self.recipe_text = recipe_text

# ==============================
# MAIN APP
# ==============================
class DietChatApp(App):
    def build(self):
        self.title = "Diet Tracker"
        self.loading = LoadingScreen()
        Clock.schedule_once(lambda dt: self.init_app(), 0.1)
        return self.loading
    
    def init_app(self):
        def init():
            try:
                Clock.schedule_once(lambda dt: self.loading.update_status(
                    "Connecting to Firebase...", 20), 0)
                db = init_firebase()
                if db is None:
                    print("[WARNING] Firebase failed, continuing...")
                
                Clock.schedule_once(lambda dt: self.loading.update_status(
                    "Loading AI model... (30-60 sec)", 50), 0)
                load_model()
                
                Clock.schedule_once(lambda dt: self.loading.update_status(
                    "Model loaded ✓", 90), 0)
                Clock.schedule_once(lambda dt: self.loading.update_status(
                    "Starting app...", 95), 0)
                Clock.schedule_once(lambda dt: self.switch_to_main(), 0.5)
            except:
                traceback.print_exc()
                Clock.schedule_once(lambda dt: self.loading.update_status(
                    "Error occurred", 0), 0)
        
        threading.Thread(target=init, daemon=True).start()
    
    def switch_to_main(self):
        self.loading.update_status("Ready!", 100)
        self.root.clear_widgets()
        self.root.add_widget(ChatScreen())

if __name__ == "__main__":
    DietChatApp().run()