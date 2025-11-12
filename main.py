from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.core.text import Label as CoreLabel
from kivy.uix.widget import Widget
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.uix.slider import Slider
from kivy.uix.progressbar import ProgressBar
from kivy.graphics import Color, RoundedRectangle, Ellipse, Rectangle
from kivy.utils import get_color_from_hex
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.uix.spinner import Spinner
import math
import threading
import time
import traceback
import datetime

from chatbot import load_model, estimate_nutrition, handle_logged_meal, get_chat_response
from upload import upload_meal, init_firebase, get_user_doc, get_meal_doc

# Config
main_colour = get_color_from_hex("#1E2D2F")
text_colour = get_color_from_hex("#BFD1E5")
accent1_colour = get_color_from_hex("#809848")
accent2_colour = get_color_from_hex("#B0CA87")
accent3_colour = get_color_from_hex("#7D4E57")
Window.clearcolor = main_colour

USER_ID = "user"
PROJECT_ID = "diet-app-sg"
FIREBASE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"

# ==============================
# LOADING SCREEN
# ==============================
class LoadingScreen(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        with self.canvas.before:
            Color(*main_colour)
            self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)
        
        container = BoxLayout(orientation="vertical", spacing=20, size_hint=(0.6, 0.4), pos_hint={"center_x": 0.5, "center_y": 0.5})
        
        container.add_widget(Label(text="Diet Tracker", font_size=32, bold=True, color=accent2_colour, size_hint_y=0.3))
        
        self.status_label = Label(text="Initializing...", font_size=18, color=text_colour, size_hint_y=0.2)
        container.add_widget(self.status_label)
        
        self.progress = ProgressBar(max=100, value=0, size_hint_y=0.2)
        container.add_widget(self.progress)
        
        container.add_widget(Label(text="Tip: First load may take 30-60 seconds", font_size=14, color=get_color_from_hex("#808080"), size_hint_y=0.2))
        
        self.add_widget(container)
    
    def _update_bg(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
    
    def update_status(self, status, progress):
        self.status_label.text = status
        self.progress.value = progress

# ==============================
# CHAT BUBBLE
# ==============================
class ChatBubble(BoxLayout):
    def __init__(self, text, is_user=False, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, **kwargs)
        self.is_user = is_user
        
        self.size_hint_x = 1
        self.padding = [Window.width * 0.1, 5, 10, 5] if is_user else [10, 5, Window.width * 0.1, 5]
        Window.bind(width=self._update_padding)
        
        bubble = BoxLayout(size_hint_y=None, size_hint_x=1, padding=15)
        
        with bubble.canvas.before:
            Color(*(accent3_colour if is_user else accent1_colour))
            self.rect = RoundedRectangle(radius=[15], pos=bubble.pos, size=bubble.size)
        
        bubble.bind(pos=self._update_rect, size=self._update_rect)
        
        label = Label(text=text, color=text_colour, halign="left", valign="top", size_hint=(1, None), markup=True, text_size=(None, None))
        
        bubble.bind(width=lambda i, v: setattr(label, 'text_size', (bubble.width - 30, None)))
        label.bind(texture_size=lambda i, v: self._update_heights(label, bubble, v))
        
        bubble.add_widget(label)
        self.add_widget(bubble)
        
        self.bubble = bubble
        self.label = label
        label.text_size = (Window.width * 0.9 - 50, None)
    
    def _update_heights(self, label, bubble, value):
        label.height = value[1] + 10
        bubble.height = label.height + 30
        self.height = bubble.height + 10
    
    def _update_padding(self, instance, width):
        self.padding = [width * 0.1, 5, 10, 5] if self.is_user else [10, 5, width * 0.1, 5]
        if hasattr(self, 'label'):
            self.label.text_size = (width * 0.9 - 50, None)
    
    def _update_rect(self, instance, *args):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

# ==============================
# PIE CHART
# ==============================
class PieChart(Widget):
    def __init__(self, consumed, remaining, calorie_goal, **kwargs):
        super().__init__(**kwargs)
        self.consumed = consumed
        self.remaining = remaining
        self.calorie_goal = calorie_goal
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
        
        if self.remaining < 0:
            total = self.calorie_goal + abs(self.remaining) or 1
            segments = [
                {'angle': (self.calorie_goal / total) * 360, 'color': (1, 0.9, 0.43, 1), 'label': f'Goal\n{int(self.calorie_goal)}'},
                {'angle': (abs(self.remaining) / total) * 360, 'color': (1, 0.42, 0.42, 1), 'label': f'Over\n{int(abs(self.remaining))}'}
            ]
        else:
            total = self.consumed + self.remaining or 1
            segments = [
                {'angle': (self.consumed / total) * 360, 'color': (0.31, 0.80, 0.77, 1), 'label': f'Consumed\n{int(self.consumed)}'},
                {'angle': (self.remaining / total) * 360, 'color': (0.88, 0.88, 0.88, 1), 'label': f'Remaining\n{int(self.remaining)}'}
            ]
        
        cx, cy = self.x + self.width / 2, self.y + self.height / 2
        radius = min(self.width, self.height) / 2.0
        
        start_angle = 90
        with self.canvas:
            for seg in segments:
                Color(*seg['color'])
                Ellipse(pos=(cx - radius, cy - radius), size=(radius * 2, radius * 2), angle_start=start_angle, angle_end=start_angle + seg['angle'])
                start_angle += seg['angle']
        
        start_angle = 90
        for seg in segments:
            mid_angle = start_angle + seg['angle'] / 2
            label_x = cx + radius * 0.6 * math.cos(math.radians(mid_angle))
            label_y = cy + radius * 0.6 * math.sin(math.radians(mid_angle))
            
            text_label = CoreLabel(text=seg['label'], font_size=12, bold=True, halign='center', valign='middle')
            text_label.refresh()
            
            with self.canvas.after:
                Color(0, 0, 0, 1)
                Rectangle(texture=text_label.texture, pos=(label_x - text_label.width / 2, label_y - text_label.height / 2), size=text_label.size)
            
            start_angle += seg['angle']

# ==============================
# MACROS HEADER
# ==============================
class MacrosHeader(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=200, padding=15, spacing=15, **kwargs)
        
        with self.canvas.before:
            Color(*accent2_colour)
            self.rect = RoundedRectangle(radius=[10], pos=self.pos, size=self.size)
        self.bind(pos=self._update_rect, size=self._update_rect)
        
        # Left: Pie chart
        left = BoxLayout(orientation='vertical', size_hint_x=0.45, spacing=5)
        left.add_widget(Label(text="Daily Calories", color=get_color_from_hex("#000000"), font_size=16, bold=True, size_hint_y=0.2))
        self.pie_container = FloatLayout(size_hint=(1, 0.8))
        left.add_widget(self.pie_container)
        
        # Right: Progress bars
        right = BoxLayout(orientation='vertical', size_hint_x=0.55, spacing=10, padding=[10, 5])
        right.add_widget(Label(text="Macros Progress", color=get_color_from_hex("#000000"), font_size=16, bold=True, size_hint_y=0.15))
        
        macros = BoxLayout(orientation='vertical', spacing=8, size_hint_y=0.85)
        self.protein_bar = self._create_bar("Protein", "#FF6B6B")
        self.carbs_bar = self._create_bar("Carbs", "#4ECDC4")
        self.fats_bar = self._create_bar("Fats", "#FFE66D")
        macros.add_widget(self.protein_bar)
        macros.add_widget(self.carbs_bar)
        macros.add_widget(self.fats_bar)
        right.add_widget(macros)
        
        self.add_widget(left)
        self.add_widget(right)
        
        self.calorie_goal = 2000
        self.protein_goal = 150
        self.carbs_goal = 250
        self.fats_goal = 65
    
    def _create_bar(self, label_text, color):
        container = BoxLayout(orientation='vertical', spacing=3)
        
        label_row = BoxLayout(orientation='horizontal', size_hint_y=0.4)
        name = Label(text=label_text, color=get_color_from_hex("#000000"), font_size=14, bold=True, halign="left", size_hint_x=0.5)
        name.bind(size=name.setter('text_size'))
        value = Label(text="0/0g (0%)", color=get_color_from_hex("#000000"), font_size=12, halign="right", size_hint_x=0.5)
        value.bind(size=value.setter('text_size'))
        label_row.add_widget(name)
        label_row.add_widget(value)
        
        prog_container = BoxLayout(size_hint_y=0.6)
        with prog_container.canvas.before:
            Color(0.8, 0.8, 0.8, 1)
            prog_container.bg = RoundedRectangle(radius=[5], pos=prog_container.pos, size=prog_container.size)
        prog_container.bind(pos=lambda o, v: setattr(o.bg, 'pos', v), size=lambda o, v: setattr(o.bg, 'size', v))
        
        bar = BoxLayout()
        with bar.canvas.before:
            Color(*get_color_from_hex(color))
            bar.rect = RoundedRectangle(radius=[5], pos=bar.pos, size=(0, bar.height))
        bar.bind(pos=lambda o, v: setattr(o.rect, 'pos', v))
        
        prog_container.add_widget(bar)
        container.add_widget(label_row)
        container.add_widget(prog_container)
        
        container.value_label = value
        container.bar = bar
        container.color = color
        return container
    
    def _update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size
    
    def _update_bar(self, container, current, goal):
        pct = min((current / goal * 100) if goal > 0 else 0, 100)
        over_pct = max((current / goal * 100) if goal > 0 else 0, 100)
        
        container.value_label.text = f"{int(current)}/{int(goal)}g ({int(over_pct)}%)"
        
        if current > goal:
            container.value_label.color = get_color_from_hex("#8B0000")
            color = "#8B0000"
        else:
            container.value_label.color = get_color_from_hex("#000000")
            color = container.color
        
        bar = container.bar
        with bar.canvas.before:
            bar.canvas.before.clear()
            Color(*get_color_from_hex(color))
            bar.rect = RoundedRectangle(radius=[5], pos=bar.pos, size=(bar.parent.width * (pct / 100), bar.height))
        
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
        
        self.pie_container.clear_widgets()
        self.pie_container.add_widget(PieChart(cal_consumed, cal_remaining, self.calorie_goal))
        Clock.schedule_once(lambda dt: self.pie_container.children[0].draw_chart() if self.pie_container.children else None, 0.1)
        
        self._update_bar(self.protein_bar, consumed.get('proteins', 0), self.protein_goal)
        self._update_bar(self.carbs_bar, consumed.get('carbs', 0), self.carbs_goal)
        self._update_bar(self.fats_bar, consumed.get('fats', 0), self.fats_goal)

# ==============================
# CHAT SCREEN
# ==============================
class ChatScreen(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=10, spacing=10, **kwargs)
        
        self.current_meal_type = "breakfast"
        self.macros_header = MacrosHeader()
        self.add_widget(self.macros_header)
        
        Clock.schedule_once(lambda dt: self.load_macros(), 1.0)
        
        self.scroll = ScrollView(size_hint=(1, 0.75))
        self.chat_history = BoxLayout(orientation="vertical", size_hint_y=None, spacing=10, padding=10)
        self.chat_history.bind(minimum_height=self.chat_history.setter("height"))
        self.scroll.add_widget(self.chat_history)
        self.add_widget(self.scroll)
        
        # Input area
        input_area = BoxLayout(size_hint=(1, 0.12), spacing=10)
        
        input_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=60, spacing=10, padding=[10, 5, 10, 10])
        self.chat_input = TextInput(hint_text="Ask me anything about nutrition...", multiline=False, size_hint_x=0.8,
                                     background_color=(1, 1, 1, 0.1), foreground_color=text_colour, cursor_color=text_colour, font_size=16)
        self.chat_input.bind(on_text_validate=self.send_chat)
        send_btn = Button(text="Send", size_hint_x=0.2, background_normal="", background_color=accent1_colour, color=text_colour, font_size=16)
        send_btn.bind(on_release=self.send_chat)
        input_layout.add_widget(self.chat_input)
        input_layout.add_widget(send_btn)
        
        log_btn = Button(text="Log\nMeal", background_normal="", background_color=accent1_colour, color=text_colour, size_hint=(0.2, 1), bold=True, font_size=16)
        log_btn.bind(on_press=self.open_meal_screen)
        
        input_area.add_widget(input_layout)
        input_area.add_widget(log_btn)
        self.add_widget(input_area)
        
        Clock.schedule_once(lambda dt: self.add_message("Welcome to Diet Tracker!\nTap 'Log Meal' to record your meals via image or manual entry.", False), 0.5)
    
    def send_chat(self, instance):
        msg = self.chat_input.text.strip()
        if not msg:
            return
        
        self.chat_input.text = ""
        self.add_message(msg, True)
        self.add_message("Thinking...", False)
        
        threading.Thread(target=self._process_chat, args=(msg,), daemon=True).start()
    
    def _process_chat(self, msg):
        try:
            context = {'daily_macros': self.total_daily_macros, 'user_id': USER_ID} if hasattr(self, 'total_daily_macros') else None
            response = get_chat_response(msg, context)
            Clock.schedule_once(lambda dt: self.remove_last_message(), 0)
            Clock.schedule_once(lambda dt: self.add_message(response, False), 0)
        except Exception as e:
            traceback.print_exc()
            Clock.schedule_once(lambda dt: self.remove_last_message(), 0)
            Clock.schedule_once(lambda dt: self.add_message("Sorry, I couldn't process that. Please try again.", False), 0)
    
    def load_macros(self):
        def load():
            try:
                db = init_firebase()
                if db is None:
                    Clock.schedule_once(lambda dt: self.macros_header.set_data({'calories': 0, 'proteins': 0, 'carbs': 0, 'fats': 0},
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
                
                daily_goal = user_doc.get('daily_macros_goal', {'calories': 2000, 'proteins': 150, 'carbs': 250, 'fats': 65}) if user_doc else {'calories': 2000, 'proteins': 150, 'carbs': 250, 'fats': 65}
                
                consumed = {'calories': 0, 'proteins': 0, 'carbs': 0, 'fats': 0}
                
                if meal_data:
                    if 'macros_left' in meal_data and isinstance(meal_data['macros_left'], dict):
                        ml = meal_data['macros_left']
                        consumed = {
                            'calories': daily_goal.get('calories', 2000) - ml.get('calories', 0),
                            'proteins': daily_goal.get('proteins', 150) - ml.get('proteins', 0),
                            'carbs': daily_goal.get('carbs', 250) - ml.get('carbs', 0),
                            'fats': daily_goal.get('fats', 65) - ml.get('fats', 0)
                        }
                    else:
                        for meal_type in ['breakfast', 'lunch', 'dinner', 'supper', 'snacks']:
                            if meal_type in meal_data and isinstance(meal_data[meal_type], dict):
                                m = meal_data[meal_type]
                                consumed['calories'] += int(m.get('calories') or m.get('Calories') or 0)
                                consumed['proteins'] += int(m.get('proteins') or m.get('Protein') or 0)
                                consumed['carbs'] += int(m.get('carbs') or m.get('Carbs') or 0)
                                consumed['fats'] += int(m.get('fats') or m.get('Fats') or 0)
                
                self.total_daily_macros = {'Calories': consumed['calories'], 'Protein': consumed['proteins'], 'Carbs': consumed['carbs'], 'Fats': consumed['fats']}
                Clock.schedule_once(lambda dt: self.macros_header.set_data(consumed, daily_goal), 0)
            except:
                traceback.print_exc()
                Clock.schedule_once(lambda dt: self.macros_header.set_data({'calories': 0, 'proteins': 0, 'carbs': 0, 'fats': 0},
                                                                             {'calories': 2000, 'proteins': 150, 'carbs': 250, 'fats': 65}), 0)
        
        threading.Thread(target=load, daemon=True).start()
    
    def add_message(self, msg, is_user=False):
        self.chat_history.add_widget(ChatBubble(msg, is_user=is_user))
        Clock.schedule_once(lambda dt: setattr(self.scroll, 'scroll_y', 0), 0.1)
    
    def remove_last_message(self):
        if self.chat_history.children:
            self.chat_history.remove_widget(self.chat_history.children[0])
    
    def open_meal_screen(self, instance):
        App.get_running_app().root.clear_widgets()
        App.get_running_app().root.add_widget(MealLoggingScreen(self))

# ==============================
# MEAL SURVEY POPUP
# ==============================
class MealSurveyPopup(Popup):
    def __init__(self, callback, **kwargs):
        super().__init__(**kwargs)
        self.callback = callback
        self.title = "Rate Your Current State"
        self.size_hint = (0.9, 0.6)
        self.auto_dismiss = False
        
        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        layout.add_widget(Label(text="Energy Level (1=Very Low, 5=Very High)", size_hint_y=0.2))
        self.energy = Slider(min=1, max=5, value=3, step=1, size_hint_y=0.2)
        self.energy_label = Label(text="3", size_hint_y=0.15)
        self.energy.bind(value=lambda i, v: setattr(self.energy_label, 'text', str(int(v))))
        layout.add_widget(self.energy)
        layout.add_widget(self.energy_label)
        
        layout.add_widget(Label(text="Hunger Level (1=Not Hungry, 5=Very Hungry)", size_hint_y=0.2))
        self.hunger = Slider(min=1, max=5, value=3, step=1, size_hint_y=0.2)
        self.hunger_label = Label(text="3", size_hint_y=0.15)
        self.hunger.bind(value=lambda i, v: setattr(self.hunger_label, 'text', str(int(v))))
        layout.add_widget(self.hunger)
        layout.add_widget(self.hunger_label)
        
        submit = Button(text="Submit", size_hint_y=0.25, background_color=(0.2, 0.6, 1, 1))
        submit.bind(on_press=self.submit)
        layout.add_widget(submit)
        
        self.content = layout
    
    def submit(self, instance):
        self.callback(int(self.energy.value), int(self.hunger.value))
        self.dismiss()

# ==============================
# MEAL LOGGING SCREEN
# ==============================
class MealLoggingScreen(BoxLayout):
    def __init__(self, chat_screen, **kwargs):
        super().__init__(orientation="vertical", padding=20, spacing=15, **kwargs)
        self.chat_screen = chat_screen
        self.selected_image = None
        
        with self.canvas.before:
            Color(*main_colour)
            self.bg = RoundedRectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)
        
        # Header
        header = BoxLayout(size_hint_y=None, height=60, spacing=10)
        back = Button(text="← Back", size_hint_x=0.2, background_normal="", background_color=accent3_colour, color=text_colour, font_size=18)
        back.bind(on_press=self.go_back)
        header.add_widget(back)
        header.add_widget(Label(text="Log Meal", font_size=24, bold=True, color=accent2_colour, size_hint_x=0.8))
        self.add_widget(header)
        
        # Content
        scroll = ScrollView(size_hint=(1, 1))
        content = BoxLayout(orientation='vertical', size_hint_y=None, spacing=20, padding=10)
        content.bind(minimum_height=content.setter('height'))
        
        # Meal type
        meal_section = BoxLayout(orientation='vertical', size_hint_y=None, height=100, spacing=10)
        meal_label = Label(text="Select Meal Type:", font_size=18, bold=True, color=text_colour, size_hint_y=0.4, halign='left')
        meal_label.bind(size=meal_label.setter('text_size'))
        self.meal_spinner = Spinner(text=self.chat_screen.current_meal_type.capitalize(),
                                     values=["Breakfast", "Lunch", "Dinner", "Supper", "Snacks"],
                                     size_hint_y=0.6, background_color=accent2_colour, color=get_color_from_hex("#000000"), font_size=16)
        meal_section.add_widget(meal_label)
        meal_section.add_widget(self.meal_spinner)
        content.add_widget(meal_section)
        
        content.add_widget(Label(text="=" * 50, size_hint_y=None, height=30, color=accent2_colour))
        
        # Image section
        img_section = BoxLayout(orientation='vertical', size_hint_y=None, height=200, spacing=10)
        img_title = Label(text="Option 1: Upload & Analyze Image", font_size=18, bold=True, color=accent2_colour, size_hint_y=0.2, halign='left')
        img_title.bind(size=img_title.setter('text_size'))
        self.img_status = Label(text="No image selected", font_size=14, color=text_colour, size_hint_y=0.2, halign='center')
        
        img_btns = BoxLayout(size_hint_y=0.3, spacing=10)
        upload = Button(text="Upload Image", background_normal="", background_color=accent2_colour, color=get_color_from_hex("#000000"), font_size=16)
        upload.bind(on_press=self.upload_image)
        self.analyze_btn = Button(text="Analyze & Log", background_normal="", background_color=accent1_colour, color=text_colour, font_size=16, disabled=True)
        self.analyze_btn.bind(on_press=self.analyze_image)
        img_btns.add_widget(upload)
        img_btns.add_widget(self.analyze_btn)
        
        img_section.add_widget(img_title)
        img_section.add_widget(self.img_status)
        img_section.add_widget(img_btns)
        content.add_widget(img_section)
        
        content.add_widget(Label(text="=" * 50, size_hint_y=None, height=30, color=accent2_colour))
        
        # Manual entry
        manual = BoxLayout(orientation='vertical', size_hint_y=None, spacing=10)
        manual.bind(minimum_height=manual.setter('height'))
        manual_title = Label(text="Option 2: Enter Manually", font_size=18, bold=True, color=accent2_colour, size_hint_y=None, height=40, halign='left')
        manual_title.bind(size=manual_title.setter('text_size'))
        manual.add_widget(manual_title)
        
        self.inputs = {}
        for field in ["Calories", "Proteins", "Carbs", "Fats"]:
            row = BoxLayout(size_hint_y=None, height=60, spacing=10)
            row.add_widget(Label(text=f"{field}:", size_hint_x=0.3, color=text_colour, font_size=16, bold=True))
            inp = TextInput(hint_text=f"Enter {field.lower()}", multiline=False, input_filter='float', size_hint_x=0.7,
                           background_color=(1, 1, 1, 0.1), foreground_color=text_colour, cursor_color=text_colour, font_size=16)
            self.inputs[field.lower()] = inp
            row.add_widget(inp)
            manual.add_widget(row)
        
        manual_btn = Button(text="Log Meal Manually", size_hint_y=None, height=60, background_normal="", background_color=accent1_colour, color=text_colour, font_size=18, bold=True)
        manual_btn.bind(on_press=self.submit_manual)
        manual.add_widget(manual_btn)
        content.add_widget(manual)
        
        scroll.add_widget(content)
        self.add_widget(scroll)
    
    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size
    
    def go_back(self, instance):
        App.get_running_app().root.clear_widgets()
        App.get_running_app().root.add_widget(self.chat_screen)
    
    def upload_image(self, instance):
        content = BoxLayout(orientation="vertical", spacing=10)
        chooser = FileChooserListView(path=".", filters=["*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"])
        
        btns = BoxLayout(size_hint_y=None, height=50, spacing=10)
        select = Button(text="Select", background_color=accent1_colour)
        cancel = Button(text="Cancel", background_color=accent3_colour)
        btns.add_widget(select)
        btns.add_widget(cancel)
        
        content.add_widget(chooser)
        content.add_widget(btns)
        
        popup = Popup(title="Select a meal image", content=content, size_hint=(0.9, 0.9))
        
        def on_select(i):
            if chooser.selection:
                self.selected_image = chooser.selection[0]
                filename = self.selected_image.replace('\\', '/').split('/')[-1]
                self.img_status.text = f"Selected: {filename}"
                self.analyze_btn.disabled = False
                popup.dismiss()
        
        select.bind(on_press=on_select)
        cancel.bind(on_press=lambda i: popup.dismiss())
        popup.open()
    
    def analyze_image(self, instance):
        if not self.selected_image:
            return
        
        meal_type = self.meal_spinner.text.lower()
        self.analyze_btn.disabled = True
        self.img_status.text = "Analyzing... (10-30 seconds)"
        
        def analyze():
            try:
                nutrition = estimate_nutrition(self.selected_image)
                
                if not nutrition:
                    Clock.schedule_once(lambda dt: setattr(self.img_status, 'text', "Analysis failed. Try again."), 0)
                    Clock.schedule_once(lambda dt: setattr(self.analyze_btn, 'disabled', False), 0)
                    return
                
                today = datetime.date.today().strftime("%Y-%m-%d")
                success = upload_meal(USER_ID, meal_type, nutrition, today)
                
                if success:
                    Clock.schedule_once(lambda dt: setattr(self.img_status, 'text', "Logged successfully!"), 0)
                    self.chat_screen.current_meal_type = meal_type
                    
                    result = f"{meal_type.capitalize()} logged:\nCalories: {nutrition.get('Calories')} kcal\nProtein: {nutrition.get('Protein')} g\nCarbs: {nutrition.get('Carbs')} g\nFats: {nutrition.get('Fats')} g"
                    Clock.schedule_once(lambda dt: self.chat_screen.add_message(result, False), 0)
                    Clock.schedule_once(lambda dt: self.chat_screen.load_macros(), 1.5)
                    
                    def on_survey(energy, hunger):
                        Clock.schedule_once(lambda dt: self.chat_screen.add_message("Generating tips...", False), 0)
                        def tips():
                            try:
                                time.sleep(1.0)
                                advice = handle_logged_meal(meal_type, nutrition, self.chat_screen.total_daily_macros, energy, hunger)
                                Clock.schedule_once(lambda dt: self.chat_screen.remove_last_message(), 0)
                                msg = advice.strip() if advice else "All nutrients within range."
                                Clock.schedule_once(lambda dt: self.chat_screen.add_message(msg, False), 0)
                            except:
                                traceback.print_exc()
                                Clock.schedule_once(lambda dt: self.chat_screen.remove_last_message(), 0)
                        threading.Thread(target=tips, daemon=True).start()
                    
                    Clock.schedule_once(lambda dt: MealSurveyPopup(callback=on_survey).open(), 1.0)
                    Clock.schedule_once(lambda dt: self.go_back(None), 2.5)
                else:
                    Clock.schedule_once(lambda dt: setattr(self.img_status, 'text', "Upload failed. Try again."), 0)
                    Clock.schedule_once(lambda dt: setattr(self.analyze_btn, 'disabled', False), 0)
            except:
                traceback.print_exc()
                Clock.schedule_once(lambda dt: setattr(self.img_status, 'text', "Error occurred"), 0)
                Clock.schedule_once(lambda dt: setattr(self.analyze_btn, 'disabled', False), 0)
        
        threading.Thread(target=analyze, daemon=True).start()
    
    def submit_manual(self, instance):
        meal_type = self.meal_spinner.text.lower()
        
        if not self.inputs["calories"].text.strip():
            self.img_status.text = "Please enter at least calories!"
            return
        
        try:
            nutrition = {
                "Calories": int(float(self.inputs["calories"].text)) if self.inputs["calories"].text else 0,
                "Protein": int(float(self.inputs["proteins"].text)) if self.inputs["proteins"].text else 0,
                "Carbs": int(float(self.inputs["carbs"].text)) if self.inputs["carbs"].text else 0,
                "Fats": int(float(self.inputs["fats"].text)) if self.inputs["fats"].text else 0,
            }
        except ValueError:
            self.img_status.text = "Invalid numbers entered!"
            return
        
        today = datetime.date.today().strftime("%Y-%m-%d")
        success = upload_meal(USER_ID, meal_type, nutrition, today)
        
        if success:
            self.chat_screen.current_meal_type = meal_type
            
            result = f"{meal_type.capitalize()} logged:\nCalories: {nutrition.get('Calories')} kcal\nProtein: {nutrition.get('Protein')} g\nCarbs: {nutrition.get('Carbs')} g\nFats: {nutrition.get('Fats')} g"
            self.chat_screen.add_message(result, False)
            Clock.schedule_once(lambda dt: self.chat_screen.load_macros(), 1.5)
            
            def on_survey(energy, hunger):
                Clock.schedule_once(lambda dt: self.chat_screen.add_message("Generating tips...", False), 0)
                def tips():
                    try:
                        time.sleep(1.0)
                        advice = handle_logged_meal(meal_type, nutrition, self.chat_screen.total_daily_macros, energy, hunger)
                        Clock.schedule_once(lambda dt: self.chat_screen.remove_last_message(), 0)
                        msg = advice.strip() if advice else "All nutrients within range."
                        Clock.schedule_once(lambda dt: self.chat_screen.add_message(msg, False), 0)
                    except:
                        traceback.print_exc()
                        Clock.schedule_once(lambda dt: self.chat_screen.remove_last_message(), 0)
                threading.Thread(target=tips, daemon=True).start()
            
            MealSurveyPopup(callback=on_survey).open()
            Clock.schedule_once(lambda dt: self.go_back(None), 2.5)
        else:
            self.img_status.text = "Upload failed. Please try again."

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
                Clock.schedule_once(lambda dt: self.loading.update_status("Connecting to Firebase...", 20), 0)
                db = init_firebase()
                if db is None:
                    print("[WARNING] Firebase failed, continuing...")
                
                Clock.schedule_once(lambda dt: self.loading.update_status("Loading AI model... (30-60 sec)", 50), 0)
                load_model()
                
                Clock.schedule_once(lambda dt: self.loading.update_status("Model loaded ✓", 90), 0)
                Clock.schedule_once(lambda dt: self.loading.update_status("Starting app...", 95), 0)
                Clock.schedule_once(lambda dt: self.switch_to_main(), 0.5)
            except:
                traceback.print_exc()
                Clock.schedule_once(lambda dt: self.loading.update_status("Error occurred", 0), 0)
        
        threading.Thread(target=init, daemon=True).start()
    
    def switch_to_main(self):
        self.loading.update_status("Ready!", 100)
        self.root.clear_widgets()
        self.root.add_widget(ChatScreen())

if __name__ == "__main__":
    DietChatApp().run()